"""Viewport overlay, in the 3D view and in the UV editor:

* the marked edges of each layer whose marks are shown: the stitch edges
  purple, line art edges green, the layer selected in the list brightest,
* for the selected layer, the edges it takes out of what it gets from the
  layer it refers to, red,
* the vertices marked as corners as yellow dots.

Drawing only; nothing is stored in the file or baked."""

import bpy
import bmesh
import numpy as np
import gpu
from gpu_extras.batch import batch_for_shader

from . import core

YELLOW = (1.0, 0.8, 0.1, 1.0)
OUTLINE = (0.08, 0.06, 0.02, 0.9)
PURPLE = (0.72, 0.25, 1.0, 0.45)     # quiet, so Blender's own selection stays visible
GREEN = (0.3, 1.0, 0.35, 0.55)    # not cyan: Blender draws sharp edges in cyan
RED = (1.0, 0.25, 0.2, 0.75)      # edges the selected layer takes out
DIM = 0.18                        # alpha of the layers not selected in the list
LIFT = 0.0004            # metres off the surface, so the marks are not hidden by it

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
        base = PURPLE if attr == core.PATH_ATTR else GREEN
        active = i == sel
        out.append((active, attr, base if active else base[:3] + (DIM,), 1))
        if active and l.ref_attr:
            out.append((active, attr, RED, -1))
    out.sort(key=lambda t: t[0])
    return [(attr, col, sign) for _, attr, col, sign in out]


def _marks(ob):
    """Shown layers' edges and the marked corners, in world space (lifted
    along the normal) and in UV space."""
    hit = _cache.get(ob.name_full)
    if hit is not None:
        return hit
    me = ob.data
    mw = ob.matrix_world
    nmat = mw.to_3x3().inverted_safe().transposed()
    s = ob.stitch_gen
    uv_name = s.uv_map
    shown = _shown(ob)
    out = {"dots": [], "dots_uv": [], "edges": [], "edges_uv": []}

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
        uvl = core.pick_uv(me, uv_name)
        verts = me.vertices
        keys = {}
        for k, (name, col, sign) in enumerate(shown):
            pairs = core.read_path_edges(me, name, sign)
            pts = []
            for a, b in pairs.tolist():
                pts += [lifted(verts[a].co, verts[a].normal),
                        lifted(verts[b].co, verts[b].normal)]
                if sign > 0:
                    on_path.update((a, b))
                keys.setdefault((min(a, b), max(a, b)), []).append(k)
            out["edges"].append((pts, col))
            out["edges_uv"].append(([], col))
        idx = []
        if s.show_corners:
            idx = [i for i in core.read_corner_verts(me).tolist() if i in on_path]
            out["dots"] += [lifted(verts[i].co, verts[i].normal) for i in idx]
        if uvl is not None and (keys or idx):
            wanted = set(idx)
            for poly in me.polygons:
                li = list(poly.loop_indices)
                for la, lb in zip(li, li[1:] + li[:1]):
                    va, vb = me.loops[la].vertex_index, me.loops[lb].vertex_index
                    for k in keys.get((min(va, vb), max(va, vb)), ()):
                        out["edges_uv"][k][0].extend((tuple(uvl.data[la].uv) + (0.0,),
                                                      tuple(uvl.data[lb].uv) + (0.0,)))
                    if va in wanted:
                        out["dots_uv"].append(tuple(uvl.data[la].uv) + (0.0,))
    _cache[ob.name_full] = out
    return out


def _objects(context):
    out = []
    for ob in context.view_layer.objects:
        if ob.type == 'MESH' and ob.visible_get() and (
                core.PATH_ATTR in ob.data.attributes or core.line_attr_names(ob.data)):
            out.append(ob)
    return out


def _lines(coords, width, color=PURPLE):
    if not coords:
        return
    shader = gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
    region = bpy.context.region
    shader.uniform_float("viewportSize", (region.width, region.height))
    shader.uniform_float("lineWidth", width)
    shader.uniform_float("color", color)
    batch_for_shader(shader, 'LINES', {"pos": coords}).draw(shader)


def _dots(coords, size):
    if not coords:
        return
    shader = gpu.shader.from_builtin('POINT_UNIFORM_COLOR')
    batch = batch_for_shader(shader, 'POINTS', {"pos": coords})
    gpu.state.point_size_set(size + 4)
    shader.uniform_float("color", OUTLINE)
    batch.draw(shader)
    gpu.state.point_size_set(size)
    shader.uniform_float("color", YELLOW)
    batch.draw(shader)


def _draw_3d():
    obs = _objects(bpy.context)
    if not obs:
        return
    gpu.state.depth_test_set('LESS_EQUAL')
    gpu.state.blend_set('ALPHA')
    for ob in obs:
        m = _marks(ob)
        for pts, col in m["edges"]:
            _lines(pts, 2.0, col)
        _dots(m["dots"], 6.0)
    gpu.state.depth_test_set('NONE')
    gpu.state.blend_set('NONE')
    gpu.state.point_size_set(1.0)


def _draw_uv():
    context = bpy.context
    space = context.space_data
    if space is None or getattr(space, "mode", "") != 'UV':
        return
    obs = [ob for ob in _objects(context) if ob.mode == 'EDIT']
    if not obs:
        return
    gpu.state.blend_set('ALPHA')
    for ob in obs:
        m = _marks(ob)
        for pts, col in m["edges_uv"]:
            _lines(pts, 2.0, col)
        _dots(m["dots_uv"], 6.0)
    gpu.state.blend_set('NONE')
    gpu.state.point_size_set(1.0)


@bpy.app.handlers.persistent
def _on_depsgraph(scene, depsgraph):
    for upd in depsgraph.updates:
        idb = upd.id
        if isinstance(idb, bpy.types.Object):
            _cache.pop(idb.original.name_full, None)
        elif isinstance(idb, bpy.types.Mesh):
            for ob in list(_cache):
                o = bpy.data.objects.get(ob)
                if o is None or o.data == idb.original:
                    _cache.pop(ob, None)


@bpy.app.handlers.persistent
def _on_load(_dummy):
    _cache.clear()


def register():
    _handles.append((bpy.types.SpaceView3D, bpy.types.SpaceView3D.draw_handler_add(
        _draw_3d, (), 'WINDOW', 'POST_VIEW')))
    _handles.append((bpy.types.SpaceImageEditor, bpy.types.SpaceImageEditor.draw_handler_add(
        _draw_uv, (), 'WINDOW', 'POST_VIEW')))
    bpy.app.handlers.depsgraph_update_post.append(_on_depsgraph)
    bpy.app.handlers.load_post.append(_on_load)


def unregister():
    for space, h in _handles:
        space.draw_handler_remove(h, 'WINDOW')
    _handles.clear()
    for lst, fn in ((bpy.app.handlers.depsgraph_update_post, _on_depsgraph),
                    (bpy.app.handlers.load_post, _on_load)):
        if fn in lst:
            lst.remove(fn)
    _cache.clear()
