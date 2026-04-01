"""
Seam Generator V4 — Three Brains for Three Shape Types

Every shape a student makes falls into one of three categories:

1. CHARACTER — Symmetric biped/humanoid (the teddy bear surgery approach)
   Seam tree: trunk down the back + branches to limbs → 1 island

2. SIMPLE SHAPE — Props, accessories, weapons, potions, hats, rocks
   One seam line that splits it like cracking a walnut → 1 island

3. THINGAMABOB — Multi-limbed creatures, organic blobs, asymmetric weirdness
   No symmetry assumed. Find every appendage, seam each one → 1-3 islands

Together these cover ~90% of shapes a student would make.
"""

import numpy as np
import bpy
import heapq
from typing import List, Set, Tuple, Optional, Dict

from .symmetry import detect_symmetry_axis, get_center_vertices
from .protrusion import detect_protrusions, Protrusion


# ===========================================================================
#  MODE 1: CHARACTER — "Teddy Bear Surgery"
#  Symmetric biped. One trunk seam + limb branches. Target: 1 island.
# ===========================================================================

def generate_seams_character(obj: bpy.types.Object) -> Set[Tuple[int, int]]:
    """
    Generate seams for a symmetric character (biped/humanoid).

    Strategy: build a "seam tree" — one trunk (center-back) with branches
    (one per limb) that all connect. Like a tree's trunk and branches.
    The whole character unfolds into a flat gingerbread man shape.
    """
    mesh = obj.data
    vertices = np.array([v.co for v in mesh.vertices])
    edges = np.array([(e.vertices[0], e.vertices[1]) for e in mesh.edges])

    if len(vertices) < 4 or len(edges) < 4:
        return set()

    adjacency = _build_adjacency(len(vertices), edges)
    seam_edges: Set[Tuple[int, int]] = set()

    # Detect symmetry and figure out orientation
    sym_axis = detect_symmetry_axis(vertices)
    up_axis = 2  # Z is up in Blender
    if sym_axis is not None:
        remaining = {0, 1, 2} - {sym_axis, up_axis}
        front_back_axis = remaining.pop() if remaining else 1
    else:
        sym_axis = 0
        front_back_axis = 1

    # Detect protrusions (arms, legs, head)
    protrusions = detect_protrusions(vertices, edges)

    # Find the body center (the torso centroid)
    body_center = np.mean(vertices, axis=0)

    # --- THE SEAM TREE ---
    # Step 1: Find the topmost center vertex (top of head)
    center_tolerance = _get_center_tolerance(vertices, sym_axis)
    center_mask = np.abs(vertices[:, sym_axis] - np.median(vertices[:, sym_axis])) < center_tolerance

    if center_mask.sum() >= 2:
        center_indices = np.where(center_mask)[0]
        top_idx = int(center_indices[np.argmax(vertices[center_indices, up_axis])])
    else:
        top_idx = int(np.argmax(vertices[:, up_axis]))

    # Step 2: Find the crotch point
    leg_protrusions = [p for p in protrusions if _is_below(vertices, p, body_center, up_axis)]
    arm_protrusions = [p for p in protrusions if not _is_below(vertices, p, body_center, up_axis)]

    if leg_protrusions:
        leg_base_positions = []
        for lp in leg_protrusions:
            leg_base_positions.extend(lp.base_vertices)
        avg_leg_base = np.mean(vertices[leg_base_positions], axis=0)
        if center_mask.sum() >= 1:
            center_dists = np.linalg.norm(vertices[center_indices] - avg_leg_base, axis=1)
            crotch_idx = int(center_indices[np.argmin(center_dists)])
        else:
            crotch_idx = _find_nearest_vertex(avg_leg_base, vertices)
    else:
        if center_mask.sum() >= 2:
            crotch_idx = int(center_indices[np.argmin(vertices[center_indices, up_axis])])
        else:
            crotch_idx = int(np.argmin(vertices[:, up_axis]))

    # Step 3: TRUNK — seam from top of head to crotch, biased toward back
    trunk_path = _find_path_biased(
        top_idx, crotch_idx, adjacency, vertices,
        bias_axis=front_back_axis,
        bias_direction=1.0,
        bias_strength=0.5,
    )
    _add_path_to_seams(trunk_path, seam_edges)
    trunk_set = set(trunk_path)

    # Step 4: LEG BRANCHES
    for leg in leg_protrusions:
        inner_dir = _get_inner_direction(vertices, leg, body_center, sym_axis)
        leg_path = _find_path_biased(
            crotch_idx, leg.tip_vertex, adjacency, vertices,
            bias_vector=inner_dir,
            bias_vector_strength=0.5,
        )
        _add_path_to_seams(leg_path, seam_edges)

    # Step 5: ARM BRANCHES
    for arm in arm_protrusions:
        arm_base_center = np.mean(vertices[arm.base_vertices], axis=0)
        branch_point = _find_nearest_vertex_in_set(arm_base_center, vertices, trunk_set)
        if branch_point is None:
            branch_point = crotch_idx

        inner_dir = _get_inner_direction(vertices, arm, body_center, sym_axis)
        arm_path = _find_path_biased(
            branch_point, arm.tip_vertex, adjacency, vertices,
            bias_vector=inner_dir,
            bias_vector_strength=0.5,
        )
        _add_path_to_seams(arm_path, seam_edges)

    # Fallback
    if len(seam_edges) < 2:
        bottom_idx = int(np.argmin(vertices[:, up_axis]))
        fallback = _find_shortest_path(top_idx, bottom_idx, adjacency, vertices)
        _add_path_to_seams(fallback, seam_edges)

    return seam_edges


