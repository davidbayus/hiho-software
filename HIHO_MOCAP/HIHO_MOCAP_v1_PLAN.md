# HIHO MOCAP — v1 Plan & Anchor

**Updated:** 2026-05-28 (wrapper architecture pivot locked, v1.2 code gate open)
**Status:** Anchor doc for Claude Code sessions. Read first, then [HIHO_MOCAP_WRAPPER_ARCHITECTURE.md](HIHO_MOCAP_WRAPPER_ARCHITECTURE.md) for architecture details.

> **2026-06-01 UPDATE, READ THIS FIRST:** The headless build shipped, so much of the version map below is superseded. The full **record → process → skelly** loop now runs on **Blender 5.2** as a **wheel-less, clickable 49 KB addon** (`SOFTWARE/hiho_mocap-1.3.0.zip`); FreeMoCap runs in an external env, never inside Blender. For the real current state read [SESSION_HANDOFF_2026-06-01.md](../../SESSION_HANDOFF_2026-06-01.md) and memory `project_hiho_mocap_wrapper_architecture.md` (its top STATUS line).

---

## 2026-05-27 pivot in one paragraph

After an audit confirmed every parity check between our v1.1 port and ajc27's official `freemocap_blender_addon` passes (constraint stacks, bone rolls, `fix_hand_data`, `enforce_rigid_bodies`, butterworth filter), HIHO MOCAP shifted from "parallel port of ajc27" to "thin opinionated wrapper that bundles ajc27 inside its distribution." The architecture doc holds the layer stack, the migration plan, and the locked section 8 decisions. This plan doc records ship status, scope per version, and the operating rules. The wrapper doc is the architecture; this is the schedule.

## Name & folder

**Name:** HIHO MOCAP. Full rename complete (user-facing, code, folder, mental model). PPParty is retired.
**Folder:** `SOFTWARE/HIHO_MOCAP/`. Renamed from `PPPARTY/` 2026-05-17.

## Purpose (one sentence)

HIHO MOCAP is a free, open-source, AGPL-3.0 Blender addon that bundles ajc27's `freemocap_blender_addon` and wraps it in an artist-facing Studio Panel, in-scene baking, sensible wrist-rotation defaults, and HIHO-program curriculum hooks. Maintained by the HIHO 4D ART CLUB at SJSU.

## First non-me user

**Who:** Members of the HIHO 4D ART CLUB at SJSU (was "experimental animation club"; renamed and scope-broadened 2026-05-24).
**When:** Club launches late June 2026. First mocap session has no fixed date.
**Pace:** Design-based research (DBR), not startup. Ships when the club is ready.

## Dogfooding decision

**REVERSED 2026-06-01. Yes, as user #1.** David now uses the addon for his own FRIENDS / open-movie capture, but deliberately as a student would: his experience must mirror the student's, with no privileged "Prof. David" build. His friction is the primary signal for hardening the student experience before the club launches. The Terminal FreeMoCap path stays a fallback, not his designated path. (The original 2026-05-17 "No" is preserved in memory.) (Memory: `project_hiho_mocap_dogfooding_decision`.)

## Version map

| Version | Status | Headline |
|---|---|---|
| v1.0 | SHIPPED 2026-05-26 | First end-to-end capture flow. Cameras, record, process, 33 empties. |
| v1.1 | SHIPPED 2026-05-27 AM | 63-bone holistic rig, finger bones, `enforce_rigid_bodies` wired in. |
| v1.2 | DESIGN LOCKED 2026-05-28, CODE STARTING | The wrapper pivot. Studio Panel, Bake Take, LIMIT_ROTATION defaults, bundled ajc27. |
| v2.0 | ARCHITECTED, CODE FALL 2026+ | Take library, stylized retarget, confidence heatmap, curriculum metadata. |
| v3.0+ | RESEARCH, 2027+ | Home-rolled HTTP/websocket server. Formerly labeled "v2.0" in this doc and in `project_hiho_mocap_v2_homerolled_ideal` memory. The wrapper pivot took the v2 slot. |

