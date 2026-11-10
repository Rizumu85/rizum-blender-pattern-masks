"""Rizum Pattern Masks: stitches, line art and grids that follow the mesh from
marked edges, baked to UV masks."""

import hashlib
import math
import os
import re
import threading
import time
import traceback

import numpy as np
import bpy
import bpy.utils.previews
import bmesh
from mathutils import Matrix
from bl_operators.presets import AddPresetBase
from bl_ui.utils import PresetPanel
from bpy.props import (BoolProperty, CollectionProperty, EnumProperty, FloatProperty,
                       IntProperty, PointerProperty, StringProperty)

from . import core, bake, grid, i18n, overlay
from .i18n import iface, rpt

COLLECTION = "Stitch Preview"
MATERIAL = "StitchGen_Mask"
LINE_MATERIAL = "StitchGen_LinePreview"
GRID_MATERIAL = "StitchGen_GridPreview"

_last = {}   # object name -> RibbonData of the last generation
_last_params = {}   # object name -> settings of the last generation


# -- ribbon object -------------------------------------------------------------

def _mask_material():
    mat = bpy.data.materials.get(MATERIAL)
    if mat is not None:
        return mat
    mat = bpy.data.materials.new(MATERIAL)
    if hasattr(mat, "use_nodes") and not mat.use_nodes:
        mat.use_nodes = True
    mat.diffuse_color = (1.0, 0.35, 0.05, 1.0)
    if hasattr(mat, "surface_render_method"):
        mat.surface_render_method = 'DITHERED'
    nt = mat.node_tree
    nt.nodes.clear()
    N = nt.nodes.new
    L = nt.links.new

    def attr(name, x, y):
        n = N("ShaderNodeAttribute")
        n.attribute_name = name
        n.location = (x, y)
        return n

    def math(op, a=None, b=None, x=0, y=0, clamp=False):
        n = N("ShaderNodeMath")
        n.operation = op
        n.use_clamp = clamp
        n.location = (x, y)
        for i, v in enumerate((a, b)):
            if v is None:
                continue
            if isinstance(v, (int, float)):
                n.inputs[i].default_value = v
            else:
                L(v, n.inputs[i])
        return n.outputs[0]

    uv = attr("stitch_uv", -1400, 200)
    dims = attr("stitch_dims", -1400, -100)
    pxa = attr("stitch_aa", -1400, -400)
    sep_a = N("ShaderNodeSeparateXYZ"); sep_a.location = (-1200, -400)
    L(pxa.outputs["Vector"], sep_a.inputs[0])
    sep_uv = N("ShaderNodeSeparateXYZ"); sep_uv.location = (-1200, 200)
    L(uv.outputs["Vector"], sep_uv.inputs[0])
    sep_d = N("ShaderNodeSeparateXYZ"); sep_d.location = (-1200, -100)
    L(dims.outputs["Vector"], sep_d.inputs[0])
    hl, hw, r = sep_d.outputs[0], sep_d.outputs[1], sep_d.outputs[2]
    # rounded-rectangle signed distance
    qx = math('SUBTRACT', math('ABSOLUTE', sep_uv.outputs[0], x=-1000, y=300),
              math('SUBTRACT', hl, r, x=-1000, y=100), x=-800, y=250)
    qy = math('SUBTRACT', math('ABSOLUTE', sep_uv.outputs[1], x=-1000, y=0),
              math('SUBTRACT', hw, r, x=-1000, y=-200), x=-800, y=0)
    mx = math('MAXIMUM', qx, 0.0, x=-600, y=300)
    my = math('MAXIMUM', qy, 0.0, x=-600, y=100)
    outside = math('SQRT', math('ADD', math('MULTIPLY', mx, mx, x=-450, y=300),
                                math('MULTIPLY', my, my, x=-450, y=100), x=-300, y=200),
                   x=-150, y=200)
    inside = math('MINIMUM', math('MAXIMUM', qx, qy, x=-600, y=-100), 0.0, x=-450, y=-100)
    sd = math('SUBTRACT', math('ADD', outside, inside, x=0, y=100), r, x=150, y=100)
    cov = math('SUBTRACT', 0.5, math('DIVIDE', sd, sep_a.outputs[0], x=300, y=0),
               x=450, y=0, clamp=True)

    emit = N("ShaderNodeEmission"); emit.location = (600, 200)
    emit.inputs["Color"].default_value = (1, 1, 1, 1)
    emit.inputs["Strength"].default_value = 1.0
    transp = N("ShaderNodeBsdfTransparent"); transp.location = (600, 350)
    mix = N("ShaderNodeMixShader"); mix.location = (800, 200)
    L(cov, mix.inputs[0])
    L(transp.outputs[0], mix.inputs[1])
    L(emit.outputs[0], mix.inputs[2])
    out = N("ShaderNodeOutputMaterial"); out.location = (1000, 200)
    L(mix.outputs[0], out.inputs["Surface"])
    return mat


def _preview_collection(scene):
    col = bpy.data.collections.get(COLLECTION)
    if col is None:
        col = bpy.data.collections.new(COLLECTION)
    if col.name not in scene.collection.children:
        scene.collection.children.link(col)
    return col


def _unhide_in(lc, ob, chain=()):
    """Clear one thing that keeps ``ob`` out of view below this layer
    collection: its collection left out of the view layer, or a collection on
    the way down hidden. True when something was changed."""
    chain += (lc,)
    if ob.name in lc.collection.objects:
        if lc.exclude:
            lc.exclude = False
            return True
        for a in chain:
            if a.hide_viewport:
                a.hide_viewport = False
                return True
            if a.collection.hide_viewport:
                a.collection.hide_viewport = False
                return True
    return any(_unhide_in(c, ob, chain) for c in lc.children)


def _show_preview(ob, scene):
    """A button was pressed: show the preview (operators only). It can have
    been deleted from the scene or hidden, and so can the collection it is in;
    otherwise the button rebuilds stitches nobody sees."""
    if not ob.users_collection:
        _preview_collection(scene).objects.link(ob)
    ob.hide_viewport = False
    if bpy.context.scene != scene:
        return
    vl = bpy.context.view_layer
    # one change at a time (each can move the others); each clears one of at
    # most three flags per collection, so this ends even if a flag won't change
    for _ in range(3 * len(bpy.data.collections) + 4):
        inside = ob.name in vl.objects
        if inside and ob.hide_get():
            ob.hide_set(False)
        if inside and ob.visible_get():
            return
        if _unhide_in(vl.layer_collection, ob):
            continue
        col = _preview_collection(scene)   # only in other scenes: into this one too
        if inside or ob.name in col.objects:
            return
        col.objects.link(ob)


def _ribbon_object(obj, scene, create):
    """The preview object. Only operators may create it (create=True): creating or
    deleting data-blocks from a property update callback breaks undo."""
    s = obj.stitch_gen
    rib = s.ribbon
    if rib is not None and rib.name in bpy.data.objects and rib.type == 'MESH':
        if create:
            _show_preview(rib, scene)
        return rib
    if not create:
        return None
    me = bpy.data.meshes.new(obj.name + "_Stitches")
    me.materials.append(_mask_material())
    rib = bpy.data.objects.new(obj.name + "_Stitches", me)
    rib.hide_render = True
    s.ribbon = rib
    _show_preview(rib, scene)
    return rib


def _line_material():
    mat = bpy.data.materials.get(LINE_MATERIAL)
    if mat is None:
        mat = bpy.data.materials.new(LINE_MATERIAL)
        mat.diffuse_color = (0.0, 0.0, 0.0, 1.0)
    _ensure_emission(mat)
    return mat


def _ensure_emission(mat):
    """A flat emission shader, so the preview color also shows in Material
    Preview and Rendered mode (operators only: it may add nodes)."""
    if hasattr(mat, "use_nodes") and not mat.use_nodes:
        mat.use_nodes = True
    nt = mat.node_tree
    if nt is None or any(n.type == 'EMISSION' for n in nt.nodes):
        return
    nt.nodes.clear()
    emit = nt.nodes.new("ShaderNodeEmission")
    emit.inputs["Color"].default_value = mat.diffuse_color
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (250, 0)
    nt.links.new(emit.outputs[0], out.inputs["Surface"])


def _apply_colors(ob):
    """Preview colors into the preview materials (display color and shader)."""
    s = ob.stitch_gen
    pairs = []
    if s.ribbon is not None and s.ribbon.type == 'MESH':
        pairs += [(mat, s.stitch_color) for mat in s.ribbon.data.materials]
    pairs += [(l.material, l.color) for l in _line_items(s)]
    pairs += [(l.material, l.color) for l in _grid_items(s)]
    for l in _grid_items(s):                      # the grid shader's own color
        nt = l.material.node_tree if l.material is not None else None
        if nt is not None and nt.nodes.get("color") is not None:
            nt.nodes["color"].outputs[0].default_value = l.color
    for mat, col in pairs:
        if mat is None:
            continue
        mat.diffuse_color = col
        if mat.node_tree is not None:
            for n in mat.node_tree.nodes:
                if n.type == 'EMISSION':
                    n.inputs["Color"].default_value = col


def _layer_materials(ob, create):
    """Preview material of each shown line art layer, in the order of the
    preview's material slots. Only operators create new materials."""
    s = ob.stitch_gen
    out = []
    for l in _line_items(s):
        if not l.enabled:
            continue
        mat = l.material
        if create:
            shared = mat is not None and any(          # a duplicated object
                o != ob and o.type == 'MESH' and any(x.material == mat for x in o.stitch_gen.lines)
                for o in bpy.data.objects)
            if mat is None or shared:
                mat = mat.copy() if shared else bpy.data.materials.new(LINE_MATERIAL)
                mat.diffuse_color = l.color
                l.material = mat
            _ensure_emission(mat)
        out.append(mat if mat is not None else bpy.data.materials.get(LINE_MATERIAL))
    return out


def _on_color(self, context):
    ob = self.id_data
    if isinstance(ob, bpy.types.Object):
        _apply_colors(ob)


