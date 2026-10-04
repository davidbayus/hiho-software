"""
QUADRE — finishing pass on the engine's quads.

The engine hands back quads that are sheared and sitting on its own rough
copy of the shape. This pass squares them up, turns them toward the flow
map, evens out neighbouring sizes, and snaps every vertex onto the
student's original shape.

Works on the half mesh before the mirror step: vertices on a mirror plane
only slide inside that plane. Vertices on a crease or an open border only
slide along that line, and where a line has a corner they do not move.
See QUADRE_FLOW_QUALITY_DESIGN_2026-10-02.md and
QUADRE_PHASE1_DESIGN_2026-10-03.md.
"""

import math
import os

import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

from .flow import _read_triangles, _read_sharp


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

# A vertex this close to one of the engine's crease or border lines (in
# quad-edges) is on that line. The engine puts them there exactly; the
# next-nearest vertices sit a third of a quad away or more (measured
# 2026-10-03 on the bracket, Suzanne and the film head)
LINE_TOL = 0.02

# A line that turns more than this at a point has a corner there
CORNER_ANGLE = 35.0

# A line shorter than this many quad-edges is a stray mark (a pinhole, a
# crease fragment), not a line worth holding vertices to
MIN_LINE_LENGTH = 4.0


def load_flow(remeshed_path, field_path):
    """A flow map on the engine's triangles: (BVH of the triangles, one direction per triangle)."""
    if not (os.path.exists(field_path) and os.path.exists(remeshed_path)):
        return None
    V, F = _read_triangles(remeshed_path)
    with open(field_path) as f:
        lines = f.read().split('\n')[2:]
    D = np.array([[float(x) for x in line.split()] for line in lines if line.strip()])
    if len(D) != len(F):
        return None
    bvh = BVHTree.FromPolygons([tuple(v) for v in V], [tuple(int(i) for i in f) for f in F])
    return bvh, D


def load_lines(qw, sym_x, sym_y):
    """The crease and border lines the engine built its quads along, or None.

    Returns (segments [M, 2, 3], length of the line each segment belongs to,
    id of that line, corner points [K, 3], length of each corner's line).
    Lines lying in a mirror plane are left out: the mirror step owns those.
    """
    if not os.path.exists(qw.remeshed_path):
        return None
    V, F = _read_triangles(qw.remeshed_path)
    if len(F) == 0:
        return None
    edges = set()
    for f, k in _read_sharp(qw.sharp_path):
        if 0 <= f < len(F) and 0 <= k < 3:
            a, b = int(F[f, k]), int(F[f, (k + 1) % 3])
            edges.add((a, b) if a < b else (b, a))
    use = {}
    for tri in F:
        for k in range(3):
            a, b = int(tri[k]), int(tri[(k + 1) % 3])
            key = (a, b) if a < b else (b, a)
            use[key] = use.get(key, 0) + 1
    edges.update(e for e, count in use.items() if count == 1)

    def in_mirror(i):
        return (sym_x and abs(V[i, 0]) < PLANE_EPS) or (sym_y and abs(V[i, 1]) < PLANE_EPS)

    edges = [e for e in edges if not (in_mirror(e[0]) and in_mirror(e[1]))]
    if not edges:
        return None
    around = {}
    for a, b in edges:
        around.setdefault(a, []).append(b)
        around.setdefault(b, []).append(a)

    # Each connected line, and how long it is
    line_of = {}
    for first in around:
        if first in line_of:
            continue
        line_of[first] = first
        stack = [first]
        while stack:
            for other in around[stack.pop()]:
                if other not in line_of:
                    line_of[other] = first
                    stack.append(other)
    edges = np.array(edges, dtype=np.int64)
    edge_length = np.linalg.norm(V[edges[:, 1]] - V[edges[:, 0]], axis=1)
    length = {}
    for a, l in zip(edges[:, 0], edge_length):
        length[line_of[int(a)]] = length.get(line_of[int(a)], 0.0) + float(l)

    # Corners: where lines meet, or where one turns sharply. A line's loose
    # end is not a corner — it may slide back along its own line
    limit = math.cos(math.radians(CORNER_ANGLE))
    corners = []
    for v, others in around.items():
        if len(others) > 2:
            corners.append(v)
        elif len(others) == 2:
            d1 = V[v] - V[others[0]]
            d2 = V[others[1]] - V[v]
            cos = d1.dot(d2) / max(np.linalg.norm(d1) * np.linalg.norm(d2), 1e-20)
            if cos < limit:
                corners.append(v)
    corners = np.array(corners, dtype=np.int64)
    return (
        V[edges],
        np.array([length[line_of[int(a)]] for a in edges[:, 0]]),
        np.array([line_of[int(a)] for a in edges[:, 0]], dtype=np.int64),
        V[corners].reshape(-1, 3),
        np.array([length[line_of[int(v)]] for v in corners]),
    )


