"""Render the grid layout figure for the docs: one open, flared panel (a
quarter of a skirt) with the grid laid from its waist, once with Follow
Loops and once with Unrolled.

blender -b --factory-startup -P docs/source/make_grid_figs.py -- <out_dir> [<samples>]

Writes <out_dir>/grid_loops.png and grid_unrolled.png (transparent).
"""
import math
import os
import sys

import bpy
import bmesh
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
out_dir = os.path.abspath(argv[0])
samples = int(argv[1]) if len(argv) > 1 else 64
repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, repo)
import rizum_pattern_masks as sg  # noqa: E402

os.makedirs(out_dir, exist_ok=True)
COLS, ROWS, LENGTH = 60, 24, 0.30
SPAN = math.radians(100)                       # the panel covers 100 degrees of the skirt


def lin(h):
    c = [int(h[i:i + 2], 16) / 255.0 for i in (1, 3, 5)]
    return tuple(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c)


def pos(t, z):
    """t in 0..1 across the panel, z down from the waist (0)."""
    theta = -SPAN / 2 + SPAN * t - math.pi / 2
    r = 0.10 + 0.10 * (-z / LENGTH)
    d = 0.22 * min(1.0, (-z / LENGTH) ** 1.25)
    r *= 1.0 - d * 0.5 * (1.0 + math.cos(5 * (theta + math.pi / 2) * 2 * math.pi / SPAN * 0.9))
    return (r * math.cos(theta), r * math.sin(theta), z)


bpy.ops.wm.read_factory_settings(use_empty=True)
sg.register()
bm = bmesh.new()
uvl = bm.loops.layers.uv.new("UVMap")
grid = [[bm.verts.new(pos(i / COLS, -LENGTH * j / ROWS)) for i in range(COLS + 1)] for j in range(ROWS + 1)]
for j in range(ROWS):
    for i in range(COLS):
        f = bm.faces.new([grid[j][i], grid[j + 1][i], grid[j + 1][i + 1], grid[j][i + 1]])
        f.smooth = True
bm.normal_update()
bm.faces.ensure_lookup_table()
if bm.faces[0].normal.y > 0:                     # face the camera (front, -y)
    bmesh.ops.reverse_faces(bm, faces=list(bm.faces))
me = bpy.data.meshes.new("Panel")
bm.to_mesh(me)
bm.free()
ob = bpy.data.objects.new("Panel", me)
bpy.context.scene.collection.objects.link(ob)
mat = bpy.data.materials.new("Cloth")
me.materials.append(mat)
bpy.context.view_layer.objects.active = ob
ob.select_set(True)
# a real unwrap of the piece
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.uv.unwrap(method='CONFORMAL', margin=0.02)
bpy.ops.object.mode_set(mode='OBJECT')

s = ob.stitch_gen
s.live = False
bpy.ops.stitch_gen.grid_add()
g = s.lines[s.line_index]
g.name = "grid"
s.line_index = 0
bpy.ops.object.mode_set(mode='EDIT')
bmx = bmesh.from_edit_mesh(me)
for e in bmx.edges:
    e.select_set(False)
for v in bmx.verts:
    v.select_set(False)
for e in bmx.edges:
    if e.is_boundary and all(v.co.z > -0.001 for v in e.verts):
        e.select_set(True)
bmx.select_mode = {'EDGE'}
bmx.select_flush_mode()
bmesh.update_edit_mesh(me)
bpy.ops.stitch_gen.path_add()
bpy.ops.object.mode_set(mode='OBJECT')
g.grid_cell, g.grid_wobble = 20.0, 0.0

CREAM, NAVY = lin("#EFE7D8"), lin("#22304A")
mat.use_nodes = True
nt = mat.node_tree
nt.nodes.clear()
outn = nt.nodes.new("ShaderNodeOutputMaterial")
bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
bsdf.inputs["Roughness"].default_value = 0.85
nt.links.new(bsdf.outputs["BSDF"], outn.inputs["Surface"])
tex = nt.nodes.new("ShaderNodeTexImage")
tex.interpolation = 'Cubic'
mix = nt.nodes.new("ShaderNodeMix")
mix.data_type = 'RGBA'
ids = {i.identifier: i for i in mix.inputs}
ids["A_Color"].default_value = CREAM + (1.0,)
ids["B_Color"].default_value = NAVY + (1.0,)
nt.links.new(tex.outputs["Color"], ids["Factor_Float"])
nt.links.new(next(o for o in mix.outputs if o.identifier == "Result_Color"), bsdf.inputs["Base Color"])

sc = bpy.context.scene
sc.render.engine = 'CYCLES'
sc.cycles.samples = samples
sc.cycles.use_denoising = True
sc.render.film_transparent = True
sc.render.resolution_x = sc.render.resolution_y = 1000
sc.view_settings.view_transform = 'Standard'
world = bpy.data.worlds.new("World")
sc.world = world
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.55, 0.57, 0.62, 1.0)
world.node_tree.nodes["Background"].inputs[1].default_value = 0.35
target = Vector((0.0, -0.14, -0.15))
cam_data = bpy.data.cameras.new("Cam")
cam_data.lens = 60
cam = bpy.data.objects.new("Cam", cam_data)
sc.collection.objects.link(cam)
cam.location = (0.0, -1.05, 0.05)
cam.rotation_euler = (target - cam.location).to_track_quat('-Z', 'Y').to_euler()
sc.camera = cam
for name, loc, energy, size in (("Key", (0.8, -1.0, 0.6), 40.0, 0.8),
                                ("Fill", (-0.9, -0.8, 0.1), 14.0, 1.5)):
    ld = bpy.data.lights.new(name, 'AREA')
    ld.energy, ld.size = energy, size
    lo = bpy.data.objects.new(name, ld)
    sc.collection.objects.link(lo)
    lo.location = loc
    lo.rotation_euler = (target - lo.location).to_track_quat('-Z', 'Y').to_euler()
for o in bpy.data.objects:
    if o not in (ob, cam) and o.type == 'MESH':
        o.hide_render = True

masks = os.path.join(out_dir, "grid_masks")
for layout in ("LOOPS", "UNROLLED"):
    os.makedirs(masks, exist_ok=True)
    for f in os.listdir(masks):
        os.remove(os.path.join(masks, f))
    g.grid_layout = layout
    sg.regenerate(ob)
    s.output_dir = masks
    s.resolution = '2048'
    print("RESULT bake", layout, bpy.ops.stitch_gen.bake(), sorted(os.listdir(masks)))
    img = bpy.data.images.load(os.path.join(masks, "Panel_Cloth_grid_black.png"), check_existing=False)
    img.colorspace_settings.name = "Non-Color"
    tex.image = img
    sc.render.filepath = os.path.join(out_dir, f"grid_{layout.lower()}.png")
    bpy.ops.render.render(write_still=True)
    print("RESULT render", sc.render.filepath)
