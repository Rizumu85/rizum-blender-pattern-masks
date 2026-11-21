# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Rizum
"""Operators and menus for managing layers, references and output settings."""

import os
import traceback

import bpy
import bmesh
from bpy.props import BoolProperty, EnumProperty, StringProperty

from . import core, grid, i18n, layers, overlay, preview, props
from .i18n import iface, rpt
from .layers import (
    GRID_ICON, LINE_ICON, STITCH_ICON, _edge_spec, _is_grid, _layer_attr, _layer_by_attr,
    _layer_icon, _new_line_layer, _new_stitch_layer, _source_object, _uses_addon,
)
from .migrate import UI_VERSION, _ensure_layers
from .presets import _apply_default_to_new
from .props import StitchGenSettings, _display_name
from .rebuild import regenerate


def _inherit_bake_settings(obj, scene):
    """A new object bakes into the same folder as the others in the scene, at
    the size last picked (so a size you changed carries on to the next
    object); its other bake settings start at their defaults."""
    s = obj.stitch_gen
    default = StitchGenSettings.bl_rna.properties["output_dir"].default
    src = next((o.stitch_gen for o in scene.objects
                if o != obj and o.type == 'MESH' and _uses_addon(o)
                and o.stitch_gen.output_dir != default), None)
    size = scene.stitch_gen_last_size or (src.resolution if src is not None else "")
    layers._MUTE = True
    try:
        if src is not None:
            s.output_dir = src.output_dir
        if size in {"1024", "2048", "4096", "8192"}:
            s.resolution = size
    finally:
        layers._MUTE = False


class STITCHGEN_OT_update(bpy.types.Operator):
    """Rebuild the stitches"""
    bl_idname = "stitch_gen.update"
    bl_label = "Update"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return _source_object(context) is not None

    def execute(self, context):
        ob = _source_object(context)
        core.drop_cache(ob)
        regenerate(ob, context.scene)
        if ob.stitch_gen.status:
            self.report({'ERROR'}, ob.stitch_gen.status)
            return {'CANCELLED'}
        return {'FINISHED'}


class STITCHGEN_OT_line_add(bpy.types.Operator):
    """Add a line art layer; while it is selected, the edge buttons mark its edges"""
    bl_idname = "stitch_gen.line_add"
    bl_label = "Add Line"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return _source_object(context) is not None

    def execute(self, context):
        ob = _source_object(context)
        _ensure_layers(ob)
        first = not _uses_addon(ob)
        layers._MUTE = True
        try:
            _new_line_layer(ob)
            _apply_default_to_new(context, ob, 'LINE')
            ob.stitch_gen.ui_version = UI_VERSION
        finally:
            layers._MUTE = False
        if first:
            _inherit_bake_settings(ob, context.scene)
        preview.note(ob)
        regenerate(ob, context.scene)
        return {'FINISHED'}


class STITCHGEN_OT_grid_add(bpy.types.Operator):
    """Add a checkered layer: squares that follow the mesh's loops out from a marked edge"""
    bl_idname = "stitch_gen.grid_add"
    bl_label = "Add Grid"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return _source_object(context) is not None

    def execute(self, context):
        ob = _source_object(context)
        _ensure_layers(ob)
        first = not _uses_addon(ob)
        layers._MUTE = True
        try:
            _new_line_layer(ob, 'GRID')
            _apply_default_to_new(context, ob, 'GRID')
            ob.stitch_gen.ui_version = UI_VERSION
        finally:
            layers._MUTE = False
        if first:
            _inherit_bake_settings(ob, context.scene)
        preview.note(ob)
        regenerate(ob, context.scene)
        return {'FINISHED'}


