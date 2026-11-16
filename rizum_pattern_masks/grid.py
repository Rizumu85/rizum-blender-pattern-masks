# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Rizum
"""Checkerboard woven into the fabric.

The lines of a checked fabric are its threads: one set runs along the marked
edge (the rows), the other runs away from it (the columns). When the fabric
drapes, the threads bend and lean, but each square keeps its size measured
along the threads. On a quad mesh the edge loops show the threads, so the
squares follow them, as a checker is painted by hand over the wireframe: rows
follow the loops that run along the marked edge, columns the loops that run
away from it, and where the loops lean the squares lean with them
(parallelograms). Triangles and n-gons carry the threads on from their
neighbours.

The directions are worked out on the UV layout, which lies flat (carried over
the folded surface itself they would drift round every pleat), starting at the
marked edge, and then laid onto the 3D faces, where the squares are measured
(real size). Where the piece flares the columns spread apart, and where the
loops fan out the rows do, so neither can keep both its width and its
direction. Like a hand-painted checker they keep both, and a new pair of
columns (or rows) starts where the piece has widened by one pair: both
coordinates are stripe patterns (after Knoeppel et al. 2015), lined up so a
row boundary runs along the marked edge. Where a pair starts the squares
fork, drawn together tightly so the fork is a small point. Each corner's place
in the pattern is worked out from the steps expected along its edges, averaged
over the triangles around each edge, so a thin sliver cannot pick the wrong
square.

The squares fill the UV islands that have a marked edge, and run on across UV
seams inside them.
"""

import heapq
import math
import zlib

import numpy as np

from . import contour


# stripe solver effort: inverse iterations, and conjugate gradient steps per
# inverse iteration (more changes little: measured on real skirt pieces)
STRIPE_OUTER = 6
STRIPE_INNER = 120
STRIPE_RELAX = 8
STRIPE_MU = 10.0           # how tightly a fork is drawn together (per cell)
FLAT_ROUNDS = 4            # "unrolled": rounds of flattening (rotation fit, then layout);
#                            more changes nothing visible (measured on two skirt pieces)


# ---------------------------------------------------------------------------
# small solvers


def _cg(apply, b, x, free, diag, iters, tol):
    """Preconditioned conjugate gradients for apply(x) = b on the ``free``
    entries (the others keep their value in x). Real or complex Hermitian."""
    x = x.copy()
    r = b - apply(x)
    r[~free] = 0.0
    pre = np.where(free, 1.0 / np.maximum(diag, 1e-300), 0.0)
    z = pre * r
    p = z.copy()
    rz = np.vdot(r, z).real
    r0 = math.sqrt(max(np.vdot(b * free, b * free).real, 1e-300))
    for _ in range(iters):
        if math.sqrt(max(np.vdot(r, r).real, 0.0)) <= tol * r0:
            break
        q = apply(p)
        q[~free] = 0.0
        den = np.vdot(p, q).real
        if den <= 0:
            break
        a = rz / den
        x += a * p
        r -= a * q
        z = pre * r
        rz2 = np.vdot(r, z).real
        p = z + (rz2 / max(rz, 1e-300)) * p
        rz = rz2
    return x


def _bc(idx, val, n):
    """np.bincount that takes complex weights."""
    if np.iscomplexobj(val):
        return np.bincount(idx, val.real, n) + 1j * np.bincount(idx, val.imag, n)
    return np.bincount(idx, val, n)


def _wrap(a):
    return (a + math.pi) % (2.0 * math.pi) - math.pi


def _unit(v):
    return v / np.maximum(np.linalg.norm(v, axis=-1), 1e-30)[..., None]


# ---------------------------------------------------------------------------
# helpers on the topology


def _edge_triangles(topo, a, b):
    """Every (edge index, triangle, a's corner, b's corner) for edges a-b."""
    nw = topo._nw
    key = np.minimum(a, b) * nw + np.maximum(a, b)
    lo = np.searchsorted(topo._ks, key, "left")
    hi = np.searchsorted(topo._ks, key, "right")
    cnt = hi - lo
    e = np.repeat(np.arange(len(a)), cnt)
    pos = np.repeat(lo, cnt) + (np.arange(cnt.sum()) - np.repeat(np.cumsum(cnt) - cnt, cnt))
    loop = topo._order[pos]
    t, j = loop // 3, loop % 3
    j2 = (j + 1) % 3
    fwd = topo.tri[t, j] == a[e]
    ja = np.where(fwd, j, j2)
    jb = np.where(fwd, j2, j)
    return e, t, ja, jb


def _quads(topo, faces, local):
    """For the triangles ``faces`` that are half of a quad: (is quad, the other
    half's local index or -1, the quad's corners a, b, c, w in order; its
    pairs of opposite edges are a->b with w->c, and b->c with a->w)."""
    F = len(faces)
    quad = np.zeros(F, bool)
    sib = np.full(F, -1, np.int64)
    qv = np.full((F, 4), -1, np.int64)
    tp = topo.tri_poly
    per_poly = np.bincount(tp, minlength=int(tp.max()) + 1 if len(tp) else 1)
    nb = topo.nbr[faces]
    same = (nb >= 0) & (tp[np.maximum(nb, 0)] == tp[faces][:, None])
    idx = np.nonzero((per_poly[tp[faces]] == 2) & (same.sum(1) == 1))[0]
    if not len(idx):
        return quad, sib, qv
    k = np.argmax(same[idx], axis=1)
    T = topo.tri[faces[idx]]
    u = nb[idx, k]
    rows = np.arange(len(idx))
    a, b, c = T[rows, (k + 1) % 3], T[rows, (k + 2) % 3], T[rows, k]
    U = topo.tri[u]
    w = np.where((U[:, 0] != a) & (U[:, 0] != c), U[:, 0],
                 np.where((U[:, 1] != a) & (U[:, 1] != c), U[:, 1], U[:, 2]))
    ul = local[u]
    ok = ul >= 0
    quad[idx[ok]] = True
    sib[idx[ok]] = ul[ok]
    qv[idx] = np.stack([a, b, c, w], 1)
    return quad, sib, qv


# ---------------------------------------------------------------------------
# the field


