"""Separate stitch edges and line art edges.

Marks the hem as stitch edges and the waist (top border) as line art edges, then
checks: the stitches stay on the hem only; a line layer that refers to the stitches
covers both borders, one that does not covers only the waist.

blender -b --factory-startup skirt_test.blend -P edge_sets_test.py -- <out_dir>
"""
import os
import sys

import bpy
import bmesh
import numpy as np

out_dir = sys.argv[sys.argv.index("--") + 1]
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import rizum_pattern_masks as sg  # noqa: E402
from rizum_pattern_masks import core, rebuild  # noqa: E402
from tests import _preview as pv  # noqa: E402

sg.register()
os.makedirs(out_dir, exist_ok=True)
for f in os.listdir(out_dir):
    if f.endswith(".png"):
        os.remove(os.path.join(out_dir, f))
ob = bpy.data.objects["Skirt"]
bpy.context.view_layer.objects.active = ob
ob.select_set(True)
s = ob.stitch_gen
s.live = False


def mark(row, pick):
    """Mark edges on the layer list row ``row`` (0 = the stitch row)."""
    s.line_index = row
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(ob.data)
    for e in bm.edges:
        e.select_set(e.is_boundary and pick([(ob.matrix_world @ v.co).z for v in e.verts]))
    bm.select_flush_mode()
    bmesh.update_edit_mesh(ob.data)
    bpy.ops.stitch_gen.path_add()
    bpy.ops.object.mode_set(mode='OBJECT')


bpy.ops.stitch_gen.stitch_add()
mark(0, lambda zs: all(z < -0.265 for z in zs))
print("RESULT rows after first marking", [(l.name, l.edge_attr) for l in s.lines])
sg.regenerate(ob)
n0 = s.dash_count
bpy.ops.stitch_gen.line_add()
s.lines[1].ref_attr = core.PATH_ATTR            # also follows the stitch edges
mark(1, lambda zs: all(z > -0.01 for z in zs))
print("RESULT layers after marking line edges", [l.name for l in s.lines])
sg.regenerate(ob)
print("RESULT stitches before/after line edges", n0, s.dash_count)
stitch_z = pv.stitch_co(ob)[:, 2]
print("RESULT stitch z range %.3f..%.3f" % (stitch_z.min(), stitch_z.max()))
bpy.ops.stitch_gen.line_add()
print("RESULT new layer edges", s.lines[2].edge_attr, "own edges before marking",
      len(core.read_path_edges(ob.data, s.lines[2].edge_attr)))
s.lines[2].ref_attr = ""                         # follows only its own edges
mark(2, lambda zs: all(z > -0.01 for z in zs))     # line2's own edges: the waist
s.lines[2].color = (1.0, 0.0, 0.0, 1.0)
sg.regenerate(ob)
print("RESULT line layers shown", pv.line_faces(ob),
      "colors", {k: tuple(round(c, 2) for c in v[:3])
                 for k, v in rebuild._layer_colors(ob).items()})
from rizum_pattern_masks import overlay  # noqa: E402
print("RESULT overlay shown", [a for a, _, _ in overlay._shown(ob)])
s.lines[1].show_marks = False
print("RESULT overlay shown, line marks hidden", [a for a, _, _ in overlay._shown(ob)])
s.lines[1].show_marks = True
lz = pv.line_co(ob)[:, 2]
print("RESULT line preview z: below hem-ish %d, near waist %d" % ((lz < -0.2).sum(), (lz > -0.05).sum()))
s.lines[1].enabled = False                              # only line2 left
sg.regenerate(ob)
lz = pv.line_co(ob)[:, 2]
print("RESULT line off: below hem-ish %d, near waist %d" % ((lz < -0.2).sum(), (lz > -0.05).sum()))
print("RESULT line off layers", pv.line_faces(ob))
s.lines[1].enabled = True
s.output_dir = out_dir
s.resolution = '2048'
print("RESULT bake", bpy.ops.stitch_gen.bake())
for f in sorted(os.listdir(out_dir)):
    if not f.endswith(".png"):
        continue
    img = bpy.data.images.load(os.path.join(out_dir, f))
    img.colorspace_settings.name = "Non-Color"
    r = img.size[0]
    px = np.empty(r * r * 4, np.float32)
    img.pixels.foreach_get(px)
    m = px.reshape(r, r, 4)[:, :, 0] > 0.5
    ys = np.nonzero(m.any(1))[0]
    print("RESULT", f, "px", int(m.sum()), "rows %d..%d" % (ys.min(), ys.max()) if len(ys) else "")
if len(sys.argv) > sys.argv.index("--") + 2:          # keep the result for screenshots
    bpy.ops.wm.save_as_mainfile(filepath=sys.argv[sys.argv.index("--") + 2], copy=True)
