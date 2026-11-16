"""Grid layer: add it, mark the waist as its edge, preview, bake three masks.

blender -b --factory-startup skirt_test.blend -P grid_test.py -- <out_dir>
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
print("RESULT add grid", bpy.ops.stitch_gen.grid_add())
g = s.lines[s.line_index]
print("RESULT row", g.name, g.kind, "shown as", g.label, "color", tuple(round(c, 2) for c in g.color))
bpy.ops.object.mode_set(mode='EDIT')
bm = bmesh.from_edit_mesh(ob.data)
for e in bm.edges:
    e.select_set(e.is_boundary and all((ob.matrix_world @ v.co).z > -0.01 for v in e.verts))
bm.select_flush_mode()
bmesh.update_edit_mesh(ob.data)
bpy.ops.stitch_gen.path_add()
bpy.ops.object.mode_set(mode='OBJECT')
sg.regenerate(ob)
print("RESULT preview faces", pv.grid_faces(ob), "status", s.status or "ok")
s.output_dir = out_dir
s.resolution = '2048'
s.transparent = False
print("RESULT bake count", sg._bake_count(ob), bpy.ops.stitch_gen.bake())
files = sorted(f for f in os.listdir(out_dir) if f.endswith(".png"))
print("RESULT files", files)
for f in files:
    img = bpy.data.images.load(os.path.join(out_dir, f))
    img.colorspace_settings.name = "Non-Color"
    r = img.size[0]
    px = np.empty(r * r * 4, np.float32)
    img.pixels.foreach_get(px)
    m = px.reshape(r, r, 4)[::-1, :, 0]
    np.save(os.path.join(out_dir, f[:-4] + ".npy"), m)
    print("RESULT", f, "mean", round(float(m.mean()), 4), "max", round(float(m.max()), 3))
# the other layouts of the same layer: each bakes, and differs
for mode in ('UNROLLED',):
    g.grid_layout = mode
    sg.regenerate(ob)
    print("RESULT", mode, "preview faces", pv.grid_faces(ob), "status",
          s.status or "ok")
    sub = os.path.join(out_dir, mode.lower())
    os.makedirs(sub, exist_ok=True)
    s.output_dir = sub
    print("RESULT", mode, "bake", bpy.ops.stitch_gen.bake())
    for f in sorted(f for f in os.listdir(sub) if f.endswith("_black.png")):
        img = bpy.data.images.load(os.path.join(sub, f))
        img.colorspace_settings.name = "Non-Color"
        r = img.size[0]
        px = np.empty(r * r * 4, np.float32)
        img.pixels.foreach_get(px)
        m = px.reshape(r, r, 4)[::-1, :, 0]
        m0 = np.load(os.path.join(out_dir, f[:-4] + ".npy"))
        print("RESULT", mode, f, "mean", round(float(m.mean()), 4),
              "pixels changed", int((np.abs(m - m0) > 0.5).sum()))
if len(sys.argv) > sys.argv.index("--") + 2:          # keep the result for screenshots
    bpy.ops.wm.save_as_mainfile(filepath=sys.argv[sys.argv.index("--") + 2], copy=True)
