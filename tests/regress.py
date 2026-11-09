"""Regression suite for the stitch line. Prints one JSON line of metrics.

blender -b --factory-startup <file.blend> -P regress.py -- <object> <out_dir> [<pkg_dir>]

Metrics:
  lines          number of separate stitch lines (pieces)
  length_mm      total line length
  stitches       number of stitches
  gaps_mm        stitch-free stretches > 1.5 mm along the line in the baked mask
  double_pts     samples where the line folds back onto itself (spikes / double lines)
  air_quads      stitch quads with an edge > 4 mm (stitches across the air)
  corners        marked corners that landed on the line
  corner_turn    median turn (deg) of the line within 2 mm at those corners
  t_first/t_dash/t_inset  build times in ms
"""
import json
import os
import sys
import time

import bpy
import bmesh
import numpy as np
from mathutils import Vector, geometry
from mathutils.bvhtree import BVHTree

args = sys.argv[sys.argv.index("--") + 1:]
obj_name, out_dir = args[0], args[1]
pkg_dir = args[2] if len(args) > 2 else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, pkg_dir)
import rizum_pattern_masks as sg  # noqa: E402
from rizum_pattern_masks import core, bake  # noqa: E402

os.makedirs(out_dir, exist_ok=True)
sg.register()
sg._on_load(None)
ob = bpy.data.objects[obj_name]
bpy.context.view_layer.objects.active = ob
ob.select_set(True)
if ob.mode != 'OBJECT':
    bpy.ops.object.mode_set(mode='OBJECT')
s = ob.stitch_gen
s.live = False

if core.PATH_ATTR not in ob.data.attributes:          # test skirt: mark the hem
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(ob.data)
    for e in bm.edges:
        e.select_set(e.is_boundary and all((ob.matrix_world @ v.co).z < -0.265 for v in e.verts))
    bm.select_flush_mode()
    bmesh.update_edit_mesh(ob.data)
    bpy.ops.stitch_gen.path_add()
    bpy.ops.object.mode_set(mode='OBJECT')
    s.inset, s.smooth, s.length, s.gap, s.width, s.corner_inset = 4.0, 2.0, 4.0, 2.5, 1.2, 1.0

core.drop_cache()
t0 = time.perf_counter()
d = sg.regenerate(ob)
t1 = time.perf_counter()
s.length = s.length * 1.05
d = sg.regenerate(ob)
t2 = time.perf_counter()
s.inset = s.inset * 1.02
d = sg.regenerate(ob)
t3 = time.perf_counter()
s.inset = s.inset / 1.02
s.length = s.length / 1.05
d = sg.regenerate(ob)

entry = core._cache[ob.name_full]
cls = entry["cls"]
topo = entry["topo"]
W = s.width * 0.001
Ls = s.length * 0.001

# double lines: a sample with another sample far along the line but close in space
double = 0
for cl in cls:
    ss = np.arange(0, cl.length, 0.0003)
    P, _, _ = cl.sample(ss)
    from mathutils import kdtree
    kd = kdtree.KDTree(len(P))
    for i, p in enumerate(P.tolist()):
        kd.insert(p, i)
    kd.balance()
    for i, p in enumerate(P.tolist()):
        for _, j, _ in kd.find_range(p, 1.5 * W):
            sep = abs(ss[i] - ss[j])
            if cl.closed:
                sep = min(sep, cl.length - sep)
            if sep > 0.006:
                double += 1
                break

# hairpins: the line comes back close to itself after a short detour
# (shortcut < 35% of the detour, detour 3-15 mm) - a spike into a narrow slit
hairpins = []
for cl in cls:
    ss = np.arange(0, cl.length, 0.0005)
    P, _, _ = cl.sample(ss)
    n = len(P)
    flagged_until = -1.0
    for lag in (6, 10, 16, 24, 30):                       # 3 .. 15 mm
        if lag >= n:
            break
        idx = np.arange(n) if cl.closed else np.arange(n - lag)
        j = (idx + lag) % n
        dist = np.linalg.norm(P[j] - P[idx], axis=1)
        bad = np.nonzero(dist < 0.35 * lag * 0.0005)[0]
        for i in bad.tolist():
            mid = (ss[i] + lag * 0.00025) * 1000
            if all(abs(mid - h) > 8 for h in hairpins):
                hairpins.append(round(mid))
hairpins.sort()

# stitches across the air
me = s.ribbon.data
co = np.empty(len(me.vertices) * 3, np.float32)
me.vertices.foreach_get("co", co)
co = co.reshape(-1, 3)
lv = np.empty(len(me.loops), np.int32)
me.loops.foreach_get("vertex_index", lv)
q = lv.reshape(-1, 4)
E = np.stack([np.linalg.norm(co[q[:, (k + 1) % 4]] - co[q[:, k]], axis=1) for k in range(4)], 1)
air = int((E.max(1) > 0.004).sum())

# corners
turns = []
for cl in cls:
    for c in cl.corners:
        P, _, _ = cl.sample(np.array([c - 0.002, c, c + 0.002]))
        v1, v2 = P[1] - P[0], P[2] - P[1]
        turns.append(float(np.degrees(np.arccos(np.clip(
            np.dot(v1, v2) / np.linalg.norm(v1) / np.linalg.norm(v2), -1, 1)))))

# gaps in the baked mask along the line
s.output_dir = out_dir
s.transparent = False
s.resolution = '4096'
paths = bake.bake_masks(bpy.context, ob, s.ribbon, d, s)
img = bpy.data.images.load(paths[0])
img.colorspace_settings.name = "Non-Color"
res = img.size[0]
px = np.empty(res * res * 4, np.float32)
img.pixels.foreach_get(px)
m = px.reshape(res, res, 4)[:, :, 0]
bvh = BVHTree.FromPolygons(topo.co.tolist(), topo.tri.tolist(), all_triangles=True)
gaps = []
step = 0.0003
for cl in cls:
    ss = np.arange(0, cl.length, step)
    P, _, _ = cl.sample(ss)
    run = 0
    for p in P.tolist():
        loc, n, ti, _ = bvh.find_nearest(p)
        V = topo.V[ti]
        U = topo.uv[ti]
        w = geometry.barycentric_transform(loc, *[Vector(x) for x in V],
                                           *[Vector((u[0], u[1], 0)) for u in U])
        x, y = int(w.x * res), int(w.y * res)
        c = m[max(y - 2, 0):y + 3, max(x - 2, 0):x + 3].max() if 0 <= x < res and 0 <= y < res else 0
        if c < 0.3:
            run += 1
        else:
            if run * step > 0.0015:
                gaps.append(round(run * step * 1000, 1))
            run = 0

out = dict(
    lines=len(cls), length_mm=round(sum(c.length for c in cls) * 1000),
    stitches=d.dash_count, gaps_mm=gaps, double_pts=double, hairpins_at_mm=hairpins, air_quads=air,
    corners=len(turns), corner_turn=round(float(np.median(turns)), 1) if turns else None,
    t_first=round((t1 - t0) * 1000), t_dash=round((t2 - t1) * 1000), t_inset=round((t3 - t2) * 1000),
    status=s.status)
print("REGRESS " + json.dumps(out))
