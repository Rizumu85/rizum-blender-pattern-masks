"""Line art: add two line layers, check the preview strips, bake, check the PNGs.

blender -b --factory-startup <file.blend> -P line_test.py -- <object> <out_dir>
"""
import os
import sys

import bpy
import bmesh
import numpy as np

args = sys.argv[sys.argv.index("--") + 1:]
obj_name, out_dir = args[0], args[1]
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import rizum_pattern_masks as sg  # noqa: E402
from rizum_pattern_masks import core  # noqa: E402

sg.register()
os.makedirs(out_dir, exist_ok=True)
ob = bpy.data.objects[obj_name]
bpy.context.view_layer.objects.active = ob
ob.select_set(True)
if ob.mode != 'OBJECT':
    bpy.ops.object.mode_set(mode='OBJECT')
s = ob.stitch_gen
if core.PATH_ATTR not in ob.data.attributes:
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(ob.data)
    for e in bm.edges:
        e.select_set(e.is_boundary and all((ob.matrix_world @ v.co).z < -0.265 for v in e.verts))
    bm.select_flush_mode()
    bmesh.update_edit_mesh(ob.data)
    bpy.ops.stitch_gen.path_add()
    bpy.ops.object.mode_set(mode='OBJECT')
    s.inset, s.width = 4.0, 1.2

if sg._stitch_item(s) is None:
    bpy.ops.stitch_gen.stitch_add()
bpy.ops.stitch_gen.line_add()
s.lines[1].width = 0.8
bpy.ops.stitch_gen.line_add()
print("RESULT second layer offset", round(s.lines[2].offset, 2), "names", [l.name for l in s.lines])
s.lines[2].width = 0.5
sg.regenerate(ob)
lo = s.line_preview
print("RESULT preview", lo.name if lo else None, "quads", len(lo.data.polygons) if lo else 0)

s.output_dir = out_dir
s.resolution = '4096'
res = bpy.ops.stitch_gen.bake()
print("RESULT bake", res)
files = sorted(f for f in os.listdir(out_dir) if f.endswith(".png"))
print("RESULT files", files)
for f in files:
    img = bpy.data.images.load(os.path.join(out_dir, f))
    img.colorspace_settings.name = "Non-Color"
    r = img.size[0]
    px = np.empty(r * r * 4, np.float32)
    img.pixels.foreach_get(px)
    m = px.reshape(r, r, 4)[:, :, 0]
    print("RESULT", f, "covered px", int((m > 0.5).sum()))

# stitches off: only the line masks are made
s.stitches = False
sg.regenerate(ob)
print("RESULT stitches off: ribbon faces", len(s.ribbon.data.polygons) if s.ribbon else None)
for f in files:
    os.remove(os.path.join(out_dir, f))
res = bpy.ops.stitch_gen.bake()
print("RESULT bake lines only", res, sorted(f for f in os.listdir(out_dir) if f.endswith(".png")))
