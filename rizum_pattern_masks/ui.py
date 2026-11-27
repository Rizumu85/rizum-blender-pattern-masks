# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Rizum
"""Viewport panel, layer list, preview colors and icons."""

import os
import traceback

import numpy as np
import bpy
from bpy.props import IntProperty

from . import core, i18n
from .i18n import iface
from .layers import (
    _edge_spec, _is_grid, _is_stitch, _layer_by_attr, _layer_icon, _source_object, _stitches_on,
    _uses_addon,
)
from .migrate import UI_VERSION, _defer_ensure
from .ops_bake import _bake_count, _bake_targets
from .props import _display_name
from .rebuild import unrolled


_icons = {"coll": None}


# The add-on's own icons (icons.npz, drawn by tools/make_icons.py at every icon
# size) for its own buttons; Blender's stay for the common ones. They are
# shapes, painted in the theme's text colour like Blender's own icons.
_FALLBACK = {"marks": 'EDGESEL', "preset": 'PRESET', "corners": 'VERTEXSEL',
             "link": 'LINKED', "folder": 'FILE_FOLDER', "reveal": 'FOLDER_REDIRECT'}
_shapes = {}             # "masks": icon masks by "<name>_<px>"


def _icon_masks():
    """All icon masks (icons.npz, from tools/make_icons.py), loaded once."""
    if "masks" not in _shapes:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons.npz")
        try:
            with np.load(path) as f:
                _shapes["masks"] = {k: f[k] for k in f.files}
        except Exception:
            traceback.print_exc()
            _shapes["masks"] = {}
    return _shapes["masks"]


def _icon(name, widget="wcol_regular", on=False):
    """icon= / icon_value= keywords for one of the add-on's icons, coloured as
    Blender colours its own: the widget's text colour, its selected text
    colour for a toggle that is on, and the theme's icon border if it has one."""
    coll = _icons["coll"]
    if coll is None:
        return {"icon": _FALLBACK[name]}
    prefs = bpy.context.preferences
    # Blender's icon size now: 16 px times the UI scale (with the system's display
    # scaling); drawn at exactly that size, the icon is not resampled (soft)
    size = min(max(round(16.0 * getattr(prefs.system, "ui_scale", 1.0)), 12), 64)
    mask = _icon_masks().get(f"{name}_{size}")
    if mask is None:
        return {"icon": _FALLBACK[name]}
    shape = mask[::-1] / 255.0                     # previews start at the bottom row
    ui = prefs.themes[0].user_interface
    wcol = getattr(ui, widget, ui.wcol_regular)
    rgb = tuple(min(max(float(c), 0.0), 1.0) for c in (wcol.text_sel if on else wcol.text))
    edge = min(max(float(getattr(ui, "icon_border_intensity", 0.0)), 0.0), 1.0)
    if sum(rgb) < 1.5:
        edge = 0.0                        # a rim only keeps light icons readable
    key = "i_%s_%d_%02x%02x%02x_%02x" % ((name, size) + tuple(round(c * 255) for c in rgb)
                                         + (round(edge * 255),))
    hit = coll.get(key)
    if hit is None:
        n = shape.shape[0]
        a = shape
        b = np.zeros_like(a)
        if edge > 0:                      # a dark rim, about a pixel wide on screen
            r = max(1, round(n / 16))
            for dy in range(-r, r + 1):
                for dx in range(-r, r + 1):
                    if dx * dx + dy * dy <= r * r + r:
                        b = np.maximum(b, np.roll(np.roll(a, dy, 0), dx, 1))
            b = b * edge * (1.0 - a)
        px = np.empty((n, n, 4), np.float32)
        px[..., :3] = np.asarray(rgb)[None, None, :] * a[..., None]     # premultiplied
        px[..., 3] = a + b
        hit = coll.new(key)
        hit.icon_size = (n, n)
        hit.icon_pixels_float = px.ravel()
    return {"icon_value": hit.icon_id}


