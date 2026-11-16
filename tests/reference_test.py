"""References between layers.

Marks the hem as stitch edges and the waist as a line art layer's edges, then
checks: the stitches follow the waist too once they refer to the line layer;
a line layer referring to the stitches covers the hem; references that loop
back stop; a grid with no edges of its own works from its reference; the
eyedropper takes the clicked layer and keeps the edited one selected;
removing a layer clears references to it; a 0.3.0 line layer with Include
Stitch Edges on comes to refer to the stitches; and the bake sees it all.

blender -b --factory-startup skirt_test.blend -P reference_test.py -- <out_dir>
"""
import os
import sys

import bpy
import bmesh
import numpy as np

out_dir = sys.argv[sys.argv.index("--") + 1]
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import rizum_pattern_masks as sg  # noqa: E402
from tests import _preview as pv  # noqa: E402
from rizum_pattern_masks import core  # noqa: E402

sg.register()
os.makedirs(out_dir, exist_ok=True)
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


def mark(row, pick):
    s.line_index = row
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(ob.data)
    for e in bm.edges:
        e.select_set(e.is_boundary and pick([(ob.matrix_world @ v.co).z for v in e.verts]))
    bm.select_flush_mode()
    bmesh.update_edit_mesh(ob.data)
    bpy.ops.stitch_gen.path_add()
    bpy.ops.object.mode_set(mode='OBJECT')


def zs(o):
    return np.array([v.co.z for v in o.data.vertices]) if o is not None else np.zeros(0)


HEM, WAIST = (lambda z: all(v < -0.265 for v in z)), (lambda z: all(v > -0.01 for v in z))

bpy.ops.stitch_gen.stitch_add()
mark(0, HEM)
bpy.ops.stitch_gen.line_add()
mark(1, WAIST)
st, line = s.lines[0], s.lines[1]
check("new layer refers to nothing", line.ref_attr == "")
sg.regenerate(ob)
n_hem = s.dash_count
z = pv.line_co(ob)[:, 2]
check("line alone: waist only", len(z) and z.min() > -0.1, round(float(z.min()), 3))

# stitches refer to the line layer: stitches along the waist too
st.ref_attr = line.edge_attr
sg.regenerate(ob)
z = pv.stitch_co(ob)[:, 2]
check("stitches follow the line's edges", s.dash_count > n_hem and z.max() > -0.1,
      n_hem, s.dash_count)
st.ref_attr = ""

# line refers to the stitches: covers the hem too
line.ref_attr = core.PATH_ATTR
sg.regenerate(ob)
z = pv.line_co(ob)[:, 2]
check("line follows the stitch edges", z.min() < -0.2 and z.max() > -0.1)

# a loop of references stops
st.ref_attr = line.edge_attr
check("loop", sg._edge_set(s, st) == sg._edge_set(s, line) ==
      tuple(sorted((core.PATH_ATTR, line.edge_attr))), sg._edge_set(s, st))
sg.regenerate(ob)
check("loop regenerates", s.status == "", s.status)
st.ref_attr = ""

# a chain: grid -> line -> stitches
bpy.ops.stitch_gen.grid_add()
g = s.lines[s.line_index]
g.ref_attr = line.edge_attr
check("chain", sg._edge_set(s, g) == tuple(sorted((core.PATH_ATTR, line.edge_attr, g.edge_attr))),
      sg._edge_set(s, g))
line.ref_attr = ""
g.grid_cell = 20.0
sg.regenerate(ob)
check("grid with no own edges, from its reference", pv.grid_faces(ob) > 0, pv.grid_faces(ob))

# eyedropper: picking the stitch row while the line layer is edited
s.line_index = 1
sg._PICK.update(ob=ob.name_full, attr=line.edge_attr, done=False, cancel=False)
s.line_index = 0                                    # the click in the list
check("eyedropper sets the reference", line.ref_attr == core.PATH_ATTR and s.line_index == 1
      and sg._PICK.get("done"), line.ref_attr, s.line_index)
sg._PICK.clear()

# bake: the line layer (waist + hem) and the grid
s.output_dir = out_dir
s.resolution = '1024'
for f in os.listdir(out_dir):
    if f.endswith(".png"):
        os.remove(os.path.join(out_dir, f))
check("bake count", sg._bake_count(ob) == 3, sg._bake_count(ob))
print("RESULT bake", bpy.ops.stitch_gen.bake())
for f in sorted(os.listdir(out_dir)):
    if f.endswith(".png"):
        img = bpy.data.images.load(os.path.join(out_dir, f))
        img.colorspace_settings.name = "Non-Color"
        r = img.size[0]
        px = np.empty(r * r * 4, np.float32)
        img.pixels.foreach_get(px)
        m = px.reshape(r, r, 4)[:, :, 0] > 0.5
        print("RESULT", f, "px", int(m.sum()))

# removing the line layer clears the grid's reference to it
s.line_index = 1
bpy.ops.stitch_gen.line_remove()
g = s.lines[s.line_index] if sg._is_grid(s.lines[s.line_index]) else s.lines[-1]
check("removed layer's references cleared", g.ref_attr == "", g.ref_attr)

# a 0.3.0 file: Include Stitch Edges on -> refers to the stitches
bpy.ops.stitch_gen.line_add()
old = s.lines[s.line_index]
old.ref_attr = ""
old.property_unset("include_stitch")               # default: on
off = s.lines.add()
off.edge_attr, off.include_stitch = "stitch_line_9", False
s.ui_version = 1
sg._ensure_layers(ob)
check("0.3.0 file upgraded", s.ui_version == sg.UI_VERSION and old.ref_attr == core.PATH_ATTR
      and off.ref_attr == "", old.ref_attr, off.ref_attr)

print("RESULT", "ALL PASS" if not fails else "FAILED: " + ", ".join(fails))