def _line_object(obj, scene, create):
    """The line art preview object; like the stitch preview, only operators
    create it."""
    s = obj.stitch_gen
    lo = s.line_preview
    if lo is not None and lo.name in bpy.data.objects and lo.type == 'MESH':
        if create:
            for mat in lo.data.materials:
                if mat is not None:
                    _ensure_emission(mat)
            _show_preview(lo, scene)
        return lo
    if not create:
        return None
    me = bpy.data.meshes.new(obj.name + "_LineArt")
    me.materials.append(_line_material())
    lo = bpy.data.objects.new(obj.name + "_LineArt", me)
    lo.hide_render = True
    s.line_preview = lo
    _show_preview(lo, scene)
    return lo


def _grid_geometry(obj, scene):
    """(co, tris, vs per corner, layer per tri) of the shown grid layers, or None."""
    s = obj.stitch_gen
    grids = _params(s, scene)["grids"]
    entry = core._cache.get(obj.name_full)
    if not grids or entry is None:
        return None
    topo = entry["topo"]
    lift = max(topo.mean_edge / 60.0, topo.span * 2e-5)
    cos, tris, vss, owner, base = [], [], [], [], 0
    for li, (attr, cell, angle, off_y, off_x, wobble, mode, attrs) in enumerate(grids):
        if mode == "unrolled" and not _unrolled_ready(obj, scene, entry, attrs):
            continue                       # being worked out; shown when done
        lay = core.grid_coords(entry, attrs).layout(cell, angle, mode)
        co, t, vs = grid.preview(topo, lay, lift, off_x, off_y,
                                 grid.Wobble(attr, cell, wobble))
        if not len(t):
            continue
        cos.append(co)
        tris.append(t + base)
        vss.append(vs)
        owner.append(np.full(len(t), li, np.int64))
        base += len(co)
    if not tris:
        return np.zeros((0, 3)), np.zeros((0, 3), np.int64), np.zeros((0, 3, 2)), np.zeros(0, np.int64)
    return np.vstack(cos), np.vstack(tris), np.vstack(vss), np.concatenate(owner)


_unroll_jobs = {}        # object name -> the Unrolled flattening being worked out


def _redraw_views():
    for win in bpy.context.window_manager.windows:
        for area in win.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()


def _unrolled_ready(obj, scene, entry, attrs):
    """Is the Unrolled flattening of this layer's piece at hand? If not, it
    is worked out in the background (a few seconds on a big piece) with a
    progress bar in the panel, and the preview is rebuilt when it is done."""
    fld = core.grid_coords(entry, attrs)
    if getattr(fld, "_flat_log", None) is not None:
        return True
    if bpy.app.background:
        return True                        # scripts: straight away
    name = obj.name_full
    job = _unroll_jobs.get(name)
    if job is not None and job["thread"].is_alive():
        return False
    job = {"thread": None, "round": (0, grid.FLAT_ROUNDS), "error": None}

    def progress(k, n):
        job["round"] = (k, n)

    fld.progress = progress

    def work():
        try:
            fld._unrolled()
        except Exception as e:             # shown in the panel instead
            job["error"] = f"{type(e).__name__}: {e}"

    scene_name = scene.name if scene else ""
    job["thread"] = threading.Thread(target=work, daemon=True)
    _unroll_jobs[name] = job
    job["thread"].start()

    def poll():
        if job["thread"].is_alive():
            _redraw_views()
            return 0.25
        _unroll_jobs.pop(name, None)
        ob = bpy.data.objects.get(name)
        if ob is not None and ob.type == 'MESH':
            if job["error"]:
                ob.stitch_gen.status = job["error"]
            else:
                regenerate(ob, bpy.data.scenes.get(scene_name))
        _redraw_views()
        return None

    bpy.app.timers.register(poll, first_interval=0.25)
    return False


def _grid_object(obj, scene, create):
    """The grid preview object; like the other previews, only operators create it."""
    s = obj.stitch_gen
    go = s.grid_preview
    if go is not None and go.name in bpy.data.objects and go.type == 'MESH':
        if create:
            _show_preview(go, scene)
        return go
    if not create:
        return None
    me = bpy.data.meshes.new(obj.name + "_Grid")
    go = bpy.data.objects.new(obj.name + "_Grid", me)
    go.hide_render = True
    s.grid_preview = go
    _show_preview(go, scene)
    return go


def _grid_shader(mat):
    """Squares drawn from the per-corner fabric coordinates (operators only:
    adds nodes): the black squares in the layer's color, the white ones clear.
    The square size lives in a Value node named cell."""
    if hasattr(mat, "use_nodes") and not mat.use_nodes:
        mat.use_nodes = True
    if hasattr(mat, "surface_render_method"):
        mat.surface_render_method = 'DITHERED'
    nt = mat.node_tree
    if nt is None or nt.nodes.get("checker") is not None:
        return
    nt.nodes.clear()
    N, L = nt.nodes.new, nt.links.new
    attr = N("ShaderNodeAttribute")
    attr.attribute_name = "grid_vs"
    sep = N("ShaderNodeSeparateXYZ")
    L(attr.outputs["Vector"], sep.inputs[0])
    cell = N("ShaderNodeValue")
    cell.name = cell.label = "cell"

    def math_(op, a_, b_):
        n = N("ShaderNodeMath")
        n.operation = op
        for i, x in enumerate((a_, b_)):
            if isinstance(x, (int, float)):
                n.inputs[i].default_value = x
            else:
                L(x, n.inputs[i])
        return n.outputs[0]

    fx = math_('FLOOR', math_('DIVIDE', sep.outputs[0], cell.outputs[0]), 0.0)
    fy = math_('FLOOR', math_('DIVIDE', sep.outputs[1], cell.outputs[0]), 0.0)
    parity = math_('MODULO', math_('ADD', math_('ADD', fx, fy), 2000000.0), 2.0)
    black = math_('LESS_THAN', parity, 0.5)
    mark = N("ShaderNodeValue")
    mark.name = "checker"                     # this is the checker version of the shader
    rgb = N("ShaderNodeRGB")
    rgb.name = "color"
    emit = N("ShaderNodeEmission")
    L(rgb.outputs[0], emit.inputs["Color"])
    transp = N("ShaderNodeBsdfTransparent")
    mix = N("ShaderNodeMixShader")
    L(black, mix.inputs[0])
    L(transp.outputs[0], mix.inputs[1])
    L(emit.outputs[0], mix.inputs[2])
    out = N("ShaderNodeOutputMaterial")
    L(mix.outputs[0], out.inputs["Surface"])


def _grid_values(mat, layer, k):
    nt = mat.node_tree if mat is not None else None
    if nt is None or nt.nodes.get("checker") is None:
        return
    nt.nodes["cell"].outputs[0].default_value = layer.grid_cell * k
    c = nt.nodes.get("color")
    if c is not None:
        c.outputs[0].default_value = layer.color


def _grid_materials(ob, create):
    """Preview material of each shown grid layer, in slot order."""
    s = ob.stitch_gen
    k = 0.001 / (bpy.context.scene.unit_settings.scale_length or 1.0)
    out = []
    for l in _grid_items(s):
        if not l.enabled:
            continue
        mat = l.material
        if create:
            shared = mat is not None and any(
                o != ob and o.type == 'MESH' and any(x.material == mat for x in o.stitch_gen.lines)
                for o in bpy.data.objects)
            if mat is None or shared:
                mat = mat.copy() if shared else bpy.data.materials.new(GRID_MATERIAL)
                mat.diffuse_color = l.color
                l.material = mat
            _grid_shader(mat)
        _grid_values(mat, l, k)
        out.append(mat)
    return out


def _write_grid(go, gdata, mats):
    me = go.data
    me.clear_geometry()
    if list(me.materials) != mats:
        me.materials.clear()
        for mat in mats:
            me.materials.append(mat)
    if gdata is not None and len(gdata[1]):
        co, tris, vs, owner = gdata
        me.vertices.add(len(co))
        me.vertices.foreach_set("co", co.astype(np.float32).ravel())
        me.loops.add(len(tris) * 3)
        me.loops.foreach_set("vertex_index", tris.astype(np.int32).ravel())
        me.polygons.add(len(tris))
        me.polygons.foreach_set("loop_start", np.arange(len(tris), dtype=np.int32) * 3)
        me.polygons.foreach_set("material_index", owner.astype(np.int32))
        a = me.attributes.new("grid_vs", 'FLOAT2', 'CORNER')
        a.data.foreach_set("vector", vs.astype(np.float32).ravel())
    me.update()
    if go.matrix_world != Matrix.Identity(4):
        go.matrix_world = Matrix.Identity(4)


SIG_PROP = "stitch_gen_built_from"


def _params_sig(p):
    """Short fingerprint of the settings a preview was built from."""
    return hashlib.md5(repr(sorted(p.items())).encode()).hexdigest()[:16]


def _write_lines(lo, data, mats):
    """Rewrite the line art preview; material slot i is the i-th shown layer."""
    me = lo.data
    me.clear_geometry()
    if list(me.materials) != mats:
        me.materials.clear()
        for mat in mats:
            me.materials.append(mat)
    co, quads = data.line_co, data.line_quads
    if len(quads):
        me.vertices.add(len(co))
        me.vertices.foreach_set("co", co.astype(np.float32).ravel())
        me.loops.add(len(quads) * 4)
        me.loops.foreach_set("vertex_index", quads.astype(np.int32).ravel())
        me.polygons.add(len(quads))
        me.polygons.foreach_set("loop_start", np.arange(len(quads), dtype=np.int32) * 4)
        me.polygons.foreach_set("material_index", data.line_layer.astype(np.int32))
    me.update()
    if lo.matrix_world != Matrix.Identity(4):
        lo.matrix_world = Matrix.Identity(4)


