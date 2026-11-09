"""A file saved with 0.2.x: the layer list gets the stitch row first, each line
layer keeps its edges and takes the old shared line art color.

blender -b --factory-startup <old.blend> -P migrate_test.py
"""
import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pattern_masks as sg  # noqa: E402

sg.register()
sg._on_load(None)          # the file was opened before the add-on was registered
for ob in bpy.data.objects:
    if ob.type != 'MESH' or not len(ob.stitch_gen.lines):
        continue
    s = ob.stitch_gen
    print("RESULT", ob.name, "rows", [(l.name, l.edge_attr) for l in s.lines],
          "selected", s.line_index, "old color", tuple(round(c, 2) for c in s.line_color[:3]),
          "layer colors", [tuple(round(c, 2) for c in l.color[:3]) for l in sg._line_items(s)])
    data = sg.regenerate(ob, create=True)
    lo = s.line_preview
    print("RESULT", ob.name, "regenerated", data is not None, "status", s.status or "ok",
          "line slots", [m.name if m else None for m in lo.data.materials] if lo else None)
