"""A file saved before 0.4.0: the stitch settings stored on the object move
onto its stitch row, which becomes a stitch layer; the stitches come out the
same as the old settings make them.

blender -b --factory-startup <old.blend> -P migrate_stitch_test.py
"""
import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import rizum_pattern_masks as sg  # noqa: E402

fails = []


def check(name, ok, *info):
    print(" ".join(["RESULT", "PASS" if ok else "FAIL", name] + [str(x) for x in info]))
    if not ok:
        fails.append(name)


sg.register()
# what the file stores under the object's stitch settings, before the migration
stored = {}
for ob in bpy.data.objects:
    if ob.type == 'MESH' and ob.stitch_gen.ui_version < 3 and sg._uses_addon(ob):
        raw = ob.stitch_gen
        stored[ob.name] = {k: raw.get(k) for k in ("width", "length", "gap", "inset", "style",
                                                     "stitches")}
sg._on_load(None)
found = 0
for name, raw in stored.items():
    ob = bpy.data.objects[name]
    s = ob.stitch_gen
    rows = sg._stitch_items(s)
    if not rows:
        continue
    found += 1
    st = rows[0]
    check(f"{name}: stitch row is a stitch layer", st.kind == 'STITCH' and s.ui_version == 3,
          st.kind, s.ui_version)
    check(f"{name}: one stitch layer", len(rows) == 1, len(rows))
    check(f"{name}: named for its old file", st.name == "stitch", st.name)
    for k, ik in (("width", "thread_width"), ("length", "length"), ("gap", "gap"),
                  ("inset", "inset")):
        if raw.get(k) is not None:
            check(f"{name}: {k} kept", abs(getattr(st, ik) - raw[k]) < 1e-6, getattr(st, ik), raw[k])
    if raw.get("style") is not None:
        check(f"{name}: style kept", st.style == ('DASH', 'ZIGZAG')[raw["style"]], st.style)
    shown = raw.get("stitches") is None or bool(raw["stitches"])
    check(f"{name}: eye kept", st.enabled == shown, st.enabled)
    data = sg.regenerate(ob, bpy.context.scene)
    if shown:
        check(f"{name}: makes its stitches", data is not None and data.dash_count > 0,
              s.status, data.dash_count if data else None)
check("found an object with stitches", found > 0, list(stored))
print("ALL PASS" if not fails else f"FAILED: {fails}")
