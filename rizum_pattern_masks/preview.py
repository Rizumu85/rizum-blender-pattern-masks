# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Rizum
"""Viewport previews: the stitches, line art and grids each object would
bake, drawn over the 3D view. Nothing is added to the scene.

regenerate() hands each object's geometry over with put(). The add-on's own
changes rebuild a preview themselves. What nothing tells the add-on about (an
undo brings settings and marks back silently) is found by comparing: while a
view is being drawn, at most every CHECK_EVERY seconds per object, its
preview's key is compared with the object's, and when they differ one rebuild
is asked for through the ``rebuild`` hook; the old preview shows until then.
Between those looks a draw only draws. Moving or turning an object moves its
preview with it; only a change of scale needs a rebuild (the sizes are real
millimetres).

Drawing only; nothing is stored in the file."""

import time

import bpy
import gpu
import numpy as np
from gpu_extras.batch import batch_for_shader

from . import core

CHECK_EVERY = 0.25       # seconds between looks at whether a preview is out of date

_store = {}              # object name -> preview entry (see put())
_hooks = {"key": None, "rebuild": None, "layers": None}
_handles = []
_shaders = {}

# -- which objects use the add-on ----------------------------------------------
# A set kept up to date cheaply instead of looking at every object on every
# redraw: rescanned when the number of objects changes or a name goes missing,
# and noted by the operators that add layers.
_known = {}             # view layer -> (its number of objects, names)


def uses(ob):
    return ob.type == 'MESH' and (len(ob.stitch_gen.lines) > 0
                                  or core.PATH_ATTR in ob.data.attributes
                                  or bool(core.line_attr_names(ob.data)))


def note(ob):
    for _count, names in _known.values():
        names.add(ob.name_full)


def rescan():
    _known.clear()


def objects(context):
    """The objects in this view layer that use the add-on."""
    vl = context.view_layer
    objs = vl.objects
    hit = _known.get(vl.as_pointer())
    if hit is None or hit[0] != len(objs) or any(n not in objs for n in hit[1]):
        hit = _known[vl.as_pointer()] = (len(objs), {o.name_full for o in objs if uses(o)})
        for name in [n for n in _store if n not in bpy.data.objects]:
            del _store[name]                # their objects are gone
    return [objs[n] for n in hit[1] if n in objs]


# -- geometry ----------------------------------------------------------------------

def put(ob, key, stitches, lines, grids):
    """The preview of ``ob``, built for ``key`` with the object where it is
    now. stitches: [(layer attribute, RibbonData)]; lines: [(attribute, co,
    tris)]; grids: [(attribute, cell size, corner positions (n, 3), fabric
    coordinates per corner (n, 2))], triangles three corners each."""
    _store[ob.name_full] = {"key": key, "mw_inv": ob.matrix_world.inverted_safe(),
                            "stitches": stitches, "lines": lines, "grids": grids,
                            "batches": None, "checked": time.monotonic()}
    note(ob)
    redraw()


def has(ob):
    return ob.name_full in _store


def forget(ob=None):
    if ob is None:
        _store.clear()
    else:
        _store.pop(ob.name_full, None)
    redraw()


def geometry(ob):
    """What the preview of ``ob`` shows (for scripts and tests), or None:
    {"stitches": [(attr, RibbonData)], "lines": [(attr, co, tris)],
    "grids": [(attr, cell, co, vs)]}."""
    e = _store.get(ob.name_full)
    if e is None:
        return None
    return {k: e[k] for k in ("stitches", "lines", "grids")}


def redraw():
    wm = getattr(bpy.context, "window_manager", None)
    for win in (wm.windows if wm else ()):
        for area in win.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()


# -- drawing -----------------------------------------------------------------------

_STITCH_FRAG = """
void main()
{
  /* the stitch: a rounded rectangle, half length dims.x, half width dims.y,
     corner radius dims.z, around its centre (the same as the bake shader) */
  vec2 q = abs(v_uv) - (v_dims.xy - vec2(v_dims.z));
  float sd = length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - v_dims.z;
  float cov = clamp(0.5 - sd / max(fwidth(sd), 1e-9), 0.0, 1.0);
  if (cov <= 0.0) {
    discard;
  }
  FragColor = vec4(color.rgb, color.a * cov);
}
"""
_GRID_FRAG = """
void main()
{
  vec2 f = floor(v_vs / cell);
  if (mod(f.x + f.y + 2000000.0, 2.0) >= 0.5) {
    discard;                      /* the white squares stay clear */
  }
  FragColor = color;
}
"""


