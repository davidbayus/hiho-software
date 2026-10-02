"""Run Quadre (from source, the real operator) on a mesh, headless. World-space OBJ out.

blender -b --factory-startup --python run_quadre.py -- <quadre_parent_dir> <input.blend> <outdir> <tag> <target>:<sym> ...
"""
import bpy, os, sys, time, shutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ab_common import *

a = args_after_dashes()
src_dir, in_blend, outdir, tag = a[0], a[1], a[2], a[3]
runs = a[4:]
os.makedirs(outdir, exist_ok=True)
sys.path.insert(0, src_dir)
import quadre
quadre.register()

for spec in runs:
    parts = spec.split(':')
    target = int(parts[0]); sym = parts[1] if len(parts) > 1 else ''
    name = f"{tag}_q{target}_sym{sym or 'off'}"
    clear_scene()
    src = append_objects(in_blend)[0]
    only_select(src)
    props = bpy.context.scene.kb_quadre
    props.quad_count = target
    props.symmetry_x = 'X' in sym
    props.symmetry_y = 'Y' in sym
    before = set(bpy.data.objects)
    t0 = time.time()
    r = bpy.ops.quadre.cleanup()
    dt = time.time() - t0
    new = [o for o in bpy.data.objects if o not in before and o.type == 'MESH']
    if 'FINISHED' not in r or not new:
        print(f"AB FAIL {name} {r}")
        continue
    res = new[0]
    bpy.context.view_layer.update()
    verts, faces = world_verts_faces(res)
    out = os.path.join(outdir, name + ".obj")
    write_obj(out, verts, faces)
    # keep the engine's intermediate files for study
    keep = os.path.join(outdir, f"_quadre_work_{name}")
    os.makedirs(keep, exist_ok=True)
    for fn in os.listdir(bpy.app.tempdir):
        try:
            shutil.copy2(os.path.join(bpy.app.tempdir, fn), os.path.join(keep, fn))
        except Exception:
            pass
    print(f"AB OK {name} faces={len(faces)} time={dt:.1f}s -> {out}")
