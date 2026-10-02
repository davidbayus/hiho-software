"""Parametrised replica of Quadre's pipeline for experiments (the shipped operator stays untouched).

blender -b --factory-startup --python exp_quadre.py -- <quadre_parent_dir> <input.blend> <outdir> <name> key=val ...
  target=5000 sym=X prep=voxel|collapse|none prep_tris=80000 presmooth=0
  sharp=35 (-1 = no angle features; symmetry/open borders are always features)
  minchain=0 (drop angle-feature chains shorter than this many edges)
  K=0.5 flow=SIMPLE satsuma=DEFAULT qr.<field>=<value>
  field=engine|custom   post=none|<spec>   (see exp_field.py / exp_post.py)
"""
import bpy, bmesh, os, sys, time, math, shutil, json
import mathutils
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ab_common import *

a = args_after_dashes()
src_dir, in_blend, outdir, name = a[0], a[1], a[2], a[3]
P = dict(target='5000', sym='X', prep='voxel', prep_tris='80000', presmooth='0', sharp='35',
         minchain='0', K='0.5', flow='SIMPLE', satsuma='DEFAULT', field='engine', post='none',
         remesh='1')
qr_over = {}
for kv in a[4:]:
    k, v = kv.split('=', 1)
    if k.startswith('qr.'):
        qr_over[k[3:]] = v
    else:
        P[k] = v
os.makedirs(outdir, exist_ok=True)
sys.path.insert(0, src_dir)
from quadre.lib import Quadwild, flow_config_files, satsuma_config_files
from quadre.lib.data import create_default_QRParameters
from quadre.util import bisect, exporter, importer
import quadre.lib as qlib

T = {}
t_all = time.time()
clear_scene()
src = append_objects(in_blend)[0]
only_select(src)
location = src.location.copy()
src_tris = sum(len(p.vertices) - 2 for p in src.data.polygons)

# ---------- prepared (simplified) full mesh, cached ----------
cache_dir = os.path.join(outdir, '_cache'); os.makedirs(cache_dir, exist_ok=True)
tag = os.path.splitext(os.path.basename(in_blend))[0]
cache = os.path.join(cache_dir, f"{tag}_{P['prep']}_{P['prep_tris']}_s{P['presmooth']}.obj")
t0 = time.time()
if os.path.exists(cache):
    cv, cf = read_obj(cache)
    work = obj_from_pydata('_work', cv, cf)
else:
    work = src.copy(); work.data = src.data.copy(); work.name = '_work'
    bpy.context.scene.collection.objects.link(work)
    only_select(work)
    tris = sum(len(p.vertices) - 2 for p in work.data.polygons)
    want = int(P['prep_tris'])
    if P['prep'] == 'voxel' and tris > 100000:
        area = sum(p.area for p in work.data.polygons)
        voxel = math.sqrt(area * 2.0 / want)
        for _ in range(3):
            mod = work.modifiers.new('v', 'REMESH'); mod.mode = 'VOXEL'; mod.voxel_size = voxel
            bpy.ops.object.modifier_apply(modifier=mod.name)
            if sum(len(p.vertices) - 2 for p in work.data.polygons) <= 100000:
                break
            voxel *= 1.5
    elif P['prep'] == 'collapse' and tris > want:
        mod = work.modifiers.new('d', 'DECIMATE'); mod.decimate_type = 'COLLAPSE'
        mod.ratio = want / tris; mod.use_collapse_triangulate = True
        bpy.ops.object.modifier_apply(modifier=mod.name)
    if int(P['presmooth']) > 0:
        mod = work.modifiers.new('s', 'LAPLACIANSMOOTH'); mod.iterations = int(P['presmooth']); mod.lambda_factor = 0.5
        mod.use_volume_preserve = True
        bpy.ops.object.modifier_apply(modifier=mod.name)
    # rotation + scale applied, location left out (same as the operator)
    M = mathutils.Matrix.LocRotScale(None, src.rotation_euler, src.scale)
    work.data.transform(M)
    work.matrix_world = mathutils.Matrix.Identity(4)
    write_obj(cache, [v.co[:] for v in work.data.vertices], [tuple(p.vertices) for p in work.data.polygons])
T['prep'] = time.time() - t0
prep_tris = sum(len(p.vertices) - 2 for p in work.data.polygons)

mesh_filepath = os.path.join(bpy.app.tempdir, "exp.obj")
qw = Quadwild(mesh_filepath)
bm = bmesh.new(); bm.from_mesh(work.data)
sym_x = 'X' in P['sym']; sym_y = 'Y' in P['sym']
if sym_x or sym_y:
    bisect.bisect_on_axes(bm, sym_x, sym_y, False)

# sharp=auto: detect creases by angle only on the user's own geometry — an
# auto-simplified (voxel) copy is full of fake crease fragments
simplified = os.path.basename(cache).split('_')[-3] == 'voxel' and prep_tris != src_tris
if P['sharp'] == 'auto':
    P['sharp'] = '-1' if simplified else '35'
