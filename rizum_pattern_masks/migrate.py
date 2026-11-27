# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Rizum
"""Upgrade layer data and settings saved by earlier versions."""

import bpy

from . import core, layers, overlay, preview
from .layers import (
    STITCH_COLOR, _default_name, _is_grid, _line_items, _new_stitch_layer, _stitch_from_stored,
    _stitch_items, _uses_addon,
)


def _ensure_layers(ob):
    """Bring objects set up by older versions up to date, once: before 0.3.0
    objects that used stitches get the stitch row and line layers their own
    color; before 0.4.0 the stitch settings move onto the stitch row. Objects
    that never used the add-on are left alone (the list starts empty)."""
    s = ob.stitch_gen
    if s.ui_version >= UI_VERSION:
        return
    if not _uses_addon(ob):
        return
    if s.ui_version >= 1:
        _migrate_references(ob)
        _migrate_stitch_layers(ob)
        _migrate_flip(ob)
        return
    _migrate_line_layers(ob)      # also when the file was open before the add-on
    _migrate_units(s)             # before the stitch row takes the stored values
    layers._MUTE = True
    try:
        if s.ui_version < 1:
            for l in _line_items(s):
                l.color = s.line_color
                if not l.is_property_set("width"):
                    l.width = 1.0          # the default width before 0.3.0
        used_stitches = s.ribbon is not None or core.PATH_ATTR in ob.data.attributes
        if used_stitches and not _stitch_items(s):
            sel = s.line_index if len(s.lines) else -1
            _new_stitch_layer(ob)
            s.lines.move(len(s.lines) - 1, 0)          # the stitch row came first
            s.line_index = sel + 1 if sel >= 0 else 0
        s.ui_version = 1
    finally:
        layers._MUTE = False
    _migrate_references(ob)
    _migrate_stitch_layers(ob)
    _migrate_flip(ob)


# 1: the layer list (0.3.0); 2: references; 3: stitch layers (0.4.0); 4: a side
# per layer (0.5.2)
UI_VERSION = 4


def _migrate_flip(ob):
    """Before 0.5.2 one Flip Side served all layers: each layer takes it."""
    s = ob.stitch_gen
    if s.ui_version >= 4:
        return
    layers._MUTE = True
    try:
        if s.flip:
            for l in s.lines:
                l.flip = not _is_grid(l)        # grids have no side
        s.ui_version = 4
    finally:
        layers._MUTE = False


def _migrate_stitch_layers(ob):
    """Before 0.4.0 an object had one stitch row whose settings were the
    object's own: they move onto the row, a stitch layer like any other."""
    s = ob.stitch_gen
    if s.ui_version >= 3:
        return
    _migrate_units(s)              # what is stored is millimetres from here on
    layers._MUTE = True
    try:
        for l in s.lines:
            if l.kind != 'STITCH' and l.edge_attr == core.PATH_ATTR:
                l.kind = 'STITCH'
                l.color = STITCH_COLOR
                if l.name in ("Stitches", "line"):
                    _default_name(s, l, "stitch")
                _stitch_from_stored(s, l)
        s.ui_version = 3
    finally:
        layers._MUTE = False


def _migrate_references(ob):
    """Before references, a line art layer followed the stitch edges when its
    Include Stitch Edges was on (the default): it now refers to the stitches."""
    s = ob.stitch_gen
    if s.ui_version >= 2:
        return
    layers._MUTE = True
    try:
        if _stitch_items(s):
            for l in _line_items(s):
                if l.include_stitch and not l.ref_attr:
                    l.ref_attr = core.PATH_ATTR
        s.ui_version = 2
    finally:
        layers._MUTE = False


def _defer_ensure(ob):
    """Panels can't write data: add the stitch row right after drawing."""
    name = ob.name_full

    def run():
        o = bpy.data.objects.get(name)
        if o is not None and o.type == 'MESH':
            _ensure_layers(o)
            overlay.invalidate(o)
            preview.redraw()
        return None
    bpy.app.timers.register(run, first_interval=0.0)


def _migrate_line_layers(ob):
    """Layers from before each layer had its own edges all used one shared
    set: the first keeps it, the others start their own."""
    s = ob.stitch_gen
    legacy = [l for l in _line_items(s) if not l.edge_attr]
    if len(legacy) < 2:
        return
    layers._MUTE = True
    try:
        used = set(ob.data.attributes.keys()) | {l.edge_attr for l in s.lines}
        n = 1
        for l in legacy[1:]:
            while f"{core.LINE_ATTR}_{n}" in used:
                n += 1
            l.edge_attr = f"{core.LINE_ATTR}_{n}"
            used.add(l.edge_attr)
    finally:
        layers._MUTE = False


# Lengths were stored in metres before 0.1.0 switched the UI to millimetres.
_MM_PROPS = ("inset", "smooth", "length", "gap", "width", "offset")


def _migrate_units(s):
    """Convert settings saved in metres to millimetres, once per object."""
    if s.units_version >= 1:
        return
    if s.ribbon is None:          # new object: values are already millimetres
        _MUTE_SET(s)
        return
    layers._MUTE = True
    try:
        # Only values that were actually saved can be old; unsaved ones are
        # already the new millimetre defaults. A saved length under 0.05 is a
        # metre value (0.05 mm stitches make no sense).
        for name in _MM_PROPS:
            v = s.get(name)
            if v is not None and 0 < abs(v) < 0.05:
                s[name] = v * 1000.0
        s.units_version = 1
    finally:
        layers._MUTE = False


def _MUTE_SET(s):
    layers._MUTE = True
    try:
        s.units_version = 1
    finally:
        layers._MUTE = False
