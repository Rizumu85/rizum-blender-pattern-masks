"""A line along a UV island's border bakes, even when it is thinner than a
texel: the skirt's waist is the top border of its UV island, and the pixel
centres nearest it lie just off the island, so they used to be skipped and
the waist line came out empty.

blender -b --factory-startup skirt_test.blend -P border_line_test.py -- <out_dir>
"""
import os
import sys

import bpy
import bmesh
import numpy as np

out_dir = sys.argv[sys.argv.index("--") + 1]
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import rizum_pattern_masks as sg  # noqa: E402
from rizum_pattern_masks import core  # noqa: E402

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

bpy.ops.stitch_gen.line_add()
bpy.ops.object.mode_set(mode='EDIT')
bm = bmesh.from_edit_mesh(ob.data)
for e in bm.edges:
    e.select_set(e.is_boundary and all((ob.matrix_world @ v.co).z > -0.01 for v in e.verts))
bm.select_flush_mode()
bmesh.update_edit_mesh(ob.data)
bpy.ops.stitch_gen.path_add()
bpy.ops.object.mode_set(mode='OBJECT')
sg.regenerate(ob)

s.output_dir = out_dir
s.resolution = '1024'
print("RESULT bake", bpy.ops.stitch_gen.bake())
entry = core._cache[ob.name_full]
uv = entry["topo"].uv
top = uv[..., 1].max()                       # the waist: top of the island
path = os.path.join(out_dir, "Skirt_Skirt_Cloth_line.png")
img = bpy.data.images.load(path)
img.colorspace_settings.name = "Non-Color"
r = img.size[0]
px = np.empty(r * r * 4, np.float32)
img.pixels.foreach_get(px)
g = px.reshape(r, r, 4)[:, :, 0]             # row 0 at the bottom, like UV
row = int(top * r)
band = g[max(row - 2, 0):row + 2]
cover = (band.max(0) > 0.5).mean()
inside = g[int(top * r - 0.5) - 3:int(top * r - 0.5) - 1]   # well inside the island
print("RESULT waist row", row, "columns covered %.3f" % cover,
      "max %.2f" % float(band.max()), "inside rows max %.2f" % float(inside.max()))
ok = cover > 0.95
print("RESULT", "PASS" if ok else "FAIL", "waist line baked along the island border")
