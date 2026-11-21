# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Rizum
"""Layer settings, edge references and layer creation."""

import bpy

from . import core, preview

_MUTE = False
_baking = {"name": None}  # object being baked: the bake makes a temporary copy active


def _source_object(context):
    if _baking["name"]:
        ob = bpy.data.objects.get(_baking["name"])
        if ob is not None:
            return ob
    ob = context.active_object
    return ob if ob is not None and ob.type == 'MESH' else None


def _params(s, scene):
    # UI values are millimetres; geometry works in scene units.
    k = 0.001 / (scene.unit_settings.scale_length or 1.0)
    return {
        "flip": s.flip,
        "offset": 0.0,                     # sliding the stitches was dropped in 0.3.0
        "resolution": int(s.resolution),
        "corner": 0.0,
        "uv_name": s.uv_map,
        "stitch_layers": tuple(
            (_layer_attr(l), _edge_spec(s, l), l.inset * k, l.stitch_smooth * k,
             l.corner_inset * k, l.length * k, l.gap * k, l.thread_width * k, l.roundness,
             l.even, l.zigzag_height * k if l.style == 'ZIGZAG' else 0.0)
            for l in _stitch_items(s) if l.enabled),
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
    # the stitch row of files from before 0.4.0 is told by its edges until
    # it is migrated
    return layer.kind == 'STITCH' or layer.edge_attr == core.PATH_ATTR


def _is_grid(layer):
    return layer.kind == 'GRID' and not _is_stitch(layer)


def _line_items(s):
    """The line art layers."""
    return [l for l in s.lines if not _is_stitch(l) and l.kind != 'GRID']


def _grid_items(s):
    """The grid (gingham) layers."""
    return [l for l in s.lines if _is_grid(l)]


def _stitch_items(s):
    """The stitch layers."""
    return [l for l in s.lines if _is_stitch(l)]


def _stitch_item(s):
    """The stitch layer the object's stitch settings stand for (scripts,
    presets): the one selected in the list, else the first."""
    if 0 <= s.line_index < len(s.lines) and _is_stitch(s.lines[s.line_index]):
        return s.lines[s.line_index]
    return next((l for l in s.lines if _is_stitch(l)), None)


def _stitches_on(s):
    """Stitches are made when a stitch layer's eye is on."""
    return any(l.enabled for l in _stitch_items(s))


def _uses_addon(ob):
    return preview.uses(ob)


STITCH_COLOR = (1.0, 0.35, 0.05, 1.0)

# Before 0.4.0 the stitch settings were the object's own; they are now each
# stitch layer's. The object's names stay for presets and scripts and stand
# for the stitch layer selected in the list (else the first); a value stored
# under them in an older file (or set before there was a stitch layer) goes
# to the object's first stitch layer.
_STITCH_MAP = {"inset": "inset", "smooth": "stitch_smooth", "corner_inset": "corner_inset",
               "style": "style", "zigzag_height": "zigzag_height", "length": "length",
               "gap": "gap", "width": "thread_width", "roundness": "roundness",
               "even": "even", "stitches": "enabled", "stitch_color": "color"}
_STYLES = ('DASH', 'ZIGZAG')


def _stitch_from_stored(s, item):
    """Give a stitch layer the stitch settings stored on the object."""
    for name, iname in _STITCH_MAP.items():
        v = s.get(name)
        if v is None:
            continue
        if name == "style":
            v = _STYLES[int(v)]
        elif name in ("even", "stitches"):
            v = bool(v)
        elif name == "stitch_color":
            v = tuple(v)
        setattr(item, iname, v)


def _new_stitch_layer(ob):
    """Add a stitch layer, selected. The object's first one takes the stitch
    edges (if no layer has them) and the stitch settings the object may
    already have; the others start their own, still empty, set of edges."""
    s = ob.stitch_gen
    first = not _stitch_items(s)
    attrs = {l.edge_attr for l in s.lines}
    item = s.lines.add()
    item.kind = 'STITCH'
    item.color = STITCH_COLOR
    if core.PATH_ATTR not in attrs:
        item.edge_attr = core.PATH_ATTR
    else:
        used = set(ob.data.attributes.keys()) | attrs
        n = 1
        while f"{core.LINE_ATTR}_{n}" in used:
            n += 1
        item.edge_attr = f"{core.LINE_ATTR}_{n}"
    if first:
        _stitch_from_stored(s, item)
    _default_name(s, item, "stitch")
    s.line_index = len(s.lines) - 1
    return item


def _default_name(s, item, stem):
    """stem, stem2, ...: a default name no other layer has (it names the
    mask file)."""
    names = {l.name for l in s.lines if l != item}
    k = 1
    item.name = stem
    while item.name in names:
        k += 1
        item.name = f"{stem}{k}"


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


def _grid_layers(s, scene):
    """[(name, edge attribute, cell, angle, from edge, along edge, wobble, layout,
    edge sets followed)] of the shown grid layers, in scene units."""
    k = 0.001 / (scene.unit_settings.scale_length or 1.0)
    return [(l.name, _layer_attr(l), l.grid_cell * k, l.grid_angle, l.grid_from * k,
             l.grid_along * k, l.grid_wobble, l.grid_layout.lower(), _edge_spec(s, l))
            for l in _grid_items(s)
            if l.enabled and l.grid_cell > 0]


STITCH_ICON = 'MOD_DASH'
LINE_ICON = 'IPO_LINEAR'
GRID_ICON = 'MESH_GRID'


def _layer_icon(layer):
    return STITCH_ICON if _is_stitch(layer) else GRID_ICON if _is_grid(layer) else LINE_ICON
