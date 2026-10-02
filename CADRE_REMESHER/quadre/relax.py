"""
QUADRE — finishing pass on the engine's quads.

The engine hands back quads that are sheared and sitting on its own rough
copy of the shape. This pass squares them up, turns them toward the flow
map, evens out neighbouring sizes, and snaps every vertex onto the
student's original shape.

Works on the half mesh before the mirror step: vertices on a mirror plane
only slide inside that plane, open-border vertices do not move.
See QUADRE_FLOW_QUALITY_DESIGN_2026-10-02.md.
"""

import math
import os

import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from .flow import _read_triangles


ROUNDS = 60

# How far each vertex moves toward where its quads want it, per round
STEP = 0.7

# How far each quad's target rectangle turns toward the flow map. Full
# strength reads better on the ruler but leaves visible zigzags
FLOW_PULL = 0.3

# Blend of each quad's size toward the average of the quads around it
SIZE_EVEN = 0.5

# The flow map is looked up again every few rounds as quads drift
FLOW_LOOKUP_EVERY = 5

# Snapping is the slow part (one Blender call per vertex, main thread).
# Past this many calls the snap runs every few rounds instead of every one
SNAP_CALL_BUDGET = 250_000

# No vertex ends up further than this many quad-edges from where the engine
# put it — keeps thin parts (an ear, a fin) from sliding over their own rim
TRAVEL_LIMIT = 1.0

# A snap further than this many quad-edges is refused: the nearest surface
# that far away is some other part of the shape
SNAP_REACH = 0.5

PLANE_EPS = 1e-4


def load_flow(qw):
    """The flow map the engine traced: (BVH of its triangles, one direction per triangle)."""
    if not (os.path.exists(qw.field_path) and os.path.exists(qw.remeshed_path)):
        return None
    V, F = _read_triangles(qw.remeshed_path)
    with open(qw.field_path) as f:
        lines = f.read().split('\n')[2:]
    D = np.array([[float(x) for x in line.split()] for line in lines if line.strip()])
    if len(D) != len(F):
        return None
    bvh = BVHTree.FromPolygons([tuple(v) for v in V], [tuple(int(i) for i in f) for f in F])
    return bvh, D


def _vertex_normals(X, Q):
    n = np.cross(X[Q[:, 1]] - X[Q[:, 0]], X[Q[:, 3]] - X[Q[:, 0]])
    out = np.zeros_like(X)
    for k in range(4):
        np.add.at(out, Q[:, k], n)
    return out / np.maximum(np.linalg.norm(out, axis=1), 1e-20)[:, None]


