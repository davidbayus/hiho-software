"""Custom cross field for QuadWild: curvature-aligned where the shape has a clear
direction, smoothest-possible elsewhere, locked to borders/creases. Pure numpy.

Overwrites <mesh>_rem.rosy (computed on the engine's own remeshed triangles) before trace().
"""
import math, os
import numpy as np


def read_tri_obj(path):
    V, F = [], []
    with open(path) as f:
        for line in f:
            if line.startswith('v '):
                t = line.split(); V.append((float(t[1]), float(t[2]), float(t[3])))
            elif line.startswith('f '):
                F.append([int(tok.split('/')[0]) - 1 for tok in line.split()[1:4]])
    return np.array(V), np.array(F, dtype=np.int64)


def face_adjacency(F):
    """nb[f,k] = face across edge k (verts k,k+1) or -1."""
    nF = len(F)
    a = F; b = np.roll(F, -1, axis=1)
    lo = np.minimum(a, b).ravel(); hi = np.maximum(a, b).ravel()
    key = lo * (F.max() + 1) + hi
    order = np.argsort(key, kind='stable')
    ks = key[order]
    same = ks[1:] == ks[:-1]
    nb = -np.ones(nF * 3, dtype=np.int64)
    i = order[:-1][same]; j = order[1:][same]
    nb[i] = j // 3
    nb[j] = i // 3
    nbk = -np.ones(nF * 3, dtype=np.int64)   # which edge slot on the neighbour
    nbk[i] = j % 3
    nbk[j] = i % 3
    return nb.reshape(nF, 3), nbk.reshape(nF, 3)


