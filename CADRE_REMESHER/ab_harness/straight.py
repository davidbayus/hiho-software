"""How straight do the edge loops run? For every regular interior vertex (4 edges), the bend of each of the two
loops through it, measured in the surface (edges projected onto the vertex's tangent plane). Degrees; 0 = ruler straight.
Also: how much neighbouring edge lengths along a loop differ (evenness), and quad-size spread.
python3 straight.py <a.obj> <b.obj> ..."""
import sys, numpy as np
def read(path):
    V, F = [], []
    for line in open(path):
        if line.startswith('v '):
            t = line.split(); V.append((float(t[1]), float(t[2]), float(t[3])))
        elif line.startswith('f '):
            F.append([int(tok.split('/')[0]) - 1 for tok in line.split()[1:]])
    return np.array(V), F
def measure(path):
    V, F = read(path)
    Q = np.array([f for f in F if len(f) == 4])
    n = len(V)
    # vertex normals
    fn = np.cross(V[Q[:, 2]] - V[Q[:, 0]], V[Q[:, 3]] - V[Q[:, 1]])
    vn = np.zeros((n, 3))
    for k in range(4): np.add.at(vn, Q[:, k], fn)
    vn /= np.maximum(np.linalg.norm(vn, axis=1), 1e-20)[:, None]
    # around each vertex: for quad (a,b,c,d) at corner b, the edges b->a and b->c are consecutive around b.
    # opposite edges at a valence-4 vertex: order the 4 neighbours cyclically using the quads.
    nxt = {}   # (vertex, neighbour) -> next neighbour around the vertex (one rotation direction)
    cnt = np.zeros(n, int)
    edge_use = {}
    for q in Q:
        for k in range(4):
            v, a, c = q[k], q[(k + 1) % 4], q[(k - 1) % 4]
            nxt[(v, a)] = c
            cnt[v] += 1
            key = (min(v, a), max(v, a)); edge_use[key] = edge_use.get(key, 0) + 1
    border = np.zeros(n, bool)
    for (a, b), c in edge_use.items():
        if c == 1: border[a] = border[b] = True
    bends, uneven = [], []
    for v in range(n):
        if cnt[v] != 4 or border[v]: continue
        start = next(a for (vv, a) in ((v, q) for q in []) ) if False else None
    # build neighbour rings
    first = {}
    for (v, a) in nxt:
        first.setdefault(v, a)
    for v, a0 in first.items():
        if cnt[v] != 4 or border[v]: continue
        ring = [a0]
        ok = True
        for _ in range(3):
            b = nxt.get((v, ring[-1]))
            if b is None: ok = False; break
            ring.append(b)
        if not ok or nxt.get((v, ring[-1])) != a0 or len(set(ring)) != 4: continue
        N = vn[v]
        E = V[ring] - V[v]
        T = E - (E @ N)[:, None] * N
        L = np.linalg.norm(T, axis=1)
        if (L < 1e-12).any(): continue
        T /= L[:, None]
        for i in (0, 1):
            c = float(np.clip(-(T[i] @ T[i + 2]), -1, 1))
            bends.append(np.degrees(np.arccos(c)))
            l1, l2 = np.linalg.norm(E[i]), np.linalg.norm(E[i + 2])
            uneven.append(abs(l1 - l2) / (0.5 * (l1 + l2)))
    bends = np.array(bends); uneven = np.array(uneven)
    A = 0.5 * (np.linalg.norm(np.cross(V[Q[:, 1]] - V[Q[:, 0]], V[Q[:, 2]] - V[Q[:, 0]]), axis=1) + np.linalg.norm(np.cross(V[Q[:, 2]] - V[Q[:, 0]], V[Q[:, 3]] - V[Q[:, 0]]), axis=1))
    return dict(quads=len(Q), bend_mean=bends.mean(), bend_p90=np.percentile(bends, 90), bend_gt15=100 * (bends > 15).mean(), uneven=100 * uneven.mean(), area_cv=A.std() / A.mean())
if __name__ == '__main__':
    for p in sys.argv[1:]:
        m = measure(p)
        print(f"{p.split('/')[-1][:44]:44s} quads {m['quads']:6d}  loop bend mean {m['bend_mean']:5.2f}  p90 {m['bend_p90']:5.1f}  >15deg {m['bend_gt15']:5.1f}%  step unevenness {m['uneven']:5.1f}%  size spread {m['area_cv']:.2f}")