def _write_ribbon(rib_obj, data):
    """Rewrite the preview mesh in place (no new data-blocks, undo-safe)."""
    me = rib_obj.data
    me.clear_geometry()
    nv = len(data.co)
    nq = len(data.quads)
    if nq:
        me.vertices.add(nv)
        me.vertices.foreach_set("co", data.co.astype(np.float32).ravel())
        me.loops.add(nq * 4)
        me.loops.foreach_set("vertex_index", data.quads.astype(np.int32).ravel())
        me.polygons.add(nq)
        me.polygons.foreach_set("loop_start", (np.arange(nq, dtype=np.int32) * 4))
        loop_v = data.quads.ravel()
        a = me.attributes.new("stitch_uv", 'FLOAT2', 'CORNER')
        a.data.foreach_set("vector", data.uv[loop_v].astype(np.float32).ravel())
        a = me.attributes.new("stitch_dims", 'FLOAT_VECTOR', 'POINT')
        a.data.foreach_set("vector", data.dims.astype(np.float32).ravel())
        # Cycles misreads plain FLOAT attributes here; carry the texel size in a vector.
        a = me.attributes.new("stitch_aa", 'FLOAT_VECTOR', 'POINT')
        aa = np.zeros((nv, 3), np.float32)
        aa[:, 0] = data.aa
        a.data.foreach_set("vector", aa.ravel())
    me.update()
    if rib_obj.matrix_world != Matrix.Identity(4):
        rib_obj.matrix_world = Matrix.Identity(4)


def _release_shared_previews(obj):
    """A duplicated or split-off object still points at the original's preview
    objects; let go of them, so each object gets (and writes) its own."""
    s = obj.stitch_gen
    for prop, suffix in (("ribbon", "_Stitches"), ("line_preview", "_LineArt"),
                         ("grid_preview", "_Grid")):
        prev = getattr(s, prop)
        if prev is None:
            continue
        others = [o for o in bpy.data.objects
                  if o != obj and o.type == 'MESH' and getattr(o.stitch_gen, prop) == prev]
        if others and not prev.name.startswith(obj.name + suffix):
            setattr(s, prop, None)


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
    global _MUTE
    _MUTE = True
    try:
        if src is not None:
            s.output_dir = src.output_dir
        if size in {"1024", "2048", "4096", "8192"}:
            s.resolution = size
    finally:
        _MUTE = False


def _on_size(self, context):
    """Remember the size picked last, for the next new object."""
    if not _MUTE and context.scene is not None:
        context.scene.stitch_gen_last_size = self.resolution
    _on_change(self, context)


def _params(s, scene):
    # UI values are millimetres; geometry works in scene units.
    k = 0.001 / (scene.unit_settings.scale_length or 1.0)
    st = _stitch_item(s)
    return {
        "inset": s.inset * k, "smooth": s.smooth * k, "flip": s.flip,
        "length": s.length * k, "gap": s.gap * k, "width": s.width * k, "round": s.roundness,
        "offset": 0.0,                     # sliding the stitches was dropped in 0.3.0
        "zigzag": s.zigzag_height * k if s.style == 'ZIGZAG' else 0.0,
        "even": s.even, "resolution": int(s.resolution),
        "corner": 0.0,
        "corner_inset": s.corner_inset * k,
        "uv_name": s.uv_map,
        "stitches": _stitches_on(s),
        "stitch_attrs": _edge_spec(s, st) if st is not None else (core.PATH_ATTR, None),
        "lines": tuple((l.offset * k, l.width * k, l.corner_inset * k, _edge_spec(s, l),
                        l.smooth * k, _layer_attr(l)) for l in _line_items(s) if l.enabled),
        "grids": tuple((_layer_attr(l), l.grid_cell * k, l.grid_angle, l.grid_from * k,
                        l.grid_along * k, l.grid_wobble, l.grid_layout.lower(), _edge_spec(s, l))
                       for l in _grid_items(s) if l.enabled),
    }


def _layer_attr(layer):
    """Edge attribute of a layer: the stitch edges for the stitch row; line
    layers from before 0.2.0 share one."""
    return layer.edge_attr or core.LINE_ATTR


def _is_stitch(layer):
    return layer.edge_attr == core.PATH_ATTR


def _is_grid(layer):
    return layer.kind == 'GRID' and not _is_stitch(layer)


def _line_items(s):
    """The line art layers."""
    return [l for l in s.lines if not _is_stitch(l) and l.kind != 'GRID']


def _grid_items(s):
    """The grid (gingham) layers."""
    return [l for l in s.lines if _is_grid(l)]


def _stitch_item(s):
    for l in s.lines:
        if _is_stitch(l):
            return l
    return None


def _stitches_on(s):
    """Stitches are made when the list has a stitch row and its eye is on."""
    return s.stitches and _stitch_item(s) is not None


def _uses_addon(ob):
    s = ob.stitch_gen
    return bool(len(s.lines) or s.ribbon is not None or s.line_preview is not None
                or s.grid_preview is not None
                or core.PATH_ATTR in ob.data.attributes)


def _new_stitch_row(s):
    had = len(s.lines)
    item = s.lines.add()
    item.name = "Stitches"
    item.edge_attr = core.PATH_ATTR
    s.lines.move(len(s.lines) - 1, 0)
    return had


def _ensure_layers(ob):
    """Bring objects set up before 0.3.0 to the layer list, once: objects that
    used stitches get the stitch row, line layers their own color. Objects
    that never used the add-on are left alone (the list starts empty)."""
    s = ob.stitch_gen
    if s.ui_version >= UI_VERSION:
        return
    if not _uses_addon(ob):
        return
    if s.ui_version >= 1:
        _migrate_references(ob)
        return
    _migrate_line_layers(ob)      # also when the file was open before the add-on
    global _MUTE
    _MUTE = True
    try:
        if s.ui_version < 1:
            for l in _line_items(s):
                l.color = s.line_color
                if not l.is_property_set("width"):
                    l.width = 1.0          # the default width before 0.3.0
        used_stitches = s.ribbon is not None or core.PATH_ATTR in ob.data.attributes
        if used_stitches and _stitch_item(s) is None:
            had = _new_stitch_row(s)
            s.line_index = min(s.line_index + 1, len(s.lines) - 1) if had else 0
        s.ui_version = 1
    finally:
        _MUTE = False
    _migrate_references(ob)


UI_VERSION = 2           # 1: the layer list (0.3.0); 2: references between layers


def _migrate_references(ob):
    """Before references, a line art layer followed the stitch edges when its
    Include Stitch Edges was on (the default): it now refers to the stitches."""
    s = ob.stitch_gen
    if s.ui_version >= UI_VERSION:
        return
    global _MUTE
    _MUTE = True
    try:
        if _stitch_item(s) is not None:
            for l in _line_items(s):
                if l.include_stitch and not l.ref_attr:
                    l.ref_attr = core.PATH_ATTR
        s.ui_version = UI_VERSION
    finally:
        _MUTE = False


def _layer_by_attr(s, attr):
    for l in s.lines:
        if _layer_attr(l) == attr:
            return l
    return None


def _edge_spec(s, layer, seen=None):
    """A layer's edges as (its edge attribute, the spec of the layer it refers
    to or None): its own edges, plus what the referred layer ends up with,
    minus the edges it takes out (marked -1). A loop of references stops
    where it comes round again."""
    seen = set() if seen is None else seen
    a = _layer_attr(layer)
    seen.add(a)
    ref = _layer_by_attr(s, layer.ref_attr) if layer.ref_attr else None
    if ref is None or _layer_attr(ref) in seen:
        return (a, None)
    return (a, _edge_spec(s, ref, seen))


def _edge_set(s, layer):
    """Edge attributes involved in a layer's edges (its own and along its
    references)."""
    return tuple(sorted(core.spec_attrs(_edge_spec(s, layer))))


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


def _defer_ensure(ob):
    """Panels can't write data: add the stitch row right after drawing."""
    name = ob.name_full

    def run():
        o = bpy.data.objects.get(name)
        if o is not None and o.type == 'MESH':
            _ensure_layers(o)
            overlay.invalidate(o)
            for win in bpy.context.window_manager.windows:
                for area in win.screen.areas:
                    if area.type == 'VIEW_3D':
                        area.tag_redraw()
        return None
    bpy.app.timers.register(run, first_interval=0.0)


def _migrate_line_layers(ob):
    """Layers from before each layer had its own edges all used one shared
    set: the first keeps it, the others start their own."""
    s = ob.stitch_gen
    legacy = [l for l in _line_items(s) if not l.edge_attr]
    if len(legacy) < 2:
        return
    global _MUTE
    _MUTE = True
    try:
        used = set(ob.data.attributes.keys()) | {l.edge_attr for l in s.lines}
        n = 1
        for l in legacy[1:]:
            while f"{core.LINE_ATTR}_{n}" in used:
                n += 1
            l.edge_attr = f"{core.LINE_ATTR}_{n}"
            used.add(l.edge_attr)
    finally:
        _MUTE = False


def _new_line_layer(ob, kind='LINE'):
    """Add a line art or grid layer with its own, still empty, set of edges."""
    s = ob.stitch_gen
    used = set(ob.data.attributes.keys()) | {l.edge_attr for l in s.lines}
    n = 1
    while f"{core.LINE_ATTR}_{n}" in used:
        n += 1
    item = s.lines.add()
    item.edge_attr = f"{core.LINE_ATTR}_{n}"
    item.kind = kind
    stem = "grid" if kind == 'GRID' else "line"
    if kind == 'GRID':
        item.color = (0.05, 0.05, 0.05, 1.0)        # the black squares
    k = 1
    item.name = stem             # a default name: shown in the interface language
    while sum(1 for l in s.lines if not _is_stitch(l) and l.name == item.name) > 1:
        k += 1
        item.name = f"{stem}{k}"
    s.line_index = len(s.lines) - 1
    return item


def _line_layers(s, scene):
    """[(name, offset, width, corner depth, edge sets followed, smooth, own edges)]
    of the enabled line layers."""
    k = 0.001 / (scene.unit_settings.scale_length or 1.0)
    return [(l.name, l.offset * k, l.width * k, l.corner_inset * k, _edge_spec(s, l),
             l.smooth * k, _layer_attr(l)) for l in _line_items(s)
            if l.enabled and l.width > 0]


