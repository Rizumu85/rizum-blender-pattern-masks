"""Build the demo skirt used for the README images and the listing's panel shot, set up the add-on's
layers on it, bake the masks, render the skirt textured with them, and
compose the masks into one UV image.

blender -b --factory-startup -P docs/source/make_demo.py -- <out_dir> [<samples>]

Writes into <out_dir>: demo.blend, masks/*.png, render.png (transparent
background), uv_masks.png.
"""
import math
import os
import sys

import bpy
import bmesh
import numpy as np
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
out_dir = os.path.abspath(argv[0])
samples = int(argv[1]) if len(argv) > 1 else 64
repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, repo)
import rizum_pattern_masks as sg  # noqa: E402

os.makedirs(out_dir, exist_ok=True)

# -- the skirt: an A-line with a scalloped hem, one UV strip ------------------
# The same shape as the docs' toon skirt (docs/source/site_layers3d.js), scaled
# to 0.30 m from waist to hem: waist radius 0.42, hem 0.98, length 1.05 there.
SEG = 200                      # columns around the waist (40 hem verts per scallop)
FOLDS = 10                     # soft ripples, one per scallop
SCALLOPS = 10
LENGTH = 0.30
R0, R1 = 0.12, 0.28            # waist and hem radius
ROWS = [-0.0125 * i for i in range(22)]       # waist (0) down to -0.2625
HEM_TOP, HEM_LOW = -0.275, -0.305


def radius(z):
    return R0 + (R1 - R0) * (-z / LENGTH) ** 0.8


TURN = math.radians(float(os.environ.get("DEMO_TURN", "54")))   # keeps the grid's forks off the front


def pos(theta, z):
    # the ripples dip in at the scallop points, as on the toon skirt
    r = radius(z) * (1.0 - 0.045 * (-z / LENGTH) * math.cos(FOLDS * theta))
    return (r * math.cos(theta + TURN), r * math.sin(theta + TURN), z)


bpy.ops.wm.read_factory_settings(use_empty=True)
sg.register()
bm = bmesh.new()
uvl = bm.loops.layers.uv.new("UVMap")
rows = [[bm.verts.new(pos(2 * math.pi * j / SEG, z)) for j in range(SEG)] for z in ROWS]
HEM = SEG * 2
per = HEM // SCALLOPS
hem = []
for j in range(HEM):
    t = (j % per) / per
    z = HEM_TOP + (HEM_LOW - HEM_TOP) * math.sin(math.pi * t) ** 0.7
    hem.append(bm.verts.new(pos(2 * math.pi * j / HEM, z)))


def ring_u(verts):
    co = [v.co for v in verts] + [verts[0].co]
    cum = [0.0]
    for a, b in zip(co, co[1:]):
        cum.append(cum[-1] + (b - a).length)
    return [c / cum[-1] for c in cum], cum[-1]


rings = rows + [hem]
U = [ring_u(r)[0] for r in rings]
S = 1.0 / ring_u(hem)[1]


def uv(ring, k):
    return (U[ring][k], 0.6 + rings[ring][k % len(rings[ring])].co.z * S)


def face(verts, uvs):
    f = bm.faces.new(verts)
    for loop, c in zip(f.loops, uvs):
        loop[uvl].uv = c
    f.smooth = True
    return f


for r in range(len(ROWS) - 1):
    a, b = rows[r], rows[r + 1]
    for j in range(SEG):
        j1 = (j + 1) % SEG
        face([a[j], b[j], b[j1], a[j1]], [uv(r, j), uv(r + 1, j), uv(r + 1, j + 1), uv(r, j + 1)])
top, last = rows[-1], len(rows) - 1
for j in range(SEG):
    j1 = (j + 1) % SEG
    h0, h1, h2 = 2 * j, 2 * j + 1, (2 * j + 2)
    face([top[j], hem[h0], hem[h1], hem[h2 % HEM], top[j1]],
         [uv(last, j), uv(last + 1, h0), uv(last + 1, h1), uv(last + 1, h2), uv(last, j + 1)])
bm.normal_update()
me = bpy.data.meshes.new("Skirt")
bm.to_mesh(me)
bm.free()
ob = bpy.data.objects.new("Skirt", me)
bpy.context.scene.collection.objects.link(ob)
mat = bpy.data.materials.new("Cloth")
me.materials.append(mat)
bpy.context.view_layer.objects.active = ob
ob.select_set(True)
print("RESULT mesh", len(me.vertices), "verts", len(me.polygons), "faces")

