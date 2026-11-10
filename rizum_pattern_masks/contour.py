"""The stitch line as a distance contour.

The stitch line is where the distance to the hem equals the inset - the same
rule a seamstress uses. Concretely:

* every hem edge is a segment; a point's distance is its distance to the
  nearest hem segment it can see. A face sees the segments reachable over the
  surface within a short range, starting on the inward side of each hem edge
  and never crossing the hem itself, so neither the outer side nor a far part
  of the hem can pull the line;
* the faces near the hem are sampled, finely only where the line can be, the
  exact crossings of the inset distance are solved for, and the crossings are
  linked into lines.

This gives, without special cases, a line that passes over a slit narrower
than twice the inset instead of spiking into it, and no self-overlaps, gaps or
forks to repair afterwards.

Marked inner corners stay sharp: around such a corner the distance is the
larger of the distances to the two edge lines (a miter join), so the two
offsets meet in a point instead of rounding around the corner. Past the miter
limit the corner is a slit, which the line passes over. Corner Inset is part
of the distance too: each hem vertex carries an extra inset that is ``depth``
at a corner and falls off along the hem with a circular-arc profile.
"""

import math
from collections import defaultdict

import numpy as np
from mathutils import kdtree

MITER_LIMIT = 2.0          # longest inner corner point, in multiples of the inset


def corner_profile(x, reach, depth):
    """Extra inset at distance ``x`` along the hem from a corner: a circular
    arc that is ``depth`` at the corner and meets 0 tangentially at ``reach``."""
    x = np.asarray(x, np.float64)
    out = np.zeros_like(x)
    inside = x < reach
    if reach <= depth:                    # too short for an arc: parabola instead
        out[inside] = depth * (1.0 - x[inside] / reach) ** 2
        return out
    R = (reach * reach + depth * depth) / (2.0 * depth)
    u = reach - x[inside]
    out[inside] = R - np.sqrt(np.maximum(R * R - u * u, 0.0))
    return out


def _normalize(v):
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    return v / np.maximum(n, 1e-30)


