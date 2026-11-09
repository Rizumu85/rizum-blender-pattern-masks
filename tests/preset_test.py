"""Save and apply stitch and line art presets.

Run with BLENDER_USER_RESOURCES pointing at a scratch folder (presets are
written to the user's scripts/presets folder):
blender -b --factory-startup skirt_test.blend -P preset_test.py
"""
import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pattern_masks as sg  # noqa: E402

sg.register()
ob = bpy.data.objects["Skirt"]
bpy.context.view_layer.objects.active = ob
ob.select_set(True)
s = ob.stitch_gen
s.live = False
bpy.ops.stitch_gen.stitch_add()
bpy.ops.stitch_gen.line_add()
layer = s.lines[s.line_index]
print("RESULT new layer width", round(layer.width, 2), "rows", [l.name for l in s.lines])

layer.width, layer.offset, layer.smooth = 0.3, 1.5, 4.0
print("RESULT save line preset", bpy.ops.stitch_gen.line_preset_add(name="Thin Trim"))
layer.width, layer.offset, layer.smooth = 2.0, 0.0, 0.0
path = os.path.join(bpy.utils.user_resource('SCRIPTS', path="presets/pattern_masks/line_art"),
                    "Thin Trim.py")
print("RESULT preset file", os.path.exists(path))
bpy.ops.script.execute_preset(filepath=path, menu_idname="STITCHGEN_MT_line_presets")
print("RESULT line after preset", round(layer.width, 2), round(layer.offset, 2),
      round(layer.smooth, 2))

s.line_index = 0
s.length, s.gap = 6.0, 3.0
print("RESULT save stitch preset", bpy.ops.stitch_gen.stitch_preset_add(name="Long"))
s.length, s.gap = 4.0, 2.0
path = os.path.join(bpy.utils.user_resource('SCRIPTS', path="presets/pattern_masks/stitches"),
                    "Long.py")
bpy.ops.script.execute_preset(filepath=path, menu_idname="STITCHGEN_MT_stitch_presets")
print("RESULT stitch after preset", round(s.length, 2), round(s.gap, 2))
p = ob.stitch_gen.bl_rna.properties["inset"]
print("RESULT inset unit", p.unit, p.subtype, "name", p.name, "ctx", p.translation_context)
