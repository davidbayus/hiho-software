"""
QUADRE — the flow map (cross field) the engine traces its quads along.

The engine's own map follows tubes but ignores soft creases such as an
eye-socket rim. This one follows the shape's curvature wherever the shape
clearly has a direction, stays as smooth as possible everywhere else, and
is pinned to borders and hard edges.

Pure numpy + mathutils.kdtree: no bpy, safe on the worker thread.
See QUADRE_FLOW_QUALITY_DESIGN_2026-10-02.md.
"""

import math
import os

import numpy as np
from mathutils.kdtree import KDTree


# Two rounds of neighbour averaging calm the curvature sampling noise
TENSOR_SMOOTH_ROUNDS = 2

# Confidence = min(strength / FULL, 1) ** POWER, where strength is how much
# more the normal turns one way than the other across one quad (radians).
# Softer settings let weak curvature steer the map and put poles mid-forehead
CONFIDENCE_FULL = 1.0
CONFIDENCE_POWER = 2.0

# Pull toward the curvature direction, relative to neighbour smoothness
ALIGN_WEIGHT = 5.0

# Normals are averaged over this fraction of a quad edge before differencing
NORMAL_RADIUS = 0.35


def _read_triangles(path):
    verts, faces = [], []
    with open(path) as f:
        for line in f:
            if line.startswith('v '):
                t = line.split()
                verts.append((float(t[1]), float(t[2]), float(t[3])))
            elif line.startswith('f '):
                faces.append([int(tok.split('/')[0]) - 1 for tok in line.split()[1:4]])
    return np.array(verts), np.array(faces, dtype=np.int64)


def _read_sharp(path):
    """The engine's border/crease list: (face, edge-in-face) pairs."""
    sharp = []
    if not os.path.exists(path):
        return sharp
    with open(path) as f:
        lines = f.read().split('\n')
    for line in lines[1:]:
        if line.strip():
            t = line.split(',')
            sharp.append((int(t[1]), int(t[2])))
    return sharp


def _face_adjacency(F):
    """nb[f, k] = face across edge k (verts k, k+1), or -1; nbk = that edge's slot there."""
    n = len(F)
    a = F
    b = np.roll(F, -1, axis=1)
    key = np.minimum(a, b).ravel() * (F.max() + 1) + np.maximum(a, b).ravel()
    order = np.argsort(key, kind='stable')
    ks = key[order]
    same = ks[1:] == ks[:-1]
    i = order[:-1][same]
    j = order[1:][same]
    nb = -np.ones(n * 3, dtype=np.int64)
    nbk = -np.ones(n * 3, dtype=np.int64)
    nb[i] = j // 3
    nb[j] = i // 3
    nbk[i] = j % 3
    nbk[j] = i % 3
    return nb.reshape(n, 3), nbk.reshape(n, 3)


