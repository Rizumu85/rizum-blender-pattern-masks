"""The previews are drawn, not objects: nothing is added to the scene, old
preview objects go, a preview out of date asks for one rebuild, and the
add-on keeps no handlers that run on every change.

    blender -b --factory-startup skirt_test.blend -P preview_test.py
"""
import os
import sys
import time

import bpy
import bmesh

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import rizum_pattern_masks as sg  # noqa: E402
from rizum_pattern_masks import core, preview  # noqa: E402
from tests import _preview as pv  # noqa: E402

sg.register()
fails = []


def check(name, ok, *info):
    print("RESULT", "PASS" if ok else "FAIL", name, *info)
    if not ok:
        fails.append(name)


def mark(o, attr, pick):
    me = o.data
    bm = bmesh.new()
    bm.from_mesh(me)
    lay = bm.edges.layers.int.get(attr) or bm.edges.layers.int.new(attr)
    for e in bm.edges:
        if e.is_boundary and all(pick(v.co.z) for v in e.verts):
            e[lay] = 1
    bm.to_mesh(me)
    bm.free()


ours = (sg.__name__, "rizum_pattern_masks")
for name in ("depsgraph_update_post", "depsgraph_update_pre", "undo_post", "redo_post",
             "undo_pre", "redo_pre"):
    mine = [f for f in getattr(bpy.app.handlers, name) if f.__module__.startswith(ours)]
    check(f"no {name} handler", not mine, mine)
check("no threads", not [m for m in sys.modules if m.startswith(ours) and
                         "threading" in vars(sys.modules[m])])

ob = bpy.data.objects["Skirt"]
bpy.context.view_layer.objects.active = ob
ob.select_set(True)
s = ob.stitch_gen
before = sorted(o.name for o in bpy.data.objects)
with bpy.context.temp_override(active_object=ob, object=ob):
    bpy.ops.stitch_gen.stitch_add()
    bpy.ops.stitch_gen.line_add()
    bpy.ops.stitch_gen.grid_add()
for l in s.lines:
    mark(ob, l.edge_attr, (lambda z: z > -0.01) if l.kind == 'GRID' else (lambda z: z < -0.265))
sg.regenerate(ob)
check("previews drawn", pv.stitch_faces(ob) > 0 and sum(pv.line_faces(ob).values()) > 0
      and pv.grid_faces(ob) > 0, pv.stitch_faces(ob), pv.line_faces(ob), pv.grid_faces(ob))
check("nothing added to the scene", sorted(o.name for o in bpy.data.objects) == before,
      sorted(o.name for o in bpy.data.objects))
check("the drawing knows the object", ob in preview.objects(bpy.context))

# colors come from the layers when drawn: no rebuild for a color
key = preview._store[ob.name_full]["key"]
s.lines[1].color = (0.2, 0.9, 0.3, 1.0)
col = sg._layer_colors(ob)[s.lines[1].edge_attr]
check("a color needs no rebuild", preview._store[ob.name_full]["key"] == key
      and sg._preview_key(ob) == key and abs(col[1] - 0.9) < 1e-6, col)

# moved: the same preview, drawn where the object is; scaled: rebuilt
ob.location.x += 0.3
bpy.context.view_layer.update()
check("moving keeps the preview", sg._preview_key(ob) == key)
ob.scale = (1.5, 1.5, 1.5)
bpy.context.view_layer.update()
check("scaling makes it out of date", sg._preview_key(ob) != key)
ob.scale = (1.0, 1.0, 1.0)
ob.location.x -= 0.3
bpy.context.view_layer.update()

# a value changed without its update (as undo brings one back): out of date,
# and the drawing asks for one rebuild
s.lines[0]["inset"] = 6.5
check("undo-like change: out of date", sg._preview_key(ob) != key)
sg._request(ob)
sg._request(ob)
check("one rebuild asked for", list(sg._pending) == [ob.name_full], list(sg._pending))
time.sleep(sg._DEBOUNCE + 0.05)
sg._flush()
check("rebuilt for the new value", preview._store[ob.name_full]["key"] == sg._preview_key(ob)
      and not sg._pending)

# a rebuild that fails (far too many stitches) shows nothing and isn't asked
# for again on every redraw
s.lines[0]["length"], s.lines[0]["gap"] = 0.01, 0.0
check("failed rebuild", sg.regenerate(ob) is None and s.status != "", s.status)
check("its key is kept: no rebuild asked for again",
      preview._store[ob.name_full]["key"] == sg._preview_key(ob) and pv.stitch_faces(ob) == 0)
s.lines[0]["length"], s.lines[0]["gap"] = 4.0, 2.0
sg.regenerate(ob)

# a preview not yet built is built even when not live (a file just opened)
s.live = False
preview.forget(ob)
sg._request(ob)
time.sleep(sg._DEBOUNCE + 0.05)
sg._flush()
check("first build while not live", preview.has(ob))
s.live = True

