"""Bake several selected objects with one press.

The skirt and a copy of it both get stitches (marked together in Edit Mode)
and the copy a line art layer; with both selected, Bake writes the masks of
both. Without -b it runs the background job in a real window and also checks
the progress label names the object being baked.

blender -b --factory-startup skirt_test.blend -P multi_bake_test.py -- <out_dir>
blender --factory-startup skirt_test.blend -P multi_bake_test.py -- <out_dir>
"""
import os
import sys
import time

import bpy
import bmesh

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import rizum_pattern_masks as sg  # noqa: E402

out_dir = sys.argv[sys.argv.index("--") + 1]
os.makedirs(out_dir, exist_ok=True)
for f in os.listdir(out_dir):
    if f.endswith(".png"):
        os.remove(os.path.join(out_dir, f))
log_path = os.path.join(out_dir, "multi_bake_log.txt")
open(log_path, "w").close()
sg.register()
fails = []


def check(name, ok, *info):
    msg = " ".join(["RESULT", "PASS" if ok else "FAIL", name] + [str(x) for x in info])
    print(msg)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(msg + "\n")
    if not ok:
        fails.append(name)


def finish():
    msg = "ALL PASS" if not fails else f"FAILED: {fails}"
    print(msg)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(msg + "\n")


def setup():
    ob = bpy.data.objects["Skirt"]
    ob2 = ob.copy()
    ob2.data = ob.data.copy()
    ob2.location.x += 1.0
    bpy.context.collection.objects.link(ob2)
    vl = bpy.context.view_layer
    for o in vl.objects:
        o.select_set(False)
    for o in (ob, ob2):
        o.select_set(True)
        s = o.stitch_gen
        s.live = False
        s.output_dir = out_dir
        s.resolution = '1024'
        s.samples = 4
        s.device = 'CPU'
    vl.objects.active = ob2
    bpy.ops.stitch_gen.line_add()              # the copy: a line art layer on the waist
    bpy.ops.object.mode_set(mode='EDIT')
    for o in (ob, ob2):                        # the waist, on the copy only
        bm = bmesh.from_edit_mesh(o.data)
        for e in bm.edges:
            e.select_set(False)
        for v in bm.verts:
            v.select_set(False)
        for e in bm.edges:
            if o == ob2 and e.is_boundary and                     all((o.matrix_world @ v.co).z > -0.01 for v in e.verts):
                e.select_set(True)
        bmesh.update_edit_mesh(o.data)
    bpy.ops.stitch_gen.path_add()
    ob2.stitch_gen.line_index = -1             # nothing selected in the list: the stitches
    vl.objects.active = ob
    for o in (ob, ob2):
        bm = bmesh.from_edit_mesh(o.data)
        for e in bm.edges:
            e.select_set(False)
        for v in bm.verts:
            v.select_set(False)
        for e in bm.edges:
            if e.is_boundary and all((o.matrix_world @ v.co).z < -0.265 for v in e.verts):
                e.select_set(True)
        bmesh.update_edit_mesh(o.data)
    bpy.ops.stitch_gen.path_add()
    bpy.ops.object.mode_set(mode='OBJECT')
    check("set up: stitches on both", ob.stitch_gen.dash_count > 0 and ob2.stitch_gen.dash_count > 0,
          ob.stitch_gen.dash_count, ob2.stitch_gen.dash_count)
    check("set up: a line layer on the copy only",
          len(sg._line_items(ob2.stitch_gen)) == 1 and not sg._line_items(ob.stitch_gen))
    targets = [o.name for o in sg._bake_targets(bpy.context)]
    check("both are bake targets, the active one first", targets == [ob.name, ob2.name], targets)
    return ob, ob2


def check_files(ob, ob2):
    pngs = sorted(f for f in os.listdir(out_dir) if f.endswith(".png"))
    a = [f for f in pngs if f.startswith(ob.name + "_")]
    b = [f for f in pngs if f.startswith(ob2.name + "_")]
    check("masks of the first object", any(f.endswith("_stitch.png") for f in a), a)
    check("masks of the second object", any(f.endswith("_stitch.png") for f in b)
          and len(b) == 2, b)
    check("selection back", ob.select_get() and ob2.select_get()
          and bpy.context.view_layer.objects.active == ob)


if bpy.app.background:
    ob, ob2 = setup()
    r = bpy.ops.stitch_gen.bake()
    check("bake finished", r == {'FINISHED'}, r)
    check_files(ob, ob2)
    finish()
else:
    state = {"t0": None, "labels": set()}

    def start():
        ob, ob2 = setup()
        state["obs"] = (ob, ob2)
        win = bpy.context.window_manager.windows[0]
        area = [a for a in win.screen.areas if a.type == 'VIEW_3D'][0]
        with bpy.context.temp_override(window=win, area=area):
            res = bpy.ops.stitch_gen.bake('INVOKE_DEFAULT')
        check("job started", res == {'RUNNING_MODAL'}, res)
        state["t0"] = time.time()
        return None

    def beat():
        if state["t0"] is None:
            return 0.2
        wm = bpy.context.window_manager
        if wm.stitch_gen_baking:
            state["labels"].add(wm.stitch_gen_bake_label)
            if time.time() - state["t0"] > 300:
                check("finished in time", False)
                finish()
                bpy.ops.wm.quit_blender()
                return None
            return 0.2
        ob, ob2 = state["obs"]
        labels = sorted(state["labels"])
        check("progress names each object", any(l.startswith(ob.name + " ") for l in labels)
              and any(l.startswith(ob2.name + " ") for l in labels), labels)
        check_files(ob, ob2)
        finish()
        bpy.ops.wm.quit_blender()
        return None

    bpy.app.timers.register(start, first_interval=1.5)
    bpy.app.timers.register(beat, first_interval=2.0)
