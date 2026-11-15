"""Stability: many random actions in a real window, the way a user mixes them.

    blender --factory-startup skirt_test.blend -P stress_test.py -- <log.txt> [steps] [seed]

With Blender's user folders in a scratch folder (BLENDER_USER_RESOURCES,
BLENDER_USER_CONFIG): presets are saved during the run.

Each step is one thing a user can do: add or remove layers of every kind,
select rows, mark and unmark edges and corners in Edit Mode, change settings,
references, presets, undo and redo (Object Mode only: Edit Mode undo from a
timer hangs Blender itself), switch modes, duplicate and delete objects, a
quick bake, Clear All Layers, turn the add-on off and on again. The log is
written as it goes, so a crash shows the step it died on; the run ends with
DONE and the timings of the panel and overlay draws (frame time: smoothness).

The steps run from a modal operator, so each one has the window's own context,
as a click has. (Run from a timer inside a Python context override instead,
Blender itself crashes now and then reading that override in undo or mode
switching, a path no user action takes.)

An exception in a step is logged as EXC and counted; the run goes on. A crash
leaves no DONE line.
"""
import os
import random
import sys
import time
import traceback

import bpy
import bmesh

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import rizum_pattern_masks as sg  # noqa: E402
from rizum_pattern_masks import overlay  # noqa: E402

args = sys.argv[sys.argv.index("--") + 1:]
log_path = args[0]
N = int(args[1]) if len(args) > 1 else 250
rng = random.Random(int(args[2]) if len(args) > 2 else 7)
out_dir = os.path.join(os.path.dirname(os.path.abspath(log_path)), "stress_out")
os.makedirs(out_dir, exist_ok=True)
open(log_path, "w").close()

# the panel on the tab the sidebar opens on, so it draws during the run
sg.VIEW3D_PT_stitch_gen.bl_category = "Item"
sg.VIEW3D_PT_stitch_gen.bl_order = -10


def log(msg):
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(msg + "\n")


# -- draw timings: the panel and the overlay, wrapped -----------------------------------
times = {"panel": [], "overlay": []}


def timed(kind, fn):
    def wrap(*a, **k):
        t = time.perf_counter()
        try:
            return fn(*a, **k)
        except Exception as e:                 # Blender only prints these: count them
            state["exc"] += 1
            log(f"EXC {kind} draw: {type(e).__name__}: {e}\n{traceback.format_exc()}")
        finally:
            ms = 1000 * (time.perf_counter() - t)
            times[kind].append(ms)
            if ms > 50:
                log(f"    slow {kind} draw {ms:.0f}ms")
    wrap.__wrapped__ = fn
    return wrap


def wrap_draws():
    P = sg.VIEW3D_PT_stitch_gen
    if not hasattr(P.draw, "__wrapped__"):
        inner = P.draw

        def draw(self, context):                 # Blender checks the panel's signature
            t = time.perf_counter()
            try:
                inner(self, context)
            except Exception as e:
                state["exc"] += 1
                log(f"EXC panel draw: {type(e).__name__}: {e}\n{traceback.format_exc()}")
            finally:
                times["panel"].append(1000 * (time.perf_counter() - t))
        draw.__wrapped__ = inner
        P.draw = draw
    for name in dir(overlay):
        if name.startswith("_draw") and callable(getattr(overlay, name)):
            fn = getattr(overlay, name)
            if not hasattr(fn, "__wrapped__"):
                setattr(overlay, name, timed("overlay", fn))


# before register: the overlay hands its draw functions to Blender there
wrap_draws()
sg.register()


def win_ctx():
    w = bpy.context.window_manager.windows[0]
    area = [a for a in w.screen.areas if a.type == 'VIEW_3D'][0]
    region = [r for r in area.regions if r.type == 'WINDOW'][0]
    return dict(window=w, area=area, region=region)


def ob():
    return bpy.context.view_layer.objects.active


