"""Presets: applying one can be undone, values a preset lacks fall back to
the defaults, and the starred preset is what Default applies and what new
layers start with. Needs a window (undo), and a scratch preset folder:

BLENDER_USER_RESOURCES=<scratch> BLENDER_USER_CONFIG=<scratch>
blender --factory-startup skirt_test.blend -P preset_default_test.py -- <log.txt> [<shot.png>]
"""
import os
import sys
import traceback

import bpy

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import rizum_pattern_masks as sg  # noqa: E402
from rizum_pattern_masks import presets  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:]
log_path = argv[0]
shot = argv[1] if len(argv) > 1 else None
sg.register()


def log(*a):
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(" ".join(str(x) for x in a) + "\n")


def ctx():
    w = bpy.context.window_manager.windows[0]
    area = [a for a in w.screen.areas if a.type == 'VIEW_3D'][0]
    region = [r for r in area.regions if r.type == 'WINDOW'][0]
    return dict(window=w, area=area, region=region)


def push(msg):
    with bpy.context.temp_override(**ctx()):
        bpy.ops.ed.undo_push(message=msg)


def undo():
    with bpy.context.temp_override(**ctx()):
        bpy.ops.ed.undo()


def preset_dir(kind):
    return presets._preset_dir(kind, create=True)


def check(name, ok, *info):
    log("PASS" if ok else "FAIL", name, *info)


def run():
    ob = bpy.data.objects["Skirt"]
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    s = ob.stitch_gen
    s.live = False
    with bpy.context.temp_override(**ctx()):
        bpy.ops.stitch_gen.stitch_add()
        bpy.ops.stitch_gen.line_add()
    W0 = ob.stitch_gen.lines[s.line_index].bl_rna.properties["width"].default

    # save a line preset, change the layer, apply the preset, undo
    lay = s.lines[s.line_index]
    lay.width, lay.offset = 0.3, 1.5
    with bpy.context.temp_override(**ctx()):
        bpy.ops.stitch_gen.line_preset_add(name="Thin")
    path = os.path.join(preset_dir('LINE'), "Thin.py")
    check("preset saved", os.path.isfile(path))
    lay.width = 2.0
    push("width 2")
    with bpy.context.temp_override(**ctx()):
        # as a click in the UI does: run it with an undo step
        r = bpy.ops.stitch_gen.apply_preset('EXEC_DEFAULT', True, kind='LINE', filepath=path)
    lay = s.lines[s.line_index]
    check("applied", r == {'FINISHED'} and abs(lay.width - 0.3) < 1e-6, r, lay.width)
    undo()
    lay = bpy.data.objects["Skirt"].stitch_gen.lines[bpy.data.objects["Skirt"].stitch_gen.line_index]
    check("undo restores", abs(lay.width - 2.0) < 1e-6, lay.width)

    # a preset without a value leaves it at the default, not at the last one
    ob = bpy.data.objects["Skirt"]
    s = ob.stitch_gen
    lay = s.lines[s.line_index]
    old = os.path.join(preset_dir('LINE'), "Old.py")
    with open(old, "w", encoding="utf-8") as f:
        f.write("import bpy\nob = bpy.context.active_object\ns = ob.stitch_gen\n"
                "layer = s.lines[s.line_index]\n\nlayer.width = 0.8\n")
    lay.smooth = 7.0
    with bpy.context.temp_override(**ctx()):
        bpy.ops.stitch_gen.apply_preset(kind='LINE', filepath=old)
    sm0 = lay.bl_rna.properties["smooth"].default
    check("missing value -> default", abs(lay.smooth - sm0) < 1e-6 and abs(lay.width - 0.8) < 1e-6,
          lay.smooth, lay.width)

    # star "Thin": Default applies it, a new line layer starts with it
    with bpy.context.temp_override(**ctx()):
        bpy.ops.stitch_gen.preset_default(kind='LINE', name="Thin")
    check("starred", presets._default_stem('LINE') == "Thin")
    lay.width = 5.0
    with bpy.context.temp_override(**ctx()):
        bpy.ops.stitch_gen.reset_defaults(kind='LINE')
    check("Default applies star", abs(lay.width - 0.3) < 1e-6, lay.width)
    with bpy.context.temp_override(**ctx()):
        bpy.ops.stitch_gen.line_add()
    new = s.lines[s.line_index]
    check("new layer uses star", abs(new.width - 0.3) < 1e-6 and abs(new.offset - 1.5) < 1e-6,
          new.width, new.offset)
    # star again: off, Default goes back to the add-on's own
    with bpy.context.temp_override(**ctx()):
        bpy.ops.stitch_gen.preset_default(kind='LINE', name="Thin")
        bpy.ops.stitch_gen.reset_defaults(kind='LINE')
    check("unstar", presets._default_stem('LINE') is None and abs(new.width - W0) < 1e-6, new.width)

    # grid: starred preset for a new grid layer
    with bpy.context.temp_override(**ctx()):
        bpy.ops.stitch_gen.grid_add()
    g = s.lines[s.line_index]
    g.grid_cell, g.grid_layout = 7.0, 'UNROLLED'
    with bpy.context.temp_override(**ctx()):
        bpy.ops.stitch_gen.grid_preset_add(name="Big")
        bpy.ops.stitch_gen.preset_default(kind='GRID', name="Big")
        bpy.ops.stitch_gen.grid_add()
    g2 = s.lines[s.line_index]
    check("new grid uses star", abs(g2.grid_cell - 7.0) < 1e-6 and g2.grid_layout == 'UNROLLED',
          g2.grid_cell, g2.grid_layout)

    # stitches: Default applies the starred stitch preset
    s.line_index = 0
    s.length = 9.0
    with bpy.context.temp_override(**ctx()):
        bpy.ops.stitch_gen.stitch_preset_add(name="Nine")
        bpy.ops.stitch_gen.preset_default(kind='STITCH', name="Nine")
    s.length = 3.0
    with bpy.context.temp_override(**ctx()):
        bpy.ops.stitch_gen.reset_defaults(kind='STITCH')
    check("stitch Default applies star", abs(s.length - 9.0) < 1e-6, s.length)

    # removing the starred preset: Default falls back to the add-on's own
    with bpy.context.temp_override(**ctx()):
        bpy.ops.stitch_gen.stitch_preset_add(name="Nine", remove_name=True)
    check("removed star ignored", presets._default_stem('STITCH') is None)

    # leave a grid layer selected and open its list for the screenshot
    s.line_index = len(s.lines) - 1
    if shot:
        with bpy.context.temp_override(**ctx()):
            bpy.ops.wm.call_panel(name="STITCHGEN_PT_grid_presets", keep_open=True)


def main():
    try:
        run()
    except Exception:
        log("FAIL exception", traceback.format_exc())
    if shot:
        bpy.app.timers.register(lambda: (bpy.ops.screen.screenshot(filepath=shot), finish())[1],
                                first_interval=1.0)
    else:
        finish()
    return None


def finish():
    log("DONE")
    bpy.ops.wm.quit_blender()


bpy.app.timers.register(main, first_interval=1.0)
