"""GUI undo stress test. blender --factory-startup skirt_test.blend -P undo_test.py -- <log.txt>

Marks the hem in Edit Mode, drags settings, then undoes/redoes many times in
Object and Edit Mode. Writes progress to the log so a crash shows where it died.
"""
import os
import sys

import bpy
import bmesh

sys.path.insert(0, os.environ.get("STITCHGEN_PKG_DIR") or
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pattern_masks as sg  # noqa: E402

log_path = sys.argv[sys.argv.index("--") + 1]
sg.register()


def log(msg):
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(msg + "\n")


def win_ctx():
    w = bpy.context.window_manager.windows[0]
    area = [a for a in w.screen.areas if a.type == 'VIEW_3D'][0]
    region = [r for r in area.regions if r.type == 'WINDOW'][0]
    return dict(window=w, area=area, region=region)


steps = []


def step(fn):
    steps.append(fn)
    return fn


OBJ = os.environ.get("STITCHGEN_OBJ", "Skirt")


@step
def s_setup():
    ob = bpy.data.objects[OBJ]
    if OBJ != "Skirt":   # a real file that already has a path
        bpy.context.view_layer.objects.active = ob
        ob.select_set(True)
        with bpy.context.temp_override(**win_ctx()):
            if ob.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
            bpy.ops.stitch_gen.update()
        log("updated existing path")
        return
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    with bpy.context.temp_override(**win_ctx()):
        bpy.ops.object.mode_set(mode='EDIT')
        bm = bmesh.from_edit_mesh(ob.data)
        for e in bm.edges:
            e.select_set(e.is_boundary and all(v.co.z < -0.265 for v in e.verts))
        bm.select_flush_mode()
        bmesh.update_edit_mesh(ob.data)
        bpy.ops.ed.undo_push(message="select")
        bpy.ops.stitch_gen.path_add()
    log("path added in edit mode")


def s_edit_undo():  # not run: edit-mode ed.undo() from a timer hangs Blender itself
    log("edit-mode: before undo")
    with bpy.context.temp_override(**win_ctx()):
        bpy.ops.ed.undo()
        log("edit-mode: undo done")
        bpy.ops.ed.redo()
    log("edit-mode undo/redo ok")


@step
def s_object_mode_drag():
    with bpy.context.temp_override(**win_ctx()):
        bpy.ops.object.mode_set(mode='OBJECT')
        win_ctx()["area"].spaces.active.shading.type = os.environ.get("STITCHGEN_SHADING", "RENDERED")
        bpy.ops.ed.undo_push(message="object mode")
        s = bpy.data.objects[OBJ].stitch_gen
        for v in (3.0, 5.0, -9.698, 0.0, 6.2):
            s.inset = v
            bpy.ops.ed.undo_push(message="inset")
            bpy.context.view_layer.update()
        for v in (3.0, 3.5):
            s.length = v
            bpy.ops.ed.undo_push(message="length")
    log("drag ok")


@step
def s_undo_many():
    with bpy.context.temp_override(**win_ctx()):
        for i in range(8):
            bpy.ops.ed.undo()
            bpy.context.view_layer.update()
        log("undo x8 ok")
        for i in range(8):
            bpy.ops.ed.redo()
            bpy.context.view_layer.update()
    log("redo x8 ok")


@step
def s_drag_after_undo():
    with bpy.context.temp_override(**win_ctx()):
        bpy.ops.ed.undo()
        s = bpy.data.objects[OBJ].stitch_gen
        s.gap = 3.0
        bpy.ops.ed.undo_push(message="gap")
        bpy.ops.ed.undo()
        bpy.context.view_layer.update()
    log("drag after undo ok; status=" + repr(bpy.data.objects[OBJ].stitch_gen.status))


@step
def s_quit():
    log("DONE")
    bpy.ops.wm.quit_blender()


def runner():
    if not steps:
        return None
    fn = steps.pop(0)
    try:
        fn()
    except Exception as e:  # keep going so the log shows everything
        log(f"EXC in {fn.__name__}: {type(e).__name__}: {e}")
    return 0.6


bpy.app.timers.register(runner, first_interval=1.5)