def objects():
    previews = sg._previews()
    return [o for o in bpy.context.view_layer.objects
            if o is not None and o.type == 'MESH' and o.name_full not in previews]


def ensure_object_mode():
    if ob() is not None and ob().mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')


def pick_edges(o, share):
    """Select a random share of the boundary edges (and a few inner ones)."""
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(o.data)
    for e in bm.edges:
        e.select_set(False)
    for v in bm.verts:
        v.select_set(False)
    edges = [e for e in bm.edges if e.is_boundary] or list(bm.edges)
    if not edges:
        log(f"    ({o.name} has no edges)")
        return
    k = max(1, int(len(edges) * share))
    start = rng.randrange(len(edges))
    for e in (edges + edges)[start:start + k]:
        e.select_set(True)
    for e in rng.sample(list(bm.edges), min(3, len(bm.edges))):
        e.select_set(True)
    bm.select_flush_mode()
    bmesh.update_edit_mesh(o.data)


# -- the actions ----------------------------------------------------------------------
def a_add_layer():
    ensure_object_mode()
    getattr(bpy.ops.stitch_gen, rng.choice(["stitch_add", "line_add", "grid_add"]))()


def a_remove_layer():
    ensure_object_mode()
    if len(ob().stitch_gen.lines):
        bpy.ops.stitch_gen.line_remove()


def a_select_row():
    s = ob().stitch_gen
    if len(s.lines):
        s.line_index = rng.randrange(len(s.lines))


def a_mark_edges():
    o = ob()
    if not len(o.stitch_gen.lines):
        return
    pick_edges(o, rng.choice([0.1, 0.3, 0.6, 1.0]))
    rng.choice([bpy.ops.stitch_gen.path_add, bpy.ops.stitch_gen.path_add,
                bpy.ops.stitch_gen.path_remove, bpy.ops.stitch_gen.path_select,
                bpy.ops.stitch_gen.path_clear])()
    bpy.ops.object.mode_set(mode='OBJECT')


def a_corners():
    o = ob()
    bpy.ops.object.mode_set(mode='EDIT')
    bm = bmesh.from_edit_mesh(o.data)
    for v in bm.verts:
        v.select_set(False)
    for v in rng.sample(list(bm.verts), min(4, len(bm.verts))):
        v.select_set(True)
    bmesh.update_edit_mesh(o.data)
    rng.choice([bpy.ops.stitch_gen.corner_mark, bpy.ops.stitch_gen.corner_clear,
                bpy.ops.stitch_gen.corner_detect, bpy.ops.stitch_gen.corner_select])()
    bpy.ops.object.mode_set(mode='OBJECT')


SETTINGS = {
    'STITCH': [("inset", -2, 12), ("stitch_smooth", 0, 20), ("corner_inset", 0, 5),
               ("length", 0.3, 15), ("gap", 0, 10), ("thread_width", 0.1, 4),
               ("roundness", 0, 1), ("zigzag_height", 0, 10)],
    'LINE': [("offset", 0, 10), ("width", 0, 6), ("corner_inset", 0, 5), ("smooth", 0, 20)],
    'GRID': [("grid_from", -20, 20), ("grid_along", -20, 20), ("grid_angle", -3, 3),
             ("grid_cell", 0.5, 30), ("grid_wobble", 0, 1)],
}


def a_change_setting():
    s = ob().stitch_gen
    if not len(s.lines):
        return
    item = s.lines[s.line_index] if 0 <= s.line_index < len(s.lines) else s.lines[0]
    kind = sg._layer_kind(item)
    for _ in range(rng.randint(1, 6)):              # a slider drag: a few values in a row
        name, lo, hi = rng.choice(SETTINGS[kind])
        setattr(item, name, rng.uniform(lo, hi))
    if kind == 'STITCH' and rng.random() < 0.3:
        item.style = rng.choice(['DASH', 'ZIGZAG'])
        item.even = rng.random() < 0.5
    if kind == 'GRID' and rng.random() < 0.2:
        item.grid_layout = rng.choice(['LOOPS', 'UNROLLED'])


