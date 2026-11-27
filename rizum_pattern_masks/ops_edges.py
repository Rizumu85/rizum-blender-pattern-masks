# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Rizum
"""Operators for editing marked edges and corners."""

import bpy
import bmesh

from . import core, layers, overlay, preview
from .i18n import rpt
from .layers import (
    _edge_spec, _is_grid, _is_stitch, _layer_attr, _new_line_layer, _new_stitch_layer,
    _source_object, _uses_addon,
)
from .migrate import UI_VERSION, _ensure_layers
from .presets import _apply_default_to_new
from .rebuild import regenerate


# -- operators -----------------------------------------------------------------

def _edited(context, main):
    """The meshes in Edit Mode, the one the panel shows first (each mesh
    once)."""
    out, seen = [main], {main.data.name_full}
    for o in getattr(context, "objects_in_mode_unique_data", None) or []:
        if o.type == 'MESH' and o.data.name_full not in seen:
            out.append(o)
            seen.add(o.data.name_full)
    return out


def _layer_kind(item):
    return 'STITCH' if _is_stitch(item) else 'GRID' if _is_grid(item) else 'LINE'


def _layer_spec(s):
    """(kind, name) of the layer selected in the list; ('STITCH', None)
    without one (scripts): the first stitch layer."""
    if 0 <= s.line_index < len(s.lines):
        item = s.lines[s.line_index]
        return (_layer_kind(item), item.name)
    return ('STITCH', None)


def _select_twin(context, ob, spec, create):
    """Select on ``ob`` the layer that matches ``spec``: the layer of that
    kind and name (no name: the first stitch layer). ``create`` makes it when
    missing. False when there is none."""
    s = ob.stitch_gen
    _ensure_layers(ob)
    kind, name = spec
    found = next((i for i, l in enumerate(s.lines) if _layer_kind(l) == kind
                  and (name is None or l.name == name)), None)
    if found is not None:
        if s.line_index != found:
            s.line_index = found
        return True
    if not create:
        return False
    layers._MUTE = True
    try:
        if kind == 'STITCH':
            _new_stitch_layer(ob)
        else:
            _new_line_layer(ob, kind)
        _apply_default_to_new(context, ob, kind)
        if name:
            s.lines[s.line_index].name = name
        s.ui_version = UI_VERSION
    finally:
        layers._MUTE = False
    return True


def _shared_mesh_changed(ob):
    """Its marks changed: the other objects that share its mesh (linked
    duplicates) are rebuilt when next drawn."""
    for o in bpy.data.objects:
        if o.data == ob.data and o != ob:
            preview.forget(o)
            overlay.invalidate(o)


def _has_selected_edges(ob):
    return any(e.select for e in bmesh.from_edit_mesh(ob.data).edges)


class _EditPathBase:
    """The edge buttons. They work on every mesh in Edit Mode: on each, on the
    layer that matches the one selected in the list."""
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        ob = _source_object(context)
        if ob is not None and ob.mode == 'EDIT':
            return True
        cls.poll_message_set(rpt("Works in Edit Mode"))
        return False

    def _layer(self, bm, name, create=True):
        lay = bm.edges.layers.int.get(name)
        if lay is None and create:
            lay = bm.edges.layers.int.new(name)
        return lay

    def apply(self, ob, bm, lay):
        raise NotImplementedError

    def execute(self, context):
        main = _source_object(context)
        adds = getattr(self, "adds", False)
        _ensure_layers(main)
        spec = _layer_spec(main.stitch_gen)
        targets = []
        for ob in _edited(context, main):
            if adds and not _has_selected_edges(ob):
                continue
            s = ob.stitch_gen
            if ob == main and 0 <= s.line_index < len(s.lines):
                targets.append(ob)
            elif _select_twin(context, ob, spec, adds) or ob == main:
                targets.append(ob)       # main without layers (scripts): the stitch edges
        if adds and not targets:
            self.report({'WARNING'}, rpt("No edges selected"))
            return {'CANCELLED'}
        done = [ob for ob in targets if self._edit(context, ob, adds)]
        if targets and not done:
            return {'CANCELLED'}
        if adds and spec[0] == 'STITCH' and any(
                _selected_layer_of(ob) is not None and _selected_layer_of(ob).dash_count == 0
                and not ob.stitch_gen.status for ob in done):
            self.report({'WARNING'}, rpt("The marked edges are too short for a stitch"))
        return {'FINISHED'}

    def _edit(self, context, ob, adds):
        _shared_mesh_changed(ob)
        s = ob.stitch_gen
        item = s.lines[s.line_index] if 0 <= s.line_index < len(s.lines) else None
        if item is not None and not item.show_marks:
            item.show_marks = True                         # show what is being edited
        if not context.scene.stitch_gen_marks:
            context.scene.stitch_gen_marks = True
        me = ob.data
        name = _edge_attr(ob)
        bm = bmesh.from_edit_mesh(me)
        if name in bm.edges.layers.int:
            pass
        elif any(name in coll for coll in (
                bm.verts.layers.int, bm.verts.layers.float, bm.edges.layers.float,
                bm.faces.layers.int, bm.faces.layers.float, bm.loops.layers.int,
                bm.loops.layers.float)) or name in me.attributes:
            # Never overwrite someone else's data with the same name.
            self.report({'ERROR'}, rpt('The mesh already has an attribute "{}" of another '
                                       'type; rename it first').format(name))
            return False
        lay = self._layer(bm, name)
        self.apply(ob, bm, lay)
        bmesh.update_edit_mesh(me, loop_triangles=False, destructive=False)
        if adds and item is not None:
            layers._MUTE = True                     # edges added to a hidden layer: show it
            try:
                item.enabled = True
            finally:
                layers._MUTE = False
        regenerate(ob, context.scene)
        return True