def compute_field(V, F, sharp, h, smooth_iters=12, lam=1.0, k0=0.3, cpow=1.0, verbose=True, ref=None, rscale=1.0, rrad=0.35):
    nF = len(F)
    P0, P1, P2 = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
    Nf = np.cross(P1 - P0, P2 - P0)
    A = 0.5 * np.linalg.norm(Nf, axis=1)
    Nf = Nf / np.maximum(2 * A, 1e-20)[:, None]
    # vertex normals (area weighted)
    Nv = np.zeros_like(V)
    for k in range(3):
        np.add.at(Nv, F[:, k], Nf * A[:, None])
    Nv /= np.maximum(np.linalg.norm(Nv, axis=1), 1e-20)[:, None]
    # local frames
    U = P1 - P0
    U /= np.maximum(np.linalg.norm(U, axis=1), 1e-20)[:, None]
    W = np.cross(Nf, U)

    # --- per-face shape operator (Rusinkiewicz 2004): least squares on the 3 edges
    E = [P2 - P1, P0 - P2, P1 - P0]
    DN = [Nv[F[:, 2]] - Nv[F[:, 1]], Nv[F[:, 0]] - Nv[F[:, 2]], Nv[F[:, 1]] - Nv[F[:, 0]]]
    AtA = np.zeros((nF, 3, 3)); Atb = np.zeros((nF, 3))
    for e, dn in zip(E, DN):
        eu = (e * U).sum(1); ev = (e * W).sum(1)
        du = (dn * U).sum(1); dv = (dn * W).sum(1)
        # unknowns (a, b, c):  [a b; b c] [eu ev]^T = [du dv]^T
        r1 = np.stack([eu, ev, np.zeros(nF)], 1)
        r2 = np.stack([np.zeros(nF), eu, ev], 1)
        AtA += r1[:, :, None] * r1[:, None, :] + r2[:, :, None] * r2[:, None, :]
        Atb += r1 * du[:, None] + r2 * dv[:, None]
    AtA += np.eye(3)[None] * 1e-12
    abc = np.linalg.solve(AtA, Atb[:, :, None])[:, :, 0]
    a, b, c = abc[:, 0], abc[:, 1], abc[:, 2]
    UU = U[:, :, None] * U[:, None, :]; WW = W[:, :, None] * W[:, None, :]
    UW = U[:, :, None] * W[:, None, :]
    M = a[:, None, None] * UU + b[:, None, None] * (UW + UW.transpose(0, 2, 1)) + c[:, None, None] * WW

    # --- smooth the tensor over the surface (sets the scale the flow listens to)
    nb, nbk = face_adjacency(F)
    has = nb >= 0
    nbc = np.where(has, nb, 0)
    for _ in range(smooth_iters):
        acc = M * A[:, None, None]
        wsum = A.copy()
        for k in range(3):
            wk = A[nbc[:, k]] * has[:, k]
            acc += M[nbc[:, k]] * wk[:, None, None]
            wsum += wk
        M = acc / wsum[:, None, None]

    a2 = np.einsum('fi,fij,fj->f', U, M, U)
    b2 = np.einsum('fi,fij,fj->f', U, M, W)
    c2 = np.einsum('fi,fij,fj->f', W, M, W)
    if ref is not None:
        # curvature measured on the real sculpt at the scale of one quad:
        # how the (smoothed) surface normal turns across a quad-sized step
        kd, RN = ref
        Cc = (P0 + P1 + P2) / 3.0
        step = 0.5 * h * rscale
        rad = rrad * h * rscale
        def nrm(Pts):
            out = np.empty_like(Pts)
            for i in range(len(Pts)):
                hits = kd.find_range(Pts[i], rad)
                if hits:
                    n = RN[[x[1] for x in hits]].sum(0)
                else:
                    n = RN[kd.find(Pts[i])[1]]
                out[i] = n / max(np.linalg.norm(n), 1e-20)
            return out
        dU = (nrm(Cc + step * U) - nrm(Cc - step * U)) / (2 * step)
        dW = (nrm(Cc + step * W) - nrm(Cc - step * W)) / (2 * step)
        a2 = (dU * U).sum(1); c2 = (dW * W).sum(1)
        b2 = 0.5 * ((dU * W).sum(1) + (dW * U).sum(1))
        # light smoothing of the 2x2 tensor in 3D to calm sampling noise
        M = a2[:, None, None] * UU + b2[:, None, None] * (UW + UW.transpose(0, 2, 1)) + c2[:, None, None] * WW
        for _ in range(smooth_iters):
            acc = M * A[:, None, None]
            wsum = A.copy()
            for k in range(3):
                wk = A[nbc[:, k]] * has[:, k]
                acc += M[nbc[:, k]] * wk[:, None, None]
                wsum += wk
            M = acc / wsum[:, None, None]
        a2 = np.einsum('fi,fij,fj->f', U, M, U)
        b2 = np.einsum('fi,fij,fj->f', U, M, W)
        c2 = np.einsum('fi,fij,fj->f', W, M, W)
    theta_c = 0.5 * np.arctan2(2 * b2, a2 - c2)
    aniso = np.sqrt((a2 - c2) ** 2 + 4 * b2 ** 2)          # |k1 - k2|
    kappa = aniso * h                                       # how much more the normal turns one way, per quad
    conf = np.clip(kappa / k0, 0.0, 1.0) ** cpow
    tgt = np.exp(4j * theta_c)

    # --- transport between adjacent faces (4-RoSy: angles x4)
    Pk = [P0, P1, P2]
    rot = np.ones((nF, 3), dtype=np.complex128)
    wgt = np.zeros((nF, 3))
    C = (P0 + P1 + P2) / 3.0
    edge_ang = np.zeros((nF, 3))
    for k in range(3):
        d = Pk[(k + 1) % 3] - Pk[k]
        L = np.linalg.norm(d, axis=1)
        d = d / np.maximum(L, 1e-20)[:, None]
        g = nbc[:, k]
        af = np.arctan2((d * W).sum(1), (d * U).sum(1))
        ag = np.arctan2((d * W[g]).sum(1), (d * U[g]).sum(1))
        edge_ang[:, k] = af
        rot[:, k] = np.exp(4j * (ag - af))                  # u_f expressed in g's frame = u_f * rot
        dist = np.linalg.norm(C - C[g], axis=1)
        wgt[:, k] = np.where(has[:, k], L / np.maximum(dist, 1e-12), 0.0)

    # --- hard-ish constraints: faces on borders / creases follow the edge
    fixed = np.zeros(nF, dtype=bool)
    fix_val = np.zeros(nF, dtype=np.complex128)
    for (_, f, k) in sharp:
        fix_val[f] += np.exp(4j * edge_ang[f, k]); fixed[f] = True
        g = nb[f, k]
        if g >= 0:
            fix_val[g] += np.exp(4j * edge_ang[g, nbk[f, k]]); fixed[g] = True
    for f in range(nF):                                     # open borders are creases too
        for k in range(3):
            if nb[f, k] < 0 and not fixed[f]:
                fix_val[f] += np.exp(4j * edge_ang[f, k]); fixed[f] = True
    mag = np.abs(fix_val)
    fix_val = np.where(mag > 1e-9, fix_val / np.maximum(mag, 1e-9), 1.0)

    An = A / A.mean()
    mass = lam * conf * An
    BIG = 1e3
    mass = np.where(fixed, BIG, mass)
    rhs = np.where(fixed, BIG * fix_val, mass * tgt)
    diag = wgt.sum(1) + mass + 1e-9

    def apply(u):
        out = diag * u
        for k in range(3):
            out -= wgt[:, k] * np.conj(rot[:, k]) * u[nbc[:, k]]
        return out

    # preconditioned conjugate gradient (Hermitian positive definite)
    u = np.where(fixed, fix_val, tgt * conf)
    r = rhs - apply(u)
    z = r / diag
    p = z.copy()
    rz = np.vdot(r, z).real
    r0 = math.sqrt(np.vdot(r, r).real) + 1e-30
    it = 0
    for it in range(4000):
        Ap = apply(p)
        alpha = rz / max(np.vdot(p, Ap).real, 1e-30)
        u += alpha * p
        r -= alpha * Ap
        if math.sqrt(np.vdot(r, r).real) / r0 < 1e-7:
            break
        z = r / diag
        rz_new = np.vdot(r, z).real
        p = z + (rz_new / rz) * p
        rz = rz_new
    theta = np.angle(u) / 4.0
    D = np.cos(theta)[:, None] * U + np.sin(theta)[:, None] * W
    if verbose:
        print(f"AB field: faces={nF} cg_iters={it + 1} fixed={int(fixed.sum())} conf>0.5: {100 * (conf > 0.5).mean():.0f}% h={h:.4f}")
    return D


