# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Rizum
"""Bake material, target selection and the mask baking operator."""

import traceback

import bpy

from . import bake, core, layers
from .i18n import rpt
from .layers import (
    _edge_set, _grid_items, _grid_layers, _line_items, _line_layers, _source_object, _stitch_items,
    _stitches_on,
)
from .rebuild import regenerate


MATERIAL = "StitchGen_Mask"           # the stitch shader the bake renders

# -- the stitch shader (bake) -----------------------------------------------------

def _mask_material():
    mat = bpy.data.materials.get(MATERIAL)
    if mat is not None:
        return mat
    mat = bpy.data.materials.new(MATERIAL)
    if hasattr(mat, "use_nodes") and not mat.use_nodes:
        mat.use_nodes = True
    mat.diffuse_color = (1.0, 0.35, 0.05, 1.0)
    if hasattr(mat, "surface_render_method"):
        mat.surface_render_method = 'DITHERED'
    nt = mat.node_tree
    nt.nodes.clear()
    N = nt.nodes.new
    L = nt.links.new

    def attr(name, x, y):
        n = N("ShaderNodeAttribute")
        n.attribute_name = name
        n.location = (x, y)
        return n

    def math(op, a=None, b=None, x=0, y=0, clamp=False):
        n = N("ShaderNodeMath")
        n.operation = op
        n.use_clamp = clamp
        n.location = (x, y)
        for i, v in enumerate((a, b)):
            if v is None:
                continue
            if isinstance(v, (int, float)):
                n.inputs[i].default_value = v
            else:
                L(v, n.inputs[i])
        return n.outputs[0]

    uv = attr("stitch_uv", -1400, 200)
    dims = attr("stitch_dims", -1400, -100)
    pxa = attr("stitch_aa", -1400, -400)
    sep_a = N("ShaderNodeSeparateXYZ")
    sep_a.location = (-1200, -400)
    L(pxa.outputs["Vector"], sep_a.inputs[0])
    sep_uv = N("ShaderNodeSeparateXYZ")
    sep_uv.location = (-1200, 200)
    L(uv.outputs["Vector"], sep_uv.inputs[0])
    sep_d = N("ShaderNodeSeparateXYZ")
    sep_d.location = (-1200, -100)
    L(dims.outputs["Vector"], sep_d.inputs[0])
    hl, hw, r = sep_d.outputs[0], sep_d.outputs[1], sep_d.outputs[2]
    # rounded-rectangle signed distance
    qx = math('SUBTRACT', math('ABSOLUTE', sep_uv.outputs[0], x=-1000, y=300),
              math('SUBTRACT', hl, r, x=-1000, y=100), x=-800, y=250)
    qy = math('SUBTRACT', math('ABSOLUTE', sep_uv.outputs[1], x=-1000, y=0),
              math('SUBTRACT', hw, r, x=-1000, y=-200), x=-800, y=0)
    mx = math('MAXIMUM', qx, 0.0, x=-600, y=300)
    my = math('MAXIMUM', qy, 0.0, x=-600, y=100)
    outside = math('SQRT', math('ADD', math('MULTIPLY', mx, mx, x=-450, y=300),
                                math('MULTIPLY', my, my, x=-450, y=100), x=-300, y=200),
                   x=-150, y=200)
    inside = math('MINIMUM', math('MAXIMUM', qx, qy, x=-600, y=-100), 0.0, x=-450, y=-100)
    sd = math('SUBTRACT', math('ADD', outside, inside, x=0, y=100), r, x=150, y=100)
    cov = math('SUBTRACT', 0.5, math('DIVIDE', sd, sep_a.outputs[0], x=300, y=0),
               x=450, y=0, clamp=True)

    emit = N("ShaderNodeEmission")
    emit.location = (600, 200)
    emit.inputs["Color"].default_value = (1, 1, 1, 1)
    emit.inputs["Strength"].default_value = 1.0
    transp = N("ShaderNodeBsdfTransparent")
    transp.location = (600, 350)
    mix = N("ShaderNodeMixShader")
    mix.location = (800, 200)
    L(cov, mix.inputs[0])
    L(transp.outputs[0], mix.inputs[1])
    L(emit.outputs[0], mix.inputs[2])
    out = N("ShaderNodeOutputMaterial")
    out.location = (1000, 200)
    L(mix.outputs[0], out.inputs["Surface"])
    return mat