class _Charts:
    """The UV layout as a flattened copy of the surface.

    A 3D distance is too short where the fabric curls or folds: another part of
    the hem can be a few millimetres away through the air but far away along
    the fabric. The UV layout lies flat, so a distance measured there (scaled to
    real size per UV island) is the distance along the fabric. Across a UV seam
    the coordinates are carried over with the transform that maps the edge on
    one side onto the other.

    A UV layout is rarely true to size everywhere: a strip that tapers on the
    model is often unwrapped as an even band, so across it the UVs are
    stretched. So the real size per UV unit is not one number per island: each
    hem segment measures it at its two ends, inward across the hem where the
    line will be (``across``), and it is blended along the segment, which
    keeps the distance continuous along the hem and over UV seams."""

    def __init__(self, topo):
        F = len(topo.tri)
        self.ok = topo.uv is not None and F > 0
        if not self.ok:
            self.isl = np.zeros(F, np.int64)
            self.scale_f = np.zeros(F)
            self.stretch = np.ones(F)
            return
        V, U = topo.V, topo.uv
        self.V0 = V[:, 0]
        e1, e2 = V[:, 1] - V[:, 0], V[:, 2] - V[:, 0]
        self.e1, self.e2 = e1, e2
        g11, g12, g22 = (e1 * e1).sum(1), (e1 * e2).sum(1), (e2 * e2).sum(1)
        det = np.maximum(g11 * g22 - g12 * g12, 1e-40)
        self.inv = np.stack([g22 / det, -g12 / det, g11 / det], 1)
        self.Uz = U[..., 0] + 1j * U[..., 1]                      # (F, 3) complex
        uarea = 0.5 * ((U[:, 1, 0] - U[:, 0, 0]) * (U[:, 2, 1] - U[:, 0, 1])
                       - (U[:, 2, 0] - U[:, 0, 0]) * (U[:, 1, 1] - U[:, 0, 1]))
        # seams: per face edge, the transform z -> s * (conj(z) if refl else z) + c
        tri, nbr = topo.tri, topo.nbr
        self.same = np.ones((F, 3), bool)
        self.refl = np.zeros((F, 3), bool)
        self.s = np.ones((F, 3), complex)
        self.c = np.zeros((F, 3), complex)
        for j in range(3):
            u = nbr[:, j]
            has = u >= 0
            t = np.nonzero(has)[0]
            u = u[has]
            a, b = tri[t, j], tri[t, (j + 1) % 3]
            ja = np.argmax(tri[u] == a[:, None], axis=1)
            jb = np.argmax(tri[u] == b[:, None], axis=1)
            Ua, Ub = self.Uz[t, j], self.Uz[t, (j + 1) % 3]
            Va, Vb = self.Uz[u, ja], self.Uz[u, jb]
            tol = 1e-7
            same = (np.abs(Ua - Va) < tol) & (np.abs(Ub - Vb) < tol)
            refl = np.sign(uarea[t]) * np.sign(uarea[u]) < 0
            Ua2 = np.where(refl, np.conj(Ua), Ua)
            Ub2 = np.where(refl, np.conj(Ub), Ub)
            den = Ub2 - Ua2
            s = np.where(np.abs(den) > 1e-12, (Vb - Va) / np.where(den == 0, 1, den), 1.0)
            self.same[t, j] = same
            self.refl[t, j] = refl & ~same
            self.s[t, j] = np.where(same, 1.0, s)
            self.c[t, j] = np.where(same, 0.0, Va - s * Ua2)
        # islands (faces joined without a seam) and their real size per UV unit
        lab = np.arange(F)
        tt = np.repeat(np.arange(F), 3)
        uu = nbr.reshape(-1)
        keep = (uu >= 0) & self.same.reshape(-1)
        tt, uu = tt[keep], uu[keep]
        while True:
            new = lab.copy()
            np.minimum.at(new, tt, lab[uu])
            np.minimum.at(new, uu, lab[tt])
            new = new[new]
            if (new == lab).all():
                break
            lab = new
        _, isl = np.unique(lab, return_inverse=True)
        self.isl = isl                              # UV island of each face
        a3 = np.bincount(isl, topo.area)
        auv = np.bincount(isl, np.abs(uarea))
        scale = np.sqrt(a3 / np.maximum(auv, 1e-30))
        scale[auv <= 1e-20] = 0.0                  # no usable UVs: 3D only
        self.scale_f = scale[isl]
        # largest stretch of UV length (in real size) per 3D length on each face
        x = e1 / np.maximum(np.linalg.norm(e1, axis=1), 1e-30)[:, None]
        y = e2 - (e2 * x).sum(1)[:, None] * x
        y = y / np.maximum(np.linalg.norm(y, axis=1), 1e-30)[:, None]
        P = np.stack([np.stack([(e1 * x).sum(1), (e2 * x).sum(1)], 1),
                      np.stack([(e1 * y).sum(1), (e2 * y).sum(1)], 1)], 1)       # (F,2,2)
        Q = np.stack([np.stack([(U[:, 1] - U[:, 0])[:, 0], (U[:, 2] - U[:, 0])[:, 0]], 1),
                      np.stack([(U[:, 1] - U[:, 0])[:, 1], (U[:, 2] - U[:, 0])[:, 1]], 1)], 1)
        detP = P[:, 0, 0] * P[:, 1, 1] - P[:, 0, 1] * P[:, 1, 0]
        Pinv = np.stack([np.stack([P[:, 1, 1], -P[:, 0, 1]], 1),
                         np.stack([-P[:, 1, 0], P[:, 0, 0]], 1)], 1) / np.where(
                             np.abs(detP) > 1e-30, detP, 1e-30)[:, None, None]
        J = Q @ Pinv
        sv = np.linalg.svd(J, compute_uv=False)[:, 0]
        self.stretch = np.maximum(1.0, sv * self.scale_f.max())
        # real length per UV vector on each face (zero where the UVs are degenerate)
        detJ = J[:, 0, 0] * J[:, 1, 1] - J[:, 0, 1] * J[:, 1, 0]
        good = np.abs(detJ) > 1e-30
        safe = np.where(good, detJ, 1.0)
        Minv = np.stack([np.stack([J[:, 1, 1], -J[:, 0, 1]], 1),
                         np.stack([-J[:, 1, 0], J[:, 0, 0]], 1)], 1) / safe[:, None, None]
        self.Minv = np.where(good[:, None, None], Minv, 0.0)
        self._trees = {}

    def _face_at(self, z, isl):
        """The face of island isl whose UV triangle holds the UV point z, or -1."""
        tree = self._trees.get(isl)
        if tree is None:
            faces = np.nonzero(self.isl == isl)[0]
            tree = kdtree.KDTree(len(faces))
            for f in faces.tolist():
                c = self.Uz[f].mean()
                tree.insert((c.real, c.imag, 0.0), f)
            tree.balance()
            self._trees[isl] = tree
        for _, f, _ in tree.find_n((z.real, z.imag, 0.0), 12):
            a, b, c = self.Uz[f]
            v0, v1, v2 = b - a, c - a, z - a
            den = (v0.conjugate() * v1).imag
            if abs(den) < 1e-30:
                continue
            u = (v2.conjugate() * v1).imag / den
            v = (v0.conjugate() * v2).imag / den
            if u >= -1e-9 and v >= -1e-9 and u + v <= 1.0 + 1e-9:
                return f
        return -1

    def across(self, z, nz, isl, d, f0):
        """Real distance from the hem per UV unit, going inward from the hem
        point z (UV) along the unit UV direction nz (square to the hem there),
        averaged over the first ``d`` of real distance; f0 is the starting
        guess (the island's). Only the part of each step square to the hem in
        real space counts: where the UVs are sheared a step also slides along
        the hem."""
        f = f0
        for _ in range(2):                         # where the line is depends on f
            u = d / max(f, 1e-30)
            got = []
            for s in (0.125, 0.375, 0.625, 0.875):
                t = self._face_at(z + nz * (u * s), isl)
                if t < 0:
                    break
                M = self.Minv[t]
                v = M @ np.array([nz.real, nz.imag])
                a = M @ np.array([-nz.imag, nz.real])        # along the hem
                na = float(np.hypot(a[0], a[1]))
                g = abs(float(a[0] * v[1] - a[1] * v[0])) / na if na > 0 else 0.0
                if g <= 0.0:
                    break
                got.append(g)
            if not got:
                return f
            prev, f = f, float(np.mean(got))
            if abs(f - prev) < 0.03 * prev:        # settled: the line stays put
                break
        return f

    def uv(self, X, T):
        """UV (complex) of points X lying on faces T."""
        d = X - self.V0[T]
        p, q = (d * self.e1[T]).sum(1), (d * self.e2[T]).sum(1)
        inv = self.inv[T]
        b1 = inv[:, 0] * p + inv[:, 1] * q
        b2 = inv[:, 1] * p + inv[:, 2] * q
        Uz = self.Uz[T]
        return Uz[:, 0] + b1 * (Uz[:, 1] - Uz[:, 0]) + b2 * (Uz[:, 2] - Uz[:, 0])


