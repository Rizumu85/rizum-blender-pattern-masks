"""The three mask backgrounds: Black (white on black), White (black on
white, for Clip Studio's Convert Brightness to Opacity) and Transparent
(white, the mask in the alpha channel). The setting keeps the older
``transparent`` flag working. A line art layer is baked (computed per texel,
the same every time; a Cycles stitch bake has noise).

blender -b --factory-startup skirt_test.blend -P background_test.py -- <out_dir>
"""
import os
import sys

import bpy
import bmesh
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import rizum_pattern_masks as sg  # noqa: E402

out_dir = sys.argv[sys.argv.index("--") + 1]
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
s.live = False
s.resolution = '1024'
s.samples = 4
s.device = 'CPU'
bpy.ops.object.mode_set(mode='EDIT')
bm = bmesh.from_edit_mesh(ob.data)
for e in bm.edges:
    e.select_set(False)
for e in bm.edges:
    if e.is_boundary and all((ob.matrix_world @ v.co).z < -0.265 for v in e.verts):
        e.select_set(True)
bmesh.update_edit_mesh(ob.data)
bpy.ops.object.mode_set(mode='OBJECT')
bpy.ops.stitch_gen.line_add()
s.lines[s.line_index].width = 2.0
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.stitch_gen.path_add()
bpy.ops.object.mode_set(mode='OBJECT')

# the switch and the stored flags agree, both ways
for bg, tr, inv in (('BLACK', False, False), ('WHITE', False, True), ('TRANSPARENT', True, False)):
    s.background = bg
    check(f"{bg}: flags", (s.transparent, s.invert) == (tr, inv), s.transparent, s.invert)
s.background = 'BLACK'
s.transparent = True                  # a file from before: only the old flag
check("old flag reads as Transparent", s.background == 'TRANSPARENT')

px = {}
for bg in ('BLACK', 'WHITE', 'TRANSPARENT'):
    s.background = bg
    d = os.path.join(out_dir, bg.lower())
    os.makedirs(d, exist_ok=True)
    s.output_dir = d
    r = bpy.ops.stitch_gen.bake()
    path = os.path.join(d, "Skirt_Skirt_Cloth_line.png")
    img = bpy.data.images.load(path)
    img.colorspace_settings.name = 'Non-Color'
    a = np.empty(img.size[0] * img.size[1] * 4, np.float32)
    img.pixels.foreach_get(a)
    px[bg] = a.reshape(-1, 4)
    check(f"{bg}: baked", r == {'FINISHED'} and os.path.isfile(path), r)

b, w, t = px['BLACK'], px['WHITE'], px['TRANSPARENT']
mark = b[:, 0] > 0.5
check("black: white marks on black", mark.any() and np.median(b[~mark, 0]) < 0.01, int(mark.sum()))
check("white: the same marks, inverted", np.allclose(w[:, 0], 1.0 - b[:, 0], atol=2e-3),
      float(np.abs(w[:, 0] - (1.0 - b[:, 0])).max()))
check("white: opaque", np.allclose(w[:, 3], 1.0))
check("transparent: the marks are the alpha", np.allclose(t[:, 3], b[:, 0], atol=2e-3)
      and np.allclose(t[:, 0], 1.0))

print("ALL PASS" if not fails else f"FAILED: {fails}")