def _color_icon(rgba):
    """Icon id of a rounded square in this color (cached per color)."""
    coll = _icons["coll"]
    if coll is None:
        return 0
    rgb = tuple(min(max(float(c), 0.0), 1.0) for c in rgba[:3])
    key = "c%02x%02x%02x" % tuple(round(c * 255) for c in rgb)
    hit = coll.get(key)
    if hit is None:
        n = 32
        y, x = np.mgrid[0:n, 0:n] + 0.5
        r, half = 6.0, 13.0                   # corner radius, half size (in 32 px)
        q = np.maximum(np.abs(np.stack([x - n / 2, y - n / 2])) - (half - r), 0.0)
        a = np.clip(r + 0.5 - np.hypot(q[0], q[1]), 0.0, 1.0)
        # Display colors are linear; icons are drawn as given (sRGB)
        srgb = [c * 12.92 if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055 for c in rgb]
        px = np.empty((n, n, 4), np.float32)
        px[..., :3] = np.asarray(srgb)[None, None, :] * a[..., None]   # premultiplied
        px[..., 3] = a
        hit = coll.new(key)
        hit.icon_size = (n, n)
        hit.icon_pixels_float = px.ravel()
    return hit.icon_id


class STITCHGEN_OT_edit_color(bpy.types.Operator):
    """Preview color in the viewport (not baked)"""
    bl_idname = "stitch_gen.edit_color"
    bl_label = "Color"
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}
    index: IntProperty()

    def _target(self, context):
        ob = _source_object(context)
        if ob is None or not 0 <= self.index < len(ob.stitch_gen.lines):
            return None, None
        s = ob.stitch_gen
        item = s.lines[self.index]
        return item, "color"

    def invoke(self, context, event):
        return context.window_manager.invoke_popup(self, width=200)

    def draw(self, context):
        data, prop = self._target(context)
        if data is not None:
            self.layout.template_color_picker(data, prop, value_slider=True)
            self.layout.prop(data, prop, text="")

    def execute(self, context):
        return {'FINISHED'}


class STITCHGEN_UL_lines(bpy.types.UIList):
    """Layer rows: name, preview color, marked edges shown, result shown."""

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname,
                  index=0, flt_flag=0):
        s = data
        on = item.enabled
        row = layout.row(align=True)
        name = row.row(align=True)
        name.active = on
        name.prop(item, "label", text="", emboss=False, icon=_layer_icon(item))
        # a link when this layer follows another one, so the list shows who follows whom
        ref = _layer_by_attr(s, item.ref_attr) if item.ref_attr else None
        if ref is not None and ref != item:
            row.label(text="", **_icon("link", "wcol_list_item"))
        # The color as an icon like the toggles next to it (a framed swatch
        # gets joined with the swatches of the rows above and below).
        op = row.operator("stitch_gen.edit_color", text="", emboss=False,
                          icon_value=_color_icon(item.color))
        op.index = index
        marks = row.row(align=True)
        marks.active = item.show_marks and context.scene.stitch_gen_marks
        marks.prop(item, "show_marks", text="", emboss=False,
                   **_icon("marks", "wcol_list_item", item.show_marks))
        row.prop(item, "enabled", text="", icon='HIDE_OFF' if on else 'HIDE_ON', emboss=False)


def _unrolled_now(ob, s, item):
    """Is the Unrolled layout of this grid layer worked out? (Only looks:
    a panel can't work anything out.)"""
    entry = core._cache.get(ob.name_full)
    gc = entry["grid_coords"].get(core._as_spec(_edge_spec(s, item))) if entry else None
    return gc is not None and unrolled(gc)


# -- panel ---------------------------------------------------------------------


def _marks_toggle(row, data, prop, icon):
    """Show / hide toggle for marks at the end of a tool row (dim when off)."""
    sub = row.row(align=True)
    sub.active = getattr(data, prop) and bpy.context.scene.stitch_gen_marks
    sub.prop(data, prop, text="", emboss=False, **_icon(icon, on=getattr(data, prop)))


def _tool_row(layout, label, ctxt=None, tail=False):
    """A row of icon buttons with a label in the property label column. With
    tail, also a slot at the right edge (row, slot), so the icons at the ends
    of the rows line up."""
    split = layout.split(factor=0.4)
    left = split.row()
    left.alignment = 'RIGHT'
    if ctxt:
        left.label(text=label, text_ctxt=ctxt)
    else:
        left.label(text=label)
    if not tail:
        return split.row(align=True)
    right = split.row()
    row = right.row(align=True)
    row.alignment = 'LEFT'
    end = right.row()
    end.alignment = 'RIGHT'                # against the right edge in every row
    end.emboss = 'NONE'
    return row, end


def _icon_group(row, n):
    """n icon buttons of one fixed width, so the + - select columns of the
    Edges and Sharp Corners rows line up whatever follows them."""
    sub = row.row(align=True)
    sub.ui_units_x = 1.2 * n
    return sub


