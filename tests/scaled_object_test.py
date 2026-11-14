"""FBX-style object scale 0.01 (mesh 100x larger) must bake like scale 1.
blender -b skirt_test.blend -P scaled_object_test.py -- <out_dir>"""
import os
import sys
import bpy
import bmesh
import numpy as np
from mathutils import Matrix

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import rizum_pattern_masks as sg  # noqa: E402
from rizum_pattern_masks import bake  # noqa: E402

out = sys.argv[sys.argv.index("--") + 1]
os.makedirs(out, exist_ok=True)
sg.register()
ob = bpy.data.objects["Skirt"]
ob.data.transform(Matrix.Scale(100.0, 4))
ob.scale = (0.01, 0.01, 0.01)
bpy.context.view_layer.update()
bpy.context.view_layer.objects.active = ob
ob.select_set(True)
s = ob.stitch_gen
s.live = False
s.resolution = '2048'
s.output_dir = out
bpy.ops.object.mode_set(mode='EDIT')
bm = bmesh.from_edit_mesh(ob.data)
for e in bm.edges:
    e.select_set(e.is_boundary and all((ob.matrix_world @ v.co).z < -0.265 for v in e.verts))
bm.select_flush_mode()
bmesh.update_edit_mesh(ob.data)
bpy.ops.stitch_gen.path_add()
bpy.ops.object.mode_set(mode='OBJECT')
s.inset, s.smooth, s.length, s.gap, s.width = 4.0, 2.0, 4.0, 2.5, 1.2
d = sg.regenerate(ob)
paths = bake.bake_masks(bake.BakeSession(bpy.context, ob, [(d.stitches[0][1], "stitch")], s,
                                         sg._mask_material()))
v = np.empty(2048 * 2048 * 4, np.float32)
img = bpy.data.images.load(paths[0])
img.colorspace_settings.name = "Non-Color"
img.pixels.foreach_get(v)
print("RESULT scale-0.01 object: stitches", d.dash_count, "stitch px", int((v[0::4] > 0.5).sum()))