def regenerate(obj, scene=None, create=False):
    """Rebuild the stitches. ``create`` is only allowed from operators."""
    scene = scene or bpy.context.scene
    s = obj.stitch_gen
    _migrate_units(s)
    if create:
        _ensure_layers(obj)
    src = None
    try:
        me = obj.data
        if me.is_editmode:
            # Edit-mode attributes and UVs live in BMesh; read a temporary,
            # non-stored copy of the synced mesh instead.
            obj.update_from_editmode()
            src = obj.to_mesh(preserve_all_data_layers=True)
            me = src
        data, _topo = core.generate(obj.name_full, me, obj.matrix_world, _params(s, scene))
    except ValueError as e:  # expected limits: show the message only
        tpl = getattr(e, "template", None)
        s.status = rpt(tpl).format(**e.kw) if tpl else str(e)
        return None
    except Exception as e:  # keep the UI alive, show the error in the panel
        traceback.print_exc()
        s.status = f"{type(e).__name__}: {e}"
        return None
    finally:
        if src is not None:
            obj.to_mesh_clear()
    _last[obj.name_full] = data
    _last_params[obj.name_full] = _params(s, scene)
    overlay.invalidate(obj)
    s.status = ""
    s.dash_count = data.dash_count
    s.width_px = data.width_px
    s.gap_px = data.gap_px
    _release_shared_previews(obj)
    if create and s.ribbon is None and s.line_preview is None and s.grid_preview is None:
        _inherit_bake_settings(obj, scene)        # first set-up of this object
    sig = _params_sig(_last_params[obj.name_full])
    rib = _ribbon_object(obj, scene, create and data.dash_count > 0)
    if rib is not None:
        _write_ribbon(rib, data)
        rib.data[SIG_PROP] = sig
    lo = _line_object(obj, scene, create and len(data.line_quads) > 0)
    if lo is not None:
        _write_lines(lo, data, _layer_materials(obj, create))
        lo.data[SIG_PROP] = sig
    gdata = _grid_geometry(obj, scene)
    go = _grid_object(obj, scene, create and gdata is not None and len(gdata[1]) > 0)
    if go is not None:
        _write_grid(go, gdata, _grid_materials(obj, create))
        go.data[SIG_PROP] = sig
    if create:
        _apply_colors(obj)
    return data


_MUTE = False

# Lengths were stored in metres before 0.1.0 switched the UI to millimetres.
_MM_PROPS = ("inset", "smooth", "length", "gap", "width", "offset")


def _migrate_units(s):
    """Convert settings saved in metres to millimetres, once per object."""
    global _MUTE
    if s.units_version >= 1:
        return
    if s.ribbon is None:          # new object: values are already millimetres
        _MUTE_SET(s)
        return
    _MUTE = True
    try:
        # Only values that were actually saved can be old; unsaved ones are
        # already the new millimetre defaults. A saved length under 0.05 is a
        # metre value (0.05 mm stitches make no sense).
        for name in _MM_PROPS:
            v = getattr(s, name)
            if s.is_property_set(name) and 0 < abs(v) < 0.05:
                setattr(s, name, v * 1000.0)
        s.units_version = 1
    finally:
        _MUTE = False


def _MUTE_SET(s):
    global _MUTE
    _MUTE = True
    try:
        s.units_version = 1
    finally:
        _MUTE = False


@bpy.app.handlers.persistent
def _on_load(_dummy):
    _baking["name"] = None
    for ob in bpy.data.objects:
        if ob.type == 'MESH' and len(ob.stitch_gen.lines) > 1:
            _migrate_line_layers(ob)
        if ob.type == 'MESH':
            st = ob.stitch_gen
            row = next((i for i, l in enumerate(st.lines) if _is_stitch(l)), None)
            if (row is not None and st.ribbon is None
                    and core.PATH_ATTR not in ob.data.attributes):
                # a stitch row a 0.3.0 test build added on its own, never used
                st.lines.remove(row)
                st.line_index = max(min(st.line_index - (st.line_index > row),
                                        len(st.lines) - 1), 0)
            for l in _grid_items(ob.stitch_gen):
                if l.offset and not l.grid_from:   # grids used the line art field before
                    l.grid_from, l.offset = l.offset, 0.0
            for l in _line_items(ob.stitch_gen):
                m = re.fullmatch(r"线稿(\d*)", l.name)
                if m:                       # named by a 0.3.0 test build
                    l.name = "line" + m.group(1)
        if ob.type == 'MESH' and (len(ob.stitch_gen.lines) or ob.stitch_gen.ribbon is not None
                                  or core.PATH_ATTR in ob.data.attributes):
            _ensure_layers(ob)
    _pending.clear()
    _last_params.clear()
    for ob in bpy.data.objects:
        if ob.type == 'MESH' and ob.stitch_gen.ribbon is not None:
            _migrate_units(ob.stitch_gen)


_DEBOUNCE = 0.15         # seconds without changes before rebuilding
_pending = {}            # object name -> (time of its last change, scene name)


def _on_change(self, context):
    obj = self.id_data
    if _MUTE or not (isinstance(obj, bpy.types.Object) and obj.stitch_gen.live):
        return
    if bpy.app.background:
        regenerate(obj, context.scene)
        return
    # Rebuilding the line can take a moment on a big mesh: wait until the
    # value stops changing (a slider drag) and rebuild once.
    _schedule(obj, context.scene)


def _schedule(obj, scene):
    _pending[obj.name_full] = (time.monotonic(), scene.name if scene else "")
    if not bpy.app.timers.is_registered(_flush):
        bpy.app.timers.register(_flush, first_interval=_DEBOUNCE)


def _flush():
    now = time.monotonic()
    wait = 0.0
    for name, (t, scene_name) in list(_pending.items()):
        left = t + _DEBOUNCE - now
        if left > 0:
            wait = max(wait, left)
            continue
        del _pending[name]
        ob = bpy.data.objects.get(name)
        if ob is not None and ob.type == 'MESH' and ob.stitch_gen.live:
            regenerate(ob, bpy.data.scenes.get(scene_name))
    return wait if _pending else None


_SYNCING = [False]


@bpy.app.handlers.persistent
def _sync_previews(_scene, _depsgraph=None):
    """The previews (stitches, line art, grid) are objects of their own, but
    show and hide with the object they belong to: hiding the others
    (Shift+H) or the object itself (H) takes its previews along, and so does
    local view. Turning a preview off is done in the add-on's panel."""
    if _SYNCING[0]:
        return
    ctx = bpy.context
    vl = getattr(ctx, "view_layer", None)
    if vl is None:
        return
    spaces = []
    wm = getattr(ctx, "window_manager", None)
    for win in (wm.windows if wm else ()):
        for area in win.screen.areas:
            if area.type == 'VIEW_3D':
                sp = area.spaces.active
                if sp.local_view is not None:
                    spaces.append(sp)
    _SYNCING[0] = True
    try:
        for ob in vl.objects:
            if ob.type != 'MESH':
                continue
            st = ob.stitch_gen
            previews = [o for o in (st.ribbon, st.line_preview, st.grid_preview)
                        if o is not None and o.name in vl.objects]
            if not previews:
                continue
            hidden = ob.hide_get()
            for o in previews:
                if o.hide_get() != hidden:
                    o.hide_set(hidden)
                for sp in spaces:
                    want = ob.local_view_get(sp)
                    if o.local_view_get(sp) != want:
                        o.local_view_set(sp, want)
    except (ReferenceError, RuntimeError):
        pass
    finally:
        _SYNCING[0] = False


@bpy.app.handlers.persistent
def _on_undo_redo(scene, _depsgraph=None):
    """Blender stores an undo step right after a value changes, before the
    preview is rebuilt (that waits a moment), so a step can hold new settings
    with the old preview. Each preview records the settings it was built
    from: rebuild the ones that don't match after undo / redo."""
    for ob in bpy.data.objects:
        if ob.type != 'MESH':
            continue
        s = ob.stitch_gen
        if not s.live:
            continue
        sig = None
        for prev in (s.ribbon, s.line_preview, s.grid_preview):
            if prev is None or prev.type != 'MESH':
                continue
            sig = sig or _params_sig(_params(s, scene))
            if prev.data.get(SIG_PROP) != sig:
                _schedule(ob, scene)
                break


_baking = {"name": None}  # object being baked: the bake makes a temporary copy active


def _source_object(context):
    if _baking["name"]:
        ob = bpy.data.objects.get(_baking["name"])
        if ob is not None:
            return ob
    ob = context.active_object
    if ob is None:
        return None
    for o in bpy.data.objects:
        if o.type == 'MESH' and ob in (o.stitch_gen.ribbon, o.stitch_gen.line_preview,
                                       o.stitch_gen.grid_preview):
            return o
    return ob if ob.type == 'MESH' else None


# -- settings ------------------------------------------------------------------

def _mm(name, default, description, minv=0.0, soft_max=10.0, upd=_on_change, **kw):
    # Plain millimetres, shown with "mm" in the field like a camera's focal length:
    # Blender's scene-unit lengths step at least 0.01 units (1 cm). Own translation
    # context, so short names like "Width" don't change Blender's own translations.
    return FloatProperty(name=name, description=description, default=default,
                         min=minv, soft_max=soft_max, subtype='DISTANCE_CAMERA', unit='CAMERA',
                         precision=2, step=10, update=upd,
                         translation_context=i18n.CTX, **kw)


def _on_all_marks(self, context):
    for win in context.window_manager.windows:
        for area in win.screen.areas:
            if area.type in ('VIEW_3D', 'IMAGE_EDITOR'):
                area.tag_redraw()


