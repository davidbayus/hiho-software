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

    X = V.copy()
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
        RE = 0.5 * (np.einsum('eij,ej->ei', R[I], AE_I) + np.einsum('eij,ej->ei', R[J], AE_J))
        b = np.zeros((n, 3))
        for c in range(3):
            b[:, c] = np.bincount(I, W * RE[:, c], n)
        r = b - laplace(X)
        z = r / diag[:, None]
        p = z.copy()
        rz = (r * z).sum(0)
        for _ in range(CG_STEPS):
            Ap = laplace(p)
            alpha = rz / np.maximum((p * Ap).sum(0), 1e-30)
            X += alpha * p
            r -= alpha * Ap
            z = r / diag[:, None]
            rz_new = (r * z).sum(0)
            p = z + (rz_new / np.maximum(rz, 1e-30)) * p
            rz = rz_new
        if plane_x is not None:
            X[plane_x, 0] = 0.0
        if plane_y is not None:
            X[plane_y, 1] = 0.0
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


def carry_back(points, X, V, F):
    """Points lying on the reshaped mesh X, carried to the same spots on the real mesh V."""
    bvh = BVHTree.FromPolygons([tuple(p) for p in X], [tuple(int(a) for a in f) for f in F])
    out = np.empty_like(points)
    worst = 0.0
    for idx in range(len(points)):
        loc, _, tri, dist = bvh.find_nearest(Vector(points[idx]))
        a, b, c = X[F[tri, 0]], X[F[tri, 1]], X[F[tri, 2]]
        v0, v1, v2 = b - a, c - a, np.array(loc) - a
        d00, d01, d11 = v0.dot(v0), v0.dot(v1), v1.dot(v1)
        d20, d21 = v2.dot(v0), v2.dot(v1)
        den = max(d00 * d11 - d01 * d01, 1e-30)
        bv = (d11 * d20 - d01 * d21) / den
        bw = (d00 * d21 - d01 * d20) / den
        out[idx] = (1 - bv - bw) * V[F[tri, 0]] + bv * V[F[tri, 1]] + bw * V[F[tri, 2]]
        worst = max(worst, dist)
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
