"""Performance: how long the work behind each kind of edit takes, on three mesh
sizes. Prints one JSON line per mesh.

    blender -b --factory-startup skirt_test.blend -P perf_suite.py

Per mesh (the skirt, subdivided 1x and 2x): two stitch layers (hem dashed,
waist zigzag), a line art layer following the stitches, a grid from the waist.
Times (ms, median of a few runs where it repeats):

  first        the first build (cold caches)
  length       a stitch length/gap change (dashes only)
  inset        a stitch offset change (the stitch line rebuilt)
  line_width   a line art width change
  grid_cell    a grid cell size change
  edge         one more marked edge (the edges change)
  overlay      building the overlay's marks for the viewport

The add-on rebuilds 0.15 s after the last change of a slider (debounced), so
what counts for smoothness is that a rebuild ends well within a frame budget
of the slider, not that it is instant: about 100 ms or less feels live.
"""
import json
import os
import statistics
import sys
import time

import bpy
import bmesh

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import rizum_pattern_masks as sg  # noqa: E402
from rizum_pattern_masks import core, overlay  # noqa: E402

sg.register()
base = bpy.data.objects["Skirt"]


def mark(o, attr, pick):
    me = o.data
    bm = bmesh.new()
    bm.from_mesh(me)
    lay = bm.edges.layers.int.get(attr) or bm.edges.layers.int.new(attr)
    for e in bm.edges:
        if e.is_boundary and all(pick(v.co.z) for v in e.verts):
            e[lay] = 1
    bm.to_mesh(me)
    bm.free()


def ms(fn, repeat=1):
    out = []
    for _ in range(repeat):
        t = time.perf_counter()
        fn()
        out.append(1000 * (time.perf_counter() - t))
    return round(statistics.median(out), 1)


for level in (0, 1, 2):
    o = base.copy()
    o.data = base.data.copy()
    o.name = f"Skirt_sub{level}"
    bpy.context.collection.objects.link(o)
    bpy.context.view_layer.objects.active = o
    if level:
        m = o.modifiers.new("s", 'SUBSURF')
        m.subdivision_type = 'SIMPLE'
        m.levels = level
        bpy.ops.object.modifier_apply(modifier="s")
    s = o.stitch_gen
    s.live = False
    with bpy.context.temp_override(active_object=o, object=o):
        bpy.ops.stitch_gen.stitch_add()
        hem = s.lines[s.line_index]
        bpy.ops.stitch_gen.stitch_add()
        waist = s.lines[s.line_index]
        waist.style = 'ZIGZAG'
        bpy.ops.stitch_gen.line_add()
        line = s.lines[s.line_index]
        line.ref_attr = hem.edge_attr
        line.width = 1.0
        bpy.ops.stitch_gen.grid_add()
        grid = s.lines[s.line_index]
    mark(o, hem.edge_attr, lambda z: z < -0.265)
    mark(o, waist.edge_attr, lambda z: z > -0.01)
    mark(o, grid.edge_attr, lambda z: z > -0.01)
    core.drop_cache(o)
    regen = lambda: sg.regenerate(o, bpy.context.scene)  # noqa: E731
    r = {"mesh": o.name, "faces": len(o.data.polygons)}
    r["first"] = ms(regen)
    r["dashes"] = sum(l.dash_count for l in sg._stitch_items(s))

    def step(setter):
        def run():
            setter()
            regen()
        return run
    k = [0]

    def bump(item, name, a, b):
        def f():
            k[0] += 1
            setattr(item, name, a if k[0] % 2 else b)
        return f
    r["length"] = ms(step(bump(hem, "length", 4.0, 4.5)), 5)
    r["inset"] = ms(step(bump(hem, "inset", 3.0, 3.5)), 5)
    r["line_width"] = ms(step(bump(line, "width", 1.0, 1.4)), 5)
    r["grid_cell"] = ms(step(bump(grid, "grid_cell", 8.0, 9.0)), 3)

    def add_edge():
        me = o.data
        a = me.attributes[hem.edge_attr]
        vals = [0] * len(a.data)
        a.data.foreach_get("value", vals)
        i = vals.index(0)
        vals[i] = 1
        a.data.foreach_set("value", vals)
        me.update()
        regen()
    r["edge"] = ms(add_edge)

    def marks():
        overlay.invalidate(o)
        overlay._marks(o)
    r["overlay"] = ms(marks, 3)
    print("PERF", json.dumps(r))
print("PERF DONE")
