# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Rizum
"""Blender properties for objects and layers, and their update callbacks."""

import math
import re

import bpy
from bpy.props import (
    BoolProperty, CollectionProperty, EnumProperty, FloatProperty, IntProperty, PointerProperty,
    StringProperty,
)

from . import i18n, layers, overlay, preview
from .layers import STITCH_COLOR, _STITCH_MAP, _STYLES, _layer_attr, _layer_by_attr, _stitch_item
from .rebuild import _on_change


_PICK = {}               # while the eyedropper is on: object name, edges of the layer


def _on_color(self, context):
    preview.redraw()


def _on_size(self, context):
    """Remember the size picked last, for the next new object."""
    if not layers._MUTE and context.scene is not None:
        context.scene.stitch_gen_last_size = self.resolution
    _on_change(self, context)


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


_DEFAULT_NAME = re.compile(r"(line|grid|stitch)(\d*)")


def _display_name(layer):
    """A default name ("line", "line2", "stitch", ...) in the interface
    language; a name the user typed as it is. Files use ``name``."""
    m = _DEFAULT_NAME.fullmatch(layer.name)
    if m is None:
        return layer.name
    base = bpy.app.translations.pgettext_iface(
        {"line": "Line", "grid": "Grid", "stitch": "Stitches"}[m.group(1)], i18n.CTX)
    return f"{base} {m.group(2)}" if m.group(2) else base


def _set_display_name(layer, value):
    value = value.strip()
    if value and value != _display_name(layer):
        layer.name = value


class StitchGenLine(bpy.types.PropertyGroup):
    """A row of the layer list: a stitch, line art or grid layer."""
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
    flip: BoolProperty(name="Flip Side", default=False, update=_on_change,
                       description="Put this layer's line on the other side of its edges")
    color: bpy.props.FloatVectorProperty(
        name="Color", subtype='COLOR', size=4, min=0.0, max=1.0,
        default=(0.0, 0.0, 0.0, 1.0), update=_on_color,
        description="Color of this layer's preview in the viewport (not baked)")
    # the preview material before 0.5.0 (_drop_old_previews)
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
    kind: EnumProperty(items=[('LINE', "Line Art", ""), ('GRID', "Grid", ""),
                              ('STITCH', "Stitches", "")], default='LINE', options={'HIDDEN'})
    # a stitch layer's own settings
    inset: _mm("Offset Inward", 3.0, "How far the stitch line sits inward from the marked "
               "edges", minv=-1000.0, soft_max=30.0)
    stitch_smooth: _mm("Smooth", 2.0, "Evens out low-poly zigzags along the line; larger "
                       "values also flatten curves", soft_max=50.0)
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
    thread_width: _mm("Width", 1.2, "Thread width", minv=0.01, soft_max=10.0)
    roundness: FloatProperty(name="Round Ends", default=1.0, min=0.0, max=1.0, subtype='FACTOR',
                             update=_on_change,
                             description="Corner radius of each stitch as a fraction of half "
                                         "its width (1 = fully round ends)")
    roundness_pct: FloatProperty(
        name="Round Ends", min=0.0, max=100.0, subtype='PERCENTAGE', precision=0, step=500,
        description="Corner radius of each stitch: 100% gives fully round ends",
        get=lambda self: self.roundness * 100.0,
        set=lambda self, v: setattr(self, "roundness", v / 100.0))
    even: BoolProperty(name="Even Fit", default=True, update=_on_change,
                       description="Closed loops get a whole number of stitches; open lines "
                                   "get equal space at both ends")
    dash_count: IntProperty(options={'HIDDEN'})       # stitches made last time
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


# the stitch layer defaults (StitchGenLine), for a stand-in without a layer
_STITCH_DEFAULTS = {"inset": 3.0, "smooth": 2.0, "corner_inset": 0.0, "style": 0,
                    "zigzag_height": 3.0, "length": 4.0, "gap": 2.0, "width": 1.2,
                    "roundness": 1.0, "even": True, "stitches": True,
                    "stitch_color": STITCH_COLOR}


def _stand_in(name):
    """An object-level stitch setting standing for the setting of the stitch
    layer the object's stitch settings stand for (_stitch_item). Without a
    stitch layer it keeps the value for the first one."""
    iname = _STITCH_MAP[name]

    def default():
        return _STITCH_DEFAULTS[name]

    def get(self):
        t = _stitch_item(self)
        if t is not None:
            v = getattr(t, iname)
            if name == "style":
                return _STYLES.index(v)
            return tuple(v) if name == "stitch_color" else v
        v = self.get(name)
        return default() if v is None else (tuple(v) if name == "stitch_color" else v)

    def set(self, v):
        t = _stitch_item(self)
        if t is None:
            self[name] = list(v) if name == "stitch_color" else v
        elif name == "style":
            t.style = _STYLES[v]
        else:
            setattr(t, iname, v)

    if name == "style":
        return EnumProperty(items=[(k, k, "") for k in _STYLES], get=get, set=set,
                            options={'HIDDEN'})
    if name in ("even", "stitches"):
        return BoolProperty(get=get, set=set, options={'HIDDEN'})
    if name == "stitch_color":
        return bpy.props.FloatVectorProperty(subtype='COLOR', size=4, get=get, set=set,
                                             options={'HIDDEN'})
    return FloatProperty(get=get, set=set, options={'HIDDEN'})


class StitchGenSettings(bpy.types.PropertyGroup):
    # the preview objects before 0.5.0 (_drop_old_previews)
    ribbon: PointerProperty(type=bpy.types.Object, options={'HIDDEN'})
    line_preview: PointerProperty(type=bpy.types.Object, options={'HIDDEN'})
    grid_preview: PointerProperty(type=bpy.types.Object, options={'HIDDEN'})
    line_color: bpy.props.FloatVectorProperty(       # before 0.3.0: one for all layers
        subtype='COLOR', size=4, min=0.0, max=1.0, default=(0.0, 0.0, 0.0, 1.0),
        options={'HIDDEN'})
    lines: CollectionProperty(type=StitchGenLine)      # the layer list
    line_index: IntProperty(name="Layer", default=0, update=_on_marks)
    show_corners: BoolProperty(name="Show Corners", default=True, update=_on_marks,
                               description="Show the marked corners in the viewport "
                                           "(display only)")
    ui_version: IntProperty(default=0)
    live: BoolProperty(name="Live", default=True, update=_on_change,
                       description="Rebuild the stitches while you change the values")

    # before 0.5.2 one side for all layers: each layer has its own now (_migrate_flip)
    flip: BoolProperty(default=False, options={'HIDDEN'})

    offset: _mm("Offset", 0.0, "Slide the stitches along the line", minv=-1000.0,
                soft_max=20.0)
    # Before 0.4.0 the stitch settings: now stand-ins for those of a stitch
    # layer (see _STITCH_MAP), for presets and scripts
    inset: _stand_in("inset")
    smooth: _stand_in("smooth")
    corner_inset: _stand_in("corner_inset")
    style: _stand_in("style")
    zigzag_height: _stand_in("zigzag_height")
    length: _stand_in("length")
    gap: _stand_in("gap")
    width: _stand_in("width")
    roundness: _stand_in("roundness")
    even: _stand_in("even")
    stitches: _stand_in("stitches")
    stitch_color: _stand_in("stitch_color")
    resolution: EnumProperty(
        name="Size", description="Size of the baked mask PNGs, in pixels",
        items=[('1024', "1024", ""), ('2048', "2048", ""), ('4096', "4096", ""),
               ('8192', "8192", "")],
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
    output_dir: StringProperty(
        name="Folder", default="//stitch_masks/",
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