def a_toggles():
    s = ob().stitch_gen
    if len(s.lines):
        item = s.lines[rng.randrange(len(s.lines))]
        setattr(item, rng.choice(["enabled", "show_marks"]), rng.random() < 0.6)
    if rng.random() < 0.3:
        s.flip = not s.flip
    if rng.random() < 0.3:
        bpy.context.scene.stitch_gen_marks = rng.random() < 0.7
    if rng.random() < 0.2:
        s.live = not s.live


def a_reference():
    s = ob().stitch_gen
    if len(s.lines) < 2:
        return
    item = s.lines[s.line_index] if 0 <= s.line_index < len(s.lines) else s.lines[0]
    other = rng.choice([l for l in s.lines if l != item])
    attr = "" if rng.random() < 0.3 else sg._layer_attr(other)
    bpy.ops.stitch_gen.set_reference(attr=attr)


def a_preset():
    s = ob().stitch_gen
    if not len(s.lines):
        return
    kind = sg._layer_kind(s.lines[s.line_index]) if 0 <= s.line_index < len(s.lines) else 'STITCH'
    op = {"STITCH": bpy.ops.stitch_gen.stitch_preset_add, "LINE": bpy.ops.stitch_gen.line_preset_add,
          "GRID": bpy.ops.stitch_gen.grid_preset_add}[kind]
    if rng.random() < 0.5:
        op(name=f"stress {rng.randrange(3)}")
    files = sg._preset_files(kind)
    if files and rng.random() < 0.7:
        bpy.ops.stitch_gen.apply_preset(kind=kind, filepath=rng.choice(files)[1])
    elif rng.random() < 0.5:
        bpy.ops.stitch_gen.reset_defaults(kind=kind)


def a_undo_redo():
    # one step back or forward per call, as Ctrl+Z / Ctrl+Shift+Z do: several in
    # one Python context override crash Blender itself (in ed_undo_step_pre
    # reading the override), a path a user's key press never takes
    ensure_object_mode()
    op = bpy.ops.ed.undo if rng.random() < 0.6 else bpy.ops.ed.redo
    if op.poll():
        op()
        log(f"    ({op.idname_py()})")


def a_duplicate():
    ensure_object_mode()
    obs = objects()
    if len(obs) < 3 and rng.random() < 0.7:
        bpy.ops.object.duplicate()
        bpy.ops.transform.translate(value=(0.6, 0, 0))
    elif len(obs) > 1:
        victim = rng.choice([o for o in obs if o != obs[0]])
        bpy.data.objects.remove(victim)
        first = objects()[0]
        bpy.context.view_layer.objects.active = first
        first.select_set(True)


def a_switch_object():
    ensure_object_mode()
    obs = objects()
    o = rng.choice(obs)
    for x in bpy.context.view_layer.objects:
        if x is not None:
            x.select_set(False)
    o.select_set(True)
    if rng.random() < 0.3 and len(obs) > 1:            # several selected: bake / edit them all
        rng.choice([x for x in obs if x != o]).select_set(True)
    bpy.context.view_layer.objects.active = o


def a_bake():
    ensure_object_mode()
    for o in objects():
        s = o.stitch_gen
        s.output_dir = out_dir
        s.resolution = '1024'
        s.samples = 1
    if bpy.ops.stitch_gen.bake.poll():
        try:
            bpy.ops.stitch_gen.bake('EXEC_DEFAULT')
        except RuntimeError as e:            # the operator's own message, not a failure
            if "No stitches to bake" not in str(e):
                raise
            log("    (nothing to bake)")


def a_clear_all():
    ensure_object_mode()
    if bpy.ops.stitch_gen.clear_scene.poll():
        bpy.ops.stitch_gen.clear_scene('EXEC_DEFAULT')


