# Curvature-Based Seam Placement — Research Notes

**Date:** April 2, 2026
**Purpose:** Understand how Substance Painter (and similar tools) decide where to place UV seams, so PaWrappa can adopt the same approach.

---

## The Big Insight

SP doesn't place seams by understanding what the shape IS (biped, prop, creature). It places seams by reading the GEOMETRY — specifically, where the surface bends sharply. Sharp bends = natural seam locations. This works on any shape without classifying it first.

**PaWrappa today:** "What kind of shape is this?" → run different algorithm per shape type
**SP approach:** "Where does this surface bend?" → one algorithm for everything

---

## How It Actually Works (Three Steps)

### Step 1: Score Every Edge

For each edge shared by two faces, measure the angle between those faces' normals. This is called the **dihedral angle**.

- Two faces that are flat/coplanar → angle near 0° → smooth surface, bad seam location
- Two faces at a sharp bend → angle near 90°+ → crease, good seam location

Blender gives us this for free: `bmesh.types.BMEdge.calc_face_angle()` returns this angle in radians.

**The weight formula used by production tools:**
```
edge_weight = 1 - cos²(dihedral_angle)
```
- Flat edge (0°): weight = 0 (never cut here)
- 45° bend: weight = 0.5
- 90° bend: weight = 1.0 (cut here)

**Bonus trick — concavity weighting:**
Blender also has `calc_face_angle_signed()` — concave edges (creases, armpits, crevices) get different treatment than convex edges (outer ridges). Concave edges are ~12x more preferred as seam locations because seams hide in crevices.

### Step 2: Cluster Faces Into Islands

This is NOT an edge-selection problem — it's a face-grouping problem. You group faces into clusters where all faces within a cluster point roughly the same direction (similar normals). The boundaries between clusters become seams.

**The algorithm (Lloyd-style clustering):**
1. Pick K seed faces (spread across the mesh)
2. Grow each seed into a "chart" by adding neighboring faces, preferring faces with:
   - Low edge weight to cross (smooth transitions)
   - Similar normal to the chart's average normal
3. Recompute chart centers
4. Re-grow from new centers
5. Repeat until stable (~5-50 iterations)

**The cost of adding a face to a chart:**
```
cost = alpha × distance_from_center + beta × (1 - dot(face_normal, chart_normal))
```
The beta term is key — it keeps each chart roughly flat/developable (good for UV unwrapping).

### Step 3: Extract Seams

Any mesh edge where the two adjacent faces belong to different charts → that edge is a seam. Trivial once you have the clustering.

---

## How Island Count Is Controlled

Island count is NEVER a direct input. It's always controlled indirectly by a quality threshold:

| Tool | What the slider controls | Effect |
|------|------------------------|--------|
| Substance Painter | Max allowed stretch | Lower tolerance → more islands |
| xatlas | maxCost parameter | Lower cost → more charts |
| Houdini UV AutoSeam | Merge Threshold (0-1) | 0 = many islands, 1 = few islands |

**For PaWrappa's UI:** A slider labeled something like "Detail Level" or "How Many Pieces" that maps to the merge threshold internally. Left = fewer islands (SP-style, good for characters), Right = more islands (Smart UV style, good for hard-surface).

---

## What Blender Gives Us for Free

| API | What it does |
|-----|-------------|
| `BMEdge.calc_face_angle()` | Dihedral angle between adjacent faces — THE curvature signal |
| `BMEdge.calc_face_angle_signed()` | Signed version — distinguishes concave from convex |
| `edge.is_boundary` | Detects boundary edges (single face) |
| `polygon.normal` | Face normal vector |
| `polygon.center` | Face centroid |

We don't need numpy for the core algorithm. BMesh handles the geometry queries.

---

## Open Source References

1. **kugelrund/mesh_segmentation** — Blender addon doing spectral clustering for mesh segmentation. Uses numpy/scipy. Most directly relevant reference.
2. **xatlas** (github.com/jpcy/xatlas) — C++ but has Python bindings on PyPI (`pip install xatlas`). The canonical face-clustering implementation.
3. **CGAL Surface_mesh_segmentation docs** — Best-written explanation of the math.

---

## What's Easy vs Hard to Build

**Easy (we can do this):**
- Computing dihedral angles for all edges (BMesh does it)
- Simple threshold-based seam selection (select sharp edges)
- Converting face clusters to seam edges
- Merging small islands by removing seams between them

**Medium (doable with care):**
- Lloyd-style face clustering with normal-deviation metric
- Controlling island count via merge threshold
- Ensuring each island has valid topology

**Hard (probably skip for now):**
- Spectral clustering (eigendecomposition, tricky tuning)
- Graph-cut energy minimization (needs solver library)
- Matching SP quality exactly (years of refinement)

---

## Proposed New Architecture for PaWrappa

Instead of three shape-specific algorithms, one universal algorithm with a quality slider:

1. **Score edges** — dihedral angles, concavity-weighted
2. **Cluster faces** — Lloyd iteration with planarity constraint
3. **Extract seams** — boundaries between clusters
4. **User control** — merge threshold slider (few islands ↔ many islands)
5. **+Y back-bias** — when two seam placements are equal, prefer the one facing away from camera

The three buttons could become presets:
- "Character" = low island count preset (merge threshold high)
- "Detailed" = high island count preset (merge threshold low)
- "Auto" = adaptive based on mesh complexity

---

## Next Steps

1. Build a minimal proof-of-concept: just Step 1 (score edges) and visualize which edges score highest — compare against SP's seam placement on the same mesh
2. If the edge scores match SP's choices, proceed to Step 2 (clustering)
3. If they don't match, figure out what SP weighs differently before building more
