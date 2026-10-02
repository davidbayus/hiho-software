"""Turn one object of an open .blend into a benchmark input.
blender -b <src.blend> --python bench_prep.py -- <object name | @hardsurface> <code> <workdir> [note]
Writes <workdir>/input/<code>.blend (one plain mesh object, modifiers applied, transform kept),
<code>_ref_world.obj (<=150K tris) and <code>.json (tris, symmetry verdict)."""
import bpy, os, sys, json, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ab_common import *
from mathutils import Vector
from mathutils.bvhtree import BVHTree
a = args_after_dashes()
name, code, W = a[0], a[1], a[2]
note = a[3] if len(a) > 3 else ''
if name == '@hardsurface':
    clear_scene()
    bpy.ops.mesh.primitive_cube_add(size=2); body = bpy.context.active_object; body.scale = (1.6, 1.0, 0.5)
    bpy.ops.object.transform_apply(scale=True)
    cutters = []
    for x in (-0.9, 0.9):
        bpy.ops.mesh.primitive_cylinder_add(vertices=64, radius=0.38, depth=3, location=(x, 0, 0)); cutters.append(bpy.context.active_object)
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0.8, 0.35)); c = bpy.context.active_object; c.scale = (1.2, 1.0, 0.5); cutters.append(c)
    bpy.ops.mesh.primitive_cylinder_add(vertices=64, radius=0.55, depth=1.2, location=(0, -0.2, 0.6)); boss = bpy.context.active_object
    bpy.context.view_layer.objects.active = body
    for c in cutters:
        m = body.modifiers.new('b', 'BOOLEAN'); m.operation = 'DIFFERENCE'; m.object = c; m.solver = 'EXACT'
        bpy.ops.object.modifier_apply(modifier=m.name)
    m = body.modifiers.new('u', 'BOOLEAN'); m.operation = 'UNION'; m.object = boss; m.solver = 'EXACT'
    bpy.ops.object.modifier_apply(modifier=m.name)
    for c in cutters + [boss]: bpy.data.objects.remove(c)
    m = body.modifiers.new('bv', 'BEVEL'); m.width = 0.04; m.segments = 2; m.limit_method = 'ANGLE'; m.angle_limit = math.radians(40)
    bpy.ops.object.modifier_apply(modifier=m.name)
    src = body
else:
    src = bpy.data.objects[name]
    if src.name not in bpy.context.view_layer.objects:
        bpy.context.scene.collection.objects.link(src)
    src.hide_viewport = False
    src.hide_set(False)
bpy.context.view_layer.update()
dg = bpy.context.evaluated_depsgraph_get()
me = bpy.data.meshes.new_from_object(src.evaluated_get(dg), depsgraph=dg)
mw = src.matrix_world.copy()
ob = bpy.data.objects.new(code, me)
bpy.context.scene.collection.objects.link(ob); ob.matrix_world = mw
for a_ in list(me.attributes):
    pass
tris = sum(len(p.vertices) - 2 for p in me.polygons)
os.makedirs(os.path.join(W, 'input'), exist_ok=True)
bpy.data.libraries.write(os.path.join(W, 'input', code + '.blend'), {ob, me})
# reference: triangulated, decimated copy in world space
ref = bpy.data.objects.new('_ref', me.copy()); bpy.context.scene.collection.objects.link(ref); ref.matrix_world = mw
only_select(ref)
if tris > 160000:
    m = ref.modifiers.new('d', 'DECIMATE'); m.ratio = 150000 / tris; m.use_collapse_triangulate = True
else:
    m = ref.modifiers.new('t', 'TRIANGULATE')
bpy.ops.object.modifier_apply(modifier=m.name)
bpy.context.view_layer.update()
V, F = world_verts_faces(ref)
write_obj(os.path.join(W, 'input', code + '_ref_world.obj'), V, F)
# symmetry about the object's own X = 0 plane (what Quadre and Exoside both mirror on)
co = np.empty(len(ref.data.vertices) * 3); ref.data.vertices.foreach_get('co', co); co = co.reshape(-1, 3)
sc = np.array(mw.to_scale())
bvh = BVHTree.FromPolygons([tuple(v) for v in co], [tuple(p.vertices) for p in ref.data.polygons])
diag = float(np.linalg.norm((co.max(0) - co.min(0)) * sc))
step = max(1, len(co) // 4000)
d = np.array([bvh.find_nearest(Vector((-p[0], p[1], p[2])))[3] for p in co[::step]]) * float(sc.mean())
sym_score = float((d < 0.004 * diag).mean())
straddles = co[:, 0].min() < -0.05 * (co[:, 0].max() - co[:, 0].min()) and co[:, 0].max() > 0.05 * (co[:, 0].max() - co[:, 0].min())
meta = {'code': code, 'tris': tris, 'sym_score': round(sym_score, 3), 'sym': 'X' if (sym_score > 0.95 and straddles) else '', 'note': note,
        'dims': [round(x, 3) for x in ob.dimensions], 'parts': None}
json.dump(meta, open(os.path.join(W, 'input', code + '.json'), 'w'))
print("AB PREP", json.dumps(meta))
