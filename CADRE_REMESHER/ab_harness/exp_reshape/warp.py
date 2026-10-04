"""
QUADRE — quads that shrink where the shape tightens (prototype).

The engine makes every quad the same size. So between step 1 and the
layouts its working mesh is reshaped: areas where the shape bends tightly
are made bigger, as if inflated. The engine lays its even quads over that
reshaped mesh, and each quad vertex is then carried back to the real shape
through the triangle it sits on. Inflated areas end up with smaller quads.

Pure numpy + mathutils: no bpy, safe on the worker thread.
"""

import math
import os

import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree


def _env(name, default):
    v = os.environ.get('QWARP_' + name)
    return type(default)(float(v)) if v is not None else default


# A quad should not span more than this much turning of the surface (radians)
TURN_PER_QUAD = _env('TURN', 0.45)
# ...but no area is enlarged more than this (in length)
MAX_SCALE = _env('SMAX', 2.0)
SCALE_SMOOTH_ROUNDS = _env('SMOOTH', 3)
ARAP_ROUNDS = _env('ROUNDS', 12)
CG_STEPS = _env('CG', 80)


def stretch_tensors(V, F, D, M, quad_edge):
    """How to stretch the mesh around each vertex, as a 3x3 matrix.

    D: the flow map (one unit direction per triangle). M: the surface's
    bending per triangle as a 3x3 matrix (normal change per unit length).
    The mesh is stretched along each of the flow map's two directions by how
    fast the surface turns along that direction: a quad should not span more
    than TURN_PER_QUAD of turning either way.
    """
    from .flow import _face_adjacency
    P0, P1, P2 = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
    N = np.cross(P1 - P0, P2 - P0)
    area = 0.5 * np.linalg.norm(N, axis=1)
    N = N / np.maximum(2 * area, 1e-20)[:, None]
    f1 = D - (D * N).sum(1)[:, None] * N
    f1 /= np.maximum(np.linalg.norm(f1, axis=1), 1e-20)[:, None]
    f2 = np.cross(N, f1)
    k1 = np.abs(np.einsum('fi,fij,fj->f', f1, M, f1))
    k2 = np.abs(np.einsum('fi,fij,fj->f', f2, M, f2))
    s1 = np.clip(k1 * quad_edge / TURN_PER_QUAD, 1.0, MAX_SCALE)
    s2 = np.clip(k2 * quad_edge / TURN_PER_QUAD, 1.0, MAX_SCALE)
    if _env('ISO', 0):
        s1 = s2 = np.maximum(s1, s2)
    A = (
        N[:, :, None] * N[:, None, :]
        + s1[:, None, None] * f1[:, :, None] * f1[:, None, :]
        + s2[:, None, None] * f2[:, :, None] * f2[:, None, :]
    )
    nb, _ = _face_adjacency(F)
    has = nb >= 0
    nbc = np.where(has, nb, 0)
    for _ in range(SCALE_SMOOTH_ROUNDS):
        acc = A * area[:, None, None]
        wsum = area.copy()
        for k in range(3):
            wk = area[nbc[:, k]] * has[:, k]
            acc += A[nbc[:, k]] * wk[:, None, None]
            wsum += wk
        A = acc / wsum[:, None, None]
    n = len(V)
    num = np.zeros((n, 3, 3))
    den = np.zeros(n)
    for k in range(3):
        np.add.at(num, F[:, k], A * area[:, None, None])
        np.add.at(den, F[:, k], area)
    return num / np.maximum(den, 1e-30)[:, None, None], float(((s1 * s2) * area).sum() / area.sum()), float(max(s1.max(), s2.max()))