def _bake_count(ob):
    """Layers the bake will write: the shown ones that have something to bake."""
    s = ob.stitch_gen
    attrs = ob.data.attributes
    n = sum(1 for l in _stitch_items(s) if l.enabled and l.dash_count > 0)
    for l in _line_items(s):
        if l.enabled and l.width > 0 and any(a in attrs for a in _edge_set(s, l)):
            n += 1
    for l in _grid_items(s):
        if l.enabled and l.grid_cell > 0 and any(a in attrs for a in _edge_set(s, l)):
            n += 1
    return n


_bake_flag = {"state": None}


def _on_bake_complete(*_args):
    _bake_flag["state"] = "done"


def _on_bake_cancel(*_args):
    _bake_flag["state"] = "cancel"


def _redraw(context):
    for win in context.window_manager.windows:
        for area in win.screen.areas:
            if area.type in ('VIEW_3D', 'STATUSBAR'):
                area.tag_redraw()


def _bakeable(ob, scene):
    s = ob.stitch_gen
    return bool(_bake_count(ob) and (_stitches_on(s)
                                     or _line_layers(s, scene) or _grid_layers(s, scene)))


def _bake_targets(context):
    """What one press of Bake bakes: the object the panel shows and the other
    selected objects, each that has something to bake, with its own settings."""
    main = _source_object(context)
    obs = [main] if main is not None else []
    obs += [o for o in context.selected_objects if o.type == 'MESH' and o != main]
    return [o for o in obs if _bakeable(o, context.scene)]


def _object_by_uid(uid):
    return next((o for o in bpy.data.objects if o.session_uid == uid), None)


