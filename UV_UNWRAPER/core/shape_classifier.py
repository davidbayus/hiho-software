"""
Shape Classifier — Figuring Out What Kind of Shape You're Looking At

Before we can pick the right seam strategy, we need to know what we're
dealing with. Is it a ball? A tube? A flat plate? Something with holes?

This module looks at the shape's geometry and classifies it into one of
these sub-types:

    BLOB     — compact, roughly spherical (rocks, potions, hats, heads)
    TUBE     — elongated, like a cylinder or pipe (scarves, belts, macaroni, snakes)
    FLAT     — plate-like, thin in one dimension (shields, books, leaves, coins)
    BRANCHING — has multiple appendages (trees, coral, tentacle creatures)

How it works:
1. PCA (Principal Component Analysis) — looks at how the shape is spread
   out in 3D space. A tube is spread along one axis. A flat shape is spread
   along two axes but thin along the third.
2. Euler Characteristic — counts vertices, edges, faces to detect holes.
   A donut has holes. A ball doesn't. Holes need extra seam cuts.
3. Protrusion count — if the shape has many sticky-out parts, it's branching.
"""

import numpy as np
from typing import Tuple, Optional
from enum import Enum


class ShapeType(Enum):
    """The shape sub-types our seam strategies can handle."""
    BLOB = "blob"           # Compact, convex-ish (rock, potion, hat)
    TUBE = "tube"           # Elongated cylinder (macaroni, scarf, belt)
    FLAT = "flat"           # Plate-like (shield, book, leaf)
    BRANCHING = "branching" # Multi-limbed without clear body (tree, coral)


def classify_shape(
    vertices: np.ndarray,
    edges: np.ndarray,
    faces: np.ndarray,
    num_protrusions: int = 0,
) -> Tuple[ShapeType, dict]:
    """
    Look at a mesh and figure out what kind of shape it is.

    Args:
        vertices: Vertex positions (Nx3 array)
        edges: Edge connections (Mx2 array)
        faces: Face vertex indices (list of tuples/arrays)
        num_protrusions: Number of detected protrusions (from protrusion.py)

    Returns:
        Tuple of (ShapeType, info_dict with metrics used for classification)
    """
    info = {}

    # --- PCA: How is the shape spread out in space? ---
    eigenvalues, eigenvectors = _compute_pca(vertices)
    info['eigenvalues'] = eigenvalues
    info['eigenvectors'] = eigenvectors

    # Elongation: how much longer is the shape along its main axis
    # compared to its second axis?
    # High elongation (>3) = tube-like
    elongation = eigenvalues[0] / max(eigenvalues[1], 1e-10)
    info['elongation'] = elongation

    # Flatness: how much wider/taller is the shape compared to its thickness?
    # High flatness (>4) with low elongation = plate-like
    flatness = eigenvalues[1] / max(eigenvalues[2], 1e-10)
    info['flatness'] = flatness

    # Tubularity: the two smaller eigenvalues should be similar for a tube
    # (circular cross-section). If they're very different, it's more like a ribbon.
    if eigenvalues[1] > 1e-10:
        tubularity = min(eigenvalues[1], eigenvalues[2]) / max(eigenvalues[1], eigenvalues[2])
    else:
        tubularity = 1.0
    info['tubularity'] = tubularity

    # --- Euler Characteristic: Does it have holes? ---
    genus = compute_genus(len(vertices), len(edges), len(faces))
    info['genus'] = genus

    # --- Classification logic ---
    # Many protrusions = branching (regardless of shape metrics)
    if num_protrusions >= 3:
        return ShapeType.BRANCHING, info

    # Elongated = tube (the macaroni case!)
    # Elongation > 3 means the shape is at least 3x longer than wide
    # Tubularity > 0.3 means the cross-section isn't too weird
    if elongation > 3.0 and tubularity > 0.25:
        return ShapeType.TUBE, info

    # Very elongated even with low tubularity = still a tube (ribbon-like)
    if elongation > 5.0:
        return ShapeType.TUBE, info

    # Flat = one dimension much thinner than the other two
    # Flatness > 4 and not elongated = plate/shield/leaf
    if flatness > 4.0 and elongation < 2.5:
        return ShapeType.FLAT, info

    # Default = blob (compact, roughly equal in all dimensions)
    return ShapeType.BLOB, info


def _compute_pca(vertices: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """
    Principal Component Analysis on vertex positions.

    Returns eigenvalues (sorted largest→smallest) and corresponding
    eigenvectors. The eigenvalues tell us how "spread out" the shape is
    along each principal direction.

    Think of it like putting the shape in a box and measuring the box:
    - eigenvalue[0] = length of the longest side
    - eigenvalue[1] = length of the medium side
    - eigenvalue[2] = length of the shortest side
    """
    # Center the vertices
    centered = vertices - np.mean(vertices, axis=0)

    # Covariance matrix (3x3)
    cov = np.cov(centered.T)

    # Eigendecomposition
    eigenvalues, eigenvectors = np.linalg.eigh(cov)

    # Sort largest first
    order = np.argsort(eigenvalues)[::-1]
    eigenvalues = eigenvalues[order]
    eigenvectors = eigenvectors[:, order]

    # Clamp negative eigenvalues to zero (numerical noise)
    eigenvalues = np.maximum(eigenvalues, 0.0)

    return eigenvalues, eigenvectors


def compute_genus(num_vertices: int, num_edges: int, num_faces: int) -> int:
    """
    Compute the topological genus (number of "holes") in a mesh.

    Uses the Euler characteristic: χ = V - E + F
    For a closed mesh: genus = (2 - χ) / 2

    A sphere has genus 0 (no holes).
    A donut has genus 1 (one hole).
    A pretzel has genus 3 (three holes).

    If the mesh isn't watertight, the result is approximate but still useful.
    """
    euler = num_vertices - num_edges + num_faces
    # For a closed orientable surface: χ = 2 - 2g
    # So g = (2 - χ) / 2
    genus = max(0, (2 - euler) // 2)
    return genus


def get_principal_axis(vertices: np.ndarray) -> np.ndarray:
    """
    Get the main direction the shape extends along.
    For a tube, this is the direction the tube runs.
    For a flat shape, this is the widest direction.

    Returns a unit vector (3D direction).
    """
    _, eigenvectors = _compute_pca(vertices)
    return eigenvectors[:, 0]  # First principal component = longest direction


def get_flatness_normal(vertices: np.ndarray) -> np.ndarray:
    """
    Get the direction the shape is thinnest along.
    For a flat shape (plate, shield), this is the "face normal" direction.

    Returns a unit vector (3D direction).
    """
    _, eigenvectors = _compute_pca(vertices)
    return eigenvectors[:, 2]  # Third principal component = thinnest direction
