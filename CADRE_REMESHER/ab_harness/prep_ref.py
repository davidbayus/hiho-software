# Reference surface for metrics: the sculpt, collapse-decimated to ~150K tris, in world space.
import bpy, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ab_common import *
S = args_after_dashes()[0]
clear_scene()
src = append_objects(os.path.join(S, 'input/chibi_sculpt_full.blend'))[0]
only_select(src)
t0 = time.time()
mod = src.modifiers.new('d', 'DECIMATE'); mod.decimate_type = 'COLLAPSE'; mod.ratio = 150000 / 2889716; mod.use_collapse_triangulate = True
bpy.ops.object.modifier_apply(modifier=mod.name)
print("AB decimate", time.time() - t0, len(src.data.polygons))
verts, faces = world_verts_faces(src)
write_obj(os.path.join(S, 'input/chibi_ref_150k_world.obj'), verts, faces)
print("AB WROTE ref", len(verts), len(faces))
