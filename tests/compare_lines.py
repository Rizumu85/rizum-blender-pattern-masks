"""Draw the stitch line of the current package and of a reference package in UV,
cropped around given positions (mm along the current line).

blender -b <file> -P compare_lines.py -- <object> <ref_pkg_dir> <out.png> <mm,mm,...>
"""
import importlib
import os
import sys

import bpy
import numpy as np
from mathutils import Vector, geometry
from mathutils.bvhtree import BVHTree

args = sys.argv[sys.argv.index("--") + 1:]
obj_name, ref_dir, out_png, spots = args[0], args[1], args[2], [float(x) for x in args[3].split(",")]
here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def lines_from(pkg_dir):
    for m in [k for k in sys.modules if k.startswith("rizum_pattern_masks")]:
        del sys.modules[m]
    sys.path.insert(0, pkg_dir)
    sg = importlib.import_module("rizum_pattern_masks")
    core = importlib.import_module("rizum_pattern_masks.core")
    sys.path.pop(0)
    try:
        sg.register()
    except Exception:
        pass
    ob = bpy.data.objects[obj_name]
    ob.stitch_gen.live = False
    core.drop_cache()
    sg.regenerate(ob)
    e = core._cache[ob.name_full]
    out = [(cl.sample(np.arange(0, cl.length, 0.0002))[0], cl.length) for cl in e["cls"]]
    topo = e["topo"]
    sg.unregister()
    return out, topo


ob = bpy.data.objects[obj_name]
bpy.context.view_layer.objects.active = ob
if ob.mode != 'OBJECT':
    bpy.ops.object.mode_set(mode='OBJECT')
new, topo = lines_from(here)
old, _ = lines_from(ref_dir)
bvh = BVHTree.FromPolygons(topo.co.tolist(), topo.tri.tolist(), all_triangles=True)


def to_uv(p):
    loc, n, ti, _ = bvh.find_nearest(list(p))
    V = topo.V[ti]
    U = topo.uv[ti]
    w = geometry.barycentric_transform(loc, *[Vector(x) for x in V], *[Vector((u[0], u[1], 0)) for u in U])
    return (w.x, w.y)


me = ob.data
uv = np.empty(len(me.loops) * 2, np.float32)
me.uv_layers[0].data.foreach_get("uv", uv)
uv = uv.reshape(-1, 2)
from rizum_pattern_masks import core as c2  # noqa: E402 (current package, re-imported below)
sys.path.insert(0, here)
for m in [k for k in sys.modules if k.startswith("rizum_pattern_masks")]:
    del sys.modules[m]
import rizum_pattern_masks.core as cur  # noqa: E402
keys = {tuple(sorted(e)) for e in cur.read_path_edges(me).tolist()}
path, wire = [], []
for poly in me.polygons:
    li = list(poly.loop_indices)
    for a, b in zip(li, li[1:] + li[:1]):
        seg = (uv[a].tolist(), uv[b].tolist())
        wire.append(seg)
        if tuple(sorted((me.loops[a].vertex_index, me.loops[b].vertex_index))) in keys:
            path.append(seg)

crops = []
for mm in spots:
    # position on the new line
    acc = 0.0
    centre = None
    for P, L in new:
        if mm / 1000.0 <= acc + L:
            centre = P[min(int((mm / 1000.0 - acc) / 0.0002), len(P) - 1)]
            break
        acc += L
    if centre is None:
        continue
    cu = to_uv(centre)
    R = 0.012
    lines_uv = []
    for col, group in (((255, 150, 40), old), ((80, 220, 255), new)):
        for P, _ in group:
            near = np.linalg.norm(P - centre, axis=1) < 0.03
            if near.any():
                lines_uv.append((col, [to_uv(p) for p in P[near]]))
    crops.append((mm, cu, R, lines_uv))
np.save(out_png + ".npy", np.array([dict(mm=c[0], cu=c[1], R=c[2], lines=c[3]) for c in crops] +
                                   [dict(path=path, wire=wire)], dtype=object), allow_pickle=True)
print("COMPARE saved", len(crops))
