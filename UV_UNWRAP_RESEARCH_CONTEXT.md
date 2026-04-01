# Automatic UV Unwrapping — Research Context & Opportunity Analysis
**Created:** March 30, 2026
**Author:** David Bayus + Claude
**Purpose:** Research landscape for building or improving automatic UV unwrapping in the K-12 Blender addon. Companion doc to `QUAD_REMESHER_RESEARCH_CONTEXT.md`.

---

## 1. WHY UV UNWRAPPING IS A BOTTLENECK

### The Problem in ART 102
UV unwrapping is Phase 4 in David's 8-phase character pipeline:

**Blockout → Voxel Remesh → Quad Remesh → UV UNWRAP → Multires Sculpt & Bake → Texture Paint → Rig → Export**

It's the gateway to painting. A student can't texture their character until the UVs are done. And UV unwrapping is where students hit a wall — it's the most abstract, least intuitive step in the entire pipeline. There's no physical metaphor for it. You can't explain "flattening a 3D surface into 2D" the way you can explain "sculpt clay" or "paint with a brush."

### What Makes It Hard for Students
- **Requires Edit Mode** — beginners constantly try to unwrap in Object Mode and nothing happens
- **Seam placement is an art** — where to cut the mesh requires understanding that students don't have yet
- **Stretching is invisible until you paint** — students don't know their UVs are bad until they try to texture
- **Blender's Smart UV Project** works OK on simple objects but produces fragmented, unpredictable results on characters
- **The UV Editor is a second workspace** that students have to learn simultaneously
- **Non-manifold geometry causes silent failures** — Blender won't tell you *why* the unwrap looks wrong

### What David Currently Does
In ART 102, David teaches UV unwrapping as a manual step with guided seam placement. Students learn to mark seams along natural body breaks (center line, under arms, inner legs, hairline, neck) and use Blender's Unwrap (angle-based) method. It works, but it requires significant demo time and student practice. For the K-12 addon, this step needs to be automatic or semi-automatic — a kid shouldn't have to understand UV space to paint their character.

### The Addon Goal
**"Paint My Character" button:** When a kid enters the paint workspace, UVs should just *exist*. No seam marking, no UV editor, no flattening concepts. The character is paintable. Period.

---

## 2. THE COMPETITIVE LANDSCAPE

### Substance Painter Auto UV (PAID — Industry Reference)
- **Who:** Adobe (Substance 3D Painter, $22.99/mo or $219.99/yr)
- **What it does:** Automatic UV unwrapping built into the texturing application. One click, reasonable results.
- **Strengths:**
  - Consistent texel density across the model
  - Handles complex geometry reasonably well
  - Integrated into the painting workflow (UVs happen transparently)