def _line_vertices(X, candidates, quad_edge, lines):
    """Which of the candidate vertices sit on a kept line.

    Returns (vertex indices, then per vertex the segments it may slide
    along as padded arrays start / direction / squared length, then which
    of the vertices sit at a corner), or None.
    """
    segments, line_length, line_id, corner_points, corner_length = lines
    keep = line_length >= MIN_LINE_LENGTH * quad_edge
    segments, line_id = segments[keep], line_id[keep]
    corner_points = corner_points[corner_length >= MIN_LINE_LENGTH * quad_edge]
    if len(segments) == 0:
        return None
    tol = LINE_TOL * quad_edge
    seg_a = segments[:, 0]
    seg_ab = segments[:, 1] - seg_a
    seg_l2 = np.maximum((seg_ab ** 2).sum(1), 1e-30)

    # Sample points along every line, so a kd-tree can say which segments
    # are near a vertex
    spacing = 0.25 * quad_edge
    samples, sample_segment = [], []
    for j in range(len(segments)):
        n = max(int(math.ceil(math.sqrt(seg_l2[j]) / spacing)), 1)
        for k in range(n + 1):
            samples.append(seg_a[j] + seg_ab[j] * (k / n))
            sample_segment.append(j)
    kd = KDTree(len(samples))
    for idx, point in enumerate(samples):
        kd.insert(point, idx)
    kd.balance()

    reach = (TRAVEL_LIMIT + 1.0) * quad_edge
    on_line, rows = [], []
    for i in candidates:
        if kd.find(X[i])[2] > tol + spacing:
            continue
        near = np.unique(
            [sample_segment[idx] for _, idx, _ in kd.find_range(X[i], reach + spacing)]
        )
        t = np.clip(((X[i] - seg_a[near]) * seg_ab[near]).sum(1) / seg_l2[near], 0.0, 1.0)
        d = np.linalg.norm(X[i] - (seg_a[near] + t[:, None] * seg_ab[near]), axis=1)
        if d.min() >= tol:
            continue
        # A vertex stays on the line it starts on, even where another line
        # runs close by (an eyeball's rim inside an eye socket's rim)
        own = line_id[near] == line_id[near[d.argmin()]]
        on_line.append(i)
        rows.append(near[own & (d < reach)])
    if not on_line:
        return None
    on_line = np.array(on_line, dtype=np.int64)
    width = max(len(r) for r in rows)
    pick = np.array([np.pad(r, (0, width - len(r)), mode='edge') for r in rows])
    at_corner = np.zeros(len(on_line), dtype=bool)
    if len(corner_points):
        for k, i in enumerate(on_line):
            at_corner[k] = np.linalg.norm(corner_points - X[i], axis=1).min() < tol
    return on_line, seg_a[pick], seg_ab[pick], seg_l2[pick], at_corner


def _closest_on_segments(P, A, AB, L2):
    """The closest point to each P[i] on its own row of segments A[i, j] + t * AB[i, j]."""
    t = np.clip(((P[:, None, :] - A) * AB).sum(2) / L2, 0.0, 1.0)
    C = A + t[:, :, None] * AB
    best = ((P[:, None, :] - C) ** 2).sum(2).argmin(1)
    return C[np.arange(len(P)), best]


def _vertex_normals(X, Q):
    n = np.cross(X[Q[:, 1]] - X[Q[:, 0]], X[Q[:, 3]] - X[Q[:, 0]])
    out = np.zeros_like(X)
    for k in range(4):
        np.add.at(out, Q[:, k], n)
    return out / np.maximum(np.linalg.norm(out, axis=1), 1e-20)[:, None]


def finish_quads(mesh, snap, flow_map, sym_x, sym_y, lines=None):
    """Square up, align, even out, and snap the quads of `mesh` in place.

    snap(X, indices, normals, max_dist) moves X[i] onto the original shape
    where that is safe. flow_map is load_flow()'s result, or None. lines is
    load_lines()'s result, or None.
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
    in_quads = quads_per_vert > 0
    fixed |= ~in_quads
    quads_per_vert = np.maximum(quads_per_vert, 1.0)

    # Vertices on a crease or an open border slide along that line instead
    # of being dragged off it (creases) or frozen (borders). Corners of a
    # line, and line vertices that also sit on a mirror plane, stay put
    on_line = np.zeros(0, dtype=np.int64)
    if lines is not None:
        e_u = 0.5 * ((X[Q[:, 1]] - X[Q[:, 0]]) + (X[Q[:, 2]] - X[Q[:, 3]]))
        e_v = 0.5 * ((X[Q[:, 3]] - X[Q[:, 0]]) + (X[Q[:, 2]] - X[Q[:, 1]]))
        quad_edge = float(
            np.sqrt(np.linalg.norm(e_u, axis=1) * np.linalg.norm(e_v, axis=1)).mean()
        )
        found = _line_vertices(X, np.nonzero(in_quads)[0], quad_edge, lines)
        if found is not None:
            on_line, line_a, line_ab, line_l2, at_corner = found
            held = at_corner | on_x[on_line] | on_y[on_line]
            fixed[on_line] = held
            on_line, line_a, line_ab, line_l2 = (
                on_line[~held], line_a[~held], line_ab[~held], line_l2[~held]
            )
    sliding = np.zeros(n_verts, dtype=bool)
    sliding[on_line] = True
    free = np.nonzero(~fixed & ~sliding)[0]
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
        if len(on_line):
            moved[on_line] = _closest_on_segments(moved[on_line], line_a, line_ab, line_l2)
        X = moved
        if rnd % snap_every == 0 or rnd == ROUNDS - 1:
            snap(X, free, _vertex_normals(X, Q), SNAP_REACH * float(size.mean()))
        X[on_x, 0] = 0.0
        X[on_y, 1] = 0.0

    if not np.isfinite(X).all():
        raise ValueError("finishing pass produced gaps")
    mesh.vertices.foreach_set('co', X.ravel())
    mesh.update()
