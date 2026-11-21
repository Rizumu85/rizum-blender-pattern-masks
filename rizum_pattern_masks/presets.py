# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Rizum
"""Layer presets, defaults and their Blender operators and panels."""

import os
import re
import traceback

import bpy
from bl_operators.presets import AddPresetBase
from bl_ui.utils import PresetPanel
from bpy.props import EnumProperty, StringProperty

from . import i18n, layers
from .layers import _STITCH_MAP, _is_grid, _is_stitch, _source_object, _stitch_item
from .rebuild import regenerate


# -- presets (Blender's own preset files, in the user's scripts/presets folder) ----

_PRESET_DEFINES = [
    "ob = bpy.context.active_object",
    "s = ob.stitch_gen",
    "layer = s.lines[s.line_index]",
]
_STITCH_VALUES = ["s.inset", "s.smooth", "s.corner_inset", "s.style", "s.width", "s.length",
                  "s.gap", "s.roundness", "s.zigzag_height", "s.even"]
_LINE_VALUES = ["layer.width", "layer.offset", "layer.corner_inset", "layer.smooth"]


class _PresetPoll:
    @classmethod
    def poll(cls, context):
        ob = context.active_object
        return ob is not None and ob.type == 'MESH' and ob == _source_object(context)

    @staticmethod
    def as_filename(name):
        """Keep the name as typed (Blender's own presets turn ". , ! ..." into
        spaces); replace only what Windows file names can't hold."""
        name = name.strip()
        for c in ('\\', '/', ':', '*', '?', '"', '<', '>', '|'):
            name = name.replace(c, "_")
        return name.rstrip(". ") or "_"


_DEFAULT_PROPS = {
    'STITCH': ("inset", "smooth", "corner_inset", "style", "width", "length", "gap",
               "roundness", "zigzag_height", "even"),
    'LINE': ("width", "offset", "corner_inset", "smooth"),
    'GRID': ("grid_from", "grid_along", "grid_angle", "grid_cell", "grid_wobble", "grid_layout"),
}


_PRESET_KINDS = [('STITCH', "", ""), ('LINE', "", ""), ('GRID', "", "")]
_PRESET_SUBDIRS = {'STITCH': "rizum_pattern_masks/stitches",
                   'LINE': "rizum_pattern_masks/line_art",
                   'GRID': "rizum_pattern_masks/grid"}
_DEFAULT_MARK = ".default"           # in each preset folder: the starred preset's file name


def _preset_dir(kind, create=False):
    return bpy.utils.user_resource('SCRIPTS', path=os.path.join("presets", _PRESET_SUBDIRS[kind]),
                                   create=create)


def _preset_files(kind):
    """[(file stem, path)] of the saved presets of a kind, in natural order."""
    d = _preset_dir(kind)
    if not d or not os.path.isdir(d):
        return []
    out = [(f[:-3], os.path.join(d, f)) for f in os.listdir(d)
           if f.endswith(".py") and not f.startswith(".")]
    out.sort(key=lambda t: tuple(int(x) if x.isdigit() else x
                                 for x in re.split(r"(\d+)", t[0].lower())))
    return out


def _default_stem(kind):
    """File stem of the starred preset of a kind, or None."""
    d = _preset_dir(kind)
    try:
        with open(os.path.join(d, _DEFAULT_MARK), encoding="utf-8") as f:
            stem = f.read().strip()
    except (OSError, TypeError):
        return None
    return stem if stem and os.path.isfile(os.path.join(d, stem + ".py")) else None


def _default_preset(kind):
    stem = _default_stem(kind)
    return os.path.join(_preset_dir(kind), stem + ".py") if stem else None


def _preset_target(ob, kind):
    """What a preset of this kind sets: the selected layer if it is of that
    kind (stitch presets: else the first stitch layer); None otherwise."""
    s = ob.stitch_gen
    if kind == 'STITCH':
        return _stitch_item(s)
    if 0 <= s.line_index < len(s.lines):
        item = s.lines[s.line_index]
        if not _is_stitch(item) and (kind == 'GRID') == _is_grid(item):
            return item
    return None