# ===========================================================================
#  MODE 2: SIMPLE SHAPE — "Crack the Walnut"
#  Props, accessories, single objects. One seam line. Target: 1 island.
# ===========================================================================

def generate_seams_simple(obj: bpy.types.Object) -> Set[Tuple[int, int]]:
    """
    Generate seams for a simple shape (prop, accessory, single object).

    Strategy: find the longest axis of the object, then place ONE seam
    line along the back/bottom — like cracking open a walnut or splitting
    a baguette. The object opens into two halves that lay flat.

    For a potion bottle: one seam down the back.
    For a sword: one seam along the flat edge.
    For a rock: one seam along the bottom where it sits on the ground.

    No protrusion detection. No symmetry tree. Just one clean cut.
    """
    mesh = obj.data
    vertices = np.array([v.co for v in mesh.vertices])
    edges = np.array([(e.vertices[0], e.vertices[1]) for e in mesh.edges])

    if len(vertices) < 4 or len(edges) < 4:
        return set()

    adjacency = _build_adjacency(len(vertices), edges)
    seam_edges: Set[Tuple[int, int]] = set()

    # Find the two vertices that are farthest apart (the "long axis" of the shape)
    # This defines the line our seam will follow
    start_idx, end_idx = _find_farthest_pair(vertices, adjacency)

    # Determine which side is the "back" or "bottom" — the least visible side.
    # Strategy: find the side with the LEAST surface area facing the camera.
    # Simplified: prefer the back (+Y), then bottom (-Z), as the seam side.
    #
    # We bias the seam path toward the back/bottom of the object.
    body_center = np.mean(vertices, axis=0)

    # Try to detect if the object has a clear "up" orientation
    bbox_size = vertices.max(axis=0) - vertices.min(axis=0)
    longest_axis = int(np.argmax(bbox_size))

    # The seam runs along the longest axis, biased to the "hidden" side
    # For most props: back = +Y, bottom = -Z
    if longest_axis == 2:
        # Tall object (like a potion bottle standing up) — seam goes top to bottom on the back
        bias_axis = 1  # Bias toward +Y (back)
        bias_direction = 1.0
    elif longest_axis == 0:
        # Wide object (like a sword lying on X) — seam goes along it on the bottom
        bias_axis = 2  # Bias toward -Z (bottom)
        bias_direction = -1.0
    else:
        # Deep object — seam on the bottom
        bias_axis = 2
        bias_direction = -1.0

    # Path from one end to the other, biased toward the hidden side
    seam_path = _find_path_biased(
        start_idx, end_idx, adjacency, vertices,
        bias_axis=bias_axis,
        bias_direction=bias_direction,
        bias_strength=0.6,  # Strong bias to keep the seam on the hidden side
    )
    _add_path_to_seams(seam_path, seam_edges)

    return seam_edges