# -- the add-on's layers -------------------------------------------------------
s = ob.stitch_gen
s.live = False


def mark(row, pick):
    s.line_index = row
    bpy.ops.object.mode_set(mode='EDIT')
    bmx = bmesh.from_edit_mesh(me)
    for e in bmx.edges:
        e.select_set(False)
    for v in bmx.verts:
        v.select_set(False)
    for e in bmx.edges:
        if e.is_boundary and pick([v.co.z for v in e.verts]):
            e.select_set(True)
    bmx.select_mode = {'EDGE'}
    bmx.select_flush_mode()
    bmesh.update_edit_mesh(me)
    bpy.ops.stitch_gen.path_add()
    bpy.ops.object.mode_set(mode='OBJECT')


bpy.ops.stitch_gen.stitch_add()
mark(0, lambda zs: all(z < HEM_TOP + 0.001 for z in zs))         # the scalloped hem
s.inset, s.length, s.gap, s.width, s.smooth = 14.0, 14.0, 8.0, 3.6, 3.0

bpy.ops.stitch_gen.line_add()                                      # hem outline
trim = s.lines[s.line_index]
trim.name = "trim"
trim.ref_attr = s.lines[0].edge_attr                               # follows the stitch edges
trim.width, trim.offset = 3.5, 0.0

bpy.ops.stitch_gen.line_add()                                      # waistband
band = s.lines[s.line_index]
band.name = "waistband"
mark(s.line_index, lambda zs: all(z > -0.001 for z in zs))
band.width, band.offset = 22.0, 0.0

bpy.ops.stitch_gen.grid_add()                                      # gingham from the waist
g = s.lines[s.line_index]
g.name = "gingham"
g.ref_attr = band.edge_attr
g.grid_cell, g.grid_wobble = 30.0, 0.25
sg.regenerate(ob, create=True)
print("RESULT layers", [(l.name, l.edge_attr, l.ref_attr) for l in s.lines], "status", s.status or "ok",
      "stitches", s.dash_count)

# -- bake ----------------------------------------------------------------------
masks = os.path.join(out_dir, "masks")
os.makedirs(masks, exist_ok=True)
for f in os.listdir(masks):
    os.remove(os.path.join(masks, f))
s.output_dir = masks
s.resolution = '4096'
print("RESULT bake", bpy.ops.stitch_gen.bake())
files = sorted(os.listdir(masks))
print("RESULT masks", files)


def load(name):
    img = bpy.data.images.load(os.path.join(masks, f"Skirt_Cloth_{name}.png"))
    img.colorspace_settings.name = "Non-Color"
    return img


# -- material from the masks -----------------------------------------------------
def lin(hexcode):
    """sRGB hex to linear RGB (what shader colors take)."""
    c = [int(hexcode[i:i + 2], 16) / 255.0 for i in (1, 3, 5)]
    return tuple(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c)


CREAM, NAVY, INK, THREAD = lin("#EFE7D8"), lin("#22304A"), lin("#12161D"), lin("#E8843A")
mat.use_nodes = True
nt = mat.node_tree
nt.nodes.clear()
out = nt.nodes.new("ShaderNodeOutputMaterial")
bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
bsdf.inputs["Roughness"].default_value = 0.85
nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
color = nt.nodes.new("ShaderNodeRGB")
color.outputs[0].default_value = CREAM + (1.0,)
sock = color.outputs[0]
strength = {}
for name, col, k in (("gingham_black", NAVY, 0.88), ("waistband", NAVY, 1.0),
                     ("trim", INK, 1.0), ("stitch", THREAD, 1.0)):
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = load(name)
    tex.interpolation = 'Cubic'
    mul = nt.nodes.new("ShaderNodeMath")
    mul.operation = 'MULTIPLY'
    mul.inputs[1].default_value = k
    strength[name] = mul.inputs[1]
    nt.links.new(tex.outputs["Color"], mul.inputs[0])
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = 'RGBA'
    by_id = {i.identifier: i for i in mix.inputs}
    by_id["B_Color"].default_value = col + (1.0,)
    nt.links.new(mul.outputs[0], by_id["Factor_Float"])
    nt.links.new(sock, by_id["A_Color"])
    sock = next(o for o in mix.outputs if o.identifier == "Result_Color")
nt.links.new(sock, bsdf.inputs["Base Color"])

# hide the add-on's previews in the render (they are viewport helpers)
for o in bpy.data.objects:
    if o != ob:
        o.hide_render = True

