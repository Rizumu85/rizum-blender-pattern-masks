"""The marks overlay in Edit Mode looks through the whole mesh only when the
marks may have changed; between those it follows just the marked edges.

    blender -b --factory-startup skirt_test.blend -P overlay_test.py
"""
import os
import sys

import bpy
import bmesh
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import rizum_pattern_masks as sg  # noqa: E402
from rizum_pattern_masks import overlay  # noqa: E402

sg.register()
fails = []


def check(name, ok, *info):
    print("RESULT", "PASS" if ok else "FAIL", name, *info)
    if not ok:
        fails.append(name)


ob = bpy.data.objects["Skirt"]
bpy.context.view_layer.objects.active = ob
ob.select_set(True)
s = ob.stitch_gen
with bpy.context.temp_override(active_object=ob, object=ob):
    bpy.ops.stitch_gen.stitch_add()
layer = s.lines[0]
bm = bmesh.new()
bm.from_mesh(ob.data)
lay = bm.edges.layers.int.new(layer.edge_attr)
for e in bm.edges:
    if e.is_boundary and all(v.co.z < -0.265 for v in e.verts):
        e[lay] = 1
bm.to_mesh(ob.data)
bm.free()
sg.regenerate(ob)

looks = []                      # every look through all the mesh's edges
pick = overlay._pick
overlay._pick = lambda o, b: looks.append(o.name) or pick(o, b)
uv_work = []                    # every time the UV marks are worked out
place_uv = overlay._place_uv
overlay._place_uv = lambda o, m, now: uv_work.append(o.name) or place_uv(o, m, now)


def later():
    """As if EDIT_REFRESH had passed since the marks were last read."""
    overlay._cache[ob.name_full]["at"] = 0.0


def points(m):
    return sum(len(pts) for pts, _col in m["edges"])


in_object = points(overlay._marks(ob))
check("Object Mode reads the marks without Edit Mode's look", in_object > 0 and not looks,
      in_object, looks)

bpy.ops.object.mode_set(mode='EDIT')
m = overlay._marks(ob)
check("entering Edit Mode: one look, the same marks", len(looks) == 1 and points(m) == in_object,
      len(looks), points(m))
check("asked again at once: the same entry", overlay._marks(ob) is m and len(looks) == 1)

later()
again = overlay._marks(ob)
check("nothing moved: no look, the same entry (its batches stay)",
      len(looks) == 1 and again is m)

# a marked vertex moves: followed, without looking through the mesh
bm = bmesh.from_edit_mesh(ob.data)
elay = bm.edges.layers.int[layer.edge_attr]
v = next(e for e in bm.edges if e[elay]).verts[0]
before = np.array(m["edges"][0][0])
v.co.z -= 0.05
bmesh.update_edit_mesh(ob.data, loop_triangles=False, destructive=False)
later()
moved = overlay._marks(ob)
check("a moved vertex is followed without a look",
      len(looks) == 1 and not np.array_equal(moved["edges"][0][0], before)
      and points(moved) == in_object)

# no UV marks unless the UV editor asks; then they stay
check("no UV marks for the 3D view", not any(pts for pts, _c in moved["edges_uv"]))
uv = overlay._marks(ob, uv=True)
check("UV marks when asked, without a look",
      any(pts for pts, _c in uv["edges_uv"]) and len(looks) == 1)
n_uv = len(uv_work)
later()
check("and kept for the next reads", any(pts for pts, _c in overlay._marks(ob)["edges_uv"]))
check("the 3D view alone does no UV work", len(uv_work) == n_uv == 1, len(uv_work))

# flipped normals: the marks are lifted to the new outside, without a look
bm = bmesh.from_edit_mesh(ob.data)
before = np.array(overlay._marks(ob)["edges"][0][0])
bmesh.ops.reverse_faces(bm, faces=bm.faces[:])
bm.normal_update()
bmesh.update_edit_mesh(ob.data, loop_triangles=False, destructive=False)
later()
flipped = np.array(overlay._marks(ob)["edges"][0][0])
far = float(np.abs(flipped - before).max())
check("flipped normals move the lift, without a look",
      len(looks) == 1 and 1.5 * overlay.LIFT < far < 2.5 * overlay.LIFT, len(looks), far)

# an edge unmarked by something else (the numbers of elements stay): noticed
bm = bmesh.from_edit_mesh(ob.data)
elay = bm.edges.layers.int[layer.edge_attr]
gone = next(e for e in bm.edges if e[elay])
gone[elay] = 0
bmesh.update_edit_mesh(ob.data, loop_triangles=False, destructive=False)
later()
m = overlay._marks(ob)
check("an edge unmarked elsewhere: one more look, one edge fewer",
      len(looks) == 2 and points(m) == in_object - 2, len(looks), points(m))
gone[elay] = 1
bmesh.update_edit_mesh(ob.data, loop_triangles=False, destructive=False)
overlay.invalidate(ob)
overlay._marks(ob)
looks.clear()
looks.append("back")

# the mesh's elements change: one look
bm = bmesh.from_edit_mesh(ob.data)
bmesh.ops.subdivide_edges(bm, edges=[next(e for e in bm.edges if not e[elay])], cuts=1)
bmesh.update_edit_mesh(ob.data)
later()
overlay._marks(ob)
check("a change of the mesh's elements: one more look", len(looks) == 2, len(looks))

# the add-on's own edit: read at once, not after EDIT_REFRESH
with bpy.context.temp_override(active_object=ob, object=ob):
    bpy.ops.stitch_gen.path_clear()
m = overlay._marks(ob)
check("Clear Edges shows at once", points(m) == 0 and len(looks) == 3, points(m), len(looks))

# another BMesh with the marks back (as undoing Clear Edges gives), the entry
# without marks still there: it looks again instead of showing none
n = len(looks)
bpy.ops.object.mode_set(mode='OBJECT')
bm = bmesh.new()
bm.from_mesh(ob.data)
elay = bm.edges.layers.int[layer.edge_attr]
for e in bm.edges:
    if e.is_boundary and all(v.co.z < -0.265 for v in e.verts):
        e[elay] = 1
bm.to_mesh(ob.data)
bm.free()
bpy.ops.object.mode_set(mode='EDIT')
later()
m = overlay._marks(ob)
check("another BMesh: looks again, the marks are back", len(looks) == n + 1 and points(m) > 0,
      len(looks) - n, points(m))
bpy.ops.object.mode_set(mode='OBJECT')

print("ALL PASS" if not fails else f"FAILED: {fails}")