# ===========================================================================
#  MODE 3: THINGAMABOB — "The Octopus"
#  Multi-limbed, asymmetric, weird. No symmetry assumed. Target: 1-3 islands.
# ===========================================================================

def generate_seams_thingamabob(obj: bpy.types.Object) -> Set[Tuple[int, int]]:
    """
    Generate seams for complex, asymmetric, multi-appendage shapes.

    Strategy: forget about symmetry. Find EVERY appendage (lower threshold
    than Character mode), then connect them all to a central trunk seam.

    Think of unwrapping an octopus: one cut from the top of the head down
    through the center, then a cut along each tentacle. No assumption that
    the left side matches the right.

    Uses a lower protrusion threshold (0.15 vs Character's 0.30) to catch
    smaller appendages like wings, tails, ears, horns, extra arms.
    """
    mesh = obj.data
    vertices = np.array([v.co for v in mesh.vertices])
    edges = np.array([(e.vertices[0], e.vertices[1]) for e in mesh.edges])

    if len(vertices) < 4 or len(edges) < 4:
        return set()

    adjacency = _build_adjacency(len(vertices), edges)
    seam_edges: Set[Tuple[int, int]] = set()
    body_center = np.mean(vertices, axis=0)

    # Use a LOWER protrusion threshold to catch more appendages
    protrusions = detect_protrusions(vertices, edges, min_protrusion_ratio=0.15)

    # Find the two most distant protrusion tips — these define the "main axis"
    # (e.g., head-to-tail on a dragon, or top-to-bottom on a multi-armed creature)
    if len(protrusions) >= 2:
        main_start, main_end = _find_farthest_protrusion_pair(vertices, protrusions)
    else:
        # Not enough protrusions — just use the farthest two vertices
        main_start, main_end = _find_farthest_pair(vertices, adjacency)

    # TRUNK — seam between the two most distant points
    # No directional bias — we don't know which side is "back" on a thingamabob
    trunk_path = _find_shortest_path(main_start, main_end, adjacency, vertices)
    _add_path_to_seams(trunk_path, seam_edges)
    trunk_set = set(trunk_path)

    # BRANCHES — connect each remaining protrusion to the trunk
    main_tips = {main_start, main_end}
    for protrusion in protrusions:
        tip = protrusion.tip_vertex
        if tip in main_tips:
            continue  # Already part of the trunk

        # Find the nearest trunk vertex to this protrusion's base
        base_center = np.mean(vertices[protrusion.base_vertices], axis=0)
        branch_point = _find_nearest_vertex_in_set(base_center, vertices, trunk_set)
        if branch_point is None:
            branch_point = main_start

        # Route from trunk to this appendage tip
        # Bias toward the inner surface (toward body center)
        inner_dir = _get_inner_direction(vertices, protrusion, body_center, 0)
        branch_path = _find_path_biased(
            branch_point, tip, adjacency, vertices,
            bias_vector=inner_dir,
            bias_vector_strength=0.3,  # Lighter bias — less predictable shapes
        )
        _add_path_to_seams(branch_path, seam_edges)
        # Add branch vertices to trunk set so future branches can connect to them too
        trunk_set.update(branch_path)

    # Fallback — if nothing was found, just do longest-axis seam
    if len(seam_edges) < 2:
        start_idx, end_idx = _find_farthest_pair(vertices, adjacency)
        fallback = _find_shortest_path(start_idx, end_idx, adjacency, vertices)
        _add_path_to_seams(fallback, seam_edges)

    return seam_edges


# ===========================================================================
#  LEGACY ENTRY POINT — defaults to Character mode
# ===========================================================================

def generate_seams(obj: bpy.types.Object) -> Set[Tuple[int, int]]:
    """Legacy entry point. Uses Character mode by default."""
    return generate_seams_character(obj)


# ===========================================================================
#  SHARED: apply_seams_to_mesh
# ===========================================================================

