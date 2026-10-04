"""
QUADRE — the flow maps (cross fields) the engine traces its quads along.

The engine's own map follows tubes but ignores soft creases such as an
eye-socket rim. Quadre's maps follow the shape's curvature wherever the
shape clearly has a direction, stay as smooth as possible everywhere else,
and are pinned to borders and hard edges.

One map is not enough: the engine's patch layout is touchy, and a map that
gives clean quads on one shape gives skewed ones on the next. So Quadre
draws a few maps from one reading of the curvature, and the operator keeps
whichever one the engine builds the best quads from.

Pure numpy + mathutils.kdtree: no bpy, safe on the worker thread.
See QUADRE_FLOW_QUALITY_DESIGN_2026-10-02.md and
QUADRE_PHASE1_DESIGN_2026-10-03.md.
"""

import math
import os

import numpy as np
from mathutils.kdtree import KDTree


# Quadre's maps: (name, smoothing rounds, confidence threshold).
#
# Smoothing rounds: neighbour averaging that calms the curvature reading.
# Two keeps soft creases; six lets only the larger forms steer.
#
# Confidence = min(strength / threshold, 1) ** POWER, where strength is how
# much more the normal turns one way than the other across one quad
# (radians). A softer threshold lets weak curvature steer the map and puts
# poles mid-forehead; a stricter one leaves more of the shape to smoothness.
#
# The first map is the one the finishing pass turns quads toward, whichever
# layout wins. These three plus the engine's own map were the best four of
# seven on the suite and the eleven benchmark shapes (2026-10-03)
MAPS = (
    ('own', 2, 1.0),
    ('smoother', 6, 1.0),
    ('stricter', 2, 2.0),
)

CONFIDENCE_POWER = 2.0

# Pull toward the curvature direction, relative to neighbour smoothness
ALIGN_WEIGHT = 5.0

# Normals are averaged over this fraction of a quad edge before differencing
NORMAL_RADIUS = 0.35

# The finishing pass turns quads toward the first map only where the shape
# clearly has a direction: not at all on a flat or ball-like patch, fully
# where the normal turns this much more (radians) one way than the other
# across one quad. On a flat face the map's direction is arbitrary, and
# turning toward it made straight grids wander (bracket, 2026-10-03)
GUIDE_FULL = 0.3


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


def normal_lookup(ref_co, ref_no):
    """normals_at(points, radius): the shape's normal near each point,
    averaged over the vertices of the mesh handed to the engine that lie
    within radius (the nearest one if none do)."""
    kd = KDTree(len(ref_co))
    for idx in range(len(ref_co)):
        kd.insert(ref_co[idx], idx)
    kd.balance()

    def normals_at(points, radius):
        out = np.empty_like(points)
        for idx in range(len(points)):
            hits = kd.find_range(points[idx], radius)
            if hits:
                n = ref_no[[h[1] for h in hits]].sum(0)
            else:
                n = ref_no[kd.find(points[idx])[1]]
            out[idx] = n / max(np.linalg.norm(n), 1e-20)
        return out

    return normals_at


def compute_fields(V, F, sharp, normals_at, quad_edge, maps=MAPS):
    """One field per map: a unit direction per triangle (an arm of the cross).

    Also returns the guide for the finishing pass: the first map's field
    with each direction scaled by how clearly the shape has a direction
    there (0 to 1; 1 on triangles pinned to a crease or border).
    """
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
    # real surface turns across a quad-sized step along each tangent axis.
    # This reading is the slow part, and every map shares it
    step = 0.5 * quad_edge
    radius = NORMAL_RADIUS * quad_edge
    dU = (normals_at(C + step * U, radius) - normals_at(C - step * U, radius)) / (2 * step)
    dW = (normals_at(C + step * W, radius) - normals_at(C - step * W, radius)) / (2 * step)
    a = (dU * U).sum(1)
    c = (dW * W).sum(1)
    b = 0.5 * ((dU * W).sum(1) + (dW * U).sum(1))

    # The tensor is averaged with its neighbours as a 3x3 matrix (frames
    # differ per triangle, the ambient matrix does not)
    UU = U[:, :, None] * U[:, None, :]
    WW = W[:, :, None] * W[:, None, :]
    UW = U[:, :, None] * W[:, None, :]
    M = a[:, None, None] * UU + b[:, None, None] * (UW + UW.transpose(0, 2, 1)) + c[:, None, None] * WW
    tensor_after = {0: M}

    def smoothed(rounds):
        done = max(r for r in tensor_after if r <= rounds)
        M = tensor_after[done]
        for r in range(done, rounds):
            acc = M * A[:, None, None]
            wsum = A.copy()
            for k in range(3):
                wk = A[nbc[:, k]] * has[:, k]
                acc += M[nbc[:, k]] * wk[:, None, None]
                wsum += wk
            M = acc / wsum[:, None, None]
            tensor_after[r + 1] = M
        return M

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

    fields = []
    guide = None
    for _, smooth_rounds, confidence_full in maps:
        M = smoothed(smooth_rounds)
        a = np.einsum('fi,fij,fj->f', U, M, U)
        b = np.einsum('fi,fij,fj->f', U, M, W)
        c = np.einsum('fi,fij,fj->f', W, M, W)
        theta_curv = 0.5 * np.arctan2(2 * b, a - c)
        strength = np.sqrt((a - c) ** 2 + 4 * b ** 2) * quad_edge
        confidence = np.clip(strength / confidence_full, 0.0, 1.0) ** CONFIDENCE_POWER
        target = np.exp(4j * theta_curv)

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
        fields.append(np.cos(theta)[:, None] * U + np.sin(theta)[:, None] * W)
        if guide is None:
            clear = np.where(pinned, 1.0, np.clip(strength / GUIDE_FULL, 0.0, 1.0))
            guide = fields[0] * clear[:, None]
    return fields, guide


def write_flow_fields(remeshed_path, sharp_path, normals_at, target_faces, paths,
                      guide_path, maps=MAPS):
    """Write one flow map file per entry of maps, for the engine's remeshed
    triangles, and the finishing pass's guide (same file layout, directions
    scaled by their strength). Raises on any problem; the caller then falls
    back to the engine's own map.
    """
    V, F = _read_triangles(remeshed_path)
    if len(F) == 0:
        raise ValueError("nothing to build a flow map on")
    sharp = _read_sharp(sharp_path)
    area = 0.5 * np.linalg.norm(
        np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]]), axis=1
    ).sum()
    quad_edge = math.sqrt(area / max(target_faces, 1))
    fields, guide = compute_fields(V, F, sharp, normals_at, quad_edge, maps)
    for D in fields + [guide]:
        if not np.isfinite(D).all():
            raise ValueError("flow map has gaps")
    for D, path in zip(fields + [guide], list(paths) + [guide_path]):
        tmp_path = path + '.tmp'
        with open(tmp_path, 'w') as f:
            f.write(f"{len(F)}\n4\n")
            for d in D:
                f.write(f"{d[0]:.6f} {d[1]:.6f} {d[2]:.6f} \n")
        os.replace(tmp_path, path)
