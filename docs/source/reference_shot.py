"""Screenshot for the docs' References section: the stitches refer to the
waistband layer, half of the waist is left out of the stitches (red), in
Edit Mode with the stitch row selected.

blender --enable-event-simulate <demo.blend> -P docs/source/reference_shot.py -- <out.png> tab_x tab_y
"""
import os
import sys

import math

import bpy
import bmesh
from mathutils import Euler

argv = sys.argv[sys.argv.index("--") + 1:]
out = argv[0]
tab = (int(argv[1]), int(argv[2]))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import rizum_pattern_masks as sg  # noqa: E402

sg.register()
bpy.context.preferences.view.language = 'en_US'
ob = bpy.data.objects["Skirt"]
s = ob.stitch_gen


def pick(test):
    bm = bmesh.from_edit_mesh(ob.data)
    for e in bm.edges:
        e.select_set(False)
    for v in bm.verts:
        v.select_set(False)
    for e in bm.edges:
        if e.is_boundary and test([ob.matrix_world @ v.co for v in e.verts]):
            e.select_set(True)
    bm.select_mode = {'EDGE'}
    bm.select_flush_mode()
    bmesh.update_edit_mesh(ob.data)


def setup():
    w = bpy.context.window_manager.windows[0]
    area = [a for a in w.screen.areas if a.type == 'VIEW_3D'][0]
    win = [r for r in area.regions if r.type == 'WINDOW'][0]
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    for o in bpy.data.objects:
        if o.type in {'CAMERA', 'LIGHT'}:
            o.hide_set(True)
    s.output_dir = "//masks/"
    s.live = True
    band = next(l for l in s.lines if l.name == "waistband")
    st = s.lines[0]
    st.ref_attr = band.edge_attr
    for l in s.lines:
        l.show_marks = l in (st, band)
    sp = area.spaces.active
    sp.show_region_ui = True
    sp.shading.type = 'MATERIAL'
    mat = ob.active_material                     # plain cloth: the marks and the stitches read on it
    mat.use_nodes = False
    mat.diffuse_color = (0.86, 0.80, 0.70, 1.0)
    s.stitch_color = (0.91, 0.42, 0.10, 1.0)
    sp.overlay.show_floor = False
    sp.overlay.show_axis_x = sp.overlay.show_axis_y = False
    with bpy.context.temp_override(window=w, area=area, region=win):
        bpy.ops.object.mode_set(mode='EDIT')
        s.line_index = 0
        pick(lambda P: all(p.z > -0.001 and p.x > 0.002 for p in P))
        bpy.ops.stitch_gen.path_remove()
        bpy.ops.mesh.select_all(action='DESELECT')
        bpy.ops.object.mode_set(mode='OBJECT')
    for l in s.lines:
        if l.name in ("waistband", "gingham", "trim"):
            l.enabled = False                    # this shot is about the stitches only
    sg.regenerate(ob)
    r3d = sp.region_3d
    r3d.view_perspective = 'PERSP'
    cam = bpy.data.objects["Cam"]
    r3d.view_rotation = Euler((math.radians(42), 0.0, math.radians(28))).to_quaternion()   # down onto the waist
    r3d.view_location = (0.0, 0.0, -0.03)
    r3d.view_distance = 0.55
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
