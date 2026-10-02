"""Blender's built-in QuadriFlow on a world-space OBJ.
blender -b --factory-startup --python run_quadriflow.py -- <in_world.obj> <out.obj> <target> <sym ''|X>"""
import bpy, os, sys, time, traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ab_common import *
a = args_after_dashes()
src, out, target = a[0], a[1], int(a[2]); sym = a[3] if len(a) > 3 else ''
clear_scene()
v, f = read_obj(src)
ob = obj_from_pydata('qf', v, f)
bpy.context.view_layer.update()
for o in bpy.context.view_layer.objects: o.select_set(False)
ob.select_set(True); bpy.context.view_layer.objects.active = ob
t0 = time.time()
try:
    r = bpy.ops.object.quadriflow_remesh(mode='FACES', target_faces=target, use_mesh_symmetry=bool(sym), use_preserve_sharp=False, use_preserve_boundary=False, smooth_normals=False, seed=0)
except Exception:
    traceback.print_exc(); r = {'EXC'}
res = bpy.context.view_layer.objects.active or ob
print("AB quadriflow", r, round(time.time() - t0, 1), "s faces", len(res.data.polygons))
if 'FINISHED' in r:
    bpy.context.view_layer.update()
    V, F = world_verts_faces(res); write_obj(out, V, F)
    print("AB OK", os.path.basename(out), "faces=%d" % len(F))
