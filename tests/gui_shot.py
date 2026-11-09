"""Open the test result in the GUI, show the Stitch panel, screenshot it, quit.

blender result.blend -P gui_shot.py -- <out.png>
"""
import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pattern_masks as sg  # noqa: E402

out = sys.argv[sys.argv.index("--") + 1]
if os.environ.get("STITCHGEN_LANG"):   # only ever used with an isolated BLENDER_USER_CONFIG
    _v = bpy.context.preferences.view
    _v.language = os.environ["STITCHGEN_LANG"]
    _v.use_translate_interface = _v.use_translate_tooltips = True
sg.VIEW3D_PT_stitch_gen.bl_category = "Item"   # screenshot only: show it on the open tab
sg.VIEW3D_PT_stitch_gen.bl_order = -10
sg.register()


def setup():
    if os.environ.get("STITCHGEN_FAKE_PROGRESS"):      # show the bake progress row
        wm = bpy.context.window_manager
        wm.stitch_gen_baking = True
        wm.stitch_gen_bake_progress = 0.5
        wm.stitch_gen_bake_label = "Baking 2/2"
    ob = bpy.data.objects[os.environ.get("STITCHGEN_OBJ", "Skirt")]
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    if os.environ.get("STITCHGEN_ADD_LINES"):           # show two line art layers
        if sg._stitch_item(ob.stitch_gen) is None:
            bpy.ops.stitch_gen.stitch_add()
        bpy.ops.stitch_gen.line_add()
        ob.stitch_gen.lines[1].width = 0.8
        bpy.ops.stitch_gen.line_add()
        ob.stitch_gen.lines[2].width = 0.5
        sg.regenerate(ob)
    if os.environ.get("STITCHGEN_SELECT") is not None:  # select a layer row
        ob.stitch_gen.line_index = int(os.environ["STITCHGEN_SELECT"])
    if os.environ.get("STITCHGEN_EDIT"):                # edge buttons enabled
        bpy.ops.object.mode_set(mode='EDIT')
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            sp = area.spaces.active
            sp.show_region_ui = True
            for region in area.regions:
                if region.type == 'UI':
                    with bpy.context.temp_override(area=area, region=region):
                        try:
                            region.active_panel_category = "Item"
                        except Exception as e:
                            print("category", e)
            win = [r for r in area.regions if r.type == 'WINDOW'][0]
            with bpy.context.temp_override(area=area, region=win):
                bpy.ops.view3d.view_selected()
                bpy.ops.view3d.view_axis(type=os.environ.get("STITCHGEN_VIEW", "FRONT"))
                bpy.ops.view3d.view_selected()
            sp.shading.type = os.environ.get("STITCHGEN_SHADING", "MATERIAL")
    if os.environ.get("STITCHGEN_ONLY"):                # show only these objects
        keep = set(os.environ["STITCHGEN_ONLY"].split(","))
        for o in bpy.context.view_layer.objects:
            if o.name not in keep:
                o.hide_set(True)
    if os.environ.get("STITCHGEN_HIDE"):
        bpy.data.objects[os.environ["STITCHGEN_HIDE"]].hide_set(True)

    return None


def popup():
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            region = [r for r in area.regions if r.type == 'UI'][0]
            with bpy.context.temp_override(area=area, region=region):
                print("POPUP", bpy.ops.stitch_gen.edit_color('INVOKE_DEFAULT', index=1))
    return None


def add_menu():
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            region = [r for r in area.regions if r.type == 'UI'][0]
            with bpy.context.temp_override(area=area, region=region):
                bpy.ops.wm.call_menu(name="STITCHGEN_MT_add_layer")
    return None


def presets():
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            region = [r for r in area.regions if r.type == 'UI'][0]
            with bpy.context.temp_override(area=area, region=region):
                bpy.ops.wm.call_panel(name=os.environ["STITCHGEN_PRESETS"], keep_open=True)
    return None


if os.environ.get("STITCHGEN_PRESETS"):                # a preset list open
    bpy.app.timers.register(presets, first_interval=2.0)
if os.environ.get("STITCHGEN_ADD_MENU"):               # the + menu open
    bpy.app.timers.register(add_menu, first_interval=2.0)
if os.environ.get("STITCHGEN_COLOR_POPUP"):            # the color picker of row 1
    bpy.app.timers.register(popup, first_interval=2.0)


def shoot():
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            if os.environ.get("STITCHGEN_GLRENDER"):      # the 3D view alone, no UI
                win = [r for r in area.regions if r.type == 'WINDOW'][0]
                sc = bpy.context.scene
                sc.render.resolution_x, sc.render.resolution_y = 1400, 1400
                sc.render.film_transparent = False
                with bpy.context.temp_override(area=area, region=win):
                    area.spaces.active.overlay.show_overlays = False
                    bpy.ops.render.opengl(view_context=True)
                bpy.data.images["Render Result"].save_render(filepath=out)
                continue
            with bpy.context.temp_override(area=area):
                bpy.ops.screen.screenshot_area(filepath=out)
    print("PANEL_STATUS", bpy.data.objects[os.environ.get("STITCHGEN_OBJ", "Skirt")].stitch_gen.status or "ok")
    bpy.ops.wm.quit_blender()


bpy.app.timers.register(setup, first_interval=1.0)
bpy.app.timers.register(shoot, first_interval=float(os.environ.get("STITCHGEN_SHOOT_DELAY", 3.0)))