class _Segments:
    """The hem segments (with inward direction, open-end flags and the extra
    inset at their ends) and the marked corners."""

    def __init__(self, topo, chains, inset, flip, corner_ids=frozenset(), depth=0.0,
                 charts=None):
        A, B, W, tri, s_end, e_end, EA, EB, IA, IB = ([] for _ in range(10))
        # corners: vertex position, walk face, walk direction, apex distance,
        # and for mitered ones the two inward normals and edge directions
        self.corners = []
        self.miters = []        # (C, n_in, n_out, u_in, u_out, seg_in, seg_out, alpha)
        d = abs(inset)
        D = d + depth
        fans = _Fans(topo)
        base = 0
        for ids, closed in chains:
            ids = np.asarray(ids, np.int64)
            if len(ids) < 2:
                continue
            a = ids if closed else ids[:-1]
            b = np.roll(ids, -1) if closed else ids[1:]
            et, cnt = topo.edge_info(a, b)
            pa, pb = topo.co[a], topo.co[b]
            w = _normalize(np.cross(topo.n_o[et], pb - pa))
            # Border edges have fabric on one side only: each points to its own
            # face. Edges inside the mesh follow the majority of the chain.
            bnd = cnt == 1
            toward = np.sign(((topo.centroid[et] - (pa + pb) / 2.0) * w).sum(1))
            side = 1.0
            if bnd.any() and toward[bnd].sum() < 0:
                side = -1.0
            sides = np.where(bnd & (toward != 0), toward, side)
            if flip:
                sides = -sides
            if inset < 0:
                sides = -sides
            w = w * sides[:, None]
            n = len(a)
            se = np.zeros(n, bool)
            ee = np.zeros(n, bool)
            if not closed:
                se[0] = True
                ee[-1] = True
            seglen = np.linalg.norm(pb - pa, axis=1)
            vextra = np.zeros(len(ids))
            cidx = [i for i in range(len(ids)) if int(ids[i]) in corner_ids
                    and (closed or 0 < i < len(ids) - 1)]
            if cidx:
                cum = np.concatenate([[0.0], np.cumsum(seglen)])
                total = float(cum[-1])
                sv = cum[:len(ids)]
                cs = sv[cidx]
                for i in cidx:
                    if depth > 0:
                        gaps = np.abs(cs - sv[i])
                        if closed:
                            gaps = np.minimum(gaps, total - gaps)
                        gaps = gaps[gaps > 0]
                        reach = 3.0 * D
                        if gaps.size:
                            reach = min(reach, 0.5 * float(gaps.min()))
                        dist = np.abs(sv - sv[i])
                        if closed:
                            dist = np.minimum(dist, total - dist)
                        vextra = np.maximum(vextra, corner_profile(dist, reach, depth))
                    j_in, j_out = (i - 1) % n, i % n
                    v = int(ids[i])
                    fan = fans.around(v, int(ids[(i + 1) % len(ids)]),
                                      int(ids[(i - 1) % len(ids)]), w[j_out])
                    if fan is None:
                        continue
                    alpha = fan[-1][2]                     # fabric angle at the corner
                    half = 0.5 * alpha
                    apex = D / max(math.sin(half), 1e-9)
                    if alpha > math.pi:
                        if apex > MITER_LIMIT * D:
                            continue                       # a slit: passed over
                        u_in = (pb[j_in] - pa[j_in]) / max(seglen[j_in], 1e-30)
                        u_out = (pb[j_out] - pa[j_out]) / max(seglen[j_out], 1e-30)
                        self.miters.append((topo.co[v].copy(), w[j_in], w[j_out], u_in, u_out,
                                            base + j_in, base + j_out, alpha))
                    t_dir = fans.direction(v, fan, half)
                    if t_dir is not None:
                        self.corners.append((topo.co[v].copy(), t_dir[0], t_dir[1], apex))
            A.append(pa); B.append(pb); W.append(w); tri.append(et)
            s_end.append(se); e_end.append(ee); IA.append(a); IB.append(b)
            EA.append(vextra[:-1] if not closed else vextra)
            EB.append(vextra[1:] if not closed else np.roll(vextra, -1))
            base += n
        cat = (lambda x: np.concatenate(x)) if A else (lambda x: np.zeros(0))
        self.A = np.vstack(A) if A else np.zeros((0, 3))
        self.B = np.vstack(B) if B else np.zeros((0, 3))
        self.W = np.vstack(W) if W else np.zeros((0, 3))
        self.tri = cat(tri).astype(np.int64)
        self.start_end = cat(s_end).astype(bool)
        self.end_end = cat(e_end).astype(bool)
        self.ia, self.ib = cat(IA).astype(np.int64), cat(IB).astype(np.int64)
        self.eA, self.eB = cat(EA), cat(EB)
        self.AB = self.B - self.A
        self.L2 = np.maximum((self.AB * self.AB).sum(1), 1e-30)
        self.len = np.sqrt(self.L2)
        self.slope = float((np.abs(self.eB - self.eA) / self.len).max()) if len(self.A) else 0.0
        self.path_edges = {(min(x, y), max(x, y)) for x, y in zip(self.ia.tolist(),
                                                                    self.ib.tolist())}
        # each segment starts from the face on its inward side
        for k in range(len(self.tri)):
            t = int(self.tri[k])
            if t < 0:
                continue
            mid = (self.A[k] + self.B[k]) * 0.5
            if np.dot(topo.centroid[t] - mid, self.W[k]) >= 0:
                continue
            row = topo.tri[t].tolist()
            for j in range(3):
                u = int(topo.nbr[t, j])
                if u >= 0 and {row[j], row[(j + 1) % 3]} == {int(self.ia[k]), int(self.ib[k])}:
                    self.tri[k] = u
                    break
        # each segment in the UV layout of its own face, the side its fabric is
        # on there (+1 left), and its island's real size per UV unit
        nS = len(self.tri)
        self.Az = np.zeros(nS, complex)
        self.Bz = np.zeros(nS, complex)
        self.psi = np.ones(nS)
        self.scale = np.zeros(nS)
        if charts is not None and charts.ok and nS:
            t = np.maximum(self.tri, 0)
            rows = topo.tri[t]
            ja = np.argmax(rows == self.ia[:, None], axis=1)
            jb = np.argmax(rows == self.ib[:, None], axis=1)
            jc = 3 - ja - jb
            Uz = charts.Uz[t]
            ar = np.arange(nS)
            self.Az, self.Bz = Uz[ar, ja], Uz[ar, jb]
            third = Uz[ar, jc]
            cross = ((self.Bz - self.Az).conjugate() * (third - self.Az)).imag
            self.psi = np.where(cross < 0, -1.0, 1.0)
            ok = (self.tri >= 0) & (np.abs(self.Bz - self.Az) > 1e-12)
            self.scale = np.where(ok, charts.scale_f[t], 0.0)
        # real size per UV unit across the hem at each end of each segment
        self.fA, self.fB = self.scale.copy(), self.scale.copy()
        if charts is not None and charts.ok and nS and d > 0:
            for k in np.nonzero(self.scale > 0)[0].tolist():
                AB = self.Bz[k] - self.Az[k]
                nz = AB / abs(AB) * 1j * self.psi[k]       # inward, in the UV layout
                isl = int(charts.isl[self.tri[k]])
                self.fA[k] = charts.across(self.Az[k], nz, isl, d, self.scale[k])
                self.fB[k] = charts.across(self.Bz[k], nz, isl, d, self.scale[k])
        if self.miters:
            M = self.miters
            self.mAlpha = np.array([m[7] for m in M])
            self.mC = np.array([m[0] for m in M])
            self.mN1 = np.array([m[1] for m in M])
            self.mN2 = np.array([m[2] for m in M])
            self.mU1 = np.array([m[3] for m in M])
            self.mU2 = np.array([m[4] for m in M])
            self.mExtra = np.array([self.eB[m[5]] for m in M])
            # surface normal at the corner, to measure how far a point is off
            # the corner's plane (the two edge normals only see in-plane offsets)
            self.mNC = _normalize(_normalize(np.cross(self.mU1, self.mN1))
                                  + _normalize(np.cross(self.mU2, self.mN2)))
            self.mSeg = [(m[5], m[6]) for m in M]