def reshape(V, F, A, plane_x=None, plane_y=None):
    """Vertex positions of a mesh shaped like V but with every neighbourhood
    stretched by its matrix in A (as-rigid-as-possible around that stretch)."""
    n = len(V)
    i = F.ravel()
    j = F[:, [1, 2, 0]].ravel()
    k = F[:, [2, 0, 1]].ravel()
    u = V[i] - V[k]
    v = V[j] - V[k]
    cot = (u * v).sum(1) / np.maximum(np.linalg.norm(np.cross(u, v), axis=1), 1e-20)
    w = 0.5 * np.maximum(cot, 0.05)
    I = np.concatenate([i, j])
    J = np.concatenate([j, i])
    W = np.concatenate([w, w])
    E = V[I] - V[J]
    AE_I = np.einsum('eij,ej->ei', A[I], E)      # the edge as vertex I wants it
    AE_J = np.einsum('eij,ej->ei', A[J], E)
    diag = np.bincount(I, W, n)

    def laplace(X):
        out = diag[:, None] * X
        for c in range(3):
            out[:, c] -= np.bincount(I, W * X[J, c], n)
        return out

    # Vertices on a mirror plane stay in it: that coordinate is taken out of
    # the solve (clamping it afterwards folded the mesh along the plane),
    # and their stretch is made the same on both sides of the plane
    held = np.zeros((n, 3), dtype=bool)
    A = A.copy()
    for plane, axis in ((plane_x, 0), (plane_y, 1)):
        if plane is not None:
            held[plane, axis] = True
            flip = np.ones(3)
            flip[axis] = -1.0
            A[plane] = 0.5 * (A[plane] + A[plane] * flip[None, :, None] * flip[None, None, :])
    AE_I = np.einsum('eij,ej->ei', A[I], E)
    AE_J = np.einsum('eij,ej->ei', A[J], E)

    X = V.copy()
    X[held] = 0.0
    for _ in range(ARAP_ROUNDS):
        Ep = X[I] - X[J]
        S = np.zeros((n, 3, 3))
        np.add.at(S, I, W[:, None, None] * AE_I[:, :, None] * Ep[:, None, :])
        U, _, Vt = np.linalg.svd(S)
        R = np.transpose(Vt, (0, 2, 1)) @ np.transpose(U, (0, 2, 1))
        flip = np.linalg.det(R) < 0
        if flip.any():
            Vt[flip, 2, :] *= -1
            R = np.transpose(Vt, (0, 2, 1)) @ np.transpose(U, (0, 2, 1))
        # On a mirror plane the turn must be one the mirrored half would
        # share: a turn about the plane's own axis, nothing else. Otherwise
        # the stretched surface meets the plane at a slant and the quads
        # come back with a kink along the centre line
        for plane, axis in ((plane_x, 0), (plane_y, 1)):
            if plane is not None and plane.any():
                o = [c for c in range(3) if c != axis]
                B = R[plane][:, o][:, :, o]
                angle = np.arctan2(B[:, 1, 0] - B[:, 0, 1], B[:, 0, 0] + B[:, 1, 1])
                Rp = np.zeros((int(plane.sum()), 3, 3))
                Rp[:, axis, axis] = 1.0
                Rp[:, o[0], o[0]] = np.cos(angle)
                Rp[:, o[0], o[1]] = -np.sin(angle)
                Rp[:, o[1], o[0]] = np.sin(angle)
                Rp[:, o[1], o[1]] = np.cos(angle)
                R[plane] = Rp
        RE = 0.5 * (np.einsum('eij,ej->ei', R[I], AE_I) + np.einsum('eij,ej->ei', R[J], AE_J))
        b = np.zeros((n, 3))
        for c in range(3):
            b[:, c] = np.bincount(I, W * RE[:, c], n)
        r = b - laplace(X)
        r[held] = 0.0
        z = r / diag[:, None]
        p = z.copy()
        rz = (r * z).sum(0)
        for _ in range(CG_STEPS):
            Ap = laplace(p)
            Ap[held] = 0.0
            alpha = rz / np.maximum((p * Ap).sum(0), 1e-30)
            X += alpha * p
            r -= alpha * Ap
            z = r / diag[:, None]
            rz_new = (r * z).sum(0)
            p = z + (rz_new / np.maximum(rz, 1e-30)) * p
            rz = rz_new
    return X