def _on_marks(self, context):
    """The overlay shows the shown layers' edges, the selected one brightest.
    While the eyedropper is on, a click on a layer in the list sets it as the
    reference of the layer being edited, which stays selected."""
    ob = self.id_data
    if _PICK.get("ob") == getattr(ob, "name_full", None) and not _PICK.get("done"):
        s = ob.stitch_gen
        me = _layer_by_attr(s, _PICK["attr"])
        if 0 <= s.line_index < len(s.lines) and me is not None:
            picked = s.lines[s.line_index]
            if picked != me:
                me.ref_attr = _layer_attr(picked)
            _PICK["done"] = True
            back = next(i for i, l in enumerate(s.lines) if l == me)
            if s.line_index != back:
                s.line_index = back           # runs this again, now not picking
            return
    if isinstance(ob, bpy.types.Object):
        overlay.invalidate(ob)
        for area in context.screen.areas if context.screen else ():
            if area.type in ('VIEW_3D', 'IMAGE_EDITOR'):
                area.tag_redraw()


_DEFAULT_NAME = re.compile(r"(line|grid)(\d*)")


def _display_name(layer):
    """A default name ("line", "line2", ...) in the interface language, like
    the stitch row; a name the user typed as it is. Files use ``name``."""
    m = _DEFAULT_NAME.fullmatch(layer.name)
    if m is None:
        return layer.name
    base = bpy.app.translations.pgettext_iface("Line" if m.group(1) == "line" else "Grid",
                                               i18n.CTX)
    return f"{base} {m.group(2)}" if m.group(2) else base


def _set_display_name(layer, value):
    value = value.strip()
    if value and value != _display_name(layer):
        layer.name = value


class StitchGenLine(bpy.types.PropertyGroup):
    """A row of the layer list: the stitch row (its settings live on the
    object's settings) or a line art layer."""
    name: StringProperty(name="Name", default="line",
                         description="Used in the file name of this layer's mask")
    label: StringProperty(name="Name", get=_display_name, set=_set_display_name,
                          description="Name of this layer; a name you type also goes into "
                                      "the file name of its mask")
    enabled: BoolProperty(name="Enabled", default=True, update=_on_change,
                          description="Show and bake this layer")
    show_marks: BoolProperty(name="Show Edges", default=True, update=_on_marks,
                             description="Show this layer's marked edges in the viewport "
                                         "(display only)")
    color: bpy.props.FloatVectorProperty(
        name="Color", subtype='COLOR', size=4, min=0.0, max=1.0,
        default=(0.0, 0.0, 0.0, 1.0), update=_on_color,
        description="Color of this layer's preview in the viewport (not baked)")
    material: PointerProperty(type=bpy.types.Material, options={'HIDDEN'})
    width: _mm("Width", 0.5, "Width of the line, the same real size everywhere",
               minv=0.0, soft_max=10.0)
    # the offsets from the marked edge read as one family: Offset Inward, Offset
    # Along (grids), Corner Depth
    offset: _mm("Offset Inward", 0.0, "How far the line sits inward from the marked edges, "
                "to its outer side (0 = the line starts at the edge)", soft_max=20.0)
    corner_inset: _mm("Corner Depth", 0.0, "Extra inward offset at marked corners, tapering "
                      "off along the line, for a deeper, pointed corner", soft_max=10.0)
    smooth: _mm("Smooth", 0.0, "Smooths the inner side of the line between corners, like "
                "the stitch line; the outer side keeps the exact edge", soft_max=50.0)
    edge_attr: StringProperty(default="", options={'HIDDEN'},
                              description="Mesh attribute with this layer's edges")
    ref_attr: StringProperty(default="", options={'HIDDEN'}, update=_on_change,
                             description="Edges of the layer this one also follows")
    # replaced by references; kept so files and presets from 0.3.0 still load
    include_stitch: BoolProperty(default=True, options={'HIDDEN'})
    kind: EnumProperty(items=[('LINE', "Line Art", ""), ('GRID', "Grid", "")], default='LINE',
                       options={'HIDDEN'})
    grid_from: _mm("Offset Inward", 0.0, "Slides the squares inward from the marked edge",
                   minv=-1000.0, soft_min=-100.0, soft_max=100.0)
    grid_along: _mm("Offset Along", 0.0, "Slides the squares along the marked edge",
                    minv=-1000.0, soft_min=-100.0, soft_max=100.0)
    grid_angle: FloatProperty(name="Angle", default=0.0, subtype='ANGLE', soft_min=-math.pi,
                              soft_max=math.pi, update=_on_change, translation_context=i18n.CTX,
                              description="Turns the squares against the marked edge "
                                          "(45 degrees: on the bias)")
    grid_cell: _mm("Cell Size", 8.0, "Size of each square", minv=0.1, soft_max=50.0)
    grid_wobble: FloatProperty(name="Wobble", default=0.3, min=0.0, max=1.0, subtype='FACTOR',
                               update=_on_change, translation_context=i18n.CTX,
                               description="Bends the lines of the squares a little at random, "
                                           "as cloth pulls them out of true; the corners stay "
                                           "sharp")
    grid_layout: EnumProperty(
        name="Layout", default='LOOPS', update=_on_change, translation_context=i18n.CTX,
        items=[('LOOPS', "Follow Loops",
                "The squares follow the mesh's loops out from the marked edge, forking where "
                "the piece widens"),
               ('UNROLLED', "Unrolled",
                "The piece unrolled on its marked edge: the edge straight, the columns "
                "straight down from it, and the squares square but growing where the piece "
                "widens; nothing forks")])
    # no longer used (kept so presets saved by 0.3.0 still load)
    grid_panel: FloatProperty(default=40.0, options={'HIDDEN'})


class StitchGenSettings(bpy.types.PropertyGroup):
    ribbon: PointerProperty(type=bpy.types.Object)
    line_preview: PointerProperty(type=bpy.types.Object)
    grid_preview: PointerProperty(type=bpy.types.Object)
    stitch_color: bpy.props.FloatVectorProperty(
        name="Stitch Color", subtype='COLOR', size=4, min=0.0, max=1.0,
        default=(1.0, 0.35, 0.05, 1.0), update=_on_color,
        description="Color of the stitch preview in the viewport (not baked)")
    line_color: bpy.props.FloatVectorProperty(       # before 0.3.0: one for all layers
        subtype='COLOR', size=4, min=0.0, max=1.0, default=(0.0, 0.0, 0.0, 1.0),
        options={'HIDDEN'})
    stitches: BoolProperty(name="Stitches", default=True, update=_on_change,
                           description="Show and bake the stitches")
    lines: CollectionProperty(type=StitchGenLine)      # the layer list
    line_index: IntProperty(name="Layer", default=0, update=_on_marks)
    show_corners: BoolProperty(name="Show Corners", default=True, update=_on_marks,
                               description="Show the marked corners in the viewport "
                                           "(display only)")
    ui_version: IntProperty(default=0)
    live: BoolProperty(name="Live", default=True, update=_on_change,
                       description="Rebuild the stitches while you change the values")

    inset: _mm("Offset Inward", 3.0, "How far the stitch line sits inward from the marked "
               "edges", minv=-1000.0, soft_max=30.0)
    smooth: _mm("Smooth", 2.0, "Evens out low-poly zigzags along the line; larger values "
                "also flatten curves", soft_max=50.0)
    corner_inset: _mm("Corner Depth", 0.0, "Extra inward offset at marked corners, tapering "
                      "off along the line, for a deeper, pointed corner", soft_max=10.0)
    flip: BoolProperty(name="Flip Side", default=False, update=_on_change,
                       description="Inset to the other side of the picked edges")

    style: EnumProperty(
        name="Style", translation_context=i18n.CTX, default='DASH', update=_on_change,
        items=[('DASH', "Dashed", "Separate stitches along the line"),
               ('ZIGZAG', "Zigzag", "One thread going back and forth across the line")],
        description="Kind of stitch")
    zigzag_height: _mm("Height", 3.0, "How far the zigzag swings across the line, from "
                       "peak to peak", minv=0.0, soft_max=20.0)
    length: _mm("Length", 4.0, "Length of each stitch; for a zigzag, the distance along "
                "the line from one peak to the next", minv=0.01, soft_max=20.0)
    gap: _mm("Gap", 2.0, "Space between stitches", soft_max=20.0)
    width: _mm("Width", 1.2, "Thread width", minv=0.01, soft_max=10.0)
    roundness: FloatProperty(name="Round Ends", default=1.0, min=0.0, max=1.0,
                             description="Corner radius of each stitch as a fraction of half its width (1 = fully round ends)",
                             subtype='FACTOR', update=_on_change)
    # the same value shown as a percentage (stored as the fraction above,
    # so files and presets keep working)
    roundness_pct: FloatProperty(
        name="Round Ends", min=0.0, max=100.0, subtype='PERCENTAGE', precision=0, step=500,
        description="Corner radius of each stitch: 100% gives fully round ends",
        get=lambda self: self.roundness * 100.0,
        set=lambda self, v: setattr(self, "roundness", v / 100.0))
    offset: _mm("Offset", 0.0, "Slide the stitches along the line", minv=-1000.0,
                soft_max=20.0)
    even: BoolProperty(name="Even Fit", default=True, update=_on_change,
                       description="Closed loops get a whole number of stitches; open lines get equal space at both ends")

    resolution: EnumProperty(name="Size", description="Size of the baked mask PNGs, in pixels", items=[
        ('1024', "1024", ""), ('2048', "2048", ""), ('4096', "4096", ""), ('8192', "8192", "")],
        default='4096', update=_on_size)
    uv_map: StringProperty(name="UV Map", update=_on_change,
                           description="UV map to bake into; empty follows the mesh's active "
                                       "UV map")
    transparent: BoolProperty(name="Transparent Background", default=False,
                              description="Save white stitches on a transparent background "
                                          "(the stitch is the alpha), e.g. for Clip Studio. Off: "
                                          "white on black, as Painter masks expect")
    invert: BoolProperty(name="White Background", default=False,
                         description="Save black stitches on white (used when Transparent is off)")
    background: EnumProperty(
        name="Background", translation_context=i18n.CTX,
        items=[('BLACK', "Black", "White on black, as Painter masks expect"),
               ('WHITE', "White", "Black on white. In Clip Studio Paint, Convert Brightness "
                                  "to Opacity turns it into a mask (it can't open a transparent "
                                  "PNG that holds very little)"),
               ('TRANSPARENT', "Transparent", "White with the mask in the alpha channel "
                                              "(soft edges kept), for Photoshop and other "
                                              "2D apps")],
        get=lambda self: 2 if self.transparent else (1 if self.invert else 0),
        set=lambda self, v: (setattr(self, "transparent", v == 2),
                             setattr(self, "invert", v == 1)) and None,
        description="Background of the saved mask PNGs")
    # a plain field: the folder button next to it is the add-on's own
    output_dir: StringProperty(name="Folder", default="//stitch_masks/",
                               description="Folder for the mask PNGs; baking again overwrites them")
    samples: IntProperty(name="Samples", default=16, min=1, max=256,
                         description="Bake samples per texel")
    device: EnumProperty(name="Device", default='CPU', items=[
        ('CPU', "CPU", ""), ('GPU', "GPU", "")],
        description="What bakes. GPU is faster but can make the screen stutter while baking")
    cpu_usage: IntProperty(name="CPU Usage", default=50, min=10, max=100, subtype='PERCENTAGE',
                           description="Share of CPU cores the bake may use; the rest keeps "
                                       "Blender responsive")

    status: StringProperty()
    units_version: IntProperty(default=0)
    dash_count: IntProperty()
    width_px: FloatProperty()
    gap_px: FloatProperty()


