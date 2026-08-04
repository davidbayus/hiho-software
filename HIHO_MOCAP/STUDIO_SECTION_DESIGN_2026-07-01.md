# STUDIO_SECTION_DESIGN_2026-07-01.md — Completing the Studio Panel for BASEMENT student testing

**Status:** design. Awaiting David signoff before code.
**Deadline:** July 7, 2026 — students test at BASEMENT.
**Prereqs read:** [AUTORIG_RESEARCH_2026-05-28.md](AUTORIG_RESEARCH_2026-05-28.md), [BIND_TO_RIG_DESIGN.md](BIND_TO_RIG_DESIGN.md), [HIHO_MOCAP_v1_PLAN.md](HIHO_MOCAP_v1_PLAN.md), `panel/studio_panel.py` (all stubs), SESSION_HANDOFF_2026-06-09 / 06-17 / 06-26.
**Base build:** `hiho_mocap-1.3.18.zip` (canonical, headless, Blender 5.0+). This work is the **1.4.x series**.
**Process record for Opus review:** [DEV_LOG_STUDIO_SECTION_JULY2026.md](DEV_LOG_STUDIO_SECTION_JULY2026.md), updated every working step.

---

## David's four scope decisions (2026-07-01, this session)

1. **Skinning engine: modernize the MIT voxel skinner** (meshonline). David knows from hands-on rigging that voxel skinning handles multi-piece student characters far better than Blender's built-in Automatic Weights. **Fallback wired in:** the skinning step is swappable; if the voxel path isn't proven by end of Day 4, Auto-Rig falls back to Automatic Weights and July 7 is still safe.
2. **Rig-fit UX: student places marker empties** (the original May design). ~13 named markers; the student drags them onto their character; Auto-Rig does the rest.
3. **"Insert a new mocap file" = pick any processed HIHO take folder from disk.** Any HIHO recording, this machine or copied from another. No foreign BVH/FBX retargeting in this release.
4. **Scope priority: character pipeline first.** Import Character → Auto-Rig → Load Take → motion on character. Then Save Out (export), then Polish, only if days remain.

## Verified 2026-07-01 (unblocks the skinning decision)

The `meshonline/Surface-Heat-Diffuse-Skinning` GitHub repo:
- **The solver IS voxel-based.** Author's README: "I have replaced the octree with naive voxel grid." The "Surface" name is historical. This resolves the research doc's sharpest open question — the free MIT repo has the voxel capability; we do not need the paid product for anything.
- **MIT license** stated repo-wide. Day 1 task: confirm at file level per the research doc's caveat.
- **Full C++ source in `/src`.** Prebuilt binaries are Intel-only (2022). We compile our own on the M4, ideally a universal binary (arm64 + x86_64) so any BASEMENT Mac can run it.
- **Multi-sub-mesh support confirmed** ("Select all the sub-meshes and one armature").
- Their Blender addon wrapper targets 2.7/2.8 — we do NOT port it. We write our own thin glue (export mesh + bones → run binary → import weights), same pattern the solver expects.

---

## The student flow (what July 7 must deliver)

1. Student opens Blender, HIHO MOCAP N-panel, **Studio** section.
2. **Character → Import Character**: file picker, `.fbx` or `.obj`. Their character lands in the scene, in its own collection, selected.
3. **Character → Add Markers**: 13 named marker empties appear in a rough human layout next to the character. Student drags each marker to the matching spot on their character (both hips, knees, ankles, shoulders, elbows, wrists, head). Plain-language names on the empties ("Left Knee", not "knee.L").
4. **Character → Auto-Rig**: one click. HIHO builds a Rigify-metarig-named armature fitted to the markers, then skins the mesh (all sub-meshes) to it with the voxel solver. Character now has bones.
5. **Choose Take → Load Take**: folder picker to any processed HIHO take. The 33 empties spawn and play (existing spawn machinery).
6. **Character → Send to Character**: the existing Bind to Rig machinery (shipped v1.1, constraint table already speaks Rigify names) binds the auto-rigged armature to the empties. Press Space: the student's character performs the take.

Steps 5–6 reuse shipped code. Steps 2–4 are the new build.

---

## Feature 1 — Import Character (FBX/OBJ)

- Operator `hiho_mocap.import_character`, file picker filtered to `.fbx;.obj` (per [[operator-file-pickers]]: picker, never auto-populate).
- FBX via `bpy.ops.import_scene.fbx`, OBJ via `bpy.ops.wm.obj_import` (the 5.x native importer).
- Post-import normalization: move imported objects into a `HIHO_Character_<name>` collection; report object + vertex counts; **do not** auto-apply transforms or auto-scale (too invasive; students may have intentional setups). If the character is wildly off-scale relative to the mocap skelly, the marker fit handles it — bones are built where the markers are, and the Damped Track constraint stack tracks direction, not position, so character proportions are preserved regardless of David-vs-character size difference.
- Edge cases: FBX that contains its own armature (Mixamo re-import) — imported as-is; Auto-Rig warns if a rig already exists on the mesh and refuses (one rig at a time). Empty file / unreadable: clear error report.

