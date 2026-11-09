"""Stress test on a subdivided skirt. blender -b skirt_test.blend -P perf_test.py"""
import os, sys, time
import bpy, bmesh
sys.path.insert(0, os.environ.get("STITCH_PKG") or os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pattern_masks as sg
sg.register()
ob = bpy.data.objects["Skirt"]
bpy.context.view_layer.objects.active = ob
m = ob.modifiers.new("s", 'SUBSURF'); m.subdivision_type = 'SIMPLE'; m.levels = 4
bpy.ops.object.modifier_apply(modifier="s")
me = ob.data
bm = bmesh.new(); bm.from_mesh(me)
lay = bm.edges.layers.int.new(sg.core.PATH_ATTR)
for e in bm.edges:
    if e.is_boundary and all(v.co.z < -0.265 for v in e.verts):
        e[lay] = 1
bm.to_mesh(me); bm.free()
print("faces", len(me.polygons))
s = ob.stitch_gen; s.live = False
s.inset, s.smooth = 4.0, 2.0
for label in ("first", "dash-only", "inset change"):
    if label == "dash-only": s.gap = 3.0
    if label == "inset change": s.inset = 5.0
    t = time.perf_counter(); d = sg.regenerate(ob)
    print(label, f"{1000*(time.perf_counter()-t):.0f}ms", "dashes", d.dash_count, s.status)
