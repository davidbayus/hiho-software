"""Does the engine-in-its-own-process path hold up when things go wrong? Headless.

blender -b --factory-startup --python test_child.py -- <quadre_parent_dir> <scratch dir>

Five cases through the real operator: a normal run, a run with the child
process made unavailable (must fall back inside Blender and give the same
mesh), a child that dies mid-step, Esc during the layouts, and a shape that
hangs the engine (the flat open grid) with the time limit turned down.
Prints one TEST line per case.
"""
import bpy, bmesh, os, sys, time, threading, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ab_common import *

a = args_after_dashes()
src_dir, scratch = a[0], a[1]
os.makedirs(scratch, exist_ok=True)
sys.path.insert(0, src_dir)
import quadre
from quadre import child, operator
quadre.register()


def children_alive():
    if os.name != 'posix':
        return 0
    out = subprocess.run(['pgrep', '-f', 'engine_runner.py'], capture_output=True, text=True).stdout
    return len([l for l in out.split('\n') if l.strip()])


def monkey():
    clear_scene()
    bpy.ops.mesh.primitive_monkey_add()
    ob = bpy.context.active_object
    m = ob.modifiers.new('s', 'SUBSURF'); m.levels = 2
    bpy.ops.object.modifier_apply(modifier=m.name)
    only_select(ob)
    bpy.context.scene.kb_quadre.quad_count = 2000
    bpy.context.scene.kb_quadre.symmetry_x = False
    bpy.context.scene.kb_quadre.symmetry_y = False
    return ob


def flat_grid():
    clear_scene()
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=20, y_subdivisions=20, size=2)
    ob = bpy.context.active_object
    for v in ob.data.vertices:
        v.co.z = 0.3 * v.co.x * v.co.y
    only_select(ob)
    bpy.context.scene.kb_quadre.quad_count = 500
    return ob


def run():
    before = set(bpy.data.objects)
    t0 = time.time()
    try:
        r = bpy.ops.quadre.cleanup()
    except RuntimeError as e:
        # headless, an operator's error report arrives as an exception
        r = {'CANCELLED', str(e).strip()[:150]}
    new = [o for o in bpy.data.objects if o not in before and o.type == 'MESH']
    return r, (new[0] if new else None), time.time() - t0


def signature(ob):
    verts, faces = world_verts_faces(ob)
    return len(faces), round(float(np.abs(verts).sum()), 3)


def report(name, ok, detail):
    print(f"TEST {'PASS' if ok else 'FAIL'} {name}: {detail}")


# 1. normal run, engine in child processes
monkey()
r, ob, dt = run()
normal = signature(ob) if ob else None
report("normal run", 'FINISHED' in r and ob is not None and children_alive() == 0,
       f"{r} {normal} in {dt:.1f}s, children left {children_alive()}")

# 2. child process unavailable: must fall back inside Blender, same mesh
real_runner = child.RUNNER
child.RUNNER = os.path.join(scratch, "no_such_runner.py")
monkey()
r, ob, dt = run()
fallback = signature(ob) if ob else None
report("fallback inside Blender", 'FINISHED' in r and fallback == normal,
       f"{r} {fallback} in {dt:.1f}s (normal run gave {normal})")

# 3. a child that dies mid-step: Blender carries on, plain failure message
dying = os.path.join(scratch, "dying_runner.py")
with open(dying, 'w') as f:
    f.write("import os, sys\nopen(sys.argv[2], 'w').write('ready')\nos._exit(139)\n")
child.RUNNER = dying
monkey()
r, ob, dt = run()
report("engine crash", 'CANCELLED' in r and ob is None, f"{r} in {dt:.1f}s, Blender still here")
child.RUNNER = real_runner

# 4. Esc during the layouts: everything stops at once
monkey()
real_run = operator._Job.run

def run_then_cancel(job):
    def press_esc():
        while job.stage < 2 and not job.done:
            time.sleep(0.01)
        time.sleep(0.2)
        job.cancel_requested = True
    threading.Thread(target=press_esc, daemon=True).start()
    real_run(job)
    run_then_cancel.job = job

operator._Job.run = run_then_cancel
r, ob, dt = run()
operator._Job.run = real_run
job = run_then_cancel.job
time.sleep(0.3)
report("Esc during layouts", 'CANCELLED' in r and job.cancelled and ob is None and children_alive() == 0,
       f"{r} cancelled={job.cancelled} in {dt:.1f}s, children left {children_alive()}")

# 5. the flat open grid hangs the engine: stopped at the time limit
child.TIME_LIMIT = 8.0
flat_grid()
r, ob, dt = run()
time.sleep(0.3)
report("hang stopped by the time limit", 'CANCELLED' in r and ob is None and 7.0 < dt < 20.0 and children_alive() == 0,
       f"{r} in {dt:.1f}s (limit 8s), children left {children_alive()}")
print("TEST DONE")
