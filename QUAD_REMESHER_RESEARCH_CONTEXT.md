The best# Open-Source Quad Remesher for Blender — Research Context & Build Plan
**Created:** March 30, 2026
**Author:** David Bayus + Claude
**Purpose:** Everything needed to start building a free, open-source quad remesher Blender addon in Claude Code. This document is the single source of truth for the project.

---

## 1. WHY THIS EXISTS

### The Problem
David Bayus teaches a character creation pipeline in ART 102 at SJSU that depends on quad remeshing as a critical step. The pipeline:

**Blockout → Voxel Remesh → QUAD REMESH → UV Unwrap → Multires Sculpt & Bake → Texture Paint → Rig → Export**

Quad remesh is the step that converts messy voxel geometry into clean, animation-friendly quad topology (~2,000–5,000 faces). Everything downstream depends on it: UVs need clean quads, multires sculpting needs subdivision-friendly topology, rigging needs edge flow that follows the body.

Currently, this step uses **Exoside Quad Remesher** — a paid addon ($59.90 indie / $15.99/3mo subscription). The rest of the pipeline is 100% free (Blender, VHD Skinning addon, Mixamo). Blender's built-in QuadriFlow is not reliable enough for character work.

David is building a K-12 Blender addon (CADRE Lab project) that compresses this pipeline for younger students on low-end hardware. **A free quad remesher is a hard requirement** — you can't ship "free tools for every kid" with a paid dependency.

### The "Local Software" Thesis
David's broader argument: as AI collapses software development costs toward zero, the only remaining value is **craftsmanship** — software made with care for specific people. Building a quad remesher tuned for *K-12 character work on low-end machines* is local software in action. We don't need to beat Exoside for every use case. We need to beat it for *kids making characters*.

---

## 2. WHAT "GOOD ENOUGH" MEANS

### Target Use Case
- **Input:** Organic character sculpts post-voxel-remesh (messy triangle soup, ~50K–200K tris)
- **Output:** Clean quad-dominant mesh, 2,000–5,000 faces
- **Quality bar:** Good enough for UV unwrapping, multires sculpting, VHD skinning/rigging, and Mixamo auto-rig
- **Edge flow:** Should roughly follow body topology (limbs, torso, head) — doesn't need to be animation-studio perfect
- **Speed:** Under 30 seconds on a low-end machine (repurposed e-waste hardware, ~8GB RAM, integrated GPU)
- **UX:** One button. No parameters for V1. "Clean Up My Shape" — that's it.

### What We Do NOT Need
- Hard-surface remeshing (mechanical parts, architecture)
- Production-quality edge flow for feature film rigs
- Support for meshes over 500K tris
- Real-time performance
- Cross-platform standalone (Blender addon only)

---

## 3. THE COMPETITIVE LANDSCAPE

### Exoside Quad Remesher (The Gold Standard — PAID)
- **Price:** $59.90 perpetual indie (non-commercial) / $15.99 per 3 months (commercial)
- **Algorithm:** Same core as ZRemesher (ZBrush). Proprietary, not published as an academic paper. Based on global parameterization and cross-field computation.
- **Key features that make it great:**
  - Adaptive quad density (smaller quads on curved areas, larger on flat)
  - Edge flow control via smoothing groups, normals creasing, material IDs
  - Vertex color-driven density maps
  - Symmetry support
  - Hard edge detection
  - Handles organic AND hard-surface well
  - Fast (seconds, not minutes)
- **Documentation:** https://exoside.com/quadremesherdata/QuadRemesher_1.3_UserDoc.pdf
- **What's New in 1.4 (July 2025):** https://exoside.com/quadremesherdata/QuadRemesher_WhatsNew.pdf
- **Why we can't just use it:** Paid. Kills the free-tools thesis for K-12 deployment.