def _selected_layer_of(ob):
    s = ob.stitch_gen
    return s.lines[s.line_index] if 0 <= s.line_index < len(s.lines) else None


def _edge_attr(ob):
    """Edge attribute the edge buttons edit: the one of the layer selected in
    the list."""
    s = ob.stitch_gen
    if 0 <= s.line_index < len(s.lines):
        return _layer_attr(s.lines[s.line_index])
    return core.PATH_ATTR


def _on_path_verts(bm):
    """Vertices on the stitch edges or the line art edges."""
    out = set()
    names = [core.PATH_ATTR] + [n for n in bm.edges.layers.int.keys()
                                if n == core.LINE_ATTR or n.startswith(core.LINE_ATTR + "_")]
    for name in names:
        lay = bm.edges.layers.int.get(name)
        if lay is not None:
            out.update(v for e in bm.edges if e[lay] > 0 for v in e.verts)
    return out


class STITCHGEN_OT_path_add(_EditPathBase, bpy.types.Operator):
    """Add the selected edges to the layer selected in the list"""
    bl_idname = "stitch_gen.path_add"
    bl_label = "Add Selected"
    adds = True

    def apply(self, ob, bm, lay):
        for e in bm.edges:
            if e.select:
                e[lay] = 1
        if core.CORNER_ATTR not in bm.verts.layers.int and \
                core.CORNER_ATTR not in ob.data.attributes:
            bmesh.update_edit_mesh(ob.data, loop_triangles=False, destructive=False)
            _detect_and_mark(ob, bm, select=False)     # first path: a starting guess


def _referred_spec(ob):
    """Edge spec of what the selected layer gets from the layer it refers to."""
    s = ob.stitch_gen
    if not 0 <= s.line_index < len(s.lines):
        return None
    return _edge_spec(s, s.lines[s.line_index])[1]


class STITCHGEN_OT_path_remove(_EditPathBase, bpy.types.Operator):
    ("Remove the selected edges from the layer selected in the list, "
     "also those it gets from the layer it refers to")
    bl_idname = "stitch_gen.path_remove"
    bl_label = "Remove Selected"

    def apply(self, ob, bm, lay):
        bm.edges.index_update()
        referred = _bm_spec_edges(bm, _referred_spec(ob))
        for e in bm.edges:
            if e.select:
                e[lay] = -1 if e.index in referred else 0


class STITCHGEN_OT_path_select(_EditPathBase, bpy.types.Operator):
    ("Select the edges of the layer selected in the list, "
     "with those it gets from the layer it refers to")
    bl_idname = "stitch_gen.path_select"
    bl_label = "Select Edges"

    def apply(self, ob, bm, lay):
        bm.edges.index_update()
        s = ob.stitch_gen
        spec = (_edge_spec(s, s.lines[s.line_index]) if 0 <= s.line_index < len(s.lines)
                else (lay.name, None))
        mine = _bm_spec_edges(bm, spec)
        for e in bm.edges:
            if e.index in mine:
                e.select_set(True)
        bm.select_flush_mode()


class STITCHGEN_OT_path_clear(_EditPathBase, bpy.types.Operator):
    ("Clear all edges of the layer selected in the list, "
     "and bring back the edges it took out of its reference")
    bl_idname = "stitch_gen.path_clear"
    bl_label = "Clear Edges"

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def apply(self, ob, bm, lay):
        for e in bm.edges:
            e[lay] = 0


