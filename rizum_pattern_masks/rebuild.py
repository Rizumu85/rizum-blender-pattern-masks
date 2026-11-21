# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Rizum
"""Rebuild layer geometry and schedule viewport preview updates."""

import hashlib
import time
import traceback

import numpy as np
import bpy

from . import core, grid, layers, overlay, preview
from .i18n import rpt
from .layers import _layer_attr, _line_items, _params, _stitch_items
from .migrate import _ensure_layers, _migrate_units


def _grid_parts(obj, scene):
    """[(attribute, cell size, corner positions, fabric coordinates per corner)]
    of the shown grid layers (preview.put). An Unrolled layer shows once it is
    worked out (the Unroll button; scripts work it out straight away)."""
    s = obj.stitch_gen
    p = _params(s, scene)
    entry = core._cache.get(obj.name_full)
    if not p["grids"] or entry is None:
        return []
    topo = entry["topo"]
    lift = max(topo.mean_edge / 60.0, topo.span * 2e-5)
    kept = entry.setdefault("grid_preview", {})     # per layer: (settings, coords, result)
    out = []
    for g in p["grids"]:
        attr, cell, angle, off_y, off_x, wobble, mode, attrs = g
        gc = core.grid_coords(entry, attrs)
        if mode == "unrolled" and not unrolled(gc) and not bpy.app.background:
            continue
        hit = kept.get(attr)
        if hit is None or hit[0] != (g, lift) or hit[1] is not gc:
            lay = gc.layout(cell, angle, mode)
            hit = kept[attr] = ((g, lift), gc, grid.preview(topo, lay, lift, off_x, off_y,
                                                            grid.Wobble(attr, cell, wobble)))
        co, tris, vs = hit[2]
        if len(tris):
            out.append((attr, cell, co[tris].reshape(-1, 3), vs.reshape(-1, 2)))
    return out


def unrolled(gc):
    """Is the Unrolled flattening of a grid's piece worked out?"""
    return getattr(gc, "_flat_log", None) is not None


def _params_sig(p):
    """Short fingerprint of the settings a preview was built from."""
    return hashlib.md5(repr(sorted(p.items())).encode()).hexdigest()[:16]


def regenerate(obj, scene=None):
    """Rebuild the stitches, line art and grids, and their viewport preview."""
    scene = scene or bpy.context.scene
    s = obj.stitch_gen
    _migrate_units(s)
    _ensure_layers(obj)           # older files: never build from settings not yet moved
    overlay.invalidate(obj)       # the marks may have changed, whatever the build does
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
    except Exception as e:
        if isinstance(e, ValueError):        # expected limits: show the message only
            tpl = getattr(e, "template", None)
            s.status = rpt(tpl).format(**e.kw) if tpl else str(e)
        else:                                # keep the UI alive, show the error in the panel
            traceback.print_exc()
            s.status = f"{type(e).__name__}: {e}"
        # nothing to show, for these settings: the drawing doesn't ask again
        preview.put(obj, _preview_key(obj, scene), [], [], [])
        return None
    finally:
        if src is not None:
            obj.to_mesh_clear()
    s.status = ""
    s.dash_count = data.dash_count
    for l, (_attr, r) in zip([l for l in _stitch_items(s) if l.enabled], data.stitches):
        l.dash_count = r.dash_count
    lines = []
    shown = [l for l in _line_items(s) if l.enabled]
    for li, l in enumerate(shown):
        q = data.line_quads[data.line_layer == li]
        if len(q):
            lines.append((_layer_attr(l), data.line_co,
                          np.vstack([q[:, [0, 1, 2]], q[:, [0, 2, 3]]])))
    preview.put(obj, _preview_key(obj, scene), list(data.stitches), lines, _grid_parts(obj, scene))
    return data


def _preview_key(ob, scene=None):
    """What a preview is built from: the settings, the mesh and its marks
    (undo reads them in again: their data moves), Edit Mode or not, and the
    object's scale (sizes are real)."""
    me = ob.data
    sc = ob.matrix_world.to_scale()
    attrs = me.attributes
    marks = tuple(attrs[n].as_pointer() for n in
                  (core.PATH_ATTR, core.CORNER_ATTR, *core.line_attr_names(me)) if n in attrs)
    return (_params_sig(_params(ob.stitch_gen, scene or bpy.context.scene)), me.as_pointer(),
            marks, me.is_editmode, tuple(round(x, 6) for x in sc))


def _shown_layers(ob):
    """[(edge attribute, color)] of the shown layers, in the list's order
    (the preview draws the ones higher up over those below)."""
    return [(_layer_attr(l), tuple(l.color)) for l in ob.stitch_gen.lines if l.enabled]


def _layer_colors(ob):
    """{edge attribute: color} of the shown layers."""
    return dict(_shown_layers(ob))


def _request(ob):
    """A drawn preview is out of date (after undo, in or out of Edit Mode) or
    not built yet (a file just opened): rebuild it once, a moment later. Out
    of date and not live: it waits for Update."""
    if ob.stitch_gen.live or not preview.has(ob):
        _schedule(ob, bpy.context.scene, restart=False)


_DEBOUNCE = 0.15         # seconds without changes before rebuilding
_pending = {}            # object name -> (time of its last change, scene name)


def _on_change(self, context):
    obj = self.id_data
    if layers._MUTE or not (isinstance(obj, bpy.types.Object) and obj.stitch_gen.live):
        return
    if bpy.app.background:
        regenerate(obj, context.scene)
        return
    # Rebuilding the line can take a moment on a big mesh: wait until the
    # value stops changing (a slider drag) and rebuild once.
    _schedule(obj, context.scene)


def _schedule(obj, scene, restart=True):
    """Rebuild a moment after the last change; restart=False leaves a rebuild
    already waiting where it is (the preview asks on every redraw)."""
    if not restart and obj.name_full in _pending:
        return
    _pending[obj.name_full] = (time.monotonic(), scene.name if scene else "")
    if not bpy.app.timers.is_registered(_flush):
        bpy.app.timers.register(_flush, first_interval=_DEBOUNCE)


_BETWEEN = 0.02          # seconds Blender gets between two objects' rebuilds


def _first(names):
    """Of the objects waiting, the one to rebuild now: the active object,
    else a selected one, else the one that has waited longest."""
    objs = bpy.context.view_layer.objects
    active = objs.active.name_full if objs.active is not None else None
    if active in names:
        return active
    selected = {o.name_full for o in objs.selected}
    return next((n for n in names if n in selected), names[0])


def _flush():
    """One object per call: with many waiting (a file just opened), Blender
    stays usable between them and the previews appear one by one."""
    now = time.monotonic()
    due = [name for name, (t, _scene) in _pending.items() if t + _DEBOUNCE <= now]
    if due:
        name = _first(due)
        _t, scene_name = _pending.pop(name)
        ob = bpy.data.objects.get(name)
        if ob is not None and ob.type == 'MESH' and (ob.stitch_gen.live or not preview.has(ob)):
            regenerate(ob, bpy.data.scenes.get(scene_name))
    if not _pending:
        return None
    if len(due) > 1:
        return _BETWEEN
    return max(_BETWEEN, min(t for t, _scene in _pending.values()) + _DEBOUNCE - time.monotonic())
