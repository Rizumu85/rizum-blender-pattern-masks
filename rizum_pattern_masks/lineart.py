# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Rizum
"""Line art: a solid band along the marked edges.

A line layer covers every point whose distance from the edges (along the
fabric, as for the stitches) lies between ``offset`` and ``offset + width``.
So its width is the same real size everywhere, whatever the UV density, and
its corners are as sharp as the stitch line's: marked inner corners get the
same miter join, outer corners are sharp by themselves.

With Smooth, the inner side of a line follows a smoothed line instead (built
like the stitch line: smoothed between corners, sharp at marked corners), while
the outer side keeps the exact shape of the edge, so the line still fills right
up to it.

* ``strips``  - preview geometry: a strip along each band.
* ``raster``  - the bake: each texel's distance, turned into antialiased
  coverage of each band. No ray casting, so nothing from another layer of the
  mesh ends up in the texture.
"""

import numpy as np

from . import contour


def _resample(P, T, closed, keep, step):
    """Thin a dense contour to about ``step`` spacing, keeping the points in
    ``keep`` (corner points) and the ends exactly."""
    n = len(P)
    if n < 3:
        return P, T
    seg = np.linalg.norm(np.diff(P, axis=0), axis=1)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    take = np.zeros(n, bool)
    take[0] = True
    if not closed:
        take[-1] = True
    take[keep] = True
    last = 0.0
    for i in range(1, n):
        if take[i] or cum[i] - last >= step:
            take[i] = True
            last = cum[i]
    return P[take], T[take]


def _strip(topo, P, T, closed, hw, lift):
    """Quads of a strip 2*hw wide centred on the polyline P, mitred at every
    vertex (so the corners of the line stay sharp), lifted off the surface."""
    n = len(P)
    if n < 2:
        return np.zeros((0, 3)), np.zeros((0, 4), np.int64)
    nv = topo.n_o[T]
    nxt = np.roll(P, -1, axis=0) if closed else np.vstack([P[1:], P[-1:]])
    d = nxt - P
    if not closed:
        d[-1] = P[-1] - P[-2]
    perp = np.cross(nv, d)
    perp /= np.maximum(np.linalg.norm(perp, axis=1), 1e-30)[:, None]
    prev = np.roll(perp, 1, axis=0)
    if not closed:
        prev[0] = perp[0]
    m = prev + perp
    m /= np.maximum(np.linalg.norm(m, axis=1), 1e-30)[:, None]
    scale = 1.0 / np.clip((m * perp).sum(1), 0.3, 1.0)       # miter, capped
    off = m * (hw * scale)[:, None]
    up = nv * lift
    left, right = P + off + up, P - off + up
    co = np.vstack([left, right])
    i = np.arange(n if closed else n - 1)
    j = (i + 1) % n
    quads = np.stack([i, j, j + n, i + n], 1)
    return co, quads


def inner_curves(topo, chains, corner_ids, flip, off, wid, dep, smooth):
    """The smoothed inner side of a line: Centerlines at offset + width,
    smoothed like the stitch line."""
    from . import core
    ds = core.centerline_spacing(topo, chains, smooth)
    return core.build_lines(topo, chains, off + wid, smooth, flip, ds, corner_ids, dep)


def _smooth_strip(topo, chains, corner_ids, flip, off, wid, dep, smooth, h, lift):
    """Preview strip from the smoothed inner side to the exact outer side."""
    from mathutils import kdtree
    cls = inner_curves(topo, chains, corner_ids, flip, off, wid, dep, smooth)
    if off > 0:
        outer, _ = contour.inset_lines(topo, chains, off, flip, corner_ids, dep, h)
        O = [P for P, _, _ in outer]
    else:                                   # the edge itself, finely sampled
        O = []
        step = max(min(wid, h) * 0.5, 1e-9)
        for ids, closed in chains:
            Q = topo.co[np.r_[ids, ids[:1]] if closed else np.asarray(ids)]
            for a, b in zip(Q[:-1], Q[1:]):
                n = max(1, int(np.ceil(np.linalg.norm(b - a) / step)))
                O.append(a + (b - a) * (np.arange(n) / n)[:, None])
            O.append(Q[-1:])
    if not O or not cls:
        return np.zeros((0, 3)), np.zeros((0, 4), np.int64)
    O = np.vstack(O)
    kd = kdtree.KDTree(len(O))
    for i, q in enumerate(O.tolist()):
        kd.insert(q, i)
    kd.balance()
    cos, quads, base = [], [], 0
    for cl in cls:
        n = len(cl.tri)
        P, T = cl.P[:n], cl.tri
        if n < 2:
            continue
        near = np.array([kd.find(p)[0][:] for p in P.tolist()])
        up = topo.n_o[T] * lift
        co = np.vstack([P + up, near + up])
        i = np.arange(n if cl.closed else n - 1)
        j = (i + 1) % n
        cos.append(co)
        quads.append(np.stack([i, j, j + n, i + n], 1) + base)
        base += len(co)
    if not quads:
        return np.zeros((0, 3)), np.zeros((0, 4), np.int64)
    return np.vstack(cos), np.vstack(quads)