class VIEW3D_PT_stitch_gen(bpy.types.Panel):
    bl_label = "Rizum Pattern Masks"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Pattern Masks"

    @classmethod
    def poll(cls, context):
        return _source_object(context) is not None

    def draw_header_preset(self, context):
        # what applies beyond the selected layer: every layer's marks (the
        # scene) and the preview of this object; Update only while not live
        ob = _source_object(context)
        row = self.layout.row(align=True)
        row.prop(context.scene, "stitch_gen_marks", text="",
                 **_icon("marks", "wcol_toggle", context.scene.stitch_gen_marks))
        if ob is not None and len(ob.stitch_gen.lines):
            s = ob.stitch_gen
            row.separator()
            if not s.live:
                row.operator("stitch_gen.update", text="", icon='FILE_REFRESH')
            row.prop(s, "live", text="", icon='PLAY')
        self.layout.separator(factor=0.6)        # clear of the panel's drag handle

    def draw(self, context):
        ob = _source_object(context)
        s = ob.stitch_gen
        lay = self.layout
        lay.use_property_split = True
        lay.use_property_decorate = False
        if s.ui_version < UI_VERSION and _uses_addon(ob):
            _defer_ensure(ob)          # set up by an older version: bring it up to date

        # the list is as tall as the buttons beside it, whatever it holds, so
        # the panel below doesn't move when a layer is added
        row = lay.row()
        row.template_list("STITCHGEN_UL_lines", "", s, "lines", s, "line_index", rows=5,
                          sort_lock=True)     # the order is the drawing order: no sorting
        ops = row.column(align=True)
        ops.menu("STITCHGEN_MT_add_layer", text="", icon='ADD')
        ops.operator("stitch_gen.line_remove", text="", icon='REMOVE')
        ops.separator()
        ops.menu("STITCHGEN_MT_list_extras", text="", icon='DOWNARROW_HLT')
        ops.separator()
        ops.operator("stitch_gen.layer_move", text="", icon='TRIA_UP').direction = 'UP'
        ops.operator("stitch_gen.layer_move", text="", icon='TRIA_DOWN').direction = 'DOWN'
        if not len(s.lines):
            return                     # nothing to set up until there is a layer
        if s.status:
            lay.label(text=s.status, icon='ERROR', translate=False)

        item = s.lines[s.line_index] if 0 <= s.line_index < len(s.lines) else s.lines[0]
        stitch = _is_stitch(item)
        is_grid = _is_grid(item)

        # marking, in working order: the selected layer's edges, the corners,
        # which all layers share (a corner is a vertex), then the layer's side
        mark = lay.column()
        r, end = _tool_row(mark, "Edges", tail=True)
        r = _icon_group(r, 4)
        r.operator("stitch_gen.path_add", text="", icon='ADD')
        r.operator("stitch_gen.path_remove", text="", icon='REMOVE')
        r.operator("stitch_gen.path_select", text="", icon='RESTRICT_SELECT_OFF')
        r.operator("stitch_gen.path_clear", text="", icon='X')
        # Reference: a small menu at the end of the row (most layers never
        # use it); a row of its own only while picking or once it is set
        # Reference: a small menu at the end of the row, pressed while one is
        # set (its tooltip names it); picking shows its hint in the status bar.
        # No rows come and go here: the rows below stay where the hand knows them.
        ref = _layer_by_attr(s, item.ref_attr) if item.ref_attr else None
        if ref is not None and ref != item:
            sub = end.row()
            sub.emboss = 'NORMAL'
            sub.operator("stitch_gen.reference_menu", text="", depress=True,
                         **_icon("link", "wcol_toggle", True))
        else:
            end.operator("stitch_gen.reference_menu", text="", **_icon("link"))
        if not is_grid:
            r, end = _tool_row(mark, "Sharp Corners", tail=True)
            icons = _icon_group(r, 3)
            icons.operator("stitch_gen.corner_mark", text="", icon='ADD')
            icons.operator("stitch_gen.corner_clear", text="", icon='REMOVE')
            icons.operator("stitch_gen.corner_select", text="", icon='RESTRICT_SELECT_OFF')
            r.operator("stitch_gen.corner_detect", text="Auto")
            _marks_toggle(end, s, "show_corners", "corners")
            mark.prop(item, "flip")

        # the selected layer's own settings, with its presets
        header, body = lay.panel("stitch_gen_layer", default_closed=False)
        header.label(text=_display_name(item), icon=_layer_icon(item), translate=False)
        pr = header.row()
        pr.alignment = 'RIGHT'
        pr.emboss = 'NONE'                  # a plain icon, not a dark popup button
        pr.popover(panel="STITCHGEN_PT_stitch_presets" if stitch else
                   "STITCHGEN_PT_grid_presets" if is_grid else "STITCHGEN_PT_line_presets",
                   text="", **_icon("preset"))
        if body and is_grid:
            # squares lined up with the marked edge: where, then turn and size
            body = body.column()
            body.active = item.enabled
            col = body.column(align=True)
            col.prop(item, "grid_from")
            col.prop(item, "grid_along")
            col = body.column(align=True)
            col.prop(item, "grid_angle")
            col.prop(item, "grid_cell")
            col.prop(item, "grid_wobble", slider=True)
            body.prop(item, "grid_layout")
            if item.grid_layout == 'UNROLLED' and not _unrolled_now(ob, s, item):
                body.operator("stitch_gen.unroll", icon='UV')
        elif body:
            # Same groups, same order for all: where the line runs, then its shape.
            body = body.column()
            body.active = item.enabled
            col = body.column(align=True)
            col.prop(item, "inset" if stitch else "offset")
            col.prop(item, "corner_inset")
            body.prop(item, "stitch_smooth" if stitch else "smooth")
            col = body.column(align=True)
            if stitch:
                col = body.column()
                col.row().prop(item, "style", expand=True)
                col = body.column(align=True)
            col.prop(item, "thread_width" if stitch else "width")
            if stitch and item.style == 'ZIGZAG':
                col.prop(item, "length")
                col.prop(item, "zigzag_height")
            elif stitch:
                col.prop(item, "length")
                col.prop(item, "gap")
                col.prop(item, "roundness_pct", slider=True)
                body.prop(item, "even")

        wm = context.window_manager

        def bake_button(where):
            if wm.stitch_gen_baking:
                where.progress(factor=wm.stitch_gen_bake_progress, type='BAR',
                               text=wm.stitch_gen_bake_label)
                return
            n = sum(_bake_count(o) for o in _bake_targets(context))
            where.operator("stitch_gen.bake", icon='RENDER_STILL',
                           text=(iface("Bake 1 Mask") if n == 1 else
                                 iface("Bake {} Masks").format(n) if n else iface("Bake Masks")))

        header, body = lay.panel("stitch_gen_bake", default_closed=False)
        header.label(text="Bake")
        if not body:                       # folded away: the button stays at hand,
            end = header.row()             # just its icon (the title says what it does)
            end.alignment = 'RIGHT'
            if wm.stitch_gen_baking:
                bake_button(end)
            else:
                end.operator("stitch_gen.bake", text="", icon='RENDER_STILL')
        if body:
            body.prop(s, "resolution")
            uvl = core.pick_uv(ob.data, s.uv_map)
            if uvl is None:
                text = "-"
            elif s.uv_map in ob.data.uv_layers:
                text = s.uv_map
            else:
                text = iface("Active: {}").format(uvl.name)
            _tool_row(body, "UV Map").menu("STITCHGEN_MT_uv_maps", text=text, icon='GROUP_UVS',
                                            translate=False)
            row = body.row(align=True)
            row.prop(s, "output_dir")
            row.operator("stitch_gen.pick_folder", text="", **_icon("folder"))
            row.operator("stitch_gen.open_folder", text="", **_icon("reveal"))
            # a menu, not three buttons: "Transparent" doesn't fit a third of
            # the value column at the sidebar's usual width
            body.prop(s, "background")
            if _stitches_on(s) and s.dash_count > 0:      # line art doesn't use these
                h2, b2 = body.panel("stitch_gen_bake_render", default_closed=True)
                h2.label(text="Stitches: Samples & Device", text_ctxt=i18n.CTX)
                if b2:
                    b2.prop(s, "samples")
                    b2.row().prop(s, "device", expand=True)
                    if s.device == 'CPU':
                        b2.prop(s, "cpu_usage")
            if wm.stitch_gen_baking:       # the button below, greyed out, keeps its place
                body.progress(factor=wm.stitch_gen_bake_progress, type='BAR',
                              text=wm.stitch_gen_bake_label)
                n = _bake_count(ob)
                body.operator("stitch_gen.bake", icon='RENDER_STILL',
                              text=(iface("Bake 1 Mask") if n == 1 else
                                    iface("Bake {} Masks").format(n) if n else
                                    iface("Bake Masks")))
            else:
                bake_button(body)
