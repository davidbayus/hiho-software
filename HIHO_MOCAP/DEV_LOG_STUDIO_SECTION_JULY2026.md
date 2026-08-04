# DEV LOG — Studio Section completion, July 2026 sprint

**Purpose:** Running process record of the July 1–7 sprint completing the HIHO MOCAP Studio Section for student testing at BASEMENT. Written for post-sprint review by Opus (after July 7). Every working step gets an entry: what was decided, what was built, what was tested, what broke, what was reverted.

**Companion docs:** [STUDIO_SECTION_DESIGN_2026-07-01.md](STUDIO_SECTION_DESIGN_2026-07-01.md) (the design), [AUTORIG_RESEARCH_2026-05-28.md](AUTORIG_RESEARCH_2026-05-28.md), [BIND_TO_RIG_DESIGN.md](BIND_TO_RIG_DESIGN.md).

**Rules in force:** laptop is HIHO dev lead (verified `Davids-MacBook-Pro` at session start); no code before design; one change at a time, test after each, revert if worse; never delete (holding pen only); zips built from `SOFTWARE/`; AGPL-3.0; zero paid deps.

---

## 2026-07-01 (Day 1) — Session start, scoping, design

**Machine check:** `scutil --get LocalHostName` → `Davids-MacBook-Pro`. Laptop confirmed; dev authorized.

**State reconciliation:** Read the late-June handoff (kept outside this repo). Confirmed: no HIHO dev happened during the June break; canonical build still `hiho_mocap-1.3.18.zip`; Studio panel in 1.3.18 is the v1.2 stub skeleton (every button reports "Coming soon"). David's live Blender still has 1.3.8 — new build install is part of the BASEMENT day anyway.

**David's brief (verbatim intent):** Final version of the Studio Section for student testing at BASEMENT by July 7. New features: FBX/OBJ upload selection, auto-rigging in the vein of Mixamo / Auto-Rig Pro, upload a student's character, a place to insert a new mocap file. Document the process for Opus review after July 7.

**Scope decisions (David, via structured questions):**
1. Skinning engine: **modernize the MIT voxel skinner** (his hands-on call — voxel handles multi-piece student characters far better). Claude flagged schedule risk; David chose it anyway; fallback to Automatic Weights designed in as insurance.
2. Rig-fit UX: **student places 13 marker empties** (the May research design).
3. "Insert a mocap file" = **pick any processed HIHO take folder from disk** (any HIHO recording, any machine).
4. Priority: **character pipeline first** (Import → Auto-Rig → Load Take → motion on character), Export/Polish only if time remains.