- **Limitations:**
  - Still in beta — hard surface objects can be problematic
  - UVs can be very dense/packed (not ideal for hand-editing, but we don't care about hand-editing for kids)
  - PAID — $22.99/month. Eliminated from David's pipeline as of SP26.
- **Key insight:** Substance's auto-UV isn't magic — it's just *good enough and invisible*. That's the bar.

### ZBrush UV Master (PAID — Best Auto-UV for Characters)
- **Who:** Maxon (part of ZBrush)
- **What it does:** Single-click UV generation with intelligent seam placement
- **Strengths:**
  - Uses Ambient Occlusion to place seams in least-visible areas automatically
  - Minimal texture distortion — best pixel-per-polygon ratio
  - Handles organic character models extremely well
  - Polygroup-aware unwrapping
  - Symmetry preservation
- **Limitations:**
  - ZBrush-only (not available in Blender)
  - Part of a paid commercial package
- **Key insight:** The AO-based seam placement is brilliant — hide seams where you can't see them. This is a design principle we should steal.

### Ministry of Flat (LICENSED — Best Standalone Algorithm)
- **Who:** Eskil Steenberg (quelsolaar.com)
- **What it does:** Fully automatic UV unwrapping using 25+ algorithms
- **Website:** https://www.quelsolaar.com/ministry_of_flat/
- **Strengths:**
  - Detects 20+ different topology types and approaches each differently
  - Robust to mesh errors (still produces UVs where other tools fail)
  - Licensed by Maxon for Cinema 4D's automatic unwrapping
  - Production-proven
- **Limitations:**
  - Not open source — available for licensing only
  - Not available as a Blender addon
- **Key insight:** The multi-algorithm approach (detect topology type → choose strategy) is the right architecture. One algorithm doesn't fit all geometry.

---

## 3. WHAT BLENDER CURRENTLY OFFERS (FREE)

### Unwrap (Angle-Based / Conformal)
- The default. Requires manual seam marking.
- Quality is good *if seams are well-placed* — which is the entire problem for beginners.
- Conformal mode preserves angles, Angle-Based is a hybrid.

### Smart UV Project
- Automatic — no seams needed.
- Analyzes geometry and splits into UV islands based on angle thresholds.
- **Problems:** Over-fragments complex models. Unpredictable island shapes. Poor for characters — body parts get split into random chunks. Not suitable for texture painting where you want recognizable UV layouts.

### SLIM (NEW in Blender 4.3)
- **Algorithm:** Scalable Local Injective Mappings (ETH Zurich)
- **Available via:** "Minimum Stretch" option in the UV menu
- **What it does:** Iterative unwrapping that preserves AREA much better than angle-based methods. Less distortion with fewer iterations.
- **Strengths:**
  - State-of-the-art distortion minimization
  - Works well even with minimal seams
  - Fast — 10 iterations comparable to existing methods' time
  - Better area preservation than angle-based (which only preserves angles)
- **Limitations:**
  - Still requires seam placement (it's a parameterization method, not a seam generator)
  - New in Blender — community still learning best practices
- **Key insight:** SLIM solves the *flattening quality* problem. The remaining problem is *where to cut*. If we can auto-generate good seams, SLIM + those seams = great UVs.

### Blender's Pack Islands
- Packs UV islands into the UV space efficiently
- Works fine — not a bottleneck

---

## 4. OPEN-SOURCE TOOLS & LIBRARIES

### Boundary First Flattening (BFF) — CMU Geometry Collective
- **GitHub:** https://github.com/GeometryCollective/boundary-first-flattening
- **Paper:** "Boundary First Flattening" by Rohan Sawhney & Keenan Crane (ACM TOG)
- **What it does:** Conformal surface parameterization with mathematically guaranteed minimal distortion
- **Strengths:**
  - Distortion guaranteed to be as low or lower than any other conformal mapping tool
  - Interactive editing of flattened mesh — direct control over boundary shape
  - Supports cone singularities (dramatically reduces area distortion)
  - Supports seamless maps (eliminates texture resolution artifacts across cuts)
  - Handles millions of triangles interactively
  - Linear method — faster than traditional linear methods
  - Free and open source
- **Limitations:**
  - Standalone application (not Blender-native)
  - Conformal only (preserves angles, not areas — though cone singularities help)
  - Still requires knowing WHERE to cut
- **License:** Open source
- **VERDICT: Best-in-class open-source flattening. Could be integrated into Blender addon for the parameterization step.**

### xatlas
- **GitHub:** https://github.com/jpcy/xatlas
- **What it does:** Automatic chart generation, parameterization, and packing
- **Strengths:**
  - Small C++11 library, no external dependencies
  - Fully automatic — generates seams, unwraps, and packs in one pipeline
  - Used by The Witness (game) — production-proven
  - Easy integration (just xatlas.cpp and xatlas.h)
  - Generates unique texture coordinates suitable for baking or painting
- **Limitations:**
  - Designed for lightmap baking — seam placement optimized for that, not character painting
  - Results can be fragmented (many small islands)
  - No semantic awareness (doesn't understand "this is an arm")
- **License:** MIT
- **VERDICT: Good reference for the full auto pipeline (segment → parameterize → pack). Seam placement logic is the weak point for our use case.**

### Blender's Internal UV Code
- Blender's UV unwrapping is built on well-known algorithms (ABF++, LSCM, now SLIM)
- The seam-related code is in the Blender source: `source/blender/editors/uvedit/`
- Smart UV Project's angle-based segmentation is the closest thing to auto-seam in Blender
- We can extend Blender's existing UV operators via Python API

---

## 5. CUTTING-EDGE RESEARCH (2024–2025)

### GraphSeam — Autodesk (2024)
- **Paper:** "GraphSeam: Supervised Graph Learning Framework for Semantic UV Mapping"
- **PDF:** https://www.research.autodesk.com/app/uploads/2024/08/GraphSeam-paper.pdf
- **What it does:** Uses Graph Neural Networks to automatically generate UV seam suggestions that replicate an artist's seam style
- **Key innovation:** Learns WHERE to cut from examples of artist-unwrapped models. Places seams along semantic boundaries (arm/torso junction, head/neck, etc.)
- **Why it matters:** This is exactly what we need — semantic seam placement. A GNN trained on character models could learn "always cut under the arm, along the center back, around the hairline" without being told.
- **Status:** Research paper, not a released tool. But the approach is implementable.

### PartUV — SIGGRAPH Asia 2025
- **Paper:** "PartUV: Part-Based UV Unwrapping of 3D Meshes"
- **GitHub:** https://github.com/EricWang12/PartUV
- **What it does:** Semantic-aware UV unwrapping. Segments mesh into meaningful parts (head, torso, arms, legs) first, then unwraps each part separately.
- **Key innovation:** Uses learned part decomposition (PartField) combined with geometric heuristics. Produces 1/31 as many charts as Blender on common shapes.
- **Why it matters:** Part-based unwrapping is EXACTLY the right approach for characters. A kid's character mesh has arms, legs, a head, a body — the unwrapper should know that and cut accordingly.
- **Status:** Code available on GitHub. SIGGRAPH Asia 2025 publication.
- **VERDICT: Most promising research direction for our use case. Investigate integration.**

### SeamCrafter — 2025
- **Paper:** "SeamCrafter: Enhancing Mesh Seam Generation for Artist UV Unwrapping via Reinforcement Learning"
- **arXiv:** https://arxiv.org/abs/2509.20725
- **What it does:** GPT-style autoregressive seam generator using reinforcement learning (DPO) to produce artist-quality seam placements
- **Key innovation:** Dual-branch point-cloud encoder that captures both topological and geometric features. Fine-tuned with preference optimization.
- **Why it matters:** The RL approach means it can learn to balance competing goals (low distortion vs. few islands vs. hidden seams) from preference data rather than hard-coded rules.

### ArtUV — 2025
- **Paper:** "ArtUV: Artist-Style UV Unwrapping"
- **What it does:** Learns to replicate specific artist UV styles
- **Relevance:** Lower priority — we want one good default, not stylistic variety

---

## 6. THE OPPORTUNITY: WHAT DOESN'T EXIST YET

Here's the gap in the market:

**Nobody has built a free, Blender-native, one-click auto-UV tool optimized for character models.**

The pieces all exist:
1. **Seam generation** → PartUV's part-based decomposition or GraphSeam's learned placement (know WHERE to cut on a character)
2. **Parameterization** → SLIM (already in Blender 4.3) or BFF (open source, best-in-class conformal) (know HOW to flatten with minimal distortion)
3. **Packing** → Blender's Pack Islands (already works fine)
4. **Character awareness** → PartUV/PartField for semantic segmentation (know WHAT the parts are)

Nobody has combined them into a single Blender operator that says: "Here's a character mesh. I'll figure out where to cut it, flatten it with minimal distortion, and pack the UVs. You can paint now."

### Why This Is Easier Than the Quad Remesher Problem
The quad remesher problem is fundamentally hard — you're generating new geometry. UV unwrapping is *mapping* existing geometry to 2D. The math is better understood, the open-source tools are more mature, and the research is further along. The hard part (seam placement) now has multiple ML-based solutions published with code.

### The Realistic V1
For the addon's first version, we might not even need ML:

1. **Detect symmetry** (most kid characters will be symmetrical)
2. **Place center-back seam** (always works for humanoids)
3. **Place limb seams** (detect protrusions, cut along inner surfaces — the ZBrush UV Master approach of hiding seams in occluded areas)
4. **Use SLIM** for parameterization (already in Blender)
5. **Pack**

This is a heuristic-based approach that handles 80% of kid-made characters. The ML approaches (PartUV, GraphSeam) are the Phase 2 upgrade.

---

## 7. RECOMMENDED BUILD STRATEGY

### Phase 1: Heuristic Auto-UV for Characters (MVP)
**Goal:** One-button UV unwrapping that works on typical student character meshes.

1. **Symmetry detection** — find the mirror plane, place a center seam
2. **Protrusion detection** — find limbs/appendages, place seams along inner surfaces (least visible)
3. **Head/body separation** — detect neck constriction, separate head UV island
4. **Use Blender's SLIM** for parameterization (it's built in as of 4.3)
5. **Pack using Blender's built-in packer**
6. **Fallback:** If heuristics fail, fall back to Smart UV Project with optimized angle threshold

**Success criteria:** Produces paintable UVs on 80%+ of typical student character meshes with no visible stretching in painted areas.

### Phase 2: Part-Based Semantic UV (ML-Enhanced)
**Goal:** Use learned part decomposition for smarter seam placement.

1. **Integrate PartUV** or similar part decomposition model
2. **Train/fine-tune on character meshes** — specifically the kind of chunky, stylized characters kids make
3. **AO-based seam hiding** — use ambient occlusion to push seams into crevices (steal from ZBrush UV Master)
4. **Texel density equalization** — ensure consistent resolution across all body parts

### Phase 3: Full Auto Pipeline Integration
**Goal:** UV unwrapping is completely invisible — it just happens when you enter paint mode.

1. **Auto-UV on mode switch** — when kid clicks "Paint My Character," UVs generate silently
2. **Adaptive quality** — detect hardware capability, adjust UV resolution accordingly
3. **Live re-UV on mesh changes** — if kid modifies the sculpt, UVs update automatically

---

## 8. KEY TECHNICAL DETAILS FOR IMPLEMENTATION

### Blender Python API for UV Operations
```python
# Mark seams
bpy.ops.mesh.mark_seam(clear=False)

# Unwrap with SLIM (Blender 4.3+)
bpy.ops.uv.unwrap(method='MINIMUM_STRETCH')

# Smart UV Project (fallback)
bpy.ops.uv.smart_project(angle_limit=66, margin_method='SCALED', island_margin=0.01)

# Pack Islands
bpy.ops.uv.pack_islands(margin=0.01)

# Access UV data
mesh = bpy.context.active_object.data
uv_layer = mesh.uv_layers.active
```

### Symmetry Detection Approach
```
1. Compute bounding box center
2. Test mesh symmetry across X, Y, Z planes
3. For each candidate plane, measure vertex-pair distances
4. If mean distance < threshold → symmetry confirmed on that axis
5. Place center seam along the symmetry plane
```

### Protrusion Detection Approach
```
1. Compute mesh skeleton (medial axis or Laplacian-based)
2. Identify branch points in the skeleton → these are limb junctions
3. At each junction, find the minimum cross-section loop → this is a natural seam location
4. For each limb, place seam along the inner surface (highest curvature concavity)
```

### Libraries That Could Help
| Library | What It Does | Relevance |
|---------|-------------|-----------|
| **BFF** | Best-in-class conformal flattening | Alternative to SLIM for parameterization |
| **xatlas** | Full auto UV pipeline | Reference for segment → flatten → pack |
| **PartUV / PartField** | Semantic part decomposition | Smart seam placement for characters |
| **trimesh** (Python) | Mesh analysis, skeletonization | Protrusion/limb detection |
| **scipy.spatial** | Convex hull, KD-trees, spatial analysis | Symmetry detection, part segmentation |
| **bmesh** (Blender) | Mesh manipulation | Direct mesh access in Blender |
| **numpy** | Numerical computing | Geometry calculations |

---

## 9. HOW THIS CONNECTS TO THE ADDON

### In the Addon Pipeline
The addon reorganizes Blender around narrative intent. UV unwrapping should be **invisible** — it's technical plumbing, not a creative act. In the addon:

1. Kid sculpts/shapes their character in **"Build Your World"** workspace
2. Kid clicks **"Paint My Character"** to enter the paint workspace
3. **Behind the scenes:** addon auto-generates UVs using our tool
4. Kid paints. They never see the UV editor. They never mark a seam. They never think about flattening.

### Dependency on Quad Remesher
Good UVs depend on good topology. If the quad remesher produces clean quads with reasonable edge flow, the UV unwrapper's job is much easier. These two tools are deeply connected — they should be developed and tested together.

### Hardware Constraint
UV unwrapping is less computationally expensive than quad remeshing, but on low-end hardware (the "Scrap in a Box" target), we still need to be conscious of memory and processing time. The heuristic approach (Phase 1) should be fast. The ML approach (Phase 2) needs to be evaluated for low-end viability.

---

## 10. COMPARISON: DIFFICULTY VS. QUAD REMESHER

| Factor | Quad Remesher | UV Unwrapper |
|--------|--------------|--------------|
| **Algorithmic difficulty** | Very hard — generating new geometry | Moderate — mapping existing geometry |
| **Open-source maturity** | Limited (QRemeshify best option) | More mature (BFF, SLIM, xatlas) |
| **ML research available** | NeurCross (early) | PartUV, GraphSeam, SeamCrafter (multiple, code available) |
| **Blender integration** | QuadriFlow (poor quality) | SLIM (good quality, new in 4.3) |
| **What's missing** | The whole thing | Just the seam generation |
| **V1 feasibility** | Depends on QRemeshify fork | Heuristic approach is very feasible |

**Bottom line:** UV unwrapping is the more tractable problem. The parameterization is solved (SLIM). The packing is solved (Blender built-in). We just need to solve seam placement for characters — and there are now multiple published approaches with code for that.

---

## 11. NEXT STEPS

1. **Test SLIM** in Blender 5.0 — confirm it's available and working well
2. **Test Smart UV Project** with various angle thresholds on student character meshes — establish the baseline
3. **Prototype heuristic seam generator** — symmetry detection + protrusion detection + inner-surface seam placement
4. **Evaluate PartUV** — clone the repo, test on character meshes, assess quality and speed
5. **Build the "Paint My Character" operator** — combines seam generation + SLIM unwrap + pack into one button
6. **Test on actual ART 102 student work** — David provides character meshes at various pipeline stages

---

*This document maps the UV unwrapping landscape as of March 2026. The key insight: the hard problem (parameterization) is already solved in Blender. The remaining problem (seam placement for characters) has multiple promising approaches. This is more tractable than the quad remesher problem and should probably be tackled first or in parallel.*