# -- operators -----------------------------------------------------------------

def _previews():
    """Names of every preview object."""
    out = set()
    for o in bpy.data.objects:
        if o.type == 'MESH':
            st = o.stitch_gen
            out.update(x.name_full for x in (st.ribbon, st.line_preview, st.grid_preview)
                       if x is not None)
    return out


def _edited(context, main):
    """The meshes in Edit Mode, the one the panel shows first (not the
    previews, and each mesh once)."""
    previews = _previews()
    out, seen = [main], {main.data.name_full}
    for o in getattr(context, "objects_in_mode_unique_data", None) or []:
        if o.type == 'MESH' and o.name_full not in previews and o.data.name_full not in seen:
            out.append(o)
            seen.add(o.data.name_full)
    return out


def _layer_spec(s):
    """('STITCH', None) or (kind, name) of the layer selected in the list."""
    if 0 <= s.line_index < len(s.lines) and not _is_stitch(s.lines[s.line_index]):
        item = s.lines[s.line_index]
        return ('GRID' if _is_grid(item) else 'LINE', item.name)
    return ('STITCH', None)


def _select_twin(context, ob, spec, create):
    """Select on ``ob`` the layer that matches ``spec``: its stitches, or its
    line art or grid layer of that name. ``create`` makes it when missing.
    False when there is none."""
    s = ob.stitch_gen
    _ensure_layers(ob)
    kind, name = spec
    if kind == 'STITCH':
        found = next((i for i, l in enumerate(s.lines) if _is_stitch(l)), None)
    else:
        found = next((i for i, l in enumerate(s.lines) if not _is_stitch(l)
                      and _is_grid(l) == (kind == 'GRID') and l.name == name), None)
    if found is not None:
        if s.line_index != found:
            s.line_index = found
        return True
    if not create:
        return False
    global _MUTE
    _MUTE = True
    try:
        if kind == 'STITCH':               # the stitch settings are the object's own: kept
            _new_stitch_row(s)
            s.line_index = 0
        else:
            _new_line_layer(ob, kind)
            _apply_default_to_new(context, ob, kind)
            s.lines[s.line_index].name = name
        s.ui_version = UI_VERSION
    finally:
        _MUTE = False
    return True


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
        act = context.active_object
        if act is not None and act != ob and act.mode == 'EDIT':
            cls.poll_message_set(rpt("Edit the mesh, not its preview"))
        else:
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
                ob.stitch_gen.dash_count == 0 and not ob.stitch_gen.status for ob in done):
            self.report({'WARNING'}, rpt("The marked edges are too short for a stitch"))
        return {'FINISHED'}

    def _edit(self, context, ob, adds):
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
            global _MUTE
            _MUTE = True                     # edges added to a hidden layer: show it
            try:
                if _is_stitch(item):
                    s.stitches = True
                else:
                    item.enabled = True
            finally:
                _MUTE = False
        regenerate(ob, context.scene, create=True)
        return True


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
    """Remove the selected edges from the layer selected in the list, also those it gets from the layer it refers to"""
    bl_idname = "stitch_gen.path_remove"
    bl_label = "Remove Selected"

    def apply(self, ob, bm, lay):
        bm.edges.index_update()
        referred = _bm_spec_edges(bm, _referred_spec(ob))
        for e in bm.edges:
            if e.select:
                e[lay] = -1 if e.index in referred else 0


class STITCHGEN_OT_path_select(_EditPathBase, bpy.types.Operator):
    """Select the edges of the layer selected in the list, with those it gets from the layer it refers to"""
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
    """Clear all edges of the layer selected in the list, and bring back the edges it took out of its reference"""
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
    ob.update_from_editmode()
    tmp = ob.to_mesh(preserve_all_data_layers=True)
    try:
        topo = core.Topology(tmp, ob.matrix_world, "")
        chains = core.build_chains(
            topo.path_pairs(tmp, tuple([core.PATH_ATTR] + core.line_attr_names(tmp))), topo.co)
        found = set()
        for ids, closed in chains:
            found.update(core.detect_corner_vertices(topo, ids, closed, ob.stitch_gen.flip))
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
            regenerate(ob, context.scene, create=True)
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
            regenerate(ob, context.scene, create=True)
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
        regenerate(ob, context.scene, create=True)
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
        global _MUTE
        _ensure_layers(ob)
        _MUTE = True
        try:
            _new_line_layer(ob)
            _apply_default_to_new(context, ob, 'LINE')
            ob.stitch_gen.ui_version = UI_VERSION
        finally:
            _MUTE = False
        regenerate(ob, context.scene, create=True)
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
        global _MUTE
        _ensure_layers(ob)
        _MUTE = True
        try:
            _new_line_layer(ob, 'GRID')
            _apply_default_to_new(context, ob, 'GRID')
            ob.stitch_gen.ui_version = UI_VERSION
        finally:
            _MUTE = False
        regenerate(ob, context.scene, create=True)
        return {'FINISHED'}


class STITCHGEN_OT_stitch_add(bpy.types.Operator):
    """Add the stitches; while they are selected, the edge buttons mark their edges"""
    bl_idname = "stitch_gen.stitch_add"
    bl_label = "Add Stitches"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        ob = _source_object(context)
        if ob is None:
            return False
        if _stitch_item(ob.stitch_gen) is None:
            return True
        cls.poll_message_set(rpt("The object already has stitches"))
        return False

    def execute(self, context):
        ob = _source_object(context)
        s = ob.stitch_gen
        global _MUTE
        _ensure_layers(ob)
        _MUTE = True
        try:
            _new_stitch_row(s)
            s.line_index = 0
            _apply_default_to_new(context, ob, 'STITCH')
            s.stitches = True
            s.ui_version = UI_VERSION
        finally:
            _MUTE = False
        regenerate(ob, context.scene, create=True)
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
    """Remove all layers, with their marked edges and corners, and the previews from every object in the scene"""
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
            message=iface("Remove all layers, marked edges, corners and previews "
                          "from every object in this scene?"),
            confirm_text=iface("Clear"))

    def execute(self, context):
        global _MUTE
        previews = _previews()
        obs = [o for o in context.scene.objects
               if o.type == 'MESH' and o.name_full not in previews and _uses_addon(o)]
        _MUTE = True
        try:
            for ob in obs:
                s = ob.stitch_gen
                for prev in {p for p in (s.ribbon, s.line_preview, s.grid_preview)
                             if p is not None}:
                    me = prev.data if prev.type == 'MESH' else None
                    bpy.data.objects.remove(prev)
                    if me is not None and me.users == 0:
                        bpy.data.meshes.remove(me)
                s.lines.clear()
                s.line_index = 0
                s.status = ""
                s.dash_count = 0
                _drop_marks(ob)
                core.drop_cache(ob)
                overlay.invalidate(ob)
                _last.pop(ob.name_full, None)
                _last_params.pop(ob.name_full, None)
        finally:
            _MUTE = False
        col = bpy.data.collections.get(COLLECTION)
        if col is not None and not col.all_objects and not col.children:
            bpy.data.collections.remove(col)
        self.report({'INFO'}, rpt("Cleared {} objects").format(len(obs)))
        return {'FINISHED'}


def _drop_marks(ob):
    """Remove the add-on's edge and corner attributes from the mesh."""
    me = ob.data
    ours = lambda n: n == core.PATH_ATTR or n == core.LINE_ATTR or \
        n.startswith(core.LINE_ATTR + "_")                                   # noqa: E731
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
              if (ours(n) and a.domain == 'EDGE') or (n == core.CORNER_ATTR and a.domain == 'POINT')]:
        me.attributes.remove(me.attributes[n])


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
        regenerate(ob, context.scene, create=True)
        return {'FINISHED'}


def _bake_count(ob):
    """Layers the bake will write: the shown ones that have something to bake."""
    s = ob.stitch_gen
    attrs = ob.data.attributes
    n = 1 if _stitches_on(s) and s.dash_count > 0 else 0
    for l in _line_items(s):
        if l.enabled and l.width > 0 and any(a in attrs for a in _edge_set(s, l)):
            n += 1
    for l in _grid_items(s):
        if l.enabled and l.grid_cell > 0 and any(a in attrs for a in _edge_set(s, l)):
            n += 1
    return n


