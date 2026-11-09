"""Corner detection on the test skirt: the 16 scallop junctions are known
(every 8th hem vertex). blender -b skirt_test.blend -P detect_test.py"""
import os
import sys
import bpy
import bmesh
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import rizum_pattern_masks as sg  # noqa: E402

sg.register()
ob = bpy.data.objects["Skirt"]
bpy.context.view_layer.objects.active = ob
ob.select_set(True)
ob.stitch_gen.live = False
bpy.ops.object.mode_set(mode='EDIT')
bm = bmesh.from_edit_mesh(ob.data)
for e in bm.edges:
    e.select_set(e.is_boundary and all(v.co.z < -0.265 for v in e.verts))
bm.select_flush_mode()
bmesh.update_edit_mesh(ob.data)
bpy.ops.stitch_gen.path_add()          # first path: seeds corners
bpy.ops.object.mode_set(mode='OBJECT')
v = np.zeros(len(ob.data.vertices), np.int32)
ob.data.attributes['stitch_corner'].data.foreach_get('value', v)
marked = set(np.nonzero(v)[0].tolist())
expected = {320 + j for j in range(0, 128, 8)}
print("RESULT marked", len(marked), "expected", len(expected),
      "hits", len(marked & expected), "extra", sorted(marked - expected))
bpy.ops.object.mode_set(mode='EDIT')
print("RESULT detect op", bpy.ops.stitch_gen.corner_detect(), "select op", bpy.ops.stitch_gen.corner_select())
bm = bmesh.from_edit_mesh(ob.data)
print("RESULT selected after select-corners", sum(1 for x in bm.verts if x.select))