def strips(topo, chains, corner_ids, flip, layers):
    """Preview strips of all line layers: (co (N,3), quads (Q,4)).
    layers: [(offset, width, corner_depth, smooth)] in scene units."""
    cos, quads = [], []
    base = 0
    for off, wid, dep, smooth in layers:
        if wid <= 0:
            continue
        if smooth > 0:
            h = max(wid / 4.0, topo.mean_edge / 48.0, topo.span * 1e-5)
            co, q = _smooth_strip(topo, chains, corner_ids, flip, off, wid, dep, smooth, h,
                                  max(0.15 * wid, topo.span * 2e-5))
            if len(q):
                cos.append(co)
                quads.append(q + base)
                base += len(co)
            continue
        mid = off + 0.5 * wid
        h = max(min(mid, wid) / 4.0, topo.mean_edge / 48.0, topo.span * 1e-5)
        lines, corners = contour.inset_lines(topo, chains, mid, flip, corner_ids, dep, h)
        lift = max(0.15 * wid, topo.span * 2e-5)
        # corner points are exact copies of points on the lines: find them once
        keeps = [np.zeros(len(P), bool) for P, _, _ in lines]
        if corners and lines:
            allP = np.vstack([P for P, _, _ in lines])
            owner = np.repeat(np.arange(len(lines)), [len(P) for P, _, _ in lines])
            start = np.concatenate([[0], np.cumsum([len(P) for P, _, _ in lines])])
            for q in corners:
                for i in np.nonzero((allP == q).all(axis=1))[0].tolist():
                    keeps[owner[i]][i - start[owner[i]]] = True
        for (P, T, closed), keep in zip(lines, keeps):
            P2, T2 = _resample(P, T, closed, np.nonzero(keep)[0], max(min(0.5 * wid, h), 1e-9))
            co, q = _strip(topo, P2, T2, closed, 0.5 * wid, lift)
            if len(q):
                cos.append(co)
                quads.append(q + base)
                base += len(co)
    if not quads:
        return np.zeros((0, 3)), np.zeros((0, 4), np.int64)
    return np.vstack(cos), np.vstack(quads)


def field_for(topo, chains, corner_ids, flip, layers):
    """One distance field for all layers (reaching past the widest one)."""
    outer = max(off + wid + 2.0 * sm for off, wid, _, sm in layers)
    depth = max(l[2] for l in layers)
    margin = max(outer * 0.1, topo.mean_edge / 16.0)
    return contour.distance_field(topo, chains, flip, corner_ids, depth, outer + margin)


def _uv_of(topo, P, T):
    """UV of points P on (the planes of) triangles T."""
    V = topo.V[T]
    e1, e2 = V[:, 1] - V[:, 0], V[:, 2] - V[:, 0]
    d = P - V[:, 0]
    g11, g12, g22 = (e1 * e1).sum(1), (e1 * e2).sum(1), (e2 * e2).sum(1)
    p, q = (d * e1).sum(1), (d * e2).sum(1)
    det = np.maximum(g11 * g22 - g12 * g12, 1e-40)
    b1 = (g22 * p - g12 * q) / det
    b2 = (g11 * q - g12 * p) / det
    U = topo.uv[T]
    return U[:, 0] + b1[:, None] * (U[:, 1] - U[:, 0]) + b2[:, None] * (U[:, 2] - U[:, 0])


