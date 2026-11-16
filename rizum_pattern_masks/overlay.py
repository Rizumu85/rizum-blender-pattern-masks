# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Rizum
"""Viewport overlay, in the 3D view and in the UV editor:

* the marked edges of each layer whose marks are shown: stitch layers'
  purple, line art and grid layers' green, the layer selected in the list brightest,
* for the selected layer, the edges it takes out of what it gets from the
  layer it refers to, red,
* the vertices marked as corners as yellow dots.

Drawing only; nothing is stored in the file or baked."""

import time

import bpy
import bmesh
import numpy as np
import gpu
from gpu_extras.batch import batch_for_shader

from . import core, preview

YELLOW = (1.0, 0.8, 0.1, 1.0)
OUTLINE = (0.08, 0.06, 0.02, 0.9)
PURPLE = (0.72, 0.25, 1.0, 0.45)     # quiet, so Blender's own selection stays visible
GREEN = (0.3, 1.0, 0.35, 0.55)    # not cyan: Blender draws sharp edges in cyan
RED = (1.0, 0.25, 0.2, 0.75)      # edges the selected layer takes out
DIM = 0.18                        # alpha of the layers not selected in the list
LIFT = 0.0004            # metres off the surface, so the marks are not hidden by it
EDIT_REFRESH = 0.25      # seconds: in Edit Mode the marks are read again at most this often

_cache = {}              # object name -> dict of point/line coordinates
_handles = []


def invalidate(ob=None):
    if ob is None:
        _cache.clear()
    else:
        _cache.pop(ob.name_full, None)


def _shown(ob):
    """[(edge attribute, color, sign)] of the layers whose marks are shown,
    the selected layer last (drawn on top) and at full strength; sign 1: its
    own edges, -1: the edges it takes out (selected layer only)."""
    s = ob.stitch_gen
    rows = list(s.lines)
    # Python wrappers of the same row are not identical: compare positions
    sel = s.line_index if 0 <= s.line_index < len(s.lines) else None
    out = []
    for i, l in enumerate(rows):
        if not l.show_marks:
            continue
        attr = l.edge_attr or core.LINE_ATTR
        base = PURPLE if l.kind == 'STITCH' or attr == core.PATH_ATTR else GREEN
        active = i == sel
        out.append((active, attr, base if active else base[:3] + (DIM,), 1))
        if active and l.ref_attr:
            out.append((active, attr, RED, -1))
    out.sort(key=lambda t: t[0])
    return [(attr, col, sign) for _, attr, col, sign in out]


def _key(ob):
    """What the marks were read from: the mesh (undo brings back another),
    the mode, where the object is, and which layers' marks show how."""
    me = ob.data
    s = ob.stitch_gen
    return (me.as_pointer(), me.is_editmode, tuple(v for row in ob.matrix_world for v in row),
            s.line_index, s.show_corners, s.uv_map,
            tuple((l.show_marks, l.edge_attr, l.ref_attr, l.kind) for l in s.lines))


def _marks(ob):
    """Shown layers' edges and the marked corners, in world space (lifted
    along the normal) and in UV space. Read again when the add-on changes
    them (invalidate), when the key changes, and in Edit Mode, where the
    mesh is being worked on, at most every EDIT_REFRESH seconds."""
    me = ob.data
    hit = _cache.get(ob.name_full)
    if hit is not None and hit["key"] == _key(ob) and (
            not me.is_editmode or time.monotonic() - hit["at"] < EDIT_REFRESH):
        return hit
    mw = ob.matrix_world
    nmat = mw.to_3x3().inverted_safe().transposed()
    s = ob.stitch_gen
    uv_name = s.uv_map
    shown = _shown(ob)
    out = {"dots": [], "dots_uv": [], "edges": [], "edges_uv": [], "key": _key(ob),
           "at": time.monotonic()}

    def lifted(co, normal):
        return tuple(mw @ co + (nmat @ normal).normalized() * LIFT)

    on_path = set()
    if me.is_editmode:
        bm = bmesh.from_edit_mesh(me)
        uvl = (bm.loops.layers.uv.get(uv_name) if uv_name else None) or bm.loops.layers.uv.active
        for name, col, sign in shown:
            path = bm.edges.layers.int.get(name)
            pts, pts_uv = [], []
            if path is not None:
                for e in bm.edges:
                    if e[path] * sign <= 0:
                        continue
                    a, b = e.verts
                    if sign > 0:
                        on_path.update((a, b))
                    pts += [lifted(a.co, a.normal), lifted(b.co, b.normal)]
                    if uvl is not None:
                        for lp in e.link_loops:
                            pts_uv += [tuple(lp[uvl].uv) + (0.0,),
                                       tuple(lp.link_loop_next[uvl].uv) + (0.0,)]
            out["edges"].append((pts, col))
            out["edges_uv"].append((pts_uv, col))
        lay = bm.verts.layers.int.get(core.CORNER_ATTR)
        if s.show_corners and lay is not None:
            for v in on_path:
                if v[lay]:
                    out["dots"].append(lifted(v.co, v.normal))
                    if uvl is not None:
                        out["dots_uv"] += [tuple(lp[uvl].uv) + (0.0,) for lp in v.link_loops]
    else:
        # Object Mode: every vertex lifted at once. (The UV editor shows marks
        # in Edit Mode only, which reads the BMesh above.)
        nv = len(me.vertices)
        co = np.empty(nv * 3, np.float32)
        no = np.empty(nv * 3, np.float32)
        me.vertices.foreach_get("co", co)
        me.vertices.foreach_get("normal", no)
        M, Nm = np.array(mw, np.float64), np.array(nmat, np.float64)
        n = no.reshape(-1, 3) @ Nm.T
        n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-30)
        P = co.reshape(-1, 3) @ M[:3, :3].T + M[:3, 3] + n * LIFT
        on_path = np.zeros(nv, bool)
        for name, col, sign in shown:
            pairs = core.read_path_edges(me, name, sign)
            if sign > 0:
                on_path[pairs.ravel()] = True
            out["edges"].append((P[pairs.ravel()].tolist(), col))
            out["edges_uv"].append(([], col))
        if s.show_corners:
            idx = core.read_corner_verts(me)
            out["dots"] = P[idx[on_path[idx]]].tolist()
    _cache[ob.name_full] = out
    return out


