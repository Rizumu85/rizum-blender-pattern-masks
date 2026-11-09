"""Workbench render of the ribbons. blender -b result.blend -P render_view.py -- out.png theta_deg dist"""
import math, sys
import bpy
from mathutils import Vector
a = sys.argv[sys.argv.index("--") + 1:]
out, th, dist = a[0], math.radians(float(a[1])), float(a[2])
sc = bpy.context.scene
sc.render.engine = 'BLENDER_WORKBENCH'
sc.display.shading.light = 'STUDIO'
sc.display.shading.color_type = 'MATERIAL'
sc.render.resolution_x, sc.render.resolution_y = 1000, 700
rib = [o for o in bpy.data.objects if o.name.endswith("_Stitches")][0]
rib.hide_render = False
bpy.data.materials["StitchGen_Mask"].diffuse_color = (1, 0.3, 0.05, 1)
sk = bpy.data.objects["Skirt"]
if not sk.data.materials[0]:
    pass
sk.data.materials[0].diffuse_color = (0.85, 0.82, 0.8, 1)
target = Vector((0.205 * math.cos(th), 0.205 * math.sin(th), -0.28))
cam_d = bpy.data.cameras.new("c"); cam_d.lens = 50
cam = bpy.data.objects.new("c", cam_d); sc.collection.objects.link(cam)
cam.location = target + Vector((math.cos(th), math.sin(th), 0.15)).normalized() * dist
cam.rotation_euler = (target - cam.location).to_track_quat('-Z', 'Y').to_euler()
sc.camera = cam
sc.render.filepath = out
bpy.ops.render.render(write_still=True)
