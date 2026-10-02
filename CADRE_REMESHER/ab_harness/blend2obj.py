import bpy, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ab_common import *
a = args_after_dashes()
clear_scene(); o = append_objects(a[0])[0]; bpy.context.view_layer.update()
v, f = world_verts_faces(o); write_obj(a[1], v, f); print("AB WROTE", a[1], len(f))
