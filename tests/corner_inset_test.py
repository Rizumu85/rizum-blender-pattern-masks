"""Corner Inset: depth of the corner point with 0 and 2.5 mm.
blender -b result.blend -P corner_inset_test.py -- <out_dir>"""
import os
import sys
import bpy
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import rizum_pattern_masks as sg  # noqa: E402
from rizum_pattern_masks import core  # noqa: E402

out = sys.argv[sys.argv.index("--") + 1]
sg.register()
ob = bpy.data.objects["Skirt"]
s = ob.stitch_gen
s.live = False
cusp = np.array(ob.matrix_world @ ob.data.vertices[320].co)      # hem vertex 0 = a scallop junction
for ci in (0.0, 2.5):
    s.corner_inset = ci
    d = sg.regenerate(ob)
    cls = next(iter(core._cache[ob.name_full]["stitch"].values()))["cls"]
    pts = [cl.sample(np.array([c]))[0][0] for cl in cls for c in cl.corners]
    near = min(pts, key=lambda p: np.linalg.norm(p - cusp))
    print(f"RESULT corner_inset={ci} corners={len(pts)} corner point depth from cusp vertex "
          f"{np.linalg.norm(near - cusp) * 1000:.2f} mm, status={s.status!r}, stitches={d.dash_count}")
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, f"ci_{ci}.blend"), copy=True)