def a_reload_addon():
    ensure_object_mode()
    sg.unregister()
    sg.register()
    wrap_draws()


ACTIONS = [(a_add_layer, 10), (a_remove_layer, 4), (a_select_row, 8), (a_mark_edges, 14),
           (a_corners, 4), (a_change_setting, 16), (a_toggles, 6), (a_reference, 4),
           (a_preset, 3), (a_undo_redo, 8), (a_duplicate, 3), (a_switch_object, 4),
           (a_bake, 1), (a_clear_all, 1), (a_reload_addon, 1)]
plan = rng.choices([a for a, _ in ACTIONS], weights=[w for _, w in ACTIONS], k=N)
state = {"i": 0, "exc": 0, "t0": None, "step_ms": []}


def setup():
    o = bpy.data.objects["Skirt"]
    for x in bpy.context.view_layer.objects:
        x.select_set(False)
    o.select_set(True)
    bpy.context.view_layer.objects.active = o
    sp = win_ctx()["area"].spaces.active
    sp.show_region_ui = True
    sp.shading.type = 'MATERIAL'
    log(f"START steps={N}")
    state["t0"] = time.perf_counter()


def step():
    """One step; False when the run is over."""
    i = state["i"]
    if i == 0:
        setup()
    if i >= len(plan):
        p, o = sorted(times["panel"]), sorted(times["overlay"])
        pct = lambda a, q: a[min(len(a) - 1, int(q * len(a)))] if a else 0.0  # noqa: E731
        sm = sorted(state["step_ms"])
        log(f"panel draws {len(p)} median {pct(p, .5):.1f}ms p95 {pct(p, .95):.1f}ms max {max(p or [0]):.1f}ms")
        log(f"overlay draws {len(o)} median {pct(o, .5):.1f}ms p95 {pct(o, .95):.1f}ms max {max(o or [0]):.1f}ms")
        log(f"steps median {pct(sm, .5):.0f}ms p95 {pct(sm, .95):.0f}ms max {max(sm or [0]):.0f}ms")
        log(f"exceptions {state['exc']}  total {time.perf_counter() - state['t0']:.0f}s")
        log("DONE")
        return False
    fn = plan[i]
    state["i"] += 1
    if ob() is None or ob().type != 'MESH' or ob().name_full in sg._previews():
        obs = objects()                      # after an undo or a delete: a user picks one
        bpy.context.view_layer.objects.active = obs[0]
        obs[0].select_set(True)
        log("    (active object picked again)")
    log(f"{i:03d} {fn.__name__}")
    t = time.perf_counter()
    try:
        fn()
        if fn is not a_undo_redo:            # a step of its own would drop the redo steps
            bpy.ops.ed.undo_push(message=fn.__name__)
    except Exception as e:
        state["exc"] += 1
        log(f"EXC {fn.__name__}: {type(e).__name__}: {e}\n{traceback.format_exc()}")
        try:
            ensure_object_mode()
        except Exception:
            pass
    ms = 1000 * (time.perf_counter() - t)
    state["step_ms"].append(ms)
    if ms > 250:
        log(f"    took {ms:.0f}ms")
    return True


class STRESS_OT_run(bpy.types.Operator):
    """Runs the steps on timer events, in the 3D view's context."""
    bl_idname = "wm.stress_run"
    bl_label = "Stress Run"

    def invoke(self, context, event):
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.05, window=context.window)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}
        if step():
            return {'RUNNING_MODAL'}
        context.window_manager.event_timer_remove(self._timer)
        bpy.app.timers.register(lambda: bpy.ops.wm.quit_blender() and None, first_interval=0.2)
        return {'FINISHED'}


bpy.utils.register_class(STRESS_OT_run)


def start():
    with bpy.context.temp_override(**win_ctx()):
        bpy.ops.wm.stress_run('INVOKE_DEFAULT')


bpy.app.timers.register(start, first_interval=1.5)
