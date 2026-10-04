"""
QUADRE — how good is a set of quads?

Two numbers in degrees, lower is better. They are the same arithmetic as
the test harness's ruler (ab_harness/metrics.py), read against the mesh
that was handed to the engine:

  flow     how far the quads' loops run off the shape's own curvature
           directions, counted only where the shape clearly has a direction
  corners  how far the corners are from square

The operator builds one layout per flow map and keeps the one with the
lowest flow + corners.

Pure numpy: no bpy, safe on the worker thread.
See QUADRE_PHASE1_DESIGN_2026-10-03.md.
"""

import numpy as np


# Normals are averaged over this fraction of a quad edge (same as the harness)
NORMAL_RADIUS = 0.35

# The shape "clearly has a direction" at a quad when its normal turns this
# much more (radians) one way than the other across that quad
CLEAR_DIRECTION = 0.15


def _read_quads(path):
    verts, quads, others = [], [], 0
    with open(path) as f:
        for line in f:
            if line.startswith('v '):
                t = line.split()
                verts.append((float(t[1]), float(t[2]), float(t[3])))
            elif line.startswith('f '):
                idx = [int(tok.split('/')[0]) - 1 for tok in line.split()[1:]]
                if len(idx) == 4:
                    quads.append(idx)
                else:
                    others += 1
    return np.array(verts), np.array(quads, dtype=np.int64), others


def _angle(u, v):
    c = (u * v).sum(1) / np.maximum(
        np.linalg.norm(u, axis=1) * np.linalg.norm(v, axis=1), 1e-20
    )
    return np.degrees(np.arccos(np.clip(c, -1.0, 1.0)))


def score_quads(path, normals_at):
    """Measure the quads in an OBJ file. normals_at is flow.normal_lookup()'s
    result. Returns {'flow', 'corners', 'faces'}, or None if there are no quads."""
    V, Q, others = _read_quads(path)
    if len(Q) == 0:
        return None
    A, B, C, D = V[Q[:, 0]], V[Q[:, 1]], V[Q[:, 2]], V[Q[:, 3]]
    e0, e1, e2, e3 = B - A, C - B, D - C, A - D
    corner = np.concatenate(
        [_angle(e0, -e3), _angle(e1, -e0), _angle(e2, -e1), _angle(e3, -e2)]
    )
    corners = float(np.abs(corner - 90.0).mean())

    # How the shape's normal turns across each quad, along the quad's own
    # two axes: a 2x2 shape operator per quad. Its principal direction is
    # where the loops ought to run
    edge_mean = float(np.mean([np.linalg.norm(e, axis=1).mean() for e in (e0, e1, e2, e3)]))
    radius = NORMAL_RADIUS * edge_mean
    m_ab, m_bc, m_cd, m_da = 0.5 * (A + B), 0.5 * (B + C), 0.5 * (C + D), 0.5 * (D + A)
    n = len(Q)
    normals = normals_at(np.concatenate([m_ab, m_bc, m_cd, m_da]), radius)
    N_ab, N_bc, N_cd, N_da = normals[:n], normals[n:2 * n], normals[2 * n:3 * n], normals[3 * n:]
    u = m_bc - m_da
    v = m_cd - m_ab
    len_u = np.maximum(np.linalg.norm(u, axis=1), 1e-20)
    len_v = np.maximum(np.linalg.norm(v, axis=1), 1e-20)
    u_hat = u / len_u[:, None]
    v_hat = v / len_v[:, None]
    cos_uv = (v_hat * u_hat).sum(1)
    w_hat = v_hat - cos_uv[:, None] * u_hat
    sin_uv = np.linalg.norm(w_hat, axis=1)
    usable = sin_uv > 0.2
    w_hat = w_hat / np.maximum(sin_uv, 1e-9)[:, None]
    turn_u = (N_bc - N_da) / len_u[:, None]
    turn_v = (N_cd - N_ab) / len_v[:, None]
    turn_w = (turn_v - cos_uv[:, None] * turn_u) / np.maximum(sin_uv, 1e-9)[:, None]
    s11 = (turn_u * u_hat).sum(1)
    s22 = (turn_w * w_hat).sum(1)
    s12 = 0.5 * ((turn_u * w_hat).sum(1) + (turn_w * u_hat).sum(1))
    off = np.abs(0.5 * np.degrees(np.arctan2(2 * s12, s11 - s22))) % 90.0
    off = np.minimum(off, 90.0 - off)
    strength = np.sqrt((s11 - s22) ** 2 + 4 * s12 ** 2)
    area = 0.5 * (
        np.linalg.norm(np.cross(B - A, C - A), axis=1)
        + np.linalg.norm(np.cross(C - A, D - A), axis=1)
    )
    clear = usable & (strength * np.sqrt(area) > CLEAR_DIRECTION)
    flow = float(off[clear].mean()) if clear.any() else 0.0

    return {'flow': flow, 'corners': corners, 'faces': len(Q) + others}