def compute_field(V, F, sharp, ref_co, ref_no, quad_edge):
    """One unit direction per triangle (an arm of the cross)."""
    nF = len(F)
    P = [V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]]
    N = np.cross(P[1] - P[0], P[2] - P[0])
    A = 0.5 * np.linalg.norm(N, axis=1)
    N = N / np.maximum(2 * A, 1e-20)[:, None]
    U = P[1] - P[0]
    U /= np.maximum(np.linalg.norm(U, axis=1), 1e-20)[:, None]
    W = np.cross(N, U)
    C = (P[0] + P[1] + P[2]) / 3.0

    nb, nbk = _face_adjacency(F)
    has = nb >= 0
    nbc = np.where(has, nb, 0)

    # --- curvature at the scale of one quad: how the smoothed normal of the
    # real surface turns across a quad-sized step along each tangent axis
    kd = KDTree(len(ref_co))
    for idx in range(len(ref_co)):
        kd.insert(ref_co[idx], idx)
    kd.balance()
    step = 0.5 * quad_edge
    radius = NORMAL_RADIUS * quad_edge

    def normals_at(points):
        out = np.empty_like(points)
        for idx in range(len(points)):
            hits = kd.find_range(points[idx], radius)
            if hits:
                n = ref_no[[h[1] for h in hits]].sum(0)
            else:
                n = ref_no[kd.find(points[idx])[1]]
            out[idx] = n / max(np.linalg.norm(n), 1e-20)
        return out

    dU = (normals_at(C + step * U) - normals_at(C - step * U)) / (2 * step)
    dW = (normals_at(C + step * W) - normals_at(C - step * W)) / (2 * step)
    a = (dU * U).sum(1)
    c = (dW * W).sum(1)
    b = 0.5 * ((dU * W).sum(1) + (dW * U).sum(1))

    # Average the tensor with its neighbours as a 3x3 matrix (frames differ
    # per triangle, the ambient matrix does not), then read it back per face
    UU = U[:, :, None] * U[:, None, :]
    WW = W[:, :, None] * W[:, None, :]
    UW = U[:, :, None] * W[:, None, :]
    M = a[:, None, None] * UU + b[:, None, None] * (UW + UW.transpose(0, 2, 1)) + c[:, None, None] * WW
    for _ in range(TENSOR_SMOOTH_ROUNDS):
        acc = M * A[:, None, None]
        wsum = A.copy()
        for k in range(3):
            wk = A[nbc[:, k]] * has[:, k]
            acc += M[nbc[:, k]] * wk[:, None, None]
            wsum += wk
        M = acc / wsum[:, None, None]
    a = np.einsum('fi,fij,fj->f', U, M, U)
    b = np.einsum('fi,fij,fj->f', U, M, W)
    c = np.einsum('fi,fij,fj->f', W, M, W)

    theta_curv = 0.5 * np.arctan2(2 * b, a - c)
    strength = np.sqrt((a - c) ** 2 + 4 * b ** 2) * quad_edge
    confidence = np.clip(strength / CONFIDENCE_FULL, 0.0, 1.0) ** CONFIDENCE_POWER
    target = np.exp(4j * theta_curv)

    # --- neighbour comparison through the shared edge (4 directions: angles x4)
    rot = np.ones((nF, 3), dtype=np.complex128)
    weight = np.zeros((nF, 3))
    edge_angle = np.zeros((nF, 3))
    for k in range(3):
        d = P[(k + 1) % 3] - P[k]
        length = np.linalg.norm(d, axis=1)
        d = d / np.maximum(length, 1e-20)[:, None]
        g = nbc[:, k]
        angle_here = np.arctan2((d * W).sum(1), (d * U).sum(1))
        angle_there = np.arctan2((d * W[g]).sum(1), (d * U[g]).sum(1))
        edge_angle[:, k] = angle_here
        rot[:, k] = np.exp(4j * (angle_there - angle_here))
        dist = np.linalg.norm(C - C[g], axis=1)
        weight[:, k] = np.where(has[:, k], length / np.maximum(dist, 1e-12), 0.0)

    # --- triangles on a border or hard edge are pinned to that edge
    pinned = np.zeros(nF, dtype=bool)
    pin_value = np.zeros(nF, dtype=np.complex128)
    for f, k in sharp:
        if not (0 <= f < nF and 0 <= k < 3):
            continue
        pin_value[f] += np.exp(4j * edge_angle[f, k])
        pinned[f] = True
        g = nb[f, k]
        if g >= 0:
            pin_value[g] += np.exp(4j * edge_angle[g, nbk[f, k]])
            pinned[g] = True
    open_f, open_k = np.nonzero(~has)
    for f, k in zip(open_f, open_k):
        if not pinned[f]:
            pin_value[f] += np.exp(4j * edge_angle[f, k])
            pinned[f] = True
    mag = np.abs(pin_value)
    pin_value = np.where(mag > 1e-9, pin_value / np.maximum(mag, 1e-9), 1.0)

    # --- one linear system: smooth + aligned + pinned, by conjugate gradient
    PIN = 1e3
    mass = np.where(pinned, PIN, ALIGN_WEIGHT * confidence * A / A.mean())
    rhs = np.where(pinned, PIN * pin_value, mass * target)
    diag = weight.sum(1) + mass + 1e-9

    def apply(u):
        out = diag * u
        for k in range(3):
            out -= weight[:, k] * np.conj(rot[:, k]) * u[nbc[:, k]]
        return out

    u = np.where(pinned, pin_value, target * confidence)
    r = rhs - apply(u)
    z = r / diag
    p = z.copy()
    rz = np.vdot(r, z).real
    r0 = math.sqrt(np.vdot(r, r).real) + 1e-30
    for _ in range(4000):
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
    return np.cos(theta)[:, None] * U + np.sin(theta)[:, None] * W


def write_flow_field(qw, ref_co, ref_no, target_faces):
    """Replace the engine's flow map on disk (between step 1 and step 2).

    ref_co / ref_no: vertex positions and normals of the mesh handed to the
    engine. Raises on any problem; the caller then keeps the engine's map.
    """
    V, F = _read_triangles(qw.remeshed_path)
    if len(F) == 0 or len(ref_co) == 0:
        raise ValueError("nothing to build a flow map on")
    sharp = _read_sharp(qw.sharp_path)
    area = 0.5 * np.linalg.norm(
        np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]]), axis=1
    ).sum()
    quad_edge = math.sqrt(area / max(target_faces, 1))
    D = compute_field(V, F, sharp, ref_co, ref_no, quad_edge)
    if not np.isfinite(D).all():
        raise ValueError("flow map has gaps")

    tmp_path = qw.field_path + '.tmp'
    with open(tmp_path, 'w') as f:
        f.write(f"{len(F)}\n4\n")
        for d in D:
            f.write(f"{d[0]:.6f} {d[1]:.6f} {d[2]:.6f} \n")
    os.replace(tmp_path, qw.field_path)
