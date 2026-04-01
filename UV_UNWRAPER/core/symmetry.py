"""
Symmetry Detection
Finds the mirror plane of a mesh — like finding the spine of a butterfly.

Most kid-made characters are symmetrical (same on left and right).
If we can detect that, we know exactly where to place the center-back seam —
the single most useful seam for any character.

How it works:
1. Look at every vertex (point) on the mesh
2. For each axis (X, Y, Z), check: does every point on one side
   have a matching point on the other side?
3. The axis with the best mirror match is the symmetry plane
4. X-axis symmetry is most common (left-right mirror in Blender)
"""

import numpy as np
from typing import Optional


def detect_symmetry_axis(
    vertices: np.ndarray,
    tolerance: float = 0.01,
) -> Optional[int]:
    """
    Figure out which axis (X=0, Y=1, Z=2) the mesh is symmetrical across.

    Think of it like holding a mirror up to the mesh along each axis
    and checking which one gives the best reflection.

    Args:
        vertices: All the vertex positions as an Nx3 array.
        tolerance: How close a mirror-match needs to be (relative to mesh size).
                   Bigger = more forgiving of imperfect symmetry.

    Returns:
        0 (X-axis), 1 (Y-axis), or 2 (Z-axis) if symmetry is found.
        None if the mesh isn't symmetrical on any axis.
    """
    if len(vertices) < 4:
        return None

    # Scale tolerance relative to mesh size so it works on tiny and huge meshes
    bbox_size = vertices.max(axis=0) - vertices.min(axis=0)
    max_dim = bbox_size.max()
    if max_dim < 1e-8:
        return None
    abs_tolerance = tolerance * max_dim

    best_axis = None
    best_score = 0.0

    for axis in range(3):
        score = _score_symmetry(vertices, axis, abs_tolerance)
        if score > best_score:
            best_score = score
            best_axis = axis

    # Need at least 70% of vertices to have a mirror match
    if best_score >= 0.70:
        return best_axis
    return None


def _score_symmetry(
    vertices: np.ndarray,
    axis: int,
    tolerance: float,
) -> float:
    """
    Score how symmetrical the mesh is across one axis.
    Returns a value from 0.0 (not symmetrical) to 1.0 (perfectly mirrored).
    """
    # Find the center of the mesh along this axis
    center = np.median(vertices[:, axis])

    # Split vertices into "positive side" and "negative side" of center
    # Vertices very close to center are on the seam line — they count as matched
    on_center = np.abs(vertices[:, axis] - center) < tolerance
    positive = vertices[vertices[:, axis] > center + tolerance]
    negative = vertices[vertices[:, axis] < center - tolerance]

    if len(positive) == 0 or len(negative) == 0:
        return 0.0

    # For each vertex on the positive side, try to find its mirror on the negative side
    matched = 0
    for vert in positive:
        # Create the mirrored position (flip across the center on this axis)
        mirrored = vert.copy()
        mirrored[axis] = 2 * center - mirrored[axis]

        # Find the closest vertex on the negative side
        distances = np.linalg.norm(negative - mirrored, axis=1)
        if distances.min() < tolerance:
            matched += 1

    total_testable = len(positive) + len(negative)
    # Each matched vertex on positive side implies its pair on negative is also matched
    match_ratio = (2 * matched + np.sum(on_center)) / len(vertices)
    return min(match_ratio, 1.0)


def get_center_vertices(
    vertices: np.ndarray,
    axis: int,
    tolerance: float = 0.01,
) -> np.ndarray:
    """
    Get the indices of vertices that sit right on the symmetry line.
    These are the vertices where the center-back seam will go.

    Args:
        vertices: All vertex positions.
        axis: Which axis the symmetry is on (0=X, 1=Y, 2=Z).
        tolerance: How close to center counts as "on the line."

    Returns:
        Array of vertex indices that are on the center line.
    """
    bbox_size = vertices.max(axis=0) - vertices.min(axis=0)
    max_dim = bbox_size.max()
    abs_tolerance = tolerance * max_dim

    center = np.median(vertices[:, axis])
    mask = np.abs(vertices[:, axis] - center) < abs_tolerance
    return np.where(mask)[0]
