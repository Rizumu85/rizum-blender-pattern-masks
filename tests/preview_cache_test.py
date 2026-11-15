"""Previews: left-over ones removed with their object, and kept-as-is previews
still put right after edits by hand.

    blender -b --factory-startup skirt_test.blend -P preview_cache_test.py
"""
import os
import sys

import bpy
import bmesh
import numpy as np
from mathutils import Matrix

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import rizum_pattern_masks as sg  # noqa: E402

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


def setup(o):
    bpy.context.view_layer.objects.active = o
    o.select_set(True)
    s = o.stitch_gen
    with bpy.context.temp_override(active_object=o, object=o):
        bpy.ops.stitch_gen.stitch_add()
        bpy.ops.stitch_gen.line_add()
        bpy.ops.stitch_gen.grid_add()
        bpy.ops.stitch_gen.grid_add()
    for l in s.lines:
        mark(o, l.edge_attr, (lambda z: z > -0.01) if l.kind == 'GRID' else (lambda z: z < -0.265))
    s.lines[3].grid_cell = 13.0
    sg.regenerate(o, bpy.context.scene, create=True)
    return s


base = bpy.data.objects["Skirt"]
s = setup(base)
rib, lo, go = s.ribbon, s.line_preview, s.grid_preview
check("previews built", all(x is not None for x in (rib, lo, go)))

# -- moved, edited or re-materialled by hand: the next rebuild puts it right
co0 = np.empty(len(rib.data.vertices) * 3, np.float32)
rib.data.vertices.foreach_get("co", co0)
bpy.context.view_layer.objects.active = rib                 # edited by hand, in Edit Mode
bpy.ops.object.mode_set(mode='EDIT')
bm = bmesh.from_edit_mesh(rib.data)
bm.verts.ensure_lookup_table()
bm.verts[0].co.x += 0.05
bmesh.update_edit_mesh(rib.data)
bpy.context.view_layer.update()
bpy.ops.object.mode_set(mode='OBJECT')
bpy.context.view_layer.objects.active = base
check("seen in Edit Mode: its write record forgotten", (base.name_full, "ribbon") not in sg._written)
rib.matrix_world = Matrix.Translation((0.3, 0, 0))
other = bpy.data.materials.new("someone else's")
lo.data.materials[0] = other
sg.regenerate(base, bpy.context.scene, create=True)
co1 = np.empty(len(rib.data.vertices) * 3, np.float32)
rib.data.vertices.foreach_get("co", co1)
check("edited stitch preview rewritten", np.allclose(co0, co1))
check("moved preview back in place", rib.matrix_world == Matrix.Identity(4))
check("material slot restored", lo.data.materials[0] != other)

# -- a deleted material: no error, the rebuild goes on
gm = go.data.materials[0]
bpy.data.materials.remove(gm)
s.lines[2].grid_cell = 9.0
data = sg.regenerate(base, bpy.context.scene, create=False)
check("deleted grid material: rebuild still works", data is not None and s.status == "", s.status)

# -- the first grid layer still being worked out: the second keeps its own slot
ready = sg._unrolled_ready
first = s.lines[2].edge_attr
s.lines[2].grid_layout = 'UNROLLED'
sg._unrolled_ready = lambda ob, sc, entry, attrs: False
try:
    g = sg._grid_geometry(base, bpy.context.scene)
finally:
    sg._unrolled_ready = ready
owners = set(g[3].tolist()) if g is not None else set()
check("waiting grid layer: the next one keeps its index", owners == {1}, owners, first)
s.lines[2].grid_layout = 'LOOPS'

# -- deleting an object removes its previews, unless one is in use somewhere
names = [x.name for x in (rib, lo, go)]
bpy.ops.object.select_all(action='DESELECT')
base.select_set(True)
bpy.context.view_layer.objects.active = base
bpy.ops.object.delete()
other_vl = bpy.context.scene.view_layers.new("other")
other_vl.objects[names[1]].select_set(True, view_layer=other_vl)   # the line art: selected elsewhere
sg._drop_orphan_previews()
left = sorted(n for n in names if n in bpy.data.objects)
check("deleted object: its previews removed, one in use elsewhere kept", left == [names[1]], left)

print("ALL PASS" if not fails else f"FAILED: {fails}")
