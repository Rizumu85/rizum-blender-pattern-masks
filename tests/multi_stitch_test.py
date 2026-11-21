"""Several stitch layers on one object (0.4.0).

Two stitch layers, each with its own edges and settings: the hem dashed, the
waist a zigzag. Each makes its own stitches, shows in its own color in the
one stitch preview and bakes to its own mask. The object's stitch settings
(presets, scripts) stand for the layer selected in the list; a value set
before there is a stitch layer goes to the first one.

blender -b --factory-startup skirt_test.blend -P multi_stitch_test.py -- <out_dir>
"""
import os
import sys

import bpy
import bmesh
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import rizum_pattern_masks as sg  # noqa: E402
from rizum_pattern_masks import bake, layers, rebuild  # noqa: E402
from tests import _preview as pv  # noqa: E402

out_dir = sys.argv[sys.argv.index("--") + 1]
os.makedirs(out_dir, exist_ok=True)
for f in os.listdir(out_dir):
    if f.endswith(".png"):
        os.remove(os.path.join(out_dir, f))
sg.register()
fails = []


def check(name, ok, *info):
    print(" ".join(["RESULT", "PASS" if ok else "FAIL", name] + [str(x) for x in info]))
    if not ok:
        fails.append(name)


def mark(ob, pick):
    """Select the boundary edges whose vertices all pass pick(z), then +."""
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(ob.data)
    for e in bm.edges:
        e.select_set(False)
    for v in bm.verts:
        v.select_set(False)
    for e in bm.edges:
        if e.is_boundary and all(pick((ob.matrix_world @ v.co).z) for v in e.verts):
            e.select_set(True)
    bmesh.update_edit_mesh(ob.data)
    bpy.ops.stitch_gen.path_add()
    bpy.ops.object.mode_set(mode='OBJECT')


ob = bpy.data.objects["Skirt"]
vl = bpy.context.view_layer
for o in vl.objects:
    o.select_set(False)
ob.select_set(True)
vl.objects.active = ob
s = ob.stitch_gen
s.live = False
s.output_dir = out_dir
s.resolution = '1024'
s.samples = 4
s.device = 'CPU'

# a setting made before there is a stitch layer goes to the first one
s.width = 0.7
bpy.ops.stitch_gen.stitch_add()
hem = s.lines[s.line_index]
check("first stitch layer takes the earlier setting", abs(hem.thread_width - 0.7) < 1e-6,
      hem.thread_width)
check("first stitch layer named stitch", hem.name == "stitch", hem.name)
mark(ob, lambda z: z < -0.265)

bpy.ops.stitch_gen.stitch_add()
check("a second stitch layer can be added", len(layers._stitch_items(s)) == 2, len(s.lines))
waist = s.lines[s.line_index]
check("second stitch layer has its own name and edges",
      waist.name == "stitch2" and waist.edge_attr != hem.edge_attr, waist.name, waist.edge_attr)
waist.style = 'ZIGZAG'
waist.thread_width = 0.5
waist.color = (0.1, 0.4, 1.0, 1.0)
mark(ob, lambda z: z > -0.01)

data = sg.regenerate(ob, bpy.context.scene)
check("each stitch layer makes its own stitches",
      len(data.stitches) == 2 and all(r.dash_count > 0 for _a, r in data.stitches),
      [r.dash_count for _a, r in data.stitches])
zs = [np.asarray(r.co)[:, 2].mean() for _a, r in data.stitches]
check("on its own edges (hem low, waist high)", zs[0] < -0.2 and zs[1] > -0.05, zs)
check("the layers' counts", hem.dash_count > 0 and waist.dash_count > 0,
      hem.dash_count, waist.dash_count)
check("both layers in the preview", pv.stitch_layers(ob) == [hem.edge_attr, waist.edge_attr],
      pv.stitch_layers(ob))
cols = rebuild._layer_colors(ob)
check("each in its own color", np.allclose(cols[waist.edge_attr][:3], (0.1, 0.4, 1.0), atol=1e-4),
      cols)

# the object's stitch settings stand for the selected stitch layer
s.line_index = 0
s.length = 5.5
check("object settings set the selected stitch layer",
      abs(hem.length - 5.5) < 1e-6 and abs(waist.length - 4.0) < 1e-6, hem.length, waist.length)
s.line_index = 1
check("and read it", s.style == 'ZIGZAG' and abs(s.width - 0.5) < 1e-6, s.style, s.width)

# hiding one leaves the other
waist.enabled = False
data = sg.regenerate(ob, bpy.context.scene)
check("a hidden stitch layer makes nothing", len(data.stitches) == 1, len(data.stitches))
waist.enabled = True

# the bake: one mask per stitch layer
ob.select_set(True)
res = bpy.ops.stitch_gen.bake()
pngs = sorted(f for f in os.listdir(out_dir) if f.endswith(".png"))
check("bake finished", res == {'FINISHED'}, res)
stitch = [f for f in pngs if f.endswith("_stitch.png")]
stitch2 = [f for f in pngs if f.endswith("_stitch2.png")]
check("a mask per stitch layer", stitch and stitch2, pngs)
check("temporary bake objects removed",
      not [o for o in bpy.data.objects if o.name.startswith(bake.TMP)]
      and not [m for m in bpy.data.materials if m.name.startswith(bake.TMP)])
if stitch and stitch2:
    def gray(name):
        img = bpy.data.images.load(os.path.join(out_dir, name))
        img.colorspace_settings.name = "Non-Color"
        w, h = img.size
        px = np.empty(w * h * 4, np.float32)
        img.pixels.foreach_get(px)
        return px.reshape(h, w, 4)[:, :, 0]
    pa, pb = gray(stitch[0]), gray(stitch2[0])
    both = ((pa > 0.5) & (pb > 0.5)).sum()
    check("the masks hold different stitches", (pa > 0.5).sum() > 0 and (pb > 0.5).sum() > 0
          and both < 0.05 * min((pa > 0.5).sum(), (pb > 0.5).sum()),
          (pa > 0.5).sum(), (pb > 0.5).sum(), both)

# removing a stitch layer takes its edges and its part of the preview
s.line_index = 1
attr = waist.edge_attr
bpy.ops.stitch_gen.line_remove()
check("stitch layer removed with its edges",
      len(layers._stitch_items(s)) == 1 and attr not in ob.data.attributes, attr)
sg.regenerate(ob, bpy.context.scene)
check("preview back to one layer", len(pv.stitch_layers(ob)) == 1, pv.stitch_layers(ob))

print("ALL PASS" if not fails else f"FAILED: {fails}")