class _Fans:
    """The faces around a hem vertex on the fabric side, with the angles they
    cover there: the corner angle measured on the surface itself."""

    def __init__(self, topo):
        self.topo = topo
        flat = topo.tri.reshape(-1)
        order = np.argsort(flat, kind="stable")
        self.vt_order = order // 3
        self.vt_start = np.searchsorted(flat[order], np.arange(len(topo.co) + 1))

    def around(self, v, b_out, a_in, w_out):
        """[(face, entry vertex, angle at the end of this face)] from the edge
        v-b_out to the edge v-a_in, through the faces on the inward side."""
        topo = self.topo
        faces = self.vt_order[self.vt_start[v]:self.vt_start[v + 1]].tolist()
        mid = (topo.co[v] + topo.co[b_out]) * 0.5
        start = [t for t in faces if b_out in topo.tri[t]
                 and np.dot(topo.centroid[t] - mid, w_out) > 0]
        if not start:
            return None
        t, x = start[0], b_out
        fan, total = [], 0.0
        for _ in range(len(faces) + 1):
            row = topo.tri[t].tolist()
            y = [u for u in row if u != v and u != x]
            if len(y) != 1:
                return None
            y = y[0]
            e1 = topo.co[x] - topo.co[v]
            e2 = topo.co[y] - topo.co[v]
            c = np.dot(e1, e2) / max(np.linalg.norm(e1) * np.linalg.norm(e2), 1e-30)
            total += math.acos(min(max(c, -1.0), 1.0))
            fan.append((t, x, total))
            if y == a_in:
                return fan
            k = [j for j in range(3) if {row[j], row[(j + 1) % 3]} == {v, y}]
            u = int(topo.nbr[t, k[0]]) if k else -1
            if u < 0:
                return None
            t, x = u, y
        return None

    def direction(self, v, fan, angle):
        """(face, 3D direction) leaving vertex v at ``angle`` into the fan."""
        topo = self.topo
        prev = 0.0
        for t, x, end in fan:
            if angle <= end + 1e-12:
                e1 = _normalize(topo.co[x] - topo.co[v])
                perp = _normalize(np.cross(topo.n[t], e1))
                y = [u for u in topo.tri[t].tolist() if u != v and u != x][0]
                if np.dot(perp, topo.co[y] - topo.co[v]) < 0:
                    perp = -perp
                phi = angle - prev
                return t, math.cos(phi) * e1 + math.sin(phi) * perp
            prev = end
        return None


def _visible(topo, segs, reach, charts):
    """Rows (face, segment, segment end points in the face's UV layout, mirror
    parity), sorted by face: the segments each face may use. A segment spreads
    from its own face to neighbours over the surface, never across the hem, as
    long as the face is within ``reach`` of it."""
    nS = len(segs.A)
    nV = len(topo.co)
    k0 = np.nonzero(segs.tri >= 0)[0]
    key0 = segs.tri[k0] * nS + k0
    cur, first = np.unique(key0, return_index=True)
    k0 = k0[first]
    cAz, cBz, cpar = segs.Az[k0], segs.Bz[k0], np.zeros(len(k0), bool)
    prev = np.zeros(0, np.int64)
    waves = [(cur, cAz, cBz, cpar)]
    pe = np.array(sorted(a * nV + b for a, b in segs.path_edges), np.int64)
    tri, nbr = topo.tri, topo.nbr
    uv = charts.ok
    while len(cur):
        front_t, front_k = cur // nS, cur % nS
        u = nbr[front_t].reshape(-1)
        k = np.repeat(front_k, 3)
        tt = np.repeat(front_t, 3)
        jj = np.tile(np.arange(3), len(front_t))
        a = tri[front_t].reshape(-1)
        b = tri[front_t][:, [1, 2, 0]].reshape(-1)
        ek = np.minimum(a, b) * nV + np.maximum(a, b)
        ok = (u >= 0) & ~np.isin(ek, pe)                 # never across the hem
        src = np.nonzero(ok)[0]
        key, first = np.unique(u[src] * nS + k[src], return_index=True)
        src = src[first]
        # breadth first: a new pair's neighbours are in this wave or the last
        new = ~np.isin(key, cur) & ~np.isin(key, prev)
        key, src = key[new], src[new]
        u, k = key // nS, key % nS
        c = topo.centroid[u]
        A, AB = segs.A[k], segs.AB[k]
        tc = np.clip(((c - A) * AB).sum(1) / segs.L2[k], 0.0, 1.0)
        dist = np.linalg.norm(c - (A + tc[:, None] * AB), axis=1) - topo.radius[u]
        near = dist <= reach
        key, src = key[near], src[near]
        pi = src // 3                                    # parent row in the front
        Az, Bz, par = cAz[pi], cBz[pi], cpar[pi]
        if uv:
            t_, j_ = tt[src], jj[src]
            rf = charts.refl[t_, j_]
            sc, cc = charts.s[t_, j_], charts.c[t_, j_]
            Az = sc * np.where(rf, np.conj(Az), Az) + cc
            Bz = sc * np.where(rf, np.conj(Bz), Bz) + cc
            par = par ^ rf
        prev, cur = cur, key
        cAz, cBz, cpar = Az, Bz, par
        waves.append((cur, cAz, cBz, cpar))
    keys = np.concatenate([w[0] for w in waves])
    order = np.argsort(keys, kind="stable")
    keys = keys[order]
    rows = {"f": keys // nS, "k": keys % nS,
            "Az": np.concatenate([w[1] for w in waves])[order],
            "Bz": np.concatenate([w[2] for w in waves])[order],
            "par": np.concatenate([w[3] for w in waves])[order]}
    f, k = rows["f"], rows["k"]
    if not len(f):                       # e.g. only loose edges marked
        return rows
    # Keep per face only the segments that can be the nearest somewhere on it:
    # a segment whose closest possible distance is beyond another segment's
    # farthest one never wins there.
    c = topo.centroid[f]
    val = _pair_value(segs, rows, np.arange(len(f)), c, charts.uv(c, f) if uv else None)
    boost = 1.0
    if uv and len(segs.fA):
        boost = max(1.0, float(np.max(np.r_[segs.fA, segs.fB])) / max(float(charts.scale_f.max()), 1e-30))
    r = topo.radius[f] * charts.stretch[f] * boost
    lo = val - r - np.maximum(segs.eA[k], segs.eB[k])
    hi = val + r - np.minimum(segs.eA[k], segs.eB[k])
    starts = np.flatnonzero(np.r_[True, f[1:] != f[:-1]])
    best = np.minimum.reduceat(hi, starts)
    keep = lo <= np.repeat(best, np.diff(np.r_[starts, len(f)]))
    return {name: v[keep] for name, v in rows.items()}