### Blender Built-in: QuadriFlow (FREE — BUT INSUFFICIENT)
- **Algorithm:** Based on QuadriFlow paper (github.com/hjwdzh/QuadriFlow)
- **Blender docs:** https://docs.blender.org/manual/en/latest/modeling/meshes/retopology.html
- **Known problems:**
  - Very slow (20+ seconds on modest meshes)
  - Frequently fails on non-manifold geometry or inconsistent normals
  - Needs polygon counts close to voxel remesh just to preserve basic details (fingers, etc.)
  - Does NOT follow body topology / edge flow — produces quasi-random quad layouts
  - Not suitable for meshes that will be deformed (animated characters)
  - Requires clean manifold input (students' meshes are often messy)
- **Verdict:** Not usable for our pipeline. This is why David uses Exoside.

### QRemeshify (FREE / PAY-WHAT-YOU-WANT — MOST PROMISING)
- **GitHub:** https://github.com/ksami/QRemeshify
- **Based on:** QuadWild with Bi-MDF solver
- **Key strengths:**
  - No external programs needed — runs entirely within Blender
  - Edge flow control via marked seams, sharp edges, material boundaries, face-set boundaries
  - Sharp feature detection from edges above threshold
  - **Good on organic meshes** (exactly our use case)
  - Symmetry support
  - Free and open source
- **Key limitations:**
  - Less effective on hard-surface (we don't care)
  - Recommended to keep input under 100K tris
  - Less frequently updated than Exoside
  - Less documented
- **Blender compatibility:** 4.2+
- **License:** Open source
- **VERDICT: This is our most promising starting point.**

### AutoRemesher (FREE — STANDALONE, NOT BLENDER-NATIVE)
- **GitHub:** https://github.com/huxingyi/autoremesher
- **Based on:** Geogram, libigl, OpenVDB, CGAL, libQEx, CoMISo solver
- **Key strengths:**
  - Sometimes produces better topology than QuadriFlow
  - Uses serious computational geometry libraries
  - GPL licensed
- **Key limitations:**
  - Standalone application (not a Blender addon — requires export/import workflow)
  - Only imports OBJ files
  - Still in alpha
  - Limited documentation
  - Processing times vary
- **Verdict:** Useful as a reference implementation and for understanding the algorithm stack, but not directly usable as a Blender addon.

### Instant Meshes (FREE — STANDALONE, FAST BUT LIMITED)
- **GitHub:** https://github.com/wjakob/instant-meshes
- **Paper:** "Instant Field-Aligned Meshes" (SIGGRAPH Asia 2015, ETH Zurich)
- **Project page:** https://igl.ethz.ch/projects/instant-meshes/
- **Key strengths:**
  - Extremely fast (sub-second on hundreds of thousands of faces)
  - Clean implementation of field-aligned meshing
  - Well-documented academic paper
  - Handles point clouds, range scans, and triangle meshes
- **Key limitations:**
  - Standalone application (not Blender-native)
  - Produces isotropic quads — doesn't follow body topology
  - No edge flow control
  - No adaptive density
  - Results are "uniform grid" quality — clean but not animation-friendly
- **Verdict:** Great for understanding the field-alignment algorithm. Too uniform for character work, but the speed is impressive and the codebase is educational.

---

## 4. THE ALGORITHM LANDSCAPE (ACADEMIC)

### Core Concept: How Quad Remeshing Works
All modern quad remeshers follow roughly the same pipeline:

1. **Cross-field computation** — Calculate a smooth 4-directional field on the surface that defines quad orientation. This field should align with sharp features and principal curvature directions.
2. **Global parameterization** — Map the surface to a 2D parameter space guided by the cross field. The integer grid lines in parameter space become the quad edges on the surface.
3. **Quad extraction** — Extract the actual quad mesh from the parameterization. This involves finding integer iso-lines and their intersections.
4. **Optimization/cleanup** — Fix degenerate quads, remove tiny faces, improve element quality.

The differences between tools come down to **how they compute the cross field** (smooth vs. feature-aligned), **how they do parameterization** (global vs. local, integer programming vs. relaxation), and **how they handle edge cases** (singularities, boundaries, sharp features).

### Key Papers & Algorithms

**QuadWild + Bi-MDF (2021) — BASIS OF QRemeshify**
- Paper: "Reliable Feature-Line Driven Quad-Remeshing" (SIGGRAPH 2021)
- DOI: 10.1145/3450626.3459941
- Authors: Nico Pietroni et al.
- GitHub (original): https://github.com/nicopietroni/quadwild
- GitHub (Bi-MDF extension): https://github.com/cgg-bern/quadwild-bimdf
- **Why it matters:** This is the algorithm QRemeshify uses. It drives cross-field computation from feature lines (sharp creases, material boundaries). The Bi-MDF solver replaces expensive Gurobi integer programming with a minimum deviation flow solver — making it free of commercial solver dependencies.
- Pre-built binaries available for Linux, Windows, macOS.

**Instant Field-Aligned Meshes (2015)**
- Paper: SIGGRAPH Asia 2015, ETH Zurich
- Project: https://igl.ethz.ch/projects/instant-meshes/
- **Why it matters:** Fastest known approach. Uses local smoothing to optimize edge orientations and vertex positions simultaneously. Great for understanding the fundamentals.

**QuadriFlow (2018)**
- GitHub: https://github.com/hjwdzh/QuadriFlow
- **Why it matters:** This is what Blender ships. Understanding its limitations tells us what to improve on.

**NeurCross (2024–2025) — NEURAL APPROACH (CUTTING EDGE)**
- Paper: "NeurCross: A Neural Approach to Computing Cross Fields for Quad Mesh Generation" (SIGGRAPH 2025)
- arXiv: https://arxiv.org/abs/2405.13745
- GitHub: https://github.com/QiujieDong/NeurCross
- **What it does:** Uses a neural network to jointly optimize a cross field and a signed distance function. Outperforms state-of-the-art in singular point placement and robustness to noise.
- **Why it matters for us:** This is the frontier. If we can integrate a lightweight neural cross-field computation step, we could potentially beat traditional methods on organic shapes specifically. But it's compute-intensive — may not work on low-end hardware. Worth investigating.

**CrossGen (2025)**
- Paper: "CrossGen: Learning and Generating Cross Fields for Quad Meshing" (ACM TOG 2025)
- **Why it matters:** Another neural approach to cross-field generation. The research community is clearly moving toward learned approaches.

---

## 5. RECOMMENDED BUILD STRATEGY

### Phase 1: Fork & Wrap QRemeshify (Proof of Concept)
**Goal:** Get a working "Clean Up My Shape" button in Blender that produces acceptable results on David's student character meshes.

1. Fork QRemeshify (it's already a Blender addon based on QuadWild-BiMDF)
2. Strip the UI down to a single button with zero exposed parameters
3. Hard-code sensible defaults for our use case:
   - Target: 2,000–5,000 quads
   - Auto-detect sharp features
   - Optimize for organic character topology
4. Test on actual ART 102 student meshes (voxel-remeshed character blockouts)
5. Benchmark: quality, speed, failure rate vs. Exoside on the same meshes

**Success criteria:** Produces usable results on 80%+ of typical student character meshes without manual intervention.

### Phase 2: Tune for Characters
**Goal:** Improve results specifically for humanoid/creature character topology.

1. Add body-aware heuristics (if we can detect limbs/torso/head, we can guide edge flow)
2. Implement adaptive density (more quads on face/hands, fewer on torso)
3. Add automatic symmetry detection and enforcement
4. Optimize for speed on low-end hardware
5. Add fallback: if the remesh fails, auto-retry with adjusted parameters before showing an error

### Phase 3: Explore Neural Cross-Field (Research)
**Goal:** Investigate whether a lightweight neural model can improve cross-field quality for organic shapes.

1. Study NeurCross and CrossGen implementations
2. Evaluate whether a small, pre-trained model could run on low-end hardware
3. If viable: train on a dataset of character meshes with known-good quad topologies
4. This is the "moonshot" — only pursue if Phase 1 & 2 produce a working tool

---

## 6. KEY TECHNICAL DETAILS FOR CLAUDE CODE

### Blender Addon Development
- Blender Python API: https://docs.blender.org/api/current/
- Addon structure: `__init__.py` with `register()` / `unregister()` functions
- Operator class inherits from `bpy.types.Operator`
- Panel class inherits from `bpy.types.Panel`
- Access mesh data via `bpy.context.active_object.data`
- bmesh module for mesh manipulation
- Target Blender version: 4.2+ (matches QRemeshify compatibility)

### QRemeshify Internals (Starting Point)
- GitHub: https://github.com/ksami/QRemeshify
- Based on QuadWild-BiMDF: https://github.com/cgg-bern/quadwild-bimdf
- The addon bundles pre-compiled QuadWild-BiMDF binaries
- It calls the binary as a subprocess, passing mesh data via temp files
- Edge flow guided by: seams, sharp edges, material boundaries, face-set boundaries
- Input recommendation: under 100K tris

### Libraries to Know
| Library | What It Does | License |
|---------|-------------|---------|
| **Geogram** | Mesh processing, parameterization, Voronoi | BSD-3 |
| **libigl** | Geometry processing (header-only C++) | MPL2 |
| **OpenVDB** | Volumetric data (voxel operations) | MPL2 |
| **CGAL** | Computational geometry algorithms | LGPL/GPL |
| **libQEx** | Quad mesh extraction from parameterization | — |
| **CoMISo** | Constrained mixed-integer solver | GPL |
| **numpy/scipy** | Python numerical computing | BSD |
| **bmesh** | Blender's mesh manipulation module | GPL |

### File Formats
- Internal: Blender mesh data (bmesh)
- Interchange with external tools: OBJ (most compatible), PLY, STL
- The addon should work entirely within Blender — no external app launches for the user

---

## 7. TEST DATA

### What to Test Against
David's ART 102 character pipeline produces specific kinds of meshes at the quad-remesh step:

1. **Post-voxel-remesh character blockouts** — chunky, organic, made from joined primitives (cubes, spheres, cylinders), then voxel-remeshed into a single continuous triangle mesh. Proportions range from chibi (stubby, big head) to more realistic humanoid.
2. **Typical poly counts at this stage:** 50K–200K triangles
3. **Common issues:** Non-manifold edges, inconsistent normals, interior faces from boolean-like joins. The remesher needs to be tolerant of messy input.
4. **Target output:** 2,000–5,000 quad faces with edge flow that roughly follows the body (loops around limbs, across torso, around head/neck)

### Quality Comparison Benchmark
For each test mesh, compare:
- Our addon output vs. Exoside Quad Remesher output vs. Blender QuadriFlow output
- Metrics: face count accuracy, quad percentage (vs. triangles/n-gons), edge flow quality (visual), UV-unwrap-ability, rigging compatibility, processing time

---

## 8. PROJECT METADATA

### People
- **David Bayus** — Project lead, designer, pedagogy expert, ART 102 instructor
- **Luca (Colpa Press)** — Potential co-designer (TBD — David considering bringing him in)
- **CADRE Lab students** — Potential development contributors (Python scripting, testing)

### Connections
- **K-12 Blender Addon** — The quad remesher is a critical dependency for this larger project
- **"Scrap in a Box"** — E-waste hardware deployment kits. Performance on low-end machines matters.
- **ART 102 pipeline** — Immediate testing ground. If it works for David's college students, it works for the addon.
- **Local Software thesis** — This IS local software. Built for specific kids in specific classrooms.

### Related Files
- `Addon_Design_Brainstorm_2026-03-30.md` — Full addon design & theory brainstorm
- TA-META Knowledge Base → ART102/ — Course materials, demo transcripts, pipeline docs
- Memory: `project_addon_reframe.md` — Strategic context for the addon project

---

## 9. NEXT SESSION CHECKLIST

When opening Claude Code to start building:

1. **Read this document first** — it's the complete context
2. **Clone QRemeshify** — `git clone https://github.com/ksami/QRemeshify.git`
3. **Read its source** — understand how it wraps QuadWild-BiMDF
4. **Create a new addon project** — fork or clean-room implementation
5. **Build the one-button UI** — "Clean Up My Shape" operator
6. **Test on a simple mesh first** — Blender's Suzanne monkey head is a good starting point
7. **Then test on actual student character meshes** — David will provide these

---

*This document is the handoff from Cowork to Claude Code. It contains everything needed to start building. When in doubt, refer back to the design principles in the Addon Design Brainstorm and the ART 102 pipeline in the TA-META Knowledge Base.*