# the preview objects of older versions go when a file is opened
me = bpy.data.meshes.new("Skirt_Stitches")
old = bpy.data.objects.new("Skirt_Stitches", me)
col = bpy.data.collections.new(sg.OLD_COLLECTION)
bpy.context.scene.collection.children.link(col)
col.objects.link(old)
s.ribbon = old
tagged = bpy.data.objects.new("Lost_LineArt", bpy.data.meshes.new("Lost_LineArt"))
tagged[sg.OLD_PREVIEW_TAG] = True
col.objects.link(tagged)
mat = bpy.data.materials.new("StitchGen_LinePreview")
s.lines[1].material = mat
bpy.data.meshes.new("Mine_Stitches")             # a user's own, unused: not ours to remove
sg._drop_old_previews()
check("a user's own mesh of a like name stays", "Mine_Stitches" in bpy.data.meshes)
check("old preview objects removed", "Skirt_Stitches" not in bpy.data.objects
      and "Lost_LineArt" not in bpy.data.objects and s.ribbon is None)
check("their collection and material removed", sg.OLD_COLLECTION not in bpy.data.collections
      and "StitchGen_LinePreview" not in bpy.data.materials and s.lines[1].material is None)

# a linked duplicate shares the mesh: marking edges on one updates both
twin = ob.copy()                                 # the same mesh
bpy.context.collection.objects.link(twin)
sg.regenerate(twin)
check("linked duplicate has its own preview", preview.has(twin))
bpy.context.view_layer.objects.active = ob
s.line_index = 0
bpy.ops.object.mode_set(mode='EDIT')
with bpy.context.temp_override(active_object=ob, object=ob):
    bpy.ops.stitch_gen.path_clear()
bpy.ops.object.mode_set(mode='OBJECT')
check("its preview is redone after the shared marks change", not preview.has(twin))
bpy.ops.ed.undo_push()
sg.regenerate(twin)
bpy.data.objects.remove(twin)
bpy.context.view_layer.update()
preview.objects(bpy.context)                     # a rescan drops it
check("a deleted object's preview is let go", "Skirt.001" not in preview._store,
      list(preview._store))
for l in s.lines:                                # marks back for the rest
    if l.kind != 'GRID':
        mark(ob, l.edge_attr, lambda z: z < -0.265)
sg.regenerate(ob)

# the overlay notices a display setting brought back without its update (undo)
from rizum_pattern_masks import overlay  # noqa: E402
k0 = overlay._key(ob)
s.lines[0]["show_marks"] = False
check("overlay key follows the shown marks", overlay._key(ob) != k0)
s.lines[0]["show_marks"] = True

# Unroll on a grid with no edges says so
bpy.ops.stitch_gen.grid_add()
empty = s.lines[s.line_index]
empty.grid_layout = 'UNROLLED'
with bpy.context.temp_override(active_object=ob, object=ob):
    res = bpy.ops.stitch_gen.unroll()
check("Unroll without edges: a message, no error", res == {'CANCELLED'}, res)
bpy.ops.stitch_gen.line_remove()

# Unrolled: a button works it out (no thread)
g = s.lines[2]
s.line_index = 2
g.grid_layout = 'UNROLLED'
with bpy.context.temp_override(active_object=ob, object=ob):
    res = bpy.ops.stitch_gen.unroll()
gc = core._cache[ob.name_full]["grid_coords"].get(core._as_spec(sg._edge_spec(s, g)))
check("Unroll works it out", res == {'FINISHED'} and gc is not None and sg.unrolled(gc), res)
check("and the grid shows it", pv.grid_faces(ob) > 0, pv.grid_faces(ob))

# the list's order is the drawing order: moving a layer needs no rebuild
key = preview._store[ob.name_full]["key"]
order = [a for a, _c in sg._shown_layers(ob)]
s.line_index = 0
with bpy.context.temp_override(active_object=ob, object=ob):
    res = bpy.ops.stitch_gen.layer_move(direction='DOWN')
    top = bpy.ops.stitch_gen.layer_move(direction='UP')
    bpy.ops.stitch_gen.layer_move(direction='UP')
moved = [a for a, _c in sg._shown_layers(ob)]
check("moving a layer reorders the drawing", res == {'FINISHED'} and moved == order
      and s.line_index == 0 and top == {'FINISHED'}, res, top, moved)
with bpy.context.temp_override(active_object=ob, object=ob):
    res = bpy.ops.stitch_gen.layer_move(direction='DOWN')
check("one step down", [a for a, _c in sg._shown_layers(ob)] == [order[1], order[0]] + order[2:]
      and s.line_index == 1)
check("and needs no rebuild", preview._store[ob.name_full]["key"] == sg._preview_key(ob) == key)
with bpy.context.temp_override(active_object=ob, object=ob):
    res = bpy.ops.stitch_gen.layer_move(direction='UP')

print("ALL PASS" if not fails else f"FAILED: {fails}")