def _pair_value(segs, rows, r, X, Xz):
    """Distance from points X (UV Xz) to the segments of rows r: the larger of
    the 3D distance and the distance along the flat UV layout."""
    k = rows["k"][r]
    AB = segs.AB[k]
    D = X - segs.A[k]
    t = (D * AB).sum(1) / segs.L2[k]
    tc = np.clip(t, 0.0, 1.0)
    diff = D - tc[:, None] * AB
    dist = np.sqrt((diff * diff).sum(1))
    if Xz is not None:
        Az, ABz = rows["Az"][r], rows["Bz"][r] - rows["Az"][r]
        Dz = Xz - Az
        L2z = np.maximum((ABz * ABz.conjugate()).real, 1e-30)
        tz = np.clip((Dz * ABz.conjugate()).real / L2z, 0.0, 1.0)
        f = segs.fA[k] + tz * (segs.fB[k] - segs.fA[k])
        dist = np.maximum(dist, np.abs(Dz - tz * ABz) * f)
    return dist


class _Field:
    """Batched field: distance to the visible hem minus the local extra inset,
    minus the inset. eval(X, T) for points X lying on faces T."""

    def __init__(self, segs, rows, d, n_faces, charts):
        self.segs = segs
        self.rows = rows
        self.d = d
        self.charts = charts
        f, k = rows["f"], rows["k"]
        csr = [self._csr(f, np.arange(len(f)), n_faces)]
        self.mrow = np.zeros(0, np.int64)
        self.mm = np.zeros(0, np.int64)
        self.mout = np.zeros(0, bool)
        if segs.miters:
            # a face uses a corner's miter when it sees either of its edges; the
            # UV position comes from that edge's row (the outgoing one if both)
            nM = len(segs.mSeg)
            r_all, m_all, out_all = [], [], []
            for col, is_out in ((1, True), (0, False)):
                owner = np.full(len(segs.A), -1, np.int64)
                owner[[m[col] for m in segs.mSeg]] = np.arange(nM)
                m = owner[k]
                sel = np.nonzero(m >= 0)[0]
                r_all.append(sel); m_all.append(m[sel]); out_all.append(np.full(len(sel), is_out))
            r_all, m_all, out_all = (np.concatenate(x) for x in (r_all, m_all, out_all))
            key = f[r_all] * nM + m_all
            _, first = np.unique(key, return_index=True)     # outgoing rows come first
            self.mrow, self.mm, self.mout = r_all[first], m_all[first], out_all[first]
            csr.append(self._csr(f[self.mrow], np.arange(len(first)), n_faces))
        else:
            csr.append((np.zeros(n_faces + 1, np.int64), np.zeros(0, np.int64)))
        self.csr = csr                  # per face lists as (offsets, flat items)

    @staticmethod
    def _csr(faces, items, n_faces):
        """faces must be sorted."""
        order = np.argsort(faces, kind="stable")
        off = np.zeros(n_faces + 1, np.int64)
        np.add.at(off, faces + 1, 1)
        return np.cumsum(off), np.asarray(items, np.int64)[order]

    def eval(self, X, T):
        M = len(X)
        out = np.full(M, np.inf)
        beyond = np.full(M, np.inf)        # nearest point lies past an open hem end
        if M == 0:
            return out
        T = np.asarray(T, np.int64)
        Xz = self.charts.uv(X, T) if self.charts.ok else None
        for (off, flat), fn in zip(self.csr, (self._seg_dist, self._miter_dist)):
            if not len(flat):
                continue
            cnt = off[T + 1] - off[T]
            cum = np.cumsum(cnt)
            budget = 2_000_000             # (point, item) pairs per batch
            a = 0
            while a < M:
                base = cum[a - 1] if a else 0
                b = int(np.searchsorted(cum, base + budget, "right"))
                b = max(b, a + 1)
                c = cnt[a:b]
                n = int(c.sum())
                if n:
                    pp = np.repeat(np.arange(a, b), c)
                    first = np.repeat(np.cumsum(c) - c, c)
                    ps = flat[np.repeat(off[T[a:b]], c) + np.arange(n) - first]
                    dist, past = fn(X[pp], None if Xz is None else Xz[pp], ps)
                    np.minimum.at(out, pp[~past], dist[~past])
                    if past.any():
                        np.minimum.at(beyond, pp[past], dist[past])
                a = b
        # past an open end of the hem there is no line: the field is undefined
        out[beyond < out] = np.inf
        return out - self.d

    def _seg_dist(self, X, Xz, r):
        sg = self.segs
        k = self.rows["k"][r]
        AB = sg.AB[k]
        t = ((X - sg.A[k]) * AB).sum(1) / sg.L2[k]
        tc = np.clip(t, 0.0, 1.0)
        dist = _pair_value(sg, self.rows, r, X, Xz)
        past = ((t < 0) & sg.start_end[k]) | ((t > 1) & sg.end_end[k])
        return dist - (sg.eA[k] + tc * (sg.eB[k] - sg.eA[k])), past

    def _miter_dist(self, X, Xz, i):
        """Around a mitered inner corner, in the wedge where the corner vertex
        itself is the nearest hem point: the larger of the distances to the two
        edge lines (a miter join). Outside the wedge it is the distance to the
        corner, so the field stays continuous; its level line is the sharp
        miter. Measured in 3D and along the UV layout, the larger counts."""
        sg = self.segs
        m = self.mm[i]
        R = X - sg.mC[m]
        inside = ((R * sg.mU1[m]).sum(1) >= 0) & ((R * sg.mU2[m]).sum(1) <= 0)
        inplane = np.maximum((R * sg.mN1[m]).sum(1), (R * sg.mN2[m]).sum(1))
        off = (R * sg.mNC[m]).sum(1)
        val = np.where(inside, np.sqrt(inplane * inplane + off * off),
                       np.linalg.norm(R, axis=1))
        if Xz is not None:
            r = self.mrow[i]
            k = self.rows["k"][r]
            Az, Bz = self.rows["Az"][r], self.rows["Bz"][r]
            psi = sg.psi[k] * np.where(self.rows["par"][r], -1.0, 1.0)
            ur = Bz - Az
            ur = ur / np.maximum(np.abs(ur), 1e-30)
            turn = np.exp(1j * psi * (sg.mAlpha[m] - math.pi))
            out = self.mout[i]
            C = np.where(out, Az, Bz)
            u_out = np.where(out, ur, ur / turn)
            u_in = np.where(out, ur * turn, ur)
            n_out, n_in = u_out * 1j * psi, u_in * 1j * psi
            Rz = Xz - C
            inz = ((Rz * u_in.conjugate()).real >= 0) & ((Rz * u_out.conjugate()).real <= 0)
            vz = np.where(inz, np.maximum((Rz * n_in.conjugate()).real,
                                          (Rz * n_out.conjugate()).real), np.abs(Rz))
            val = np.maximum(val, vz * np.where(out, sg.fA[k], sg.fB[k]))
        return val - sg.mExtra[m], np.zeros(len(i), bool)


