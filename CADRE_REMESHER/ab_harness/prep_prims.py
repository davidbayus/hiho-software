import bpy, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ab_common import *
S = args_after_dashes()[0]
def save(o, name):
    bpy.context.view_layer.update()
    v, f = world_verts_faces(o); write_obj(os.path.join(S, f'input/{name}_ref_world.obj'), v, f)
    bpy.data.libraries.write(os.path.join(S, f'input/{name}.blend'), {o, o.data})
clear_scene()
bpy.ops.mesh.primitive_cube_add(); save(bpy.context.active_object, 'cube')
bpy.ops.mesh.primitive_grid_add(x_subdivisions=20, y_subdivisions=20); o = bpy.context.active_object
for v in o.data.vertices: v.co.z = 0.3 * (v.co.x ** 2 - v.co.y ** 2)
save(o, 'saddle')
bpy.ops.mesh.primitive_torus_add(major_segments=96, minor_segments=32); save(bpy.context.active_object, 'torus')
bpy.ops.mesh.primitive_cylinder_add(vertices=64, depth=2); o = bpy.context.active_object
o.rotation_euler = (0.4, 0.2, 0.9); o.scale = (1, 0.6, 1.3); o.location = (3, 1, 0)
save(o, 'cyl_rot')
