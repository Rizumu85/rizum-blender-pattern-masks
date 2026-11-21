# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Rizum
"""Rizum Pattern Masks: stitches, line art and grids that follow the mesh from
marked edges, baked to UV masks."""

import bpy
import bpy.utils.previews
from bpy.props import BoolProperty, FloatProperty, PointerProperty, StringProperty

from . import (
    core, i18n, load, ops_bake, ops_edges, ops_layers, overlay, presets, preview, props,
    rebuild, ui,
)
from .rebuild import regenerate  # noqa: F401  (what other code calls on the package)

classes = (
    props.StitchGenLine,
    props.StitchGenSettings,
    ops_edges.STITCHGEN_OT_path_add,
    ops_edges.STITCHGEN_OT_path_remove,
    ops_edges.STITCHGEN_OT_path_select,
    ops_edges.STITCHGEN_OT_path_clear,
    ops_edges.STITCHGEN_OT_corner_detect,
    ops_edges.STITCHGEN_OT_corner_select,
    ops_edges.STITCHGEN_OT_corner_mark,
    ops_edges.STITCHGEN_OT_corner_clear,
    ops_layers.STITCHGEN_OT_update,
    ops_layers.STITCHGEN_OT_unroll,
    ops_layers.STITCHGEN_OT_line_add,
    ops_layers.STITCHGEN_OT_grid_add,
    ops_layers.STITCHGEN_OT_stitch_add,
    ops_layers.STITCHGEN_MT_add_layer,
    ops_layers.STITCHGEN_OT_line_remove,
    ops_layers.STITCHGEN_OT_layer_move,
    ops_layers.STITCHGEN_OT_clear_scene,
    ops_layers.STITCHGEN_MT_list_extras,
    ops_layers.STITCHGEN_OT_set_uv_map,
    ui.STITCHGEN_OT_edit_color,
    ops_layers.STITCHGEN_OT_pick_folder,
    ops_layers.STITCHGEN_OT_open_folder,
    presets.STITCHGEN_OT_reset_defaults,
    presets.STITCHGEN_OT_apply_preset,
    presets.STITCHGEN_OT_preset_default,
    presets.STITCHGEN_OT_stitch_preset_add,
    presets.STITCHGEN_OT_grid_preset_add,
    presets.STITCHGEN_MT_grid_presets,
    presets.STITCHGEN_PT_grid_presets,
    presets.STITCHGEN_OT_line_preset_add,
    presets.STITCHGEN_MT_stitch_presets,
    presets.STITCHGEN_MT_line_presets,
    presets.STITCHGEN_PT_stitch_presets,
    presets.STITCHGEN_PT_line_presets,
    ops_layers.STITCHGEN_MT_uv_maps,
    ops_layers.STITCHGEN_OT_set_reference,
    ops_layers.STITCHGEN_MT_reference,
    ops_layers.STITCHGEN_OT_pick_reference,
    ops_layers.STITCHGEN_OT_reference_menu,
    ui.STITCHGEN_UL_lines,
    ops_bake.STITCHGEN_OT_bake,
    ui.VIEW3D_PT_stitch_gen,
)


def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Object.stitch_gen = PointerProperty(type=props.StitchGenSettings)
    wm = bpy.types.WindowManager
    wm.stitch_gen_baking = BoolProperty(default=False)
    bpy.types.Scene.stitch_gen_last_size = StringProperty(default="", options={'HIDDEN'})
    bpy.types.Scene.stitch_gen_marks = BoolProperty(
        name="Show Marks", default=True, update=props._on_all_marks,
        description="Show the marked edges and corners of all layers in the viewport "
                    "(display only)")
    wm.stitch_gen_bake_progress = FloatProperty(default=0.0, min=0.0, max=1.0)
    wm.stitch_gen_bake_label = StringProperty(default="")
    i18n.register(__package__)
    overlay.register()
    preview.register(rebuild._preview_key, rebuild._request, rebuild._shown_layers)
    ui._icons["coll"] = bpy.utils.previews.new()
    bpy.app.handlers.load_post.append(load._on_load)
    # enabled with a file already open: bring its objects up to date (data
    # can't be written while registering)
    bpy.app.timers.register(load._migrate_open_file, first_interval=0.0)


def unregister():
    if bpy.app.timers.is_registered(load._migrate_open_file):
        bpy.app.timers.unregister(load._migrate_open_file)
    if load._on_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(load._on_load)
    if bpy.app.timers.is_registered(rebuild._flush):
        bpy.app.timers.unregister(rebuild._flush)
    rebuild._pending.clear()
    del bpy.types.Object.stitch_gen
    for name in ("stitch_gen_last_size", "stitch_gen_marks"):
        if hasattr(bpy.types.Scene, name):
            delattr(bpy.types.Scene, name)
    for name in ("stitch_gen_baking", "stitch_gen_bake_progress", "stitch_gen_bake_label"):
        if hasattr(bpy.types.WindowManager, name):
            delattr(bpy.types.WindowManager, name)
    i18n.unregister(__package__)
    overlay.unregister()
    preview.unregister()
    if ui._icons["coll"] is not None:
        bpy.utils.previews.remove(ui._icons["coll"])
        ui._icons["coll"] = None
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
    core.drop_cache()