_lattice_cache = {}


def _lattice(n):
    """Barycentric lattice of a triangle subdivided n times: (weights, tris)."""
    hit = _lattice_cache.get(n)
    if hit:
        return hit
    index = {}
    wts = []
    for a in range(n + 1):
        for b in range(n + 1 - a):
            index[(a, b)] = len(wts)
            wts.append((1.0 - (a + b) / n, a / n, b / n))
    tris = []
    for a in range(n):
        for b in range(n - a):
            tris.append((index[(a, b)], index[(a + 1, b)], index[(a, b + 1)]))
            if a + b < n - 1:
                tris.append((index[(a + 1, b)], index[(a + 1, b + 1)], index[(a, b + 1)]))
    hit = (np.array(wts), np.array(tris, np.int64))
    _lattice_cache[n] = hit
    return hit


_fine_cache = {}


def _fine(n_c, ref):
    """Fine lattice (n_c * ref) of a triangle and, per fine sub-triangle, the
    index of the coarse sub-triangle (lattice n_c) that contains it."""
    key = (n_c, ref)
    hit = _fine_cache.get(key)
    if hit:
        return hit
    wts_f, ltri_f = _lattice(n_c * ref)
    cid = {}
    k = 0
    for a in range(n_c):
        for b in range(n_c - a):
            cid[(a, b, True)] = k
            k += 1
            if a + b < n_c - 1:
                cid[(a, b, False)] = k
                k += 1
    cen = wts_f[ltri_f].mean(axis=1) * n_c
    A, B = cen[:, 1], cen[:, 2]
    a = np.floor(A + 1e-9).astype(int)
    b = np.floor(B + 1e-9).astype(int)
    up = (A - a) + (B - b) < 1.0
    f2c = np.array([cid.get((int(x), int(y), bool(u)), cid.get((int(x), int(y), True), 0))
                    for x, y, u in zip(a, b, up)], np.int64)
    hit = (wts_f, ltri_f, f2c)
    _fine_cache[key] = hit
    return hit


def charts_for(topo):
    """The UV charts of a topology, built once and kept with it."""
    charts = getattr(topo, "_charts", None)
    if charts is None:
        charts = topo._charts = _Charts(topo)
    return charts


def distance_field(topo, chains, flip, corner_ids, corner_depth, reach):
    """The distance to the hem along the fabric, minus the extra inset at
    corners, for points up to ``reach`` from it. Returns (field, faces): call
    field.eval(X, T); faces are the triangles where it is defined."""
    charts = charts_for(topo)
    segs = _Segments(topo, chains, reach, flip, corner_ids, corner_depth, charts)
    if len(segs.A) == 0:
        return None, np.zeros(0, np.int64)
    rows = _visible(topo, segs, reach + corner_depth, charts)
    return _Field(segs, rows, 0.0, len(topo.tri), charts), np.unique(rows["f"])


