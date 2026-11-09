"""Screenshot the corner overlay in the 3D view and the UV editor.

blender --factory-startup result.blend -P overlay_shot.py -- <out_prefix>
"""
import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import rizum_pattern_masks as sg  # noqa: E402

prefix = sys.argv[sys.argv.index("--") + 1]
sg.register()
log = []


def area3d():
    return [a for a in bpy.context.screen.areas if a.type in ('VIEW_3D', 'IMAGE_EDITOR')][0]


def setup():
    ob = bpy.data.objects["Skirt"]
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    area = area3d()
    win = [r for r in area.regions if r.type == 'WINDOW'][0]
    with bpy.context.temp_override(area=area, region=win):
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='DESELECT')
        bpy.ops.view3d.view_axis(type='FRONT')
        bpy.ops.view3d.view_all()
    area.spaces.active.region_3d.view_distance *= 0.55
    return None


def shot3d():
    area = area3d()
    with bpy.context.temp_override(area=area):
        bpy.ops.screen.screenshot_area(filepath=prefix + "_3d.png")
    area.type = 'IMAGE_EDITOR'
    area.ui_type = 'UV'
    return None


def shot_uv():
    area = area3d()
    win = [r for r in area.regions if r.type == 'WINDOW'][0]
    with bpy.context.temp_override(area=area, region=win):
        bpy.ops.image.view_all(fit_view=True)
    return None


def shot_uv2():
    area = area3d()
    with bpy.context.temp_override(area=area):
        bpy.ops.screen.screenshot_area(filepath=prefix + "_uv.png")
    print("OVERLAY_SHOTS_DONE")
    bpy.ops.wm.quit_blender()


for i, fn in enumerate((setup, shot3d, shot_uv, shot_uv2)):
    bpy.app.timers.register(fn, first_interval=1.5 + i * 1.5)
