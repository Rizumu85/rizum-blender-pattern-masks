"""Dump the stitch lines and corner points of the current package in UV space,
for drawing crops around corners (or around given mm positions).

blender -b <file> -P corner_tiles.py -- <object> <out.npy> [<mm,mm,...>]
"""
import os
import sys

import bpy
import bmesh
import numpy as np
from mathutils import Vector, geometry

args = sys.argv[sys.argv.index("--") + 1:]
obj_name, out_npy = args[0], args[1]
spots = [float(x) for x in args[2].split(",")] if len(args) > 2 else []
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pattern_masks as sg  # noqa: E402
from pattern_masks import core  # noqa: E402

sg.register()
ob = bpy.data.objects[obj_name]
bpy.context.view_layer.objects.active = ob
ob.select_set(True)
s = ob.stitch_gen
s.live = False
if ob.mode != 'OBJECT':
    bpy.ops.object.mode_set(mode='OBJECT')
if core.PATH_ATTR not in ob.data.attributes:
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
sg.regenerate(ob)
e = core._cache[ob.name_full]
topo = e["topo"]
bvh = topo.bvh()


def to_uv(p):
    loc, n, ti, _ = bvh.find_nearest(list(p))
    V = topo.V[ti]
    U = topo.uv[ti]
    w = geometry.barycentric_transform(loc, *[Vector(x) for x in V],
                                       *[Vector((u[0], u[1], 0)) for u in U])
    return (w.x, w.y)


lines, centres = [], []
acc = 0.0
ends_only = os.environ.get("TILES_ENDS") == "1"
for cl in e["cls"]:
    P = cl.P
    lines.append([to_uv(p) for p in P])
    if ends_only:
        if not cl.closed:
            centres.append(("end %d %dmm" % (len(lines) - 1, round(cl.length * 1000)), to_uv(P[0])))
            centres.append(("end %d" % (len(lines) - 1), to_uv(P[-1])))
        else:
            centres.append(("loop %d %dmm" % (len(lines) - 1, round(cl.length * 1000)), to_uv(P[0])))
    else:
        for c in cl.corners:
            q, _, _ = cl.sample(np.array([c]))
            centres.append(("c", to_uv(q[0])))
    for mm in spots:
        if acc <= mm / 1000 < acc + cl.length:
            q, _, _ = cl.sample(np.array([mm / 1000 - acc]))
            centres.append(("%d" % mm, to_uv(q[0])))
    acc += cl.length
me = ob.data
uv = np.empty(len(me.loops) * 2, np.float32)
(me.uv_layers.get(topo.uv_name) or me.uv_layers[0]).data.foreach_get("uv", uv)
uv = uv.reshape(-1, 2)
keys = {tuple(sorted(x)) for x in core.read_path_edges(me).tolist()}
path, wire = [], []
for poly in me.polygons:
    li = list(poly.loop_indices)
    for a, b in zip(li, li[1:] + li[:1]):
        sgm = (uv[a].tolist(), uv[b].tolist())
        wire.append(sgm)
        if tuple(sorted((me.loops[a].vertex_index, me.loops[b].vertex_index))) in keys:
            path.append(sgm)
np.save(out_npy, np.array([dict(lines=lines, centres=centres, path=path, wire=wire)], dtype=object),
        allow_pickle=True)
print("TILES", len(lines), len(centres), [round(c.length * 1000) for c in e["cls"]])
