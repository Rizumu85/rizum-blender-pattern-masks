"""Marks off the path: Mark Corner ignores them, the overlay hides them."""
import os
import sys
import bpy
import bmesh
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import rizum_pattern_masks as sg  # noqa: E402
from rizum_pattern_masks import overlay  # noqa: E402

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
bpy.ops.stitch_gen.path_add()                 # seeds 16 corners
overlay.invalidate()
n_path = len(overlay._marks(ob)["dots"])
bm = bmesh.from_edit_mesh(ob.data)
bm.verts.ensure_lookup_table()
for v in bm.verts:
    v.select_set(False)
bm.verts[0].select_set(True)                   # waist vertex, not on the path
bmesh.update_edit_mesh(ob.data)
bpy.ops.stitch_gen.corner_mark()
lay = bmesh.from_edit_mesh(ob.data).verts.layers.int.get("stitch_corner")
bm = bmesh.from_edit_mesh(ob.data)
bm.verts.ensure_lookup_table()
print("RESULT mark on off-path vertex stored:", bm.verts[0][lay])
bm.verts[0][lay] = 1                           # stray mark written directly
bmesh.update_edit_mesh(ob.data)
overlay.invalidate()
print("RESULT overlay dots (edit mode)", len(overlay._marks(ob)["dots"]), "expected", n_path)
bpy.ops.object.mode_set(mode='OBJECT')
overlay.invalidate()
print("RESULT overlay dots (object mode)", len(overlay._marks(ob)["dots"]), "expected", n_path)
