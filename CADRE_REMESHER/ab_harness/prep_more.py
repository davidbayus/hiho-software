import bpy, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ab_common import *
S = args_after_dashes()[0]
def make_ref(o, name):
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    tmp = bpy.data.objects.new('t', bpy.data.meshes.new_from_object(o.evaluated_get(dg)))
    bpy.context.scene.collection.objects.link(tmp); tmp.matrix_world = o.matrix_world.copy()
    only_select(tmp)
    tris = sum(len(p.vertices) - 2 for p in tmp.data.polygons)
    m = tmp.modifiers.new('t', 'TRIANGULATE'); bpy.ops.object.modifier_apply(modifier=m.name)
    if tris > 160000:
        m = tmp.modifiers.new('d', 'DECIMATE'); m.ratio = 150000 / tris; bpy.ops.object.modifier_apply(modifier=m.name)
    bpy.context.view_layer.update()
    v, f = world_verts_faces(tmp); write_obj(os.path.join(S, f'input/{name}_ref_world.obj'), v, f)
    print("AB ref", name, tris, len(f))
    bpy.data.objects.remove(tmp)
# bucket (from the student bug report; the original is Roundcube.001 by name)
o = bpy.data.objects['Roundcube.001']
print("AB bucket", len(o.data.polygons), [m.type for m in o.modifiers], tuple(o.scale), tuple(o.location))
make_ref(o, 'bucket')
bpy.data.libraries.write(os.path.join(S, 'input/bucket.blend'), {o, o.data})
# suzanne subdiv 3 (applied), slightly off-origin + scaled to exercise transforms
bpy.ops.mesh.primitive_monkey_add()
mk = bpy.context.active_object
m = mk.modifiers.new('s', 'SUBSURF'); m.levels = 3; bpy.ops.object.modifier_apply(modifier=m.name)
mk.location = (1.0, 0.5, 2.0); mk.scale = (1.5, 1.5, 1.5)
make_ref(mk, 'suzanne')
bpy.data.libraries.write(os.path.join(S, 'input/suzanne.blend'), {mk, mk.data})
print("AB done")