def apply_seams_to_mesh(obj: bpy.types.Object, seam_edges: Set[Tuple[int, int]]):
    """Mark edges as seams in Blender."""
    mesh = obj.data

    for edge in mesh.edges:
        edge.use_seam = False

    edge_lookup = {}
    for edge in mesh.edges:
        key = tuple(sorted((edge.vertices[0], edge.vertices[1])))
        edge_lookup[key] = edge

    marked = 0
    for v1, v2 in seam_edges:
        key = tuple(sorted((v1, v2)))
        if key in edge_lookup:
            edge_lookup[key].use_seam = True
            marked += 1

    return marked


# ===========================================================================
#  HELPER FUNCTIONS
# ===========================================================================

def _is_below(vertices, protrusion, body_center, up_axis):
    """Is this protrusion below the body center? (legs vs arms)"""
    return vertices[protrusion.tip_vertex][up_axis] < body_center[up_axis]


def _get_inner_direction(vertices, protrusion, body_center, sym_axis):
    """Get the 'inner' direction for a limb — toward body center, perpendicular to limb."""
    tip_pos = vertices[protrusion.tip_vertex]
    base_center = np.mean(vertices[protrusion.base_vertices], axis=0)
    limb_dir = tip_pos - base_center
    limb_length = np.linalg.norm(limb_dir)

    if limb_length < 1e-8:
        result = np.zeros(3)
        result[sym_axis] = 1.0
        return result

    limb_dir = limb_dir / limb_length
    to_body = body_center - base_center
    inner_dir = to_body - np.dot(to_body, limb_dir) * limb_dir
    inner_length = np.linalg.norm(inner_dir)

    if inner_length < 1e-8:
        result = np.zeros(3)
        result[sym_axis] = 1.0
        return result

    return inner_dir / inner_length


def _add_path_to_seams(path, seam_edges):
    """Add all edges along a path to the seam set."""
    for i in range(len(path) - 1):
        seam_edges.add(tuple(sorted((path[i], path[i + 1]))))


def _get_center_tolerance(vertices, sym_axis):
    """How wide the 'center zone' should be (5% of mesh width)."""
    bbox_size = vertices.max(axis=0) - vertices.min(axis=0)
    return max(bbox_size[sym_axis] * 0.05, 0.001)


def _find_nearest_vertex(position, vertices):
    """Find the vertex closest to a 3D position."""
    distances = np.linalg.norm(vertices - position, axis=1)
    return int(np.argmin(distances))


def _find_nearest_vertex_in_set(position, vertices, vertex_set):
    """Find the vertex in a set closest to a 3D position."""
    if not vertex_set:
        return None
    indices = list(vertex_set)
    distances = np.linalg.norm(vertices[indices] - position, axis=1)
    return indices[int(np.argmin(distances))]


def _find_farthest_pair(vertices, adjacency):
    """
    Find the two vertices that are farthest apart on the mesh surface.
    Used to determine the "long axis" of a shape.

    Uses the double-BFS trick: BFS from a random vertex to find the farthest,
    then BFS from THAT vertex to find the true farthest. Fast and reliable.
    """
    # First BFS from vertex 0
    dists1 = _bfs_distances_simple(0, adjacency, len(vertices))
    far1 = int(np.argmax(dists1))

    # Second BFS from the farthest point found
    dists2 = _bfs_distances_simple(far1, adjacency, len(vertices))
    far2 = int(np.argmax(dists2))

    return far1, far2


def _find_farthest_protrusion_pair(vertices, protrusions):
    """Find the two protrusion tips that are farthest apart in 3D space."""
    max_dist = 0.0
    best_pair = (protrusions[0].tip_vertex, protrusions[1].tip_vertex)

    for i in range(len(protrusions)):
        for j in range(i + 1, len(protrusions)):
            tip_i = protrusions[i].tip_vertex
            tip_j = protrusions[j].tip_vertex
            dist = float(np.linalg.norm(vertices[tip_i] - vertices[tip_j]))
            if dist > max_dist:
                max_dist = dist
                best_pair = (tip_i, tip_j)

    return best_pair


