"""Run Exoside Quad Remesher 1.4 on a mesh, headless, the same way its Blender
bridge does (FBX out -> xremesh -s settings -> FBX in). Writes a world-space OBJ.

blender -b --python run_exoside.py -- <input.blend> <outdir> <tag> <target> <sym ''|X> [adaptive=50] [adapt_count=1]
Several runs can be chained:  ... <target>:<sym>:<adaptive>:<adapt_count>  (repeat)
"""
import bpy, os, sys, time, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ab_common import *

ENGINE = "/Users/Shared/Exoside/QuadRemesher/Datas_Blender/QuadRemesherEngine_1.4/xremesh"

a = args_after_dashes()
in_blend, outdir, tag = a[0], a[1], a[2]
runs = a[3:]
os.makedirs(outdir, exist_ok=True)
# The engine only accepts the bridge's own exchange folder and file names
work = "/var/tmp/Exoside/QuadRemesher/Blender"
os.makedirs(work, exist_ok=True)

clear_scene()
src = append_objects(in_blend)[0]
only_select(src)

fbx_in = os.path.join(work, "inputMesh.fbx")
t0 = time.time()
bpy.ops.export_scene.fbx(filepath=fbx_in, use_selection=True, bake_anim=False, global_scale=1,
                         apply_unit_scale=False, apply_scale_options='FBX_SCALE_NONE',
                         use_space_transform=False, axis_forward='-X', axis_up='Z')
print(f"AB fbx export {time.time()-t0:.1f}s")

for spec in runs:
    parts = spec.split(':')
    target = int(parts[0]); sym = parts[1] if len(parts) > 1 else ''
    adaptive = float(parts[2]) if len(parts) > 2 else 50.0
    adapt_count = int(parts[3]) if len(parts) > 3 else 1
    name = f"{tag}_exoside_q{target}_sym{sym or 'off'}_ad{int(adaptive)}_ac{adapt_count}"
    fbx_out = os.path.join(work, "retopo.fbx")
    settings = os.path.join(work, "RetopoSettings.txt")
    progress = os.path.join(work, "progress.txt")
    if os.path.exists(fbx_out):
        os.remove(fbx_out)
    with open(settings, 'w') as f:
        f.write('HostApp=Blender\n')
        f.write('HostAppVer=%s\n' % bpy.app.version_string)
        f.write('FileIn="%s"\n' % fbx_in)
        f.write('FileOut="%s"\n' % fbx_out)
        f.write('ProgressFile="%s"\n' % progress)
        f.write("TargetQuadCount=%s\n" % target)
        f.write("CurvatureAdaptivness=%s\n" % adaptive)
        f.write("ExactQuadCount=%d\n" % (not adapt_count))
        f.write("UseVertexColorMap=False\n")
        f.write("UseMaterialIds=0\n")
        f.write("UseIndexedNormals=0\n")
        f.write("AutoDetectHardEdges=1\n")
        if sym:
            f.write('SymAxis=%s\n' % sym)
            f.write("SymLocal=1\n")
    t0 = time.time()
    rc = subprocess.run([ENGINE, "-s", settings]).returncode
    dt = time.time() - t0
    if not os.path.exists(fbx_out):
        print(f"AB FAIL {name} rc={rc}")
        continue
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=fbx_out, global_scale=1, use_manual_orientation=True,
                             axis_forward='-X', axis_up='Z')
    res = [o for o in bpy.data.objects if o not in before and o.type == 'MESH'][0]
    res.matrix_world = src.matrix_world.copy()
    bpy.context.view_layer.update()
    verts, faces = world_verts_faces(res)
    out = os.path.join(outdir, name + ".obj")
    write_obj(out, verts, faces)
    print(f"AB OK {name} faces={len(faces)} engine_time={dt:.1f}s -> {out}")
    bpy.data.objects.remove(res)
