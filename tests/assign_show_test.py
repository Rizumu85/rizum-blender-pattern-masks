"""+ (Add Selected) shows what it adds, or says why nothing shows.

Each case starts from the saved file:
- the preview's collection excluded, hidden, or its eye off: + shows it again;
- the stitch layer's eye off: + turns it on;
- a list with no layer selected: + uses the existing stitch row, no second one;
- nothing selected: + says so (cancelled);
- stitches longer than the marked edges: + finishes but warns (no dashes);
- two meshes in Edit Mode: each gets the edges selected on it, on the
  matching layer (stitches, or a line art layer of the same name);
- the preview made active in Edit Mode: + is off, nothing is marked on it;
- applying a preset leaves no Adjust Last Operation panel.

blender -b --factory-startup skirt_test.blend -P assign_show_test.py
"""
import os
import sys

import bpy
import bmesh

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import rizum_pattern_masks as sg  # noqa: E402

sg.register()
PATH = bpy.data.filepath
fails = []

HEM = lambda P: all(p.z < -0.265 for p in P)                     # noqa: E731
WAIST = lambda P: all(p.z > -0.01 for p in P)                    # noqa: E731


def check(name, ok, *info):
    print("RESULT", "PASS" if ok else "FAIL", name, *info)
    if not ok:
        fails.append(name)


def fresh():
    bpy.ops.wm.open_mainfile(filepath=PATH)
    ob = bpy.data.objects["Skirt"]
    vl = bpy.context.view_layer
    vl.objects.active = ob
    ob.select_set(True)
    return ob


def select(ob, pick, first_only=False):
    """Select the boundary edges whose world-space verts pass ``pick``."""
    bm = bmesh.from_edit_mesh(ob.data)
    for e in bm.edges:                 # clear first: deselecting an edge after
        e.select_set(False)            # selecting its neighbour drops their shared vertex
    for v in bm.verts:
        v.select_set(False)
    n = 0
    for e in bm.edges:
        if e.is_boundary and pick([ob.matrix_world @ v.co for v in e.verts]):
            e.select_set(True)
            n += 1
            if first_only:
                break
    bmesh.update_edit_mesh(ob.data)
    return n


def shown(ob):
    rib = ob.stitch_gen.ribbon
    vl = bpy.context.view_layer
    return (rib is not None and len(rib.data.polygons) > 0 and rib.name in vl.objects
            and rib.visible_get())


def stitch_rows(ob):
    return sum(1 for l in ob.stitch_gen.lines if l.edge_attr == sg.core.PATH_ATTR)


def first_assign(ob):
    bpy.ops.object.mode_set(mode='EDIT')
    select(ob, HEM)
    return bpy.ops.stitch_gen.path_add()


def layer_collection(name):
    def walk(lc):
        if lc.collection.name == name:
            return lc
        for c in lc.children:
            r = walk(c)
            if r:
                return r
    return walk(bpy.context.view_layer.layer_collection)


# the preview's collection hidden in three ways
for how in ("exclude", "collection", "eye"):
    ob = fresh()
    first_assign(ob)
    bpy.ops.object.mode_set(mode='OBJECT')
    if how == "exclude":
        layer_collection(sg.COLLECTION).exclude = True
    elif how == "collection":
        bpy.data.collections[sg.COLLECTION].hide_viewport = True
    else:
        layer_collection(sg.COLLECTION).hide_viewport = True
    hidden = not shown(ob)
    bpy.ops.object.mode_set(mode='EDIT')
    select(ob, WAIST)
    r = bpy.ops.stitch_gen.path_add()
    check(f"collection hidden ({how}): + shows it", hidden and r == {'FINISHED'} and shown(ob),
          hidden, r)

# the preview object hidden or deleted
for how in ("hide", "delete"):
    ob = fresh()
    first_assign(ob)
    bpy.ops.object.mode_set(mode='OBJECT')
    if how == "hide":
        ob.stitch_gen.ribbon.hide_set(True)
    else:
        bpy.data.objects.remove(ob.stitch_gen.ribbon)
    bpy.ops.object.mode_set(mode='EDIT')
    select(ob, WAIST)
    bpy.ops.stitch_gen.path_add()
    check(f"preview {how}: + shows it", shown(ob))

# the stitch layer's eye off
ob = fresh()
first_assign(ob)
ob.stitch_gen.stitches = False
select(ob, WAIST)
bpy.ops.stitch_gen.path_add()
check("eye off: + turns it on", ob.stitch_gen.stitches and shown(ob))

