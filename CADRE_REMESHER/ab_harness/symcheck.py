import bpy, os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ab_common import *
from mathutils import Vector
from mathutils.bvhtree import BVHTree
W = args_after_dashes()[0]
for code in args_after_dashes()[1:]:
    clear_scene()
    ob = append_objects(os.path.join(W, 'input', code + '.blend'))[0]
    me = ob.data
    co = np.empty(len(me.vertices) * 3); me.vertices.foreach_get('co', co); co = co.reshape(-1, 3)
    sc = np.abs(np.array(ob.matrix_world.to_scale()))
    step = max(1, len(co) // 3000)
    sub = co[::step]
    kd = KDTree(len(co[::7]))
    for i, p in enumerate(co[::7]): kd.insert(p, i)
    kd.balance()
    d = np.array([kd.find((-p[0], p[1], p[2]))[2] for p in sub]) * float(sc.mean())
    diag = float(np.linalg.norm((co.max(0) - co.min(0)) * sc))
    score = float((d < 0.01 * diag).mean())
    xr = (co[:, 0].min(), co[:, 0].max())
    straddles = xr[0] < -0.2 * (xr[1] - xr[0]) and xr[1] > 0.2 * (xr[1] - xr[0])
    meta = json.load(open(os.path.join(W, 'input', code + '.json')))
    meta['sym_score'] = round(score, 3); meta['sym'] = 'X' if (score > 0.95 and straddles) else ''
    json.dump(meta, open(os.path.join(W, 'input', code + '.json'), 'w'))
    print("AB SYM", code, "scale", [round(float(x), 3) for x in ob.matrix_world.to_scale()], "local x range", [round(float(x), 3) for x in xr], "score", round(score, 3), "->", repr(meta['sym']))