def _objects(context):
    space = context.space_data if getattr(context.space_data, "type", "") == 'VIEW_3D' else None
    return [ob for ob in preview.objects(context) if ob.visible_get(viewport=space)]


def _point_shader():
    """Points in one colour: their own shader since Blender 4.5, the plain
    uniform colour one before."""
    try:
        return gpu.shader.from_builtin('POINT_UNIFORM_COLOR')
    except ValueError:
        return gpu.shader.from_builtin('UNIFORM_COLOR')


def _batches(m, key):
    """GPU batches of a cached marks entry, made on first draw."""
    b = m.get("_b_" + key)
    if b is None:
        if key.startswith("edges"):
            shader = gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
            b = [(batch_for_shader(shader, 'LINES', {"pos": pts}), col)
                 for pts, col in m[key] if pts]
        else:
            shader = _point_shader()
            b = [batch_for_shader(shader, 'POINTS', {"pos": m[key]})] if m[key] else []
        m["_b_" + key] = b
    return b


def _lines(batches, width):
    if not batches:
        return
    shader = gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
    region = bpy.context.region
    shader.uniform_float("viewportSize", (region.width, region.height))
    shader.uniform_float("lineWidth", width)
    for batch, color in batches:
        shader.uniform_float("color", color)
        batch.draw(shader)


def _dots(batches, size):
    if not batches:
        return
    shader = _point_shader()
    batch = batches[0]
    gpu.state.point_size_set(size + 4)
    shader.uniform_float("color", OUTLINE)
    batch.draw(shader)
    gpu.state.point_size_set(size)
    shader.uniform_float("color", YELLOW)
    batch.draw(shader)


def _marks_on(context):
    return getattr(context.scene, "stitch_gen_marks", True)


def _draw_3d():
    if not _marks_on(bpy.context):
        return
    obs = _objects(bpy.context)
    if not obs:
        return
    gpu.state.depth_test_set('LESS_EQUAL')
    gpu.state.blend_set('ALPHA')
    for ob in obs:
        m = _marks(ob)
        _lines(_batches(m, "edges"), 2.0)
        _dots(_batches(m, "dots"), 6.0)
    gpu.state.depth_test_set('NONE')
    gpu.state.blend_set('NONE')
    gpu.state.point_size_set(1.0)


def _draw_uv():
    context = bpy.context
    space = context.space_data
    if space is None or getattr(space, "mode", "") != 'UV' or not _marks_on(context):
        return
    obs = [ob for ob in _objects(context) if ob.mode == 'EDIT']
    if not obs:
        return
    gpu.state.blend_set('ALPHA')
    for ob in obs:
        m = _marks(ob)
        _lines(_batches(m, "edges_uv"), 2.0)
        _dots(_batches(m, "dots_uv"), 6.0)
    gpu.state.blend_set('NONE')
    gpu.state.point_size_set(1.0)


def register():
    _handles.append((bpy.types.SpaceView3D, bpy.types.SpaceView3D.draw_handler_add(
        _draw_3d, (), 'WINDOW', 'POST_VIEW')))
    _handles.append((bpy.types.SpaceImageEditor, bpy.types.SpaceImageEditor.draw_handler_add(
        _draw_uv, (), 'WINDOW', 'POST_VIEW')))


def unregister():
    for space, h in _handles:
        space.draw_handler_remove(h, 'WINDOW')
    _handles.clear()
    _cache.clear()
