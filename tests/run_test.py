"""Headless test: mark the hem border, generate stitches, bake the mask.

blender -b <skirt_test.blend> -P run_test.py -- <out_dir> [resolution]
"""
import os
import sys
import time

import bpy
import bmesh

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import pattern_masks as sg  # noqa: E402

args = sys.argv[sys.argv.index("--") + 1:]
out_dir = args[0]
res = args[1] if len(args) > 1 else "4096"
os.makedirs(out_dir, exist_ok=True)

sg.register()
ob = bpy.data.objects["Skirt"]
bpy.context.view_layer.objects.active = ob
ob.select_set(True)

s = ob.stitch_gen
s.live = False
s.resolution = res
s.output_dir = out_dir

# Select the hem border (open edges below the last quad row), as a user would.
bpy.ops.object.mode_set(mode='EDIT')
bm = bmesh.from_edit_mesh(ob.data)
for e in bm.edges:
    e.select_set(e.is_boundary and all(v.co.z < -0.265 for v in e.verts))
bm.select_flush_mode()
bmesh.update_edit_mesh(ob.data)
bpy.ops.stitch_gen.path_add()
bpy.ops.object.mode_set(mode='OBJECT')

for k, v in dict(inset=4.0, smooth=2.0, length=4.0, gap=2.0, width=1.2,
                 roundness=1.0).items():
    setattr(s, k, v)

t0 = time.perf_counter()
data = sg.regenerate(ob)
t1 = time.perf_counter()
s.gap = 2.5       # dash-only change (centerline cached)
data = sg.regenerate(ob)
t2 = time.perf_counter()
print(f"STATUS={s.status!r} dashes={data.dash_count} width_px={data.width_px:.2f} "
      f"gap_px={data.gap_px:.2f} lift={data.lift*1000:.3f}mm border_hits={data.border_hits} "
      f"first={1000*(t1-t0):.0f}ms dash_only={1000*(t2-t1):.0f}ms "
      f"verts={len(data.co)} band_polys={len(data.band_polys)}")

t3 = time.perf_counter()
paths = sg.bake.bake_masks(bpy.context, ob, s.ribbon, data, s)
print(f"BAKE {1000*(time.perf_counter()-t3):.0f}ms -> {paths}")
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out_dir, "result.blend"), copy=True)
