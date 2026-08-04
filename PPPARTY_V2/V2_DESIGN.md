# PPPARTY V2 — Design Document

**Status:** Draft, 2026-04-26 (revised post-Phase-0 spike, same day; revised 2026-04-28 — Phase 1 measurements dropped, Phase 2 bones-only build kicked off; revised 2026-04-29 — TWO-PASS architecture committed after Day 5 testing validated Pose+Hand running together at 30 FPS on M3 in async LIVE_STREAM mode. Pass 1 = full body including arms + hands; Pass 2 = face. The original three-pass split was based on a "single landmarker per pass" FPS argument that Phase 0 already disproved; layering the captures didn't add enough pedagogical value to justify the wrist-coherence pain it caused at the body/hands boundary).
**Provenance:** Synthesized from the Apr 2026 critique series (David Bayus + Claude Opus 4.7, with Gemini Pro 2.5 as referee for early rounds). Phase 0 spike findings folded in 2026-04-26.
**Supersedes:** PPPARTY V1 (frozen at alpha.6, lives at `SOFTWARE/PPPARTY/` as read-only knowledge archive).

---

## 1. Goal

**Kid moves → puppet mirrors → kid refines → kid exports a short film.**

V2 is a Blender addon for **capture-and-bake puppeteering**. Live performance is captured as keyframes, layered into NLA strips, polished into short student animations. The pedagogical product is the animation, not the live mirror.

## 2. Non-Goals

- Real-time unified holistic performance ("live VJing with extra steps").
- Replicating traditional marionette dynamics on the tracked main armature during capture.
- Running body, hand, and face landmarkers simultaneously every frame.
- Solving every animation problem in one addon — Green Room (puppet builder) and a future native binder remain *separate* utilities.

## 3. Why V2 — what V1 taught us

1. **Hand-on-face FPS cliff (~15 FPS) — observed on the deployment spec floor.** V1 hits ~15 FPS on David's 2023 iMac when hands cross face; the iMac IS the spec floor (representative of ART 102 student hardware; mobile lab will be specced to match). Phase 0's sender spike (`spike/SPIKE_PLAN.md`) confirmed the cliff is NOT sender-side — three landmarkers fit comfortably in the 33ms frame budget on M3-class hardware. The cliff lives Blender-side: 217-GN-node re-evaluation + Verlet sim on the tracked armature + modifier dirty propagation (see #5). V2's primary FPS lever is dropping Verlet on the tracked rig and gating GN-tree work per pass; the bones-only Day 1 posture sidesteps the GN-tree contribution entirely during capture, with mesh re-entering post-bake.
2. **MediaPipe Holistic API gap.** HolisticLandmarker still doesn't expose `facial_transformation_matrixes` (verified live Apr 26, 2026 against `github.com/google-ai-edge/mediapipe`). Google itself migrated to **task-specific landmarkers** — exactly what V1's Path B already uses.
3. **Industry SOTA validates pass-based capture.** MetaHuman Animator runs separate body and face captures composed in a Level Sequence; face capture is *offline*. V2's three-pass NLA composition is the same pattern in Blender form.
4. **Rose marionette dynamics fight mocap fidelity on the tracked rig.** Verlet dangle adds lag, double-stacks gravity, and imposes a string-fall pattern that doesn't match the kid's actual motion. The Rose framework's *anatomy* is universally useful; its *dynamics* solve a hardware constraint (puppeteer has 10 fingers) that mocap doesn't share.
5. **217 GN nodes re-evaluate per slider change** in V1. Sim-zone Verlet on the main armature is part of the cost. Dropping it on the tracked rig is a meaningful FPS unlock.

## 4. Architectural Pillars

1. **Two sequential passes, one addon.** Body → Face. Pass 1 runs PoseLandmarker + HandLandmarker together (single sender process, both in MP `LIVE_STREAM` async mode) — captures full body, arms, and hand articulation in one take. Pass 2 runs FaceLandmarker. Single-landmarker-per-pass was the original constraint per V1's FPS cliff thesis, but Phase 0 + Day 5 testing showed the cliff lived Blender-side (GN tree + Verlet on the tracked rig); on the sender side, M3-class hardware comfortably fits multi-landmarker async dispatch in the 33ms frame budget.
2. **Direct mocap drive on the tracked main armature.** Rose anatomy stays as joint-stop / ROM-limit constraints. No Verlet dangle on tracked bones.
3. **Disjoint pass ownership.** Pass 1 keyframes everything except the head bone; Pass 2 keyframes the head. NLA strips from each pass touch non-overlapping fcurves and stack cleanly without fighting. Cross-pass attachment is via Blender parenting (head bone is a child of neck), not constraints.
4. **Standard Blender data crosses pass boundaries.** Each pass writes an Action; NLA composes. Passes never share live Python state.
5. **Playback-while-recording.** Pass 2 capture is timestamped to *viewport playback frame*, not wallclock. (This is the Live Link Face / ADR pattern.)
6. **Three smoothing/physics surfaces, three tools.** One Euro on tracker inputs. In-house Goo-style spring chains on non-tracked bones (hair, ears, accessories). Verlet/cloth-sim isolated to garment layer (future, optional). See `feedback_three_smoothing_physics_surfaces` memory.

## 5. Pass Specifications

### Pass 1 — Body (full body + arms + hands)
- **Landmarkers:** MediaPipe PoseLandmarker (33 body landmarks) AND HandLandmarker (21 per hand × 2). Both run in the same sender process in MP `LIVE_STREAM` (async dispatch + result callback) mode. Frame loop runs at camera rate; inference overlaps capture. Day 5 testing on M3 confirmed steady 30 FPS with both landmarkers active.
- **Why both in one pass:** the wrist is one of the most flexible joints in the body. Splitting body and hands into separate passes meant the kid's wrist at hand-recording time had no relation to whatever the body NLA was replaying — fingers projected through a STALE wrist. Capturing pose + hands together eliminates the temporal mismatch by construction.
- **Drives + keyframes:** full body except head — pelvis, chest, neck, upper_leg.L/R, lower_leg.L/R, upper_arm.L/R, lower_arm.L/R, all 30 finger bones. The body sender lives-drives the head bone too (from pose landmark 0 / nose) so the kid sees their whole body in the mirror, but the head is NOT keyframed in Pass 1 — Pass 2 owns it.
- **Joint constraints (Rose anatomy):** compound neck (two pivots), floating shoulder slack, twist-limited waist between chest and pelvis, anatomical ROM stops at every hinge, toe splay (~15°/foot).
- **Smoothing:** One Euro on all 33 pose landmarks + all 21×2 hand landmarks. Lighter (`min_cutoff=1.0, beta=0.02`) on the 6 pose-arm landmarks (11–16) — calmer arms keep the wrist stable, which keeps the finger projection stable.
- **Receiver order:** arm chain first (`upper_arm` then `lower_arm`, both sides, from Pose 11–16), THEN finger projection through the JUST-WRITTEN `lower_arm.L/R` matrix. Same-frame coherence by construction. The rest of the body (spine + legs) drives independently from pose landmarks 11/12/23/24/25/26/27/28.
- **Output:** `PP_V2_BodyPass` action.
- **Duration:** kid-determined, capped at scene `frame_end`.

### Pass 2 — Face
- **Landmarker:** MediaPipe FaceLandmarker (the *standalone* — exposes the 4×4 facial transformation matrix HolisticLandmarker lacks).
- **Drives + keyframes:** head bone rotation (matrix → quaternion via basis-write in head bone's rest-local frame: `basis = M_rest⁻¹ · R_world · M_rest`). The basis-write makes face rotation parent-pose-independent, so when Pass 1's NLA moves the spine/neck the head composes naturally instead of fighting the parent every frame. Future: shape keys / blend shapes (52 ARKit-compatible) for facial expression — deferred from V2.0.
- **Setup on entry:** Pass 1's body NLA strip plays back so the kid sees their full prior performance while adding head detail. Head bone is parented to `neck` in the rig — no Copy Loc/Copy Rot constraints needed; parent chain handles position, basis-write handles rotation.
- **Recording:** viewport plays the Pass 1 body strip; capture timestamp = current viewport frame.
- **Output:** `PP_V2_FacePass` action.
- **Optional offline mode:** per the MetaHuman precedent, Pass 2 can record video first and solve face afterward at higher fidelity. Defer to a later iteration; live capture is the V2 default.

### Composition
- Both actions pushed to NLA as separate strips on `PP_V2_Rig`.
- Standard Blender NLA editing: speed, blend, replace, additive.
- Studio Track students get full NLA editor access for cleanup/stylization.
- Stage Track kids get a simplified "polish my show" UI on top of NLA.

### NLA mute orchestration during live capture
Each pass's existing NLA strips are auto-muted when that pass enters live mode (mirror or recording) and restored on Stop Mirror (no recording) — same recording-studio pattern where arming a track silences its previous take. On Stop Recording, the camera auto-closes and the new strip becomes canonical; previously-muted drafts stay muted. Implemented as `mute_pass_strips` / `restore_pass_strips` / `discard_pass_mutes` in `operators/_nla.py` (added Day 5b, 2026-04-29).

## 6. Mirror Mode (the K-12 hook)

- Live preview, no recording. User picks: Body Mirror or Face Mirror.
- Body Mirror runs the Pass 1 sender (Pose + Hand together) — kid sees full body, arms, and fingers move with them. The "wave at the screen, puppet waves back" demo. Pedagogical lesson 1.
- Face Mirror runs the Pass 2 sender — kid sees their head rotation drive the puppet's head.
- Mirror mode shares all infrastructure with capture passes — same gating, same drive code paths. The only difference is "no Action recording."

## 7. Anatomy Layer (kept from Jim Rose)

| Joint | Rose principle | V2 implementation |
|---|---|---|
| Neck | Compound: top of skull + base of neck | Two-bone head chain in armature |
| Shoulder | Floating socket with ~5/8" slack | Soft attachment + drift constraint within tracked range |
| Waist | Twist-limited cord | Chest + pelvis as separate driven masses, twist limit constraint |
| Elbow / Knee | Hinge with ROM stops | Limit Rotation constraint per axis |
| Wrist | Cone-cap with stops | Limit Rotation per axis |
| Ankle | ~60° latitude, 15°/foot splay | Limit Rotation + base splay rotation |
| Hand rest | "Never dead at sides" | Default rest pose + subtle pendulum follow-through (post-bake stylization) |

**Carried forward:** Rose's "movement is the chief architect of character" pedagogy. Used in UI copy and curriculum framing.

## 8. Dynamics Layer (deferred to optional stylization)

- **Verlet / spring-damper** physics: applied **only** to non-tracked bones (hair, ears, accessories, chest jiggle, etc.) via in-house Goo-style engine. Per `project_goo_unified_secondary_motion` memory.
- **Marionette feel** as a post-bake stylization pass: optional NLA additive layer that adds string-physics follow-through to baked clips. Animation aesthetic, not capture pipeline.
- **Specials** (threshold-triggered gestures à la Rose's hand-to-mouth pluck): optional stylization, layered after capture. E.g., `smile > 0.7` → puppet's hand pops to mouth. Implemented as NLA pose-library triggers, not part of mocap drive.

## 9. What V2 Reuses From V1 (no rebuild)

- `mediapipe_sender.py` — webcam → 52 blend shapes + 33 body landmarks + 21×2 hand landmarks. May need a small refactor to support per-pass sender modes (body-only, hands-only, face-only).
- One Euro filter implementation (V1 alpha.3).
- `TrackingReceiver` UDP pipeline + auto-detection.
- Bone driver mapping logic (Pose / Hand / Face → bones).
- Bake operators.
- Object Info node Studio Track inputs (custom geometry).
- Material slot system (15 materials + Cheek Material).
- N-panel UI patterns + workspace setup.
- Joint topology (chest+pelvis split, compound neck, floating shoulder).
- Blob head template (`assets/blob_puppet.blend`) — passes through unchanged.
- Calibration tools, debug operators.

## 10. What V2 Changes

- **Two-pass state machine** (UI: Body Mirror / Body Recording / Face Mirror / Face Recording / NLA-edit). Three-pass split was eliminated 2026-04-29 in favor of capturing pose + hands together.
- **Pass 1 sender runs two landmarkers** — PoseLandmarker + HandLandmarker, both in MP `LIVE_STREAM` async mode in one Python process. Sequential synchronous (`VIDEO` mode) was attempted in day5d and halved FPS to 15; async dispatch fixed it.
- **Disjoint pass bone ownership** — Pass 1 keyframes everything except the head; Pass 2 keyframes the head. NLA strips don't share fcurves so they can't fight.
- **NLA mute orchestration** — entering live mode for a pass auto-mutes that pass's existing strips (so live receiver wins); Stop Mirror restores them; Stop Recording leaves the new strip canonical and prior takes muted as drafts.
- **Stop Recording auto-closes the camera** — sender process and UDP receiver shut down on Stop. UX collapses "stop recording + stop mirror" into one button.
- **Cross-pass attachment via parenting** — head bone is a child of `neck` in the rig; no Copy Loc/Copy Rot constraints needed. Same for finger bones (children of `lower_arm.L/R`).
- **Hand projection through wrist frame** — MP's `hand_world_landmarks` are hand-local (wrist near origin); we project them through the puppet's CURRENT wrist orientation (just-written this same tick) so finger directions are coherent with the wrist that captured them.
- **Basis-write face rotation** — face matrix is expressed in the head bone's rest-local frame and written to `rotation_quaternion` directly, not via `pose_bone.matrix =`. Parent-pose-independent, so the body NLA driving the spine doesn't fight the live face receiver.
- **Playback-bound capture** — Pass 2 capture frame = viewport frame, not wallclock. Required for ADR-style sync.
- **Drop Verlet sim zone on the tracked main armature.** Verlet stays only on non-tracked secondary-motion bones.
- **Drop face→body heuristic channels in capture path.** V1 alpha.5b already mutes them during BT — V2 removes the code path entirely from capture mode.
- **NLA composition for pass actions** — explicit strip-stacking on the armature.

## 11. Phased Build Plan

**Phase 0 — Afternoon spike (1–3 hours, V2 sandbox-isolated)** ✅ ran 2026-04-26
- Validate the FPS thesis: gate landmarkers in a V1-derived spike, run body-only, measure FPS in scenarios that previously dropped to 12–15 FPS.
- Deliverable: FPS log + go/no-go decision.
- **Outcome on M3:** *inconclusive.* Sender is camera-locked at ~30 FPS regardless of mode/scenario; no cliff to clear and no body-vs-all gain. See `spike/SPIKE_PLAN.md` for the full table. Phase 1 scope expanded to cover what the M3 spike couldn't measure.

**Phase 1 — Lock cross-pass constraint defaults (~half day)** — revised 2026-04-28
- ~~P1.a (e-waste sender repeat)~~ and ~~P1.b (Blender-side viewport FPS measure)~~ **dropped 2026-04-28.** P1.a is moot — deployment spec floor = David's iMac, mobile lab will be specced to match, cliff already observed there. P1.b is moot — David has confirmed V1 hits ~15 FPS on his iMac when hands cross face; Phase 2's Verlet-drop on a bones-only armature will validate the lever by building it.
- **Surviving Phase 1 work:** lock cross-pass constraint setup details before Phase 2 wiring lands. Axis order, copy-influence default (1.0 pure copy or 0.8 with stylization room?), edge cases for dropout/reacquire on the constrained side.
- Phase 2–5 estimates below remain unchanged. V2 is justified on architecture grounds (#3.2–3.4) + the observed cliff (#3.1).

**Phase 2 — Pass 1 (Body) — three-pass version implemented 2026-04-28** ✅
- Pass state machine UI scaffold.
- Direct mocap drive on the main armature (no Verlet, no GN tree).
- Body pass action recording, push-down to NLA.
- Mirror mode for body-only.

**Phase 3 — Pass 2 (Hands) — three-pass version implemented 2026-04-28** ✅
- Hand landmarker single-stream mode.
- Hand recording + NLA push-down.

**Phase 4 — Pass 3 (Face) — three-pass version implemented 2026-04-28** ✅
- Face landmarker.
- Head bone basis-write driver.
- NLA composition: three strips stacked.

**Phase 5 — Day 5 calibration + architectural pivot (2026-04-29)** ✅
- Mirror-mode parity across senders (cv2.flip on all three).
- Basis-write face rotation (parent-pose-independent).
- Disjoint pass ownership (head removed from body keyframing).
- NLA mute orchestration (per-pass auto-mute on Mirror enter, restore on Stop).
- Stop Recording auto-closes camera.
- Hand landmark projection through wrist frame (day5c).
- Pass 2 absorbs arms (day5d) — wrist coherence by same-frame capture.
- LIVE_STREAM async dispatch for Pose+Hand simultaneously (day5e) — confirmed 30 FPS on M3.
- **Architectural decision: collapse to two-pass.** Three-pass split lacked pedagogical value commensurate with its complexity once wrist coherence forced arms into Pass 2 anyway.

**Phase 6 — Two-pass refactor (NEXT, ~1 day)**
- Extend `mediapipe_sender.py` (Pass 1) with HandLandmarker + unified packet (port day5e from `hand_sender.py`).
- Retire `hand_sender.py`, `operators/hand_ops.py`, `HandReceiver`, `HandRecorder`.
- Merge `_HAND_DRIVEN_BONES` into `_BODY_DRIVEN_BONES` (12 body + 30 finger = 42 bones owned by Pass 1).
- Update Face Mirror/Recording gate: requires Body NLA only.
- Strip "Hand Mirror / Hand Recording" sections from N-panel.
- Rename Face Mirror panel from "(Pass 3)" to "(Pass 2)".

**Phase 7 — Calibration + polish (after refactor)**
- Hand axis remap calibration (MP hand_world_landmarks frame ↔ puppet wrist frame). Deferred from Day 5.
- Body lean tuning (forward chest lean observed at desk).
- Bake `fps=30` + longer `frame_end` into V2 rig builder (current scene defaults to 24fps + frame_end=250).
- Failure-mode handling (mocap dropout, fast motion, occlusion). Per `feedback_three_mode_tracked_physics` memory.
- Per `feedback_liveness_signals` memory: explicit liveness float from sender side.
- E-waste hardware test (Chromebook with Linux, or oldest available laptop).
- iMac FPS test (deployment spec floor).
- Save UI states, session recovery.

**Ship gate:** kid in classroom can do both passes and export a short clip.

## 12. Open Questions

- ~~Does single-stream body landmarker hold 30 FPS in the hand-near-face scenarios that broke V1?~~ → **Closed 2026-04-28.** Sender-side is fine on M3. Cliff lives Blender-side.
- ~~Does dropping Verlet on the tracked armature give measurable FPS gain?~~ → **Closed 2026-04-28.** Confirmed primary lever; bones-only capture holds 30 FPS comfortably.
- ~~Can Pose + Hand landmarkers run simultaneously in one sender at 30 FPS on M3?~~ → **Closed 2026-04-29 (day5e).** Yes, in MP `LIVE_STREAM` async mode. `VIDEO` sync mode halves FPS (sequential blocking inference); never use it for multi-landmarker.
- ~~Should body and hands be separate passes?~~ → **Closed 2026-04-29.** No. Wrist coherence requires same-frame capture; pedagogical layering didn't justify the complexity. Two-pass committed.
- **Open:** Will the iMac (deployment spec floor) hold 30 FPS on Pass 1 with Pose + Hand together? Untested; Phase 7 task.
- **Open:** Hand axis remap calibration — MP `hand_world_landmarks` frame convention vs puppet wrist-local frame. Day 5 testing showed projection produces coherent hand SHAPES but with rotational offsets. Specific axes need empirical sign/swap correction.
- **Open:** Pass 2 offline-solve mode: in V2.0 or defer to V2.1?
- **Open:** Goo-style secondary motion: applied per-pass or only at NLA-edit time? (Probably NLA-edit, but worth verifying.)
- **Open:** Failure-mode handling for tracked physics — TRACKED / RELEASED / REACQUIRING per `feedback_three_mode_tracked_physics` memory. Not yet implemented.

## 13. Out of Scope for V2.0

- Templates / template browser (per V1 build order: "one great puppet before templates"; carry forward).
- Native shape-key binder (replaces Face-It; still pre-templates per V1 plan, but not load-bearing for V2.0 capture pipeline).
- FBX / Unreal export (V2.1).
- Marionette-feel post-bake stylization layer (V2.1).
- Specials / trigger gestures (V2.1+).
- Memory palace AI integration (V3+, per `project_memory_palace_research`).

## 14. Pedagogical Mapping

The architecture *is* the syllabus:
- **Lesson 1 — Mirror mode.** Hook. Wow factor. K-12 first contact.
- **Lesson 2 — Pass 1: Capture body.** Full body + arms + hands in one take. Kid performs the whole body.
- **Lesson 3 — Pass 2: Capture face over baked body.** Layered animation literacy — performing facial expression in sync with the body that's already recorded. Same workflow as ADR / Live Link Face.
- **Lesson 4 — NLA cleanup.** Animation graph editor literacy.
- **Lesson 5 — Stylization.** Marionette-feel layer, exaggeration, holds, secondary-motion polish. The actual craft of animation.

## 15. References

- **Memory:** `project_mp_holistic_transform_matrix_gap` (verified Apr 26, 2026), `project_ppparty_deliverable_is_baked_animation`, `feedback_three_smoothing_physics_surfaces`, `project_goo_unified_secondary_motion`, `project_smoothing_research_outcome`, `feedback_liveness_signals`, `feedback_three_mode_tracked_physics`, `feedback_subgroup_defaults_safe`, `feedback_research_doc_first_pattern`.
- **Codebase reference:** `SOFTWARE/PPPARTY/` (V1 archive — patterns, MediaPipe sender, OSC receiver, joint constraints, blob template, Studio Track Object Info pattern).
- **Rose materials:** `SOFTWARE/PUPPET_RIG_R&D/JIM_ROSE_MARIONETTE_RESEARCH.md` and the two transcripts.
- **External validation:**
  - MediaPipe Holistic deprecation notice (github.com/google-ai-edge/mediapipe/blob/master/docs/solutions/holistic.md)
  - MetaHuman Animator pipeline (Epic, 2024–2025)
  - One Euro filter (Casiez, Roussel, Vogel 2012)
  - ACM Computing Surveys 2024 — Real-Time Multi-View Markerless Mocap
- **What we explicitly do *not* lean on:** the Grenze 2024 Barracuda VTO paper (cited loosely by Gemini in the early critique round; its Verlet equation is for cloth simulation on garments, not bones or tracker smoothing).

---

**Next action (start of next session):** Two-pass refactor (Phase 6 above). Extend `mediapipe_sender.py` with HandLandmarker (port the day5e logic), unified packet format, retire `hand_sender.py` + `hand_ops.py` + `HandReceiver` + `HandRecorder`, merge bone ownership in `_BODY_DRIVEN_BONES`, strip "Hand Mirror" panel sections, rename Face panels from "(Pass 3)" to "(Pass 2)". Then ship and test end-to-end. After refactor lands clean: hand axis calibration + body lean + fps=30 rig builder bake.