def carry_directions(D, V, X, F):
    """A direction per triangle of V, as the same direction on the reshaped triangle of X."""
    e1, e2 = V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]]
    g11, g12, g22 = (e1 * e1).sum(1), (e1 * e2).sum(1), (e2 * e2).sum(1)
    d1, d2 = (D * e1).sum(1), (D * e2).sum(1)
    det = np.maximum(g11 * g22 - g12 * g12, 1e-30)
    a = (g22 * d1 - g12 * d2) / det
    b = (g11 * d2 - g12 * d1) / det
    out = a[:, None] * (X[F[:, 1]] - X[F[:, 0]]) + b[:, None] * (X[F[:, 2]] - X[F[:, 0]])
    return out / np.maximum(np.linalg.norm(out, axis=1), 1e-20)[:, None]


def carry_back(points, X, V, F, quads=None, reach=0.0):
    """Points lying on the reshaped mesh X, carried to the same spots on the real mesh V.

    Where the reshaped mesh passes through itself (two lips pressed together)
    the nearest triangle can belong to the wrong sheet. Reshaping only ever
    stretches, so a quad edge that comes back longer than it was on the
    reshaped mesh gives a wrong pick away; those points try the other
    triangles within reach and keep the one that sits best with their neighbours."""
    bvh = BVHTree.FromPolygons([tuple(p) for p in X], [tuple(int(a) for a in f) for f in F])

    def real_point(loc, tri):
        a, b, c = X[F[tri, 0]], X[F[tri, 1]], X[F[tri, 2]]
        v0, v1, v2 = b - a, c - a, np.array(loc) - a
        d00, d01, d11 = v0.dot(v0), v0.dot(v1), v1.dot(v1)
        d20, d21 = v2.dot(v0), v2.dot(v1)
        den = max(d00 * d11 - d01 * d01, 1e-30)
        bv = (d11 * d20 - d01 * d21) / den
        bw = (d00 * d21 - d01 * d20) / den
        return (1 - bv - bw) * V[F[tri, 0]] + bv * V[F[tri, 1]] + bw * V[F[tri, 2]]

    out = np.empty_like(points)
    worst = 0.0
    for idx in range(len(points)):
        loc, _, tri, dist = bvh.find_nearest(Vector(points[idx]))
        out[idx] = real_point(loc, tri)
        worst = max(worst, dist)
    fixed = 0
    if quads is not None and len(quads) and reach > 0:
        E = np.concatenate([quads[:, [0, 1]], quads[:, [1, 2]], quads[:, [2, 3]], quads[:, [3, 0]]])
        E = np.unique(np.sort(E, axis=1), axis=0)
        L = np.linalg.norm(points[E[:, 0]] - points[E[:, 1]], axis=1)
        around = {}
        for (i, j), l in zip(E, L):
            around.setdefault(int(i), []).append((int(j), l))
            around.setdefault(int(j), []).append((int(i), l))

        def misfit(i, pos):
            return sum(max(np.linalg.norm(pos - out[j]) - 1.3 * l, 0.0) for j, l in around[i])

        for _ in range(3):
            long_edge = np.linalg.norm(out[E[:, 0]] - out[E[:, 1]], axis=1) > 1.3 * L + 1e-9
            suspects = np.unique(E[long_edge])
            if len(suspects) == 0:
                break
            changed = 0
            for i in suspects:
                i = int(i)
                best, best_pos = misfit(i, out[i]), None
                for loc, _, tri, _ in bvh.find_nearest_range(Vector(points[i]), reach):
                    pos = real_point(loc, tri)
                    m = misfit(i, pos)
                    if m < best - 1e-9:
                        best, best_pos = m, pos
                if best_pos is not None:
                    out[i] = best_pos
                    changed += 1
            fixed += changed
            if changed == 0:
                break
        long_edge = np.linalg.norm(out[E[:, 0]] - out[E[:, 1]], axis=1) > 1.3 * L + 1e-9
        print(f"QUADRE: carry back: {fixed} points moved to another sheet, {int(long_edge.sum())} overlong edges left")
    return out, worst