def _inner_sdf(topo, field, cls, b, res, tile, texel):
    """For the pixels near the smoothed inner side: the distance from the edge
    of the nearest point on it. A pixel is inside the line where its own
    distance is smaller. (No sides or directions involved, so a little hook
    of the smoothed line at a corner cannot flip anything.)
    Returns (sorted flat pixel keys, values, how far the smoothed line strays
    from the exact one)."""
    segs_a, segs_b, segs_fa, segs_fb = [], [], [], []
    dev = 0.0
    dev_px = 0.0
    for cl in cls:
        n = len(cl.tri)
        if n < 2:
            continue
        P, T = cl.P[:n], cl.tri
        px = (_uv_of(topo, P, T) - tile) * res - 0.5
        f = field.eval(P, T)
        ok = np.isfinite(f)
        if not ok.any():
            continue
        f = np.where(ok, f, b)
        dv = np.abs(f - b)
        dev = max(dev, float(dv.max()))
        dev_px = max(dev_px, float((dv / np.maximum(texel[T], 1e-12)).max()))
        i = np.arange(n if cl.closed else n - 1)
        j = (i + 1) % n
        d = px[j] - px[i]
        # not across a UV seam
        d3 = np.linalg.norm(P[j] - P[i], axis=1) / np.maximum(texel[T[i]], 1e-12)
        keep = np.linalg.norm(d, axis=1) <= 4.0 * d3 + 3.0
        segs_a.append(px[i][keep]); segs_b.append(px[j][keep])
        segs_fa.append(f[i][keep]); segs_fb.append(f[j][keep])
    if not segs_a:
        return np.zeros(0, np.int64), np.zeros(0), dev
    A, B = np.vstack(segs_a), np.vstack(segs_b)
    FA, FB = np.concatenate(segs_fa), np.concatenate(segs_fb)
    R = int(min(48, np.ceil(dev_px + 3.0)))
    W = int(np.ceil(np.linalg.norm(B - A, axis=1).max())) + 2 * R + 2
    o = np.arange(W)
    ox, oy = np.meshgrid(o, o)
    ox, oy = ox.ravel(), oy.ravel()
    keys, dists, vals = [], [], []
    step = max(1, 2_000_000 // (W * W))
    for a in range(0, len(A), step):
        a0, b0 = A[a:a + step], B[a:a + step]
        fa, fb = FA[a:a + step, None], FB[a:a + step, None]
        base = np.floor(np.minimum(a0, b0)).astype(np.int64) - R
        cx = base[:, 0:1] + ox[None]
        cy = base[:, 1:2] + oy[None]
        d = b0 - a0
        L2 = np.maximum((d * d).sum(1), 1e-12)[:, None]
        t = np.clip(((cx - a0[:, 0:1]) * d[:, 0:1] + (cy - a0[:, 1:2]) * d[:, 1:2]) / L2, 0.0, 1.0)
        rx, ry = cx - (a0[:, 0:1] + t * d[:, 0:1]), cy - (a0[:, 1:2] + t * d[:, 1:2])
        dist = np.sqrt(rx * rx + ry * ry)
        ok = (dist <= R) & (cx >= 0) & (cx < res) & (cy >= 0) & (cy < res)
        keys.append((cy * res + cx)[ok]); dists.append(dist[ok])
        vals.append(np.broadcast_to(fa + t * (fb - fa), dist.shape)[ok])
    keys, dists, vals = np.concatenate(keys), np.concatenate(dists), np.concatenate(vals)
    order = np.lexsort((dists, keys))                # per pixel, the nearest segment first
    keys, vals = keys[order], vals[order]
    first = np.r_[True, keys[1:] != keys[:-1]]
    return keys[first], vals[first], dev


def raster(topo, field, faces, res, tile, layers, inner=None, block=8):
    """Coverage images (res, res), Blender orientation (row 0 at the bottom),
    one per layer, for the triangles ``faces`` of one UV tile.
    layers: [(offset, width, corner_depth, smooth)]; inner: per layer None or
    the smoothed inner Centerlines."""
    imgs = [np.zeros((res, res), np.float32) for _ in layers]
    if field is None or not len(faces) or topo.uv is None:
        return imgs
    charts = contour.charts_for(topo)
    tile = np.asarray(tile, np.float64)
    with np.errstate(divide="ignore", invalid="ignore"):
        texel = 1.0 / (res * np.sqrt(topo.uv_area / topo.area))   # 3D size of a texel
    texel = np.where(np.isfinite(texel), texel, 0.0)
    inner = inner or [None] * len(layers)
    sdfs = []
    hi_all = 0.0
    for (off, wid, _, _), cls in zip(layers, inner):
        if cls:
            sdf = _inner_sdf(topo, field, cls, off + wid, res, tile, texel)
            sdfs.append(sdf)
            hi_all = max(hi_all, off + wid + sdf[2])
        else:
            sdfs.append(None)
            hi_all = max(hi_all, off + wid)
    lo_all = min(l[0] for l in layers)
    slope = 1.0 + field.segs.slope

    # 1) blocks of pixels per triangle; keep those the bands can reach
    #    (one pixel round it: the pixels a UV island border cuts through)
    bx, by, bt = [], [], []
    for t in faces.tolist():
        U = (topo.uv[t] - tile) * res - 0.5
        x0, y0 = np.floor(U.min(0)).astype(int) - 1
        x1, y1 = np.ceil(U.max(0)).astype(int) + 1
        x0, y0 = max(x0, 0), max(y0, 0)
        x1, y1 = min(x1, res - 1), min(y1, res - 1)
        if x1 < x0 or y1 < y0 or texel[t] <= 0:
            continue
        gx = np.arange(x0, x1 + 1, block)
        gy = np.arange(y0, y1 + 1, block)
        X, Y = np.meshgrid(gx, gy)
        bx.append(X.ravel()); by.append(Y.ravel()); bt.append(np.full(X.size, t))
    if not bt:
        return imgs
    bx, by, bt = np.concatenate(bx), np.concatenate(by), np.concatenate(bt)
    cx, cy = bx + 0.5 * (block - 1), by + 0.5 * (block - 1)
    P, inside = _points(topo, bt, cx, cy, tile, res, allow_outside=True)
    f = field.eval(P, bt)
    rb = block * 0.75 * texel[bt] * charts.stretch[bt] * slope
    keep = np.isfinite(f) & (f - rb <= hi_all + 2 * texel[bt]) & (f + rb >= lo_all - 2 * texel[bt])
    bx, by, bt = bx[keep], by[keep], bt[keep]
    if not len(bt):
        return imgs

    # 2) every pixel of the kept blocks that lies on its triangle, and the
    #    pixels an open UV border cuts through (their centre just off the
    #    island): those take the value at the border, so a line along the
    #    border shows there even when it is thinner than a texel
    open_edges = _open_uv_edges(topo)
    o = np.arange(block)
    ox, oy = np.meshgrid(o, o)
    ox, oy = ox.ravel(), oy.ravel()
    step = max(1, 2_000_000 // (block * block))
    for a in range(0, len(bt), step):
        px = (bx[a:a + step, None] + ox[None]).ravel()
        py = (by[a:a + step, None] + oy[None]).ravel()
        pt = np.repeat(bt[a:a + step], block * block)
        ok = (px < res) & (py < res)
        px, py, pt = px[ok], py[ok], pt[ok]
        P, inside = _points(topo, pt, px, py, tile, res)
        use = inside | _on_open_border(topo, open_edges, pt, px, py, tile, res)
        px, py, pt, P = px[use], py[use], pt[use], P[use]
        if not len(pt):
            continue
        f = field.eval(P, pt)
        tau = np.maximum(texel[pt], 1e-12)
        for img, (off, wid, _, _), sdf in zip(imgs, layers, sdfs):
            if sdf is None:
                inner = np.clip((off + wid - f) / tau + 0.5, 0.0, 1.0)
            else:                       # the smoothed inner side
                keys, vals, dev = sdf
                k = py * res + px
                at = np.clip(np.searchsorted(keys, k), 0, max(len(keys) - 1, 0))
                hit = (keys[at] == k) if len(keys) else np.zeros(len(k), bool)
                inner = np.where(hit, np.clip((vals[at] - f) / tau + 0.5, 0.0, 1.0)
                                 if len(keys) else 0.0, (f < off + wid).astype(np.float64))
                # never further from the edge than the smoothed line can stray
                inner *= (f <= off + wid + dev + 2.0 * tau)
            # A line that starts at the edge stays on the edge: with Corner
            # Inset its inner side goes deeper at a corner, the outer side
            # does not leave the edge (no lower bound).
            if off > 0:
                inner *= np.clip((f - off) / tau + 0.5, 0.0, 1.0)
            inner = np.where(np.isfinite(f), inner, 0.0).astype(np.float32)
            np.maximum.at(img, (py, px), inner)
    return imgs


def _open_uv_edges(topo):
    """(F, 3) bool: is the edge opposite each corner of each triangle an open
    UV border (no other triangle has it in UV: the mesh's own border or a
    seam)? Cached on the topology."""
    hit = getattr(topo, "_open_uv_edges", None)
    if hit is not None:
        return hit
    q = np.round(topo.uv * 2.0 ** 22).astype(np.int64)            # (F, 3, 2)
    a = q[:, [1, 2, 0]]                                            # edge opposite corner i
    b = q[:, [2, 0, 1]]
    first = (a[..., 0] < b[..., 0]) | ((a[..., 0] == b[..., 0]) & (a[..., 1] <= b[..., 1]))
    lo = np.where(first[..., None], a, b)
    hi = np.where(first[..., None], b, a)
    keys = np.concatenate([lo, hi], -1).reshape(-1, 4)
    _, inv, cnt = np.unique(keys, axis=0, return_inverse=True, return_counts=True)
    hit = (cnt[inv.reshape(-1)] == 1).reshape(-1, 3)
    topo._open_uv_edges = hit
    return hit


def _on_open_border(topo, open_edges, T, px, py, tile, res, reach=0.75):
    """Pixel centres just off their triangle, within ``reach`` pixels of it,
    and off it only across open UV border edges. (Known limit: where two UV
    islands are packed less than a pixel apart, such a pixel can lie on the
    other island and take the line's border value.)"""
    U = (topo.uv[T] - tile) * res - 0.5                              # (n,3,2)
    out = np.zeros(len(T), bool)
    beyond = np.zeros(len(T), bool)
    for i in range(3):
        A, B = U[:, (i + 1) % 3], U[:, (i + 2) % 3]
        C = U[:, i]
        e = B - A
        L = np.maximum(np.linalg.norm(e, axis=1), 1e-12)
        # signed distance of the centre from the edge line, positive towards C
        side = lambda x, y: (e[:, 0] * (y - A[:, 1]) - e[:, 1] * (x - A[:, 0])) / L  # noqa: E731
        sc = np.sign(side(C[:, 0], C[:, 1]))
        d = side(px.astype(np.float64), py.astype(np.float64)) * sc
        off = d < -1e-9                                              # beyond this edge
        out |= off
        beyond |= off & (~open_edges[T, i] | (d < -reach))
    return out & ~beyond


def _points(topo, T, px, py, tile, res, allow_outside=False):
    """3D points of pixel centres (px, py) on triangles T, and whether each
    centre lies on its triangle."""
    U = (topo.uv[T] - tile) * res - 0.5                              # (n,3,2)
    a, b, c = U[:, 0], U[:, 1], U[:, 2]
    v0, v1 = b - a, c - a
    q = np.stack([px - a[:, 0], py - a[:, 1]], 1)
    det = v0[:, 0] * v1[:, 1] - v0[:, 1] * v1[:, 0]
    ok = np.abs(det) > 1e-12
    det = np.where(ok, det, 1.0)
    w1 = (q[:, 0] * v1[:, 1] - q[:, 1] * v1[:, 0]) / det
    w2 = (v0[:, 0] * q[:, 1] - v0[:, 1] * q[:, 0]) / det
    w0 = 1.0 - w1 - w2
    eps = -1e-6
    inside = ok & (w0 >= eps) & (w1 >= eps) & (w2 >= eps)
    if allow_outside:
        # block centres may fall just off the triangle: keep them on its plane
        w = np.stack([w0, w1, w2], 1)
    else:
        w = np.clip(np.stack([w0, w1, w2], 1), 0.0, 1.0)
        w /= np.maximum(w.sum(1, keepdims=True), 1e-12)
    V = topo.V[T]
    return (w[:, :, None] * V).sum(1), inside
