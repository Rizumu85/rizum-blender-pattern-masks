"""Grid layer on a copy of a real file: mark the top edges of an object's
existing line art edges as the grid's edges, build the preview, save a copy.

blender -b --factory-startup <copy.blend> -P grid_user.py -- <object> <out.blend> [top_fraction]
"""
import os
import sys

import bpy
import bmesh
import numpy as np

argv = sys.argv[sys.argv.index("--") + 1:]
name, out = argv[0], argv[1]
frac = float(argv[2]) if len(argv) > 2 else 0.2
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import rizum_pattern_masks as sg  # noqa: E402
from rizum_pattern_masks import core, layers, load  # noqa: E402
from tests import _preview as pv  # noqa: E402

sg.register()
load._on_load(None)
ob = bpy.data.objects[name]
for o in bpy.context.view_layer.objects:
    o.select_set(False)
bpy.context.view_layer.objects.active = ob
ob.select_set(True)
s = ob.stitch_gen
s.live = False
src = core.line_attr_names(ob.data)[0]
pairs = core.read_path_edges(ob.data, src)
z = np.array([(ob.matrix_world @ v.co).z for v in ob.data.vertices])
zmin = z[np.unique(pairs)]
thr = np.percentile(zmin, 100 * (1 - frac))
top = {tuple(sorted(p)) for p in pairs.tolist() if z[p].min() >= thr}
if len(argv) > 3:                        # the grid's edges given as vertex pairs
    top = {tuple(sorted(p)) for p in np.load(argv[3]).tolist()}
print("RESULT top edges", len(top), "of", len(pairs))
weld = None
if len(argv) > 3:                        # pairs in the add-on's welded numbering
    weld = core.Topology(ob.data, ob.matrix_world, "").vert_weld
bpy.ops.stitch_gen.grid_add()
bpy.ops.object.mode_set(mode='EDIT')
bm = bmesh.from_edit_mesh(ob.data)
bm.verts.ensure_lookup_table()
n_sel = 0
for e in bm.edges:
    ids = [v.index for v in e.verts]
    if weld is not None:
        ids = [int(weld[i]) for i in ids]
    on = tuple(sorted(ids)) in top
    e.select_set(on)
    n_sel += on
print("RESULT selected", n_sel)
bm.select_flush_mode()
bmesh.update_edit_mesh(ob.data)
bpy.ops.stitch_gen.path_add()
bpy.ops.object.mode_set(mode='OBJECT')
for l in layers._line_items(s):
    l.enabled = False                    # only the grid in the screenshot
sg.regenerate(ob)
print("RESULT preview faces", pv.grid_faces(ob), "status", s.status or "ok")
bpy.ops.wm.save_as_mainfile(filepath=out, copy=True)
