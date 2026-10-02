"""Student's path: install the zip with the real installer, press the button in a
real window (modal + worker thread), check the UI stays alive, save the result."""
import bpy, os, sys, time, json, importlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ab_common import *
a = args_after_dashes()
zip_path, in_blend, out_obj, report = a[0], a[1], a[2], a[3]
state = {'phase': 0, 'ticks': 0, 't0': 0.0, 'log': []}

def log(*x):
    state['log'].append(' '.join(str(i) for i in x)); print("AB GUI", *x)

def finish(ok):
    json.dump({'ok': ok, 'log': state['log']}, open(report, 'w'), indent=1)
    bpy.ops.wm.quit_blender()

def step():
    try:
        if state['phase'] == 0:
            r = bpy.ops.extensions.package_install_files(filepath=zip_path, repo='user_default', enable_on_install=True)
            log("install", r)
            state['phase'] = 1
            return 0.5
        if state['phase'] == 1:
            import addon_utils
            mods = [m.__name__ for m in addon_utils.modules() if 'quadre' in m.__name__]
            log("modules", mods, "operator registered:", hasattr(bpy.types, 'QUADRE_OT_cleanup'))
            clear_scene()
            src = append_objects(in_blend)[0]
            only_select(src)
            p = bpy.context.scene.kb_quadre
            p.quad_count = 5000; p.symmetry_x = True
            win = bpy.context.window_manager.windows[0]
            area = [ar for ar in win.screen.areas if ar.type == 'VIEW_3D'][0]
            region = [rg for rg in area.regions if rg.type == 'WINDOW'][0]
            state['before'] = set(bpy.data.objects)
            state['t0'] = time.time()
            with bpy.context.temp_override(window=win, area=area, region=region):
                r = bpy.ops.quadre.cleanup('INVOKE_DEFAULT')
            log("invoke", r)
            state['phase'] = 2
            return 0.05
        if state['phase'] == 2:
            op = bpy.types.QUADRE_OT_cleanup
            cls = bpy.ops.quadre.cleanup.get_rna_type()
            mod = importlib.import_module('bl_ext.user_default.quadre.operator')
            job = mod.QUADRE_OT_cleanup.active_job
            if job is not None:
                state['ticks'] += 1
                state['last_status'] = job.status_line()
                return 0.05
            dt = time.time() - state['t0']
            new = [o for o in bpy.data.objects if o not in state['before'] and o.type == 'MESH']
            log("done in", round(dt, 1), "s; main-thread ticks while working:", state['ticks'], "(", round(state['ticks'] / max(dt, 0.01), 1), "/s ) last status:", state.get('last_status'))
            if not new:
                log("NO RESULT"); finish(False); return None
            res = new[0]
            bpy.context.view_layer.update()
            v, f = world_verts_faces(res); write_obj(out_obj, v, f)
            log("result", res.name, "faces", len(f), "original hidden:", bpy.data.objects[0].hide_get())
            finish(True)
            return None
    except Exception as e:
        import traceback
        log("EXC", traceback.format_exc()); finish(False)
        return None

bpy.app.timers.register(step, first_interval=1.5)
