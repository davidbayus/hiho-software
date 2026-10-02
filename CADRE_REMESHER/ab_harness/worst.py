import bpy, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ab_common import *
from mathutils.bvhtree import BVHTree
from mathutils import Vector
a = args_after_dashes()
rv, rf = read_obj(a[0]); rv = np.array(rv)
diag = np.linalg.norm(rv.max(0) - rv.min(0))
for p in a[1:]:
    v, f = read_obj(p)
    b = BVHTree.FromPolygons(v, f)
    d = np.array([b.find_nearest(Vector(x))[3] for x in rv])
    order = np.argsort(-d)[:400]
    c = rv[order].mean(0)
    print("AB WORST", os.path.basename(p), "max‰", round(1000 * d.max() / diag, 1), "count>5‰:", int((1000 * d / diag > 5).sum()), "of", len(d), "worst at", np.round(rv[order[0]], 3), "bbox lo", np.round(rv.min(0), 2), "hi", np.round(rv.max(0), 2))