class Layout:
    """Square coordinates for one cell size and angle: per triangle corner of
    ``faces`` (x, y) in scene units, exact up to whole two-square periods per
    triangle (so the colours agree everywhere).

    A triangle where a new pair of squares starts holds a knot: its corners'
    coordinates do not close up around it. Inside such a triangle the field is
    followed instead (``knot``, per coordinate: the field at the corners with
    the expected run along ``g`` taken out), so the knot is a small point
    rather than a sliver of wrong squares."""

    def __init__(self, faces, xy, knot=None, chi=None, g=None, k=None, p0=None,
                 continuous=False):
        self.faces = faces
        self.xy = xy
        self.continuous = continuous           # one field over the piece (no periods)
        F = len(faces)
        self.knot = knot if knot is not None else np.zeros((F, 2), bool)
        self.chi = chi
        self.g = g
        self.k = k
        self.p0 = p0

    def at(self, rows, w, p):
        """(x, y) at points with barycentric w (n, 3) and 3D position p (n, 3)
        in triangles ``rows`` (indices into faces)."""
        xy = (w[:, :, None] * self.xy[rows]).sum(1)
        for c in (0, 1):
            m = self.knot[rows, c]
            if m.any():
                r = rows[m]
                z = (w[m] * self.chi[c][r]).sum(1)
                d = ((p[m] - self.p0[r]) * self.g[c][r]).sum(1)
                xy[m, c] = (np.angle(z) / self.k + d)
        return xy