SHARP = float(P['sharp'])
bm.edges.ensure_lookup_table()
angle_edges = []
for e in bm.edges:
    if e.is_boundary:
        e.smooth = False
    elif SHARP > 0 and len(e.link_faces) == 2 and math.degrees(e.calc_face_angle(0)) > SHARP:
        e.smooth = False
        angle_edges.append(e)
    else:
        e.smooth = True
# optional: drop short isolated feature chains (connected components of angle edges)
minchain = int(P['minchain'])
if minchain > 0 and angle_edges:
    aset = set(angle_edges); seen = set(); dropped = 0
    for e0 in angle_edges:
        if e0 in seen:
            continue
        comp = []; stack = [e0]
        while stack:
            e = stack.pop()
            if e in seen:
                continue
            seen.add(e); comp.append(e)
            for v in e.verts:
                for e2 in v.link_edges:
                    if e2 in aset and e2 not in seen:
                        stack.append(e2)
        if len(comp) < minchain:
            for e in comp:
                e.smooth = True
            dropped += len(comp)
    print(f"AB minchain dropped {dropped} of {len(angle_edges)} angle-feature edges")
bmesh.ops.triangulate(bm, faces=bm.faces, quad_method='SHORT_EDGE', ngon_method='BEAUTY')
bm.faces.index_update()
exporter.export_mesh(bm, mesh_filepath)
nsharp = exporter.export_sharp_features(bm, qw.sharp_path, SHARP)
half_tris = len(bm.faces)
bm.free()

t0 = time.time()
if P['field'] == 'engine' or P['field'].startswith('custom'):
    qw.remeshAndField(remesh=P['remesh'] == '1', enableSharp=True, sharpAngle=SHARP if SHARP > 0 else 35.0)
T['remesh_field'] = time.time() - t0
if P['field'].startswith('custom'):
    import exp_field
    t0 = time.time()
    exp_field.replace_field(qw, P, work)
    T['custom_field'] = time.time() - t0
t0 = time.time()
ok = qw.trace()
T['trace'] = time.time() - t0
if not ok or not os.path.exists(qw.traced_path):
    print(f"AB FAIL {name} trace"); sys.exit(0)

qr = create_default_QRParameters()
lib_dir = os.path.dirname(os.path.abspath(qlib.__file__))
qr.flow_config_filename = os.path.join(lib_dir, flow_config_files[P['flow']]).encode()
qr.satsuma_config_filename = os.path.join(lib_dir, satsuma_config_files[P['satsuma']]).encode()
for k, v in qr_over.items():
    cur = getattr(qr, k)
    setattr(qr, k, type(cur)(float(v)) if not isinstance(cur, bool) else bool(int(v)))
sym_div = (2 if sym_x else 1) * (2 if sym_y else 1)
target_faces = max(int(P['target']) // sym_div, 1)
rem_tris = sum(1 for l in open(qw.remeshed_path) if l.startswith('f '))
density = math.sqrt(float(P['K']) * rem_tris / target_faces)
density = min(max(density, 0.4), 12.0)
t0 = time.time()
qw.quadrangulate(qr, density, 0, True)
T['quadrangulate'] = time.time() - t0
if not os.path.exists(qw.output_smoothed_path):
    print(f"AB FAIL {name} quadrangulate"); sys.exit(0)

final_mesh = importer.import_mesh(qw.output_smoothed_path)
res = bpy.data.objects.new(name, final_mesh)
bpy.context.scene.collection.objects.link(res)

if P['post'] != 'none':
    import exp_post
    t0 = time.time()
    exp_post.post_process(res, src, work, P, sym_x, sym_y, qw)
    T['post'] = time.time() - t0

res.location = location
if sym_x or sym_y:
    only_select(res)
    mir = res.modifiers.new('m', 'MIRROR'); mir.use_axis[0] = sym_x; mir.use_axis[1] = sym_y
    mir.use_clip = True; mir.merge_threshold = 0.001
    bpy.ops.object.modifier_apply(modifier=mir.name)
bpy.context.view_layer.update()
verts, faces = world_verts_faces(res)
out = os.path.join(outdir, name + ".obj")
write_obj(out, verts, faces)
keep = os.path.join(outdir, f"_work_{name}"); os.makedirs(keep, exist_ok=True)
for fn in os.listdir(bpy.app.tempdir):
    try:
        shutil.copy2(os.path.join(bpy.app.tempdir, fn), os.path.join(keep, fn))
    except Exception:
        pass
T['total'] = time.time() - t_all
print(f"AB OK {name} faces={len(faces)} prep_tris={prep_tris} half_tris={half_tris} sharp={nsharp} rem_tris={rem_tris} density={density:.2f} times={json.dumps({k: round(v, 1) for k, v in T.items()})}")
