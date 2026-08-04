# SDF Blockout System Research
## WOMP-Style Voxel/SDF Modeling for Blender Studio Track

**Date:** April 3, 2026
**Context:** Research track for K-12 Blender Addon — Studio Track blockout tool
**Goal:** Can we build a WOMP-like SDF blockout experience inside Blender for high school students?

---

## What WOMP Does (and Why It Matters)

WOMP is a browser-based 3D modeler built entirely on Signed Distance Fields (SDFs). The core idea:

1. **Shapes are math, not mesh.** Every primitive (sphere, box, cylinder, etc.) is defined as a distance function — a formula that tells you how far any point in space is from the surface.
2. **Smooth unions are the magic trick.** When two SDF shapes overlap, instead of a hard boolean cut, the system blends them together with a controllable radius. This is what gives WOMP that "clay" or "goopy" feeling — shapes merge organically.
3. **Non-destructive stacking.** You build up complex forms by adding, subtracting, and blending primitives in a hierarchy. Nothing is committed until you export. Change anything at any time.
4. **Real-time feedback.** WOMP raymarches the SDF directly — no meshing step during editing. You see the smooth blended result instantly as you move shapes.

**Why this matters for students:** The blockout phase is where beginners get stuck in traditional 3D. They're fighting topology, edge loops, and mesh operations before they've even figured out what shape they want. SDF blockout separates **form exploration** from **mesh wrangling**. You think in volumes and silhouettes, not vertices.

WOMP is actively marketing to education — "3D modeling in the classroom" guides, 500K+ community, free tier. They get it. But WOMP is cloud-dependent and proprietary. We need this locally on scrap-in-a-box hardware.

---

## The Blender Landscape (As of April 2026)

### Native: Blender 5.0/5.1 SDF Grid Nodes (THE BIG DEAL)

Blender 5.0 (November 2025) shipped **27 new volume grid nodes** in Geometry Nodes, built on OpenVDB. This is the single most important development for this project. Blender now has native SDF infrastructure.

**Key nodes for our use case:**

| Node | What It Does | Why We Care |
|------|-------------|-------------|
| **Mesh to SDF Grid** | Converts any mesh to an SDF volume | Entry point — turn primitives into SDF space |
| **Points to SDF Grid** | Creates SDF from point cloud | Alternative entry for scatter-based workflows |
| **SDF Grid Boolean** | Union / Difference / Intersect on SDF grids | The core operation — combine shapes |
| **Grid to Mesh** | Converts SDF back to polygonal mesh | Exit point — get a mesh for remeshing/sculpting |
| **SDF Grid Mean** | Fast separable averaging filter | Smooth the result |
| **SDF Grid Offset** | Uniform dilation/erosion | Inflate/deflate shapes |
| **SDF Fillet** | Rounds off concave internal corners | Softer transitions where shapes meet |
| **Voxelize Grid** | Adjusts grid sparseness | Performance control |
| **Prune Grid** | Removes inactive voxels | Memory optimization |
| **Grid Info / Sample Grid** | Read data from grids | Inspection and debugging |

**Blender 5.1 (March 2026) added:**
- Clip Grid — deactivate voxels outside a box (great for slicing)
- Dilate/erode operations on volume grids
- Mask to SDF node in compositor

