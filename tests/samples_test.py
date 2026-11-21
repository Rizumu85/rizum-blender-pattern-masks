"""How much the Cycles bake samples change the stitch mask, and what they cost.

Bakes the stitches of the file's object at several sample counts and compares
each mask with the highest count.

blender -b --factory-startup <result.blend> -P samples_test.py -- <object> <out_dir> [res]
"""
import os
import sys
import time

import bpy
import numpy as np

argv = sys.argv[sys.argv.index("--") + 1:]
obj_name, out_root = argv[0], argv[1]
res = argv[2] if len(argv) > 2 else '4096'
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import rizum_pattern_masks as sg  # noqa: E402
from rizum_pattern_masks import layers  # noqa: E402

sg.register()
ob = bpy.data.objects[obj_name]
bpy.context.view_layer.objects.active = ob
ob.select_set(True)
s = ob.stitch_gen
for l in layers._line_items(s):
    l.enabled = False                    # stitches only
s.resolution = res
s.device = 'CPU'
s.cpu_usage = 100


def load(path):
    img = bpy.data.images.load(path)
    img.colorspace_settings.name = "Non-Color"
    r = img.size[0]
    px = np.empty(r * r * 4, np.float32)
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    return px.reshape(r, r, 4)[:, :, 0]


masks = {}
for n in (1, 2, 4, 8, 16, 64):
    d = os.path.join(out_root, f"s{n}")
    os.makedirs(d, exist_ok=True)
    s.output_dir = d
    s.samples = n
    t = time.perf_counter()
    r = bpy.ops.stitch_gen.bake()
    dt = time.perf_counter() - t
    f = [x for x in os.listdir(d) if x.endswith("_stitch.png")][0]
    masks[n] = load(os.path.join(d, f))
    print(f"RESULT samples {n} {r} time {dt:.1f}s")
ref = masks[64]
edge = (ref > 0.02) & (ref < 0.98)         # the antialiased border texels
for n, m in masks.items():
    diff = np.abs(m - ref)
    print(f"RESULT samples {n}: covered {(m > 0.5).sum()} vs {(ref > 0.5).sum()}, "
          f"mean |diff| on border {diff[edge].mean():.4f}, max {diff.max():.3f}, "
          f"texels off by >0.1: {(diff > 0.1).sum()}")
