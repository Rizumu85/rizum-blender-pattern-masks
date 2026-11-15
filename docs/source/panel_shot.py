"""Screenshot Blender with the demo skirt and the add-on's panel, for the
extension listing (with Blender's user folders in a scratch folder):

blender --enable-event-simulate <demo.blend> -P docs/source/panel_shot.py -- <out.png> <layer> [tab_x tab_y]

Scripts can't switch the sidebar tab: pass the window position of the
"Pattern Masks" tab (origin bottom left; find it on a first shot without).
"""
import os
import sys

import bpy

argv = sys.argv[sys.argv.index("--") + 1:]
out = argv[0]
layer = argv[1]
tab = (int(argv[2]), int(argv[3])) if len(argv) > 3 else None
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import rizum_pattern_masks as sg  # noqa: E402

sg.register()
bpy.context.preferences.view.language = 'en_US'
ob = bpy.data.objects["Skirt"]


def setup():
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    s = ob.stitch_gen
    s.line_index = next(i for i, l in enumerate(s.lines) if l.name == layer)
    # plain cream cloth (the demo material shows the baked result); previews on
    # top. Materials always have nodes since Blender 5.0: colour the Principled one.
    cloth = (0.86, 0.80, 0.70, 1.0)
    mat = bpy.data.materials.new("cloth_plain")
    mat.diffuse_color = cloth
    if mat.node_tree is not None:
        for n in mat.node_tree.nodes:
            if n.type == 'BSDF_PRINCIPLED':
                n.inputs["Base Color"].default_value = cloth
                n.inputs["Roughness"].default_value = 0.8
    ob.material_slots[0].material = mat
    for o in bpy.data.objects:
        if o.type in {'CAMERA', 'LIGHT'}:
            o.hide_set(True)
    s.stitch_color = (0.91, 0.42, 0.10, 1.0)
    s.output_dir = "//masks/"                 # no local paths in the shot
    os.makedirs(bpy.path.abspath(s.output_dir), exist_ok=True)
    for l in s.lines:
        if l.name == "gingham":
            l.color = (0.10, 0.15, 0.26, 1.0)
        elif l.name == "waistband":
            l.color = (0.13, 0.19, 0.32, 1.0)
        elif l.name == "trim":
            l.color = (0.03, 0.03, 0.04, 1.0)
    cam = bpy.data.objects["Cam"]
    w = bpy.context.window_manager.windows[0]
    for area in w.screen.areas:
        if area.type != 'VIEW_3D':
            continue
        sp = area.spaces.active
        sp.show_region_ui = True
        sp.shading.type = 'MATERIAL'           # the grid preview draws its squares in a shader
        sp.overlay.show_floor = False
        sp.overlay.show_axis_x = sp.overlay.show_axis_y = False
        win = [r for r in area.regions if r.type == 'WINDOW'][0]
        ui = [r for r in area.regions if r.type == 'UI'][0]
        r3d = sp.region_3d
        r3d.view_perspective = 'PERSP'
        r3d.view_rotation = cam.matrix_world.to_quaternion()
        r3d.view_location = (0.0, 0.0, -0.26)
        r3d.view_distance = 1.15
    sg.regenerate(ob, create=True)
    # a fresh config opens with the first-start splash: Esc closes it, nothing saved
    w.event_simulate(type='MOUSEMOVE', value='NOTHING', x=900, y=700)
    w.event_simulate(type='ESC', value='PRESS')
    w.event_simulate(type='ESC', value='RELEASE')
    if tab is not None:
        for t, v in (('MOUSEMOVE', 'NOTHING'), ('LEFTMOUSE', 'PRESS'), ('LEFTMOUSE', 'RELEASE')):
            w.event_simulate(type=t, value=v, x=tab[0], y=tab[1])
        w.event_simulate(type='MOUSEMOVE', value='NOTHING', x=900, y=700)
    return None


def shot():
    bpy.ops.screen.screenshot(filepath=out)
    print("RESULT shot", out)
    bpy.ops.wm.quit_blender()
    return None


bpy.app.timers.register(setup, first_interval=0.5)
bpy.app.timers.register(shot, first_interval=15.0)       # let Material Preview compile
