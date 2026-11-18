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
EDIT_REFRESH = 0.25      # seconds: in Edit Mode the marked edges are followed at most this often

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


class _Stale(Exception):
    """A kept edge is no longer marked: the mesh is looked through again."""


def _marks(ob, uv=False):
    """Shown layers' edges and the marked corners, in world space (lifted
    along the normal) and, in Edit Mode when ``uv`` is asked for (the UV
    editor), in UV space.

    Read again when the add-on changes the marks (invalidate) and when the
    key changes. In Edit Mode, where the mesh is being worked on, the whole
    mesh is looked through only then, when its number of vertices, edges or
    faces changed, and when a kept edge is gone or no longer marked;
    otherwise just the marked elements are followed, at most every
    EDIT_REFRESH seconds, so the cost goes with the marks and not with the
    size of the mesh. (Edges marked by other tools without changing those
    numbers show after the next look.)"""
    me = ob.data
    key = _key(ob)
    hit = _cache.get(ob.name_full)
    if hit is not None and hit["key"] != key:
        hit = None
    if not me.is_editmode:
        if hit is None:
            hit = _cache[ob.name_full] = _read_object(ob, key)
        return hit
    now = time.monotonic()
    out = hit
    if hit is None or now - hit["at"] >= EDIT_REFRESH:
        bm = bmesh.from_edit_mesh(me)
        counts = (len(bm.verts), len(bm.edges), len(bm.faces))
        # the picked elements are those of one BMesh (undo builds another) and
        # stay valid only while its Python object lives, so that is kept too
        same = hit is not None and hit["bm"] is bm and hit["counts"] == counts
        picked = hit["picked"] if same else None
        out = None
        if picked is not None:
            try:
                out = _placed(ob, bm, picked, hit)
            except (ReferenceError, _Stale):
                picked = None
        if out is None:
            picked = _pick(ob, bm)
            out = _placed(ob, bm, picked, None)
        out.update(key=key, at=now, picked=picked, counts=counts, bm=bm)
        _cache[ob.name_full] = out
    if uv and now - out.get("uv_at", -EDIT_REFRESH) >= EDIT_REFRESH:
        try:
            _place_uv(ob, out, now)
        except ReferenceError:          # an edge went since the last look
            invalidate(ob)
            return _marks(ob, uv)
    return out


def _pick(ob, bm):
    """The marked elements of an Edit Mode mesh, from one look through all
    its edges per edge attribute shown: each marked vertex once, and per
    shown layer its edges, as positions in that list of vertices."""
    verts, at = [], {}

    def number(v):
        i = at.get(v)
        if i is None:
            i = at[v] = len(verts)
            verts.append(v)
        return i

    shown = _shown(ob)
    marked = {}                         # edge attribute -> [(edge, value)]
    for name in {name for name, _col, _sign in shown}:
        path = bm.edges.layers.int.get(name)
        marked[name] = [] if path is None else [(e, e[path]) for e in bm.edges if e[path]]
    layers, on_path = [], set()
    for name, col, sign in shown:
        edges = [e for e, value in marked[name] if value * sign > 0]
        idx = np.array([number(v) for e in edges for v in e.verts], np.intp)
        if sign > 0:
            on_path.update(idx.tolist())
        layers.append((col, edges, idx, name, sign))
    lay = bm.verts.layers.int.get(core.CORNER_ATTR)
    corners = []
    if ob.stitch_gen.show_corners and lay is not None:
        corners = [i for i in sorted(on_path) if verts[i][lay]]
    return {"verts": verts, "layers": layers, "corners": np.array(corners, np.intp)}


def _placed(ob, bm, picked, hit):
    """Where the picked edges and corners of an Edit Mode mesh are now;
    ``hit`` itself when nothing moved since it was made from the same pick
    (the batches made for it stay). Raises when a kept edge is gone
    (ReferenceError) or no longer marked (_Stale)."""
    for _col, edges, _idx, name, sign in picked["layers"]:
        path = bm.edges.layers.int.get(name)
        if edges and (path is None or not all(e[path] * sign > 0 for e in edges)):
            raise _Stale
    verts = picked["verts"]
    co = np.array([v.co[:] for v in verts], np.float64).reshape(-1, 3)
    normal = np.array([v.normal[:] for v in verts], np.float64).reshape(-1, 3)
    if hit is not None and hit["picked"] is picked and np.array_equal(co, hit["co"]) \
            and np.array_equal(normal, hit["normal"]):
        return hit
    mw = ob.matrix_world
    M = np.array(mw, np.float64)
    n = normal @ np.array(mw.to_3x3().inverted_safe().transposed(), np.float64).T
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-30)
    P = (co @ M[:3, :3].T + M[:3, 3] + n * LIFT).astype(np.float32)
    return {"co": co, "normal": normal,
            "edges": [(P[layer[2]], layer[0]) for layer in picked["layers"]],
            "edges_uv": [([], layer[0]) for layer in picked["layers"]],
            "dots": P[picked["corners"]], "dots_uv": []}


def _place_uv(ob, m, now):
    """The UV points of an Edit Mode entry's edges and corners, for the UV
    editor: worked out only when it draws."""
    bm, picked = m["bm"], m["picked"]
    name = ob.stitch_gen.uv_map
    uvl = (bm.loops.layers.uv.get(name) if name else None) or bm.loops.layers.uv.active
    edges_uv, dots = [], []
    for col, edges, _idx, _name, _sign in picked["layers"]:
        pts = []
        if uvl is not None:
            for e in edges:
                for lp in e.link_loops:
                    pts += [tuple(lp[uvl].uv) + (0.0,),
                            tuple(lp.link_loop_next[uvl].uv) + (0.0,)]
        edges_uv.append((pts, col))
    if uvl is not None:
        verts = picked["verts"]
        dots = [tuple(lp[uvl].uv) + (0.0,) for i in picked["corners"].tolist()
                for lp in verts[i].link_loops]
    m["uv_at"] = now
    if edges_uv != m["edges_uv"] or dots != m["dots_uv"]:
        m["edges_uv"], m["dots_uv"] = edges_uv, dots
        m.pop("_b_edges_uv", None)      # their batches are made again
        m.pop("_b_dots_uv", None)


def _read_object(ob, key):
    """The marks of a mesh in Object Mode: every vertex lifted at once. (The
    UV editor shows marks in Edit Mode only.)"""
    me = ob.data
    mw = ob.matrix_world
    nmat = mw.to_3x3().inverted_safe().transposed()
    out = {"dots": [], "dots_uv": [], "edges": [], "edges_uv": [], "key": key,
           "at": time.monotonic()}
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
    for name, col, sign in _shown(ob):
        pairs = core.read_path_edges(me, name, sign)
        if sign > 0:
            on_path[pairs.ravel()] = True
        out["edges"].append((P[pairs.ravel()].tolist(), col))
        out["edges_uv"].append(([], col))
    if ob.stitch_gen.show_corners:
        idx = core.read_corner_verts(me)
        out["dots"] = P[idx[on_path[idx]]].tolist()
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
                 for pts, col in m[key] if len(pts)]
        else:
            shader = _point_shader()
            b = [batch_for_shader(shader, 'POINTS', {"pos": m[key]})] if len(m[key]) else []
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
        m = _marks(ob, uv=True)
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
