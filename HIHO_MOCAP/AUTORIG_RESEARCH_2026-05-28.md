# HIHO MOCAP — Auto-Rig / "HIHO Mixamo" Research (2026-05-28)

**What this is.** Durable findings from a deep-research pass run 2026-05-28 on the
state of free and open-source automatic character rigging and skinning, for the
"HIHO Mixamo" feature: a student makes a character mesh in A-pose, places a small
set of landmark markers (hips, knees, ankles, shoulders, elbows, wrists, head), and
HIHO fits the shared skelly skeleton to that mesh and skins it, so any character can
play any clip in the shared local mocap library with zero retargeting.

**Method.** Automated fan-out web research: 5 angles, 19 sources fetched, 93 claims
extracted, 25 adversarially verified (24 confirmed, 1 refuted). This doc keeps the
durable conclusions. The temp run output is not preserved; this file is the record.

---

## Bottom line: BUILD, do not adopt (but it is a tractable build)

No existing free tool clears the whole bar at once. The bar is: Mixamo-level quality
AND targets a fixed predefined skeleton (our skelly) AND AGPL-3.0 compatible AND
maintained AND lightweight. Nothing hits all five. But the architecture we want is
proven and decades old, and our own UX removes the hardest algorithmic step. So the
smallest viable path is to build a Pinocchio-style pipeline, not to wait for a tool.

---

## The big validation: we re-derived Pinocchio (2007)

The architecture David designed (one fixed shared skeleton, fit it to each character,
skin it, then any character plays any clip from a shared library with no retargeting)
is exactly the **Pinocchio** method (Baran & Popović, SIGGRAPH 2007). Its own abstract
frames it as "a user-friendly animation system for novices and children," which is
HIHO's exact audience. Adobe's Mixamo descends from this same lineage.

So "Mixamo-level" is not bleeding edge. It is a well-understood ~2007 algorithm. We
are rebuilding a known, proven thing, not inventing a risky one.

Pinocchio's skinning (how it binds the mesh to the bones) uses a heat-diffusion solve
that is the **same family as Blender's own built-in "Automatic Weights" (bone-heat).**
That means a usable version of the hard half already ships inside Blender for free.

Source: https://www.cs.toronto.edu/~jacobson/seminar/baran-and-popovic-2007.pdf

---

## Our marker-placement UX removes the hardest step

Pinocchio's single hardest, most failure-prone step is automatically guessing where a
character's joints are. David's design has the **student place the markers** (hips,
knees, ankles, shoulders, elbows, wrists, head). That hands the algorithm the answer
to its hardest question. It substantially de-risks the rig half of the build.

---

## The two halves of the job

### 1. Rig: fit the skelly to the markers
Tractable geometry, de-risked by the markers. Reuse Blender's built-in **Rigify** only
for its bone-construction plumbing. Note: Rigify builds its own rig from templates and
does **not** skin the mesh, so it is machinery, not a solution.

### 2. Skin: generate vertex weights (the genuinely hard part)
Ranked by what is usable now:

