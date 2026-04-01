"""
Protrusion Detection — Finding Limbs and Appendages
Looks at a character mesh and figures out where the arms, legs, head, etc. are.

Think of it like this: if you hold a gummy bear by its belly, the parts that
stick out (arms, legs, head) are "protrusions." We find those so we can place
seams at their bases — right where the arm meets the body, etc.

How it works:
1. Calculate how "far inside" each vertex is using geodesic-like distance
   (how far you'd have to walk along the surface to reach the center)
2. Vertices deep inside the body = high "centrality"
3. Vertices at fingertips, toes, top of head = low centrality (far from center)
4. Find the narrow "necks" where protrusions connect to the body
   (the armpit, the crotch, the actual neck)
5. Those narrow connections are perfect seam locations
"""

import numpy as np
from typing import List, Tuple, Dict
from dataclasses import dataclass


@dataclass
class Protrusion:
    """A detected limb or appendage."""
    tip_vertex: int          # The vertex at the farthest point (fingertip, top of head)
    base_vertices: List[int] # Vertices at the base where it connects to body
    member_vertices: List[int]  # All vertices that belong to this protrusion
    direction: np.ndarray    # Which way the protrusion points (unit vector)


def detect_protrusions(
    vertices: np.ndarray,
    edges: np.ndarray,
    min_protrusion_ratio: float = 0.30,
) -> List[Protrusion]:
    """
    Find all the sticky-out parts of a mesh (arms, legs, head, tail, etc.).

    Args:
        vertices: Vertex positions (Nx3 array).
        edges: Edge connections as pairs of vertex indices (Mx2 array).
        min_protrusion_ratio: How much something has to stick out to count.
                              0.30 means it needs to extend at least 30% of the
                              mesh's total size. Only detects real limbs, not bumps.

    Returns:
        List of detected protrusions, each with tip, base, and member vertices.
    """
    if len(vertices) < 10 or len(edges) < 10:
        return []

    # Step 1: Build adjacency — which vertices are connected to which
    adjacency = _build_adjacency(len(vertices), edges)

    # Step 2: Find the "most central" vertex (deepest inside the body)
    # We use a trick: find the two farthest-apart vertices, then find
    # the vertex that minimizes the maximum distance to both.
    centrality = _compute_centrality(vertices, adjacency)
    center_idx = int(np.argmax(centrality))

    # Step 3: Compute distance from center for every vertex
    distances = _bfs_distances(center_idx, adjacency, vertices)

    # Step 4: Find tips — local maxima of distance (farthest points)
    tips = _find_tips(distances, adjacency, vertices, min_protrusion_ratio)

    # Step 5: For each tip, trace back toward center and find the "neck"
    # (narrowest cross-section) — that's where the base of the protrusion is
    protrusions = []
    for tip_idx in tips:
        protrusion = _trace_protrusion(
            tip_idx, center_idx, distances, adjacency, vertices
        )
        if protrusion is not None:
            protrusions.append(protrusion)

    return protrusions


def find_junction_edges(
    protrusions: List[Protrusion],
    edges: np.ndarray,
) -> List[int]:
    """
    Find edges at the junctions where protrusions meet the body.
    These are ideal seam locations — the "armpits" and "crotch" of the character.

    Args:
        protrusions: Detected protrusions from detect_protrusions().
        edges: Edge array (Mx2).

    Returns:
        List of edge indices that sit at protrusion junctions.
    """
    junction_edges = []
    for protrusion in protrusions:
        base_set = set(protrusion.base_vertices)
        for edge_idx, (v1, v2) in enumerate(edges):
            if v1 in base_set or v2 in base_set:
                junction_edges.append(edge_idx)
    return list(set(junction_edges))


def _build_adjacency(
    num_vertices: int,
    edges: np.ndarray,
) -> Dict[int, List[int]]:
    """Build a lookup: for each vertex, which other vertices is it connected to?"""
    adj: Dict[int, List[int]] = {i: [] for i in range(num_vertices)}
    for v1, v2 in edges:
        adj[int(v1)].append(int(v2))
        adj[int(v2)].append(int(v1))
    return adj


def _compute_centrality(
    vertices: np.ndarray,
    adjacency: Dict[int, List[int]],
) -> np.ndarray:
    """
    Estimate how "central" each vertex is. Central vertices are deep inside
    the body. Peripheral vertices are at fingertips, toes, etc.

    Uses an approximation: centrality = inverse of average distance to all
    other vertices, computed via multi-source BFS from sampled points.
    """
    n = len(vertices)
    # Sample some vertices to estimate distances from (full BFS from all would be slow)
    num_samples = min(20, n)
    rng = np.random.RandomState(42)  # Deterministic for reproducibility
    sample_indices = rng.choice(n, size=num_samples, replace=False)

    total_dist = np.zeros(n)
    for src in sample_indices:
        dists = _bfs_distances(src, adjacency, vertices)
        total_dist += dists

    # Centrality = inverse of average distance (high = central)
    avg_dist = total_dist / num_samples
    max_dist = avg_dist.max()
    if max_dist < 1e-8:
        return np.ones(n)
    centrality = 1.0 - (avg_dist / max_dist)
    return centrality


def _bfs_distances(
    source: int,
    adjacency: Dict[int, List[int]],
    vertices: np.ndarray,
) -> np.ndarray:
    """
    Compute approximate geodesic distance from source vertex to all others.
    Uses BFS weighted by actual edge lengths (Dijkstra-like but simpler).
    """
    n = len(vertices)
    dist = np.full(n, np.inf)
    dist[source] = 0.0
    visited = np.zeros(n, dtype=bool)

    # Simple priority-less BFS with distance updates (good enough for our purposes)
    queue = [source]
    while queue:
        current = queue.pop(0)
        if visited[current]:
            continue
        visited[current] = True

        for neighbor in adjacency[current]:
            edge_len = np.linalg.norm(vertices[neighbor] - vertices[current])
            new_dist = dist[current] + edge_len
            if new_dist < dist[neighbor]:
                dist[neighbor] = new_dist
                if not visited[neighbor]:
                    queue.append(neighbor)

    # Replace any remaining inf with max finite distance
    finite_mask = np.isfinite(dist)
    if finite_mask.any():
        dist[~finite_mask] = dist[finite_mask].max()
    return dist


