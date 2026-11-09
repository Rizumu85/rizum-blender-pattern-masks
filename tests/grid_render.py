"""Bake the checkerboard of an object, put the black mask on it as a texture
and render it (Workbench, texture colors) from a few sides.

blender -b --factory-startup <file with a grid layer> -P grid_render.py -- <object> <out_dir>
"""
import math
import os
import sys

import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
name, out_dir = argv[0], argv[1]
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pattern_masks as sg  # noqa: E402

sg.register()
os.makedirs(out_dir, exist_ok=True)
ob = bpy.data.objects[name]
for o in bpy.data.objects:
    o.select_set(False)
    if o != ob:
        o.hide_render = True
bpy.context.view_layer.objects.active = ob
ob.select_set(True)
s = ob.stitch_gen
s.output_dir = out_dir
s.resolution = '2048'
s.transparent = False
print("RESULT bake", bpy.ops.stitch_gen.bake())
black = [f for f in os.listdir(out_dir) if f.endswith("_black.png")][0]
img = bpy.data.images.load(os.path.join(out_dir, black))
img.colorspace_settings.name = "Non-Color"

mat = bpy.data.materials.new("CheckPreview")
mat.use_nodes = True
nt = mat.node_tree
tex = nt.nodes.new("ShaderNodeTexImage")
tex.image = img
inv = nt.nodes.new("ShaderNodeInvert")
nt.links.new(tex.outputs["Color"], inv.inputs["Color"])
bsdf = nt.nodes["Principled BSDF"]
nt.links.new(inv.outputs["Color"], bsdf.inputs["Base Color"])
ob.data.materials.clear()
ob.data.materials.append(mat)

sc = bpy.context.scene
sc.render.engine = 'BLENDER_WORKBENCH'
sc.display.shading.light = 'STUDIO'
sc.display.shading.color_type = 'TEXTURE'
sc.render.resolution_x = sc.render.resolution_y = 900
sc.render.film_transparent = False
cam_data = bpy.data.cameras.new("cam")
cam = bpy.data.objects.new("cam", cam_data)
sc.collection.objects.link(cam)
sc.camera = cam
corners = [ob.matrix_world @ Vector(c) for c in ob.bound_box]
center = sum(corners, Vector()) / 8
size = max((c - center).length for c in corners)
cam_data.type = 'ORTHO'
cam_data.ortho_scale = size * 2.2
for label, yaw in (("front", 0.0), ("side", 90.0), ("back", 180.0)):
    a = math.radians(yaw)
    d = Vector((math.sin(a), -math.cos(a), 0.15)).normalized()
    cam.location = center + d * size * 4
    cam.rotation_euler = (center - cam.location).to_track_quat('-Z', 'Y').to_euler()
    sc.render.filepath = os.path.join(out_dir, f"render_{label}.png")
    bpy.ops.render.render(write_still=True)
    print("RESULT rendered", label)
