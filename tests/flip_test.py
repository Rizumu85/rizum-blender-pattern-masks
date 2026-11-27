"""Flip Side is each layer's own: flipping one layer moves only its line, in
the preview and in the bake, and files from before keep their side.

    blender -b --factory-startup skirt_test.blend -P flip_test.py
"""
import os
import sys

import bmesh
import bpy
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import rizum_pattern_masks as sg  # noqa: E402
from rizum_pattern_masks import bake, core, layers, migrate  # noqa: E402
from tests import _preview as pv  # noqa: E402

sg.register()
fails = []


def check(name, ok, *info):
    print("RESULT", "PASS" if ok else "FAIL", name, *info)
    if not ok:
        fails.append(name)


ob = bpy.data.objects["Skirt"]
bpy.context.view_layer.objects.active = ob
ob.select_set(True)
s = ob.stitch_gen
zs = sorted({round(v.co.z, 4) for v in ob.data.vertices})
mid = zs[len(zs) // 2]                       # a ring of edges inside the skirt


def mark(attr, pick):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    lay = bm.edges.layers.int.get(attr) or bm.edges.layers.int.new(attr)
    for e in bm.edges:
        if pick(e):
            e[lay] = 1
    bm.to_mesh(ob.data)
    bm.free()


with bpy.context.temp_override(active_object=ob, object=ob):
    bpy.ops.stitch_gen.stitch_add()
    bpy.ops.stitch_gen.line_add()
    bpy.ops.stitch_gen.line_add()
hem, inner, ring = s.lines
mark(hem.edge_attr, lambda e: e.is_boundary and all(v.co.z < -0.265 for v in e.verts))
for l in (inner, ring):
    mark(l.edge_attr, lambda e: not e.is_boundary
         and all(abs(round(v.co.z, 4) - mid) < 1e-4 for v in e.verts))
inner.width = ring.width = 1.0
sg.regenerate(ob)
stitches = pv.stitch_co(ob)
a0, b0 = pv.line_co(ob, inner.edge_attr), pv.line_co(ob, ring.edge_attr)
check("same layers, same lines", len(stitches) and len(a0) and np.allclose(a0, b0))

ring.flip = True
sg.regenerate(ob)
a1, b1 = pv.line_co(ob, inner.edge_attr), pv.line_co(ob, ring.edge_attr)
side = lambda co: float(np.mean(co[:, 2]) - mid)      # above or below the ring
check("the flipped layer moved to the other side", len(b1) and side(b1) * side(a0) < 0,
      side(a0), side(b1) if len(b1) else None)
check("the other layers stayed", np.allclose(a1, a0)
      and np.allclose(pv.stitch_co(ob), stitches))

hem.flip = True
sg.regenerate(ob)
check("on a border the stitches stay on the cloth", np.allclose(pv.stitch_co(ob), stitches)
      and np.allclose(pv.line_co(ob, inner.edge_attr), a0))
hem.flip = False
sg.regenerate(ob)

# the bake works out one field per set of edges and side
entry = core._cache[ob.name_full]
one = layers._line_layers(s, bpy.context.scene)[0]
lb = bake.LineBake(ob, entry, s, [one, one[:7] + (not one[7],)])     # the same edges
check("bake: one field per side", sorted(len(p[0]) for p in lb.parts) == [1, 1],
      [p[0] for p in lb.parts])

# Auto corners judge each layer on its own side, without an error
bpy.ops.object.mode_set(mode='EDIT')
with bpy.context.temp_override(active_object=ob, object=ob):
    res = bpy.ops.stitch_gen.corner_detect()
bpy.ops.object.mode_set(mode='OBJECT')
check("Auto corners with a flipped layer", res == {'FINISHED'}, res)
sg.regenerate(ob)
cornered = pv.stitch_co(ob)
hem.flip = True
sg.regenerate(ob)
from mathutils.kdtree import KDTree  # noqa: E402
fl = pv.stitch_co(ob)
kd = KDTree(len(cornered))
for i, c in enumerate(cornered):
    kd.insert(c, i)
kd.balance()
far = max(kd.find(c)[2] for c in fl)
# (flipped, a border's marked corners no longer apply: hence "leave it off" in the docs)
check("with marked corners, a flipped border stitch stays on the cloth", far < 0.002, far)
hem.flip = False

# a file from before: the one Flip Side goes to every layer
for flip in (True, False):
    o2 = ob.copy()
    o2.data = ob.data.copy()
    bpy.context.collection.objects.link(o2)
    s2 = o2.stitch_gen
    for l in s2.lines:
        l.flip = False
    s2.ui_version, s2.flip = 3, flip
    migrate._ensure_layers(o2)
    check(f"old file, Flip Side {'on' if flip else 'off'}: every layer takes it",
          [l.flip for l in s2.lines] == [flip] * 3 and s2.ui_version == migrate.UI_VERSION,
          [l.flip for l in s2.lines])
    migrate._ensure_layers(o2)
    bpy.data.objects.remove(o2)

print("ALL PASS" if not fails else f"FAILED: {fails}")
