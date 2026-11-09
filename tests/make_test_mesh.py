"""Build a low-poly test skirt: folds, scalloped hem made of ngon fans, UV seam at u=0.

blender -b --factory-startup -P make_test_mesh.py -- <out.blend>
"""
import math
import sys

import bpy
import bmesh

out = sys.argv[sys.argv.index("--") + 1]

SEG = 64          # columns around
FOLDS = 8
SCALLOPS = 16
ROWS = [0.0, -0.08, -0.16, -0.22, -0.26]   # z of quad rows (waist -> above hem)
HEM_TOP, HEM_LOW = -0.272, -0.300           # cusp / scallop bottom


def radius(z):
    return 0.12 + (0.22 - 0.12) * (-z / 0.3)


def fold_depth(z):
    return 0.35 * min(1.0, (-z / 0.3) ** 1.5)


def pos(theta, z):
    d = fold_depth(z)
    th = theta + 0.11 * math.sin(FOLDS * theta) * (d / 0.35)
    r = radius(z) * (1.0 - d * 0.5 * (1.0 + math.cos(FOLDS * theta)))
    return (r * math.cos(th), r * math.sin(th), z)


bpy.ops.wm.read_factory_settings(use_empty=True)
bm = bmesh.new()
uvl = bm.loops.layers.uv.new("UVMap")

rows = []
for z in ROWS:
    rows.append([bm.verts.new(pos(2 * math.pi * j / SEG, z)) for j in range(SEG)])
HEM = SEG * 2
hem = []
for j in range(HEM):
    t = (j % (HEM // SCALLOPS)) / (HEM // SCALLOPS)
    z = HEM_TOP + (HEM_LOW - HEM_TOP) * math.sin(math.pi * t) ** 0.7
    hem.append(bm.verts.new(pos(2 * math.pi * j / HEM, z)))


def ring_u(verts):
    """Arc-length u per ring, so texels stay roughly square (like a real unwrap)."""
    co = [v.co for v in verts] + [verts[0].co]
    cum = [0.0]
    for a, b in zip(co, co[1:]):
        cum.append(cum[-1] + (b - a).length)
    return [c / cum[-1] for c in cum], cum[-1]


U = {}
for ring in rows + [hem]:
    us, length = ring_u(ring)
    U[len(U)] = us
HEM_LEN = ring_u(hem)[1]
S = 1.0 / HEM_LEN


def uv_of(theta_index, total, z, ring=None):
    us = U[ring]
    return (us[theta_index], 0.55 + z * S)


def face(verts, uvs):
    f = bm.faces.new(verts)
    for loop, uv in zip(f.loops, uvs):
        loop[uvl].uv = uv
    return f


for r in range(len(ROWS) - 1):
    a, b = rows[r], rows[r + 1]
    for j in range(SEG):
        j1 = (j + 1) % SEG
        face([a[j], b[j], b[j1], a[j1]],
             [uv_of(j, SEG, ROWS[r], r), uv_of(j, SEG, ROWS[r + 1], r + 1),
              uv_of(j + 1, SEG, ROWS[r + 1], r + 1), uv_of(j + 1, SEG, ROWS[r], r)])
top = rows[-1]
zt = ROWS[-1]
for j in range(SEG):
    j1 = (j + 1) % SEG
    h0, h1, h2 = hem[2 * j], hem[2 * j + 1], hem[(2 * j + 2) % HEM]
    face([top[j], h0, h1, h2, top[j1]],
         [uv_of(j, SEG, zt, len(rows) - 1), uv_of(2 * j, HEM, h0.co.z, len(rows)),
          uv_of(2 * j + 1, HEM, h1.co.z, len(rows)), uv_of(2 * j + 2, HEM, h2.co.z, len(rows)),
          uv_of(j + 1, SEG, zt, len(rows) - 1)])

bm.normal_update()
me = bpy.data.meshes.new("Skirt")
bm.to_mesh(me)
bm.free()
ob = bpy.data.objects.new("Skirt", me)
bpy.context.scene.collection.objects.link(ob)
mat = bpy.data.materials.new("Skirt_Cloth")
me.materials.append(mat)
bpy.ops.wm.save_as_mainfile(filepath=out)
print("saved", out, len(me.vertices), "verts", len(me.polygons), "faces")