class STITCHGEN_OT_stitch_add(bpy.types.Operator):
    """Add a stitch layer; while it is selected, the edge buttons mark its edges"""
    bl_idname = "stitch_gen.stitch_add"
    bl_label = "Add Stitches"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return _source_object(context) is not None

    def execute(self, context):
        ob = _source_object(context)
        s = ob.stitch_gen
        _ensure_layers(ob)
        first = not _uses_addon(ob)
        layers._MUTE = True
        try:
            _new_stitch_layer(ob)
            _apply_default_to_new(context, ob, 'STITCH')
            s.ui_version = UI_VERSION
        finally:
            layers._MUTE = False
        if first:
            _inherit_bake_settings(ob, context.scene)
        preview.note(ob)
        regenerate(ob, context.scene)
        return {'FINISHED'}


class STITCHGEN_OT_unroll(bpy.types.Operator):
    ("Work out the Unrolled layout of the selected grid layer's piece "
     "(a few seconds on a big piece)")
    bl_idname = "stitch_gen.unroll"
    bl_label = "Unroll"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        _ob, item = _selected_layer(context)
        return item is not None and _is_grid(item) and item.grid_layout == 'UNROLLED'

    def execute(self, context):
        ob, item = _selected_layer(context)
        s = ob.stitch_gen
        if regenerate(ob, context.scene) is None:
            self.report({'ERROR'}, s.status)
            return {'CANCELLED'}
        gc = core.grid_coords(core._cache[ob.name_full], _edge_spec(s, item))
        if not len(gc.faces):
            self.report({'WARNING'}, rpt("Mark this grid's edge first"))
            return {'CANCELLED'}
        wm = context.window_manager
        wm.progress_begin(0, grid.FLAT_ROUNDS)
        gc.progress = lambda k, n: wm.progress_update(k)
        try:
            gc._unrolled()
        except Exception as e:
            traceback.print_exc()
            self.report({'ERROR'}, f"{type(e).__name__}: {e}")
            return {'CANCELLED'}
        finally:
            gc.progress = None
            wm.progress_end()
        regenerate(ob, context.scene)
        return {'FINISHED'}


class STITCHGEN_MT_add_layer(bpy.types.Menu):
    bl_label = "Add Layer"

    def draw(self, context):
        lay = self.layout
        lay.operator("stitch_gen.stitch_add", text="Stitches", text_ctxt=i18n.CTX,
                     icon=STITCH_ICON)
        lay.operator("stitch_gen.line_add", text="Line Art", text_ctxt=i18n.CTX, icon=LINE_ICON)
        lay.operator("stitch_gen.grid_add", text="Grid", text_ctxt=i18n.CTX, icon=GRID_ICON)


class STITCHGEN_OT_clear_scene(bpy.types.Operator):
    """Remove all layers, with their marked edges and corners, from every object in the scene"""
    bl_idname = "stitch_gen.clear_scene"
    bl_label = "Clear All Layers"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        if any(o.type == 'MESH' and _uses_addon(o) for o in context.scene.objects):
            return True
        cls.poll_message_set(rpt("Nothing to clear"))
        return False

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(
            self, event, title=iface("Clear All Layers"), icon='WARNING',
            message=iface("Remove all layers, marked edges and corners "
                          "from every object in this scene?"),
            confirm_text=iface("Clear"))

    def execute(self, context):
        obs = [o for o in context.scene.objects if o.type == 'MESH' and _uses_addon(o)]
        layers._MUTE = True
        try:
            for ob in obs:
                s = ob.stitch_gen
                s.lines.clear()
                s.line_index = 0
                s.status = ""
                s.dash_count = 0
                _drop_marks(ob)
                core.drop_cache(ob)
                overlay.invalidate(ob)
                preview.forget(ob)
        finally:
            layers._MUTE = False
        self.report({'INFO'}, rpt("Cleared {} objects").format(len(obs)))
        return {'FINISHED'}