def _find_tips(
    distances: np.ndarray,
    adjacency: Dict[int, List[int]],
    vertices: np.ndarray,
    min_ratio: float,
) -> List[int]:
    """
    Find the "tips" of protrusions — vertices that are local maxima of distance
    from center AND far enough away to be meaningful.

    A tip is a vertex that is farther from center than ALL its neighbors.
    Like the peak of a mountain — every direction from it goes downhill.
    """
    max_dist = distances.max()
    threshold = max_dist * min_ratio

    tips = []
    for v_idx in range(len(vertices)):
        if distances[v_idx] < threshold:
            continue

        # Check if this vertex is farther than all its neighbors
        is_local_max = True
        for neighbor in adjacency[v_idx]:
            if distances[neighbor] >= distances[v_idx]:
                is_local_max = False
                break

        if is_local_max:
            tips.append(v_idx)

    # Merge tips that are close together (e.g., multiple vertices at one fingertip)
    # Use 10% of max distance — moderate merge that keeps separate limbs apart
    tips = _merge_nearby_tips(tips, vertices, max_dist * 0.10)

    return tips


def _merge_nearby_tips(
    tips: List[int],
    vertices: np.ndarray,
    merge_distance: float,
) -> List[int]:
    """
    If multiple tips are very close together, keep only the most prominent one.
    BUT: tips on opposite sides of the mesh center are kept separate — they're
    probably paired limbs (left foot + right foot, left hand + right hand).
    """
    if len(tips) <= 1:
        return tips

    # Detect the mesh center for symmetry-awareness
    mesh_center = np.mean(vertices, axis=0)

    merged = []
    used = set()
    tip_positions = vertices[tips]

    for i, tip in enumerate(tips):
        if i in used:
            continue
        # Find all tips close to this one
        cluster = [i]
        for j in range(i + 1, len(tips)):
            if j in used:
                continue
            if np.linalg.norm(tip_positions[i] - tip_positions[j]) < merge_distance:
                # CHECK: are these on opposite sides of center?
                # If so, they're probably paired limbs (left/right) — DON'T merge
                on_opposite_sides = False
                for axis in range(3):
                    side_i = tip_positions[i][axis] - mesh_center[axis]
                    side_j = tip_positions[j][axis] - mesh_center[axis]
                    # If they're on opposite sides AND both meaningfully far from center
                    axis_range = vertices[:, axis].max() - vertices[:, axis].min()
                    min_offset = axis_range * 0.05  # At least 5% away from center
                    if (abs(side_i) > min_offset and abs(side_j) > min_offset
                            and side_i * side_j < 0):  # Opposite signs = opposite sides
                        on_opposite_sides = True
                        break

                if not on_opposite_sides:
                    cluster.append(j)
                    used.add(j)
        # Keep the first one in the cluster (arbitrary but consistent)
        merged.append(tips[cluster[0]])
        used.add(i)

    return merged


def _trace_protrusion(
    tip_idx: int,
    center_idx: int,
    distances: np.ndarray,
    adjacency: Dict[int, List[int]],
    vertices: np.ndarray,
) -> Protrusion:
    """
    Starting from a tip, walk back toward the body center and figure out
    which vertices belong to this protrusion and where the "neck" (base) is.

    The base is found by looking for the narrowest cross-section along the path
    from tip to center — like finding the narrowest part of a balloon animal's arm.
    """
    # Walk from tip toward center, collecting vertices at each "ring"
    visited = set()
    current_ring = {tip_idx}
    rings = []
    member_verts = []

    max_rings = len(vertices)  # Safety limit
    ring_count = 0

    while current_ring and ring_count < max_rings:
        rings.append(list(current_ring))
        member_verts.extend(current_ring)
        visited.update(current_ring)

        # Expand to neighbors that are closer to center (walking inward)
        next_ring = set()
        for v in current_ring:
            for neighbor in adjacency[v]:
                if neighbor not in visited and distances[neighbor] < distances[v]:
                    next_ring.add(neighbor)

        current_ring = next_ring
        ring_count += 1

    if len(rings) < 3:
        return None

    # Find the ring with the smallest spatial spread (the "neck")
    # This is the narrowest cross-section — the base of the protrusion
    min_spread = float('inf')
    base_ring_idx = len(rings) // 2  # Default to middle

    for i, ring in enumerate(rings):
        if len(ring) < 2:
            continue
        ring_positions = vertices[ring]
        spread = np.std(ring_positions, axis=0).sum()
        if spread < min_spread and i > 1:  # Don't pick the very tip
            min_spread = spread
            base_ring_idx = i

    # Everything from tip to base = protrusion members
    protrusion_members = []
    for ring in rings[:base_ring_idx + 1]:
        protrusion_members.extend(ring)

    # Direction = from base center to tip
    tip_pos = vertices[tip_idx]
    base_positions = vertices[rings[base_ring_idx]]
    base_center = base_positions.mean(axis=0)
    direction = tip_pos - base_center
    length = np.linalg.norm(direction)
    if length > 1e-8:
        direction = direction / length

    return Protrusion(
        tip_vertex=tip_idx,
        base_vertices=rings[base_ring_idx],
        member_vertices=protrusion_members,
        direction=direction,
    )
