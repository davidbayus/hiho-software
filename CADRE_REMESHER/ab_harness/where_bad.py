"""Where do a result's bad corners sit? plain python3 + numpy.
usage: where_bad.py <result.obj> [more.obj ...]"""
import sys, numpy as np
def read_obj(path):
    V, F = [], []
    for line in open(path):
        if line.startswith('v '):
            t = line.split(); V.append((float(t[1]), float(t[2]), float(t[3])))
        elif line.startswith('f '):
            F.append(tuple(int(tok.split('/')[0]) - 1 for tok in line.split()[1:]))
    return np.array(V), F
def ang(u, v):
    c = (u * v).sum(1) / np.maximum(np.linalg.norm(u, axis=1) * np.linalg.norm(v, axis=1), 1e-20)
    return np.degrees(np.arccos(np.clip(c, -1, 1)))
for path in sys.argv[1:]:
    V, F = read_obj(path)
    Q = np.array([f for f in F if len(f) == 4])
    nV = len(V)
    eu = {}
    for f in F:
        n = len(f)
        for k in range(n):
            a, b = f[k], f[(k + 1) % n]
            key = (a, b) if a < b else (b, a)
            eu[key] = eu.get(key, 0) + 1
    E = np.array(list(eu.keys()))
    val = np.bincount(E.ravel(), minlength=nV)
    border = np.zeros(nV, bool)
    for (a, b), c in eu.items():
        if c == 1: border[a] = border[b] = True
    pole = (~border) & (val != 4)
    # graph distance (in edges) from every vertex to nearest border vertex / pole
    adj = [[] for _ in range(nV)]
    for a, b in eu.keys(): adj[a].append(b); adj[b].append(a)
    def bfs(seed):
        d = np.full(nV, 99); d[seed] = 0; cur = list(np.nonzero(seed)[0]); k = 0
        while cur and k < 6:
            k += 1; nxt = []
            for v in cur:
                for w in adj[v]:
                    if d[w] > k: d[w] = k; nxt.append(w)
            cur = nxt
        return d
    db = bfs(border); dp = bfs(pole)
    A, B, C, D = (V[Q[:, i]] for i in range(4))
    e0, e1, e2, e3 = B - A, C - B, D - C, A - D
    corner = np.stack([ang(e0, -e3), ang(e1, -e0), ang(e2, -e1), ang(e3, -e2)], 1)   # at A,B,C,D
    dev = np.abs(corner - 90)
    cv = Q   # vertex of each corner
    bad = dev > 45
    el = np.linalg.norm(V[E[:, 0]] - V[E[:, 1]], axis=1).mean()
    xplane = np.abs(V[:, 0] - 0.5 * (V[:, 0].max() + V[:, 0].min())) < 0.05 * el
    print(f"\n== {path.split('/')[-1]}  quads={len(Q)} verts={nV} border_v={int(border.sum())} poles={int(pole.sum())} mean_dev={dev.mean():.2f} bad%={100*bad.mean():.2f}")
    def row(name, mask_v):
        m = mask_v[cv]
        n = m.sum()
        if n == 0: print(f"   {name:34s} corners=0"); return
        print(f"   {name:34s} corners={int(n):6d} ({100*n/m.size:5.1f}%)  mean_dev={dev[m].mean():5.2f}  bad%={100*bad[m].mean():5.2f}  share_of_bad={100*bad[m].sum()/max(bad.sum(),1):5.1f}%  share_of_dev={100*dev[m].sum()/dev.sum():5.1f}%")
    row("on border", db == 0)
    row("1 edge from border", db == 1)
    row("2 edges from border", db == 2)
    row("3+ from border", db >= 3)
    row("at pole", dp == 0)
    row("1 edge from pole", dp == 1)
    row("2 from pole", dp == 2)
    row("far from poles+borders", (dp >= 3) & (db >= 3))
    row("near centre x-plane", xplane)