def _drop_marks(ob):
    """Remove the add-on's edge and corner attributes from the mesh."""
    me = ob.data

    def ours(n):
        return n == core.PATH_ATTR or n == core.LINE_ATTR or n.startswith(core.LINE_ATTR + "_")

    if me.is_editmode:
        bm = bmesh.from_edit_mesh(me)
        for n in [n for n in bm.edges.layers.int.keys() if ours(n)]:
            bm.edges.layers.int.remove(bm.edges.layers.int[n])
        lay = bm.verts.layers.int.get(core.CORNER_ATTR)
        if lay is not None:
            bm.verts.layers.int.remove(lay)
        bmesh.update_edit_mesh(me, loop_triangles=False, destructive=False)
        return
    for n in [n for n, a in me.attributes.items()
              if (ours(n) and a.domain == 'EDGE')
              or (n == core.CORNER_ATTR and a.domain == 'POINT')]:
        me.attributes.remove(me.attributes[n])


class STITCHGEN_OT_layer_move(bpy.types.Operator):
    ("Move the selected layer up or down the list. "
     "In the viewport, a layer higher up is drawn over the ones below")
    bl_idname = "stitch_gen.layer_move"
    bl_label = "Move Layer"
    bl_options = {'REGISTER', 'UNDO'}
    direction: EnumProperty(items=[('UP', "Up", ""), ('DOWN', "Down", "")], options={'HIDDEN'})

    @classmethod
    def poll(cls, context):
        ob = _source_object(context)
        return ob is not None and len(ob.stitch_gen.lines) > 1

    def execute(self, context):
        s = _source_object(context).stitch_gen
        i = s.line_index
        j = i - 1 if self.direction == 'UP' else i + 1
        if not (0 <= i < len(s.lines) and 0 <= j < len(s.lines)):
            return {'CANCELLED'}
        s.lines.move(i, j)
        s.line_index = j
        preview.redraw()
        return {'FINISHED'}


class STITCHGEN_MT_list_extras(bpy.types.Menu):
    bl_label = "Layers"

    def draw(self, context):
        self.layout.operator("stitch_gen.clear_scene", icon='TRASH')


class STITCHGEN_OT_line_remove(bpy.types.Operator):
    """Remove the selected layer together with its marked edges"""
    bl_idname = "stitch_gen.line_remove"
    bl_label = "Remove Layer"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        ob = _source_object(context)
        if ob is None:
            return False
        s = ob.stitch_gen
        return 0 <= s.line_index < len(s.lines)

    def execute(self, context):
        ob = _source_object(context)
        s = ob.stitch_gen
        i = s.line_index
        name = _layer_attr(s.lines[i])
        s.lines.remove(i)
        for l in s.lines:
            if l.ref_attr == name:
                l.ref_attr = ""
        s.line_index = max(min(i, len(s.lines) - 1), 0)
        if not any(_layer_attr(l) == name for l in s.lines):   # its edges go with it
            me = ob.data
            if me.is_editmode:
                bm = bmesh.from_edit_mesh(me)
                lay = bm.edges.layers.int.get(name)
                if lay is not None:
                    bm.edges.layers.int.remove(lay)
                    bmesh.update_edit_mesh(me, loop_triangles=False, destructive=False)
            elif name in me.attributes:
                me.attributes.remove(me.attributes[name])
        regenerate(ob, context.scene)
        return {'FINISHED'}


class STITCHGEN_OT_pick_folder(bpy.types.Operator):
    """Choose the folder for the mask PNGs"""
    bl_idname = "stitch_gen.pick_folder"
    bl_label = "Choose Folder"
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}
    directory: StringProperty(subtype='DIR_PATH', options={'HIDDEN', 'SKIP_SAVE'})
    filter_folder: BoolProperty(default=True, options={'HIDDEN', 'SKIP_SAVE'})
    relative_path: BoolProperty(name="Relative Path", default=True,
                                description="Keep the folder relative to the .blend file")

    @classmethod
    def poll(cls, context):
        return _source_object(context) is not None

    def invoke(self, context, event):
        self.directory = bpy.path.abspath(_source_object(context).stitch_gen.output_dir)
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        path = self.directory
        if self.relative_path and bpy.data.filepath:
            try:
                path = bpy.path.relpath(path)
            except ValueError:            # on another drive
                pass
        _source_object(context).stitch_gen.output_dir = path
        return {'FINISHED'}