def _shader(kind):
    sh = _shaders.get(kind)
    if sh is not None:
        return sh
    info = gpu.types.GPUShaderCreateInfo()
    info.push_constant('MAT4', "mvp")
    info.push_constant('VEC4', "color")
    info.vertex_in(0, 'VEC3', "pos")
    out = gpu.types.GPUStageInterfaceInfo("rizum_pm_" + kind)
    if kind == "stitch":
        info.vertex_in(1, 'VEC2', "uv")
        info.vertex_in(2, 'VEC3', "dims")
        out.smooth('VEC2', "v_uv")
        out.smooth('VEC3', "v_dims")
        vert = "v_uv = uv; v_dims = dims;"
        frag = _STITCH_FRAG
    elif kind == "grid":
        info.push_constant('FLOAT', "cell")
        info.vertex_in(1, 'VEC2', "vs")
        out.smooth('VEC2', "v_vs")
        vert = "v_vs = vs;"
        frag = _GRID_FRAG
    else:
        vert = ""
        frag = "void main() { FragColor = color; }"
    if kind != "flat":
        info.vertex_out(out)
    info.fragment_out(0, 'VEC4', "FragColor")
    info.vertex_source("void main() { " + vert + " gl_Position = mvp * vec4(pos, 1.0); }")
    info.fragment_source(frag)
    sh = _shaders[kind] = gpu.shader.create_from_info(info)
    return sh


def _f32(a):
    return np.ascontiguousarray(a, np.float32)


def _batches(e):
    """GPU batches of an entry, made on its first draw."""
    if e["batches"] is not None:
        return e["batches"]
    out = []
    for attr, r in e["stitches"]:
        if len(r.quads):
            q = r.quads
            tris = np.ascontiguousarray(np.vstack([q[:, [0, 1, 2]], q[:, [0, 2, 3]]]), np.int32)
            out.append(("stitch", attr, None, batch_for_shader(
                _shader("stitch"), 'TRIS',
                {"pos": _f32(r.co), "uv": _f32(r.uv), "dims": _f32(r.dims)},
                indices=tris)))
    for attr, co, tris in e["lines"]:
        if len(tris):
            out.append(("flat", attr, None, batch_for_shader(
                _shader("flat"), 'TRIS', {"pos": _f32(co)},
                indices=np.ascontiguousarray(tris, np.int32))))
    for attr, cell, co, vs in e["grids"]:
        if len(co):
            out.append(("grid", attr, cell, batch_for_shader(
                _shader("grid"), 'TRIS', {"pos": _f32(co), "vs": _f32(vs)})))
    e["batches"] = out
    return out


def _check(ob, e, now):
    """Ask for a rebuild when the preview ``e`` of ``ob`` is missing or out of
    date; an existing one is compared at most every CHECK_EVERY seconds."""
    if e is None:
        _hooks["rebuild"](ob)
    elif now - e["checked"] >= CHECK_EVERY:
        e["checked"] = now
        if e["key"] != _hooks["key"](ob):
            _hooks["rebuild"](ob)       # one rebuild, a moment later


def _draw():
    context = bpy.context
    obs = objects(context)
    if not obs:
        return
    space, rv3d = context.space_data, context.region_data
    drawn = False
    now = time.monotonic()
    for ob in obs:
        if not ob.visible_get(viewport=space):
            continue
        e = _store.get(ob.name_full)
        _check(ob, e, now)
        if e is None:
            continue
        shown = _hooks["layers"](ob)        # [(attribute, color)], the list's order
        colors, rank = dict(shown), {a: i for i, (a, _c) in enumerate(shown)}
        mvp = rv3d.perspective_matrix @ ob.matrix_world @ e["mw_inv"]
        # the list's bottom layer first: the ones higher up are drawn over it
        # (the previews test the scene's depth, not each other's)
        for kind, attr, cell, batch in sorted(_batches(e), key=lambda b: -rank.get(b[1], -1)):
            col = colors.get(attr)
            if col is None:
                continue
            if not drawn:
                gpu.state.depth_test_set('LESS_EQUAL')
                gpu.state.depth_mask_set(False)
                gpu.state.blend_set('ALPHA')
                drawn = True
            sh = _shader(kind)
            sh.bind()
            sh.uniform_float("mvp", mvp)
            sh.uniform_float("color", col)     # scene linear: the viewport color-manages it
            if cell is not None:
                sh.uniform_float("cell", cell)
            batch.draw(sh)
    if drawn:
        gpu.state.depth_test_set('NONE')
        gpu.state.depth_mask_set(True)
        gpu.state.blend_set('NONE')


def register(key, rebuild, layers):
    """key(ob): what a preview is built from; rebuild(ob): ask for one;
    layers(ob): [(edge attribute, color)] of the shown layers, top of the
    list first."""
    _hooks.update(key=key, rebuild=rebuild, layers=layers)
    _handles.append(bpy.types.SpaceView3D.draw_handler_add(_draw, (), 'WINDOW', 'POST_VIEW'))


def unregister():
    for h in _handles:
        bpy.types.SpaceView3D.draw_handler_remove(h, 'WINDOW')
    _handles.clear()
    _store.clear()
    _known.clear()
    _shaders.clear()