def finish_quads(mesh, snap, flow_map, sym_x, sym_y):
    """Square up, align, even out, and snap the quads of `mesh` in place.

    snap(X, indices, normals, max_dist) moves X[i] onto the original shape
    where that is safe. flow_map is load_flow()'s result, or None.
    """
    n_verts = len(mesh.vertices)
    X = np.empty(n_verts * 3)
    mesh.vertices.foreach_get('co', X)
    X = X.reshape(-1, 3).copy()
    polys = [tuple(p.vertices) for p in mesh.polygons]
    Q = np.array([p for p in polys if len(p) == 4], dtype=np.int64)
    if len(Q) == 0:
        return

    # --- which vertices may move, and how
    edge_use = {}
    for p in polys:
        n = len(p)
        for k in range(n):
            a, b = p[k], p[(k + 1) % n]
            key = (a, b) if a < b else (b, a)
            edge_use[key] = edge_use.get(key, 0) + 1
    border = sorted({v for e, c in edge_use.items() if c == 1 for v in e})
    border = np.array(border, dtype=np.int64)
    on_x = np.zeros(n_verts, dtype=bool)
    on_y = np.zeros(n_verts, dtype=bool)
    fixed = np.zeros(n_verts, dtype=bool)
    if len(border):
        if sym_x:
            on_x[border] = np.abs(X[border, 0]) < PLANE_EPS
        if sym_y:
            on_y[border] = np.abs(X[border, 1]) < PLANE_EPS
        fixed[border] = ~(on_x[border] | on_y[border])
    quads_per_vert = np.zeros(n_verts)
    np.add.at(quads_per_vert, Q.ravel(), 1.0)
    fixed |= quads_per_vert == 0
    quads_per_vert = np.maximum(quads_per_vert, 1.0)
    free = np.nonzero(~fixed)[0]
    on_mirror_line = (on_x | on_y)[Q].any(1)

    snap_every = max(1, math.ceil(len(free) * ROUNDS / SNAP_CALL_BUDGET))
    flow_dirs = None
    start = X.copy()

    for rnd in range(ROUNDS):
        A, B, C, D = X[Q[:, 0]], X[Q[:, 1]], X[Q[:, 2]], X[Q[:, 3]]
        centre = 0.25 * (A + B + C + D)
        u_axis = 0.5 * ((B - A) + (C - D))
        v_axis = 0.5 * ((D - A) + (C - B))
        normal = np.cross(u_axis, v_axis)
        normal /= np.maximum(np.linalg.norm(normal, axis=1), 1e-20)[:, None]
        len_u = np.linalg.norm(u_axis, axis=1)
        len_v = np.linalg.norm(v_axis, axis=1)
        u_hat = u_axis / np.maximum(len_u, 1e-20)[:, None]
        v_hat = v_axis / np.maximum(len_v, 1e-20)[:, None]

        # Nearest square frame to the quad's own axes: the bisector, turned 45 degrees
        b1 = u_hat + v_hat
        b1 /= np.maximum(np.linalg.norm(b1, axis=1), 1e-20)[:, None]
        b2 = np.cross(normal, b1)
        tu = (b1 - b2) / math.sqrt(2.0)
        tv = (b1 + b2) / math.sqrt(2.0)

        if flow_map is not None:
            if flow_dirs is None or rnd % FLOW_LOOKUP_EVERY == 0:
                bvh, field = flow_map
                flow_dirs = np.array([field[bvh.find_nearest(Vector(c))[2]] for c in centre])
            d1 = flow_dirs - (flow_dirs * normal).sum(1)[:, None] * normal
            d1 /= np.maximum(np.linalg.norm(d1, axis=1), 1e-20)[:, None]
            d2 = np.cross(normal, d1)
            # Turn toward the nearest arm of the cross. Quads on a mirror
            # line turn all the way so loops cross the centre line square
            angle = np.arctan2((tu * d2).sum(1), (tu * d1).sum(1))
            turn = -(((angle + math.pi / 4) % (math.pi / 2)) - math.pi / 4)
            turn *= np.where(on_mirror_line, 1.0, FLOW_PULL)
            cos_t, sin_t = np.cos(turn)[:, None], np.sin(turn)[:, None]
            tu, tv = cos_t * tu + sin_t * tv, -sin_t * tu + cos_t * tv

        size = np.sqrt(len_u * len_v)
        around = np.zeros(n_verts)
        np.add.at(around, Q.ravel(), np.repeat(size, 4))
        local_size = (around / quads_per_vert)[Q].mean(1)
        scale = (1.0 - SIZE_EVEN) + SIZE_EVEN * local_size / np.maximum(size, 1e-20)

        half_u = (0.5 * len_u * scale)[:, None] * tu
        half_v = (0.5 * len_v * scale)[:, None] * tv
        wanted = np.zeros_like(X)
        np.add.at(wanted, Q[:, 0], centre - half_u - half_v)
        np.add.at(wanted, Q[:, 1], centre + half_u - half_v)
        np.add.at(wanted, Q[:, 2], centre + half_u + half_v)
        np.add.at(wanted, Q[:, 3], centre - half_u + half_v)
        wanted /= quads_per_vert[:, None]

        moved = X + STEP * (wanted - X)
        moved[fixed] = X[fixed]
        travel = moved - start
        dist = np.linalg.norm(travel, axis=1)
        limit = TRAVEL_LIMIT * float(size.mean())
        over = dist > limit
        moved[over] = start[over] + travel[over] * (limit / dist[over])[:, None]
        X = moved
        if rnd % snap_every == 0 or rnd == ROUNDS - 1:
            snap(X, free, _vertex_normals(X, Q), SNAP_REACH * float(size.mean()))
        X[on_x, 0] = 0.0
        X[on_y, 1] = 0.0

    if not np.isfinite(X).all():
        raise ValueError("finishing pass produced gaps")
    mesh.vertices.foreach_set('co', X.ravel())
    mesh.update()