def inset_lines(topo, chains, inset, flip, corner_ids, corner_depth, h):
    """Returns (lines, corner_points). lines: list of (P (N,3), tri (N,), closed)
    along the contour; corner_points: the sharp corner points on the lines."""
    d = abs(inset)
    charts = charts_for(topo)
    segs = _Segments(topo, chains, inset, flip, corner_ids, corner_depth, charts)
    if len(segs.A) == 0:
        return [], []

    # Closed lines shorter than this are islands of the distance (a pocket of
    # fabric just over the inset away from the hem), not stitch lines. A real
    # closed line runs around a closed hem and is about as long.
    lens = [(float(np.linalg.norm(np.diff(topo.co[np.r_[ids, ids[:1]] if c else ids], axis=0),
                                  axis=1).sum()), c) for ids, c in chains if len(ids) > 1]
    closed_lens = [L for L, c in lens if c]
    min_loop = 0.3 * (min(closed_lens) if closed_lens else max(L for L, _ in lens))

    rows = _visible(topo, segs, d + corner_depth + 3.0 * h, charts)
    field = _Field(segs, rows, d, len(topo.tri), charts)
    faces = np.unique(rows["f"])
    if not len(faces):
        return [], []

    # 1) coarse lattice on every visible face (3x coarser than h), faces with
    #    the same lattice size processed together
    REF = 3
    V = topo.V[faces]
    edge = np.linalg.norm(V - np.roll(V, -1, axis=1), axis=2).max(1)
    n_c = np.clip(np.ceil(edge / (h * REF)), 1, 32).astype(np.int64)
    ref = np.clip(np.ceil(edge / (h * n_c)), 1, REF).astype(np.int64)
    groups = []
    Xc, Tc = [], []
    off = 0
    for nc, rf in sorted(set(zip(n_c.tolist(), ref.tolist()))):
        sel = (n_c == nc) & (ref == rf)
        fs, Vs = faces[sel], V[sel]
        wts, ltri = _lattice(nc)
        Xc.append(np.einsum("pk,fkd->fpd", wts, Vs).reshape(-1, 3))
        Tc.append(np.repeat(fs, len(wts)))
        groups.append((nc, rf, fs, Vs, edge[sel] / nc * charts.stretch[fs], off, len(wts)))
        off += len(fs) * len(wts)
    gc = field.eval(np.vstack(Xc), np.concatenate(Tc))
    gc = np.where(np.isfinite(gc), gc, 1e9)

    # 2) refine only coarse cells that can hold the line: the field changes by
    #    at most L per unit length, so a cell whose corners are all further
    #    than L * cell size from the level cannot contain it.
    L = 1.0 + segs.slope
    Xf, Tf, Ft, Fface, Zf = [], [], [], [], []
    foff = 0
    for nc, rf, fs, Vs, cell, o, npt in groups:
        _, ltri = _lattice(nc)
        gv = gc[o:o + len(fs) * npt].reshape(len(fs), npt)[:, ltri]          # (F, C, 3)
        near0 = ((np.abs(gv).min(2) <= L * cell[:, None] * 1.05)
                 | ((gv < 0).any(2) & (gv >= 0).any(2)))
        if not near0.any():
            continue
        wts_f, ltri_f, f2c = _fine(nc, rf)
        fi, ti = np.nonzero(near0[:, f2c])                                    # fine tris
        need = np.zeros((len(fs), len(wts_f)), bool)
        need[fi[:, None], ltri_f[ti]] = True
        pf, pp = np.nonzero(need)
        local = np.full(need.shape, -1, np.int64)
        local[pf, pp] = np.arange(len(pf)) + foff
        Xf.append(np.einsum("nk,nkd->nd", wts_f[pp], Vs[pf]))
        # which sides of its triangle a lattice point lies on (bit per side)
        Zf.append(((wts_f[pp] == 0.0) * np.array([1, 2, 4])).sum(1))
        Tf.append(fs[pf])
        Ft.append(local[fi[:, None], ltri_f[ti]])
        Fface.append(fs[fi])
        foff += len(pf)
    if not Xf:
        return [], []
    X = np.vstack(Xf)
    TX = np.concatenate(Tf)
    ZX = np.concatenate(Zf)
    tris = np.vstack(Ft)
    tri_face = np.concatenate(Fface)
    g = field.eval(X, TX)
    void = ~np.isfinite(g)              # no hem visible (past an open end)
    g = np.where(void, 1e9, g)
    neg = g < 0

    # 3) sub-triangles the level crosses; each crossing lies on a lattice edge
    cnt = neg[tris].sum(1)
    # a jump to "no hem visible" is not a crossing of the inset
    mixed = ((cnt == 1) | (cnt == 2)) & ~void[tris].any(1)
    sel = tris[mixed]
    if not len(sel):
        return [], []
    e = np.stack([sel[:, [0, 1]], sel[:, [1, 2]], sel[:, [2, 0]]], 1)        # (n,3,2)
    cross = neg[e[..., 0]] != neg[e[..., 1]]                                  # two per row
    ee = e[cross].reshape(-1, 2, 2)
    E0, E1 = ee[:, 0], ee[:, 1]
    ST = tri_face[mixed]
    edges = np.vstack([E0, E1])
    key = np.minimum(edges[:, 0], edges[:, 1]) * len(X) + np.maximum(edges[:, 0], edges[:, 1])
    ukey, first, inv = np.unique(key, return_index=True, return_inverse=True)
    ue = edges[first]
    te = TX[ue[:, 0]]

    # 4) solve each crossing edge once (Illinois regula falsi on the exact field)
    lo_i = np.where(neg[ue[:, 0]], ue[:, 0], ue[:, 1])
    hi_i = np.where(neg[ue[:, 0]], ue[:, 1], ue[:, 0])
    lo, hi = X[lo_i], X[hi_i]
    glo, ghi = g[lo_i].copy(), g[hi_i].copy()
    side = np.zeros(len(lo), np.int8)
    # crossings on a side of their triangle must match the neighbour's exactly
    on_side = (ZX[ue[:, 0]] & ZX[ue[:, 1]]) != 0
    every = np.arange(len(lo))
    for it in range(6):
        a = every if it < 3 else np.nonzero(on_side)[0]
        if not len(a):
            break
        f = glo[a] / np.minimum(glo[a] - ghi[a], -1e-30)
        f = np.clip(f, 0.0, 1.0)
        mid = lo[a] + f[:, None] * (hi[a] - lo[a])
        gm = field.eval(mid, te[a])
        gm = np.where(np.isfinite(gm), gm, 1e9)
        inside = gm < 0
        lo[a] = np.where(inside[:, None], mid, lo[a])
        hi[a] = np.where(inside[:, None], hi[a], mid)
        # Illinois: halve the stale end's value so the bracket keeps shrinking
        sd = side[a]
        ghi[a] = np.where(inside, np.where(sd == 1, ghi[a] * 0.5, ghi[a]), gm)
        glo[a] = np.where(inside, gm, np.where(sd == -1, glo[a] * 0.5, glo[a]))
        side[a] = np.where(inside, 1, -1).astype(np.int8)
    f = np.clip(glo / np.minimum(glo - ghi, -1e-30), 0.0, 1.0)
    upos = lo + f[:, None] * (hi - lo)

    # 5) link: crossing edges inside one face are shared exactly; across a
    #    mesh edge the two faces' lattices differ, so merge by position there
    tol = max(h * 1e-3, topo.span * 1e-8)
    node = np.full(len(upos), -1, np.int64)
    inner = np.nonzero(~on_side)[0]
    node[inner] = np.arange(len(inner))
    nodes = len(inner)
    side = np.nonzero(on_side)[0]
    if len(side):
        kd = kdtree.KDTree(len(side))
        for i, p in zip(side.tolist(), upos[side].tolist()):
            kd.insert(p, i)
        kd.balance()
        for i, p in zip(side.tolist(), upos[side].tolist()):
            if node[i] >= 0:
                continue
            for _, j, _ in kd.find_range(p, tol):
                if node[j] < 0:
                    node[j] = nodes
            node[i] = nodes
            nodes += 1
    pos = np.zeros((nodes, 3))
    pos[node] = upos
    ns = len(E0)
    a_node = node[inv[:ns]]
    b_node = node[inv[ns:]]
    # node -> its segments (most nodes have two: the line goes through)
    good = np.nonzero(a_node != b_node)[0]
    ends_n = np.concatenate([a_node[good], b_node[good]])
    ends_k = np.concatenate([good, good])
    order = np.argsort(ends_n, kind="stable")
    ends_n, ends_k = ends_n[order], ends_k[order]
    starts = np.searchsorted(ends_n, np.arange(nodes + 1))
    deg = np.diff(starts).tolist()
    inc = ends_k.tolist()
    first = starts.tolist()
    A, B, S = a_node.tolist(), b_node.tolist(), ST.tolist()
    used = [False] * ns

    def walk(start, k):
        seq, tris = [start], []
        cur = start
        while True:
            used[k] = True
            nxt = B[k] if A[k] == cur else A[k]
            seq.append(nxt)
            tris.append(S[k])
            cur = nxt
            if deg[cur] != 2:
                break
            f = first[cur]
            k2 = inc[f] if inc[f] != k else inc[f + 1]
            if used[k2]:
                break
            k = k2
        return seq, tris

    lines = []
    for v in np.nonzero(np.asarray(deg) != 2)[0].tolist():
        for k in inc[first[v]:first[v + 1]]:
            if not used[k]:
                lines.append(walk(v, k) + (False,))
    for k in good.tolist():
        if not used[k]:
            seq, tris = walk(A[k], k)
            lines.append((seq, tris, len(seq) > 3 and seq[0] == seq[-1]))

    out = []
    for seq, tris, closed in lines:
        if closed:
            seq = seq[:-1]
        P = pos[np.asarray(seq)]
        T = np.asarray(tris + ([tris[-1]] if not closed else []), np.int64)[:len(P)]
        length = float(np.linalg.norm(np.diff(np.vstack([P, P[:1]]) if closed else P,
                                              axis=0), axis=1).sum())
        if length < max(4.0 * h, 1e-4) or (closed and length < min_loop):
            continue
        out.append((P, T, closed))

    corners = _apexes(topo, segs, field, h)
    return _insert_apexes(out, corners, h), [c[0] for c in corners]


