# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Rizum
"""File-load handlers and cleanup of old preview data."""

import re

import bpy

from . import core, layers, overlay, preview, rebuild
from .layers import _grid_items, _is_stitch, _line_items
from .migrate import _ensure_layers, _migrate_line_layers, _migrate_units
from .ops_bake import MATERIAL


OLD_COLLECTION = "Stitch Preview"        # held the preview objects before 0.5.0
OLD_PREVIEW_TAG = "stitch_gen_preview"


def _drop_old_previews():
    """Before 0.5.0 the previews were objects of their own (with their own
    materials): remove them; the previews are drawn now."""
    olds = {o.name_full for o in bpy.data.objects if o.get(OLD_PREVIEW_TAG)}
    mats = set()
    for ob in [o for o in bpy.data.objects if o.type == 'MESH']:
        s = ob.stitch_gen
        for prop in ("ribbon", "line_preview", "grid_preview"):
            o = getattr(s, prop)
            if o is not None:
                olds.add(o.name_full)
                setattr(s, prop, None)
        for l in s.lines:
            if l.material is not None:
                mats.add(l.material.name_full)
                l.material = None
    meshes = set()
    for name in olds:
        o = bpy.data.objects.get(name)
        if o is not None and o.library is None:
            if o.type == 'MESH':
                meshes.add(o.data.name_full)
                mats.update(m.name_full for m in o.data.materials if m is not None)
            bpy.data.objects.remove(o)
    col = bpy.data.collections.get(OLD_COLLECTION)
    if col is not None and col.library is None and not col.all_objects and not col.children:
        bpy.data.collections.remove(col)
    # only the previews' own data, once nothing else uses it
    for coll, names in ((bpy.data.meshes, meshes), (bpy.data.materials, mats)):
        for name in names:
            d = coll.get(name)
            if d is not None and d.users == 0 and d.library is None and name != MATERIAL:
                coll.remove(d)


@bpy.app.handlers.persistent
def _on_load(_dummy):
    layers._baking["name"] = None
    preview.forget()
    preview.rescan()
    overlay.invalidate()
    for ob in bpy.data.objects:
        if ob.type == 'MESH' and len(ob.stitch_gen.lines) > 1:
            _migrate_line_layers(ob)
        if ob.type == 'MESH':
            st = ob.stitch_gen
            row = next((i for i, l in enumerate(st.lines) if _is_stitch(l)), None)
            if (row is not None and st.ui_version < 3 and st.ribbon is None
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
    rebuild._pending.clear()
    for ob in bpy.data.objects:
        if ob.type == 'MESH' and ob.stitch_gen.ribbon is not None:
            _migrate_units(ob.stitch_gen)
    _drop_old_previews()          # last: the steps above tell old files by them


def _migrate_open_file():
    """Enabled with a file already open: what loading a file does."""
    _on_load(None)
    return None