def _bfs_distances_simple(source, adjacency, num_vertices):
    """Simple unweighted BFS distance (hop count). Fast for finding farthest pair."""
    dist = np.full(num_vertices, -1, dtype=int)
    dist[source] = 0
    queue = [source]
    while queue:
        current = queue.pop(0)
        for neighbor in adjacency.get(current, []):
            if dist[neighbor] == -1:
                dist[neighbor] = dist[current] + 1
                queue.append(neighbor)
    # Replace unreachable with 0
    dist[dist == -1] = 0
    return dist


# ===========================================================================
#  PATHFINDING
# ===========================================================================

def _build_adjacency(num_vertices, edges):
    """Build vertex adjacency lookup from edge array."""
    adj = {i: [] for i in range(num_vertices)}
    for v1, v2 in edges:
        adj[int(v1)].append(int(v2))
        adj[int(v2)].append(int(v1))
    return adj


def _find_shortest_path(start, end, adjacency, vertices, max_steps=10000):
    """Standard Dijkstra shortest path along mesh edges."""
    if start == end:
        return [start]

    dist = {start: 0.0}
    prev = {}
    heap = [(0.0, start)]
    visited = set()

    while heap:
        d, current = heapq.heappop(heap)
        if current in visited:
            continue
        visited.add(current)
        if current == end:
            break
        if len(visited) > max_steps:
            break

        for neighbor in adjacency.get(current, []):
            if neighbor in visited:
                continue
            edge_len = float(np.linalg.norm(vertices[neighbor] - vertices[current]))
            new_dist = d + edge_len
            if neighbor not in dist or new_dist < dist[neighbor]:
                dist[neighbor] = new_dist
                prev[neighbor] = current
                heapq.heappush(heap, (new_dist, neighbor))

    path = []
    current = end
    while current in prev:
        path.append(current)
        current = prev[current]
    if current == start:
        path.append(start)
        path.reverse()
        return path
    return [start, end]


def _find_path_biased(
    start, end, adjacency, vertices,
    bias_axis=None, bias_direction=1.0, bias_strength=0.0,
    bias_vector=None, bias_vector_strength=0.0,
    max_steps=10000,
):
    """
    Shortest path with directional bias.
    bias_axis/direction: prefer one side of an axis (e.g., back of character)
    bias_vector/strength: prefer a specific 3D direction (e.g., inner surface)
    """
    if start == end:
        return [start]

    axis_min = axis_range = 0.0
    if bias_axis is not None and bias_strength > 0:
        axis_min = float(vertices[:, bias_axis].min())
        axis_range = float(vertices[:, bias_axis].max()) - axis_min
        if axis_range < 1e-8:
            bias_strength = 0.0

    start_pos = vertices[start]
    dist = {start: 0.0}
    prev = {}
    heap = [(0.0, start)]
    visited = set()

    while heap:
        d, current = heapq.heappop(heap)
        if current in visited:
            continue
        visited.add(current)
        if current == end:
            break
        if len(visited) > max_steps:
            break

        for neighbor in adjacency.get(current, []):
            if neighbor in visited:
                continue

            edge_len = float(np.linalg.norm(vertices[neighbor] - vertices[current]))
            penalty = 0.0

            if bias_axis is not None and bias_strength > 0:
                normalized = (vertices[neighbor][bias_axis] - axis_min) / axis_range
                if bias_direction > 0:
                    penalty += (1.0 - normalized) * bias_strength * edge_len
                else:
                    penalty += normalized * bias_strength * edge_len

            if bias_vector is not None and bias_vector_strength > 0:
                neighbor_rel = vertices[neighbor] - start_pos
                alignment = float(np.dot(neighbor_rel, bias_vector))
                penalty += max(0.0, -alignment) * bias_vector_strength

            new_dist = d + edge_len + penalty
            if neighbor not in dist or new_dist < dist[neighbor]:
                dist[neighbor] = new_dist
                prev[neighbor] = current
                heapq.heappush(heap, (new_dist, neighbor))

    path = []
    current = end
    while current in prev:
        path.append(current)
        current = prev[current]
    if current == start:
        path.append(start)
        path.reverse()
        return path
    return [start, end]