**Research verification (closed the May research doc's sharpest open question):** Fetched `meshonline/Surface-Heat-Diffuse-Skinning`. The MIT repo's solver IS voxel-based (author replaced octree with voxel grid; "Surface" name is historical). MIT license repo-wide (file-level check still owed). Full C++ source in `/src`. Prebuilt binaries Intel-only/2022 → we compile our own, target a universal (arm64+x86_64) binary. Multi-sub-mesh skinning explicitly supported. Their Blender wrapper is 2.7/2.8-era; we write our own thin subprocess glue instead of porting it.

**Written today:** `STUDIO_SECTION_DESIGN_2026-07-01.md` (full design: student flow, 4 features, marker→bone derivation table, panel layout, file map, day-by-day schedule, risks). This log.

**Next:** David signoff on the design → Day-1 gate (compile solver on M4, file-level license check, quality smoke test vs Automatic Weights on a multi-piece mesh).

---

## 2026-07-01 (Day 1, cont.) — Design signoff + Day-1 gate: VOXEL PATH IS GO

**Signoff:** David approved STUDIO_SECTION_DESIGN_2026-07-01.md ("looks good, lets go!").

**Day-1 gate results (all pass):**
1. **License, file level:** repo cloned to `SOFTWARE/R&D/voxel_skinning_reference/`. Top-level LICENSE = MIT (c) 2018 Mingfen Wang. `raytri.cpp` / `tribox.cpp` are Tomas Möller's classic journal-of-graphics-tools routines (freely reusable, headers intact). **Caveat found:** the repo's *Blender addon wrapper* (`addon/.../__init__.py`) is GPL-2+, NOT MIT — we write our own glue from scratch (already planned) and vendor only the MIT `src/` + LICENSE.
2. **Compile:** `clang++ src/*.cpp -std=c++11 -O2 -pthread -arch arm64 -arch x86_64` → `vhd_mac_universal`, 182KB universal binary, zero errors first try.
3. **Exchange format captured** (from reading their wrapper, formats are facts not code): mesh.txt = `v,x,y,z` + `f,i,...` (world space, all sub-meshes concatenated with vertex offset); bone.txt = `b,name,headxyz,tailxyz` (deform bones, world space); weight.txt out = `b,name` group-order lines + `w,vertIndex,boneIndex,weight`. CLI: `binary mesh bone weight resolution(128) loops(5) samples(64) influence(8) falloff(0.2) sharpness(3) detectSolidify(n)`, cwd = data dir.
4. **Quality smoke test** (headless Blender 5.2 LTS Beta, script preserved in session scratchpad, outputs in `R&D/voxel_skinning_reference/hiho_smoke_test/`): built a deliberately multi-piece "student chibi" (floating head, detached hands, 8 separate pieces), skinned one copy per engine, posed both arms, saved `comparison.blend`.
   - **Voxel: 0.4s, exit 0, zero unweighted vertices, every piece's dominant group is the semantically correct bone** (head→head, hands→hand.L/R, etc.).
   - **Automatic Weights: completed, but torso's dominant group = `leg.R`** — the classic smear David predicted. Validates his engine choice with data.
   - David to eyeball `comparison.blend` when convenient; numeric gate already passed.

**Decision:** Voxel path GO, Automatic Weights stays as the designed fallback/toggle. Proceeding to Day-2 build (Import Character + Add Markers) same day — ahead of schedule.

---

## 2026-07-01 (Day 1, cont. 2) — Design amendment + 1.4.0 built (Day-2 scope, a day early)

**Design amendment (recorded in the design doc before code):** the May BIND_TO_RIG_DESIGN's Rigify-name plan is stale. In the live codebase `operators/bind.py` is RETIRED (unregistered) and `core/bind_to_rig.py`'s constraint table is verbatim ajc27 (`pelvis`, `spine`, `spine.001`, `neck`, `face`, ... incl. fingers), consumed by the registered Spawn Rig (`operators/spawn_rig.py`) which builds its own ajc27 armature + applies constraints. **Auto-Rig will therefore build ajc27-named bones** — the live `apply_constraints()` then drives the student character with no translation layer; unbuilt finger bones are skipped by existing missing-bone handling. Roll/proportion conventions come from `core/build_rig.py`'s `_TPOSE` / `_ARMATURE_DEFINITION`.

**Build recipe confirmed:** zips are `blender --command extension build` from `HIHO_MOCAP/` using the manifest's `paths_exclude_pattern` (flat zip, retired modules + docs excluded). Added excludes for `DEV_LOG_*.md` + `HIHO_ADOPTABLE_INNOVATIONS.md`.

**Shipped `hiho_mocap-1.4.0.zip`** (SOFTWARE/):
- NEW `operators/import_character.py` — `.fbx`/`.obj` file picker; imports into `HIHO_Character_<name>` collection; sets `scene.hiho_mocap.character_collection`; reports mesh/vertex counts; warns (doesn't touch) if the file carries its own armature.
- NEW `operators/markers.py` — 13 joint markers (head, shoulders, elbows, wrists, hips, knees, ankles), plain-language object names ("Left Knee"), identity in a `hiho_marker` custom property so student renames can't break Auto-Rig; template positions = classic human proportions scaled to the character's bounding box; sphere display, show-in-front; idempotent (re-run resets to template, never duplicates).
- `properties.py` + `character_collection` StringProperty; Studio panel Character section now has real Import Character + Add Markers buttons (Send to Character still stub until Day 5); version bumps.

**Tested (headless Blender 5.2 LTS, --factory-startup, script in session scratchpad):** register from built zip OK; OBJ import → collection OK; 13 markers, correct ids, sane heights; idempotency OK. ALL PASSED.

**Awaiting David:** install 1.4.0 + hands-on test of Import Character / Add Markers (one-change-at-a-time gate before Day-3 Auto-Rig fit work). Also `R&D/voxel_skinning_reference/hiho_smoke_test/comparison.blend` ready for his eyeball.

---

## 2026-07-01 (Day 1, cont. 3) — David's first hands-on test + 1.4.1

**David tested 1.4.0 live (screenshot):** imported his SHOW_LOWPOLY character (single-piece A-pose biped), markers spawned around it correctly. Verdict: "so far so good."

**Feedback → 1.4.1 (built + tested same session):**
1. **Marker name labels in viewport** — `show_name` on every marker; each sphere now says "Left Knee" etc.
2. **Mirror markers, X/Y axis option** — new `hiho_mocap.mirror_markers` operator + `marker_mirror_axis` scene enum (X default; Y for sideways-facing characters). Two panel buttons: Left → Right, Right → Left. Mirror plane = character bounding-box center on the chosen axis (falls back to marker centroid if no character collection). Only the marker's mirror-axis coordinate flips; height/depth stay.
3. **Neck + Groin markers:** David asked about them; chose (via structured question) to KEEP 13 markers and derive neck/groin from shoulder/hip midpoints. Revisit only if BASEMENT testing shows the midpoint guess missing on real student characters.

**Tests:** 1.4.0 suite re-run on 1.4.1 zip + new checks (labels on; L→R mirror flips only the axis coordinate; R→L works). ALL PASSED.

**Note for the file:** `tomllib` pip-install errors during extension build are startup noise from one of David's OTHER installed addons (it tries to pip-install stdlib tomllib every launch), not HIHO. Ignore in future builds.

**Awaiting David:** hands-on with 1.4.1 (labels + mirror), then Day-3 Auto-Rig fit begins.

---

## 2026-07-01 (Day 1, cont. 4) — 1.4.2: Auto-Rig ships (Day 3+4 scope, two days early)

David confirmed 1.4.1 (labels + mirror) working on his SHOW_LOWPOLY character and invited Claude into his live Blender via the MCP connector (he's on Blender 5.1.2 — connector needs 5.1+, works). Scene verified live: character mesh + 13 placed markers.

**Shipped `hiho_mocap-1.4.2.zip` — the Auto-Rig:**
- NEW `core/marker_fit.py` — grows the 23 ajc27-named body bones from the 13 markers. Parenting/connect flags imported from `build_rig._ARMATURE_DEFINITION` (single source of truth); per-bone roll aligned to the canonical T-pose's local-Z (read off temp bones built from `_TPOSE`, mirrored if the character faces +Y) so constraint-driven twist matches the canonical rig. Forward-facing detection: toe-volume centroid vs ankle markers below ankle height, fallback -Y; forward axis follows the marker mirror axis setting.
- NEW `core/voxel_skinning.py` — HIHO-written glue (upstream wrapper is GPL, untouched): world-space mesh/bone text export, vendored binary as watched subprocess (600s timeout), weight import, ARMATURE parent. `skin_automatic()` = Blender Automatic Weights. Solver knobs: upstream defaults except max influences 8→4 (game-engine norm). Any voxel failure auto-falls-back to Automatic with the reason in the report.
- NEW `operators/autorig.py` — validates markers/meshes, refuses characters already rigged to a non-HIHO armature, purges the prior HIHO_AutoRig on re-run (modifiers + vertex groups + parenting, world transforms preserved), builds + skins, sets `character_target` to the new rig.
- NEW `external/voxel_skinning/` vendored: MIT LICENSE, README (provenance + build recipe), C++ source, `vhd_mac_universal` binary. Ships in the zip (157KB total).
- `skinning_mode` enum (Voxel default / Automatic) + panel toggle; Auto-Rig button in Character section.

**Tested (headless, end-to-end):** import multi-piece OBJ → markers → drag to joints (scripted) → Auto-Rig: 23 bones land exactly on markers (upper_arm.L, thigh.R spot-checked to 1e-4); all 8 pieces weighted, zero unweighted verts; floating hand sphere dominated by hand.L; re-run idempotent (one rig, no weight stacking); AUTOMATIC mode passes. ALL PASSED.

**Next:** David installs 1.4.2 → live Auto-Rig on his character (Claude can drive via MCP). Then Day-5 scope: Load Take + Send to Character wiring.

---

## 2026-07-01 (Day 1, cont. 5) — 1.4.3: depth centering (David's field find #1)

**David ran Auto-Rig 1.4.2 live on his character: WORKED** ("Voxel-skinned 17970 vertices to 23 bones") **but he spotted the flat-rig problem immediately:** markers spawn at one depth and students drag them in front view, so the whole skeleton sat on a flat plane — outside the body from any side angle. Exactly the kind of thing only a working artist catches on sight.

**Fix (1.4.3):** `marker_fit.center_marker_depth()` — at Auto-Rig time, cast a line through the character along the depth axis (perpendicular to the mirror axis) at each marker's position, collect all surface crossings across all mesh pieces, move the marker to the midpoint of the outermost crossings. Markers whose line misses the mesh stay put. Markers move visibly so the student can see and correct the decision; report says how many were centered. Re-running Auto-Rig re-centers (idempotent).

**Tested:** head piece offset 0.25 in Y + head marker at flat y=0 → after Auto-Rig marker y=0.25 (±0.02), neck bone depth follows. Full 1.4.2 suite re-passed on the 1.4.3 zip.

**Awaiting:** David re-runs Auto-Rig with 1.4.3 on his character (side view check). Then Day-5 scope (Load Take + Send to Character).

---

## 2026-07-01 (Day 1, cont. 6) — 1.4.4: head bone placement (David's field find #2)

**1.4.3 verified by David live: depth centering works** (rig inside body from side view). Remaining issue he flagged: **head bones** — on his chibi-proportioned character the neck ended at chin height and the forward "face" bone (the one that aims the head at the `nose` empty during mocap) poked out through the face. Cause: neck tail was `mid_shoulders + 0.5 × (head_marker − mid_shoulders)` and face length `0.7 × head_vec` — pure marker math, blind to how big the head actually is.

**Fix (1.4.4), mesh-informed head placement** in `marker_fit`:
- New `_axis_params()` helper — signed surface-crossing distances along any axis through any point (generalizes the depth-centering raycast).
- **Neck tail** = skull base: vertical line through the head marker gives head bottom/top; base = bottom + 20% of head height (guarded: never below shoulders; falls back to old formula if the line misses).
- **Face bone length** = 75% of the distance from the skull base to the front face surface along the forward axis (min 2cm; falls back to marker math if no hits). Stays inside the head by construction.

**Tested:** offset head sphere (center z=1.58, r=0.15) → neck tail z=1.49 (expected 1.49), face tip 0.126 from head center (< 0.15 radius = inside). 1.4.2 + 1.4.3 suites re-passed.

**Awaiting:** David re-runs Auto-Rig with 1.4.4 (head check). Day-5 scope (Load Take + Send to Character) is next regardless.

---

## 2026-07-01 (Day 1, cont. 7) — 1.4.5: neck-pinch head placement (1.4.4's fix was wrong)

**1.4.4's head fix FAILED on David's real character** (neck tail at eye level / crown; he initially suspected user error, checked, confirmed not). Root cause: the single vertical "skull top/bottom" probe is unreliable on real meshes — connected neck-to-body volumes have no chin crossing at all, and concave features (his deep eye sockets) add crossings that read as a false "head bottom." The 1.4.4 unit test only passed because its head was a detached ball the probe couldn't misread. Lesson for the log: probe fixes must be tested against CONNECTED, concave geometry, not idealized primitives.

**1.4.5 approach — silhouette pinch:** sample front-to-back outermost width at 23 heights between mid-shoulders and crown; the neck is the narrow band, the skull base is the top of that band (+10% nudge). Two guards from failures found in testing: (a) the pinch must sit BELOW the widest slice — a round head tapers to zero at the crown, which otherwise wins the narrowest contest (caught by the new connected-mesh test before shipping); (b) no real pinch (min ≥ 75% of max width) → marker-formula fallback. Depth midpoint at the junction also recenters the neck front-to-back. Face bone length logic unchanged (75% of distance to face surface).

**Tests now include the hostile case:** joined single-mesh head+body (no chin gap) → neck tail z=1.352 (true pinch zone 1.28–1.42 ✓), face tip inside head. Detached-ball suites re-passed (neck 1.467). MCP note: David's Blender MCP server doesn't auto-start after restart — reconnect needed per session.

**Awaiting:** David re-runs Auto-Rig with 1.4.5 on the chibi.

---

## 2026-07-01 (Day 1, cont. 8) — 1.4.6: David designs the head layout live (MCP session)

**Live MCP session in David's Blender (5.2, server started).** Diagnostics on his chibi showed 1.4.5's pinch-finder worked correctly (neck pinch found at z=5.37 on a 7.4-unit character, width profile clean) — the *placement rule* was what read wrong: skull-base neck + small forward face bone leaves a giant chibi head visually boneless. Claude previewed an ear-height variant live on his rig; David then **hand-edited the head bones in Edit Mode to his preferred layout**, which Claude measured directly from his edit session (edit-mode reads, since `data.bones` is stale in Edit Mode):

- `neck`: shoulders → skull base (pinch + ~5% of skull span). Short.
- `face`: skull base → **10% past the crown**, ~10% forward lean. One big bone spanning the whole skull — the classic animator head bone, tip grabbable above the crown.

**1.4.6 codifies David's proportions** in `marker_fit` (pinch machinery unchanged; placement rule his). This is the collaboration working as designed: algorithm finds the anatomy, the artist decides what the rig should BE, code encodes the artist's answer.

**Critical bind-time consequence documented (design doc amendment #2):** ajc27's `face` constraint is `DAMPED_TRACK nose` — correct for their short forward bone, but on the up-pointing spanning bone it would pitch the head ~90° forward at playback. **Send to Character (Day 5) must override `face`** → `DAMPED_TRACK head_center` + `LOCKED_TRACK nose`, axes to be verified empirically against a real take.

**Tests updated + all pass:** face-bone asserts flipped from "stays inside head" to "spans skull past crown" (detached: tail z 1.72–1.83 ✓; connected: 1.70–1.87 ✓); neck asserts hold (1.452 / 1.332).

**Awaiting:** David installs 1.4.6, exits Edit Mode, re-runs Auto-Rig (rebuild + re-skin with the new layout).

---

## 2026-07-01 (Day 1, cont. 9) — 1.4.7: David reverts the 1.4.6 head rule (risk call)

**David's call, and a sharp one:** after more hands-on time he judged 1.4.5's bone placement "acceptable for now" and ordered the 1.4.6 skull-spanning head bone REVERTED — because it forced a bind-recipe override, and changing the proven ajc27 constraint recipe days before BASEMENT is exactly the wrong kind of risk. Scope discipline from the artist; the deadline beats the prettier rig.

**1.4.7 = 1.4.5 fitter behavior, restored verbatim** (versions only move forward; a comment in `marker_fit.py` records the revert and why). Verified by running the exact 1.4.5 test suite against the 1.4.7 zip — all pass. Design doc amendment #2 marked REVERTED; the spanning-bone layout + its `face → DAMPED_TRACK head_center + LOCKED_TRACK nose` override design stay on record as a **post-July-7 candidate**.

**Consequence:** stock ajc27 constraint table now drives auto-rigged characters verbatim — no bind overrides anywhere. Simplest possible Day-5 wiring.

**State:** David should install 1.4.7 (or stay on 1.4.5 — identical fitter; 1.4.6 is the only odd one out). Next: Load Take + Send to Character.

---

## 2026-07-01 (Day 1, cont. 10) — 1.4.8: Load Take + Send to Character. FULL PIPELINE WORKS.

**Shipped `hiho_mocap-1.4.8.zip` — the Day-5 scope, on Day 1:**
- NEW `operators/load_take.py` — folder picker to any processed HIHO take; validates `output_data/mediapipe_body_3d_xyz.npy` (also tolerates picking output_data itself or one level above); sets `last_processed_path`; runs the shipped Spawn Rig (empties + skelly + constraints). Take-portable: works with folders copied from any machine.
- NEW `operators/send_to_character.py` — binds the picked character armature to the loaded take's empties via the STOCK ajc27 recipe (verbatim, per David's revert call): `ensure_virtual_empties` (idempotent) → `clear_hiho_constraints` → `apply_constraints`. Finger-bone skips reported as expected-and-friendly, missing BODY bones as a warning. (`operators/bind.py` stays retired/untouched; this is a fresh operator.)
- Panel: Choose Take now has real Load Take + processed-path field (restart recovery); Character's Send to Character is a real button. Library picker remains the one stub (v2.0).
- Build hiccup: parallel version-bump sed raced the registration edits; first 1.4.8 zip built unregistered — caught by checking zip contents, rebuilt. (Lesson: bump versions after content edits, not alongside.)

**FULL STUDENT PIPELINE TEST (headless, real data):** import multi-piece character → markers → Auto-Rig (voxel) → **Load Take on the real May-16 walk-cycle recording** → Send to Character → 37 HIHO constraints on the auto-rig → **hand.L world position moves 1.34 units between frames 10→60**. The character performs the take. PASSED.

**This completes the critical path David asked for on July 1 — six days before deadline:** FBX/OBJ upload ✓, marker auto-rig ✓ (voxel skinning ✓, mirror ✓, depth centering ✓), insert any HIHO mocap take ✓, motion on student character ✓. Remaining before BASEMENT: David's hands-on pass on 1.4.8, Save Out (export) if time, BASEMENT install + 2026-06-09 verify list, student-day prep.

---

## 2026-07-01 (Day 1, cont. 11) — 1.4.9: Load Take context bug (David's field find #3)

**David hit a real bug in 1.4.8's Load Take:** "Operator bpy.ops.object.armature_add.poll() failed, context is incorrect." Cause: an operator invoked through `fileselect_add` executes in the FILE BROWSER's context, where Spawn Rig's internal `armature_add` refuses to run. The headless test missed it because it calls the operator with `directory=` directly — the file-browser path never executes in --background. **Testing gap now known: fileselect-invoked operators need GUI verification.**

**Fix verified LIVE before shipping:** via the MCP session, ran spawn_rig under a `context.temp_override` with a real VIEW_3D window/area/region in David's Blender — his June-1 take (`2026-06-01_14-12-20`, the one his failed click had stored) built successfully: 63 bones bound. His scene got the take as a side effect, unblocking him immediately.

**1.4.9:** `load_take` now finds a VIEW_3D area and wraps the spawn_rig call in `temp_override` (+ object-mode guard); falls back to a bare call when no viewport exists (headless). Full-pipeline test re-passed on the 1.4.9 zip.

**Note:** the same fileselect-context risk applies to `import_character` (its importers are context-tolerant, and it has worked in David's GUI repeatedly) — but if a GUI-only bug ever surfaces there, this is the pattern.

---

## 2026-07-01 (Day 1, cont. 12) — 1.4.10: scale-to-character (David's field find #4, the crumple)

**David's first real Send to Character produced a crumpled character** — folded into a ball. Diagnosis via live MCP measurement: his character's hips rest at z=3.78; the recorded performer's hips ride at z=0.71. **5.36× scale mismatch**: the pelvis COPY_LOCATION yanks the giant character down to person-height and every over-long bone chain folds back trying to aim at targets sitting inside it. The headless test's character was human-sized (factor 1.2), so it never crumpled. ajc27 never hits this because their armature is BUILT at mocap-measured lengths; auto-rigged characters are built at CHARACTER lengths — the mismatch is inherent to our new feature and needed its own fix.

**Fix — verified live in David's scene first** (skelly scaled 5.36×, character un-crumpled), then codified in 1.4.10: `_scale_take_to_character()` in send_to_character — uniform-scales the skelly root by (character rest hip height ÷ recorded hip height, median of 3 sampled frames), clamped 0.05–100×. Original scale remembered in a `hiho_base_scale` custom prop so re-sends recompute from base instead of compounding. Factor reported to the student ("scaled the take to your character (x5.4)"). Skips gracefully when the rig has no `pelvis` bone or heights are degenerate.

**Tests:** full pipeline re-passed + new checks — scale applied (1.198 for the test chibi), at mid-take the neck stays ABOVE the pelvis (anti-crumple), pelvis rides near its own rest height, and re-send leaves scale unchanged (1.198 → 1.198, no compounding).

**Known limitation (v2.0 territory, per the parametric-retarget memory):** proportion differences (chibi limb ratios vs performer's) still shift where hands/feet land — scale fixes size, not proportions. Good enough for BASEMENT; the parametric rig is the real answer later.

---

## 2026-07-01 (Day 1, cont. 13) — 1.4.11: rotation retarget (David's field find #5: head collapse / foot crumple / wrist flips)

**David's verdict on 1.4.10: "much improved but still not complete"** — head fully collapsed, feet/shoes crumpling, wrists flipping wildly, hands rigid. Root cause of the first two: **uniform scale can't reconcile chibi proportions.** Hip-matched scaling leaves the performer's head-target above the chibi's crown (neck bends back = head collapse) and ankle-targets below the tall shoes (shins fold in = foot crumple). Position-targeting constraints only work when the skeleton is BUILT at performer proportions (ajc27's is; auto-rigs aren't — inherent to the new feature).

**Fix (1.4.11): Mixamo-style FK rotation retarget.** New `core/rotation_retarget.py`: world-space `COPY_ROTATION` per character bone from the SAME-NAMED bone on the skelly rig (which plays the take correctly at performer proportions), plus `COPY_LOCATION` on pelvis for travel. Character keeps its own proportions, borrows orientations — nothing reaches, nothing folds. The skelly rig's ajc27 recipe is UNTOUCHED (David's morning veto respected: this changes only the character layer, which was ours and broken). 1.4.10's uniform take-scaling stays (sizes the pelvis path + the visible skelly). Verified live in David's scene first (37 old constraints cleared, 23 bones retargeted), then shipped.

**Tests:** full suite re-passed + new: character thigh/forearm/neck world directions match the skelly's to 0.0° at mid-take.

**Known limitations logged honestly:**
- **Wrist flips**: character now mirrors the skelly's wrist flips — the pre-existing upstream issue (`project_hiho_mocap_wrist_flipping`, open since v1.1). The Polish section's "Fix wrist flips" stub (LIMIT_ROTATION) is the planned mitigation — post-critical-path candidate this week.
- **Rigid hands** (David's ask): auto-rigs have no finger bones (no finger markers). Skelly rig has all 63 incl. fingers, so the data exists — auto-finger-bones needs its own design (finger marker set? mesh-based finger detection?). **Post-July-7 backlog, explicitly.**
- **Foot skate**: FK retarget trades reach-folding for possible foot sliding. Acceptable per the chest-up classroom focus + capture-and-bake deliverable memories.

---

## 2026-07-01 (Day 1 wrap) — Verdict: "much improved" + David's corrective-smooth find

**David's close-of-day verdict on 1.4.11:** "much improved," and he added his own fix that "helped immensely" — a **Corrective Smooth modifier after the Armature modifier** on the character mesh (captured live: factor 0.377, iterations 191, smooth_type SIMPLE, rest_source ORCO). Notable: the paid voxel-skinning product ships a corrective-smooth baker as its companion feature — David independently converged on the industry pairing. **Candidate for this week: Auto-Rig adds a Corrective Smooth automatically** (David's numbers as the reference point; his 191 iterations is heavy — test perf on bigger meshes before defaulting).

**Day 1 final tally:** 11 builds (1.4.0 → 1.4.11), the full student pipeline working on real data on David's machine, 5 David field finds fixed same-day (flat rig → depth centering; head placement → silhouette pinch; head layout → built, then REVERTED at his call; file-picker context crash; proportion crumple → rotation retarget), 1 Claude-caught test-design flaw (crown-taper), 1 build-process mistake (version-bump race → unregistered zip, caught pre-delivery). All planned Day 2–5 scope from the design doc landed on Day 1.

**David's agenda for Jul 2: mocap camera RECORDING-side improvements** (his words — "further improvements need to be made on the Mocap Camera recording side of things"). Relevant standing docs: `HIHO_ADOPTABLE_INNOVATIONS.md` Tier 1 (per-frame timestamps = audit M9, parallel per-camera pipeline, selective hand tracking, dropped-frame interpolation), `project_hiho_mocap_camera_scaling` (4-cam USB wall), BASEMENT camera enumeration memory. Remaining sprint items after that: Save Out, wrist-flip polish (LIMIT_ROTATION), BASEMENT install + 2026-06-09 verify list, student-day prep.

---

*(entries below added as the sprint proceeds)*

## 2026-07-02 (Day 2, BASEMENT) — Recording side: ground-plane calibration was OFF; 1.4.12

**Scope correction from David (memory updated):** final products are NOT chest-up — that was the old single-cam era. Target is **full-body animation moving through the volume in full 3D range.** Consequence: yesterday's "foot skate acceptable per chest-up focus" justification is void; foot contact quality is promoted to a real polish priority. `project_chest_up_classroom_focus.md` rewritten to record the reversal.

**Camera rig change (physical):** ring → front-facing arc, per FreeMoCap's 40–60° neighbor-spacing guidance; camera heights/angles intentionally allowed to vary (calibration measures actual poses; asymmetry is fine). The stored 90/270 rotation pattern in `~/.hiho_mocap/camera_rotations.json` predates the move — Show Cameras check required before recording.

**Discovery: ground-plane calibration was silently off.** FreeMoCap 1.8.2's `use_charuco_as_groundplane` (board flat on floor at the start of the calibration take = world origin + up-axis) is installed in freemocap-env but `external/calibrate.py` hardcoded it `False`. Every calibration to date has been camera-0-origin — the likely root of tilted skeletons and the 5-second floor-standing workaround. Design note: `GROUNDPLANE_SOLVE_DESIGN_2026-07-02.md`.

**Shipped `hiho_mocap-1.4.12.zip` (one change):** `calibrate.py` flips `use_charuco_as_groundplane=True` (pin stays on as automatic fallback — upstream applies pin first, groundplane on top, and reverts gracefully on CharucoVisibilityError/CharucoVelocityError), and stops discarding `GroundPlaneSuccess`: outcome now emitted as an `HIHO_INFO::` line AND written to `GROUNDPLANE_STATUS.txt` in the take folder (June audit theme: no silent failure). DONE payload untouched (runner parses it as a bare toml path). Verified: py_compile + `--check` in freemocap-env pass; zip inspected (flag + status file present, manifest 1.4.12).

**New calibration ritual:** ONE board only ever in frame (the second board leaves the room). Board flat on floor, center, visible to all cameras, untouched for the first ~5s; then pair-painting the arc's 3 neighbor gaps 10–15s each; then slow volume sweep. ~90s total. Quality gate unchanged: <1px usable, ~0.5 good, >2 redo.

**Hypothesis logged (David's):** correct camera rotations + floor-true calibration may reduce the long-standing wrist flipping. Test against a take today before touching the LIMIT_ROTATION polish stub.

## 2026-07-02 (Day 2, cont.) — 1.4.12's Solve was DOA (Claude edit bug); 1.4.13; first floor-true calibration: 0.217 px

**Mistake, on the record:** while adding the groundplane flag to `calibrate.py`, Claude dropped the `calibration_videos_folder_path=str(sync)` argument from the solve call. 1.4.12's Solve failed instantly with a TypeError on David's first real use. **Why the tests missed it: `--check` exits before the solve call, and `py_compile` can't see a missing keyword argument.** Lesson for every future `external/` change: the cheap gate is necessary but not sufficient — exercise the real code path (a real solve/process on an existing take) before shipping. The recording itself was unharmed (solve is disk-side and re-runnable — the record/solve split earned its keep).

**Shipped `hiho_mocap-1.4.13.zip`:** the one missing line restored. Verified the honest way this time: full real solve on David's 2026-07-02_13-04-34 calibration take (90s, new front-arc rig, board floor-start).

**Result — the whole morning validated in one run:**
- Anipose solve successful; `groundplane OK: origin and up-axis set from the board's opening floor position` (new INFO line + `GROUNDPLANE_STATUS.txt` both worked as designed).
- Score: **0.217 px reprojection — "excellent"** (best this rig has produced; old lying-down calibrations were the previous method).
- Saved as `last_successful_calibration.toml` (default), plus calibrations + recording folders.

**State:** front-arc rig calibrated floor-true at 960×540. Next: David installs 1.4.13; short standing test take (bone-length jitter, floor contact, wrist-flip hypothesis check); then the Round-2 experiments (720p60 recorder dials + A/B, outlier-rejection A/B).

## 2026-07-02 (Day 2, cont.) — First floor-true take diagnosed; 720p60 verified live; 1.4.14

**First take on the new calibration (13-15-51), diagnosis via Blender connector:** data fundamentally healthy — heels ON the floor (2-4cm), no dead points, real motion. Three findings: (1) viewport "chaos" was largely the 84 empties' dashed relationship lines (turned off in David's viewport; consider disabling on Spawn Rig as polish); (2) **scene fps bug confirmed live: Load Take leaves Blender at 24fps while takes are 30 (now 60) → slow floaty playback; the April PPParty gremlin again. Backlog: Load Take must set scene fps to the take's real rate**; (3) real defect: whole body leans ~12° constantly. Board-track forensics (charuco_3d_xyz.npy): opening 10s = flat to 0.3-0.4° AND exactly z=0 in the final world → groundplane + calibration are CORRECT; the lean lives in body tracking. David's field diagnosis concurs: heavy motion blur (long exposures, dim room) + black pants on the legs = MediaPipe guessing the lower body. Consistent with full-body-scope stakes.

**720p60 verified on the real rig:** recorder dials added to `record_take.py` (`--width/--height/--fps`, RECORDER_DIALS_DESIGN doc). Direct terminal test blocked by macOS camera permission (Claude's shell can't open ANY camera — .command via David's Terminal is the pattern; `HIHO_SPEED_TEST.command` on Desktop, reusable). Verdict: all four C922s delivered ~300/300 frames at 1280×720@60. **1.4.14 ships the dials + defaults flipped to 720p60** (constants in camera_manager.py). Disk check: 130GB free, fine for 5× files.

**Next:** reinstall → Show Cameras (post-replug order check) → NEW calibration at 720p60 (resolution change invalidates the 0.217px one — new ritual take, bright lights) → test take (bright + leg contrast) → scene fps 60 manually until the Load Take fix lands.

## 2026-07-02 (Day 2, cont.) — 1.4.14's defaults never reached the panel; 1.4.15; requested-vs-delivered resolution truth

**Second Claude integration bug of the day:** the new `--width/--height/--fps` dials shipped with their own argparse defaults (960/540/30). The panel launches `record_take.py` with NO format flags, so the dial defaults silently overrode the flipped `DEFAULT_RESOLUTION`/`DEFAULT_FPS` constants — 1.4.14 recorded 30fps low-res exactly like 1.4.13. Caught because David's 13:49 calibration files probed as 576×1024@30 despite 1.4.14 being installed at 13:44. **Compounding lesson with 1.4.12: the speed test passed explicit flags — it tested Claude's invocation, not the user's button.** The verification that matters is the exact path the user clicks.

**Fix (1.4.15):** dial defaults now literal 1280/720/60 with a keep-in-sync comment pointing at camera_manager. Verified in-zip. Live verification = David's panel Record, probed on disk.

**Field truth uncovered while diagnosing:** the C922s never delivered the requested 960×540 — every historical recording is actually 1024×576 (writer records actual frame size; camera negotiates nearest native mode). "Requested ≠ measured" (audit M8 theme) applies to resolution too. The 13:49 calibration (0.20px, excellent, groundplane OK) is valid but married to 1024×576 — retired unused once 720p60 calibration lands.

## 2026-07-02 (Day 2 wrap) — 720p60 pipeline validated end-to-end; light+format fixes measurably better

**New calibration (14-02-02):** 120s take, 720p60, 0.27px "excellent" + groundplane OK. (0.27 at 1280-wide ≈ same fractional accuracy as the 0.20 at 1024-wide; longer take = more volume coverage. Both retired predecessors logged.)

**First 720p60 performance take (14-10-31), raw npy comparison vs the morning take (same script, scratchpad lean_check.py):**
- Heels while standing: **-7.5cm (below the floor!) → +0.1cm (dead on it)**
- Body plumb (ankles→shoulders): 2.4° → 1.9°; ankles→hips 5.3° → 4.0°
- Shin-length wobble (tracking steadiness): **2.2cm → 1.5cm (~1/3 steadier)**
- Leg points missing: 0% both (MediaPipe always guesses — quality shows in wobble, not gaps)
- Processing cost: ~2x frames × ~2.3x pixels ≈ 3-4× longer per take. Classroom-turnaround consideration, logged.

**Note on measurement:** morning Blender-scene lean read ~12° at frame 1 via empties, raw npy standing-window mean said 5.3° — the Blender import (ajc27 layer) transforms/grounds differently than raw npy. For A/Bs, measure the npy; for "what the artist sees," measure the scene. Both matter; don't mix them.

**Still open:** wrist-flip verdict needs eyeballs on playback (David, on return: Load Take → Spawn Rig; scene fps pre-set to 60). Load-Take-should-set-scene-fps fix is next on the backlog (fourth fps-mismatch incident today counting the morning 24fps find).

## 2026-07-02 (evening, home debrief) — Bake Animation ships (1.4.16)

**David's debrief asks:** bake button (bones carry keyframes → manual cleanup + retime experiments), markers question (answered: no — MediaPipe is markerless by training, contrast clothing is the lever), "run through FreeMoCap and compare" (answered: we ARE FreeMoCap; the meaningful A/B is the unused v1.8.2 outlier-rejection switch → running now on a copy of take 14-10-31), true fps cap (answered: 60 = C922 hardware ceiling; track@60 → deliver@24 in post is the correct pipeline, his instinct).

**Shipped `hiho_mocap-1.4.16.zip` — Bake Animation** (design: `BAKE_ANIMATION_DESIGN_2026-07-02.md`, David locked: bake-whatever's-selected; strip constraints + hide empties). New `operators/bake_animation.py`: two-pass visual-keying bake (sample all frames first, strip constraints, then key — no feedback contamination), action renamed `<rig>_baked`, empties hidden never deleted, plain report line. Button in Studio panel Export section.

**Tested BOTH ways (the new discipline):** 7-check headless suite (baked motion == live motion to 0.1mm; constraints stripped; action named; empties hidden) AND David's real button on the real take: 63 bones × 1800 frames = 1,134,000 keys, 0 constraints left, 81 empties hidden, "baked relatively quickly" (David). Verified in-scene via connector.

**Still open tonight:** outlier-rejection A/B (processing), remaining lean (small now), foot/wrist noise cleanup = David's manual pass on the baked keys + maybe outlier rejection + the stubbed Polish buttons (Smooth hands / Fix wrist flips) as future builds.

## 2026-07-02 (close) — Outlier-rejection A/B results + the cleanup recipe that works

**A/B (same take, default vs `use_triangulate_outlier_rejection=True`):** wrist jitter **-55%**, feet jitter **-19%**, torso slightly up but tiny in absolute terms, lean unchanged (it's tracker bias, not triangulation). Processed copy for eyeballing: `HIHO_CAPTURES/2026-07-02_14-10-31_OUTLIER_AB`. **Decision queued for tomorrow: expose outlier rejection on Process (likely default ON) — design note first.**

**David's cleanup verdict:** Graph Editor **Butterworth smooth at default settings on the baked curves "improved it massively."** The working recipe as of tonight: record 720p60 (bright light, contrast at joints) → floor-flat calibration → process (outlier rejection ON, pending build) → Bake Animation → Butterworth defaults → manual polish. This also reframes the stubbed "Smooth hands" Polish button: Butterworth-on-baked-curves may be the honest implementation, not One Euro. Design question for later.

**Tomorrow's queue:** (1) outlier-rejection option on Process, (2) Load-Take-sets-scene-clock (designed), (3) Save Out real implementation now that bake exists, (4) remaining sprint: wrist-flip check on cleaned data, BASEMENT student-machine install, Jul 7 prep.

**Eyeball verdict on the outlier-rejection A/B (side-by-side rigs in scene):** David: "omg... so much better" — and that's the RAW outlier version vs his Butterworth-cleaned default bake. Decision confirmed by numbers and eyes: **outlier rejection goes on the Process button, default ON (tomorrow's build, design note first).** Also logged: Load Take's folder-vs-file picker confusion tripped David — students will hit it too; polish list.

## 2026-07-03 (morning, house) — 1.4.17: outlier rejection on Process, default ON

**Design:** `OUTLIER_REJECTION_DESIGN_2026-07-03.md`, David signed off before code. Facts verified against the live freemocap-env (v1.8.2), not memory: param is `AniposeTriangulate3DParametersModel.use_triangulate_outlier_rejection` (ships False); its guardrails (`minimum_cameras_for_triangulation=3`, `maximum_cameras_to_drop=1`) are already right for the 4-cam rig, untouched.

**Shipped `hiho_mocap-1.4.17.zip`** (SOFTWARE/, built from SOFTWARE/ with explicit --source-dir/--output-dir): `external/process_take.py` grows `--outlier-rejection {on,off}` **default `on`** — 1.4.14 lesson applied: the panel passes no flags, so the default IS the student path. Mode echoed to the process log (`HIHO_INFO::outlier rejection: on`), groundplane-status spirit. No new panel UI, no runner changes, vendored code untouched.

**Pre-install checks (Claude's side, done):** `--check` on a dummy folder through the env: no-flag run reports `on`, explicit `off` reports `off`, both import+params OK. Pydantic assignment read back True. Zip inspected: manifest 1.4.17, new code present.

**Pending (David's path):** install 1.4.17 → Process button on staged copy `HIHO_CAPTURES/2026-07-02_14-10-31_OUTLIER_BUTTON_TEST` (raw Camera_*.mp4 only; originals + `_OUTLIER_AB` untouched) → Claude compares output npy to `_OUTLIER_AB` (same input + same setting → same numbers).

**1.4.17 VERIFIED (user's path):** David installed via fresh Blender, Claude set the panel fields over MCP (staged copy + canonical calibration + scene fps 60), David pressed Process. Output `mediapipe_body_3d_xyz.npy` is an EXACT match to `_OUTLIER_AB` (max diff 0.0 over 1800×33×3) and differs from the default solve by mean ~1.4cm / max ~35cm (units: mm in the npy) — the button path definitively runs outlier rejection. Test folder kept: `2026-07-02_14-10-31_OUTLIER_BUTTON_TEST`. Note: the `outlier rejection: on` INFO line surfaces in the panel status stream, not as a file in the take folder — fine for now, but the sidecar work (next build) is the pattern for on-disk truth.

## 2026-07-03 (mid-day, house) — 1.4.18 built: Load Take sets the scene clock

**Shipped `hiho_mocap-1.4.18.zip`** (design: `LOAD_TAKE_FPS_DESIGN_2026-07-02.md`, coded only after 1.4.17 verified — one change at a time). Two edits: `external/record_take.py` writes `HIHO_RECORDING_INFO.json` (fps/width/height/camera_ids/duration_sec) into the take folder after a clean recording; `operators/load_take.py` reads it after spawn — sets `scene.render.fps` + frame range 1→npy frame count, reports "Scene clock set to Nfps". No sidecar → loud WARNING ("Old take - no recording info"), scene untouched, never a silent guess.

**Test state (pending David):** read path staged at the house — truthful fixture sidecar written into `_OUTLIER_BUTTON_TEST` (fps 60), David's open scene deliberately set to 24fps/250 frames; expected: Load Take → 60fps, 1–1800. Legacy-warning path: Load any pre-sidecar take. **Write path NOT yet verified** — needs a real panel recording (laptop junk take or first BASEMENT take tonight: check the JSON appears in the new take folder).

**Remaining queue:** Save Out (real, bake exists), wrist-flip verdict on cleaned data (David's eyes, `_OUTLIER_AB`), corrective-smooth candidate, BASEMENT student-machine install + verify list, Jul 7 prep. Polish: folder-vs-file picker, "preview live" status wording.

**1.4.18 read path VERIFIED (BASEMENT, David's clicks):** sidecar take → clock 24→60fps, range 1–1800, status message correct. Legacy take (`2026-06-01_14-12-20`) → WARNING banner shown, clock untouched (read 24 because David undid test 1 first — undo reverts the clock set, correct `bl_options` UNDO behavior). Incidental find: `core/output_rig.py:101` has always grown `frame_end` via max() on spawn (never shrinks, never touches fps) — coexists fine with the sidecar path, which sets the exact range afterward. **Write path still pending: first real panel recording tonight → confirm `HIHO_RECORDING_INFO.json` appears in the new take folder.**

## 2026-07-03 (afternoon, BASEMENT) — camera-moved incident → 1.4.19: quality score on the board

**1.4.18 write path VERIFIED:** David's first real panel recording (`2026-07-03_14-38-05`, 40s) wrote a correct `HIHO_RECORDING_INFO.json` (60fps/1280x720/cams 0-3). Cameras delivered true 720x1280@60, 4x2400 frames, synced. Gap found by David in the same breath: the Record→Process→Spawn Rig path never reads the sidecar (only Load Take does) — frame range grew (old `output_rig.py:101` max() behavior) but fps stayed. Design anticipated this ("process.py's post-process flow eventually"); eventually = now, that's the PRIMARY student path. Queued as 1.4.20.

**Incident: take "noisier than yesterday" (David's eyes — again the best instrument).** Audit: recording format ✓, calibration used = canonical 14-02-02 via `last_successful_calibration.toml` fallback (byte-identical) ✓, outlier rejection ✓. But mean reprojection 68px vs yesterday's 17, heels −6.6cm vs −0.4cm, jitter 2–3×. Geometry disagreement + floor drift = **a camera moved after yesterday's 14:02 calibration** (already moved by the unnoticed 14:26 take, 47px). Not lighting: light degrades 2D tracking, not cross-camera agreement. David recalibrating.

**Shipped `hiho_mocap-1.4.19.zip` — process quality score** (design: `PROCESS_QUALITY_SCORE_DESIGN_2026-07-03.md`, David approved). `process_take.py` scores mean reprojection after every solve → `PROCESS_QUALITY.txt` in the take folder (written before the DONE sentinel; cleared with sentinels at start) + INFO line. Blender side: `process_verdict` scene prop, verdict box under Process Mocap (GOOD ≤30px / CHECK ≤50 / BAD >50, alert on BAD), status line carries it too. Bands from all 10 processed takes on disk: good era 15–22, today 47/68, June ring era 74–84. Unit-tested against all three eras: GOOD/CHECK/BAD all fire correctly. 720p60-specific bands — re-derive on format change (recipe in design note).

**Pending:** David's recalibration → panel-Process `2026-07-03_14-38-05_RECAL_TEST` (staged copy, raw videos + sidecar) → expect verdict box GOOD ~17px = live proof of both the score and the recalibration.

## 2026-07-03 (evening, BASEMENT) — score's first catch, drift confirmed, groundplane FLIP found

**Recalibration test:** the 14:38 take reprocessed against the fresh 15:14 calibration still scored BAD (66.6px) — because cameras kept moving between the take and the calibration. Pairwise camera-distance comparison across the two calibration tomls (frame-invariant): cams 1+3 moved 3–7cm relative to the rigid 0–2 pair between Jul 2 14:02 and Jul 3 15:14. **David's diagnosis is the doctrine: ceiling mounts + old SF building = cm-scale drift between sessions; calibration is a PER-SESSION RITUAL, not setup.** Clamps are tight; both solves were "excellent" (steady on the minutes scale). The 14:38 take is orphaned (matches no calibration; kept, never delete).

**Fresh take `15-55-14`** (after a false start — laptop power brick was stealing a USB port; add to session checklist): **GOOD 25.3px** through the panel. Drift theory confirmed; USB-replug enumeration scare didn't materialize.

**Then the flip.** Same take: heels read −59cm, 71% of frames below floor, heel-z vs position R²=0.83, body-up 130° off +Z. Board WAS flat and untouched (verified by extracting the calibration take's opening frames — David's ritual was perfect; camera 2's edge-clipped board view matches yesterday's, not the cause). Decisive check: **camera heights in the calibration's own world frame — yesterday all ~+1.6m; today −0.5 to −2.2m. All four cameras underground = the upstream charuco groundplane picked the wrong side of the planar pose ambiguity** (flat targets at shallow angles have two PnP solutions) and reported OK.

**Why David's rig still looked right:** `core/loader.py` re-levels from the body at load (ajc27's put_skeleton_on_ground lineage) — body-based alignment masks a flipped world. Honest metric note: post-alignment residual-tilt regressions are unreliable (R²≤0.31, motion-dominated; the enforce step pins heels), so the precision cost after alignment is unmeasured. Reprojection also can't see orientation — the score correctly said GOOD while the world was upside down. Different instruments see different failures.

**Queue from today (design-first, in order):** (1) 1.4.20 sidecar read on Record→Process→Spawn path (David's find, primary student path); (2) calibrate.py post-solve sanity check — all camera heights positive + roughly consistent, else groundplane FAILED loudly (would have caught today's flip at solve time); (3) candidate: floor/orientation stat in PROCESS_QUALITY (body-up angle on raw data); (4) session checklist: calibrate first, unplug the power brick, board opening spot central. Upstream note: the ambiguity + silent flip is worth reporting to FreeMoCap once we have the check written.

**Four-cam optimization research landed:** `FOUR_CAM_OPTIMIZATION_RESEARCH_2026-07-03.md` (two parallel web-research passes: FreeMoCap docs/Matthis notes + Pose2Sim/Anipose/OpenCV/C922 tooling; Discord is login-walled, its public echo is Matthis's HackMD + the troubleshooting docs). Headlines: David's performance-noise read confirmed (4 cams = lean end for fast floor work; Pose2Sim optimal is ~6 for occlusion-heavy movement); THE official fast-motion lever is manual exposure -7/-8 + more light, scriptable on macOS via uvcc (C922-supported) → future HIHO_CAMERA_SETTINGS.command in the session ritual; all-cams-at-1.6m is the known-weak config for floor work — height-diversity remount is the big deliberate experiment; groundplane flip = OpenCV planar two-fold ambiguity, undocumented in FreeMoCap (upstream report opportunity once our check ships); cheap A/B queued: min-cameras 2 vs 3 reprocess on today's floor-work take. Order of attack in §6.

## 2026-07-04 (morning, house) — research day first: the 6-camera question answered

Three parallel web-research passes (USB bandwidth/C922 formats, headless-Mac capture node, 6-cam placement geometry) landed in `SIX_CAMERA_SCALING_RESEARCH_2026-07-04.md`. Headlines: David's resolution-drop idea is impossible at the descriptor level (C922's ONLY 60fps mode is 1280×720 MJPEG) — but unnecessary: this M4 laptop has THREE independent USB controllers (verified via ioreg), and 2 C922s/controller is field-proven, so **6× 720p60 on the laptop alone is ~75% likely (2+2+2 across the three ports)**. Proof costs one ~$25 powered hub + the existing speed test with 4 cams split 2+2 across two ports. Headless broken-screen MacBook node fully researched as Plan B / path-to-8 (one borrowed-monitor bootstrap session; cross-machine sync must be the brightness FLASH via skelly_synchronize — OpenCV records silent video, audio sync impossible). Studio scheme: ~270° wrap, three height bands (2 high / 2 mid / 2 low), never a 180°-opposed pair, portrait; anipose chains pairwise board views so no all-camera floor spot is needed. Camera-scaling memory updated; David green-lit queue items 1–3 for autonomous build and went to do character work.

## 2026-07-04 (midday, house) — 1.4.20: scene clock on the Spawn path (primary student path)

**Design:** `SIDECAR_ON_SPAWN_DESIGN_2026-07-04.md`. The 1.4.18 clock logic moved verbatim into a shared helper (`core/scene_clock.py`); **Spawn Rig calls it** — both student paths (Record→Process→Spawn and Load Take) converge there, closing David's 2026-07-03 find. Load Take's inline block replaced by the same helper (messages byte-identical to the 1.4.18-verified strings; helper runs twice on the Load Take path — idempotent, documented so nobody "fixes" it). Spawn Empties (debug) untouched.

**Tested headless** (Blender 5.2 LTS, --factory-startup, addon from source — David's install untouched): 11/11 PASS. Sidecar fixture (`_OUTLIER_BUTTON_TEST`): 24fps/250fr scene → spawn → 60fps, range 1–1800 (npy-exact). Legacy fixture (original `14-10-31`): scene untouched + WARNING. Message strings compare equal to 1.4.18's. **Shipped `hiho_mocap-1.4.20.zip`.** David's-path verification pending: his next Spawn after Process should say "Scene clock set to 60fps".

## 2026-07-04 (midday, house) — 1.4.21: groundplane flip caught at solve time

**Design:** `GROUNDPLANE_SANITY_CHECK_DESIGN_2026-07-04.md`. `external/calibrate.py`: after a groundplane-success solve, parse the produced toml (stdlib tomllib), camera center = −Rᵀt per camera, height = world z. Any camera at/below the floor ⇒ `GROUNDPLANE_STATUS.txt` + INFO line become **FAILED: world is flipped upside down (heights listed) + the ritual fix** (board central and large). Healthy solve now records its camera heights in the OK status (drift-watching gets numbers for free). Deliberately NO height-consistency check (the 6-cam plan staggers heights — above-floor is the invariant that survives every layout). Check wrapped so a parse hiccup can never sink a good calibration. No auto-flip-fix — loud failure only; upstream report still queued.

**Tested against the real fixtures** (freemocap-env, calling the shipped functions): good 07-02 toml → "; cameras above floor at 1.61m, 1.66m, 1.58m, 1.56m"; flipped 07-03 15-14 toml → FAILED loud; missing toml → skipped-note, no exception. `calibrate.py --check` import path clean. **Shipped `hiho_mocap-1.4.21.zip`.** Live catch awaits the next BASEMENT calibration.

## 2026-07-04 (afternoon, house) — 1.4.22: Save Out is real (Export section complete)

**Design:** `SAVE_OUT_DESIGN_2026-07-04.md`. New `operators/save_out.py` replaces the stub: save-file picker; FBX (`use_selection`, `add_leaf_bones=False`), GLB (`use_selection` — confirmed the 5.2 param name from the operator's RNA, not memory), .blend (`save_as_mainfile(copy=True)` — whole scene, report says so). Operator auto-selects the armature + child meshes (students won't remember to shift-click the character). **Loud guard on both entry points:** any pose-bone constraint ⇒ "press Bake Animation first" and refuse — exporting a live-constraint rig makes a T-pose file, the classic silent failure. Panel button rebound; stub remains only for Preview/library/Polish items.

**Tested headless:** 11/11 PASS — unbaked rig refused (no file written); after bake (constraints 0): FBX 28.5MB / GLB 180KB / .blend 8.5MB all written with extension enforcement; **round-trip proof:** FBX and GLB re-imported into the session each yield 1 armature, 63 bones, action present. **Shipped `hiho_mocap-1.4.22.zip` — the canonical build.** David's-path check pending on his chibi (same code path, different object).

**Sprint state after today:** queue items 1–3 done. Remaining before Jul 7: wrist-flip verdict (David's eyes, `_OUTLIER_AB` — pinged him), corrective-smooth candidate (design question), BASEMENT student-machine install + 2026-06-09 verify list, polish items (folder-vs-file picker, preview status wording). Candidate follow-on from 1.4.21's design: floor/orientation stat in PROCESS_QUALITY (queued 2026-07-03, unbuilt).

## 2026-07-05 (BASEMENT, varied-heights session) — 1.4.23: square size becomes a panel setting (board measured: 110mm, not 100)

**The find:** first varied-heights calibration (4 cams: ~2'2"–5'8" bands, 13-00-16 take) solved excellent 0.35px, groundplane OK — 1.4.21's height report fired live for the first time and the numbers looked uniformly low. David tape-measured the house Skelly Shop board: **one black square = 110mm** (ruler photo read: left edge 4mm, right edge ~114mm), 5 squares along the long edge — the board's own printed edge text confirms `squares_x=5, squares_y=3`. Every calibration to date passed the hardcoded `--square-mm 100` → **every solve so far uniformly ~10% small.** Harmless for retargets, wrong for real-world distances. (The board literally prints "measure this and input into FreeMoCap" on its edge.)

**Design:** `SQUARE_SIZE_PANEL_DESIGN_2026-07-05.md` (David's call: value slot in the Calibrate section, default 110). Scene prop `charuco_square_mm` (Float, default 110, clamp 10–500); panel row under Board take; Solve passes it instead of the literal; Check Calibration passes the SAME value to the scorer via `run_score(square_mm=...)` (scorer builds its 3D board from it — solve/score mismatch would corrupt the verdict). Board shape stays hardcoded 5x3; CLI defaults untouched (panel always passes the flag, so the student path is explicit).

**Tested headless** (Blender 5.2 LTS, --factory-startup, addon from source): 10/10 PASS — default 110, clamps both ends, run_score cmd carries `--square-mm 110` (omits when not given), Solve operator args carry `--square-mm 110` + `--board 5x3`, non-default 87.5 flows through. **Shipped `hiho_mocap-1.4.23.zip`** (built from SOFTWARE/, manifest + new code verified in-zip). Live validation next: David reinstalls, re-solves the same 13-00-16 take — expect heights ~×1.1 (1.33/1.25/1.72/0.74m) at unchanged px, then compare against tape-measured lens heights.

**1.4.23 VALIDATED LIVE + varied-heights verdict (same day, BASEMENT):** David reinstalled, re-solved the same 13-00-16 take through the panel — px unchanged (excellent 0.35), groundplane heights 1.33/1.26/1.74/0.74m (exactly ×1.1 of the 100mm solve; cam 2 at 1.74m = "just over my head", David is 5'8" — eyeball-consistent, tape check next visit). Performance take `13-37-13` (40s @ 60fps: walk/crouch/kneel/sit/reach): **PROCESS_QUALITY GOOD 16.5px — best-band solve with cameras at FOUR different heights (2'5"–5'8")**. Scene clock auto-set on Spawn (1.4.20 user-path verified). Cleaned (Bake → Butterworth ×2 → NLA SMOOTH fmod): right ankle never below floor (min +2.9cm), jitter 4.2→2.9mm/2fr (−32%); floor-sit pose resolves cleanly, no leg L/R swap. **WRIST-FLIP SPRINT ITEM CLOSED: quaternion sweep of forearm/upper_arm across all 2400 baked frames = zero events >20°/frame, worst 15°** (David's eyes concur). Sweep gotcha logged in the wrist memory: use min(a, 360−a) — rotation_difference can report ~358° for a ~2° change. Varied heights = doctrine for the 6-cam layout. Tomorrow: hub #2 topology test (2+2 across two ports).

## 2026-07-06 (morning, house) — 1.4.24: the camera picker (Show Cameras becomes point-and-click)

**Context:** promoted from polish backlog Jul 5 — enumeration shuffling × 6 future cameras makes "preview, read indices, type them" untenable, and the failure mode is silent garbage triangulation. Hub #2 still in transit; topology test queued for later today.

**Design:** `CAMERA_PICKER_DESIGN_2026-07-06.md` (David approved right-click). Pick by eyes, not hardware ID (identical C922s report absent/duplicate serials; OpenCV exposes no IDs — option B logged for v2). The Show Cameras window now ALWAYS detects everything; the panel's list rides in as `--selected` (those tiles start included). **Left-click = rotate (unchanged), right-click = include/exclude** (excluded tiles dim + "EXCLUDED — right-click to include" banner; window title counts "recording N of M"). On Q/ESC the script emits `HIHO_CAMERAS::<sorted csv>`; the runner stores it; the preview poll writes it into `camera_ids` ("Recording cameras 0,1,2,3."). All-excluded close keeps the old list, loudly. Window killed via X → no marker → box untouched. Record path unchanged.

**Files:** `external/record_take.py` (picker + `_parse_selected`/`_selection_csv` helpers + marker), `core/external_runner.py` (`HIHO_CAMERAS::` → `cameras_csv` property), `operators/external_capture.py` (`--selected` out, poll applies result, tooltip), `ui/panels.py` (hint lines), `properties.py` (camera_ids tooltip).

**Tested:** 17/17 pure-Python in freemocap-env (marker consumption incl. empty payload; selection parse/toggle/csv incl. malformed + undetected ids; `_grid` synthetic-frame render, excluded tile measurably dimmed 70-vs-200, record path unaffected) + 9/9 headless Blender 5.2 `--factory-startup` from source (picked csv lands in `camera_ids`, empty selection keeps old value + explains, no-marker leaves box + generic hint, Show Cameras arg construction with full and blank box). **Shipped `hiho_mocap-1.4.24.zip`** (built from SOFTWARE/, in-zip manifest verified 1.4.24). Live check (David's path): home laptop cam + a C922 — right-click the laptop out, Q, watch the box; then Record and confirm only included cameras write mp4s. Full ritual at next BASEMENT visit.

## 2026-07-08 (BASEMENT) — hub-topology test PASSED + HIHO_SPEED_TEST_6CAM.command + 6-cam readiness audit

**The gate cleared:** David ran `HIHO_SPEED_TEST.command` with the 4 cams split 2+2 across the two SABRENT hubs on two Thunderbolt ports. Pre-flight `ioreg` confirmed the hubs sat on two SEPARATE `AppleT8132USBXHCI` controllers (2× C922 each; third controller empty). **All four cameras 300/300 frames, true 60fps, ~11s wall** — identical to the 2026-07-02 single-topology pass. Third lane is the same silicon ⇒ 6× 720p60 on the laptop alone is near-certain. Cameras 5–6 cleared for purchase; second-computer node is now only the path to 8. Memory updated (`project_hiho_mocap_camera_scaling.md`).

**6-cam readiness audit (no addon changes needed, none made):** grepped record/preview/calibrate/process/score + core + operators for camera-count assumptions. Everything is parameterized by camera list: `detect_cameras` probes 0–9 (covers 6 C922 + laptop cam), rotations default 0 for unseen ids (`rotations.get(cid, 0)`), grid is N-generic, `score_calibration` reads n_cams from the data shape, defaults "0,1,2,3" are editable fallbacks not limits. The two hits that looked suspicious were a docstring example (`camera_manager.py:214`) and a head-geometry sample count (`marker_fit.py:174`). The 1.4.24 picker was the real prerequisite and it's already shipped. Still open after first 6-cam data: re-derive quality bands (Jul 3 recipe) — data-driven, can't be done pre-hardware.

**New: `~/Desktop/HIHO_SPEED_TEST_6CAM.command`** (per SIX_CAMERA_SCALING_RESEARCH §5.3, one deliberate deviation): instead of hardcoding `--cameras 0,1,2,3,4,5` — wrong whenever the laptop cam lands inside 0–5, which enumeration WILL do — it runs picker-first: Stage 1 opens the 1.4.24 preview picker (right-click excludes the laptop cam by eye, Q closes), captures the `HIHO_CAMERAS::<csv>` marker; Stage 2 records 5s from exactly that list and checks frames per camera (≥270 of ~300 = true 60fps; file-count-vs-picked-count check; wall-time note at >20s for 6-cam warmup). Empty/no pick aborts loudly, records nothing. **Tested:** `zsh -n` clean; marker extraction against a synthetic picker log (`0,1,2,3,5,6` → N=6); verdict block against the REAL morning take (passes, "all 4 cameras") and against a simulated 6-expected/4-found case (fails loudly). Camera stages untestable from Claude's shell (no camera permission) — David's double-click path when cameras 5–6 arrive.

## 2026-07-12 (BASEMENT) — floor-check badge in the panel (1.4.25)

**Field find (David, first 6-cam calibration):** the solve's groundplane check FAILED
(world flipped underground, camera heights negative) but nothing in the addon said so —
the completion status read "Calibration complete", and Check Calibration showed
"Quality: Excellent (0.28 px)" because reprojection scores camera agreement, not
which way is up. The verdict existed only in GROUNDPLANE_STATUS.txt and the terminal.
Same silent-failure theme as the June audit; David only caught it because Claude read
the sentinel file off disk.

**Design (this entry; display-only, one change):** surface the sentinel the solver
already writes.
- New scene prop `groundplane_status` — holds GROUNDPLANE_STATUS.txt's text from the
  last Solve ("" = no solve yet / file missing → no badge, old behavior).
- Solve clears it on start; `_poll_calibration` reads the sentinel from the take
  folder on completion. On FAILED the status line says so loudly instead of
  "Calibration complete."
- Panel: second badge under the quality badge — "Floor: OK (set from board)"
  (checkmark) vs "Floor: FAILED - re-record calibration" (red alert). Two badges,
  two questions: cameras agree? floor real? Both must be green before a take.
No solver changes; calibrate.py untouched.

**Built `hiho_mocap-1.4.25.zip`** (blender --command extension build, from HIHO_MOCAP/;
zip contents verified: manifest 1.4.25 + all three edited files carry the new code).
**Tested without Blender:** py_compile clean ×3; badge logic against the REAL failed
sentinel from today's first 6-cam calibration → "Floor: FAILED - re-record calibration";
OK-prefix case → "Floor: OK (set from board)"; missing file → "" (no badge, old
behavior). Untestable from Claude's shell: the live panel draw + solve round-trip —
David's install is the real test. 1.4.24 remains canonical until his live check passes.