def rewrite_obj_vertices(src, dst, X):
    """Copy an OBJ file with its vertex positions replaced, everything else kept."""
    it = iter(X)
    with open(src) as f, open(dst, 'w') as g:
        for line in f:
            if line.startswith('v '):
                p = next(it)
                g.write(f"v {p[0]:.6f} {p[1]:.6f} {p[2]:.6f}\n")
            else:
                g.write(line)


# ---- version 3: read the bending finely, then let small quads grow back gradually ----

FINE_STEP = _env('FSTEP', 0.25)      # the bending is read across this fraction of a quad edge, each way
FINE_RADIUS = _env('FRAD', 0.25)
GROW_LENGTH = _env('GROW', 0.5)      # stretch fades by 1/e over this many quad edges away from a tight spot


def fine_bending(V, F, normals_at, quad_edge):
    """The surface's bending per triangle (3x3, normal change per unit length), read over a short step."""
    P0, P1, P2 = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
    N = np.cross(P1 - P0, P2 - P0)
    N /= np.maximum(np.linalg.norm(N, axis=1), 1e-20)[:, None]
    U = P1 - P0
    U /= np.maximum(np.linalg.norm(U, axis=1), 1e-20)[:, None]
    W = np.cross(N, U)
    C = (P0 + P1 + P2) / 3.0
    step = FINE_STEP * quad_edge
    radius = FINE_RADIUS * quad_edge
    dU = (normals_at(C + step * U, radius) - normals_at(C - step * U, radius)) / (2 * step)
    dW = (normals_at(C + step * W, radius) - normals_at(C - step * W, radius)) / (2 * step)
    a = (dU * U).sum(1)
    c = (dW * W).sum(1)
    b = 0.5 * ((dU * W).sum(1) + (dW * U).sum(1))
    UU = U[:, :, None] * U[:, None, :]
    WW = W[:, :, None] * W[:, None, :]
    UW = U[:, :, None] * W[:, None, :]
    return a[:, None, None] * UU + b[:, None, None] * (UW + UW.transpose(0, 2, 1)) + c[:, None, None] * WW