## v1.2 scope (this is the current ship)

Per the architecture doc sections 4 through 7, the must-haves:

1. **Bundle ajc27.** Vendored copy at `vendor/ajc27_freemocap_blender_addon/`. Register both addons from `__init__.py`. Compatibility patches under `vendor_patches/`, dated and explained.
2. **Studio Panel.** Five sections: Choose Take, Preview, Character, Polish, Export. Plain-language only (glossary in arch doc section 9).
3. **Science Mode toggle.** Hidden by default. When on, re-exposes ajc27's biomechanics panels (ROM, BOS, COM, joint angles, time-series).
4. **Bake Take operator.** `bpy.ops.nla.bake(bake_types={'POSE'}, visual_keying=True, clear_constraints=True)`. Empties move into a `HIHO_MOCAP_Raw` collection, hidden, never deleted.
5. **LIMIT_ROTATION defaults during bake.** Applied to `hand.R / hand.L`. Stand-in angles: +/- 70 pitch, +/- 30 roll, +/- 90 yaw (constants in `operators/bake_take.py`, tuned after first artist test).
6. **Polish operators.** Smooth Hands (One Euro on finger empties), Fix Wrist Flips (re-apply LIMIT_ROTATION), Trim Frames (set scene frame range).
7. **Save Out.** FBX, GLB, or `.blend` export. FBX path uses `bake_anim=True`.
8. **Migration.** v1.1 ported files (`core/loader.py`, `core/enforce_rigid_bodies.py`, `core/topology.py`, `core/build_rig.py`, `core/bind_to_rig.py`, `core/output_rig.py`, `core/virtual_landmarks.py`) move into `_LEGACY_v1.1_port/`. Per never-delete rule, David archives manually.
9. **Test.** Fresh install on a clean Blender 5.0 user account, end to end.

Out of v1.2 (deferred to v2.0): take library, stylized retarget, parametric rig, confidence heatmap.

## v2.0 scope (Fall 2026 / Spring 2027)

Lock the v1.2 surface for the summer test class, then build v2.0 against feedback from that class.

- Take library: `library.json` schema, thumbnails (first frame of `annotated_videos/Camera_0_mediapipe.mp4`), grid browser panel, side-by-side load.
- Curriculum metadata: per-take `hiho_metadata.json` with class section, semester, assignment, consent, license. Consent doubles as the training-data-policy opt-in record.
- Stylized retarget + parametric rig: source baked rig, target chibi / grown-chibi / normal / stylized. Math accounts for limb-length and pivot-offset differences. Probably consumes a parametric rig owned by Green Room (resolve during v2.0 design pass).
- Confidence heatmap overlay: viewport overlay coloring empties by reprojection error from `mediapipe_3dData_numFrames_numTrackedPoints_reprojectionError.npy`.

## v3.0+ (research, formerly labeled v2.0)

Home-rolled HTTP/websocket server. Decouples Blender's Python version from FreeMoCap's permanently. Research doc: [V2_HOMEROLLED_RESEARCH.md](V2_HOMEROLLED_RESEARCH.md) (filename keeps the old label, content stays relevant). Memory: `project_hiho_mocap_v2_homerolled_ideal` (same caveat).