**What's missing natively:**
- **No smooth boolean radius parameter** on the SDF Grid Boolean node (it's hard union/difference/intersect only — no blending)
- No built-in "add primitive to SDF scene" workflow — you wire it yourself in geometry nodes
- No dedicated UI for SDF blockout — it's all node-graph level

**Performance note:** OpenVDB is voxel-based, not analytic SDF. Resolution matters. High voxel counts = slow on weak hardware. Need to test on scrap-in-a-box specs.

### GSoC 2024: Smooth Boolean Nodes & Material Blending

Giorgio De Magistris proposed (and appears to have partially implemented) smooth boolean support and material blending for Blender's SDF grid nodes. This was a Google Summer of Code 2024 project.

**Status:** The SDF Fillet node in Blender 5.0 may be a direct result of this work. However, a full "smooth radius" parameter on the Boolean node (like WOMP's smooth union) doesn't appear to have shipped yet. This is the single biggest gap.

**Implication:** We may need to implement smooth blending ourselves in geometry nodes (it's mathematically simple — `min(a, b) - smoothing_factor` style), or wait for it to land natively.

---

## Third-Party Addons (Existing Work)

### ConjureSDF (by João Desager)
- **What:** Dedicated SDF editor inside Blender. Uses raymarched rendering of analytic SDFs.
- **Primitives:** 12 SDF primitives (box, sphere, cylinder, etc.)
- **Booleans:** 4 operations (union, subtract, difference, intersect) with 4 blend modes (none, smooth, chamfered, inverted round)
- **Key feature:** Nested primitives for hierarchical shape building. Custom raymarched viewport via "Conjure Vision."
- **Limitations:** Windows/Linux only (no macOS). Requires Blender 3.3 (reduced support for 3.6). **Not updated for Blender 4.x/5.x.** Appears semi-abandoned — last meaningful update was v0.2.3.
- **Relevance:** Proves the UI concept works. Shows what a "blockout mode" could feel like. But the codebase is too old to use directly.
- **Links:** [Blender Artists thread](https://blenderartists.org/t/conjuresdf-smooth-non-destructive-booleans/1478671) · [Gumroad](https://johnkazart.gumroad.com/l/csdf)

### FieldForge (by AonoZan/Dejan Petrović)
- **What:** SDF modeling addon using **libfive** (open-source SDF library from MIT) via Python bindings.
- **Architecture:** Bounds Controller (root) → Sources (primitives) → Groups (hierarchies) → Canvas (2D shapes for extrusion/revolution)
- **Primitives:** Cube, Sphere, Cylinder, Cone, Torus, Pyramid, Rounded Box
- **Booleans:** Union, Difference, Intersection, plus "Clearance" (offset subtraction for sockets/joints)
- **Key feature:** Direct viewport interaction — click wireframe visuals to select/manipulate SDF objects
- **Limitations:** Depends on libfive compiled library (external dependency). Need to verify it works on Linux ARM/low-spec.
- **Relevance:** The architecture (Bounds → Sources → Groups) is a smart hierarchy model. The libfive dependency is a concern for our zero-external-dependency policy, but the UX concepts are worth studying.
- **Links:** [GitHub](https://github.com/AonoZan/FieldForge) · [Blender Artists](https://blenderartists.org/t/fieldforge/1587542)

### SD5 (also libfive-based)
- **What:** Earlier libfive-based CSG/SDF addon, predates FieldForge.
- **Links:** [Blender Artists](https://blenderartists.org/t/sd5-addon-csg-sdf-modeling-using-libfive/1561003)
- **Relevance:** Historical reference. FieldForge appears to be its successor.

### SDF Boolean Mixer (by Nikita Bukoros)
- **What:** Geometry Nodes setup + addon wrapper for Blender 5.0+ SDF Grid nodes.
- **Key feature:** Advanced boolean operations with different blend types and chamfers. Essentially wraps the native SDF Grid Boolean node with smooth blending math.
- **Version 1.2.0 (Blender 5.1+):** New "Increase Resolution" mode, smooth option in mesher, emboss/deboss toggles.
- **Limitations:** Paid addon ($). Can be slow at high voxel resolutions.
- **Relevance:** HIGH. This proves that smooth SDF booleans work with native Blender 5.0 nodes. We can study the approach (it's geometry nodes, so the math is visible) and build our own version.
- **Links:** [Gumroad](https://bukoros.gumroad.com/l/sdf_mixer) · [Superhive](https://superhivemarket.com/products/sdf-boolean-mixer)

### Blender SDF Node Addon (by hooyuser)
- **What:** Custom node system for SDF modeling in Blender.
- **Links:** [GitHub](https://github.com/hooyuser/blender_sdf_node_addon)
- **Relevance:** Research reference. Another approach to SDF node systems.

### SDF NodeBox (by Salami)
- **What:** 46 shader nodes for SDF work — raymarching, SDF to vector displacement, etc.
- **Relevance:** Shader-level, not geometry-level. More for rendering effects than blockout modeling.
- **Links:** [Gumroad](https://salami.gumroad.com/l/blendersdf)

### Sascha Rode's SDF Modeler
- **What:** Standalone experimental SDF modeling tool (not Blender-specific).
- **Links:** [itch.io](https://sascha-rode.itch.io/sdf-modeler)
- **Relevance:** UI reference only.

---

## What Blender's Metaballs Already Do (and Why They're Not Enough)

Blender has had metaballs since forever. They're technically SDF-based (isosurface extraction from distance fields). But:

- **Limited shape vocabulary:** Ball, capsule, plane, ellipsoid, cube. No cone, torus, rounded box, etc.
- **No per-pair blend control:** All metaballs in an object blend with each other uniformly. Can't do "these two shapes blend smooth, but that one is a hard subtraction."
- **No hierarchy:** Flat list of elements, no grouping.
- **Poor viewport performance** at high element counts.
- **No integration with geometry nodes** — metaballs are their own data type, can't be processed in geonodes.
- **Terrible for production:** Everyone says "use metaballs for blockout" but nobody actually does because you can't take a metaball result anywhere useful without converting to mesh and losing all editability.

**Bottom line:** Metaballs prove the concept but fail in execution. The new SDF Grid nodes are what metaballs should have been.

---

## Proposed Approach: SDF Blockout Tool for Studio Track

### Architecture

Build a geometry-nodes-based SDF blockout system that wraps Blender 5.0+'s native SDF Grid nodes behind a simple operator-driven UI.

**The student experience:**
1. Click "Add Shape" → pick from primitives (sphere, box, cylinder, cone, torus, capsule)
2. A new empty appears in the viewport — grab/rotate/scale it to position the shape
3. Shapes automatically combine with smooth union (adjustable blend radius)
4. Student can switch any shape to "subtract" mode (carve out)
5. Live voxel preview updates in real-time as shapes are moved
6. When happy with the blockout: "Freeze Shape" → converts to mesh → feeds into QUADRE remesher → PaWrappa UV → paint

**Under the hood:**
- Each "shape" is an Empty with custom properties (shape type, blend radius, operation)
- A single geometry nodes tree on the blockout object reads all empties and builds the SDF pipeline
- The geonodes tree: for each empty → generate primitive mesh → Mesh to SDF Grid → SDF Grid Boolean (with custom smooth blending math) → Grid to Mesh for viewport display
- Smooth union math: `sdf_smooth_union(a, b, k) = min(a, b) - h*h*k/4` where `h = max(k - abs(a-b), 0) / k`

### Key Technical Questions to Resolve

1. **Performance on scrap hardware:** OpenVDB SDF operations at what resolution? Need to benchmark Mesh to SDF Grid → Boolean → Grid to Mesh on 8GB RAM / integrated GPU. Target: 10+ FPS interactive.

2. **Smooth union in geonodes:** The native SDF Grid Boolean node doesn't have a smooth radius. Can we implement smooth min in the geometry node graph using math nodes on the raw grid values? Or do we need a custom node/Python operator?

3. **Per-shape blend control:** WOMP lets you set blend radius per shape pair. Can we do this with separate SDF Grid Boolean operations chained together, each with its own smoothing?

4. **Voxel resolution control:** Need a simple "detail" slider that maps to voxel size. Low detail = fast preview. High detail = final freeze.

5. **Does Grid to Mesh produce acceptable topology for QUADRE?** The output mesh will be all triangles from marching cubes. QUADRE (QuadWild) needs to handle this gracefully.

6. **Undo/history:** Moving an empty should be undoable. Blender's undo should "just work" since we're using standard objects + geonodes, but need to verify with SDF grid caching.

### Implementation Phases

**Phase 1: Proof of Concept (geometry nodes only, no addon code)**
- Build a geometry nodes tree by hand that takes 2-3 empties, generates SDF primitives, smooth-unions them, and outputs a mesh
- Test performance on low-spec machine
- Test smooth blending math options
- Document what works and what breaks

**Phase 2: Operator Wrapper**
- `KIDBLENDER_OT_add_blockout_shape` — adds an empty with the right custom properties
- `KIDBLENDER_OT_freeze_blockout` — converts SDF result to mesh, removes the geonodes system
- UI panel in Studio Track sidebar with shape picker + blend slider

**Phase 3: Polish & Pipeline Integration**
- Freeze → QUADRE remesh → PaWrappa UV (one-click pipeline)
- Thumbnail previews of shapes
- "Detail" slider for voxel resolution
- Presets: "Character Blockout" (body + head + limbs as preset empties)

### Minimum Viable Demo

A geometry nodes tree that:
1. Takes N input empties (each with shape_type, operation, blend_radius properties)
2. Generates the corresponding SDF primitive for each
3. Chains them through smooth SDF boolean unions
4. Outputs a live-updating mesh via Grid to Mesh

If this runs at interactive framerates on scrap hardware with 5-10 shapes, we have a viable tool.

---

## Comparison Matrix

| Feature | WOMP | Blender Metaballs | Blender 5.0 SDF Nodes | ConjureSDF | FieldForge | Our Proposed Tool |
|---------|------|-------------------|----------------------|------------|------------|-------------------|
| Smooth union | Yes | Yes (global only) | Not built-in* | Yes (4 modes) | CSG only | Yes (custom math) |
| Shape variety | 10+ | 5 | Any mesh → SDF | 12 | 7 | 6-8 target |
| Non-destructive | Yes | Yes | Yes (geonodes) | Yes | Yes | Yes |
| Hierarchy/grouping | Yes | No | Manual (node tree) | Yes (nested) | Yes (groups) | TBD |
| Per-shape blend | Yes | No | Manual | Yes | No | Target yes |
| Real-time preview | Yes (raymarch) | Yes | Yes (Grid to Mesh) | Yes (raymarch) | Viewport wireframe | Yes (Grid to Mesh) |
| Runs on scrap HW | No (cloud) | Yes | **Unknown** | Probably | Unknown | **Must verify** |
| Open source | No | Yes (Blender) | Yes (Blender) | No | Yes (GPL) | Yes |
| Blender 5.x compat | N/A | Yes | Yes | No (3.3 only) | Unknown | Yes (target) |
| No external deps | N/A | Yes | Yes | Yes | No (libfive) | Yes |

*SDF Grid Boolean does hard booleans. Smooth blending requires custom math on grid values.

---

## Key Takeaways

1. **Blender 5.0's SDF Grid nodes are the foundation.** Don't fight the platform — build on native infrastructure. This means targeting Blender 5.0+, not 4.5 as originally planned for the puppet show addon. (The puppet show can stay on 4.5 since it doesn't need SDF nodes.)

2. **Smooth union is the missing piece.** The native Boolean node doesn't blend. SDF Mixer proves it's solvable in geometry nodes. This is our Phase 1 R&D task.

3. **ConjureSDF and FieldForge validate the UX.** A primitive-based blockout mode with smooth blending IS a good workflow for beginners. Multiple people have built it. We just need to do it on modern Blender with zero dependencies.

4. **Performance is the unknown.** Everything depends on whether OpenVDB SDF operations at reasonable resolution can run interactively on 8GB/integrated GPU. This is the first thing to benchmark.

5. **Pipeline integration is the differentiator.** WOMP is a dead end — you export an OBJ and start over. Our tool feeds directly into QUADRE → PaWrappa → texture paint → geometry nodes puppet template. The blockout is the START of the pipeline, not a standalone toy.

6. **This is Studio Track only.** Stage Track (K-8) students use pre-made puppet templates. Studio Track (HS/CADRE) students BUILD those templates. SDF blockout is a Studio Track tool — the first step in "design a character from scratch."

---

## References & Links

- [Blender Dev Blog: Volume Grids in Geometry Nodes](https://code.blender.org/2025/10/volume-grids-in-geometry-nodes/)
- [Blender 5.0 Geometry Nodes Release Notes](https://developer.blender.org/docs/release_notes/5.0/geometry_nodes/)
- [SDF Grid Boolean Node — Blender Manual](https://docs.blender.org/manual/en/latest/modeling/geometry_nodes/volume/operations/sdf_grid_boolean.html)
- [Mesh to SDF Grid Node — Blender Manual](https://docs.blender.org/manual/en/latest/modeling/geometry_nodes/mesh/operations/mesh_to_sdf_grid.html)
- [SDF Fillet Node — Blender Manual](https://docs.blender.org/manual/en/latest/modeling/geometry_nodes/volume/operations/sdf_grid_fillet.html)
- [SDF Grid Offset Node — Blender Manual](https://docs.blender.org/manual/en/latest/modeling/geometry_nodes/volume/operations/sdf_grid_offset.html)
- [GSoC 2024: Smooth Boolean Nodes](https://devtalk.blender.org/t/gsoc-2024-draft-smooth-boolean-nodes-and-material-blending/33953)
- [ConjureSDF — Blender Artists](https://blenderartists.org/t/conjuresdf-smooth-non-destructive-booleans/1478671)
- [FieldForge — GitHub](https://github.com/AonoZan/FieldForge)
- [SDF Boolean Mixer — Gumroad](https://bukoros.gumroad.com/l/sdf_mixer)
- [Blender SDF Node Addon — GitHub](https://github.com/hooyuser/blender_sdf_node_addon)
- [WOMP — GameFromScratch Overview](https://gamefromscratch.com/womp-3d-modelling-app/)
- [WOMP — 80 Level Feature](https://80.lv/articles/womp-creating-goopy-3d-models-in-your-browser)
- [WOMP — Hacker News Discussion](https://news.ycombinator.com/item?id=33478459)
- [WOMP — 3D in the Classroom Guide](https://www.womp.com/blogs/3d-modeling-in-the-classroom-a-teachers-complete-guide-for-2025)
- [Blender Artists: The Big SDF Thread](https://blenderartists.org/t/the-big-sdf-thread/1293075)
- [Blender Artists: New Grid Nodes 5.0/5.1](https://blenderartists.org/t/new-grid-nodes-from-5-0-5-1-sdf-volumes-voxels-advection/1616473)
- [Custom Metaballs with Geometry Nodes (80 Level)](https://80.lv/articles/smooth-metaballs-blender-setup-with-sdf)
- [Fab Academy: Blender 5.0 SDF Nodes Workshop](https://academany.fabcloud.io/fabacademy/2026/bootcamp-instructors/workshops/Blender_5.0_Geometry_Nodes/)