def stretch_tensors_graded(V, F, D, M, quad_edge):
    """Like stretch_tensors, but the stretch spreads outward from each tight
    spot and fades with distance, so quads grow back to full size gradually
    (a stack of thin rings in a crease instead of one small ring)."""
    from .flow import _face_adjacency
    P0, P1, P2 = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
    N = np.cross(P1 - P0, P2 - P0)
    area = 0.5 * np.linalg.norm(N, axis=1)
    N = N / np.maximum(2 * area, 1e-20)[:, None]
    C = (P0 + P1 + P2) / 3.0
    f1 = D - (D * N).sum(1)[:, None] * N
    f1 /= np.maximum(np.linalg.norm(f1, axis=1), 1e-20)[:, None]
    f2 = np.cross(N, f1)
    k1 = np.abs(np.einsum('fi,fij,fj->f', f1, M, f1))
    k2 = np.abs(np.einsum('fi,fij,fj->f', f2, M, f2))
    # Gentle roundness (a leg, a skull) asks for nothing; past TURN_PER_QUAD
    # the stretch rises steeply, so real creases get most of it
    power = _env('POWER', 1.0)
    s1 = np.clip((k1 * quad_edge / TURN_PER_QUAD) ** power, 1.0, MAX_SCALE)
    s2 = np.clip((k2 * quad_edge / TURN_PER_QUAD) ** power, 1.0, MAX_SCALE)
    # Rounded forms (a leg, a nose) get evenly smaller, still square quads;
    # only the crease part above is one-directional
    even_turn = _env('EVEN_TURN', 0.0)
    if even_turn > 0:
        even = np.clip(np.maximum(k1, k2) * quad_edge / even_turn, 1.0, _env('EVEN_MAX', 2.0))
        s1 = np.maximum(s1, even)
        s2 = np.maximum(s2, even)
    nb, _ = _face_adjacency(F)
    has = nb >= 0
    nbc = np.where(has, nb, 0)
    for _ in range(int(_env('GROW_ROUNDS', 40))):
        n1, n2 = s1.copy(), s2.copy()
        for k in range(3):
            g = nbc[:, k]
            decay = np.exp(-np.linalg.norm(C - C[g], axis=1) / (GROW_LENGTH * quad_edge)) * has[:, k]
            swap = np.abs((f1[g] * f2).sum(1)) > np.abs((f1[g] * f1).sum(1))
            n1 = np.maximum(n1, np.where(swap, s2[g], s1[g]) * decay)
            n2 = np.maximum(n2, np.where(swap, s1[g], s2[g]) * decay)
        s1, s2 = n1, n2
    A = (
        N[:, :, None] * N[:, None, :]
        + s1[:, None, None] * f1[:, :, None] * f1[:, None, :]
        + s2[:, None, None] * f2[:, :, None] * f2[:, None, :]
    )
    n = len(V)
    num = np.zeros((n, 3, 3))
    den = np.zeros(n)
    for k in range(3):
        np.add.at(num, F[:, k], A * area[:, None, None])
        np.add.at(den, F[:, k], area)
    return num / np.maximum(den, 1e-30)[:, None, None], float(((s1 * s2) * area).sum() / area.sum()), float(max(s1.max(), s2.max()))


def folded_vertices(V, F, X, rings=2):
    """Vertices on or near a spot where the reshaped mesh X folds over itself
    (two neighbouring triangles facing opposite ways that did not on V), or
    where a triangle was crushed."""
    from .flow import _face_adjacency

    def normals(P):
        n = np.cross(P[F[:, 1]] - P[F[:, 0]], P[F[:, 2]] - P[F[:, 0]])
        a = np.linalg.norm(n, axis=1)
        return n / np.maximum(a, 1e-20)[:, None], a

    nv, av = normals(V)
    nx, ax = normals(X)
    nb, _ = _face_adjacency(F)
    bad = np.zeros(len(F), dtype=bool)
    for k in range(3):
        g = np.where(nb[:, k] >= 0, nb[:, k], np.arange(len(F)))
        bad |= ((nx * nx[g]).sum(1) < 0.0) & ((nv * nv[g]).sum(1) > 0.3)
    bad |= ax < 0.3 * av
    mark = np.zeros(len(V), dtype=bool)
    mark[F[bad].ravel()] = True
    for _ in range(rings):
        grow = mark[F].any(1)
        mark[F[grow].ravel()] = True
    return mark, int(bad.sum())


def reshape_safe(V, F, A, plane_x=None, plane_y=None, tries=5):
    """reshape(), then wherever the result folds over itself the stretch is
    halved around that spot and the solve is run again. If folds remain after
    that, the whole stretch is turned down until they are gone."""
    A = A.copy()
    eye = np.eye(3)
    for attempt in range(tries):
        X = reshape(V, F, A, plane_x, plane_y)
        mark, n_bad = folded_vertices(V, F, X, rings=2 + attempt)
        if n_bad == 0:
            return X, attempt
        A[mark] = eye + 0.5 * (A[mark] - eye) if attempt < 2 else eye
    for k, keep in enumerate((0.6, 0.35, 0.15)):
        X = reshape(V, F, eye + keep * (A - eye), plane_x, plane_y)
        if folded_vertices(V, F, X)[1] == 0:
            return X, tries + 1 + k
    return V.copy(), -1