def _detect_and_mark(ob, bm, select):
    """Mark likely corners on the path vertices (replacing marks there).
    Returns the number of marked corners."""
    _ensure_layers(ob)                       # an older file: each layer's side first
    ob.update_from_editmode()
    tmp = ob.to_mesh(preserve_all_data_layers=True)
    try:
        topo = core.Topology(tmp, ob.matrix_world, "")
        # the edges of layers on the other side are judged on that side
        flipped = {_layer_attr(l) for l in ob.stitch_gen.lines if l.flip and not _is_grid(l)}
        names = [core.PATH_ATTR] + core.line_attr_names(tmp)
        found = set()
        for flip in (False, True):
            group = tuple(n for n in names if (n in flipped) == flip)
            if not group:
                continue
            for ids, closed in core.build_chains(topo.path_pairs(tmp, group), topo.co):
                found.update(core.detect_corner_vertices(topo, ids, closed, flip))
        weld = topo.vert_weld
    finally:
        ob.to_mesh_clear()
    lay = bm.verts.layers.int.get(core.CORNER_ATTR) or bm.verts.layers.int.new(core.CORNER_ATTR)
    bm.verts.index_update()
    on_path = {v.index for v in _on_path_verts(bm)}
    count = 0
    for v in bm.verts:
        if v.index in on_path:
            v[lay] = 1 if weld[v.index] in found else 0
            count += v[lay]
    if select:
        for v in bm.verts:
            v.select_set(bool(v[lay]))
        bm.select_flush_mode()
    return count


def _corner_objects(context):
    """The meshes in Edit Mode the corner buttons act on: the one the panel
    shows, and the others that use the add-on."""
    main = _source_object(context)
    return [o for o in _edited(context, main) if o == main or _uses_addon(o)]


class _EditCornerBase(_EditPathBase):
    def execute(self, context):
        for ob in _corner_objects(context):
            me = ob.data
            bm = bmesh.from_edit_mesh(me)
            lay = bm.verts.layers.int.get(core.CORNER_ATTR)
            if lay is None:
                if core.CORNER_ATTR in me.attributes:
                    self.report({'ERROR'}, rpt('The mesh already has an attribute "{}" of '
                                               'another type; rename it first')
                                .format(core.CORNER_ATTR))
                    continue
                lay = bm.verts.layers.int.new(core.CORNER_ATTR)
            on_path = _on_path_verts(bm)
            for v in bm.verts:
                if v.select and (v in on_path or self.value == 0):   # only path vertices get marks
                    v[lay] = self.value
            bmesh.update_edit_mesh(me, loop_triangles=False, destructive=False)
            _shared_mesh_changed(ob)
            regenerate(ob, context.scene)
        return {'FINISHED'}


class STITCHGEN_OT_corner_mark(_EditCornerBase, bpy.types.Operator):
    """Keep the lines sharp at the selected vertices"""
    bl_idname = "stitch_gen.corner_mark"
    bl_label = "Mark Corner"
    value = 1


class STITCHGEN_OT_corner_clear(_EditCornerBase, bpy.types.Operator):
    """Let the lines round off at the selected vertices again"""
    bl_idname = "stitch_gen.corner_clear"
    bl_label = "Clear Corner"
    value = 0


class STITCHGEN_OT_corner_detect(_EditPathBase, bpy.types.Operator):
    """Mark likely corners on the marked edges automatically (replaces the marks there)"""
    bl_idname = "stitch_gen.corner_detect"
    bl_label = "Detect Corners"

    def execute(self, context):
        n = 0
        for ob in _corner_objects(context):
            bm = bmesh.from_edit_mesh(ob.data)
            if core.CORNER_ATTR not in bm.verts.layers.int and \
                    core.CORNER_ATTR in ob.data.attributes:
                self.report({'ERROR'}, rpt('The mesh already has an attribute "{}" of '
                                           'another type; rename it first')
                            .format(core.CORNER_ATTR))
                continue
            n += _detect_and_mark(ob, bm, select=True)
            bmesh.update_edit_mesh(ob.data, loop_triangles=False, destructive=False)
            _shared_mesh_changed(ob)
            regenerate(ob, context.scene)
        self.report({'INFO'}, rpt("Marked {} corners").format(n))
        return {'FINISHED'}


class STITCHGEN_OT_corner_select(_EditPathBase, bpy.types.Operator):
    """Select the vertices marked as corners"""
    bl_idname = "stitch_gen.corner_select"
    bl_label = "Select Corners"

    def execute(self, context):
        for ob in _corner_objects(context):
            bm = bmesh.from_edit_mesh(ob.data)
            lay = bm.verts.layers.int.get(core.CORNER_ATTR)
            for v in bm.verts:
                v.select_set(bool(lay and v[lay]))
            bm.select_flush_mode()
            bmesh.update_edit_mesh(ob.data, loop_triangles=False, destructive=False)
        return {'FINISHED'}


def _bm_spec_edges(bm, spec):
    """Indices of the edges of an edge spec, read from an edit-mode BMesh."""
    if spec is None:
        return set()
    attr, child = spec
    lay = bm.edges.layers.int.get(attr)
    out = _bm_spec_edges(bm, child)
    if lay is not None:
        out |= {e.index for e in bm.edges if e[lay] > 0}
        out -= {e.index for e in bm.edges if e[lay] < 0}
    return out