def _grid_layers(s, scene):
    """[(name, edge attribute, cell, angle, from edge, along edge, wobble, layout,
    edge sets followed)] of the shown grid layers, in scene units."""
    k = 0.001 / (scene.unit_settings.scale_length or 1.0)
    return [(l.name, _layer_attr(l), l.grid_cell * k, l.grid_angle, l.grid_from * k,
             l.grid_along * k, l.grid_wobble, l.grid_layout.lower(), _edge_spec(s, l))
            for l in _grid_items(s)
            if l.enabled and l.grid_cell > 0]


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
        bpy.ops.wm.path_open(filepath=bpy.path.abspath(_source_object(context).stitch_gen.output_dir))
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


_PICK = {}               # while the eyedropper is on: object name, edges of the layer


def _layer_label(layer):
    return iface("Stitches") if _is_stitch(layer) else _display_name(layer)


def _layer_icon(layer):
    return STITCH_ICON if _is_stitch(layer) else GRID_ICON if _is_grid(layer) else LINE_ICON


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
        if _PICK.get("ob") == ob.name_full:            # clicked again: stop picking
            _PICK["cancel"] = True
            return {'CANCELLED'}
        _PICK.clear()
        _PICK.update(ob=ob.name_full, attr=_layer_attr(item), done=False, cancel=False,
                     win=context.window)
        context.window.cursor_modal_set('EYEDROPPER')
        context.workspace.status_text_set(iface("Click a layer in the list") + "    Esc")
        bpy.app.timers.register(_keep_eyedropper, first_interval=_EYEDROPPER_EVERY)
        context.window_manager.modal_handler_add(self)
        _redraw_views()
        return {'RUNNING_MODAL'}

    def _end(self, context, result):
        _PICK.clear()
        context.window.cursor_modal_restore()
        context.workspace.status_text_set(None)
        _redraw_views()
        return result

    def modal(self, context, event):
        if _PICK.get("done"):
            return self._end(context, {'FINISHED'})
        if _PICK.get("cancel") or not _PICK:
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
    win = _PICK.get("win")
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
    """What a preset of this kind sets on the object: the stitch settings, or
    the selected layer if it is of that kind; None otherwise."""
    s = ob.stitch_gen
    if kind == 'STITCH':
        return s
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
        data.property_unset(name)
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
        global _MUTE
        _MUTE = True
        try:
            ok = _apply_preset(context, ob, self.kind, filepath)
        except Exception as e:
            self.report({'ERROR'}, f"{type(e).__name__}: {e}")
            ok = False
        finally:
            _MUTE = False
        if not ok:
            return {'CANCELLED'}
        regenerate(ob, context.scene, create=True)
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
    """Use this preset as the default: new layers start with it, and Default applies it. Click again to go back to the add-on's own default"""
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
        return (s, "stitch_color") if _is_stitch(item) else (item, "color")

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
        stitch = _is_stitch(item)
        on = s.stitches if stitch else item.enabled
        row = layout.row(align=True)
        name = row.row(align=True)
        name.active = on
        if stitch:
            name.label(text="Stitches", icon=STITCH_ICON)
        else:
            name.prop(item, "label", text="", emboss=False,
                      icon=GRID_ICON if _is_grid(item) else LINE_ICON)
        # a link when this layer follows another one, so the list shows who follows whom
        ref = _layer_by_attr(s, item.ref_attr) if item.ref_attr else None
        if ref is not None and ref != item:
            row.label(text="", **_icon("link", "wcol_list_item"))
        # The color as an icon like the toggles next to it (a framed swatch
        # gets joined with the swatches of the rows above and below).
        op = row.operator("stitch_gen.edit_color", text="", emboss=False,
                          icon_value=_color_icon(s.stitch_color if stitch else item.color))
        op.index = index
        marks = row.row(align=True)
        marks.active = item.show_marks and context.scene.stitch_gen_marks
        marks.prop(item, "show_marks", text="", emboss=False,
                   **_icon("marks", "wcol_list_item", item.show_marks))
        row.prop(s if stitch else item, "stitches" if stitch else "enabled", text="",
                 icon='HIDE_OFF' if on else 'HIDE_ON', emboss=False)


_bake_flag = {"state": None}


def _on_bake_complete(*_args):
    _bake_flag["state"] = "done"


def _on_bake_cancel(*_args):
    _bake_flag["state"] = "cancel"


def _redraw(context):
    for win in context.window_manager.windows:
        for area in win.screen.areas:
            if area.type in ('VIEW_3D', 'STATUSBAR'):
                area.tag_redraw()


def _bakeable(ob, scene):
    s = ob.stitch_gen
    return bool(_bake_count(ob) and ((_stitches_on(s) and s.ribbon is not None)
                                     or _line_layers(s, scene) or _grid_layers(s, scene)))


def _bake_targets(context):
    """What one press of Bake bakes: the object the panel shows and the other
    selected objects, each that has something to bake, with its own settings."""
    main = _source_object(context)
    obs = [main] if main is not None else []
    previews = _previews()
    obs += [o for o in context.selected_objects
            if o.type == 'MESH' and o != main and o.name_full not in previews]
    return [o for o in obs if _bakeable(o, context.scene)]


def _object_by_uid(uid):
    return next((o for o in bpy.data.objects if o.session_uid == uid), None)


class STITCHGEN_OT_bake(bpy.types.Operator):
    """Bake the stitches and each line art layer into a 16-bit mask PNG per texture set, for every selected object"""
    bl_idname = "stitch_gen.bake"
    bl_label = "Bake Masks"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        if _source_object(context) is None or context.window_manager.stitch_gen_baking:
            return False
        if _bake_targets(context):
            return True
        cls.poll_message_set(rpt("Nothing to bake: show a layer that has edges"))
        return False

    def _jobs(self, context, ob, data):
        """(stitch session or None, line bake or None) for this object."""
        s = ob.stitch_gen
        session = lines = None
        if _stitches_on(s) and data.dash_count > 0 and s.ribbon is not None:
            session = bake.BakeSession(context, ob, s.ribbon, data, s)
        layers = _line_layers(s, context.scene)
        entry = core._cache.get(ob.name_full)
        texel = []                          # bakes computed per texel (no Cycles)
        if layers and entry is not None:
            lb = bake.LineBake(ob, entry, s, layers)
            if lb.groups:
                texel.append(lb)
        grids = _grid_layers(s, context.scene)
        if grids and entry is not None:
            gb = bake.GridBake(ob, entry, s, grids)
            if gb.groups:
                texel.append(gb)
        lines = bake.Chain(texel) if texel else None
        if session is None and lines is None:
            raise RuntimeError(rpt("No stitches to bake"))
        return session, lines

    def _error(self, ob, msg):
        many = len(getattr(self, "_queue", ())) > 1
        self.report({'ERROR'}, f"{ob.name}: {msg}" if many else msg)

    def execute(self, context):
        """Blocking bake (used without a window, e.g. from scripts)."""
        targets = _bake_targets(context)
        self._queue = [o.session_uid for o in targets]
        paths = []
        try:
            for ob in targets:
                _baking["name"] = ob.name_full
                data = regenerate(ob, context.scene, create=True)
                if data is None:
                    self._error(ob, ob.stitch_gen.status)
                    return {'CANCELLED'}
                try:
                    session, lines = self._jobs(context, ob, data)
                    if session is not None:
                        paths += bake.bake_masks(context, ob, ob.stitch_gen.ribbon, data,
                                                 ob.stitch_gen)
                    if lines is not None:
                        for i in range(len(lines.groups)):
                            paths += lines.step(i, paths)
                except Exception as e:
                    traceback.print_exc()
                    self._error(ob, str(e))
                    return {'CANCELLED'}
        finally:
            _baking["name"] = None
        self.report({'INFO'}, rpt("Saved {}").format(", ".join(paths)))
        return {'FINISHED'}

    def invoke(self, context, event):
        """Bake as a background job: Blender stays usable, the status bar shows
        the progress (cancel there or with Esc). The selected objects are baked
        one after another."""
        if bpy.app.background or context.window is None:
            return self.execute(context)
        self._queue = [o.session_uid for o in _bake_targets(context)]    # names can change
        self._k = -1
        self._session = self._lines = None
        self._written = []
        self._window = context.window
        handlers = bpy.app.handlers
        handlers.object_bake_complete.append(_on_bake_complete)
        handlers.object_bake_cancel.append(_on_bake_cancel)
        wm = context.window_manager
        wm.stitch_gen_baking = True
        started = self._next_object(context)
        if not started:
            if started is None:
                self.report({'ERROR'}, rpt("No stitches to bake"))
            return self._end(context, ok=False)
        self._timer = wm.event_timer_add(0.25, window=context.window)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _next_object(self, context):
        """Start baking the next object in the queue. True when started, False
        on an error (reported), None when there is nothing left."""
        while True:
            self._session = self._lines = None
            self._k += 1
            if self._k >= len(self._queue):
                return None
            ob = _object_by_uid(self._queue[self._k])
            if ob is None:                     # deleted while the others were baking
                continue
            _baking["name"] = ob.name_full
            data = regenerate(ob, context.scene, create=True)
            if data is None:
                self._error(ob, ob.stitch_gen.status)
                return False
            try:
                self._session, self._lines = self._jobs(context, ob, data)
                if self._session is not None:
                    self._session.begin()
                    if not self._session.groups:
                        self._session.end()
                        self._session = None
            except Exception as e:
                traceback.print_exc()
                if self._session is not None:
                    self._session.end()
                    self._session = None
                self._error(ob, str(e))
                return False
            if self._session is None and self._lines is None:
                continue
            self._i = 0
            return self._start(context)

    def _steps(self):
        a = len(self._session.groups) if self._session is not None else 0
        b = len(self._lines.groups) if self._lines is not None else 0
        return a, b

    def _start(self, context):
        wm = context.window_manager
        a, b = self._steps()
        n = a + b
        k, objects = self._k, len(self._queue)
        wm.stitch_gen_bake_progress = (k + self._i / n) / objects
        label = rpt("Baking {}/{}").format(self._i + 1, n)
        if objects > 1:                  # which object, as the outliner names it
            label = f"{_object_by_uid(self._queue[k]).name}  {self._i + 1}/{n}"
        wm.stitch_gen_bake_label = label
        _redraw(context)
        if self._i >= a:                 # line art: no Cycles job, done on the next tick
            _bake_flag["state"] = "lines"
            return True
        _bake_flag["state"] = "running"
        try:
            kwargs = self._session.prepare(self._i)
            with context.temp_override(window=self._window):
                res = bpy.ops.object.bake('INVOKE_DEFAULT', **kwargs)
        except Exception as e:
            traceback.print_exc()
            self.report({'ERROR'}, str(e))
            return False
        if 'CANCELLED' in res:
            return False
        if 'FINISHED' in res:            # ran without a job: already done
            _bake_flag["state"] = "done"
        return True

    def modal(self, context, event):
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}
        state = _bake_flag["state"]
        if state in ("done", "lines"):
            a, b = self._steps()
            try:
                if state == "done":
                    self._written.append(self._session.finish())
                else:
                    self._written += self._lines.step(self._i - a, self._written)
            except Exception as e:
                traceback.print_exc()
                self.report({'ERROR'}, str(e))
                return self._end(context, ok=False)
            self._i += 1
            if self._i == a and self._session is not None:
                self._session.end()          # scene back before the line art steps
            if self._i < a + b:
                if not self._start(context):
                    return self._end(context, ok=False)
                return {'PASS_THROUGH'}
            started = self._next_object(context)
            if started:
                return {'PASS_THROUGH'}
            return self._end(context, ok=started is None)
        if state == "cancel":
            self.report({'WARNING'}, rpt("Baking stopped"))
            return self._end(context, ok=False)
        return {'PASS_THROUGH'}

    def _end(self, context, ok):
        wm = context.window_manager
        if getattr(self, "_timer", None) is not None:
            wm.event_timer_remove(self._timer)
            self._timer = None
        handlers = bpy.app.handlers
        for lst, fn in ((handlers.object_bake_complete, _on_bake_complete),
                        (handlers.object_bake_cancel, _on_bake_cancel)):
            if fn in lst:
                lst.remove(fn)
        _bake_flag["state"] = None
        try:
            if self._session is not None:
                self._session.end()
        except Exception:
            traceback.print_exc()
        wm.stitch_gen_baking = False
        _baking["name"] = None
        wm.stitch_gen_bake_progress = 0.0
        _redraw(context)
        if ok:
            self.report({'INFO'}, rpt("Saved {}").format(", ".join(self._written)))
            return {'FINISHED'}
        return {'CANCELLED'}


