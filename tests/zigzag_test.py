"""Zigzag stitches: build, bake, and save a close-up of the mask.

blender -b --factory-startup skirt_test.blend -P zigzag_test.py -- <out_dir>
"""
import os
import sys

import bpy
import bmesh
import numpy as np

out_dir = sys.argv[sys.argv.index("--") + 1]
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import rizum_pattern_masks as sg  # noqa: E402
from tests import _preview as pv  # noqa: E402

sg.register()
os.makedirs(out_dir, exist_ok=True)
for f in os.listdir(out_dir):
    if f.endswith(".png"):
        os.remove(os.path.join(out_dir, f))
ob = bpy.data.objects["Skirt"]
bpy.context.view_layer.objects.active = ob
ob.select_set(True)
s = ob.stitch_gen
s.live = False
bpy.ops.stitch_gen.stitch_add()
bpy.ops.object.mode_set(mode='EDIT')
bm = bmesh.from_edit_mesh(ob.data)
for e in bm.edges:
    e.select_set(e.is_boundary and all((ob.matrix_world @ v.co).z < -0.265 for v in e.verts))
bm.select_flush_mode()
bmesh.update_edit_mesh(ob.data)
bpy.ops.stitch_gen.path_add()
bpy.ops.object.mode_set(mode='OBJECT')

s.inset, s.width = (float(os.environ.get("ZZ_INSET", 5.0)), float(os.environ.get("ZZ_WIDTH", 0.6)))
dash = sg.regenerate(ob)
print("RESULT dashed stitches", dash.dash_count)
s.style = 'ZIGZAG'
s.length, s.zigzag_height = 3.0, 3.0
zz = sg.regenerate(ob)
print("RESULT zigzag legs", zz.dash_count, "faces", pv.stitch_faces(ob),
      "status", s.status or "ok")
s.output_dir = out_dir
s.resolution = '4096'
print("RESULT bake", bpy.ops.stitch_gen.bake())
f = [x for x in os.listdir(out_dir) if x.endswith("_stitch.png")][0]
img = bpy.data.images.load(os.path.join(out_dir, f))
img.colorspace_settings.name = "Non-Color"
r = img.size[0]
px = np.empty(r * r * 4, np.float32)
img.pixels.foreach_get(px)
m = px.reshape(r, r, 4)[::-1, :, 0]          # row 0 = top
ys, xs = np.nonzero(m > 0.5)
print("RESULT covered px", len(xs))
cy, cx = int(np.median(ys)), int(np.median(xs))
crop = m[max(cy - 60, 0):cy + 60, max(cx - 200, 0):cx + 200]
out = bpy.data.images.new("crop", crop.shape[1], crop.shape[0], alpha=False)
rgba = np.repeat(crop[::-1, :, None], 4, 2)
rgba[..., 3] = 1.0
out.pixels.foreach_set(rgba.astype(np.float32).ravel())
out.filepath_raw = os.path.join(out_dir, "zigzag_crop.png")
out.file_format = 'PNG'
out.save()
print("RESULT crop saved")
if len(sys.argv) > sys.argv.index("--") + 2:
    bpy.ops.wm.save_as_mainfile(filepath=sys.argv[sys.argv.index("--") + 2], copy=True)