class STITCHGEN_OT_open_folder(bpy.types.Operator):
    """Open the mask folder in the file manager"""
    bl_idname = "stitch_gen.open_folder"
    bl_label = "Open Folder"

    @classmethod
    def poll(cls, context):
        ob = _source_object(context)
        if ob is None:
            return False
        if os.path.isdir(bpy.path.abspath(ob.stitch_gen.output_dir)):
            return True
        cls.poll_message_set(rpt("Nothing baked here yet"))
        return False

    def execute(self, context):
        folder = _source_object(context).stitch_gen.output_dir
        bpy.ops.wm.path_open(filepath=bpy.path.abspath(folder))
        return {'FINISHED'}


class STITCHGEN_OT_set_uv_map(bpy.types.Operator):
    """Bake into this UV map"""
    bl_idname = "stitch_gen.set_uv_map"
    bl_label = "Set UV Map"
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}
    name: StringProperty()

    @classmethod
    def poll(cls, context):
        return _source_object(context) is not None

    def execute(self, context):
        _source_object(context).stitch_gen.uv_map = self.name
        return {'FINISHED'}


def _layer_label(layer):
    return _display_name(layer)


def _selected_layer(context):
    ob = _source_object(context)
    if ob is None:
        return None, None
    s = ob.stitch_gen
    if 0 <= s.line_index < len(s.lines):
        return ob, s.lines[s.line_index]
    return ob, None