# -- panel ---------------------------------------------------------------------

STITCH_ICON = 'MOD_DASH'
LINE_ICON = 'IPO_LINEAR'
GRID_ICON = 'MESH_GRID'


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
        if ob is None or not len(ob.stitch_gen.lines):
            return
        s = ob.stitch_gen
        row.separator()
        if not s.live:
            row.operator("stitch_gen.update", text="", icon='FILE_REFRESH')
        row.prop(s, "live", text="", icon='PLAY')

    def draw(self, context):
        ob = _source_object(context)
        s = ob.stitch_gen
        lay = self.layout
        lay.use_property_split = True
        lay.use_property_decorate = False
        if s.ui_version < UI_VERSION and _uses_addon(ob):
            _defer_ensure(ob)          # set up by an older version: bring it up to date

        row = lay.row()
        row.template_list("STITCHGEN_UL_lines", "", s, "lines", s, "line_index", rows=3)
        ops = row.column(align=True)
        ops.menu("STITCHGEN_MT_add_layer", text="", icon='ADD')
        ops.operator("stitch_gen.line_remove", text="", icon='REMOVE')
        ops.menu("STITCHGEN_MT_list_extras", text="", icon='DOWNARROW_HLT')
        if not len(s.lines):
            return                     # nothing to set up until there is a layer
        if s.status:
            lay.label(text=s.status, icon='ERROR', translate=False)

        item = s.lines[s.line_index] if 0 <= s.line_index < len(s.lines) else s.lines[0]
        stitch = _is_stitch(item)
        is_grid = _is_grid(item)

        # marking, in working order: the selected layer's edges, then the
        # corners and side, which all layers share (a corner is a vertex)
        mark = lay.column()
        r, end = _tool_row(mark, "Edges", tail=True)
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
            r.operator("stitch_gen.corner_mark", text="", icon='ADD')
            r.operator("stitch_gen.corner_clear", text="", icon='REMOVE')
            r.operator("stitch_gen.corner_select", text="", icon='RESTRICT_SELECT_OFF')
            r.operator("stitch_gen.corner_detect", text="Auto")
            _marks_toggle(end, s, "show_corners", "corners")
            mark.prop(s, "flip")

        # the selected layer's own settings, with its presets
        header, body = lay.panel("stitch_gen_layer", default_closed=False)
        if stitch:
            header.label(text="Stitches", icon=STITCH_ICON)
        else:
            header.label(text=_display_name(item), icon=GRID_ICON if is_grid else LINE_ICON,
                         translate=False)
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
            job = _unroll_jobs.get(ob.name_full)
            if job is not None and job["thread"].is_alive():
                k, n = job["round"]
                body.progress(factor=(k + 0.5) / max(n, 1), type='BAR',
                              text=iface("Unrolling {}/{}").format(k + 1, n))
        elif body:
            # Same groups, same order for all: where the line runs, then its shape.
            body = body.column()
            src = s if stitch else item
            body.active = s.stitches if stitch else item.enabled
            col = body.column(align=True)
            col.prop(src, "inset" if stitch else "offset")
            col.prop(src, "corner_inset")
            body.prop(src, "smooth")
            col = body.column(align=True)
            if stitch:
                col = body.column()
                col.row().prop(s, "style", expand=True)
                col = body.column(align=True)
            col.prop(src, "width")
            if stitch and s.style == 'ZIGZAG':
                col.prop(s, "length")
                col.prop(s, "zigzag_height")
            elif stitch:
                col.prop(s, "length")
                col.prop(s, "gap")
                col.prop(s, "roundness_pct", slider=True)
                body.prop(s, "even")

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
        if not body:                       # folded away: the button stays at hand
            bake_button(header.row())
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
            body.row().prop(s, "background", expand=True)
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


classes = (
    StitchGenLine,
    StitchGenSettings,
    STITCHGEN_OT_path_add,
    STITCHGEN_OT_path_remove,
    STITCHGEN_OT_path_select,
    STITCHGEN_OT_path_clear,
    STITCHGEN_OT_corner_detect,
    STITCHGEN_OT_corner_select,
    STITCHGEN_OT_corner_mark,
    STITCHGEN_OT_corner_clear,
    STITCHGEN_OT_update,
    STITCHGEN_OT_line_add,
    STITCHGEN_OT_grid_add,
    STITCHGEN_OT_stitch_add,
    STITCHGEN_MT_add_layer,
    STITCHGEN_OT_line_remove,
    STITCHGEN_OT_clear_scene,
    STITCHGEN_MT_list_extras,
    STITCHGEN_OT_set_uv_map,
    STITCHGEN_OT_edit_color,
    STITCHGEN_OT_pick_folder,
    STITCHGEN_OT_open_folder,
    STITCHGEN_OT_reset_defaults,
    STITCHGEN_OT_apply_preset,
    STITCHGEN_OT_preset_default,
    STITCHGEN_OT_stitch_preset_add,
    STITCHGEN_OT_grid_preset_add,
    STITCHGEN_MT_grid_presets,
    STITCHGEN_PT_grid_presets,
    STITCHGEN_OT_line_preset_add,
    STITCHGEN_MT_stitch_presets,
    STITCHGEN_MT_line_presets,
    STITCHGEN_PT_stitch_presets,
    STITCHGEN_PT_line_presets,
    STITCHGEN_MT_uv_maps,
    STITCHGEN_OT_set_reference,
    STITCHGEN_MT_reference,
    STITCHGEN_OT_pick_reference,
    STITCHGEN_OT_reference_menu,
    STITCHGEN_UL_lines,
    STITCHGEN_OT_bake,
    VIEW3D_PT_stitch_gen,
)


def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Object.stitch_gen = PointerProperty(type=StitchGenSettings)
    wm = bpy.types.WindowManager
    wm.stitch_gen_baking = BoolProperty(default=False)
    bpy.types.Scene.stitch_gen_last_size = StringProperty(default="", options={'HIDDEN'})
    bpy.types.Scene.stitch_gen_marks = BoolProperty(
        name="Show Marks", default=True, update=_on_all_marks,
        description="Show the marked edges and corners of all layers in the viewport (display only)")
    wm.stitch_gen_bake_progress = FloatProperty(default=0.0, min=0.0, max=1.0)
    wm.stitch_gen_bake_label = StringProperty(default="")
    i18n.register(__package__)
    overlay.register()
    _icons["coll"] = bpy.utils.previews.new()
    bpy.app.handlers.load_post.append(_on_load)
    bpy.app.handlers.undo_post.append(_on_undo_redo)
    bpy.app.handlers.redo_post.append(_on_undo_redo)
    bpy.app.handlers.depsgraph_update_post.append(_sync_previews)


def unregister():
    if _sync_previews in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_sync_previews)
    if _on_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_load)
    for lst in (bpy.app.handlers.undo_post, bpy.app.handlers.redo_post):
        if _on_undo_redo in lst:
            lst.remove(_on_undo_redo)
    if bpy.app.timers.is_registered(_flush):
        bpy.app.timers.unregister(_flush)
    _pending.clear()
    del bpy.types.Object.stitch_gen
    for name in ("stitch_gen_last_size", "stitch_gen_marks"):
        if hasattr(bpy.types.Scene, name):
            delattr(bpy.types.Scene, name)
    for name in ("stitch_gen_baking", "stitch_gen_bake_progress", "stitch_gen_bake_label"):
        if hasattr(bpy.types.WindowManager, name):
            delattr(bpy.types.WindowManager, name)
    i18n.unregister(__package__)
    overlay.unregister()
    if _icons["coll"] is not None:
        bpy.utils.previews.remove(_icons["coll"])
        _icons["coll"] = None
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
    core.drop_cache()
