"""Clear All Layers, and the one switch for all marks.

Two meshes with stitches, line art and corners (one of them in Edit Mode):
Clear All Layers leaves no layers, no add-on attributes, no previews and no
preview collection, and keeps the meshes. The marks switch hides the
overlay of every layer without touching their own toggles, and + turns it
back on.

blender -b --factory-startup skirt_test.blend -P clear_scene_test.py
"""
import os
import sys

import bpy
import bmesh

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import rizum_pattern_masks as sg  # noqa: E402
from rizum_pattern_masks import core, overlay  # noqa: E402

sg.register()
fails = []


def check(name, ok, *info):
    print("RESULT", "PASS" if ok else "FAIL", name, *info)
    if not ok:
        fails.append(name)


def select(ob, pick):
    bm = bmesh.from_edit_mesh(ob.data)
    for e in bm.edges:
        e.select_set(False)
    for v in bm.verts:
        v.select_set(False)
    for e in bm.edges:
        if e.is_boundary and pick([ob.matrix_world @ v.co for v in e.verts]):
            e.select_set(True)
    bmesh.update_edit_mesh(ob.data)


HEM = lambda P: all(p.z < -0.265 for p in P)                     # noqa: E731
WAIST = lambda P: all(p.z > -0.01 for p in P)                    # noqa: E731

ob = bpy.data.objects["Skirt"]
ob2 = ob.copy()
ob2.data = ob.data.copy()
ob2.location.x += 1.0
bpy.context.collection.objects.link(ob2)
vl = bpy.context.view_layer
for o in (ob, ob2):
    o.select_set(True)
vl.objects.active = ob
bpy.ops.stitch_gen.line_add()
bpy.ops.object.mode_set(mode='EDIT')        # both in Edit Mode
for o in (ob, ob2):
    select(o, WAIST)
bpy.ops.stitch_gen.path_add()                # the line layer, on both
ob.stitch_gen.line_index = -1
for o in (ob, ob2):
    select(o, HEM)
bpy.ops.stitch_gen.path_add()                # the stitches, on both
bpy.ops.object.mode_set(mode='OBJECT')
bpy.ops.object.mode_set(mode='EDIT')         # ob2 stays in Edit Mode only
bpy.ops.object.mode_set(mode='OBJECT')
ob2.select_set(False)
vl.objects.active = ob2
bpy.ops.object.mode_set(mode='EDIT')
vl.objects.active = ob

ATTRS = (core.PATH_ATTR, core.CORNER_ATTR)


def ours(o):
    o.update_from_editmode()
    return sorted(n for n in o.data.attributes.keys()
                  if n in ATTRS or n.startswith(core.LINE_ATTR))


def previews():
    from rizum_pattern_masks import preview
    return sorted(o.name for o in (ob, ob2) if preview.has(o))


before = (len(ob.stitch_gen.lines), len(ob2.stitch_gen.lines), ours(ob), ours(ob2), previews())
check("set up: layers, attributes and previews on both",
      before[0] == 2 and before[1] == 2 and len(before[2]) == 3 and len(before[3]) == 3
      and len(before[4]) == 2, before)

# the marks switch
scene = bpy.context.scene
own = [l.show_marks for l in ob.stitch_gen.lines]
scene.stitch_gen_marks = False
check("marks off: the layers keep their own toggles",
      [l.show_marks for l in ob.stitch_gen.lines] == own)
check("marks off: nothing drawn", not overlay._marks_on(bpy.context))
bpy.ops.object.mode_set(mode='OBJECT')
vl.objects.active = ob
bpy.ops.object.mode_set(mode='EDIT')
select(ob, HEM)
bpy.ops.stitch_gen.path_add()
check("+ turns the marks back on", scene.stitch_gen_marks)
bpy.ops.object.mode_set(mode='OBJECT')
vl.objects.active = ob2
bpy.ops.object.mode_set(mode='EDIT')        # ob2 in Edit Mode for the clear
vl.objects.active = ob

# clear
bpy.ops.ed.undo_push(message="before clear")
r = bpy.ops.stitch_gen.clear_scene()
after = (len(ob.stitch_gen.lines), len(ob2.stitch_gen.lines), ours(ob), ours(ob2), previews())
check("clear: finished", r == {'FINISHED'}, r)
check("clear: no layers, attributes or previews",
      after == (0, 0, [], [], []), after)
check("clear: nothing added to the scene", sorted(o.name for o in bpy.data.objects)
      == sorted((ob.name, ob2.name)), [o.name for o in bpy.data.objects])
check("clear: nothing left to clear", not bpy.ops.stitch_gen.clear_scene.poll())
check("clear: the meshes keep their faces", len(ob.data.polygons) > 0 and len(ob2.data.polygons) > 0)

print("ALL PASS" if not fails else f"FAILED: {fails}")
