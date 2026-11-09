"""Multi-material + UDIM + duplicate-slot bake test, started from Edit Mode.

blender -b skirt_test.blend -P multi_test.py -- <out_dir>
"""
import os
import sys

import bpy
import bmesh
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pattern_masks as sg  # noqa: E402

out_dir = sys.argv[sys.argv.index("--") + 1]
os.makedirs(out_dir, exist_ok=True)
for f in os.listdir(out_dir):
    if f.endswith(".png"):
        os.remove(os.path.join(out_dir, f))
sg.register()
ob = bpy.data.objects["Skirt"]
me = ob.data
cloth = me.materials[0]
lace = bpy.data.materials.new("Skirt_Lace")
me.materials.append(lace)    # slot 1
me.materials.append(cloth)   # slot 2: same material again

# Faces with x > 0: slot 1 + UDIM 1002; faces with x < 0 and y > 0: slot 2 (same as slot 0).
uv = me.uv_layers[0].data
for p in me.polygons:
    c = p.center
    if c.x > 0:
        p.material_index = 1
        for li in p.loop_indices:
            uv[li].uv.x += 1.0
    elif c.y > 0:
        p.material_index = 2

bpy.context.view_layer.objects.active = ob
ob.select_set(True)
s = ob.stitch_gen
s.live = False
s.resolution = '2048'
s.output_dir = out_dir
bpy.ops.object.mode_set(mode='EDIT')
bm = bmesh.from_edit_mesh(me)
for e in bm.edges:
    e.select_set(e.is_boundary and all(v.co.z < -0.265 for v in e.verts))
bm.select_flush_mode()
bmesh.update_edit_mesh(me)
bpy.ops.stitch_gen.path_add()
res = bpy.ops.stitch_gen.bake()
print("BAKE_RESULT", res, "mode after bake:", ob.mode)
print("FILES", sorted(f for f in os.listdir(out_dir) if f.endswith(".png")))