# a line art layer's eye off
ob = fresh()
bpy.ops.stitch_gen.line_add()
ob.stitch_gen.lines[ob.stitch_gen.line_index].enabled = False
bpy.ops.object.mode_set(mode='EDIT')
select(ob, WAIST)
bpy.ops.stitch_gen.path_add()
lo = ob.stitch_gen.line_preview
check("line eye off: + turns it on", ob.stitch_gen.lines[ob.stitch_gen.line_index].enabled
      and lo is not None and len(lo.data.polygons) > 0 and lo.visible_get())

# no layer selected in the list
ob = fresh()
first_assign(ob)
ob.stitch_gen.line_index = -1
select(ob, WAIST)
bpy.ops.stitch_gen.path_add()
check("no layer selected: one stitch row", stitch_rows(ob) == 1, stitch_rows(ob))

# nothing selected
ob = fresh()
bpy.ops.object.mode_set(mode='EDIT')
select(ob, lambda P: False)
r = bpy.ops.stitch_gen.path_add()
check("nothing selected: cancelled", r == {'CANCELLED'} and len(ob.stitch_gen.lines) == 0,
      r, len(ob.stitch_gen.lines))

# stitches longer than the marked edge
ob = fresh()
ob.stitch_gen.length = 100.0
bpy.ops.object.mode_set(mode='EDIT')
select(ob, HEM, first_only=True)
r = bpy.ops.stitch_gen.path_add()
check("too short: finished, no dashes", r == {'FINISHED'} and ob.stitch_gen.dash_count == 0,
      r, ob.stitch_gen.dash_count)

# two meshes in Edit Mode, the other one active
ob = fresh()
ob2 = ob.copy()
ob2.data = ob.data.copy()
ob2.location.x += 1.0
bpy.context.collection.objects.link(ob2)
ob2.select_set(True)
bpy.context.view_layer.objects.active = ob2
bpy.ops.object.mode_set(mode='EDIT')
select(ob2, lambda P: False)
select(ob, HEM)
r = bpy.ops.stitch_gen.path_add()
check("two objects: the selected one gets stitches", r == {'FINISHED'} and stitch_rows(ob) == 1
      and shown(ob), r, stitch_rows(ob))
check("two objects: the active one is left alone", len(ob2.stitch_gen.lines) == 0,
      [l.name for l in ob2.stitch_gen.lines])
select(ob2, WAIST)
r = bpy.ops.stitch_gen.path_add()
check("two objects: both selected, each marked", stitch_rows(ob) == 1 and stitch_rows(ob2) == 1
      and shown(ob) and shown(ob2))

# two meshes, a line art layer selected on the active one
ob = fresh()
ob2 = ob.copy()
ob2.data = ob.data.copy()
ob2.location.x += 1.0
bpy.context.collection.objects.link(ob2)
bpy.ops.stitch_gen.line_add()
name = ob.stitch_gen.lines[ob.stitch_gen.line_index].name
ob2.select_set(True)
bpy.ops.object.mode_set(mode='EDIT')
select(ob, WAIST)
select(ob2, WAIST)
bpy.ops.stitch_gen.path_add()
s2 = ob2.stitch_gen
twin = [l for l in s2.lines if l.name == name and l.kind == 'LINE']
check("two objects: the line layer is matched by name", len(twin) == 1
      and s2.line_preview is not None and len(s2.line_preview.data.polygons) > 0,
      [(l.name, l.kind) for l in s2.lines])
bpy.ops.object.mode_set(mode='OBJECT')

# the preview active in Edit Mode
ob = fresh()
first_assign(ob)
bpy.ops.object.mode_set(mode='OBJECT')
rib = ob.stitch_gen.ribbon
for o in bpy.context.selected_objects:
    o.select_set(False)
bpy.context.view_layer.objects.active = rib
rib.select_set(True)
bpy.ops.object.mode_set(mode='EDIT')
check("preview in Edit Mode: + is off", not bpy.ops.stitch_gen.path_add.poll()
      and len(rib.stitch_gen.lines) == 0)

# applying a preset: nothing to adjust afterwards
check("preset: no redo panel", 'REGISTER' not in sg.STITCHGEN_OT_apply_preset.bl_options
      and 'REGISTER' not in sg.STITCHGEN_OT_reset_defaults.bl_options)

print("ALL PASS" if not fails else f"FAILED: {fails}")