class Field:
    """What does not depend on the square size: the region and its threads
    (per triangle, as the gradients gs and gt that measure along them)."""

    def __init__(self):
        self.faces = np.zeros(0, np.int64)
        self._layouts = {}

    def layout(self, cell, angle, mode="loops"):
        """mode: "loops" (squares follow the mesh's loops, forking where the
        piece widens) or "unrolled" (the piece unrolled on its marked edge:
        the squares stay square but grow where it widens, nothing forks)."""
        key = (round(float(cell), 9), round(float(angle), 6), str(mode))
        hit = self._layouts.get(key)
        if hit is None:
            if len(self._layouts) > 6:
                self._layouts.clear()
            hit = self._layouts[key] = self._make_layout(cell, angle, mode)
        return hit

    # -- per square size

    def _make_layout(self, cell, angle, mode):
        if not len(self.faces) or cell <= 0:
            return Layout(np.zeros(0, np.int64), np.zeros((0, 3, 2)))
        c, s = math.cos(angle), math.sin(angle)
        gx = c * self.gs + s * self.gt
        gy = -s * self.gs + c * self.gt
        if mode == "unrolled":
            u, v = self._unrolled()
            xy = np.stack([c * u + s * v, -s * u + c * v], 2)
            return Layout(self.faces, xy, None, (None, None), (gx, gy), math.pi / cell,
                          self.P[:, 0], continuous=True)
        x, kx, cx = self._stripes(gx, c * self.anchor_s, cell)
        y, ky, cy = self._stripes(gy, -s * self.anchor_s, cell)
        return Layout(self.faces, np.stack([x, y], 2), np.stack([kx, ky], 1), (cx, cy),
                      (gx, gy), math.pi / cell, self.P[:, 0])

    def _unrolled(self):
        """Per triangle corner (x, y), scene units: the piece unrolled on its
        marked edge. The cloth is first laid out flat (_flat), then bent
        straight by a conformal map (log-polar about the circle the marked
        edge lies on): the edge becomes the line y = 0 with x its length
        along it, the columns run straight down from it, and the squares
        stay square but grow away from the edge as the piece widens. Nothing
        forks."""
        hit = getattr(self, "_flat_log", None)
        if hit is not None:
            return hit
        xy = self._flat()
        u, v = xy[0].copy(), xy[1].copy()
        isl = self.isl_f
        isa = np.zeros(self.nv, bool)
        isa[self.anchor_v] = True
        am = isa[self.tri]                                   # anchor corners
        size = max(float(np.ptp(u)), float(np.ptp(v)), 1e-9)
        for i in range(int(isl.max()) + 1):
            fm = isl == i
            m = fm[:, None] & am
            if m.sum() < 3:
                continue
            x, y = u[m], v[m]
            # the circle through the marked edge (least squares)
            Amat = np.stack([x, y, np.ones_like(x)], 1)
            try:
                D, E, Fc = np.linalg.lstsq(Amat, -(x * x + y * y), rcond=None)[0]
            except np.linalg.LinAlgError:
                continue
            cx, cy = -D / 2.0, -E / 2.0
            r0sq = cx * cx + cy * cy - Fc
            if r0sq <= 0 or math.sqrt(r0sq) > 50.0 * size:
                continue                                     # straight enough already
            r0 = math.sqrt(r0sq)
            X, Y = u[fm] - cx, v[fm] - cy
            th = np.arctan2(Y, X)
            # angles about the edge's middle, cut where the piece has no
            # cloth (the widest empty gap round the circle)
            s_ = self.anchor_s[self.tri][m]
            th_a = np.arctan2(y - cy, x - cx)
            mid = th_a[np.argsort(s_)[len(s_) // 2]]
            th = (th - mid) % (2.0 * math.pi)
            th_a = (th_a - mid) % (2.0 * math.pi)
            srt = np.sort(th.reshape(-1))
            gaps = np.diff(np.concatenate([srt, [srt[0] + 2.0 * math.pi]]))
            k = int(np.argmax(gaps))
            cut_at = (srt[k] + 0.5 * gaps[k]) % (2.0 * math.pi)
            th = np.where(th >= cut_at, th - 2.0 * math.pi, th)
            th_a = np.where(th_a >= cut_at, th_a - 2.0 * math.pi, th_a)
            # u runs with the length along the edge, v = 0 on it
            sgn = 1.0 if float(np.corrcoef(th_a, s_)[0, 1]) >= 0 else -1.0
            s_mid = float(s_[np.argsort(s_)[len(s_) // 2]])
            u[fm] = s_mid + sgn * r0 * th
            v[fm] = r0 * np.log(np.maximum(np.hypot(X, Y), 1e-9) / r0)
        # rows count away from the edge
        Gv = np.einsum("fk,fkd->fd", v, self.G)
        if float(((Gv * self.gt).sum(1) * self.A).sum()) < 0:
            v = -v
        self._flat_log = (u, v)
        return self._flat_log

    def _flat(self):
        """Per triangle corner (x, y), scene units: the cloth laid out flat
        (each UV island on its own, flattened with as little stretch as
        possible: rotations fitted per face, then the layout that best
        follows them, a few rounds), turned and placed so that the marked
        edge starts at (its length along it, 0) running along x. A square
        grid on it is a check printed on the fabric before it was sewn."""
        hit = getattr(self, "_flat_xy", None)
        if hit is not None:
            return hit
        tri, P, A = self.tri, self.P, self.A
        F = len(tri)
        n = self.n_f
        if not hasattr(self, "G"):
            self.G = np.stack([np.cross(n, P[:, (j + 2) % 3] - P[:, (j + 1) % 3])
                               / (2.0 * A)[:, None] for j in range(3)], 1)
        G = self.G
        isl = self.isl_f
        # vertices split between islands (a seam in UV is a cut in the cloth)
        key = isl[:, None] * (self.nv + 1) + tri
        uk, tri2 = np.unique(key, return_inverse=True)
        tri2 = tri2.reshape(F, 3)
        nv2 = len(uk)
        isl_v = uk // (self.nv + 1)
        # start from the UV layout at true scale (mirrored islands turned over)
        uv = self.uvr
        E3 = np.stack([P[:, 1] - P[:, 0], P[:, 2] - P[:, 0]], 1)
        Eu = np.stack([uv[:, 1] - uv[:, 0], uv[:, 2] - uv[:, 0]], 1)
        det = Eu[:, 0, 0] * Eu[:, 1, 1] - Eu[:, 0, 1] * Eu[:, 1, 0]
        n3 = np.cross(E3[:, 0], E3[:, 1])
        mirrored = np.sign(det) * np.sign((n3 * n).sum(1)) < 0
        nisl = int(isl.max()) + 1
        flip = np.bincount(isl, A * mirrored, nisl) > 0.5 * np.bincount(isl, A, nisl)
        uv = uv.copy()
        uv[flip[isl], :, 1] *= -1.0
        cnt = np.bincount(tri2.reshape(-1), minlength=nv2)
        u = np.bincount(tri2.reshape(-1), uv[..., 0].reshape(-1), nv2) / np.maximum(cnt, 1)
        v = np.bincount(tri2.reshape(-1), uv[..., 1].reshape(-1), nv2) / np.maximum(cnt, 1)
        e1 = _unit(E3[:, 0])
        e2 = np.cross(n, e1)
        pin = np.array([int(np.nonzero(isl_v == i)[0][0]) for i in range(nisl)])
        isa = np.zeros(self.nv, bool)
        isa[self.anchor_v] = True
        isa2 = np.zeros(nv2, bool)
        isa2[tri2.reshape(-1)] = isa[tri.reshape(-1)]
        s_v = np.zeros(nv2)
        s_v[tri2.reshape(-1)] = self.anchor_s[tri.reshape(-1)]
        progress = getattr(self, "progress", None)
        for rnd in range(FLAT_ROUNDS):
            if progress is not None:
                progress(rnd, FLAT_ROUNDS)
            # early rounds need no precision: the fit moves on anyway
            last = rnd == FLAT_ROUNDS - 1
            Gu = np.einsum("fk,fkd->fd", u[tri2], G)
            Gv = np.einsum("fk,fkd->fd", v[tri2], G)
            a, b = (Gu * e1).sum(1), (Gu * e2).sum(1)
            c_, d = (Gv * e1).sum(1), (Gv * e2).sum(1)
            # the rotation nearest each face's map (p, q) ~ (a + d, c - b)
            p, q = a + d, c_ - b
            ln = np.maximum(np.hypot(p, q), 1e-12)
            p, q = p / ln, q / ln
            gu = p[:, None] * e1 - q[:, None] * e2
            gv = q[:, None] * e1 + p[:, None] * e2
            u, v = _poisson2(tri2, G, A, nv2, gu, gv, pin, u, v,
                             iters=800 if last else 150, tol=1e-7 if last else 1e-4)
        # turn and place each island on its marked edge
        Gu = np.einsum("fk,fkd->fd", u[tri2], G)
        Gv = np.einsum("fk,fkd->fd", v[tri2], G)
        rf = np.stack([(Gu * self.r3).sum(1), (Gv * self.r3).sum(1)], 1)   # rows, flat
        for i in range(nisl):
            m = isl_v == i
            fm = isl == i
            av = np.nonzero(m & isa2)[0]
            if len(av) >= 2:
                # x runs along the marked edge where it is at its middle (a
                # flat grid can lie along a curved edge in one place only)
                o = av[np.argsort(s_v[av])]
                mid = len(o) // 2
                a_, b_ = o[max(mid - 1, 0)], o[min(mid + 1, len(o) - 1)]
                ang = math.atan2(v[b_] - v[a_], u[b_] - u[a_])
                v0 = o[mid]
            else:
                w = (rf[fm] * A[fm][:, None]).sum(0)
                ang = math.atan2(w[1], w[0])
                v0 = None
            ca, sa = math.cos(-ang), math.sin(-ang)
            x_, y_ = u[m], v[m]
            u[m], v[m] = ca * x_ - sa * y_, sa * x_ + ca * y_
            if v0 is not None:
                u[m] += s_v[v0] - u[v0]
                v[m] -= v[v0]
            else:
                u[m] -= u[m].mean()
                v[m] -= v[m].mean()
        # rows count away from the edge, as in the other layouts
        Gv = np.einsum("fk,fkd->fd", v[tri2], G)
        if float(((Gv * self.gt).sum(1) * A).sum()) < 0:
            v = -v
        self._flat_xy = (u[tri2], v[tri2])
        return self._flat_xy

    def _stripes(self, g, anchor, cell):
        """Per corner coordinate whose gradient is close to g (per triangle),
        exact up to whole periods of two squares: the phase of the smoothest
        unit field psi with psi_j ~ exp(i w_ij) psi_i along the edges."""
        k = math.pi / cell                                  # phase per unit length
        tri, P, nv = self.tri, self.P, self.nv
        # target phase change along each triangle edge (from that triangle's
        # g), gathered per edge: c = sum of w exp(i w_ij)
        kk = np.arange(len(tri)).repeat(3)
        D = P[kk, self.EJk] - P[kk, self.EIk]
        om = k * (g[kk] * D).sum(1) * self.esign
        ne = len(self.UI)
        c = (np.bincount(self.emap, self.Wst * np.cos(om), ne)
             + 1j * np.bincount(self.emap, self.Wst * np.sin(om), ne))
        I, J = self.UI, self.UJ
        M = self.mass
        eps = 0.1 * (math.pi / max(self.size, 1e-9)) ** 2
        diag = self.Wdiag + eps * M
        cc = np.conj(c)

        def A(v):
            return diag * v - _bc(I, cc * v[J], nv) - _bc(J, c * v[I], nv)

        free = np.ones(nv, bool)
        psi = np.ones(nv, complex)
        for _ in range(STRIPE_OUTER):
            y = _cg(A, M * psi, psi, free, diag, STRIPE_INNER, 1e-5)
            nrm = math.sqrt(max(np.vdot(y, M * y).real, 1e-300))
            psi = y / nrm
        # The smoothest field above tends to gather in one part of the piece
        # and fade elsewhere, where its phase then wanders. Relax it with
        # every point held near unit length instead: where a pair of squares
        # must start, that makes a small knot rather than a long tear.
        mu = (STRIPE_MU / cell) ** 2 * M
        diag2 = diag + mu

        def A2(v):
            return A(v) + mu * v

        for _ in range(STRIPE_RELAX):
            u = psi / np.maximum(np.abs(psi), 1e-12)
            psi = _cg(A2, mu * u, u, free, diag2, STRIPE_INNER, 1e-5)
        # turn the whole pattern so it best matches the anchor along the edge
        av = self.anchor_v
        if len(av):
            z = np.exp(1j * k * anchor[av]) * np.conj(psi[av]) / np.maximum(np.abs(psi[av]),
                                                                            1e-300)
            psi = psi * np.exp(1j * np.angle(z.sum()))
        ph = np.angle(psi)[tri]                              # (F, 3)
        # The expected phase step along each edge, from all the triangles
        # around it (by area): a thin sliver's own direction is unreliable,
        # and taken alone it can pick the wrong whole period (a thin streak
        # of the wrong colour along the sliver).
        Ar = np.repeat(self.A, 3)
        avg = (np.bincount(self.emap, Ar * om, ne)
               / np.maximum(np.bincount(self.emap, Ar, ne), 1e-30))
        step = (avg[self.emap] * self.esign).reshape(-1, 3)
        w01, w12, w20 = step[:, 2], step[:, 0], step[:, 1]   # edges 0-1, 1-2, 2-0
        out = np.empty_like(ph)
        out[:, 0] = ph[:, 0]
        out[:, 1] = ph[:, 0] + w01 + _wrap(ph[:, 1] - ph[:, 0] - w01)
        out[:, 2] = ph[:, 0] - w20 + _wrap(ph[:, 2] - ph[:, 0] + w20)
        run = [np.zeros(len(tri)), w01, -w20]
        # a knot: going round the triangle the phase does not close up
        turn = (_wrap(ph[:, 1] - ph[:, 0] - w01) + _wrap(ph[:, 2] - ph[:, 1] - w12)
                + _wrap(ph[:, 0] - ph[:, 2] - w20))
        knot = np.abs(turn) > math.pi
        chi = psi[tri] * np.exp(-1j * np.stack(run, 1))      # the expected run taken out
        return out / k, knot, chi


SMOOTH_STEPS = 24          # how far (in faces) the threads are evened out
SMOOTH_PULL = 0.25         # how hard a quad holds on to its own edges


def _smooth_threads(ar, ad, quad, nbl, th_i, th_j, hand):
    """Even out the row and column angles (per face, in UV) over their
    neighbours: a hand-painted checker follows the loops, not every kink of
    every quad, and does not turn sharply where thin wedges cut in. Quads keep
    a pull towards their own edges, so the squares still follow the loops."""
    m = nbl >= 0
    j = np.where(m, nbl, 0)
    same = hand[:, None] == hand[j]
    # a neighbour's angle a seen from face i: a + ti - tj, or ti + tj - a
    # where the UV is mirrored between them
    rot = np.exp(1j * (th_i - th_j))
    mir = np.exp(1j * (th_i + th_j))
    w_self = np.where(quad, 1.0 + SMOOTH_PULL * 3.0, 1.0)
    out = []
    for a0 in (ar, ad):
        z0 = np.exp(1j * a0)
        anchor = np.where(quad, z0, 0.0)
        z = z0.copy()
        for _ in range(SMOOTH_STEPS):
            zj = z[j]
            seen = np.where(same, zj * rot, np.conj(zj) * mir)
            acc = w_self * z + SMOOTH_PULL * 3.0 * anchor + (seen * m).sum(1)
            acc -= np.where(quad, SMOOTH_PULL * 3.0 * z, 0.0)     # pull replaces self
            ln = np.abs(acc)
            z = np.where(ln > 1e-9, acc / np.maximum(ln, 1e-12), z)
        out.append(np.angle(z))
    ar2, ad2 = out
    # keep the two threads apart (a square, not a sliver)
    sn = np.sin(ad2 - ar2)
    thin = np.abs(sn) < 0.5
    ad2 = np.where(thin, ar2 + np.where(sn >= 0, 0.5, -0.5) * math.pi, ad2)
    return ar2, ad2


def _poisson(tri, G, A, nv, g, fixed, fixed_val, iters=4000, x0=None, tol=1e-9):
    """Per vertex scalar whose gradient is closest to g (least squares by
    area), equal to fixed_val on ``fixed``; from x0 when given."""
    def K(v):
        gr = np.einsum("fk,fkd->fd", v[tri], G)
        out = np.zeros(nv)
        for k in range(3):
            out += np.bincount(tri[:, k], A * (G[:, k] * gr).sum(1), nv)
        return out

    b = np.zeros(nv)
    diag = np.zeros(nv)
    for k in range(3):
        b += np.bincount(tri[:, k], A * (G[:, k] * g).sum(1), nv)
        diag += np.bincount(tri[:, k], A * (G[:, k] ** 2).sum(1), nv)
    free = np.ones(nv, bool)
    free[fixed] = False
    x = np.zeros(nv) if x0 is None else x0.copy()
    x[fixed] = fixed_val
    return _cg(K, b, x, free, np.maximum(diag, 1e-30), iters, tol)


def _sum3(tri, nv, ws):
    """Per vertex sum of the complex per-corner values ws[k] (k = corner)."""
    out = np.zeros(nv, complex)
    for k, w in enumerate(ws):
        out += np.bincount(tri[:, k], w.real, nv) + 1j * np.bincount(tri[:, k], w.imag, nv)
    return out


def _poisson2(tri, G, A, nv, gu, gv, fixed, u0, v0, iters, tol):
    """Two scalars at once (as one complex one: the same matrix), their
    gradients closest to gu and gv, from u0 and v0, which they keep on
    ``fixed``."""
    def K(x):
        gr = np.einsum("fk,fkd->fd", x[tri], G)
        return _sum3(tri, nv, [A * (G[:, k_] * gr).sum(1) for k_ in range(3)])

    b = _sum3(tri, nv, [A * (G[:, k_] * (gu + 1j * gv)).sum(1) for k_ in range(3)])
    diag = np.zeros(nv)
    for k in range(3):
        diag += np.bincount(tri[:, k], A * (G[:, k] ** 2).sum(1), nv)
    free = np.ones(nv, bool)
    free[fixed] = False
    x = _cg(K, b, u0 + 1j * v0, free, np.maximum(diag, 1e-30), iters, tol)
    return x.real, x.imag


def fabric_coords(topo, chains):
    """The Field of a grid layer whose marked edges are ``chains``."""
    out = Field()
    if topo.uv is None or not chains:
        return out
    ea, eb = [], []
    for ids, closed in chains:
        ids = np.asarray(ids, np.int64)
        if len(ids) < 2:
            continue
        ea.append(ids if closed else ids[:-1])
        eb.append(np.roll(ids, -1) if closed else ids[1:])
    if not ea:
        return out
    ea, eb = np.concatenate(ea), np.concatenate(eb)
    e, t, ja, jb = _edge_triangles(topo, ea, eb)
    if not len(t):
        return out
    # the region: UV islands with a marked edge, the parts of them joined to it
    charts = contour.charts_for(topo)
    isl = charts.isl
    inreg = np.isin(isl, np.unique(isl[t]))
    nbr = topo.nbr
    seen = np.zeros(len(topo.tri), bool)
    seen[t] = True
    front = np.unique(t)
    while len(front):
        nb = nbr[front].reshape(-1)
        nb = np.unique(nb[nb >= 0])
        nb = nb[inreg[nb] & ~seen[nb]]
        seen[nb] = True
        front = nb
    faces = np.nonzero(seen)[0]
    verts, tri = np.unique(topo.tri[faces], return_inverse=True)
    tri = tri.reshape(-1, 3)
    nv, F = len(verts), len(faces)
    X = topo.co[verts]
    P = X[tri]
    n = topo.n[faces]
    n_o = topo.n_o[faces]
    A = topo.area[faces]
    # cotan weights
    cot = np.empty((F, 3))
    for j in range(3):
        p0, p1, p2 = P[:, j], P[:, (j + 1) % 3], P[:, (j + 2) % 3]
        u, v = p1 - p0, p2 - p0
        cot[:, j] = (u * v).sum(1) / np.maximum(np.linalg.norm(np.cross(u, v), axis=1), 1e-300)
    EIk = np.tile([1, 2, 0], F)                         # edge opposite corner j
    EJk = np.tile([2, 0, 1], F)
    ff = np.arange(F).repeat(3)
    EI, EJ = tri[ff, EIk], tri[ff, EJk]
    Wk = 0.5 * cot.reshape(-1)

    fld = out
    fld.faces, fld.tri, fld.P, fld.nv = faces, tri, P, nv
    fld.EIk, fld.EJk = EIk, EJk
    fld.Wst = np.maximum(Wk, 0.05)                      # stripes: no negative weights
    ekey = np.minimum(EI, EJ) * nv + np.maximum(EI, EJ)
    uk, emap = np.unique(ekey, return_inverse=True)
    fld.UI, fld.UJ = uk // nv, uk % nv
    fld.emap = emap.reshape(-1)
    fld.esign = np.where(EI < EJ, 1.0, -1.0)            # triangle edge runs UI -> UJ
    We = np.bincount(fld.emap, fld.Wst, len(uk))
    fld.Wdiag = np.bincount(fld.UI, We, nv) + np.bincount(fld.UJ, We, nv)
    fld.mass = np.maximum(np.bincount(tri.reshape(-1), np.repeat(A / 3.0, 3), nv), 1e-30)
    fld.size = float(np.ptp(X, axis=0).max()) if nv else 1.0

    # the marked edge in local numbering, with lengths along it
    loc = {int(v): i for i, v in enumerate(verts.tolist())}
    la = np.array([loc.get(int(v), -1) for v in ea.tolist()])
    lb = np.array([loc.get(int(v), -1) for v in eb.tolist()])
    ok = (la >= 0) & (lb >= 0)
    have = np.zeros(nv, bool)
    have[la[ok]] = True
    have[lb[ok]] = True
    fld.anchor_v = np.nonzero(have)[0]

    # The threads: a row and a column direction per face, carried out from
    # the marked edge face by face. They are worked out on the UV layout,
    # which lies flat (on the folded surface, directions drift as they are
    # carried round the pleats), then laid onto the 3D faces. On a quad
    # both snap to the quad's own pairs of opposite edges (the one closest to
    # the rows carries the rows), so they follow the mesh's loops and lean as
    # the loops lean; on triangles and n-gons they are carried on.
    local = np.full(len(topo.tri), -1, np.int64)
    local[faces] = np.arange(F)
    quad, sib, qv = _quads(topo, faces, local)
    nb = nbr[faces]
    nbl = np.where(nb >= 0, local[np.maximum(nb, 0)], -1)
    UV = topo.uv[faces]
    gt_ = topo.tri[faces]                                # welded corners

    def uv_at(f, v):
        """UV of welded vertex v (per row) in face f (per row)."""
        pos = np.argmax(gt_[f] == v[:, None], axis=1)
        return UV[f, pos]

    # handedness of each face's UV against the surface's outside
    e1u, e2u = UV[:, 1] - UV[:, 0], UV[:, 2] - UV[:, 0]
    uvdet = e1u[:, 0] * e2u[:, 1] - e1u[:, 1] * e2u[:, 0]
    hand = np.where(uvdet * (n * n_o).sum(1) >= 0, 1.0, -1.0)
    # each edge's angle in the face's own UV and in the neighbour's
    th_i = np.zeros((F, 3))
    th_j = np.zeros((F, 3))
    for k in range(3):
        x, y = gt_[:, k], gt_[:, (k + 1) % 3]
        vi = UV[:, (k + 1) % 3] - UV[:, k]
        th_i[:, k] = np.arctan2(vi[:, 1], vi[:, 0])
        j = nbl[:, k]
        m = j >= 0
        if m.any():
            vj = uv_at(j[m], y[m]) - uv_at(j[m], x[m])
            th_j[m, k] = np.arctan2(vj[:, 1], vj[:, 0])
    # the quads' pairs of opposite edges, in UV
    qa = np.zeros((F, 2))
    qi = np.nonzero(quad)[0]
    if len(qi):
        a_, b_, c_, w_ = qv[qi, 0], qv[qi, 1], qv[qi, 2], qv[qi, 3]
        ua, ub, uc = uv_at(qi, a_), uv_at(qi, b_), uv_at(qi, c_)
        sq = sib[qi]
        uw = uv_at(sq, w_) - uv_at(sq, c_) + uc          # w, from the other half
        p0 = (ub - ua) + (uc - uw)
        p1 = (uc - ub) + (uw - ua)
        qa[qi, 0] = np.arctan2(p0[:, 1], p0[:, 0])
        qa[qi, 1] = np.arctan2(p1[:, 1], p1[:, 0])
    tdir = topo.co[eb[e]] - topo.co[ea[e]]
    st = local[t]
    okst = st >= 0
    st, tdir_s = st[okst], tdir[okst]
    PI, TWO = math.pi, 2.0 * math.pi
    ql, qal = quad.tolist(), qa.tolist()
    thil, thjl, handl = th_i.tolist(), th_j.tolist(), hand.tolist()

    def off(a, b):                     # a - b, wrapped to (-pi, pi]
        return (a - b + PI) % TWO - PI

    def snap(j, wr, wd):
        """Row and column angles on face j, wanted wr and wd."""
        if not ql[j]:
            return wr, wd
        p0, p1 = qal[j]
        e0 = abs(off(p0, wr))
        e0 = min(e0, PI - e0)
        e1 = abs(off(p1, wr))
        e1 = min(e1, PI - e1)
        if e1 < e0:
            p0, p1, e0 = p1, p0, e1
        if e0 > math.radians(40):
            return wr, wd
        rr = p0 if abs(off(p0, wr)) <= PI / 2 else p0 + PI
        dd = p1 if abs(off(p1, wd)) <= PI / 2 else p1 + PI
        if abs(off(dd, wd)) > math.radians(60):
            dd = wd
        if abs(math.sin(dd - rr)) < 0.5:                  # too sheared: square it up
            dd = rr + (PI / 2 if math.sin(dd - rr) >= 0 else -PI / 2)
        return rr, dd

    AR = [None] * F
    AD = [None] * F
    cen_a = P.mean(1)
    cen = cen_a.tolist()
    nbll = nbl.tolist()
    se = e[okst]
    # start at the middle of the marked edge; a piece not reached from there
    # (not joined to it) starts at its own marked edge
    for k0 in [len(st) // 2] + list(range(len(st))):
        i = int(st[k0])
        if AR[i] is not None:
            continue
        pa_ = uv_at(np.array([i]), np.array([ea[se[k0]]]))[0]
        pb_ = uv_at(np.array([i]), np.array([eb[se[k0]]]))[0]
        a0 = math.atan2(pb_[1] - pa_[1], pb_[0] - pa_[0])
        AR[i], AD[i] = snap(i, a0, a0 + handl[i] * PI / 2)   # columns to the left
        heap = [(0.0, i)]
        while heap:
            dist, i = heapq.heappop(heap)
            for k in range(3):
                j = nbll[i][k]
                if j < 0 or AR[j] is not None:
                    continue
                ti_, tj_ = thil[i][k], thjl[i][k]
                if handl[i] == handl[j]:
                    wr, wd = AR[i] - ti_ + tj_, AD[i] - ti_ + tj_
                else:                                        # mirrored UV
                    wr, wd = tj_ - (AR[i] - ti_), tj_ - (AD[i] - ti_)
                AR[j], AD[j] = snap(j, wr, wd)
                c0, c1 = cen[i], cen[j]
                heapq.heappush(heap, (dist + math.sqrt((c0[0] - c1[0]) ** 2
                                                       + (c0[1] - c1[1]) ** 2
                                                       + (c0[2] - c1[2]) ** 2), j))
    ar = np.array([a_ if a_ is not None else 0.0 for a_ in AR])
    ad = np.array([a_ if a_ is not None else PI / 2 for a_ in AD])
    ar, ad = _smooth_threads(ar, ad, quad, nbl, th_i, th_j, hand)
    # onto the 3D faces: through each face's UV -> 3D map
    E3 = np.stack([P[:, 1] - P[:, 0], P[:, 2] - P[:, 0]], 1)            # (F, 2, 3)
    Eu = np.stack([e1u, e2u], 2)                                        # (F, 2, 2) columns
    good = np.abs(uvdet) > 1e-14
    Eu[~good] = np.eye(2)

    def to3d(al):
        v = np.stack([np.cos(al), np.sin(al)], 1)
        c = np.linalg.solve(Eu, v[..., None])[..., 0]
        out_ = c[:, :1] * E3[:, 0] + c[:, 1:] * E3[:, 1]
        return _unit(out_)

    r = to3d(ar)
    d = to3d(ad)
    if (~good).any():                                   # no UV area: any direction
        r[~good] = _unit(E3[~good, 0])
        d[~good] = np.cross(n_o[~good], r[~good])
    flip = (np.cross(r, d) * n_o).sum(1) < 0
    d[flip] = -d[flip]
    # the gradients that measure along the threads: gs . r = 1, gs . d = 0, ...
    pd = np.cross(d, n)
    gs = pd / np.where(np.abs((pd * r).sum(1)) > 1e-6, (pd * r).sum(1), 1e-6)[:, None]
    pr_ = np.cross(n, r)
    gt = pr_ / np.where(np.abs((pr_ * d).sum(1)) > 1e-6, (pr_ * d).sum(1), 1e-6)[:, None]
    # lengths along the marked edge, counted the way the rows run
    sgn = np.zeros(len(ea))
    np.add.at(sgn, e[okst], (r[st] * tdir_s).sum(1))
    seg = np.where(ok, np.linalg.norm(topo.co[eb] - topo.co[ea], axis=1), 0.0)
    seg *= np.where(sgn < 0, -1.0, 1.0)
    s_end = np.cumsum(seg)
    anchor_s = np.zeros(nv)
    got = np.zeros(nv, bool)
    for j in np.nonzero(ok)[0].tolist():
        for v, sv in ((la[j], s_end[j] - seg[j]), (lb[j], s_end[j])):
            if not got[v]:
                got[v] = True
                anchor_s[v] = sv
    fld.anchor_s = anchor_s
    # rows count away from the edge (on the side most of the piece is on)
    away = ((cen_a[st] - (topo.co[ea[e[okst]]] + topo.co[eb[e[okst]]]) / 2) * d[st]).sum(1)
    if float((away * A[st]).sum()) < 0:
        gt = -gt
    fld.gs, fld.gt, fld.A = gs, gt, A
    fld.r3, fld.d3, fld.n_f, fld.nbl = r, d, n, nbl
    fld.isl_f = isl[faces]                               # for "unrolled"
    fld.uvr = topo.uv[faces] * charts.scale_f[faces][:, None, None]
    return out


# ---------------------------------------------------------------------------
# output


_GRADS = np.array([[1, 1, 0], [-1, 1, 0], [1, -1, 0], [-1, -1, 0], [1, 0, 1], [-1, 0, 1],
                   [1, 0, -1], [-1, 0, -1], [0, 1, 1], [0, -1, 1], [0, 1, -1], [0, -1, -1]],
                  np.float64)


def _noise(p, perm):
    """Smooth gradient noise (about -1..1) at points p (n, 3)."""
    pi = np.floor(p)
    f = p - pi
    i = pi.astype(np.int64) & 255
    u = f * f * f * (f * (f * 6.0 - 15.0) + 10.0)
    out = 0.0
    for dx in (0, 1):
        for dy in (0, 1):
            for dz in (0, 1):
                h = perm[perm[perm[i[:, 0] + dx] + i[:, 1] + dy] + i[:, 2] + dz] % 12
                g = _GRADS[h]
                dot = (g[:, 0] * (f[:, 0] - dx) + g[:, 1] * (f[:, 1] - dy)
                       + g[:, 2] * (f[:, 2] - dz))
                w = ((u[:, 0] if dx else 1.0 - u[:, 0]) * (u[:, 1] if dy else 1.0 - u[:, 1])
                     * (u[:, 2] if dz else 1.0 - u[:, 2]))
                out = out + w * dot
    return out


class Wobble:
    """Random gentle bends of the lines of the squares: the square coordinates
    are pushed by smooth noise, so every line bows a little on its own, and
    lines still cross at sharp corners. One bow spans a few squares, so a
    line is curved, not wavy. ``amount`` 0..1. The noise is taken over the
    square coordinates themselves where they are one continuous field
    (Unrolled: the bows then grow with the squares towards the hem), else
    over the surface in 3D (the stripes, whose coordinates are exact only up
    to periods per triangle)."""

    def __init__(self, key, cell, amount):
        self.amp = 0.3 * float(amount) * cell
        self.scale = 3.5 * cell                      # one bow over a few squares
        seed = zlib.crc32(str(key).encode("utf-8"))
        perm = np.random.default_rng(seed).permutation(256)
        self.perm = np.concatenate([perm, perm, perm])
        self.shift = np.random.default_rng(seed + 1).uniform(0, 100, (2, 3))

    def __call__(self, p, xy=None):
        """(dx, dy) for points p (n, 3) in scene units; xy (n, 2) are their
        square coordinates, given when those are continuous over the piece."""
        if self.amp <= 0 or not len(p):
            z = np.zeros(len(p))
            return z, z
        if xy is None:
            q = np.asarray(p, np.float64) / self.scale
        else:
            q = np.concatenate([np.asarray(xy, np.float64) / self.scale,
                                np.full((len(xy), 1), 0.37)], 1)
        dx = _noise(q + self.shift[0], self.perm)
        dy = _noise(q + self.shift[1], self.perm)
        return self.amp * dx, self.amp * dy


def _halves(x, aa, cell):
    """Antialiased share of each texel in the first half of every 2-cell
    period of x (where cell index floor(x / cell) is even); aa is how much x
    changes over one texel."""
    p = np.mod(x, 2.0 * cell)
    sd = np.where(p < cell, -np.minimum(p, cell - p), np.minimum(p - cell, 2.0 * cell - p))
    cov = np.clip(0.5 - sd / np.maximum(aa, 1e-30), 0.0, 1.0)
    return np.where(aa > 0.5 * cell, 0.5, cov)          # finer than a texel


def raster(topo, lay, faces, res, tile, cell, off_x, off_y, wobble=None, block=8):
    """(black, white) square coverage images (res, res), Blender orientation
    (row 0 at the bottom), for the triangles ``faces`` (a subset of
    lay.faces) of one UV tile."""
    black = np.zeros((res, res), np.float32)
    white = np.zeros((res, res), np.float32)
    faces = np.asarray(faces, np.int64)
    if not len(faces) or cell <= 0:
        return black, white
    row = np.searchsorted(lay.faces, faces)
    tile = np.asarray(tile, np.float64)
    U = (topo.uv[faces] - tile) * res - 0.5                        # (n, 3, 2)
    e1, e2 = U[:, 1] - U[:, 0], U[:, 2] - U[:, 0]
    det = e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]
    ok = np.abs(det) > 1e-12
    det = np.where(ok, det, 1.0)
    uarea = 0.5 * np.abs(det)
    # real size of a texel on each triangle (x and y are distances)
    tex = np.sqrt(topo.area[faces] / np.maximum(uarea, 1e-30)) * math.sqrt(2.0)

    bx, by, bt = [], [], []
    for i in np.nonzero(ok)[0].tolist():
        x0, y0 = np.floor(U[i].min(0)).astype(int)
        x1, y1 = np.ceil(U[i].max(0)).astype(int)
        x0, y0 = max(x0, 0), max(y0, 0)
        x1, y1 = min(x1, res - 1), min(y1, res - 1)
        if x1 < x0 or y1 < y0:
            continue
        gx_, gy_ = np.meshgrid(np.arange(x0, x1 + 1, block), np.arange(y0, y1 + 1, block))
        bx.append(gx_.ravel())
        by.append(gy_.ravel())
        bt.append(np.full(gx_.size, i))
    if not bt:
        return black, white
    bx, by, bt = np.concatenate(bx), np.concatenate(by), np.concatenate(bt)
    o = np.arange(block)
    ox, oy = np.meshgrid(o, o)
    ox, oy = ox.ravel(), oy.ravel()
    step = max(1, 2_000_000 // (block * block))
    for a in range(0, len(bt), step):
        px = (bx[a:a + step, None] + ox[None]).ravel()
        py = (by[a:a + step, None] + oy[None]).ravel()
        pt = np.repeat(bt[a:a + step], block * block)
        keep = (px < res) & (py < res)
        px, py, pt = px[keep], py[keep], pt[keep]
        u0, d1, d2, dt = U[pt, 0], e1[pt], e2[pt], det[pt]
        qx, qy = px - u0[:, 0], py - u0[:, 1]
        w1 = (qx * d2[:, 1] - qy * d2[:, 0]) / dt
        w2 = (d1[:, 0] * qy - d1[:, 1] * qx) / dt
        w0 = 1.0 - w1 - w2
        eps = -1e-6
        inside = (w0 >= eps) & (w1 >= eps) & (w2 >= eps)
        px, py, pt = px[inside], py[inside], pt[inside]
        w = np.stack([w0[inside], w1[inside], w2[inside]], 1)
        p3 = (w[:, :, None] * topo.V[faces[pt]]).sum(1)
        xy = lay.at(row[pt], w, p3)
        x = xy[:, 0] - off_x
        y = xy[:, 1] - off_y
        if wobble is not None:
            dx, dy = wobble(p3, np.stack([x, y], 1) if lay.continuous else None)
            x, y = x + dx, y + dy
        aa = tex[pt]
        hx = _halves(x, aa, cell)
        hy = _halves(y, aa, cell)
        b = (hx * hy + (1.0 - hx) * (1.0 - hy)).astype(np.float32)   # same parity
        np.maximum.at(black, (py, px), b)
        np.maximum.at(white, (py, px), (1.0 - b).astype(np.float32))
    return black, white


def _split(n):
    """Barycentric corners (m, 3, 3) of a triangle cut into n * n."""
    out = []
    for i in range(n):
        for j in range(n - i):
            a = np.array([i, j, n - i - j]) / n
            b = np.array([i + 1, j, n - i - j - 1]) / n
            c = np.array([i, j + 1, n - i - j - 1]) / n
            out.append((a, b, c))
            if j < n - i - 1:
                d = np.array([i + 1, j + 1, n - i - j - 2]) / n
                out.append((b, d, c))
    return np.array(out)


def preview(topo, lay, lift, off_x, off_y, wobble=None):
    """Preview geometry: the triangles that have squares, lifted off the
    surface; a triangle with a knot is cut into small ones. Returns
    (co (n, 3), tris (m, 3), xy per corner (m, 3, 2))."""
    f = lay.faces
    if not len(f):
        return np.zeros((0, 3)), np.zeros((0, 3), np.int64), np.zeros((0, 3, 2))
    # corners are not shared (x is exact only up to whole periods per
    # triangle), but lifted along shared vertex normals, so neighbouring
    # triangles still meet without a crack
    vn = np.zeros((len(topo.co), 3))
    np.add.at(vn, topo.tri[f].reshape(-1), np.repeat(topo.n_o[f], 3, axis=0))
    vn /= np.maximum(np.linalg.norm(vn, axis=1), 1e-30)[:, None]
    ids = topo.tri[f]
    lifted = topo.co[ids] + vn[ids] * lift                     # (F, 3, 3)
    plain = ~lay.knot.any(1)
    rows = np.nonzero(plain)[0]
    co = [lifted[rows].reshape(-1, 3)]
    xy = [lay.xy[rows].reshape(-1, 2)]
    p3 = [topo.V[f[rows]].reshape(-1, 3)]
    kr = np.nonzero(~plain)[0]
    if len(kr):
        sub = _split(6)                                         # (m, 3, 3)
        m = len(sub)
        r = np.repeat(kr, m * 3)
        w = np.tile(sub.reshape(-1, 3), (len(kr), 1))          # (len*m*3, 3)
        V = topo.V[f[r]]
        pp = (w[:, :, None] * V).sum(1)
        co.append((w[:, :, None] * lifted[r]).sum(1))
        v = lay.at(r, w, pp).reshape(-1, 3, 2)
        # line each small triangle up with its first corner
        q = pp.reshape(-1, 3, 3)
        gr = (lay.g[0][r].reshape(-1, 3, 3)[:, 0], lay.g[1][r].reshape(-1, 3, 3)[:, 0])
        per = 2.0 * math.pi / lay.k
        for c in (0, 1):
            for j in (1, 2):
                d = ((q[:, j] - q[:, 0]) * gr[c]).sum(1)
                v[:, j, c] = v[:, 0, c] + d + ((v[:, j, c] - v[:, 0, c] - d + per / 2) % per
                                               - per / 2)
        xy.append(v.reshape(-1, 2))
        p3.append(pp)
    co, xy, p3 = np.vstack(co), np.vstack(xy), np.vstack(p3)
    xy = xy - np.array([off_x, off_y])
    if wobble is not None:
        dx, dy = wobble(p3, xy if lay.continuous else None)
        xy = xy + np.stack([dx, dy], 1)
    tris = np.arange(len(co)).reshape(-1, 3)
    return co, tris, xy.reshape(-1, 3, 2)
