"""Grid layer on a copy of a real file, marked on one run of its line art
edges: the run nearest a UV point (walked until the line art branches), or
the top part of the line art (mode "top").

blender -b --factory-startup <copy.blend> -P grid_hand.py -- <object> <out.blend> <u> <v>
blender -b --factory-startup <copy.blend> -P grid_hand.py -- <object> <out.blend> top [fraction]
"""
import os
import sys
import time

import bpy
import bmesh
import numpy as np

argv = sys.argv[sys.argv.index("--") + 1:]
name, out = argv[0], argv[1]
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
me = ob.data
pairs = core.read_path_edges(me, core.line_attr_names(me)[0])
co = np.array([ob.matrix_world @ v.co for v in me.vertices])
if argv[2] == "top":
    frac = float(argv[3]) if len(argv) > 3 else 0.1
    z = co[:, 2]
    thr = np.percentile(z[np.unique(pairs)], 100 * (1 - frac))
    want = {tuple(sorted(p)) for p in pairs.tolist() if z[p].min() >= thr}
else:
    target = np.array([float(argv[2]), float(argv[3])])
    uv = np.zeros((len(me.loops), 2))
    me.uv_layers.active.data.foreach_get("uv", uv.ravel())
    vuv = np.zeros((len(me.vertices), 2))
    lv = np.array([lp.vertex_index for lp in me.loops])
    vuv[lv] = uv
    mid = (vuv[pairs[:, 0]] + vuv[pairs[:, 1]]) / 2
    seed = int(np.argmin(np.linalg.norm(mid - target, axis=1)))
    deg = np.bincount(pairs.reshape(-1), minlength=len(me.vertices))
    by_v = {}
    for i, (a, b) in enumerate(pairs.tolist()):
        by_v.setdefault(a, []).append(i)
        by_v.setdefault(b, []).append(i)
    keep = {seed}
    # walk both ways from the seed edge while the line art does not branch
    # or turn sharply (in UV)
    for start, prev in ((int(pairs[seed][0]), int(pairs[seed][1])),
                        (int(pairs[seed][1]), int(pairs[seed][0]))):
        v, w = start, prev
        while deg[v] == 2:
            nxt = [i for i in by_v[v] if i not in keep]
            if not nxt:
                break
            i = nxt[0]
            u = int(pairs[i][0] if pairs[i][1] == v else pairs[i][1])
            a1, a2 = vuv[v] - vuv[w], vuv[u] - vuv[v]
            cos = float(a1 @ a2) / (np.linalg.norm(a1) * np.linalg.norm(a2) + 1e-12)
            if cos < 0.5:
                break
            keep.add(i)
            v, w = u, v
    want = {tuple(sorted(pairs[i])) for i in keep}
print("RESULT marked edges", len(want), "of", len(pairs))
bpy.ops.stitch_gen.grid_add()
bpy.ops.object.mode_set(mode='EDIT')
bm = bmesh.from_edit_mesh(me)
for e in bm.edges:
    e.select_set(tuple(sorted(v.index for v in e.verts)) in want)
bm.select_flush_mode()
bmesh.update_edit_mesh(me)
bpy.ops.stitch_gen.path_add()
bpy.ops.object.mode_set(mode='OBJECT')
for l in layers._line_items(s):
    l.enabled = False                    # only the grid
t0 = time.time()
sg.regenerate(ob)
print("RESULT preview faces", pv.grid_faces(ob), "status", s.status or "ok",
      "time %.2f" % (time.time() - t0))
bpy.ops.wm.save_as_mainfile(filepath=out, copy=True)
