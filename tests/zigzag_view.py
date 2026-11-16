"""Close-up of the zigzag preview in the viewport (Material Preview).

blender --factory-startup zigzag.blend -P zigzag_view.py -- <out.png> [inset width length height]
"""
import os
import sys

import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import rizum_pattern_masks as sg  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:]
out = argv[0]
vals = [float(v) for v in argv[1:5]] if len(argv) >= 5 else [3.0, 1.2, 4.0, 3.0]
sg.register()


def setup():
    ob = bpy.data.objects["Skirt"]
    s = ob.stitch_gen
    s.live = False
    s.style = 'ZIGZAG'
    s.inset, s.width, s.length, s.zigzag_height = vals
    with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]):
        sg.regenerate(ob, bpy.context.scene)
    from rizum_pattern_masks import preview
    # look at a stretch of the zigzag from the front, close
    co = [Vector(c) for c in preview.geometry(ob)["stitches"][0][1].co.tolist()]
    target = min(co, key=lambda p: abs(p.x - 0.02) + abs(p.z + 0.27) * 3)
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            sp = area.spaces.active
            sp.shading.type = 'MATERIAL'
            sp.overlay.show_overlays = False
            r3 = sp.region_3d
            r3.view_perspective = 'ORTHO'
            r3.view_rotation = Vector((1, 0, 0)).rotation_difference(Vector((1, 0, 0))) @ \
                __import__("mathutils").Euler((1.5708, 0, 0)).to_quaternion()
            r3.view_location = target
            r3.view_distance = 0.03
    return None


def shoot():
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            with bpy.context.temp_override(area=area):
                bpy.ops.screen.screenshot_area(filepath=out)
    bpy.ops.wm.quit_blender()


bpy.app.timers.register(setup, first_interval=1.0)
bpy.app.timers.register(shoot, first_interval=4.0)
