"""Geometry core for the stitch generator.

Everything is computed in world space with numpy:

* ``Topology``     - welded triangle mesh with adjacency, used to walk on the surface.
* ``build_chains`` - turn the marked edges into ordered polylines.
* ``build_lines``  - the stitch line: the inset contour from contour.py, smoothed
  per stretch between corners.
* ``build_ribbons`` - dashed, rounded-rectangle ribbons slightly above the surface.

Walking across triangles (instead of snapping to the nearest point) keeps the line
on the same layer of fabric, so folds that touch each other are never mixed up.
"""

import math
from collections import defaultdict

import numpy as np
from mathutils import kdtree
from mathutils.bvhtree import BVHTree

PATH_ATTR = "stitch_path"          # edges the stitches follow
LINE_ATTR = "stitch_line_path"     # edges of a line art layer; newer layers each have
                                   # their own: stitch_line_path_<n>
CORNER_ATTR = "stitch_corner"
CORNER_STEPS = 6
MAX_STITCHES = 20000


class StitchLimitError(ValueError):
    """A limit the user can fix by changing values; message is a template."""

    def __init__(self, template, **kw):
        super().__init__(template.format(**kw))
        self.template = template
        self.kw = kw
EPS = 1e-12


def _normalize(v):
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    return v / np.maximum(n, 1e-30)


def line_attr_names(me):
    """Edge attributes holding line art edges (one per layer)."""
    return sorted(n for n, a in me.attributes.items()
                  if (n == LINE_ATTR or n.startswith(LINE_ATTR + "_")) and a.domain == 'EDGE')


def read_path_edges(me, name=PATH_ATTR, sign=1):
    """Return (k, 2) vertex index pairs of edges marked with ``name``: the
    layer's own edges (value 1), or with ``sign`` -1 the edges it takes out
    of what it gets from the layer it refers to (value -1)."""
    attr = me.attributes.get(name)
    ne = len(me.edges)
    if attr is None or attr.domain != 'EDGE' or ne == 0:
        return np.zeros((0, 2), np.int64)
    if attr.data_type == 'BOOLEAN':
        vals = np.zeros(ne, bool)
    else:
        vals = np.zeros(ne, np.int32)
    attr.data.foreach_get("value", vals)
    ev = np.empty(ne * 2, np.int32)
    me.edges.foreach_get("vertices", ev)
    pick = vals > 0 if sign > 0 else vals < 0
    return ev.reshape(-1, 2)[pick].astype(np.int64)


def read_corner_verts(me):
    """Vertex indices marked as sharp corners (CORNER_ATTR on points)."""
    attr = me.attributes.get(CORNER_ATTR)
    nv = len(me.vertices)
    if attr is None or attr.domain != 'POINT' or nv == 0:
        return np.zeros(0, np.int64)
    vals = np.zeros(nv, bool if attr.data_type == 'BOOLEAN' else np.int32)
    attr.data.foreach_get("value", vals)
    return np.nonzero(vals)[0].astype(np.int64)


def pick_uv(me, uv_name):
    """The UV map to use: the one picked by name, else the mesh's active one."""
    if uv_name and uv_name in me.uv_layers:
        return me.uv_layers[uv_name]
    return me.uv_layers.active or (me.uv_layers[0] if len(me.uv_layers) else None)


def mesh_signature(me, mw, uv_name):
    """(everything the stitches depend on, the line art edges)."""
    nv = len(me.vertices)
    co = np.empty(nv * 3, np.float32)
    me.vertices.foreach_get("co", co)
    path = read_path_edges(me)
    nl = len(me.loops)
    lv = np.empty(nl, np.int32)
    me.loops.foreach_get("vertex_index", lv)
    uv_hash = 0
    uvl = pick_uv(me, uv_name)
    if uvl is not None:
        uv = np.empty(nl * 2, np.float32)
        uvl.data.foreach_get("uv", uv)
        uv_hash = hash(uv.tobytes())
    return (
        nv, len(me.edges), len(me.polygons), nl,
        hash(co.tobytes()),
        hash(path.tobytes()), hash(read_path_edges(me, PATH_ATTR, -1).tobytes()),
        hash(read_corner_verts(me).tobytes()),
        hash(lv.tobytes()), uv_hash,
        tuple(round(x, 9) for row in mw for x in row),
        uv_name,
    ), hash(tuple((n, hash(read_path_edges(me, n).tobytes()),
                   hash(read_path_edges(me, n, -1).tobytes())) for n in line_attr_names(me)))


def _consistent_orientation(tri, nbr):
    """+1/-1 per triangle so that connected faces agree on their winding
    (like "Recalculate Outside", but only for our own use). Each connected
    part keeps the winding most of its faces already have."""
    T = len(tri)
    orient = np.zeros(T, np.int8)
    tl = tri.tolist()
    nl = nbr.tolist()
    for seed in range(T):
        if orient[seed]:
            continue
        orient[seed] = 1
        comp = [seed]
        stack = [seed]
        while stack:
            t = stack.pop()
            vt = tl[t]
            for k in range(3):
                u = nl[t][k]
                if u < 0 or orient[u]:
                    continue
                a, b = vt[k], vt[(k + 1) % 3]
                vu = tl[u]
                j = vu.index(a) if a in vu else -1
                # same direction a->b in both faces means opposite winding
                same_dir = j >= 0 and vu[(j + 1) % 3] == b
                orient[u] = -orient[t] if same_dir else orient[t]
                comp.append(u)
                stack.append(u)
        if orient[comp].sum() < 0:          # keep the majority winding
            orient[comp] *= -1
    return orient.astype(np.float64)