def replace_field(qw, P, work=None):
    V, F = read_tri_obj(qw.remeshed_path)
    sharp = []
    if os.path.exists(qw.sharp_path):
        lines = open(qw.sharp_path).read().split('\n')
        for l in lines[1:]:
            if l.strip():
                t = l.split(',')
                sharp.append((int(t[0]), int(t[1]), int(t[2])))
    sym_div = (2 if 'X' in P['sym'] else 1) * (2 if 'Y' in P['sym'] else 1)
    area = 0.5 * np.linalg.norm(np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]]), axis=1).sum()
    h = math.sqrt(area / max(int(P['target']) / sym_div, 1))
    ref = None
    if P.get('f_curv', 'mesh') == 'ref' and work is not None:
        from mathutils.kdtree import KDTree
        me = work.data
        n = len(me.vertices)
        co = np.empty(n * 3); me.vertices.foreach_get('co', co); co = co.reshape(-1, 3)
        rn = np.empty(n * 3); me.vertex_normals.foreach_get('vector', rn); rn = rn.reshape(-1, 3)
        kd = KDTree(n)
        for i in range(n):
            kd.insert(co[i], i)
        kd.balance()
        ref = (kd, rn)
    D = compute_field(V, F, sharp, h,
                      smooth_iters=int(P.get('f_iters', 12)), lam=float(P.get('f_lam', 1.0)),
                      k0=float(P.get('f_k0', 0.3)), cpow=float(P.get('f_cpow', 1.0)),
                      ref=ref, rscale=float(P.get('f_rscale', 1.0)), rrad=float(P.get('f_rrad', 0.35)))
    os.replace(qw.field_path, qw.field_path + '.engine')
    with open(qw.field_path, 'w') as f:
        f.write(f"{len(F)}\n4\n")
        for d in D:
            f.write(f"{d[0]:.6f} {d[1]:.6f} {d[2]:.6f} \n")