class STITCHGEN_OT_set_reference(bpy.types.Operator):
    """Also follow this layer's edges"""
    bl_idname = "stitch_gen.set_reference"
    bl_label = "Reference"
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}
    attr: StringProperty(options={'HIDDEN', 'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        return _selected_layer(context)[1] is not None

    @classmethod
    def description(cls, context, props):
        return "Stop following that layer's edges" if not props.attr else cls.__doc__

    def execute(self, context):
        ob, item = _selected_layer(context)
        item.ref_attr = self.attr if self.attr != _layer_attr(item) else ""
        return {'FINISHED'}


class STITCHGEN_OT_reference_menu(bpy.types.Operator):
    """Also follow another layer's edges"""
    bl_idname = "stitch_gen.reference_menu"
    bl_label = "Reference"
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        return _selected_layer(context)[1] is not None

    @classmethod
    def description(cls, context, props):
        ob, item = _selected_layer(context)
        ref = _layer_by_attr(ob.stitch_gen, item.ref_attr) if item and item.ref_attr else None
        if ref is None or ref == item:
            return iface(cls.__doc__)
        return iface("Also follows {}").format(_layer_label(ref))

    def invoke(self, context, event):
        bpy.ops.wm.call_menu(name="STITCHGEN_MT_reference")
        return {'FINISHED'}

    def execute(self, context):
        return self.invoke(context, None)


class STITCHGEN_MT_reference(bpy.types.Menu):
    """Also follow another layer's edges"""
    bl_label = "Reference"

    def draw(self, context):
        ob, item = _selected_layer(context)
        if item is None:
            return
        lay = self.layout
        # the eyedropper first, then the layers (the current one ticked), then
        # clearing it
        lay.operator_context = 'INVOKE_DEFAULT'
        lay.operator("stitch_gen.pick_reference", text=iface("Pick in List"), translate=False,
                     icon='EYEDROPPER')
        lay.separator()
        for l in ob.stitch_gen.lines:
            if l != item:
                cur = item.ref_attr == _layer_attr(l)
                lay.operator("stitch_gen.set_reference", text=_layer_label(l), translate=False,
                             icon='CHECKMARK' if cur else _layer_icon(l)).attr = _layer_attr(l)
        if item.ref_attr:
            lay.separator()
            lay.operator("stitch_gen.set_reference", text=iface("Clear Reference"),
                         translate=False, icon='X').attr = ""


class STITCHGEN_OT_pick_reference(bpy.types.Operator):
    """Click a layer in the list to also follow its edges (Esc or right-click: cancel)"""
    bl_idname = "stitch_gen.pick_reference"
    bl_label = "Pick Layer"
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}

    @classmethod
    def poll(cls, context):
        return _selected_layer(context)[1] is not None and context.window is not None

    def invoke(self, context, event):
        ob, item = _selected_layer(context)
        if props._PICK.get("ob") == ob.name_full:            # clicked again: stop picking
            props._PICK["cancel"] = True
            return {'CANCELLED'}
        props._PICK.clear()
        props._PICK.update(ob=ob.name_full, attr=_layer_attr(item), done=False, cancel=False,
                     win=context.window)
        context.window.cursor_modal_set('EYEDROPPER')
        context.workspace.status_text_set(iface("Click a layer in the list") + "    Esc")
        bpy.app.timers.register(_keep_eyedropper, first_interval=_EYEDROPPER_EVERY)
        context.window_manager.modal_handler_add(self)
        _redraw_views()
        return {'RUNNING_MODAL'}

    def _end(self, context, result):
        props._PICK.clear()
        context.window.cursor_modal_restore()
        context.workspace.status_text_set(None)
        _redraw_views()
        return result

    def modal(self, context, event):
        if props._PICK.get("done"):
            return self._end(context, {'FINISHED'})
        if props._PICK.get("cancel") or not props._PICK:
            return self._end(context, {'CANCELLED'})
        if event.type in {'ESC', 'RIGHTMOUSE'} and event.value == 'PRESS':
            return self._end(context, {'CANCELLED'})
        if (event.type == 'LEFTMOUSE' and event.value == 'PRESS'
                and not _over_sidebar(context, event)):
            return self._end(context, {'CANCELLED'})      # a click outside the panel
        if event.type == 'MOUSEMOVE':
            context.window.cursor_modal_set('EYEDROPPER')
        return {'PASS_THROUGH'}


_EYEDROPPER_EVERY = 0.05


def _keep_eyedropper():
    """While picking, put the eyedropper cursor back: the events go on to the
    panel (so a click on a layer in the list works), and over the list the
    interface sets its own cursor."""
    win = props._PICK.get("win")
    if win is None:
        return None
    try:
        win.cursor_modal_set('EYEDROPPER')
    except (ReferenceError, RuntimeError):
        return None
    return _EYEDROPPER_EVERY


def _over_sidebar(context, event):
    """Is the mouse over a 3D View's sidebar (where the layer list is)?"""
    x, y = event.mouse_x, event.mouse_y
    for area in context.window.screen.areas:
        if area.type != 'VIEW_3D':
            continue
        for region in area.regions:
            if (region.type == 'UI' and region.x <= x < region.x + region.width
                    and region.y <= y < region.y + region.height):
                return True
    return False


class STITCHGEN_MT_uv_maps(bpy.types.Menu):
    bl_label = "UV Map"

    def draw(self, context):
        ob = _source_object(context)
        if ob is None:
            return
        lay = self.layout
        op = lay.operator("stitch_gen.set_uv_map", text=iface("Follow Active UV Map"),
                          icon='CHECKBOX_HLT' if ob.stitch_gen.uv_map not in ob.data.uv_layers
                          else 'BLANK1', translate=False)
        op.name = ""
        lay.separator()
        for uvl in ob.data.uv_layers:
            op = lay.operator("stitch_gen.set_uv_map", text=uvl.name, translate=False,
                              icon='CHECKBOX_HLT' if ob.stitch_gen.uv_map == uvl.name
                              else 'BLANK1')
            op.name = uvl.name


def _redraw_views():
    for win in bpy.context.window_manager.windows:
        for area in win.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
