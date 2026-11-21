"""Background bake job in a real window: progress, responsiveness, result.

blender --factory-startup result.blend -P bake_job_test.py -- <out_dir> <log>
"""
import os
import sys
import time

import bpy

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import rizum_pattern_masks as sg  # noqa: E402
from rizum_pattern_masks import layers  # noqa: E402

out_dir, log_path = sys.argv[sys.argv.index("--") + 1:][:2]
sg.register()
t0 = [None]
beats = []


def log(msg):
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(msg + "\n")


def start():
    ob = bpy.data.objects["Skirt"]
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    s = ob.stitch_gen
    s.live = False
    s.output_dir = out_dir
    s.resolution = '4096'
    s.samples = 64              # slow on purpose, to watch the job
    s.device = 'CPU'
    s.cpu_usage = 50
    if os.environ.get("STITCHGEN_ADD_LINES"):          # bake line art layers too
        bpy.ops.stitch_gen.line_add()
        bpy.ops.stitch_gen.line_add()
    if os.environ.get("STITCHGEN_NO_STITCHES"):
        s.stitches = False
    win = bpy.context.window_manager.windows[0]
    area = [a for a in win.screen.areas if a.type == 'VIEW_3D'][0]
    with bpy.context.temp_override(window=win, area=area):
        res = bpy.ops.stitch_gen.bake('INVOKE_DEFAULT')
    t0[0] = time.time()
    log(f"invoke -> {res}, threads now {bpy.context.scene.render.threads} "
        f"of {os.cpu_count()}, mode {bpy.context.scene.render.threads_mode}")
    return None


def beat():
    if t0[0] is None:
        return 0.3
    wm = bpy.context.window_manager
    beats.append(time.time())
    if len(beats) == 4:
        src = layers._source_object(bpy.context)
        log(f"during bake: active {bpy.context.view_layer.objects.active.name}, panel shows "
            f"{src.name if src else None}, folder {src.stitch_gen.output_dir if src else None}")
        with bpy.context.temp_override(window=wm.windows[0]):
            bpy.ops.screen.screenshot(filepath=os.path.join(out_dir, "bake_progress.png"))
    if not wm.stitch_gen_baking:
        gaps = [b - a for a, b in zip(beats, beats[1:])] or [0]
        log(f"done after {time.time() - t0[0]:.1f}s, heartbeats {len(beats)}, "
            f"longest gap {max(gaps):.2f}s, threads restored to "
            f"{bpy.context.scene.render.threads_mode}/{bpy.context.scene.render.threads}")
        log("files " + ", ".join(sorted(f for f in os.listdir(out_dir) if f.endswith('.png'))))
        bpy.ops.wm.quit_blender()
        return None
    if time.time() - t0[0] > 120:
        log("timeout")
        bpy.ops.wm.quit_blender()
        return None
    return 0.3


bpy.app.timers.register(start, first_interval=1.5)
bpy.app.timers.register(beat, first_interval=2.0)