Scope options (Mathis's vibe-coded MediaPipe Holistic replacement is the scope reference, NOT "rewrite all of FreeMoCap"):

- **A.** Full clean-room reimplementation of FreeMoCap. Years of work. **Skip.**
- **B.** Replace specific bottlenecks (cameras, tracker stitching, HTTP server, Blender adapter). Keep FreeMoCap for hard math (calibration, triangulation). Already partially in motion via BASEMENT custom recorder + Anipose patch.
- **C.** Thin HTTP wrapper around FreeMoCap. Smallest commitment.

Ideal: Option B with SJSU CS-student labor (matches refuse pedagogy). Pragmatic fallback: whichever of B or C gets students to art-making fastest. Never let the ideal block art-making.

---

## Ship history (v1.0 / v1.1)

### v1.0 feature checklist (shipped 2026-05-26)

All in Blender's N-panel under "HIHO MOCAP":

- [x] **Cameras up button.** Bundled SkellyCam. Shipped 2026-05-23.
- [x] **Record button.** Default 15s countdown, 60s record, both adjustable. Shipped 2026-05-23.
- [x] **Process mocap button.** Wrapper around FreeMoCap pipeline with native Blender progress bar. Shipped 2026-05-26.
- [x] **Output rig.** 33 keyframed empties parented to `HIHO_MOCAP_Skelly_<takename>`. Shipped 2026-05-26. (Armature-with-bones deferred to v1.1; see deviations below.)
- [x] **4-camera live grid.** "Open Camera Views" button spawns a new top-level window with a 2x2 Image Editor grid. Pivoted from inline-N-panel video on 2026-05-23.

Stretch (not shipped): 3D skeleton viewer. Empties output effectively delivered the same visualization (33 dots playing back in viewport).

### v1.0 deviations from original plan

- **33 empties, not an armature.** ajc27's armature builder uses `action.fcurves`, removed in Blender 5.0 slotted actions. Patching is ~200 lines; clean-room armature is similar effort; 50-line empties path ships in one session. The empties drive any armature via Copy Location constraints, which became v1.1's bind step.
- **Calibration TOML must be present.** v1.0 requires `~/freemocap_data/logs_info_and_settings/last_successful_calibration.toml` or a manually picked path. v1.1 candidate (not shipped): "Record Calibration" button.
- **Progress bar advances by stage, not sub-stage.** v1.1 candidate.

### v1.1 (shipped 2026-05-27 AM)

63-bone holistic rig with finger bones. `enforce_rigid_bodies` wired in (3x per Spawn Rig click). Wrist-flipping noted as open issue. Post-2026-05-27 PM audit confirmed the v1.1 port is 1:1 with ajc27, which triggered the wrapper pivot. **v1.1 code is now legacy in light of v1.2.** Per never-delete, the files stay in `core/` until David archives them to `_LEGACY_v1.1_port/`.

---

## Blender version pin

**5.0** (Python 3.11.13). Durable until FreeMoCap supports Python 3.13. (Memory: `project_hiho_mocap_blender_50_pin`.) ajc27's addon runs on 5.2's 3.13 with a harmless syntax warning, but FreeMoCap proper (layer 1) holds us on 5.0.

cv2 install path on 5.0: `--target ~/Library/Application Support/Blender/5.0/scripts/modules --no-deps`. The `--no-deps` keeps Blender's bundled numpy 1.26.4, which opencv 4.8 needs.

## Operating rules (preserved)

- **HIHO = "Human In, Human Out."** Pedagogical principle: human ideas in, full toolset doing executional middle work, human curation and meaning out. Tech-agnostic. Origin: David's Spring 2026 ART 105 AI policy. Now program-wide.
- **HIHO 4D ART CLUB** at SJSU is the maintainer body. Distinct from the SCRAP program in San Francisco. Do not conflate.
- **N-panel label "HIHO MOCAP"** carries dual meaning for the student: (1) family flag (this tool belongs to HIHO); (2) posture reminder (the human is the source, the rig is listening). Both intended.
- **FreeMoCap relationship:** bundled-vendored at layer 1, never "fork." (Memory: `project_hiho_mocap_freemocap_relationship`.)
- **ajc27 relationship:** bundled at layer 2 as of v1.2. Same discipline. Patches under `vendor_patches/`.

## Still open

- **Suite question.** Are Green Room (procedural character design) and Quadre (quad remesher) standalone HIHO tools, or one shared HIHO suite with HIHO MOCAP? Affects branding and shared infrastructure. Not resolved.
- **Course connection.** Whether any v1.x addon work ties to an ART 102 / 105 / 180 / 195 deliverable. Not resolved.
- **Parametric rig home.** Green Room or HIHO MOCAP? v2.0 design question. See architecture doc section 8, decision 4.