class Topology:
    """Welded triangle soup with adjacency (world space)."""

    def __init__(self, me, mw, uv_name=""):
        nv = len(me.vertices)
        co = np.empty(nv * 3, np.float32)
        me.vertices.foreach_get("co", co)
        co = co.reshape(nv, 3).astype(np.float64)
        mw = np.array(mw, np.float64)
        co = co @ mw[:3, :3].T + mw[:3, 3]

        me.calc_loop_triangles()
        nt = len(me.loop_triangles)
        tv = np.empty(nt * 3, np.int32)
        tl = np.empty(nt * 3, np.int32)
        tp = np.empty(nt, np.int32)
        me.loop_triangles.foreach_get("vertices", tv)
        me.loop_triangles.foreach_get("loops", tl)
        me.loop_triangles.foreach_get("polygon_index", tp)
        tv = tv.reshape(nt, 3)
        tl = tl.reshape(nt, 3)

        # Weld by position so split vertices (hard edges / UV splits from FBX)
        # do not look like open borders.
        span = float(np.ptp(co, axis=0).max()) if nv else 1.0
        self.span = max(span, 1e-9)
        tol = self.span * 1e-7
        q = np.round(co / tol).astype(np.int64)
        _, first, inv = np.unique(q, axis=0, return_index=True, return_inverse=True)
        inv = inv.reshape(-1)
        self.vert_weld = inv
        self.co = co[first]

        tri = inv[tv]
        V = self.co[tri]
        cr = np.cross(V[:, 1] - V[:, 0], V[:, 2] - V[:, 0])
        area2 = np.linalg.norm(cr, axis=1)
        good = ((tri[:, 0] != tri[:, 1]) & (tri[:, 1] != tri[:, 2]) & (tri[:, 2] != tri[:, 0])
                & (area2 > (self.span * 1e-9) ** 2))
        tri, tl, tp, V, cr, area2 = tri[good], tl[good], tp[good], V[good], cr[good], area2[good]

        self.tri = tri
        self.tri_loops = tl
        self.tri_poly = tp
        self.V = V
        self.n = cr / area2[:, None]
        self.area = 0.5 * area2
        E = np.roll(V, -1, axis=1) - V            # edge k runs V[k] -> V[k+1]
        elen = np.linalg.norm(E, axis=2)
        self.eu = E / np.maximum(elen, 1e-30)[..., None]
        self.m = np.cross(self.eu, self.n[:, None, :])   # in-plane outward edge normals
        self.centroid = V.mean(axis=1)
        self.radius = np.linalg.norm(V - self.centroid[:, None], axis=2).max(axis=1)
        self.mean_edge = float(elen.mean()) if elen.size else 1.0

        # Edge -> triangle adjacency.
        nw = len(self.co)
        a = tri.astype(np.int64)
        b = np.roll(a, -1, axis=1)
        key = (np.minimum(a, b) * nw + np.maximum(a, b)).reshape(-1)
        order = np.argsort(key, kind="stable")
        ks = key[order]
        nbr = np.full(key.size, -1, np.int64)
        # Pair up edges shared by exactly two triangles; edges with three or more
        # (non-manifold) are treated as borders so a walk never picks a random layer.
        starts = np.concatenate([[True], ks[1:] != ks[:-1]])
        gid = np.cumsum(starts) - 1
        gsize = np.bincount(gid)[gid]
        same = np.nonzero((ks[1:] == ks[:-1]) & (gsize[1:] == 2))[0]
        A = order[same]
        B = order[same + 1]
        nbr[A] = B // 3
        nbr[B] = A // 3
        self.nbr = nbr.reshape(-1, 3)
        self._ks = ks
        self._order = order
        self._nw = nw
        self.n_o = self.n * _consistent_orientation(tri, self.nbr)[:, None]
        self.vert_tri = np.full(nw, -1, np.int64)
        self.vert_tri[tri.reshape(-1)] = np.repeat(np.arange(len(tri)), 3)

        # Active UV (per triangle corner).
        self.uv = None
        self.uv_name = ""
        uvl = pick_uv(me, uv_name)
        if uvl is not None:
            nl = len(me.loops)
            uv = np.empty(nl * 2, np.float32)
            uvl.data.foreach_get("uv", uv)
            uv = uv.reshape(nl, 2).astype(np.float64)[self.tri_loops]
            self.uv = uv
            d1 = uv[:, 1] - uv[:, 0]
            d2 = uv[:, 2] - uv[:, 0]
            self.uv_area = 0.5 * np.abs(d1[:, 0] * d2[:, 1] - d1[:, 1] * d2[:, 0])
            self.uv_name = uvl.name

        self._centroid_kd = None
        self._bvh = None

    def bvh(self):
        if self._bvh is None:
            self._bvh = BVHTree.FromPolygons(self.co.tolist(), self.tri.tolist(),
                                             all_triangles=True)
        return self._bvh

    # -- lookups -----------------------------------------------------------

    def edge_info(self, a, b):
        """For welded vertex pairs return (triangle, face count) per edge."""
        a = np.asarray(a, np.int64)
        b = np.asarray(b, np.int64)
        key = np.minimum(a, b) * self._nw + np.maximum(a, b)
        lo = np.searchsorted(self._ks, key, "left")
        hi = np.searchsorted(self._ks, key, "right")
        count = hi - lo
        tri = np.where(count > 0, self._order[np.minimum(lo, len(self._order) - 1)] // 3, -1)
        missing = tri < 0
        if missing.any():
            tri[missing] = self.vert_tri[a[missing]]
        return tri, count

    def corner_ids(self, me):
        return set(self.vert_weld[read_corner_verts(me)].tolist())

    def path_pairs(self, me, names=(PATH_ATTR,), sign=1):
        e = np.vstack([read_path_edges(me, n, sign) for n in names])
        if not len(e):
            return np.zeros((0, 2), np.int64)
        w = self.vert_weld[e]
        w = w[w[:, 0] != w[:, 1]]
        w = np.sort(w, axis=1)
        w = np.unique(w, axis=0)
        if len(w):
            tri, _ = self.edge_info(w[:, 0], w[:, 1])
            w = w[tri >= 0]          # loose edges / edges of degenerate faces only
        return w

    def centroid_kd(self):
        if self._centroid_kd is None:
            kd = kdtree.KDTree(len(self.centroid))
            for i, c in enumerate(self.centroid.tolist()):
                kd.insert(c, i)
            kd.balance()
            self._centroid_kd = kd
        return self._centroid_kd

    # -- surface walk --------------------------------------------------------

    def walk(self, p, t, d, s, max_iter=None):
        """Move points along the surface.

        p (N,3) start points lying on triangles t (N,), direction d (N,3),
        distance s (N,). The direction is re-projected into each triangle and
        carried across shared edges (straightest path). Points stop at open
        borders. Returns (p, t, stopped_at_border).
        """
        p = np.array(p, np.float64)
        t = np.array(t, np.int64)
        d = np.array(d, np.float64)
        s = np.array(s, np.float64)
        border = np.zeros(len(p), bool)
        active = (s > EPS) & (t >= 0)
        ar_cache = {}
        if max_iter is None:
            # each triangle crossing advances at least ~ a small edge length
            longest = float(s[active].max()) if active.any() else 0.0
            max_iter = 400 + int(8.0 * longest / max(self.mean_edge * 0.05, 1e-12))
        for _ in range(max_iter):
            idx = np.nonzero(active)[0]
            if idx.size == 0:
                break
            tt = t[idx]
            pp = p[idx]
            n = self.n[tt]
            dd = d[idx]
            dd = dd - (dd * n).sum(1)[:, None] * n
            ln = np.linalg.norm(dd, axis=1)
            ok = ln > 1e-20
            dd = dd / np.maximum(ln, 1e-30)[:, None]
            m = self.m[tt]
            V = self.V[tt]
            h = ((V - pp[:, None, :]) * m).sum(2)
            rate = (dd[:, None, :] * m).sum(2)
            with np.errstate(divide="ignore", invalid="ignore"):
                lam = np.where(rate > 1e-12, h / np.where(rate > 1e-12, rate, 1.0), np.inf)
            lam = np.maximum(lam, 0.0)
            k = len(idx)
            ar = ar_cache.get(k)
            if ar is None:
                ar = ar_cache[k] = np.arange(k)
            kk = lam.argmin(1)
            lmin = lam[ar, kk]
            rem = s[idx]
            fin = (~ok) | (lmin >= rem) | ~np.isfinite(lmin)

            fi = idx[fin]
            step = np.where(ok[fin] & np.isfinite(rem[fin]), rem[fin], 0.0)
            p[fi] = pp[fin] + dd[fin] * step[:, None]
            s[fi] = 0.0
            active[fi] = False

            c = ~fin
            if not c.any():
                continue
            ic = idx[c]
            tc = tt[c]
            kc = kk[c]
            dc = dd[c]
            pexit = pp[c] + dc * lmin[c][:, None]
            s[ic] = rem[c] - lmin[c]
            p[ic] = pexit
            t2 = self.nbr[tc, kc]
            at_border = t2 < 0
            if at_border.any():
                bi = ic[at_border]
                border[bi] = True
                active[bi] = False
            go = ~at_border
            if not go.any():
                continue
            ig = ic[go]
            tg = tc[go]
            kg = kc[go]
            t2g = t2[go]
            e = self.eu[tg, kg]
            P0 = self.V[tg, kg]
            P1 = self.V[tg, (kg + 1) % 3]
            third = self.V[t2g].sum(1) - P0 - P1
            qv = third - P0
            m2 = _normalize(qv - (qv * e).sum(1)[:, None] * e)
            along = (dc[go] * e).sum(1)
            perp = np.sqrt(np.maximum(0.0, 1.0 - along * along))
            d[ig] = along[:, None] * e + perp[:, None] * m2
            t[ig] = t2g
        return p, t, border


# -- chains -----------------------------------------------------------------

def build_chains(pairs, co=None):
    """Split edge pairs into ordered vertex chains. Returns [(ids, closed)]."""
    pairs = [tuple(x) for x in np.asarray(pairs).tolist()]
    adj = defaultdict(list)
    for i, (a, b) in enumerate(pairs):
        adj[a].append(i)
        adj[b].append(i)
    used = [False] * len(pairs)

    def run(v, ei):
        path = [v]
        cur = v
        while True:
            used[ei] = True
            a, b = pairs[ei]
            cur = b if a == cur else a
            path.append(cur)
            if len(adj[cur]) != 2:
                break
            nxt = [e for e in adj[cur] if not used[e]]
            if not nxt:
                break
            ei = nxt[0]
        return path

    chains = []
    for v, lst in adj.items():
        if len(lst) != 2:
            for ei in lst:
                if not used[ei]:
                    chains.append((run(v, ei), False))
    for ei in range(len(pairs)):
        if not used[ei]:
            path = run(pairs[ei][0], ei)
            closed = len(path) > 3 and path[0] == path[-1]
            if closed:
                path = path[:-1]
            chains.append((path, closed))
    if co is not None:
        chains = _join_through_forks(chains, co)
    return chains


def _drop_stubs(chains, co, fork_points):
    """Remove short open lines that start or end at a fork point."""
    if not fork_points:
        return chains

    def length(ids):
        return float(np.linalg.norm(np.diff(co[np.asarray(ids)], axis=0), axis=1).sum())

    longest = max(length(c) for c, _ in chains)
    out = []
    for ids, closed in chains:
        if not closed and (ids[0] in fork_points or ids[-1] in fork_points):
            if length(ids) < min(0.1 * longest, 0.03):      # short stub (under 3 cm)
                continue
        out.append((ids, closed))
    return out


def _join_through_forks(chains, co):
    """Where three or more lines meet in one point (e.g. duplicate vertices at a
    seam that were welded together), continue straight through: at each such
    point, pair the open line ends whose directions line up best. A line whose
    two ends meet there becomes a loop. Short stubs left hanging off such a
    point (a stray edge up a slit, say) are dropped: a stitch line there is
    never wanted."""
    ends = defaultdict(list)                 # vertex -> [(chain index, 0 start / 1 end)]
    for i, (ids, closed) in enumerate(chains):
        if not closed and len(ids) >= 2:
            ends[ids[0]].append((i, 0))
            ends[ids[-1]].append((i, 1))
    link = {}                                # (chain, end) -> (chain, end)
    fork_points = set()
    for v, lst in ends.items():
        if len(lst) < 3:
            continue
        fork_points.add(v)
        p = co[v]
        dirs = []
        for i, e in lst:
            ids = chains[i][0]
            d = co[ids[1] if e == 0 else ids[-2]] - p
            dirs.append(d / max(np.linalg.norm(d), 1e-30))
        cand = sorted(((-float(np.dot(dirs[x], dirs[y])), x, y)
                       for x in range(len(lst)) for y in range(x + 1, len(lst))), reverse=True)
        taken = set()
        for _, x, y in cand:                 # straightest pairs first
            if x in taken or y in taken:
                continue
            taken.update((x, y))
            link[lst[x]] = lst[y]
            link[lst[y]] = lst[x]
    if not link:
        return _drop_stubs(chains, co, fork_points)

    # walk the linked lines into merged chains (paths, or loops)
    seen = set()
    out = []

    def walk(i, e_in):
        """Follow from chain i entered at end e_in; returns (ids, closed)."""
        ids, first = [], (i, e_in)
        while True:
            seen.add(i)
            seg = list(chains[i][0])
            if e_in == 1:
                seg = seg[::-1]
            ids += seg if not ids else seg[1:]
            nxt = link.get((i, 1 - e_in))
            if nxt is None:
                return ids, False
            if nxt == first:
                return ids[:-1], True
            i, e_in = nxt

    for i, (ids, closed) in enumerate(chains):
        if closed or len(ids) < 2:
            out.append((ids, closed))
            seen.add(i)
    for i in range(len(chains)):              # paths: start at a free end
        if i in seen:
            continue
        for e in (0, 1):
            if (i, e) not in link:
                out.append(walk(i, e))
                break
    for i in range(len(chains)):              # what is left are loops
        if i not in seen:
            out.append(walk(i, 0))
    return _drop_stubs(out, co, fork_points)


def resample_exact(topo, ids, closed, ds):
    """Like resample_chain, but every chain vertex is a sample too, and each
    sample knows the edge directions before and after it (exact at vertices)."""
    ids = np.asarray(ids, np.int64)
    Pv = topo.co[ids]
    Pe = np.vstack([Pv, Pv[:1]]) if closed else Pv
    a, b = (ids, np.roll(ids, -1)) if closed else (ids[:-1], ids[1:])
    seg = np.diff(Pe, axis=0)
    sl = np.linalg.norm(seg, axis=1)
    nseg = len(sl)
    cum = np.concatenate([[0.0], np.cumsum(sl)])
    L = float(cum[-1])
    stri, cnt = topo.edge_info(a, b)
    n = max(8 if closed else 2, int(math.ceil(L / ds)))
    s_uni = np.arange(n) * (L / n) if closed else np.linspace(0.0, L, n + 1)
    s_ver = cum[:-1] if closed else cum
    near = np.abs(s_uni[:, None] - s_ver[None, :]).min(1) < 0.3 * (L / n)
    s = np.concatenate([s_uni[~near], s_ver])
    is_v = np.concatenate([np.zeros((~near).sum(), bool), np.ones(len(s_ver), bool)])
    vid = np.concatenate([np.full((~near).sum(), -1), ids[:len(s_ver)]])
    order = np.argsort(s, kind="stable")
    s, is_v, vid = s[order], is_v[order], vid[order]
    i = np.clip(np.searchsorted(cum, s, "right") - 1, 0, nseg - 1)
    f = (s - cum[i]) / np.maximum(sl[i], 1e-30)
    pts = Pe[i] + f[:, None] * seg[i]
    d_out = seg[i] / np.maximum(sl[i], 1e-30)[:, None]
    t_out = stri[i]
    k_in = np.where(is_v, i - 1, i)
    if closed:
        k_in = k_in % nseg
    else:
        k_in = np.clip(k_in, 0, nseg - 1)
    d_in = seg[k_in] / np.maximum(sl[k_in], 1e-30)[:, None]
    t_in = stri[k_in]
    return dict(P=pts, s=s, vid=vid, d_in=d_in, d_out=d_out, t_in=t_in, t_out=t_out,
                bnd=(cnt[i] == 1), ds=L / n, L=L)


def detect_corner_vertices(topo, ids, closed, flip=False):
    """Likely corners of a hem chain (welded vertex ids), judged per vertex
    against its neighbours rather than by one fixed angle:

    * it bends AWAY from the fabric and more than both neighbours - the point
      where two scallops meet (scallop arcs, even low-poly ones, only ever
      bend towards the fabric), even when the angle is small;
    * or it bends towards the fabric very sharply (75+ degrees), or at least
      30 degrees and 2.5x more than the bends around it.
    """
    ids = np.asarray(ids, np.int64)
    n = len(ids)
    if n < 3:
        return []
    P = topo.co[ids]
    idx = np.arange(n)
    if closed:
        prev, nxt = P[(idx - 1) % n], P[(idx + 1) % n]
        a, b = ids, np.roll(ids, -1)
        e_in, e_out = (idx - 1) % n, idx
    else:
        prev, nxt = P[np.maximum(idx - 1, 0)], P[np.minimum(idx + 1, n - 1)]
        a, b = ids[:-1], ids[1:]
        e_in, e_out = np.maximum(idx - 1, 0), np.minimum(idx, n - 2)
    etri, ecnt = topo.edge_info(a, b)
    nv = _normalize(topo.n_o[etri[e_in]] + topo.n_o[etri[e_out]])
    t_in = _normalize(P - prev)
    t_out = _normalize(nxt - P)
    theta = np.degrees(np.arctan2((np.cross(t_in, t_out) * nv).sum(1), (t_in * t_out).sum(1)))

    # fabric side: left of the walking direction if the faces of the border edges are there
    seg = (np.roll(P, -1, 0) - P) if closed else (P[1:] - P[:-1])
    mid = (np.roll(P, -1, 0) + P) / 2.0 if closed else (P[1:] + P[:-1]) / 2.0
    left = np.cross(topo.n_o[etri], seg)
    bnd = ecnt == 1
    side = 1.0
    if bnd.any() and ((topo.centroid[etri[bnd]] - mid[bnd]) * left[bnd]).sum() < 0:
        side = -1.0
    if flip:
        side = -side
    toward = theta * side                  # + bends towards the fabric, - away from it
    away = -toward
    mag = np.abs(theta)

    def nb(arr, k):
        return arr[(idx + k) % n] if closed else arr[np.clip(idx + k, 0, n - 1)]

    med = np.median(np.stack([nb(mag, k) for k in (-3, -2, -1, 1, 2, 3)]), axis=0)
    corner = ((away >= 10.0) & (away >= nb(away, -1)) & (away >= nb(away, 1))) \
        | (toward >= 75.0) | ((toward >= 30.0) & (toward >= 2.5 * med))
    if not closed:
        corner[0] = corner[-1] = False
    return ids[corner].tolist()


def gauss_smooth(P, sigma, closed):
    """Gaussian filter along the sample index (sigma in samples)."""
    N = len(P)
    if sigma < 0.3 or N < 3:
        return P.copy()
    rad = int(math.ceil(3.0 * sigma))
    x = np.arange(-rad, rad + 1)
    k = np.exp(-0.5 * (x / sigma) ** 2)
    k /= k.sum()
    idx = np.arange(-rad, N + rad)
    if closed:
        Pp = P[idx % N]
    else:
        Pp = np.empty((len(idx), 3))
        mid = (idx >= 0) & (idx < N)
        Pp[mid] = P[idx[mid]]
        lo = idx < 0
        Pp[lo] = 2.0 * P[0] - P[np.clip(-idx[lo], 0, N - 1)]
        hi = idx >= N
        Pp[hi] = 2.0 * P[-1] - P[np.clip(2 * (N - 1) - idx[hi], 0, N - 1)]
    out = np.empty_like(P)
    for c in range(3):
        out[:, c] = np.convolve(Pp[:, c], k, mode="valid")
    return out


def tangents(P, closed):
    if closed:
        T = np.roll(P, -1, axis=0) - np.roll(P, 1, axis=0)
    else:
        T = np.empty_like(P)
        T[1:-1] = P[2:] - P[:-2]
        T[0] = P[1] - P[0]
        T[-1] = P[-1] - P[-2]
    return _normalize(T)


class Centerline:
    __slots__ = ("P", "T", "N", "cum", "length", "closed", "ds", "at_border", "corners",
                 "tri")

    def __init__(self, P, T, N, closed, ds, at_border, corner_idx=(), tri=None):
        self.closed = closed
        self.tri = np.zeros(0, np.int64) if tri is None else np.asarray(tri, np.int64)
        self.ds = ds
        self.at_border = at_border
        if closed:
            P = np.vstack([P, P[:1]])
            T = np.vstack([T, T[:1]])
            N = np.vstack([N, N[:1]])
        self.P, self.T, self.N = P, T, N
        seg = np.linalg.norm(np.diff(P, axis=0), axis=1)
        self.cum = np.concatenate([[0.0], np.cumsum(seg)])
        self.length = float(self.cum[-1])
        self.corners = sorted(float(self.cum[i]) for i in corner_idx)

    def sample(self, s):
        L = self.length
        if self.closed:
            sc = np.mod(s, L)
        else:
            sc = np.clip(s, 0.0, L)
        P = np.stack([np.interp(sc, self.cum, self.P[:, c]) for c in range(3)], 1)
        T = _normalize(np.stack([np.interp(sc, self.cum, self.T[:, c]) for c in range(3)], 1))
        N = _normalize(np.stack([np.interp(sc, self.cum, self.N[:, c]) for c in range(3)], 1))
        if not self.closed:
            P = P + T * (s - sc)[:, None]
        return P, T, N


def centerline_spacing(topo, chains, smooth):
    total = sum(float(np.linalg.norm(np.diff(topo.co[ids + ([ids[0]] if c else [])], axis=0),
                                     axis=1).sum()) for ids, c in chains)
    ds = topo.mean_edge / 8.0
    if smooth > 0:
        ds = min(ds, smooth / 4.0)
    return max(ds, total / 40000.0, topo.span * 1e-6)


def build_lines(topo, chains, inset, smooth, flip, ds, corner_ids, corner_inset):
    """The stitch lines: the inset contour (see contour.py), smoothed per
    stretch between corners. Inset 0 follows the hem itself."""
    from . import contour
    window = max(topo.mean_edge, 4.0 * ds)
    out = []
    if abs(inset) < 1e-9:
        for ids, closed in chains:
            R = resample_exact(topo, ids, closed, ds)
            mark = np.array([v in corner_ids for v in R["vid"].tolist()], bool)
            if not closed:
                mark[0] = mark[-1] = False
            out.append(_finish_piece(topo, R["P"], R["t_out"], np.zeros(len(R["P"]), bool),
                                     closed, smooth, R["ds"], 0.0, window, R["P"][mark]))
        return out
    h = max(abs(inset) / 4.0, topo.mean_edge / 48.0, topo.span * 1e-5)
    lines, corners = contour.inset_lines(topo, chains, inset, flip, corner_ids,
                                         max(corner_inset, 0.0), h)
    for P, T, closed in lines:
        Pe = np.vstack([P, P[:1]]) if closed else P
        seg = np.linalg.norm(np.diff(Pe, axis=0), axis=1)
        cum = np.concatenate([[0.0], np.cumsum(seg)])
        L = float(cum[-1])
        # resample evenly per stretch between corner apexes, so each apex is a sample
        knots = sorted(float(cum[i]) for q in corners
                       for i in np.nonzero((P == q).all(axis=1))[0].tolist())
        if closed:
            bounds = (knots + [knots[0] + L]) if knots else [0.0, L]
        else:
            bounds = [0.0] + [k for k in knots if 0.0 < k < L] + [L]
        parts = []
        for a, b in zip(bounds[:-1], bounds[1:]):
            n = max(1, int(math.ceil((b - a) / ds)))
            parts.append(a + np.arange(n) * ((b - a) / n))
        s_ = np.concatenate(parts) if parts else np.zeros(0)
        if not closed:
            s_ = np.append(s_, L)
        elif len(s_) < 8:
            s_ = np.arange(8) * (L / 8)
        s_ = np.mod(s_, L) if closed else s_
        i = np.clip(np.searchsorted(cum, s_, "right") - 1, 0, len(seg) - 1)
        f = (s_ - cum[i]) / np.maximum(seg[i], 1e-30)
        Q = Pe[i] + f[:, None] * (Pe[i + 1] - Pe[i])
        Tq = T[np.minimum(i, len(T) - 1)]
        step = L / max(len(Q) - (0 if closed else 1), 1)
        out.append(_finish_piece(topo, Q, Tq, np.zeros(len(Q), bool), closed, smooth,
                                 step, 0.0, window, corners, tol=1e-6 + step * 1e-3))
    return out


def find_corners(P, closed, ds, window, angle):
    """Indices where the line turns by more than ``angle`` (radians) within
    ``window`` of arc length on each side; one index per corner."""
    N = len(P)
    if angle <= 0 or N < 5:
        return []
    w = max(2, int(round(window / ds)))
    if not closed and N < 2 * w + 1:
        return []
    idx = np.arange(N)

    def turning(k):
        if closed:
            a, b = P[(idx - k) % N], P[(idx + k) % N]
        else:
            a, b = P[np.clip(idx - k, 0, N - 1)], P[np.clip(idx + k, 0, N - 1)]
        return np.arccos(np.clip((_normalize(P - a) * _normalize(b - P)).sum(1), -1.0, 1.0))

    turn = turning(w)
    # A corner turns at one point: over a quarter of the window it still turns
    # most of the way. A steady curve (scallop arc) turns only about a quarter.
    turn_short = turning(max(1, w // 4))
    turn = np.where(turn_short >= 0.6 * turn, turn, 0.0)
    if not closed:
        turn[:w] = 0.0
        turn[-w:] = 0.0
    out = []
    for i in np.argsort(-turn):            # strongest first, then suppress neighbours
        if turn[i] < angle:
            break
        if all(min(abs(i - j), N - abs(i - j)) > w for j in out):
            out.append(int(i))
    return sorted(out)


def _smooth_on_surface(topo, P, tri, border, closed, smooth, ds):
    if smooth <= 0 or len(P) < 3:
        return P, tri, border
    Q = gauss_smooth(P, smooth / ds, closed)
    if not closed:
        Q[0], Q[-1] = P[0], P[-1]          # keep corner / end points in place
    D = Q - P
    n = topo.n[tri]
    D = D - (D * n).sum(1)[:, None] * n
    P2, tri2, b2 = topo.walk(P, tri, D, np.linalg.norm(D, axis=1))
    return P2, tri2, border | b2


def _finish_piece(topo, P, tri, border, closed, smooth, ds, corner_angle=0.0, window=0.0,
                  marked_pos=(), tol=None):
    corners = set(find_corners(P, closed, ds, window, corner_angle))
    for q in marked_pos:                   # marked corners: nearest sample of this piece
        dist = np.linalg.norm(P - q, axis=1)
        i = int(dist.argmin())
        if dist[i] < (tol if tol is not None else 3.0 * ds) and (closed or 0 < i < len(P) - 1):
            corners.add(i)
    corners = sorted(corners)
    if corners and closed:
        # start the loop at a corner so every stretch is an open run between corners
        r = corners[0]
        P, tri, border = np.roll(P, -r, 0), np.roll(tri, -r), np.roll(border, -r)
        corners = [(c - r) % len(P) for c in corners]
    N = len(P)

    if corners:
        # Smooth and take tangents per stretch, so corners stay sharp.
        if closed:
            cuts = list(corners) + [N]        # wrap back to the first corner
        else:
            cuts = [0] + [c for c in corners if 0 < c < N - 1] + [N - 1]
        Pn, Tn, Bn = P.copy(), tri.copy(), border.copy()
        T = np.zeros_like(P)
        for a, b in zip(cuts[:-1], cuts[1:]):
            sel = np.arange(a, b + 1) % N
            ps, ts, bs = _smooth_on_surface(topo, P[sel], tri[sel], border[sel], False,
                                            smooth, ds)
            Pn[sel], Tn[sel], Bn[sel] = ps, ts, bs
            if len(sel) > 2:
                T[sel[1:-1]] = tangents(gauss_smooth(ps, 1.0, False), False)[1:-1]
        P, tri, border = Pn, Tn, Bn
        # stretch ends: average of the one-sided directions (the corner itself)
        for i in np.nonzero(~T.any(axis=1))[0].tolist():
            if closed or 0 < i < N - 1:
                d = _normalize(P[i] - P[(i - 1) % N]) + _normalize(P[(i + 1) % N] - P[i])
            elif i == 0:
                d = P[1] - P[0]
            else:
                d = P[-1] - P[-2]
            T[i] = d
        T = _normalize(T)
    else:
        P, tri, border = _smooth_on_surface(topo, P, tri, border, closed, smooth, ds)
        T = tangents(gauss_smooth(P, 1.0, closed), closed)

    # Face normals with the winding made consistent across connected faces.
    # (Aligning them along the line instead flips whole stretches after a fold,
    # where the two walls really face opposite ways.)
    Nrm = topo.n_o[tri]
    Nrm = _normalize(gauss_smooth(Nrm, 1.0, closed))
    return Centerline(P, T, Nrm, closed, ds, border, corners, tri)


# -- dashes -----------------------------------------------------------------

def dash_starts(Lt, closed, Ls, G, offset, even):
    pitch = Ls + G
    if pitch <= 0 or Ls <= 0 or Lt <= 0:
        return np.zeros(0), Ls
    if closed:
        if even:
            n = max(1, int(round(Lt / pitch)))
            k = Lt / (n * pitch)
            Ls *= k
            pitch *= k
        else:
            n = int(math.floor(Lt / pitch + 1e-9))
        return (offset + np.arange(n) * pitch) % Lt, Ls
    n = int(math.floor((Lt + G) / pitch + 1e-9))
    base = offset
    if even and n > 0:
        base += (Lt - (n * Ls + (n - 1) * G)) / 2.0
    tol = Lt * 1e-9
    kmin = int(math.ceil((-base - tol) / pitch))
    kmax = int(math.floor((Lt - Ls - base + tol) / pitch))
    return base + np.arange(kmin, kmax + 1) * pitch, Ls


def dash_groups(cl, Ls, G, offset, even):
    """[(starts, length)] per run. Lines with corners are fitted per stretch
    between corners, with half a gap on each side of every corner, so two
    stitches point into the corner instead of one bending around it."""
    if not cl.corners:
        return [dash_starts(cl.length, cl.closed, Ls, G, offset, even)]
    L = cl.length
    marks = cl.corners
    if cl.closed:
        runs = [(a, b if b > a else b + L) for a, b in zip(marks, marks[1:] + marks[:1])]
    else:
        edges = [0.0] + [c for c in marks if 0.0 < c < L] + [L]
        runs = list(zip(edges[:-1], edges[1:]))
    pitch = Ls + G
    out = []
    for a, b in runs:
        S = b - a
        if S < 0.5 * Ls:
            continue
        n = max(1, int(round(S / pitch)))
        k = S / (n * pitch)
        ls, g = Ls * k, G * k
        starts = a + g / 2.0 + np.arange(n) * (ls + g)
        if cl.closed:
            starts = starts % L
        out.append((starts, ls))
    return out


def _append_dashes(cl, starts, ls, W, r, pad, verts, uvs, dims, quads, base):
    u, hw = dash_profile(ls, W, min(r, ls / 2.0), pad, cl.ds)
    M = len(u)
    D = len(starts)
    s = (starts[:, None] + ls / 2.0 + u[None, :]).reshape(-1)
    P, T, N = cl.sample(s)
    # Direction from the stitch's own points: a stitch never crosses a corner,
    # while the line's tangent is averaged at corners and turns sideways at a
    # very sharp one (a twisted, flat stitch there would not bake).
    if M >= 2:
        own = np.gradient(P.reshape(D, M, 3), axis=1).reshape(-1, 3)
        ok = np.linalg.norm(own, axis=1) > 1e-12
        T = np.where(ok[:, None], _normalize(own), T)
    B = _normalize(np.cross(N, T))
    w = np.repeat(hw[None, :], D, 0).reshape(-1)
    cols = np.array([-1.0, 0.0, 1.0])
    co = P[:, None, :] + B[:, None, :] * (w[:, None] * cols[None, :])[..., None]
    verts.append((co.reshape(-1, 3), np.repeat(N, 3, axis=0), np.repeat(B, 3, axis=0)))
    uv = np.stack([np.repeat(np.tile(u, D), 3), (w[:, None] * cols[None, :]).reshape(-1)], 1)
    uvs.append(uv)
    rr = min(r, ls / 2.0, W / 2.0)
    dims.append(np.tile([ls / 2.0, W / 2.0, rr], (D * M * 3, 1)))
    j = np.arange(M - 1)
    c = np.arange(2)
    dd = np.arange(D)
    v00 = (dd[:, None, None] * M + j[None, :, None]) * 3 + c[None, None, :]
    q = np.stack([v00, v00 + 1, v00 + 4, v00 + 3], -1).reshape(-1, 4)
    quads.append(q + base)
    return base + D * M * 3


def zigzag_runs(cl, step):
    """Peaks of a zigzag along the line: [(s, side)] per run, side +1 / -1 at
    the peaks and 0 where a run starts or ends on the line (open ends and
    marked corners). Every run is fitted with a whole number of legs."""
    L = cl.length
    if not cl.corners and cl.closed:
        n = max(2, 2 * int(round(L / (2.0 * step))))
        sv = np.arange(n + 1) * (L / n)
        side = np.where(np.arange(n + 1) % 2 == 0, 1.0, -1.0)
        return [(sv, side)]
    marks = cl.corners
    if cl.closed:
        runs = [(a, b if b > a else b + L) for a, b in zip(marks, marks[1:] + marks[:1])]
    else:
        edges = [0.0] + [c for c in marks if 0.0 < c < L] + [L]
        runs = list(zip(edges[:-1], edges[1:]))
    out = []
    for a, b in runs:
        S = b - a
        if S <= 1e-12:
            continue
        n = max(1, int(round(S / step)))
        h = S / n
        peaks = a + h / 2.0 + np.arange(n) * h
        sv = np.concatenate([[a], peaks, [b]])
        side = np.concatenate([[0.0], np.where(np.arange(n) % 2 == 0, 1.0, -1.0), [0.0]])
        out.append((sv, side))
    return out


class _RunFrame:
    """Along-the-line / across-the-line coordinates (u, w) of one run of the
    zigzag, mapped onto the surface like the dashes: P(u) + B(u) * w. Past the
    ends of a run (a marked corner or an open end) it goes on straight along
    the run's own direction, not around the corner."""

    def __init__(self, cl, a, b, cyclic, ext):
        L = cl.length
        ds = max(cl.ds, 1e-9)
        self.period = L if cyclic else None
        if cyclic:
            uu = np.linspace(0.0, L, max(8, int(math.ceil(L / ds)) + 1))[:-1]
            P, _, N = cl.sample(uu)
            T = np.roll(P, -1, 0) - np.roll(P, 1, 0)
        else:
            n = max(2, int(math.ceil((b - a) / ds)) + 1)
            uu = np.linspace(a, b, n)
            P, _, N = cl.sample(np.mod(uu, L) if cl.closed else uu)
            T = np.gradient(P, axis=0)
        T = _normalize(T)
        if not cyclic:
            k = max(1, int(math.ceil(ext / ds)))
            d = np.arange(1, k + 1) * (ext / k)
            ub, ua = a - d[::-1], b + d
            P = np.vstack([P[0] + T[0] * (ub - a)[:, None], P, P[-1] + T[-1] * (ua - b)[:, None]])
            N = np.vstack([np.repeat(N[:1], k, 0), N, np.repeat(N[-1:], k, 0)])
            T = np.vstack([np.repeat(T[:1], k, 0), T, np.repeat(T[-1:], k, 0)])
            uu = np.concatenate([ub, uu, ua])
        self.uu, self.P, self.N, self.T = uu, P, N, T
        self.B = _normalize(np.cross(N, T))

    def _at(self, arr, u):
        return np.stack([np.interp(u, self.uu, arr[:, c], period=self.period)
                         for c in range(3)], -1)

    def point(self, u, w):
        u, w = np.asarray(u, float), np.asarray(w, float)
        return self._at(self.P, u) + _normalize(self._at(self.B, u)) * w[..., None]

    def frame(self, u):
        """(P, T, B, N) at u."""
        return (self._at(self.P, u), _normalize(self._at(self.T, u)),
                _normalize(self._at(self.B, u)), _normalize(self._at(self.N, u)))


def _perp(d):
    return np.array([-d[1], d[0]])


def _fold_free(uv, q):
    """Quads of q that are not folded over in the (x, y) coordinates uv."""
    q0, q1, q2, q3 = (uv[q[:, k]] for k in range(4))

    def area(a_, b_, c_):
        return ((b_[:, 0] - a_[:, 0]) * (c_[:, 1] - a_[:, 1])
                - (b_[:, 1] - a_[:, 1]) * (c_[:, 0] - a_[:, 0]))
    a1, a2 = area(q0, q1, q2), area(q0, q2, q3)
    ref = np.sign(np.median(np.concatenate([a1, a2])))
    return q[(a1 * ref > 0) & (a2 * ref > 0)]


def _append_zigzag(cl, step, W, A, pad, verts, uvs, dims, quads, base):
    """The zigzag, one strip per leg, each drawn as a capsule by the same
    rounded-rectangle shader as the dashes. The legs are laid out flat in the
    line's own (along, across) coordinates and mapped onto the surface like the
    dashes, so every strip follows the fabric. Two legs meeting at a point are
    cut along the line halving the angle between them: the strips fit together
    without overlapping (the bake sees only the top surface) and the round
    joint is whole. At a marked corner the cut is found on the surface, from
    both runs' own directions; open ends get a full round cap."""
    runs = zigzag_runs(cl, step)
    if not runs:
        return base, 0
    H = W / 2.0 + pad
    cap = W / 2.0 + pad
    LIM = 0.25                                   # mitre limit (cos of half the turn)
    cyclic = cl.closed and not cl.corners
    frames = [_RunFrame(cl, float(sv[0]), float(sv[-1]), cyclic, A + 4.0 * H + cap)
              for sv, _ in runs]
    pts = [np.stack([sv, side * (A / 2.0)], 1) for sv, side in runs]
    nruns = len(runs)

    def corner_cut(ka, kb):
        """Cut between the last leg of run ka and the first leg of run kb, in
        each run's own coordinates: ((left, right) for ka, (left, right) for kb)."""
        fa, fb = frames[ka], frames[kb]
        va, vb = pts[ka], pts[kb]
        sa, sb = va[-1, 0], vb[0, 0]
        J = fa.point(sa, 0.0)
        Na = fa.frame(sa)[3]
        Da = _normalize(fa.point(*va[-1]) - fa.point(*va[-2]))
        Db = _normalize(fb.point(*vb[1]) - fb.point(*vb[0]))
        qa, qb = _normalize(np.cross(Na, Da)), _normalize(np.cross(Na, Db))
        m = qa + qb
        m = _normalize(m) if np.linalg.norm(m) > 1e-6 else qa
        t = H / max(float(m @ qa), LIM)
        ends3 = (J - m * t, J + m * t)
        out = []
        for f, s0 in ((fa, sa), (fb, sb)):
            _, T0, B0, _ = f.frame(s0)
            J0 = f.point(s0, 0.0)
            out.append(tuple(np.array([s0 + (X - J0) @ T0, (X - J0) @ B0]) for X in ends3))
        out.append(ends3)              # both strips take these exact points
        return out

    corner_cuts = {}                             # run k -> cut after it
    if not cyclic:
        for k in range(nruns):
            if k + 1 < nruns:
                corner_cuts[k] = corner_cut(k, k + 1)
            elif cl.closed:
                corner_cuts[k] = corner_cut(k, 0)

    cols = np.array([0.0, 0.5, 1.0])
    count = 0
    for k, (V, f) in enumerate(zip(pts, frames)):
        n = len(V)
        legs = n - 1                             # a cyclic run repeats its first point
        D = np.diff(V, axis=0)
        Ls = np.linalg.norm(D, axis=1)
        dirs = D / np.maximum(Ls, 1e-30)[:, None]

        def cut3(j):
            """The 3D ends of a corner cut at point j, or None."""
            if cyclic or 0 < j < n - 1:
                return None
            if j == 0:
                prev = (k - 1) % nruns
                return corner_cuts[prev][2] if (k > 0 or cl.closed) and prev in corner_cuts else None
            return corner_cuts[k][2] if k in corner_cuts else None

        def cut(j):
            """(left, right) ends of the cut at point j of this run."""
            if 0 < j < n - 1 or cyclic:
                i0, i1 = (j - 1) % legs, j % legs
                p0, p1 = _perp(dirs[i0]), _perp(dirs[i1])
                m = p0 + p1
                m = m / np.linalg.norm(m) if np.linalg.norm(m) > 1e-9 else p0
                t = H / max(float(m @ p0), LIM)
                return V[j] - m * t, V[j] + m * t
            if j == 0:
                prev = (k - 1) % nruns
                if (k > 0 or cl.closed) and prev in corner_cuts:
                    return corner_cuts[prev][1]
                d = dirs[0]
                c = V[0] - d * cap
                return c - _perp(d) * H, c + _perp(d) * H
            if k in corner_cuts:
                return corner_cuts[k][0]
            d = dirs[-1]
            c = V[-1] + d * cap
            return c - _perp(d) * H, c + _perp(d) * H

        cuts = [cut(j) for j in range(n)]
        for i in range(legs):
            if Ls[i] <= 1e-12:
                continue
            (s_l, s_r), (e_l, e_r) = cuts[i], cuts[i + 1]
            M = max(2, int(math.ceil(Ls[i] / max(cl.ds, 1e-12))) + 1)
            fr = np.linspace(0.0, 1.0, M)[:, None]
            left = s_l + (e_l - s_l) * fr
            right = s_r + (e_r - s_r) * fr
            uvb = (left[:, None, :] + (right - left)[:, None, :] * cols[None, :, None]).reshape(-1, 2)
            C = (V[i] + V[i + 1]) / 2.0
            d, p = dirs[i], _perp(dirs[i])
            rel = uvb - C
            uv = np.stack([rel @ d, rel @ p], 1)
            co = f.point(uvb[:, 0], uvb[:, 1])
            for row, jj in ((0, i), (M - 1, i + 1)):
                e3 = cut3(jj)
                if e3 is not None:          # a corner: the same points for both runs
                    co[row * 3:row * 3 + 3] = [e3[0], (e3[0] + e3[1]) / 2.0, e3[1]]
            _, T_, B_, N_ = f.frame(uvb[:, 0])
            across = _normalize(B_ * d[0] - T_ * d[1])          # the leg's own side
            j = np.arange(M - 1)
            c = np.arange(2)
            v00 = (j[:, None] * 3 + c[None, :])
            q = np.stack([v00, v00 + 1, v00 + 4, v00 + 3], -1).reshape(-1, 4)
            # a leg on the inside of a curve tighter than half the height can
            # fold over: skip folded quads (the neighbouring leg covers them)
            q = _fold_free(uv, q)
            uvs.append(uv)
            verts.append((co, N_, across))
            dims.append(np.tile([Ls[i] / 2.0 + W / 2.0, W / 2.0, W / 2.0], (len(co), 1)))
            quads.append(q + base)
            base += len(co)
            count += 1
    return base, count


def dash_profile(Ls, W, r, pad, du):
    """Centered outline samples (u, half width) of the padded rounded rectangle."""
    hl = Ls / 2.0 + pad
    hw = W / 2.0 + pad
    rr = min(r + pad, hl, hw)
    phi = np.linspace(0.0, math.pi / 2.0, CORNER_STEPS + 1)
    ul = -hl + rr * (1.0 - np.cos(phi))
    wl = hw - rr + rr * np.sin(phi)
    inner = 2.0 * (hl - rr)
    n_in = max(0, int(math.ceil(inner / max(du, 1e-12))) - 1)
    ui = np.linspace(-hl + rr, hl - rr, n_in + 2)[1:-1]
    u = np.concatenate([ul, ui, -ul[::-1]])
    w = np.concatenate([wl, np.full(n_in, hw), wl[::-1]])
    keep = np.concatenate([[True], np.diff(u) > hl * 1e-6])
    return u[keep], w[keep]


class RibbonData:
    def __init__(self):
        self.co = np.zeros((0, 3))
        self.quads = np.zeros((0, 4), np.int64)
        self.uv = np.zeros((0, 2))
        self.dims = np.zeros((0, 3))
        self.dash_count = 0
        self.band_polys = np.zeros(0, np.int64)
        self.width_px = 0.0
        self.gap_px = 0.0
        self.texel = 0.0
        self.aa = np.zeros(0)
        self.lift = 0.0
        self.border_hits = 0
        self.line_co = np.zeros((0, 3))     # line art preview strips
        self.line_quads = np.zeros((0, 4), np.int64)
        self.line_layer = np.zeros(0, np.int64)   # index into p["lines"] of each quad
        self.line_uv = np.zeros((0, 2))     # the stitch line in UV, on its own faces
        self.line_r_uv = np.zeros(0)        # half the stitch width there, in UV units


def band_triangles(topo, centerlines, reach):
    kd = topo.centroid_kd()
    if not len(topo.radius):
        return np.zeros(0, np.int64)
    # Search radius from typical triangles; the few very large ones are checked directly.
    r_typ = float(np.percentile(topo.radius, 99))
    rmax = r_typ + reach
    found = set(np.nonzero(topo.radius > r_typ)[0].tolist())
    for cl in centerlines:
        step = max(1, int(cl.ds and (reach / cl.ds) // 2))
        for p in cl.P[::step].tolist():
            for _, i, _ in kd.find_range(p, rmax):
                found.add(i)
    if not found:
        return np.zeros(0, np.int64)
    idx = np.fromiter(found, np.int64)
    # keep triangles whose own extent can reach a centerline sample
    allP = np.vstack([cl.P for cl in centerlines])
    ckd = kdtree.KDTree(len(allP))
    for i, p in enumerate(allP.tolist()):
        ckd.insert(p, i)
    ckd.balance()
    keep = []
    for i, c in zip(idx.tolist(), topo.centroid[idx].tolist()):
        _, _, dist = ckd.find(c)
        if dist <= topo.radius[i] + reach:
            keep.append(i)
    keep = np.array(keep, np.int64)
    # Only the layer of fabric the line lies on: spread from the line's own
    # faces through faces near it. A second layer close by in 3D (lace folded
    # over itself) is not connected that way, so the bake does not print the
    # stitches onto it as well.
    seeds = np.unique(np.concatenate([cl.tri for cl in centerlines]))
    seeds = seeds[seeds >= 0]
    if not len(seeds):
        return keep
    allowed = np.zeros(len(topo.tri), bool)
    allowed[keep] = True
    allowed[seeds] = True
    reached = np.zeros(len(topo.tri), bool)
    reached[seeds] = True
    front = seeds
    while len(front):
        u = topo.nbr[front].reshape(-1)
        u = np.unique(u[u >= 0])
        u = u[allowed[u] & ~reached[u]]
        reached[u] = True
        front = u
    return np.nonzero(reached)[0]


def _across_texel(topo, tri, dirs, resolution, fallback):
    """Texel size (scene units) along ``dirs`` on triangles ``tri`` via the UV Jacobian."""
    out = np.full(len(tri), fallback)
    ok = tri >= 0
    if topo.uv is None or not ok.any():
        return out
    t = tri[ok]
    V = topo.V[t]
    UV = topo.uv[t]
    e1, e2 = V[:, 1] - V[:, 0], V[:, 2] - V[:, 0]
    d1, d2 = UV[:, 1] - UV[:, 0], UV[:, 2] - UV[:, 0]
    g11, g12, g22 = (e1 * e1).sum(1), (e1 * e2).sum(1), (e2 * e2).sum(1)
    b = dirs[ok]
    r1, r2 = (b * e1).sum(1), (b * e2).sum(1)
    det = g11 * g22 - g12 * g12
    with np.errstate(divide="ignore", invalid="ignore"):
        a1 = (g22 * r1 - g12 * r2) / det
        a2 = (g11 * r2 - g12 * r1) / det
        duv = np.linalg.norm(a1[:, None] * d1 + a2[:, None] * d2, axis=1)
        tex = 1.0 / (resolution * duv)
    good = np.isfinite(tex) & (tex > 0)
    vals = np.where(good, tex, fallback)
    out[ok] = vals
    return out


def _band(topo, centerlines, W, ds, cache):
    """Triangles near the path and a BVH over them; cached per width."""
    if cache is not None and cache.get("W") == W:
        return cache["band"], cache["bvh"]
    band = band_triangles(topo, centerlines, W + 2.0 * ds)
    bvh = None
    if band.size:
        used = np.unique(topo.tri[band])
        remap = np.full(len(topo.co), -1, np.int64)
        remap[used] = np.arange(len(used))
        bvh = BVHTree.FromPolygons(topo.co[used].tolist(), remap[topo.tri[band]].tolist(),
                                   all_triangles=True)
    if cache is not None:
        cache.update(W=W, band=band, bvh=bvh)
    return band, bvh


def build_ribbons(topo, centerlines, Ls, G, W, roundness, offset, even, resolution, cache=None,
                  zigzag=0.0):
    """Dashes, or with ``zigzag`` > 0 a zigzag of that height (peak to peak)
    whose legs span Ls along the line."""
    out = RibbonData()
    if not centerlines or W <= 0 or Ls <= 0:
        return out
    total = sum(cl.length for cl in centerlines)
    estimate = total / (Ls if zigzag > 0 else Ls + G)
    if estimate > MAX_STITCHES:
        raise StitchLimitError(
            "{count} stitches: Length + Gap too small for this path (limit {limit})",
            count=f"{int(estimate):,}", limit=f"{MAX_STITCHES:,}")
    ds = min(cl.ds for cl in centerlines)
    We = W + zigzag                          # how far the stitch reaches across
    # The fabric the strips are dropped onto must reach past every strip point,
    # or points beyond it land on its border and the strip stands up (a stray
    # line in the bake). A zigzag's joints reach well past its peaks.
    reach = 2.0 * We if zigzag > 0 else W
    band, bvh = _band(topo, centerlines, reach, ds, cache)
    if band.size == 0:
        return out
    out.band_polys = np.unique(topo.tri_poly[band])

    # Local texel size of the bake target (UV density varies over a mesh).
    tri_texel = np.full(len(topo.area), W / 16.0)
    if topo.uv is not None:
        with np.errstate(divide="ignore", invalid="ignore"):
            dens = resolution * np.sqrt(topo.uv_area[band] / topo.area[band])
        ok = np.isfinite(dens) & (dens > 0)
        if ok.any():
            tri_texel[band[ok]] = 1.0 / dens[ok]
            tri_texel[band[~ok]] = np.median(1.0 / dens[ok])
    bt = tri_texel[band]
    texel = float(np.median(bt))
    coarse = float(np.percentile(bt, 90))      # thinnest-looking spots
    out.texel = texel
    out.width_px = W / coarse
    out.gap_px = G / coarse
    pad = min(coarse, max(W, 2.0 * texel))
    lift = max(0.2 * W, 0.5 * texel)
    out.lift = lift
    r = max(0.0, min(1.0, roundness)) * W / 2.0

    verts, quads, uvs, dims = [], [], [], []
    base = 0
    for cl in centerlines:
        out.border_hits += int(cl.at_border.sum())
        if zigzag > 0:
            base, n = _append_zigzag(cl, Ls, W, zigzag, pad, verts, uvs, dims, quads, base)
            out.dash_count += n
            continue
        for starts, ls in dash_groups(cl, Ls, G, offset, even):
            if starts.size == 0:
                continue
            base = _append_dashes(cl, starts, ls, W, r, pad, verts, uvs, dims, quads, base)
            out.dash_count += len(starts)

    if not verts:
        return out
    co = np.vstack([v[0] for v in verts])
    Ncl = np.vstack([v[1] for v in verts])
    Bv = np.vstack([v[2] for v in verts])

    # Snap onto the surface near the path, then lift along the face normal.
    maxd = We * 2.0 + pad * 4.0 + ds
    snapped = co.copy()
    nrm = Ncl.copy()
    hit_tri = np.full(len(co), -1, np.int64)
    find = bvh.find_nearest
    for i, v in enumerate(co.tolist()):
        loc, n, fi, _ = find(v, maxd)
        if loc is not None:
            snapped[i] = loc
            nrm[i] = topo.n_o[band[fi]]
            hit_tri[i] = band[fi]
    across = _across_texel(topo, hit_tri, Bv, resolution, texel)
    out.width_px = W / float(np.percentile(across, 90))
    out.aa = np.minimum(across, 2.0 * pad)
    flip = (nrm * Ncl).sum(1) < 0
    nrm[flip] *= -1.0
    out.co = snapped + nrm * lift
    out.quads = np.vstack(quads)
    out.uv = np.vstack(uvs)
    out.dims = np.vstack(dims)
    out.line_uv, out.line_r_uv = _line_uv(topo, centerlines, 0.5 * We)
    return out


def _line_uv(topo, centerlines, half):
    """The stitch line in UV, each sample on the face it was built on, with
    ``half`` (a length on the surface) converted to UV units there."""
    if topo.uv is None:
        return np.zeros((0, 2)), np.zeros(0)
    P = np.vstack([cl.P[:len(cl.tri)] for cl in centerlines if len(cl.tri)] or [np.zeros((0, 3))])
    T = np.concatenate([cl.tri for cl in centerlines if len(cl.tri)] or [np.zeros(0, np.int64)])
    ok = T >= 0
    P, T = P[ok], T[ok]
    if not len(T):
        return np.zeros((0, 2)), np.zeros(0)
    V = topo.V[T]
    e1, e2 = V[:, 1] - V[:, 0], V[:, 2] - V[:, 0]
    d = P - V[:, 0]
    g11, g12, g22 = (e1 * e1).sum(1), (e1 * e2).sum(1), (e2 * e2).sum(1)
    p, q = (d * e1).sum(1), (d * e2).sum(1)
    det = np.maximum(g11 * g22 - g12 * g12, 1e-40)
    b1 = (g22 * p - g12 * q) / det
    b2 = (g11 * q - g12 * p) / det
    U = topo.uv[T]
    uv = U[:, 0] + b1[:, None] * (U[:, 1] - U[:, 0]) + b2[:, None] * (U[:, 2] - U[:, 0])
    with np.errstate(divide="ignore", invalid="ignore"):
        k = np.sqrt(topo.uv_area[T] / topo.area[T])
    k = np.where(np.isfinite(k), k, 0.0)
    return uv, half * k


# -- top level with caching ---------------------------------------------------

_cache = {}


def generate(key_obj, me, mw, p):
    """key_obj: cache key. me: mesh (object mode data). mw: world matrix.
    p: dict with inset, smooth, flip, length, gap, width, round, offset, even,
    resolution, uv_name. Returns (RibbonData, Topology)."""
    sig, line_sig = mesh_signature(me, mw, p["uv_name"])
    entry = _cache.get(key_obj)
    if entry is not None and entry["sig"] == sig and entry.get("line_sig") != line_sig:
        # only the line art edges changed: keep the mesh data and the stitches
        entry["line_pairs"] = {n: entry["topo"].path_pairs(me, (n,)) for n in line_attr_names(me)}
        entry["excl"] = {n: v for n, v in entry["excl"].items() if n == PATH_ATTR}
        entry["excl"].update({n: entry["topo"].path_pairs(me, (n,), -1)
                              for n in line_attr_names(me)})
        entry["line_chains"] = {}
        entry["grid_coords"] = {}
        if any(a != PATH_ATTR for a in spec_attrs(entry.get("stitch_attrs"))):
            entry["cl_key"] = None          # the stitches follow line art edges too
        entry["line_key"] = None
        entry["line_sig"] = line_sig
    if entry is None or entry["sig"] != sig:
        topo = Topology(me, mw, p["uv_name"])
        pairs = topo.path_pairs(me)
        line_pairs = {n: topo.path_pairs(me, (n,)) for n in line_attr_names(me)}
        excl = {n: topo.path_pairs(me, (n,), -1) for n in [PATH_ATTR] + line_attr_names(me)}
        entry = {"sig": sig, "topo": topo, "cl_key": None, "cls": None, "excl": excl,
                 "corners": topo.corner_ids(me), "pairs": pairs, "line_pairs": line_pairs,
                 "line_chains": {}, "grid_coords": {}, "line_sig": line_sig}
        _cache[key_obj] = entry
    topo = entry["topo"]
    entry["stitch_attrs"] = stitch_attrs = p.get("stitch_attrs") or (PATH_ATTR, None)
    chains = edge_chains(entry, stitch_attrs)
    rib = RibbonData()
    if chains and p.get("stitches", True):
        rib = _stitch_ribbons(entry, topo, chains, p)
    # line art preview strips, cached per layer settings
    layers = tuple(p.get("lines", ()))
    line_key = (layers, p["flip"])
    if entry.get("line_key") != line_key:
        from . import lineart
        cos, quads, owner, base = [], [], [], 0
        for li, l in enumerate(layers):
            ch = line_chains(entry, l[3])
            if not ch:
                continue
            co, q = lineart.strips(topo, ch, entry["corners"], p["flip"],
                                   [(l[0], l[1], l[2], l[4])])
            if not len(q):
                continue
            cos.append(co)
            quads.append(q + base)
            owner.append(np.full(len(q), li, np.int64))
            base += len(co)
        geo = ((np.vstack(cos), np.vstack(quads), np.concatenate(owner)) if quads else
               (np.zeros((0, 3)), np.zeros((0, 4), np.int64), np.zeros(0, np.int64)))
        entry["line_key"] = line_key
        entry["line_geo"] = geo
    rib.line_co, rib.line_quads, rib.line_layer = entry["line_geo"]
    return rib, topo


_NO_PAIRS = np.zeros((0, 2), np.int64)


def spec_attrs(spec):
    """Edge attributes in an edge spec (attr, spec of the layer it refers to
    or None), in order."""
    out = []
    while spec is not None:
        out.append(spec[0])
        spec = spec[1]
    return out


def _rows_in(a, b):
    """Rows of the pair array a that occur in b (both sorted per row)."""
    n = int(max(a.max(), b.max())) + 1
    return np.isin(a[:, 0] * n + a[:, 1], b[:, 0] * n + b[:, 1])


def spec_pairs(entry, spec):
    """Edges of an edge spec (attr, child): the layer's own edges, plus the
    edges of the layer it refers to (worked out the same way), minus the
    edges it takes out."""
    attr, child = spec
    own = entry["pairs"] if attr == PATH_ATTR else entry["line_pairs"].get(attr, _NO_PAIRS)
    parts = [own] + ([spec_pairs(entry, child)] if child is not None else [])
    pairs = np.vstack(parts)
    if not len(pairs):
        return _NO_PAIRS
    pairs = np.unique(np.sort(pairs, axis=1), axis=0)
    out = entry.get("excl", {}).get(attr, _NO_PAIRS)
    if len(out):
        pairs = pairs[~_rows_in(pairs, np.sort(out, axis=1))]
    return pairs


def _as_spec(spec):
    return (spec, None) if isinstance(spec, str) else spec


def edge_chains(entry, spec):
    """Chains along a layer's edges, given as an edge spec (see spec_pairs)."""
    spec = _as_spec(spec)
    cache = entry["line_chains"]
    hit = cache.get(spec)
    if hit is None:
        pairs = spec_pairs(entry, spec)
        topo = entry["topo"]
        hit = [c for c in build_chains(pairs, topo.co) if len(c[0]) >= 2] if len(pairs) else []
        cache[spec] = hit
    return hit


line_chains = edge_chains            # a line art layer's chains


def grid_coords(entry, spec):
    """Fabric coordinates for a grid layer following the edges of ``spec``."""
    key = _as_spec(spec)
    cache = entry.setdefault("grid_coords", {})
    hit = cache.get(key)
    if hit is None:
        from . import grid
        hit = cache[key] = grid.fabric_coords(entry["topo"], edge_chains(entry, key))
    return hit


def _stitch_ribbons(entry, topo, chains, p):
    cl_key = (p["inset"], p["smooth"], p["flip"], p.get("corner", 0.0),
              p.get("corner_inset", 0.0), entry.get("stitch_attrs"))
    if entry["cl_key"] != cl_key:
        ds = centerline_spacing(topo, chains, p["smooth"])
        cls = build_lines(topo, [c for c in chains if len(c[0]) >= 2], p["inset"], p["smooth"],
                          p["flip"], ds, entry["corners"], p.get("corner_inset", 0.0))
        entry["cls"] = cls
        entry["cl_key"] = cl_key
        entry["band"] = {}
    return build_ribbons(topo, entry["cls"], p["length"], p["gap"], p["width"], p["round"],
                         p["offset"], p["even"], p["resolution"], entry["band"],
                         zigzag=p.get("zigzag", 0.0))


def drop_cache(obj=None):
    if obj is None:
        _cache.clear()
    else:
        _cache.pop(obj.name_full, None)
