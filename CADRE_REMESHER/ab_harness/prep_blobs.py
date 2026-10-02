import bpy, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ab_common import *
S = args_after_dashes()[0]
clear_scene()
parts = []
for loc, r in (((0, 0, 0), 1.0), ((0.9, 0, 0.6), 0.6), ((-0.7, 0.2, 0.8), 0.5), ((0, 0, -1.1), 0.7)):
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=6, radius=r, location=loc)
    parts.append(bpy.context.active_object)
for o in parts: o.select_set(True)
bpy.context.view_layer.objects.active = parts[0]
bpy.ops.object.join()
o = bpy.context.active_object
print("AB blobs tris", len(o.data.polygons))
bpy.context.view_layer.update()
v, f = world_verts_faces(o); write_obj(os.path.join(S, 'input/blobs_ref_world.obj'), v, f)
bpy.data.libraries.write(os.path.join(S, 'input/blobs.blend'), {o, o.data})