def _apply_preset(context, ob, kind, filepath):
    """Set the add-on's defaults, then the preset's values over them (so a
    preset saved before a setting existed leaves that setting at its default,
    not at whatever the last preset had). No preset: the defaults only."""
    data = _preset_target(ob, kind)
    if data is None:
        return False
    for name in _DEFAULT_PROPS[kind]:
        # stitch presets name the object's settings, which stand for the layer's
        data.property_unset(_STITCH_MAP[name] if kind == 'STITCH' else name)
    if filepath:
        # preset files act on the active object
        with context.temp_override(active_object=ob, object=ob):
            bpy.utils.execfile(filepath)
    return True


def _apply_default_to_new(context, ob, kind):
    """A new layer starts with the starred preset, if there is one."""
    path = _default_preset(kind)
    if path:
        try:
            _apply_preset(context, ob, kind, path)
        except Exception:
            traceback.print_exc()


class _PresetApplyBase:
    bl_options = {'UNDO', 'INTERNAL'}     # no Adjust Last Operation panel: nothing to adjust
    kind: EnumProperty(items=_PRESET_KINDS, options={'HIDDEN', 'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return _source_object(context) is not None

    def apply(self, context, filepath):
        ob = _source_object(context)
        layers._MUTE = True
        try:
            ok = _apply_preset(context, ob, self.kind, filepath)
        except Exception as e:
            self.report({'ERROR'}, f"{type(e).__name__}: {e}")
            ok = False
        finally:
            layers._MUTE = False
        if not ok:
            return {'CANCELLED'}
        regenerate(ob, context.scene)
        return {'FINISHED'}


class STITCHGEN_OT_reset_defaults(_PresetApplyBase, bpy.types.Operator):
    """Set this layer's settings back to the default: the starred preset, or the add-on's own"""
    bl_idname = "stitch_gen.reset_defaults"
    bl_label = "Default"

    def execute(self, context):
        return self.apply(context, _default_preset(self.kind))


class STITCHGEN_OT_apply_preset(_PresetApplyBase, bpy.types.Operator):
    """Apply this preset"""
    bl_idname = "stitch_gen.apply_preset"
    bl_label = "Apply Preset"
    filepath: StringProperty(options={'HIDDEN', 'SKIP_SAVE'})

    def execute(self, context):
        if not os.path.isfile(self.filepath):
            return {'CANCELLED'}
        return self.apply(context, self.filepath)


class STITCHGEN_OT_preset_default(bpy.types.Operator):
    ("Use this preset as the default: new layers start with it, and Default applies it. "
     "Click again to go back to the add-on's own default")
    bl_idname = "stitch_gen.preset_default"
    bl_label = "Use as Default"
    bl_options = {'INTERNAL'}
    kind: EnumProperty(items=_PRESET_KINDS)
    name: StringProperty(options={'HIDDEN', 'SKIP_SAVE'})

    def execute(self, context):
        d = _preset_dir(self.kind, create=True)
        mark = os.path.join(d, _DEFAULT_MARK)
        try:
            if _default_stem(self.kind) == self.name:
                os.remove(mark)
            else:
                with open(mark, "w", encoding="utf-8") as f:
                    f.write(self.name)
        except OSError as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}
        for area in context.screen.areas if context.screen else ():
            area.tag_redraw()
        return {'FINISHED'}


class _DefaultsFirst:
    """Preset list: Default on top, then the saved presets (apply, star as
    the default, remove), then a name field and + to save the current
    settings."""
    reset_kind = 'STITCH'

    def draw(self, context):
        lay = self.layout
        lay.emboss = 'PULLDOWN_MENU'
        # run the buttons directly: + saves under the typed name, no second dialog
        lay.operator_context = 'EXEC_DEFAULT'
        kind = self.reset_kind
        lay.operator("stitch_gen.reset_defaults", text="Default",
                     text_ctxt=i18n.CTX).kind = kind
        files = _preset_files(kind)
        if files:
            lay.separator()
            starred = _default_stem(kind)
            col = lay.column(align=True)
            for stem, path in files:
                row = col.row(align=True)
                op = row.operator("stitch_gen.apply_preset", text=stem, translate=False)
                op.kind, op.filepath = kind, path
                op = row.operator("stitch_gen.preset_default", text="",
                                  icon='SOLO_ON' if stem == starred else 'SOLO_OFF')
                op.kind, op.name = kind, stem
                op = row.operator(self.preset_add_operator, text="", icon='REMOVE')
                op.name, op.remove_name = stem, True
        lay.separator()
        wm = bpy.data.window_managers[0]
        row = lay.row()
        sub = row.row()
        sub.emboss = 'NORMAL'
        sub.prop(wm, "preset_name", text="")
        row.operator(self.preset_add_operator, text="", icon='ADD').name = wm.preset_name


class STITCHGEN_OT_stitch_preset_add(_PresetPoll, AddPresetBase, bpy.types.Operator):
    """Save the stitch settings as a preset, or remove the selected preset"""
    bl_idname = "stitch_gen.stitch_preset_add"
    bl_label = "Add Stitch Preset"
    preset_menu = "STITCHGEN_MT_stitch_presets"
    preset_subdir = "rizum_pattern_masks/stitches"
    preset_defines = _PRESET_DEFINES[:2]
    preset_values = _STITCH_VALUES


class STITCHGEN_OT_line_preset_add(_PresetPoll, AddPresetBase, bpy.types.Operator):
    """Save this line art layer's settings as a preset, or remove the selected preset"""
    bl_idname = "stitch_gen.line_preset_add"
    bl_label = "Add Line Art Preset"
    preset_menu = "STITCHGEN_MT_line_presets"
    preset_subdir = "rizum_pattern_masks/line_art"
    preset_defines = _PRESET_DEFINES
    preset_values = _LINE_VALUES


_GRID_VALUES = ["layer.grid_from", "layer.grid_along", "layer.grid_angle", "layer.grid_cell",
                "layer.grid_wobble", "layer.grid_layout"]


class STITCHGEN_OT_grid_preset_add(_PresetPoll, AddPresetBase, bpy.types.Operator):
    """Save this grid layer's settings as a preset, or remove the selected preset"""
    bl_idname = "stitch_gen.grid_preset_add"
    bl_label = "Add Grid Preset"
    preset_menu = "STITCHGEN_MT_grid_presets"
    preset_subdir = "rizum_pattern_masks/grid"
    preset_defines = _PRESET_DEFINES
    preset_values = _GRID_VALUES


class STITCHGEN_MT_grid_presets(bpy.types.Menu):
    bl_label = "Grid Presets"
    preset_subdir = "rizum_pattern_masks/grid"
    preset_operator = "script.execute_preset"
    draw = bpy.types.Menu.draw_preset


class STITCHGEN_MT_stitch_presets(bpy.types.Menu):
    bl_label = "Stitch Presets"
    preset_subdir = "rizum_pattern_masks/stitches"
    preset_operator = "script.execute_preset"
    draw = bpy.types.Menu.draw_preset


class STITCHGEN_MT_line_presets(bpy.types.Menu):
    bl_label = "Line Art Presets"
    preset_subdir = "rizum_pattern_masks/line_art"
    preset_operator = "script.execute_preset"
    draw = bpy.types.Menu.draw_preset


class STITCHGEN_PT_stitch_presets(_DefaultsFirst, PresetPanel, bpy.types.Panel):
    bl_label = "Stitch Presets"
    preset_subdir = "rizum_pattern_masks/stitches"
    preset_operator = "script.execute_preset"
    preset_add_operator = "stitch_gen.stitch_preset_add"


class STITCHGEN_PT_grid_presets(_DefaultsFirst, PresetPanel, bpy.types.Panel):
    bl_label = "Grid Presets"
    reset_kind = 'GRID'
    preset_subdir = "rizum_pattern_masks/grid"
    preset_operator = "script.execute_preset"
    preset_add_operator = "stitch_gen.grid_preset_add"


class STITCHGEN_PT_line_presets(_DefaultsFirst, PresetPanel, bpy.types.Panel):
    bl_label = "Line Art Presets"
    reset_kind = 'LINE'
    preset_subdir = "rizum_pattern_masks/line_art"
    preset_operator = "script.execute_preset"
    preset_add_operator = "stitch_gen.line_preset_add"
