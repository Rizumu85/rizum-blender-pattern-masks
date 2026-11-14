"""Mark a vertex in the middle of a smooth scallop arc as a corner (Edit Mode
operator) and check that a corner appears there. blender -b skirt_test.blend -P corner_mark_test.py"""
import os
import sys
import bpy
import bmesh
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import rizum_pattern_masks as sg  # noqa: E402
from rizum_pattern_masks import core  # noqa: E402

sg.register()
ob = bpy.data.objects["Skirt"]
bpy.context.view_layer.objects.active = ob
ob.select_set(True)
ob.stitch_gen.live = False
bpy.ops.object.mode_set(mode='EDIT')
bm = bmesh.from_edit_mesh(ob.data)
hem = [e for e in bm.edges if e.is_boundary and all(v.co.z < -0.265 for v in e.verts)]
hem_vi = {v.index for e in hem for v in e.verts}
for e in bm.edges:
    e.select_set(e in hem)
bm.select_flush_mode()
bmesh.update_edit_mesh(ob.data)
bpy.ops.stitch_gen.path_add()


def corners():
    sg.regenerate(ob)
    return [c for cl in next(iter(core._cache[ob.name_full]["stitch"].values()))["cls"] for c in cl.corners]


before = len(corners())
# lowest hem vertex = middle of a scallop arc (smooth there)
bm = bmesh.from_edit_mesh(ob.data)
bm.verts.ensure_lookup_table()
target = min((bm.verts[i] for i in hem_vi), key=lambda v: (v.co.z, v.co.x))
for v in bm.verts:
    v.select_set(False)
target.select_set(True)
bm.select_flush_mode()
bmesh.update_edit_mesh(ob.data)
print("RESULT mark", bpy.ops.stitch_gen.corner_mark())
after = len(corners())
print("RESULT clear", bpy.ops.stitch_gen.corner_clear())
cleared = len(corners())
print(f"RESULT corners before={before} after_mark={after} after_clear={cleared}")