| Option | Quality / robustness | Catch |
|---|---|---|
| **Blender bone-heat** (built-in Automatic Weights) | The free floor. Same Pinocchio family. Fine on clean, single-piece meshes. | Struggles on messy / non-watertight / multi-piece meshes. |
| **libigl Bounded Biharmonic Weights** | Standard high-quality smooth weights. Free, working code. | Needs the mesh interior turned into a tetrahedral volume first, which is fragile and can fail on messy meshes. C++ with Python bindings, so bpy integration is real work. |
| **2024 "Robust Biharmonic Skinning Using Geometric Fields"** (MIT/USC) | Best published robustness on non-watertight / triangle-soup meshes. No tetrahedralization. | Skinning only (needs a skeleton supplied). ~30 to 100s per mesh, not interactive. **No public code or license found.** Would need clean-room reimplementation. |
| **Geodesic Voxel Binding** (Maya's robust auto-skin) | Robust on exactly the failure modes of hand-made meshes (non-manifold, holes, self-intersections, multi-piece). | Maya-only. **No open Blender port.** Would need clean-room reimplementation. |

---

## Ruled out

- **RigNet** (neural, predicts joints + weights): GPL-3.0 (AGPL-compatible), but it
  generates its **own** skeleton and cannot natively target our fixed skelly, and it
  needs heavyweight PyTorch / CUDA (~2GB). Source: https://github.com/zhan-xu/RigNet
- **brignet** (RigNet wrapper for Blender): its own maintainer declares it dead
  ("THIS ADD-ON IS DEAD AND WILL HARDLY WORK"). Not adoptable.
  Source: https://github.com/pKrime/brignet
- **GameRig** (Rigify-based auto-rigger): **GPL-2.0-only**, which legally **cannot** be
  combined into an AGPL-3.0 work. Also does not skin. Source: https://github.com/Arminando/GameRig
- **Rigify alone**: builds a rig, does not skin. Useful as plumbing only.

---

## Concrete free starting points to evaluate

- **pmolodo/Pinocchio** — a maintained port of the original Pinocchio. https://github.com/pmolodo/Pinocchio
- **meshonline/Surface-Heat-Diffuse-Skinning** — an open-source bone-heat / surface heat-diffuse skinning addon. https://github.com/meshonline/Surface-Heat-Diffuse-Skinning
- **Blender bone-heat** — built in, free, the quality floor to beat (Ctrl+P > With Automatic Weights).

---

## The cheap first experiment (do this BEFORE building anything)

The key open question is: **how good is Blender's built-in bone-heat, by itself, on a
clean chibi student mesh?** If most student meshes are clean enough (single piece, no
holes), bone-heat may already clear the Mixamo bar. If so, the whole HIHO Mixamo
shrinks to "fit the skelly to the markers, then call bone-heat," which is a small,
club-buildable scope. The expensive robust-solver work only becomes necessary if real
student meshes are too messy for bone-heat. Test first, build second.

---

## David's lead: Voxel Heat Diffuse Skinning (chase this FIRST next session)

David flagged from hands-on rigging experience (2026-05-28): he uses **Voxel Heat Diffuse Skinning** (an addon/method by "meshonline") and it skins **multi-piece characters** far better than Blender's built-in Automatic Weights. This may be a direct hit on the exact gap this report could not fill.

Why it likely works:
- Blender's built-in bone-heat is **surface-based**: it needs connected geometry, so it struggles when a character is built from separate pieces (a head, a body, detached hands, floating accessories), which is exactly how students build chibi characters.
- **Voxel methods fill the volume** with a 3D grid and compute weights through that volume, so disconnected pieces still bind correctly. Same robustness advantage as Geodesic Voxel Binding (the Maya method flagged above as robust-but-no-open-port). David's lead may be the open, Blender-native voxel skinner the automated search missed. Likely a sibling of the `meshonline/Surface-Heat-Diffuse-Skinning` repo this report already found (look for `meshonline/Voxel-Heat-Diffuse-Skinning`).

**Findings (checked 2026-05-28, the GitHub repo David linked: `meshonline/Surface-Heat-Diffuse-Skinning`):**
- **License: MIT.** Permissive, fully AGPL-3.0 compatible, free to use and adapt. The repo ships the **full C++ solver source** plus prebuilt Windows/Linux/macOS binaries.
- **Method: voxel-grid heat diffusion** (the robust, volume-filling kind), despite "Surface" in the repo name. The README explicitly supports **multiple separate sub-meshes skinned to one armature** (select all sub-meshes + the armature). That is exactly the multi-piece capability David wanted from the paid version.
- **Targets a provided armature** (select meshes + your armature), so it can skin to our skelly.
- **Catch: it is old.** Last updated 2022, Blender 2.7 / 2.8 era, described as a prototype. The Python addon wrapper needs modernizing for current Blender (4.x / 5.x API). The heavy lifting is an external compiled C++ binary, which is Blender-version-independent, so the solver itself is reusable as-is; mostly the glue needs updating.
- **The paid "Voxel Heat Diffuse Skinning"** (superhivemarket.com / mesh-online.net) is the polished, supported, current-Blender product. We do NOT need it and must NOT pirate it: the free repo ships MIT-licensed source, so HIHO compiles and modernizes its own.

**Remaining to verify next session:** (1) a hands-on quality test on a real multi-piece chibi mesh (does the free version match the paid one's quality?); (2) a file-level license read (repo states MIT; one secondary source hinted the command-line binary's license is noted separately, so confirm at the file level); (3) modernize-effort scoping for the current-Blender addon wrapper.

**Paid addon structure (structural peek only, 2026-05-28; David shared the v3.5.3 zip; we read the file listing, NOT the code, to honor the clean-room rule):** the paid addon is a thin Python wrapper (ships GPL-3.0, as every Blender addon must be) plus compiled solver binaries per platform: `shd` (surface heat diffuse) and `vhd` (voxel heat diffuse), for macOS / Linux / Windows. The Python glue exports mesh + bones to a file, runs the binary, imports the weights back. Extras: a corrective-smooth baker and a joint-alignment tool. The proprietary value is the compiled binary; the MIT repo ships the equivalent solver as SOURCE, so we need nothing from the paid zip, and clean-room is preserved (no proprietary internals read).

**The single sharpest next-session question:** the paid addon ships BOTH `shd` and `vhd`. Confirm whether the MIT repo's C++ source is the VOXEL solver (`vhd`, the multi-piece-robust one) or only the surface one (`shd`). That decides whether the free path delivers multi-piece quality directly, or whether voxel is the paid-only upgrade we reimplement from the published method.

This reframes the skinning half from "clean-room build a robust solver" to **"adopt and modernize an MIT-licensed voxel skinner that already does multi-piece."** A large de-risk on the hardest part of the HIHO Mixamo, and the first thread to pull next session.

Repo: https://github.com/meshonline/Surface-Heat-Diffuse-Skinning  ·  Author's page: https://www.mesh-online.net/voxel.html

## Open questions for future sessions

1. How good is Blender bone-heat alone on clean chibi meshes? (Test first; it may make the rest optional.)
2. Is there any AGPL-compatible voxel-geodesic / Geodesic-Voxel-Binding implementation to vendor, or must it be clean-room reimplemented?
3. Did the 2024 Robust Biharmonic (Geometric Fields) team release code, and under what license?
4. Do newer learned skinners (UniRig, RigAnything, ASMR, ARMO) offer a fixed-skeleton mode and an AGPL-compatible license? Not evaluated here.

---

## Caveats (read before quoting numbers)

- **No reliable success-rate number exists.** A claimed "Pinocchio rigs 81% of characters correctly" benchmark was adversarially **refuted** and must not be cited. Effort confidence rests on architecture fit, not a measured score.
- The two robust skinning methods for messy meshes (2024 Geometric Fields, Geodesic Voxel Binding) have **no usable open code**, so robustness on truly messy meshes is the hard frontier and is deferred.
- The robust academic methods run ~30 to 100s per mesh. Mixamo-level UX may mean accepting a "submit and wait" bake step, not instant.
- Newest learned skinners were noted but not verified for license / fixed-skeleton support / Blender integration.

---

## Key sources

- Pinocchio (Baran & Popović 2007): https://www.cs.toronto.edu/~jacobson/seminar/baran-and-popovic-2007.pdf
- Pinocchio port: https://github.com/pmolodo/Pinocchio
- Surface Heat Diffuse Skinning (open bone-heat addon): https://github.com/meshonline/Surface-Heat-Diffuse-Skinning
- Robust Biharmonic Skinning Using Geometric Fields (2024): https://arxiv.org/abs/2406.00238
- Geodesic Voxel Binding (2013): https://dl.acm.org/doi/10.1145/2485895.2485919
- libigl Bounded Biharmonic Weights: https://libigl.github.io/tutorial/
- RigNet: https://github.com/zhan-xu/RigNet  ·  brignet (dead): https://github.com/pKrime/brignet
- GameRig (GPL-2-only): https://github.com/Arminando/GameRig
- Blender Rigify manual: https://docs.blender.org/manual/en/latest/addons/rigging/rigify/index.html
