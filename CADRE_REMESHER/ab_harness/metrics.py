"""Quad-mesh quality metrics. Runs inside Blender (numpy + mathutils).

blender -b --factory-startup --python metrics.py -- <ref_world.obj> <out.json> <result.obj> [<result.obj> ...]
"""
import bpy, os, sys, json, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ab_common import *
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree


def pct(a, p):
    return float(np.percentile(a, p)) if len(a) else 0.0


class Ref:
    def __init__(self, path):
        verts, faces = read_obj(path)
        self.verts = np.array(verts)
        self.bvh = BVHTree.FromPolygons(verts, faces)
        ob = obj_from_pydata('_ref', verts, faces)
        me = ob.data
        n = np.empty(len(me.vertices) * 3)
        me.vertex_normals.foreach_get('vector', n)
        self.vnormals = n.reshape(-1, 3)
        self.kd = KDTree(len(verts))
        for i, v in enumerate(verts):
            self.kd.insert(v, i)
        self.kd.balance()
        self.diag = float(np.linalg.norm(self.verts.max(0) - self.verts.min(0)))
        bpy.data.objects.remove(ob)

    def smooth_normal(self, p, radius):
        hits = self.kd.find_range(p, radius)
        if not hits:
            hits = [self.kd.find(p)]
        n = np.zeros(3)
        for _, idx, _ in hits:
            n += self.vnormals[idx]
        L = np.linalg.norm(n)
        return n / L if L > 0 else n


