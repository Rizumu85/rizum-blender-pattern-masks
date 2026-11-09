"""GUI undo test for the layer list (0.3.0).

blender --factory-startup skirt_test.blend -P undo_layers_test.py -- <log.txt>

Each step does one thing the user can do, undoes it, checks the state went
back (rows, edges, preview faces, material colors), redoes it and checks again.
Writes to the log as it goes, so a crash shows where it died.
"""
import os
import sys

import bpy
import bmesh

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pattern_masks as sg  # noqa: E402
from pattern_masks import core  # noqa: E402

log_path = sys.argv[sys.argv.index("--") + 1]
open(log_path, "w").close()
sg.register()
OB = "Skirt"


def log(msg):
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(msg + "\n")


def ctx():
    w = bpy.context.window_manager.windows[0]
    area = [a for a in w.screen.areas if a.type == 'VIEW_3D'][0]
    region = [r for r in area.regions if r.type == 'WINDOW'][0]
    return dict(window=w, area=area, region=region)


def state():
    """What the user would see: rows, edges per row, preview faces, colors."""
    ob = bpy.data.objects[OB]
    s = ob.stitch_gen
    rows = []
    for l in s.lines:
        attr = l.edge_attr or core.LINE_ATTR
        n = len(core.read_path_edges(ob.data, attr)) if attr in ob.data.attributes else 0
        rows.append((l.name, l.enabled, n, tuple(round(c, 2) for c in l.color[:3])))
    lo = s.line_preview
    rib = s.ribbon
    mats = ([tuple(round(c, 2) for c in m.diffuse_color[:3]) if m else None
             for m in lo.data.materials] if lo else [])
    return {
        "rows": rows, "sel": s.line_index,
        "line_faces": len(lo.data.polygons) if lo else 0,
        "stitch_faces": len(rib.data.polygons) if rib else 0,
        "line_mats": mats,
    }


def settle():
    """Let the debounced rebuild after undo run (it waits for 0.15 s)."""
    bpy.context.view_layer.update()
    sg._flush()
    for name in list(sg._pending):
        ob = bpy.data.objects.get(name)
        if ob is not None:
            sg.regenerate(ob)
    sg._pending.clear()


def check(label, do):
    settle()
    before = state()
    with bpy.context.temp_override(**ctx()):
        do()
        bpy.ops.ed.undo_push(message=label)
        settle()
        after = state()
        bpy.ops.ed.undo()
        settle()
        undone = state()
        bpy.ops.ed.redo()
        settle()
        redone = state()
    ok_undo = undone == before
    ok_redo = redone == after
    log(f"{'OK  ' if ok_undo and ok_redo else 'FAIL'} {label}: changed={after != before} "
        f"undo={'ok' if ok_undo else 'WRONG'} redo={'ok' if ok_redo else 'WRONG'}")
    if not ok_undo:
        log(f"     before {before}\n     undone {undone}")
    if not ok_redo:
        log(f"     after  {after}\n     redone {redone}")


steps = []


def step(fn):
    steps.append(fn)
    return fn


@step
def s_setup():
    ob = bpy.data.objects[OB]
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    with bpy.context.temp_override(**ctx()):
        ctx()["area"].spaces.active.shading.type = 'MATERIAL'
        bpy.ops.stitch_gen.stitch_add()
        bpy.ops.object.mode_set(mode='EDIT')
        bm = bmesh.from_edit_mesh(ob.data)
        for e in bm.edges:
            e.select_set(e.is_boundary and all(v.co.z < -0.265 for v in e.verts))
        bm.select_flush_mode()
        bmesh.update_edit_mesh(ob.data)
        bpy.ops.stitch_gen.path_add()
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.ed.undo_push(message="setup")
    log("setup " + repr(state()))


def _line_add():
    bpy.ops.stitch_gen.line_add()


def _waist_edges():
    ob = bpy.data.objects[OB]
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(ob.data)
    for e in bm.edges:
        e.select_set(e.is_boundary and all(v.co.z > -0.01 for v in e.verts))
    bm.select_flush_mode()
    bmesh.update_edit_mesh(ob.data)
    bpy.ops.stitch_gen.path_add()
    bpy.ops.object.mode_set(mode='OBJECT')


@step
def s_add_line():
    check("add line art layer", _line_add)


@step
def s_mark_line_edges():
    s = bpy.data.objects[OB].stitch_gen
    s.lines[1].include_stitch = False
    bpy.ops.ed.undo_push(message="include off")
    check("mark line edges (edit mode, back to object)", _waist_edges)


@step
def s_color():
    def do():
        bpy.data.objects[OB].stitch_gen.lines[1].color = (1.0, 0.0, 0.0, 1.0)
    check("change layer color", do)


@step
def s_eye():
    def do():
        bpy.data.objects[OB].stitch_gen.lines[1].enabled = False
    check("hide layer (eye)", do)


@step
def s_width():
    def do():
        bpy.data.objects[OB].stitch_gen.lines[1].width = 2.0
    check("change line width", do)


@step
def s_stitch_eye():
    def do():
        bpy.data.objects[OB].stitch_gen.stitches = False
    check("hide stitches (eye)", do)


@step
def s_remove_line():
    def do():
        s = bpy.data.objects[OB].stitch_gen
        s.line_index = 1
        bpy.ops.stitch_gen.line_remove()
    check("remove line layer (with its edges)", do)


@step
def s_remove_stitch():
    def do():
        s = bpy.data.objects[OB].stitch_gen
        s.line_index = 0
        bpy.ops.stitch_gen.line_remove()
    check("remove stitch row (with its edges)", do)


@step
def s_select():
    def do():
        bpy.data.objects[OB].stitch_gen.line_index = 0
    check("select another row", do)


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
        import traceback
        log(f"EXC in {fn.__name__}: {type(e).__name__}: {e}\n{traceback.format_exc()}")
    return 0.8


bpy.app.timers.register(runner, first_interval=1.5)