## Feature 2 — Add Markers

- Operator `hiho_mocap.add_markers`. Spawns 13 empties (PLAIN_AXES, sized relative to character bounding box, in a `HIHO_Markers` collection):
  head, shoulder L/R, elbow L/R, wrist L/R, hip L/R, knee L/R, ankle L/R.
- Initial placement: a rough humanoid template scaled to the imported character's bounding box, standing at the character's location — so most markers land near-right and the student only nudges.
- Empty display names are plain language ("Left Knee"); internal names are stable IDs (`hiho_marker_knee.L`) so Auto-Rig finds them regardless of display renames.
- Idempotent: re-running moves existing markers back to template positions rather than duplicating.

## Feature 3 — Auto-Rig (the HIHO Mixamo)

Two halves, per the research doc.

> **AMENDMENT 2026-07-01 (found during build, before code):** the bone names below
> originally followed the May BIND_TO_RIG_DESIGN Rigify-metarig convention. That
> design is superseded in the live codebase: `operators/bind.py` is RETIRED, and the
> live constraint table (`core/bind_to_rig.py`, used by today's Spawn Rig) is verbatim
> ajc27 — names like `pelvis`, `spine`, `spine.001`, `neck`, `face`, `heel.02.R`.
> **Auto-Rig therefore builds ajc27-named bones**, so the existing live
> `apply_constraints()` drives the student character directly with no translation
> layer, and bones we don't build (fingers) are skipped by the existing
> missing-bone handling. Roll conventions come from `core/build_rig.py`'s `_TPOSE`
> table (the canonical ajc27 orientations already in our codebase) rather than from a
> Rigify metarig. Table below rewritten to ajc27 names.

### 3a. Fit: build an ajc27-named armature from the 13 markers

Bone derivation table (all names = ajc27 convention, matching the live constraint table):

| Bone | Head | Tail |
|---|---|---|
| `pelvis` | mid(hip.L, hip.R) | ¼ of the way up toward mid-shoulders |
| `pelvis.L/R` | pelvis head | hip.L/R marker |
| `spine` | tail of pelvis | ⅝ up toward mid-shoulders |
| `spine.001` | tail of spine | mid(shoulder.L, shoulder.R) |
| `neck` | mid-shoulders | ⅔ toward head marker |
| `face` | tail of neck | head marker, projected forward — tracks `nose` |
| `shoulder.L/R` | on spine.001 tail, offset toward marker | shoulder.L/R marker |
| `upper_arm.L/R` | shoulder marker | elbow marker |
| `forearm.L/R` | elbow marker | wrist marker |
| `hand.L/R` | wrist marker | wrist + 0.35 × forearm-length along forearm direction |
| `thigh.L/R` | hip marker | knee marker |
| `shin.L/R` | knee marker | ankle marker |
| `foot.L/R` | ankle marker | ankle projected forward (character −Y) and down toward ground |
| `heel.02.L/R` | below ankle at ground | short bone along +Y at ground |

Exact spine-chain proportions and heads/tails follow `core/build_rig.py`'s `_ARMATURE_DEFINITION` + `_TPOSE` (parenting, connect flags, roll conventions) — we reuse ajc27's canonical skeleton shape, scaled and positioned by the markers. Finger bones are NOT built (no markers); the live constraint code already skips missing bones with a warning list.

### 3b. Skin: voxel heat diffuse, external binary

- Vendor the MIT repo under `external/voxel_skinning/` (source + LICENSE + our compiled binary `vhd_mac_universal`). AGPL-3.0 + MIT = compatible; keep their copyright header intact.
- Glue (`core/voxel_skinning.py`): export selected meshes + armature to the solver's exchange format, run the binary via `subprocess` (same external-runner pattern as FreeMoCap — no wheels, no sys.path games, Extensions-platform safe), parse weights back, create vertex groups.
- Timeout + failure handling: if the binary is missing for this platform, crashes, or exceeds a timeout, report plainly and **fall back to `parent_set(type='ARMATURE_AUTO')`** (Automatic Weights) with a warning that multi-piece characters may need the voxel path. The student always walks away with a rigged character.
- A `Skinning: [Voxel | Automatic]` toggle in the panel (default Voxel) makes the fallback student-selectable too.

### Day-1 gate (before any glue code)

Compile the solver on the M4, run it on a real multi-piece test mesh, and eyeball the weights against Automatic Weights in Blender. If the free solver's quality is visibly at paid-version level on a multi-piece character, the voxel path is GO. If not, David decides: fallback-only ship or debug time.

> **AMENDMENT 2026-07-01 #2 — REVERTED same day.** A skull-spanning `face` bone
> (David's hand-tuned layout, shipped as 1.4.6) was reverted at David's call: it
> required overriding ajc27's `face: DAMPED_TRACK nose` constraint at bind time,
> and he doesn't want to touch the binding recipe before BASEMENT. Auto-Rig uses
> the 1.4.5 head layout (pinch-based skull base + short forward face bone), which
> the stock constraint table drives verbatim — no bind override needed. The
> spanning-bone layout + its bind override design stay recorded here and in the
> dev log as a post-July-7 candidate.

## Feature 4 — Load Take (Choose Take, real)

- Operator `hiho_mocap.load_take`: **folder picker** to any FreeMoCap-processed take folder (validates the body npy exists; clear error if the folder isn't a processed take).
- Reuses the existing Spawn Rig path (`output_rig.py` empties spawner + slotted-actions recipe) pointed at the picked folder instead of `last_processed_path`.
- Multiple loaded takes coexist (each under its own `HIHO_MOCAP_Skelly_<takename>` root, matching existing behavior); Send to Character binds to the take picked in the panel.

## Send to Character (wiring, not new build)

The Studio panel's "Send to Character" button rebinds from the stub to the shipped `HIHO_MOCAP_OT_bind_to_rig`, with the target rig auto-filled from the Auto-Rig result **but still shown in a picker** (per [[operator-file-pickers]] — auto-populate dies on restart, picker survives).

---

## Panel changes (Studio section, revised)

```
Studio
├── 1. Choose Take
│   ├── Take folder: [folder picker]
│   └── [Load Take]
├── 2. Preview            (unchanged stub this release unless time remains —
│                          Load Take + Space already previews)
├── 3. Character
│   ├── [Import Character (.fbx/.obj)]
│   ├── [Add Markers]
│   ├── Skinning: [Voxel | Automatic]
│   ├── [Auto-Rig]
│   ├── Target rig: [armature picker]
│   └── [Send to Character]
├── 4. Polish              (stubs; real only if days remain)
└── 5. Export              (Save Out FBX — build if Days 6–7 free)
```

## File map

| File | Status | Purpose |
|---|---|---|
| `operators/import_character.py` | NEW | FBX/OBJ picker + import + collection sort |
| `operators/markers.py` | NEW | Add Markers operator |
| `operators/autorig.py` | NEW | Auto-Rig operator (fit + skin + fallback) |
| `operators/load_take.py` | NEW | Load Take folder picker |
| `core/marker_fit.py` | NEW | marker → metarig bone derivation table |
| `core/voxel_skinning.py` | NEW | exchange-format export, subprocess run, weight import, fallback |
| `external/voxel_skinning/` | NEW (vendored) | MIT source + LICENSE + compiled universal binary |
| `panel/studio_panel.py` | EDIT | rebind stubs → real operators, new Character sub-layout |
| `properties.py` | EDIT | take_folder, skinning_mode, autorig_target props |
| `operators/__init__.py` | EDIT | register new operators |
| `__init__.py` + `blender_manifest.toml` | EDIT | version bumps 1.4.0 → 1.4.x per step |

No changes to record/process/camera code. Pure additive. Zips built **from `SOFTWARE/`** (per [[zip-build-from-software-dir]]), one per step.

## Build schedule (one change at a time, test after each)

| Day | Ship |
|---|---|
| **Tue Jul 1** | This design + signoff. Compile voxel solver on M4; file-level license check; quality smoke test vs Automatic Weights (the Day-1 gate). |
| **Wed Jul 2** | 1.4.0: Import Character + Add Markers. David tests with a real character file. |
| **Thu Jul 3** | 1.4.1: Auto-Rig fit half (armature from markers, no skinning yet). Verify against a real metarig side by side. |
| **Fri Jul 4** | 1.4.2: skinning (voxel + fallback + toggle). Full Character section works. |
| **Sat Jul 5** | 1.4.3: Load Take + Send to Character wiring. **Full pipeline end-to-end on the laptop.** |
| **Sun Jul 6** | BASEMENT: install build, walk the 2026-06-09 verify list (capture window item #1), end-to-end on the rig, fix what breaks. |
| **Mon Jul 7** | Buffer + student testing. Save Out / Polish only if Days 2–5 ran ahead. |

## Out of scope (unchanged from prior backlogs)

Foreign BVH/FBX mocap retargeting; take library browser (v2.0); finger articulation from mocap; Rigify face sub-rig; Bake-to-keyframes; parametric/chibi retarget (v2.0); Preview section beyond Load-Take-and-press-Space.

## Risks and the honest read

1. **Voxel solver compile/exchange-format unknowns** — biggest risk; that's why it's Day 1 and gated, with the Automatic Weights fallback always shipping alongside.
2. **Bone rolls on the fitted armature** — wrong rolls make Damped Track results look twisted. Mitigation: copy roll conventions from a real generated metarig, and test Send to Character on Day 5 against the same take used in the v1.1 bind tests.
3. **BASEMENT machines vs universal binary** — confirm arch day 6; fallback covers a miss.
4. **Scale mismatches** (giant/tiny student characters) — constraint stack is direction-based so proportions hold; foot/ground contact quality on extreme proportions is a known v2.0 (parametric retarget) problem, not a July 7 problem.

## Ready-to-code checklist

- [ ] David signs off on this design
- [ ] Day-1 gate: solver compiled, licensed-checked, quality-tested
- [ ] Then the schedule above, one zip per step, dev log updated every step