def _apexes(topo, segs, field, h):
    """Exact corner points: where the contour crosses each marked corner's
    bisector, found by bisection along a surface walk."""
    if not segs.corners:
        return []
    C = np.array([c[0] for c in segs.corners])
    T = np.array([c[1] for c in segs.corners], np.int64)
    Dv = np.array([c[2] for c in segs.corners])
    smax = np.array([c[3] for c in segs.corners]) * 1.5 + 2.0 * h

    def at(s):
        P, t, _ = topo.walk(C, T, Dv, s)
        g = field.eval(P, t)
        return P, t, np.where(np.isfinite(g), g, 1e9)

    K = 12
    grid = np.linspace(0.0, 1.0, K + 1)[1:]
    gs = np.stack([at(smax * f)[2] for f in grid], 1)          # (n, K)
    pos = gs >= 0
    first = np.where(pos.any(1), pos.argmax(1), -1)
    ok = first >= 0
    lo = np.where(first > 0, grid[np.maximum(first - 1, 0)], 0.0) * smax
    hi = grid[np.maximum(first, 0)] * smax
    for _ in range(18):
        mid = (lo + hi) * 0.5
        inside = at(mid)[2] < 0
        lo = np.where(inside, mid, lo)
        hi = np.where(inside, hi, mid)
    P, t, _ = at((lo + hi) * 0.5)
    return [(P[i], int(t[i])) for i in np.nonzero(ok)[0].tolist()]


def _insert_apexes(lines, corners, h):
    """Put each corner point into the line it lies on, replacing the line
    points around it (which cut the corner by up to a lattice cell)."""
    if not corners or not lines:
        return lines
    # each corner goes to the line with the nearest point (vectorised search)
    allP = np.vstack([P for P, _, _ in lines])
    owner = np.repeat(np.arange(len(lines)), [len(P) for P, _, _ in lines])
    Q = np.array([q for q, _ in corners])
    p2 = (allP * allP).sum(1)
    mine = defaultdict(list)
    for a in range(0, len(Q), 16):
        q = Q[a:a + 16]
        d2 = p2[None] + (q * q).sum(1)[:, None] - 2.0 * (q @ allP.T)
        best = d2.argmin(1)
        for c, (b, dd) in enumerate(zip(best.tolist(), d2[np.arange(len(q)), best].tolist())):
            if dd <= (2.0 * h) ** 2:
                mine[int(owner[b])].append(corners[a + c])
    out = []
    for li, (P, T, closed) in enumerate(lines):
        if li not in mine:
            out.append((P, T, closed))
            continue
        P = P.copy()
        T = T.copy()
        for q, tq in mine[li]:
            dist = np.linalg.norm(P - q, axis=1)
            i = int(dist.argmin())
            if dist[i] > 2.0 * h:
                continue
            n = len(P)
            r = 1.5 * h
            lo, hi = i, i
            while (lo - 1 >= 0 or closed) and hi - lo + 1 < n - 2 and dist[(lo - 1) % n] < r:
                lo -= 1
            while (hi + 1 < n or closed) and hi - lo + 1 < n - 2 and dist[(hi + 1) % n] < r:
                hi += 1
            if closed and lo < 0:
                P, T, dist = np.roll(P, -lo, 0), np.roll(T, -lo), np.roll(dist, -lo)
                hi -= lo
                lo = 0
            elif closed and hi >= n:
                k = hi - n + 1
                P, T, dist = np.roll(P, -k, 0), np.roll(T, -k), np.roll(dist, -k)
                lo -= k
                hi -= k
            P = np.vstack([P[:lo], q[None], P[hi + 1:]])
            T = np.concatenate([T[:lo], [tq], T[hi + 1:]])
        out.append((P, T, closed))
    return out