# -- render ----------------------------------------------------------------------
sc = bpy.context.scene
sc.render.engine = 'CYCLES'
sc.cycles.samples = samples
sc.cycles.use_denoising = True
sc.render.film_transparent = True
sc.render.resolution_x, sc.render.resolution_y = 1400, 1100
sc.view_settings.view_transform = 'Standard'
world = bpy.data.worlds.new("World")
sc.world = world
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.55, 0.57, 0.62, 1.0)
world.node_tree.nodes["Background"].inputs[1].default_value = 0.35
cam_data = bpy.data.cameras.new("Cam")
cam_data.lens = 62
cam = bpy.data.objects.new("Cam", cam_data)
sc.collection.objects.link(cam)
cam.location = (0.62, -0.98, 0.09)       # three-quarter front, just above the waist
target = Vector((0.0, 0.0, -0.15))


def aim(o):
    o.rotation_euler = (target - o.location).to_track_quat('-Z', 'Y').to_euler()


aim(cam)
sc.camera = cam
for name, loc, energy, size in (("Key", (1.2, -0.6, 1.0), 45.0, 0.8),
                                ("Fill", (-1.0, -1.2, 0.2), 12.0, 1.5),
                                ("Rim", (-0.4, 1.3, 0.8), 30.0, 0.6)):
    ld = bpy.data.lights.new(name, 'AREA')
    ld.energy, ld.size = energy, size
    lo = bpy.data.objects.new(name, ld)
    sc.collection.objects.link(lo)
    lo.location = loc
    aim(lo)
sc.render.filepath = os.path.join(out_dir, "render.png")
bpy.ops.render.render(write_still=True)
print("RESULT render", sc.render.filepath)
# a close-up of the hem: stitches round the scallops, sharp at the points
# (grid off, so the stitches and the outline read on their own)
strength["gingham_black"].default_value = 0.0
cam.location = (0.33, -0.50, -0.20)
target = Vector((0.113, -0.155, -0.272))       # the cusp on the fold crest at -54 degrees
aim(cam)
cam_data.lens = 85
sc.render.resolution_x, sc.render.resolution_y = 1100, 1100
sc.render.filepath = os.path.join(out_dir, "closeup.png")
bpy.ops.render.render(write_still=True)
print("RESULT closeup", sc.render.filepath)

# -- the masks as one UV picture -------------------------------------------------
R = 4096


def px(name):
    img = load(name)
    a = np.empty(R * R * 4, np.float32)
    img.pixels.foreach_get(a)
    return a.reshape(R, R, 4)[:, :, 0]


lay = me.uv_layers["UVMap"].data
co = np.empty(len(lay) * 2, np.float32)
lay.foreach_get("uv", co)
co = co.reshape(-1, 2)
v0, v1 = co[:, 1].min(), co[:, 1].max()
r0, r1 = max(int(v0 * R) - 12, 0), min(int(v1 * R) + 12, R)
img = np.ones((R, R, 3), np.float32) * np.array(lin("#161B24"))      # outside the island
# the island: everything the grid covers (black or white squares)
gb, gw = px("gingham_black"), px("gingham_white")
inside = np.clip(gb + gw, 0, 1)
base = np.array(CREAM)
img = img * (1 - inside[..., None]) + base * inside[..., None]
for name, col, k in (("gingham_black", NAVY, 0.88), ("waistband", NAVY, 1.0),
                     ("trim", INK, 1.0), ("stitch", THREAD, 1.0)):
    m = np.clip(px(name) * k, 0, 1)[..., None]
    img = img * (1 - m) + np.array(col) * m
img = np.where(img <= 0.0031308, img * 12.92, 1.055 * np.power(np.clip(img, 0, 1), 1 / 2.4) - 0.055)
crop = img[r0:r1]          # sRGB values, as the PNG stores them
H = crop.shape[0]
rgba = np.concatenate([crop, np.ones((H, R, 1), np.float32)], 2)
out_img = bpy.data.images.new("uv_masks", R, H, alpha=True)
out_img.colorspace_settings.name = "sRGB"
out_img.pixels.foreach_set(rgba.reshape(-1).astype(np.float32))
out_img.filepath_raw = os.path.join(out_dir, "uv_masks.png")
out_img.file_format = 'PNG'
out_img.save()
print("RESULT uv_masks", R, H, "v range", round(float(v0), 3), round(float(v1), 3))
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out_dir, "demo.blend"))