def metrics(path, ref):
    verts, faces = read_obj(path)
    V = np.array(verts)
    nV = len(V)
    out = {'file': os.path.basename(path), 'verts': nV, 'faces': len(faces)}
    quads = [f for f in faces if len(f) == 4]
    out['quads'] = len(quads)
    out['tris'] = sum(1 for f in faces if len(f) == 3)
    out['ngons'] = sum(1 for f in faces if len(f) > 4)
    Q = np.array(quads, dtype=np.int64)

    # --- edges, valence, boundaries
    edge_faces = {}
    for fi, f in enumerate(faces):
        n = len(f)
        for k in range(n):
            a, b = f[k], f[(k + 1) % n]
            key = (a, b) if a < b else (b, a)
            edge_faces.setdefault(key, []).append(fi)
    E = np.array(list(edge_faces.keys()), dtype=np.int64)
    val = np.bincount(E.ravel(), minlength=nV)
    boundary_v = np.zeros(nV, dtype=bool)
    nb = 0
    nonmanifold = 0
    for (a, b), fl in edge_faces.items():
        if len(fl) == 1:
            boundary_v[a] = boundary_v[b] = True
            nb += 1
        elif len(fl) > 2:
            nonmanifold += 1
    out['boundary_edges'] = nb
    out['nonmanifold_edges'] = nonmanifold
    interior = ~boundary_v
    vi = val[interior]
    out['val3'] = int((vi == 3).sum())
    out['val5'] = int((vi == 5).sum())
    out['val6plus'] = int((vi >= 6).sum())
    out['val2'] = int((vi <= 2).sum())
    out['singular'] = int((vi != 4).sum())
    out['singular_pct'] = 100.0 * out['singular'] / max(len(vi), 1)

    # --- edge lengths
    el = np.linalg.norm(V[E[:, 0]] - V[E[:, 1]], axis=1)
    out['edge_mean'] = float(el.mean())
    out['edge_cv'] = float(el.std() / el.mean())
    out['edge_p5_over_mean'] = pct(el, 5) / float(el.mean())
    out['edge_p95_over_mean'] = pct(el, 95) / float(el.mean())

    # --- per-quad shape
    A, B, C, D = V[Q[:, 0]], V[Q[:, 1]], V[Q[:, 2]], V[Q[:, 3]]
    e0, e1, e2, e3 = B - A, C - B, D - C, A - D
    l0, l1, l2, l3 = (np.linalg.norm(e, axis=1) for e in (e0, e1, e2, e3))
    su = 0.5 * (l0 + l2)
    sv = 0.5 * (l1 + l3)
    aspect = np.maximum(su, sv) / np.maximum(np.minimum(su, sv), 1e-12)
    out['aspect_mean'] = float(aspect.mean())
    out['aspect_p95'] = pct(aspect, 95)
    out['aspect_gt2_pct'] = float(100.0 * (aspect > 2).mean())

    def ang(u, v):
        c = (u * v).sum(1) / np.maximum(np.linalg.norm(u, axis=1) * np.linalg.norm(v, axis=1), 1e-20)
        return np.degrees(np.arccos(np.clip(c, -1, 1)))
    corner = np.concatenate([ang(e0, -e3), ang(e1, -e0), ang(e2, -e1), ang(e3, -e2)])
    dev = np.abs(corner - 90.0)
    out['angle_dev_mean'] = float(dev.mean())
    out['angle_dev_p95'] = pct(dev, 95)
    out['angle_bad_pct'] = float(100.0 * (dev > 45).mean())

    n1 = np.cross(B - A, C - A)
    n2 = np.cross(C - A, D - A)
    area = 0.5 * (np.linalg.norm(n1, axis=1) + np.linalg.norm(n2, axis=1))
    warp = ang(n1, n2)
    out['warp_mean_deg'] = float(warp.mean())
    out['area_cv'] = float(area.std() / area.mean())

    # --- local uniformity: area ratio of the two faces across each interior edge
    face_area = {}
    qi = 0
    for fi, f in enumerate(faces):
        if len(f) == 4:
            face_area[fi] = area[qi]
            qi += 1
    ratios = []
    for fl in edge_faces.values():
        if len(fl) == 2 and fl[0] in face_area and fl[1] in face_area:
            a1, a2 = face_area[fl[0]], face_area[fl[1]]
            ratios.append(max(a1, a2) / max(min(a1, a2), 1e-20))
    ratios = np.array(ratios)
    out['nbr_area_ratio_mean'] = float(ratios.mean())
    out['nbr_area_ratio_p95'] = pct(ratios, 95)

    # --- fidelity (per mille of bbox diagonal)
    d_fwd = np.array([ref.bvh.find_nearest(Vector(p))[3] for p in V])
    out['fid_fwd_mean_pm'] = float(1000 * d_fwd.mean() / ref.diag)
    out['fid_fwd_max_pm'] = float(1000 * d_fwd.max() / ref.diag)
    res_bvh = BVHTree.FromPolygons([tuple(v) for v in V], faces)
    step = max(1, len(ref.verts) // 30000)
    d_rev = np.array([res_bvh.find_nearest(Vector(p))[3] for p in ref.verts[::step]])
    out['fid_rev_mean_pm'] = float(1000 * d_rev.mean() / ref.diag)
    out['fid_rev_p99_pm'] = float(1000 * pct(d_rev, 99) / ref.diag)
    out['fid_rev_max_pm'] = float(1000 * d_rev.max() / ref.diag)

    # --- curvature alignment: do the quad's two axes follow the principal
    # curvature directions of the sculpt (measured at the quad's own scale)?
    m_ab, m_bc, m_cd, m_da = 0.5 * (A + B), 0.5 * (B + C), 0.5 * (C + D), 0.5 * (D + A)
    radius = 0.35 * out['edge_mean']
    def normals(P):
        return np.array([ref.smooth_normal(Vector(p), radius) for p in P])
    N_ab, N_bc, N_cd, N_da = normals(m_ab), normals(m_bc), normals(m_cd), normals(m_da)
    u = m_bc - m_da
    v = m_cd - m_ab
    Lu = np.linalg.norm(u, axis=1); Lv = np.linalg.norm(v, axis=1)
    uh = u / Lu[:, None]; vh = v / Lv[:, None]
    e1v = uh
    cosphi = (vh * e1v).sum(1)
    e2v = vh - cosphi[:, None] * e1v
    sinphi = np.linalg.norm(e2v, axis=1)
    ok = sinphi > 0.2
    e2v = e2v / np.maximum(sinphi, 1e-9)[:, None]
    Dn_e1 = (N_bc - N_da) / Lu[:, None]
    Dn_v = (N_cd - N_ab) / Lv[:, None]
    Dn_e2 = (Dn_v - cosphi[:, None] * Dn_e1) / np.maximum(sinphi, 1e-9)[:, None]
    S11 = (Dn_e1 * e1v).sum(1); S12 = (Dn_e1 * e2v).sum(1)
    S21 = (Dn_e2 * e1v).sum(1); S22 = (Dn_e2 * e2v).sum(1)
    Soff = 0.5 * (S12 + S21)
    theta = 0.5 * np.degrees(np.arctan2(2 * Soff, S11 - S22))
    mis = np.abs(theta) % 90.0
    mis = np.minimum(mis, 90.0 - mis)                       # 0..45 deg
    aniso = np.sqrt((S11 - S22) ** 2 + 4 * Soff ** 2)       # |k1-k2|
    w = aniso * area * ok
    out['curv_misalign_wmean_deg'] = float((mis * w).sum() / max(w.sum(), 1e-20))
    strong = ok & (aniso * np.sqrt(area) > 0.15)            # normal turns > ~9 deg more one way than the other
    out['curv_strong_quads_pct'] = float(100.0 * strong.mean())
    out['curv_misalign_strong_mean_deg'] = float(mis[strong].mean()) if strong.any() else 0.0
    out['curv_misalign_strong_gt20_pct'] = float(100.0 * (mis[strong] > 20).mean()) if strong.any() else 0.0
    if len(quads) == len(faces):
        np.save(path + '.mis.npy', np.where(strong, mis, -1.0))

    # --- poly-chords (quad strips): union opposite edges of every quad
    eid = {k: i for i, k in enumerate(edge_faces.keys())}
    parent = list(range(len(eid)))
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    qedges = []
    for f in quads:
        ids = []
        for k in range(4):
            a, b = f[k], f[(k + 1) % 4]
            ids.append(eid[(a, b) if a < b else (b, a)])
        qedges.append(ids)
        for x, y in ((ids[0], ids[2]), (ids[1], ids[3])):
            rx, ry = find(x), find(y)
            if rx != ry:
                parent[rx] = ry
    chord_len = {}
    selfcross = 0
    for ids in qedges:
        c1, c2 = find(ids[0]), find(ids[1])
        chord_len[c1] = chord_len.get(c1, 0) + 1
        chord_len[c2] = chord_len.get(c2, 0) + 1
        if c1 == c2:
            selfcross += 1
    cl = np.array(sorted(chord_len.values()))
    out['chords'] = int(len(cl))
    out['chord_len_median'] = float(np.median(cl)) if len(cl) else 0
    out['chord_len_max'] = int(cl.max()) if len(cl) else 0
    out['chord_longest_share_pct'] = float(100.0 * cl.max() / max(cl.sum(), 1)) if len(cl) else 0
    out['selfcross_faces_pct'] = float(100.0 * selfcross / max(len(quads), 1))

    # --- mirror symmetry of the topology (X): vertex has a partner at -x
    kd = KDTree(nV)
    for i, p in enumerate(V):
        kd.insert(p, i)
    kd.balance()
    cx = 0.5 * (ref.verts[:, 0].max() + ref.verts[:, 0].min())
    tol = 0.1 * out['edge_mean']
    hit = 0
    for p in V:
        if kd.find((2 * cx - p[0], p[1], p[2]))[2] < tol:
            hit += 1
    out['mirror_partner_pct'] = 100.0 * hit / nV
    return out


if __name__ == '__main__':
    a = args_after_dashes()
    ref = Ref(a[0])
    results = []
    for p in a[2:]:
        try:
            m = metrics(p, ref)
            results.append(m)
            print("AB METRICS", json.dumps(m))
        except Exception as e:
            import traceback; traceback.print_exc()
            print("AB METRICS FAIL", p, e)
    with open(a[1], 'w') as f:
        json.dump(results, f, indent=1)
