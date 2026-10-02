"""Post-process for the engine's quad mesh: square the quads up, turn them to follow
the flow field, and sit every vertex on the ORIGINAL sculpt. Runs on the half mesh
before mirroring (symmetry-plane vertices slide in the plane only)."""
import math, os
import numpy as np
import mathutils
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from exp_field import read_tri_obj


def post_process(res, src, work, P, sym_x, sym_y, qw=None):
    me = res.data
    nV = len(me.vertices)
    V = np.empty(nV * 3); me.vertices.foreach_get('co', V); V = V.reshape(-1, 3).copy()
    polys = [tuple(p.vertices) for p in me.polygons]
    Q = np.array([p for p in polys if len(p) == 4], dtype=np.int64)

    iters = int(P.get('p_iters', 30))
    omega = float(P.get('p_omega', 0.7))
    beta = float(P.get('p_beta', 1.0))        # 0 = just square up, 1 = also turn fully to the field
    size_mix = float(P.get('p_size', 0.0))    # blend quad sizes toward the local average
    proj = P.get('p_proj', 'orig')
    refield = int(P.get('p_refield', 5))

    # --- projection target
    M = mathutils.Matrix.LocRotScale(None, src.rotation_euler, src.scale).to_4x4()
    Minv = M.inverted()
    if proj == 'orig':
        def project(X, idx):
            for i in idx:
                ok, loc, nrm, fi = src.closest_point_on_mesh(Minv @ Vector(X[i]))
                if ok:
                    X[i] = (M @ loc)[:]
    elif proj == 'work':
        wv = [v.co[:] for v in work.data.vertices]
        wb = BVHTree.FromPolygons(wv, [tuple(p.vertices) for p in work.data.polygons])
        def project(X, idx):
            for i in idx:
                loc = wb.find_nearest(Vector(X[i]))[0]
                if loc is not None:
                    X[i] = loc[:]
    else:
        def project(X, idx):
            pass

    # --- field lookup (engine's remeshed triangles + the .rosy actually used)
    field = None
    if beta > 0 and qw is not None and os.path.exists(qw.field_path):
        Vr, Fr = read_tri_obj(qw.remeshed_path)
        L = open(qw.field_path).read().split('\n')[2:]
        D = np.array([[float(x) for x in l.split()] for l in L if l.strip()])
        rb = BVHTree.FromPolygons([tuple(v) for v in Vr], [tuple(int(i) for i in f) for f in Fr])
        field = (rb, D)

    # --- boundary classes
    ecount = {}
    for p in polys:
        n = len(p)
        for k in range(n):
            a, b = p[k], p[(k + 1) % n]
            key = (a, b) if a < b else (b, a)
            ecount[key] = ecount.get(key, 0) + 1
    bverts = set()
    for (a, b), c in ecount.items():
        if c == 1:
            bverts.add(a); bverts.add(b)
    bverts = np.array(sorted(bverts), dtype=np.int64)
    eps = 1e-4
    on_x = np.zeros(nV, dtype=bool); on_y = np.zeros(nV, dtype=bool); pinned = np.zeros(nV, dtype=bool)
    if len(bverts):
        if sym_x:
            on_x[bverts] = np.abs(V[bverts, 0]) < eps
        if sym_y:
            on_y[bverts] = np.abs(V[bverts, 1]) < eps
        pinned[bverts] = ~(on_x[bverts] | on_y[bverts])
    free = np.nonzero(~pinned)[0]

    q_on_plane = (on_x | on_y)[Q].any(1)
    cnt = np.zeros(nV)
    np.add.at(cnt, Q.ravel(), 1.0)
    cnt = np.maximum(cnt, 1.0)
    X = V.copy()
    X0 = X.copy()
    Dq = None
    for it in range(iters):
        A_, B_, C_, D_ = X[Q[:, 0]], X[Q[:, 1]], X[Q[:, 2]], X[Q[:, 3]]
        m = 0.25 * (A_ + B_ + C_ + D_)
        ue = 0.5 * ((B_ - A_) + (C_ - D_))
        ve = 0.5 * ((D_ - A_) + (C_ - B_))
        n = np.cross(ue, ve)
        n /= np.maximum(np.linalg.norm(n, axis=1), 1e-20)[:, None]
        lu = np.linalg.norm(ue, axis=1); lv = np.linalg.norm(ve, axis=1)
        uh = ue / np.maximum(lu, 1e-20)[:, None]
        vh = ve / np.maximum(lv, 1e-20)[:, None]
        # closest orthonormal frame to (uh, vh): rotate the bisectors by 45 degrees
        b1 = uh + vh; b1 /= np.maximum(np.linalg.norm(b1, axis=1), 1e-20)[:, None]
        b2 = np.cross(n, b1)
        tu = (b1 - b2) / math.sqrt(2.0)
        tv = (b1 + b2) / math.sqrt(2.0)
        if field is not None:
            if Dq is None or it % refield == 0:
                rb, D = field
                Dq = np.array([D[rb.find_nearest(Vector(c))[2]] for c in m])
            d1 = Dq - (Dq * n).sum(1)[:, None] * n
            d1 /= np.maximum(np.linalg.norm(d1, axis=1), 1e-20)[:, None]
            d2 = np.cross(n, d1)
            # signed angle from tu to the nearest arm of the cross
            ang = np.arctan2((tu * d2).sum(1), (tu * d1).sum(1))          # angle of tu in the (d1,d2) frame
            delta = -(((ang + np.pi / 4) % (np.pi / 2)) - np.pi / 4)        # rotation taking tu onto the cross
            delta *= np.where(q_on_plane, 1.0, beta)          # quads on the mirror line square up to it fully
            c, s = np.cos(delta)[:, None], np.sin(delta)[:, None]
            tu, tv = c * tu + s * tv, -s * tu + c * tv
        if size_mix > 0:
            # even out sizes: blend each quad's size with the average of the quads around its corners
            accu = np.zeros(nV); accv = np.zeros(nV)
            s_ = np.sqrt(lu * lv)
            np.add.at(accu, Q.ravel(), np.repeat(s_, 4))
            vs = accu / cnt
            sq = vs[Q].mean(1)
            k = (1 - size_mix) + size_mix * sq / np.maximum(s_, 1e-20)
            lu = lu * k; lv = lv * k
        hu = (0.5 * lu)[:, None] * tu
        hv = (0.5 * lv)[:, None] * tv
        tgt = np.zeros_like(X)
        np.add.at(tgt, Q[:, 0], m - hu - hv)
        np.add.at(tgt, Q[:, 1], m + hu - hv)
        np.add.at(tgt, Q[:, 2], m + hu + hv)
        np.add.at(tgt, Q[:, 3], m - hu + hv)
        tgt /= cnt[:, None]
        Xn = X + omega * (tgt - X)
        Xn[pinned] = X[pinned]
        Xn[on_x, 0] = 0.0
        Xn[on_y, 1] = 0.0
        X = Xn
        project(X, free)
        X[on_x, 0] = 0.0
        X[on_y, 1] = 0.0
    if iters == 0:
        project(X, free)
        X[on_x, 0] = 0.0
        X[on_y, 1] = 0.0
    me.vertices.foreach_set('co', X.ravel())
    me.update()
    print(f"AB post: iters={iters} moved mean {np.linalg.norm(X - X0, axis=1).mean():.5f}")
