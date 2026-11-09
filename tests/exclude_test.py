"""Taking edges out of what a layer gets from its reference.

The stitches mark the hem and refer to a line art layer on the waist; then
− with half the waist selected takes that half out of the stitches only:
the stitches leave it, the line layer keeps the whole waist. Select picks
the stitches' edges as they end up; + brings an edge back; × clears both;
the overlay shows the taken-out edges for the selected layer.

blender -b --factory-startup skirt_test.blend -P exclude_test.py
"""
import os
import sys

import bpy
import bmesh
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import rizum_pattern_masks as sg  # noqa: E402
from rizum_pattern_masks import core, overlay  # noqa: E402

sg.register()
ob = bpy.data.objects["Skirt"]
bpy.context.view_layer.objects.active = ob
ob.select_set(True)
s = ob.stitch_gen
s.live = False
fails = []


def check(name, ok, *info):
    print("RESULT", "PASS" if ok else "FAIL", name, *info)
    if not ok:
        fails.append(name)


def edit(row, pick, op):
    """Select boundary edges whose world-space verts pass ``pick`` and run op
    on layer ``row``."""
    s.line_index = row
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(ob.data)
    for e in bm.edges:                 # clear first: deselecting an edge after
        e.select_set(False)            # selecting its neighbour would drop their shared vertex
    for v in bm.verts:
        v.select_set(False)
    for e in bm.edges:
        if e.is_boundary and pick([ob.matrix_world @ v.co for v in e.verts]):
            e.select_set(True)
    bm.select_mode = {'EDGE'}
    bm.select_flush_mode()
    bmesh.update_edit_mesh(ob.data)
    r = op()
    bpy.ops.object.mode_set(mode='OBJECT')
    return r


HEM = lambda P: all(p.z < -0.265 for p in P)                     # noqa: E731
WAIST = lambda P: all(p.z > -0.01 for p in P)                    # noqa: E731
HALF = lambda P: WAIST(P) and all(p.x > 0.001 for p in P)        # noqa: E731

bpy.ops.stitch_gen.stitch_add()
edit(0, HEM, bpy.ops.stitch_gen.path_add)
bpy.ops.stitch_gen.line_add()
edit(1, WAIST, bpy.ops.stitch_gen.path_add)
st, line = s.lines[0], s.lines[1]
st.ref_attr = line.edge_attr
sg.regenerate(ob, create=True)
n_all = s.dash_count
waist_right = lambda o: int(sum(1 for v in o.data.vertices                          # noqa: E731
                                if v.co.z > -0.1 and v.co.x > 0.02))

check("stitches on the whole waist", waist_right(s.ribbon) > 0, n_all)

# take the right half of the waist out of the stitches
edit(0, HALF, bpy.ops.stitch_gen.path_remove)
out = core.read_path_edges(ob.data, core.PATH_ATTR, -1)
own = core.read_path_edges(ob.data, core.PATH_ATTR)
check("taken-out edges marked -1 on the stitches", len(out) > 0 and len(own) > 0,
      len(out), len(own))
check("line layer untouched", len(core.read_path_edges(ob.data, line.edge_attr, -1)) == 0
      and len(core.read_path_edges(ob.data, line.edge_attr)) == 64)
sg.regenerate(ob, create=True)
check("stitches leave that half", waist_right(s.ribbon) == 0 and 0 < s.dash_count < n_all,
      waist_right(s.ribbon), s.dash_count)
lz = [v for v in s.line_preview.data.vertices if v.co.z > -0.1 and v.co.x > 0.02]
check("line keeps the whole waist", len(lz) > 0, len(lz))

# overlay: the selected layer's taken-out edges in red
s.line_index = 0
reds = [a for a, c, sign in overlay._shown(ob) if sign < 0]
check("overlay shows taken-out edges", reds == [core.PATH_ATTR], reds)

# Select: what the stitches end up with (hem + left half of the waist)
s.line_index = 0
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='DESELECT')
bpy.ops.stitch_gen.path_select()
bm = bmesh.from_edit_mesh(ob.data)
sel = [e for e in bm.edges if e.select]
right = [e for e in sel if all((ob.matrix_world @ v.co).z > -0.01 and (ob.matrix_world @ v.co).x > 0.001
                               for v in e.verts)]
hem = [e for e in sel if all((ob.matrix_world @ v.co).z < -0.265 for v in e.verts)]
check("select: hem and left waist, not the right", len(hem) > 0 and len(right) == 0
      and len(sel) > len(hem), len(sel), len(hem), len(right))
bpy.ops.object.mode_set(mode='OBJECT')

# + on one taken-out edge brings it back
first = None


def one(P):
    global first
    if HALF(P) and first is None:
        first = True
        return True
    return False


edit(0, one, bpy.ops.stitch_gen.path_add)
check("+ brings an edge back", len(core.read_path_edges(ob.data, core.PATH_ATTR, -1)) == len(out) - 1)

# − on an own edge (not from the reference) just clears it
edit(0, lambda P: HEM(P) and all(p.x > 0.001 for p in P), bpy.ops.stitch_gen.path_remove)
check("− on own edges clears them",
      len(core.read_path_edges(ob.data, core.PATH_ATTR, -1)) == len(out) - 1
      and len(core.read_path_edges(ob.data, core.PATH_ATTR)) < len(own) + 1)

# × clears own edges and taken-out marks
s.line_index = 0
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.stitch_gen.path_clear('EXEC_DEFAULT')
bpy.ops.object.mode_set(mode='OBJECT')
check("× clears both", len(core.read_path_edges(ob.data, core.PATH_ATTR)) == 0
      and len(core.read_path_edges(ob.data, core.PATH_ATTR, -1)) == 0)
sg.regenerate(ob, create=True)
check("after ×: stitches follow the whole referred waist", waist_right(s.ribbon) > 0)

print("RESULT", "ALL PASS" if not fails else "FAILED: " + ", ".join(fails))