class STITCHGEN_OT_bake(bpy.types.Operator):
    ("Bake the stitches and each line art layer into a 16-bit mask PNG per texture set, "
     "for every selected object")
    bl_idname = "stitch_gen.bake"
    bl_label = "Bake Masks"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        if _source_object(context) is None or context.window_manager.stitch_gen_baking:
            return False
        if _bake_targets(context):
            return True
        cls.poll_message_set(rpt("Nothing to bake: show a layer that has edges"))
        return False

    def _jobs(self, context, ob, data):
        """(stitch session or None, line bake or None) for this object."""
        s = ob.stitch_gen
        session = lines = None
        if data.dash_count > 0:
            shown = [l for l in _stitch_items(s) if l.enabled]
            names = bake.unique_names([l.name for l in shown], "stitch")
            session = bake.BakeSession(context, ob, [(r, n) for (_a, r), n in
                                                     zip(data.stitches, names)],
                                       s, _mask_material())
        layers = _line_layers(s, context.scene)
        entry = core._cache.get(ob.name_full)
        texel = []                          # bakes computed per texel (no Cycles)
        if layers and entry is not None:
            lb = bake.LineBake(ob, entry, s, layers)
            if lb.groups:
                texel.append(lb)
        grids = _grid_layers(s, context.scene)
        if grids and entry is not None:
            gb = bake.GridBake(ob, entry, s, grids)
            if gb.groups:
                texel.append(gb)
        lines = bake.Chain(texel) if texel else None
        if session is None and lines is None:
            raise RuntimeError(rpt("No stitches to bake"))
        return session, lines

    def _error(self, ob, msg):
        many = len(getattr(self, "_queue", ())) > 1
        self.report({'ERROR'}, f"{ob.name}: {msg}" if many else msg)

    def execute(self, context):
        """Blocking bake (used without a window, e.g. from scripts)."""
        targets = _bake_targets(context)
        self._queue = [o.session_uid for o in targets]
        paths = []
        try:
            for ob in targets:
                layers._baking["name"] = ob.name_full
                data = regenerate(ob, context.scene)
                if data is None:
                    self._error(ob, ob.stitch_gen.status)
                    return {'CANCELLED'}
                try:
                    session, lines = self._jobs(context, ob, data)
                    if session is not None:
                        paths += bake.bake_masks(session)
                    if lines is not None:
                        for i in range(len(lines.groups)):
                            paths += lines.step(i, paths)
                except Exception as e:
                    traceback.print_exc()
                    self._error(ob, str(e))
                    return {'CANCELLED'}
        finally:
            layers._baking["name"] = None
        self.report({'INFO'}, rpt("Saved {}").format(", ".join(paths)))
        return {'FINISHED'}

    def invoke(self, context, event):
        """Bake as a background job: Blender stays usable, the status bar shows
        the progress (cancel there or with Esc). The selected objects are baked
        one after another."""
        if bpy.app.background or context.window is None:
            return self.execute(context)
        self._queue = [o.session_uid for o in _bake_targets(context)]    # names can change
        self._k = -1
        self._session = self._lines = None
        self._written = []
        self._window = context.window
        handlers = bpy.app.handlers
        handlers.object_bake_complete.append(_on_bake_complete)
        handlers.object_bake_cancel.append(_on_bake_cancel)
        wm = context.window_manager
        wm.stitch_gen_baking = True
        started = self._next_object(context)
        if not started:
            if started is None:
                self.report({'ERROR'}, rpt("No stitches to bake"))
            return self._end(context, ok=False)
        self._timer = wm.event_timer_add(0.25, window=context.window)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _next_object(self, context):
        """Start baking the next object in the queue. True when started, False
        on an error (reported), None when there is nothing left."""
        while True:
            self._session = self._lines = None
            self._k += 1
            if self._k >= len(self._queue):
                return None
            ob = _object_by_uid(self._queue[self._k])
            if ob is None:                     # deleted while the others were baking
                continue
            layers._baking["name"] = ob.name_full
            data = regenerate(ob, context.scene)
            if data is None:
                self._error(ob, ob.stitch_gen.status)
                return False
            try:
                self._session, self._lines = self._jobs(context, ob, data)
                if self._session is not None:
                    self._session.begin()
                    if not self._session.groups:
                        self._session.end()
                        self._session = None
            except Exception as e:
                traceback.print_exc()
                if self._session is not None:
                    self._session.end()
                    self._session = None
                self._error(ob, str(e))
                return False
            if self._session is None and self._lines is None:
                continue
            self._i = 0
            return self._start(context)

    def _steps(self):
        a = len(self._session.groups) if self._session is not None else 0
        b = len(self._lines.groups) if self._lines is not None else 0
        return a, b

    def _start(self, context):
        wm = context.window_manager
        a, b = self._steps()
        n = a + b
        k, objects = self._k, len(self._queue)
        wm.stitch_gen_bake_progress = (k + self._i / n) / objects
        label = rpt("Baking {}/{}").format(self._i + 1, n)
        if objects > 1:                  # which object, as the outliner names it
            label = f"{_object_by_uid(self._queue[k]).name}  {self._i + 1}/{n}"
        wm.stitch_gen_bake_label = label
        _redraw(context)
        if self._i >= a:                 # line art: no Cycles job, done on the next tick
            _bake_flag["state"] = "lines"
            return True
        _bake_flag["state"] = "running"
        try:
            kwargs = self._session.prepare(self._i)
            with context.temp_override(window=self._window):
                res = bpy.ops.object.bake('INVOKE_DEFAULT', **kwargs)
        except Exception as e:
            traceback.print_exc()
            self.report({'ERROR'}, str(e))
            return False
        if 'CANCELLED' in res:
            return False
        if 'FINISHED' in res:            # ran without a job: already done
            _bake_flag["state"] = "done"
        return True

    def modal(self, context, event):
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}
        state = _bake_flag["state"]
        if state in ("done", "lines"):
            a, b = self._steps()
            try:
                if state == "done":
                    self._written.append(self._session.finish())
                else:
                    self._written += self._lines.step(self._i - a, self._written)
            except Exception as e:
                traceback.print_exc()
                self.report({'ERROR'}, str(e))
                return self._end(context, ok=False)
            self._i += 1
            if self._i == a and self._session is not None:
                self._session.end()          # scene back before the line art steps
            if self._i < a + b:
                if not self._start(context):
                    return self._end(context, ok=False)
                return {'PASS_THROUGH'}
            started = self._next_object(context)
            if started:
                return {'PASS_THROUGH'}
            return self._end(context, ok=started is None)
        if state == "cancel":
            self.report({'WARNING'}, rpt("Baking stopped"))
            return self._end(context, ok=False)
        return {'PASS_THROUGH'}

    def _end(self, context, ok):
        wm = context.window_manager
        if getattr(self, "_timer", None) is not None:
            wm.event_timer_remove(self._timer)
            self._timer = None
        handlers = bpy.app.handlers
        for lst, fn in ((handlers.object_bake_complete, _on_bake_complete),
                        (handlers.object_bake_cancel, _on_bake_cancel)):
            if fn in lst:
                lst.remove(fn)
        _bake_flag["state"] = None
        try:
            if self._session is not None:
                self._session.end()
        except Exception:
            traceback.print_exc()
        wm.stitch_gen_baking = False
        layers._baking["name"] = None
        wm.stitch_gen_bake_progress = 0.0
        _redraw(context)
        if ok:
            self.report({'INFO'}, rpt("Saved {}").format(", ".join(self._written)))
            return {'FINISHED'}
        return {'CANCELLED'}
