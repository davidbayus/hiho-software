# PPParty V2 — Benchmarks Ledger

Append-only chronological record of "best stable build" milestones. Each entry captures: which build was the benchmark, why it earned that status, what properties it locks in (don't-regress), and what to-beat metrics defined the next horizon. New entries go at the TOP.

This file is a redundant marker — the `HANDOFF.md` top block also flags the current benchmark, and a git tag would too if V2 source were tracked. The redundancy is the feature: if any one place goes stale, the others catch it.

---

## 🎯 `PPPARTY_V2_v2.0.2.zip` — 2026-05-01 (CURRENT)

**Title:** Floor constraint on foot bones + constant-stance documented as explicit design choice.

**Verified by David:** 2026-05-01 afternoon. All three test cases passed:
- Constraint inspected in Pose mode → Bone Constraints panel shows "Floor (v2.0.2)" with Z=0.05m, Owner=World Space ✓
- Manual pose-mode test: rotating foot.L to push tail through floor → ankle (head) refused to dip below z=0.05 ✓ (screenshot captured the constraint actively clamping with foot tail visibly dipping below floor while ankle pinned at floor)
- No regression on body / arm / leg / hand / face behavior ✓

**What this build does correctly (don't regress, ADDS to the v2.0.1 carry-forward set):**
- **Floor constraint on feet (NEW):** `LimitLocation` constraint named "Floor (v2.0.2)" applied to `foot.L` and `foot.R` during `Create V2 Rig`. Clamps bone HEAD (ankle) world-space Z to ≥ rest-pose foot head Z (= 0.05m, self-calibrated from `bone.head_local.z`). Survives across live drive, NLA playback, timeline scrubbing, manual pose mode. Visible in Pose mode → Bone Constraints panel. Toe-tail can still dip slightly when toes-down (known v2.0.3 candidate — second constraint or driver targeting tail).
- **Constant-stance documented (NEW):** comment block at the parent-less pelvis branch in `_drive_bone_segment` explicitly states "puppet does NOT translate when the kid walks; intentional puppet-show pedagogy." Future readers don't try to "fix" the deliberate design.
- All v2.0.1 don't-regress properties (across-palm hand `side_ref` + everything from day8d), carried forward intact.

**To-beat metrics (next builds should improve):**
- Fingertip rotation noise — STILL pending numeric measurement on v2.0.1/v2.0.2. Pre-v2.0.1 baseline (day8d): 0.30-0.44 mean Δq on `f_*.03`. Measurement script ready at `spike/measure_hand_rotation_noise.py`; decision tree on Lever B in `HAND_SIDE_REF_DESIGN.md` Measurement Protocol section.
- Pelvis world position (intentionally NOT translating per v2.0.2 design choice — no longer "to-beat" unless classroom testing demands).
- Foot tail (toe) dipping below floor when toes-pointed-down (v2.0.3 candidate).
- Default scene fps/frame_end still 24/250.
- Laptop sender FPS investigation still open (~24-26 FPS observed; code-side cannot affect by design).

**Cross-references:**
- Source change: 9 lines in `core/rig.py` (constraint setup loop after Object mode set, before return rig_object); 10-line comment block in `core/receiver.py` (`_drive_bone_segment` parent-less branch); `__init__.py` bl_info (2,0,1)→(2,0,2).
- Research: [`WORLD_SPACE_ANCHORING_RESEARCH.md`](WORLD_SPACE_ANCHORING_RESEARCH.md) — covers both hip translation (chose constant-stance) and foot+floor (chose ground-plane clamp); 4 candidate solutions for hip, 3 for foot, picked simplest pair.
- Design: [`V2_0_2_DESIGN.md`](V2_0_2_DESIGN.md) — Option 2 (declarative constraint) chosen over Option 1 (imperative clamp) per David's design call. Constraint vs Verlet vs imperative comparison documented inline.
- Companion future-track: [`LOWER_BODY_PASS_RESEARCH.md`](LOWER_BODY_PASS_RESEARCH.md) — scoping note for the kid-at-desk-vs-kid-standing problem (V2.x territory, parked).
- Workflow lesson cumulative through this session: **two builds shipped same day with proper research → design → code arc.** v2.0.1 hit a duplicate-doc wall mid-implementation (caught and corrected); v2.0.2 ran clean. The benchmark-ledger pattern (this file) shipped between v2.0.1 and v2.0.2, makes future regressions easier to catch.

---

## `PPPARTY_V2_v2.0.1.zip` — 2026-05-01 (DETHRONED 2026-05-01 — same day)

**Title:** Lever A — across-palm `side_ref` for hand bones eliminates `to_track_quat('Y','Z')` roll flicker on near-vertical hand bones.

**Verified by David:** 2026-05-01 afternoon, "no visible regression, feels more tsbale [sic]" — visible thumb-base / finger-base flicker GONE. Numeric measurement pending; queued per `HAND_SIDE_REF_DESIGN.md` Measurement Protocol.

**Naming convention transition:** day-counter retired at day8d. v2.0.1 is the first release under semver-style `vX.Y.Z` versioning. Future ships: v2.0.2, v2.0.3, etc.

**What this build does correctly (don't regress, ADDS to the day8d carry-forward set):**
- **Hand bone rotation stability (NEW):** across-palm vector (`projected[17] - projected[5]`) passed as `side_ref` to all hand bone drives in `core/receiver.py`. Self-mirrors per hand — pinky/index swap sides between L and R so the same code produces the anatomically-correct bone-X direction for both hands, no L/R sign correction needed. Same natural-anatomy emergence pattern that body bones get from `(L_HIP - R_HIP)` for free.
- **Issue 1.c (thumb-joint orientation weirdness) — RESOLVED** as a side effect. Thumb-roll arbitrariness is the same root cause as finger-base flicker (degenerate `to_track_quat` fallback on near-vertical bones); the Lever A fix kills both.
- All day8d don't-regress properties, carried forward intact.

**To-beat metrics (next builds should improve):**
- **Fingertip rotation noise — measurement pending.** Pre-v2.0.1 (day8d): 0.30-0.44 mean Δq on `f_*.03` tips. Lever A predicted: substantial drop on palm/thumb-base bones (0.08-0.10 → 0.02-0.04); modest drop on tips (their noise is dominated by MP pixel-uncertainty, not roll choice). Post-v2.0.1 measurement decides Lever B.
- Pelvis world position (still anchored at origin).
- Foot+floor contact (still no IK).
- Default scene fps/frame_end still 24/250.
- **NEW open follow-up:** is laptop sender FPS (~24-26) a real regression vs. desktop, or just M3 laptop baseline? Code-side cannot affect sender FPS by design (different processes — `mediapipe_sender.py` is a separate subprocess from the Blender receiver), so this is a hardware/OS/thermal investigation, not a V2-source one. Apples-to-apples test (install day8d, measure; reinstall v2.0.1, measure) would settle it.

**Cross-references:**
- Source change: `core/receiver.py` lines ~644-667 (one new local + one new arg on existing `_drive_bone_segment` call). Plus `__init__.py` bl_info bump (2,0,0)→(2,0,1).
- Canonical math + sign analysis: [`HAND_SIDE_REF_RESEARCH.md`](HAND_SIDE_REF_RESEARCH.md) (2026-04-30, predates today's session — discovered mid-implementation, course-corrected the design before shipping)
- Today's design + measurement protocol: [`HAND_SIDE_REF_DESIGN.md`](HAND_SIDE_REF_DESIGN.md) (with errata block acknowledging the duplicate-doc workflow gap)
- Three-lever framing: [`HAND_ROTATION_NOISE_RESEARCH.md`](HAND_ROTATION_NOISE_RESEARCH.md)
- Workflow lesson: this build's research-pre-implementation phase nearly duplicated existing 2026-04-30 work because the earlier doc lived only on the desktop machine and wasn't surfaced in the laptop session's initial scan. **Worth designing a fix for the cross-machine sync gap as a workflow item.**

---

## `PPPARTY_V2_v2.0.0-day8d.zip` — 2026-04-30 (DETHRONED 2026-05-01)

**Title:** Per-class scale estimator split — fingers land at correct anatomical scale.

**Verified by David:** 2026-05-01 afternoon, "the most recent build, best and most stable it's been."

**What this build does correctly (don't regress these properties):**
- Median hand calibration: fingers don't pulse in size during NLA playback (day8b foundation; day8c+8d preserve)
- Per-class scale estimator: finger proximal + middle phalanges (`f_*.01`, `f_*.02`) at 90th percentile (correcting MP's foreshortening bias); palms, thumbs, fingertips (`.03`) at median (where the distribution is already noise-centered on truth)
- Slotted-Actions fcurve API correctly handled (Blender 5.2 alpha breaking change — `action.fcurves` is gone, use `action.layers[*].strips[*].channelbags[*].fcurves`)
- Pelvis stays vertical; chest captures all torso lean (no double-counted forward lean) — day7d
- `side_ref` pattern stabilizes near-vertical bones — spine + legs + arms pass `hip_lateral`, prevents `to_track_quat('Y','Z')` from picking arbitrary roll
- Foot triangle math: ankle/heel/foot_index → 3-axis basis. Per-side `side_sign` flip handles winding without breaking dorsal direction (day7c→day7d)
- Leg L/R mirror inversion fix: legs use direct mapping (MP-L → puppet-L) to undo MP's flip-induced inversion on lower-body landmarks. Arms still use mirror (day7f)
- Shoulder shrug uses running-min spine length as the rest baseline (anchor stays at rest height while actual shoulders rise → bone tilts up visibly) — day7b
- 56-bone armature: 12 body + 2 shoulders + 4 feet/toes + 38 hand
- Two-pass capture: Pass 1 = body + arms + hands; Pass 2 = face. Disjoint pass ownership; Pass 1 keyframes 55 (everything except head)
- AGPL-3.0 license (LICENSE file at PPPARTY_V2/ root)

**To-beat metrics (the horizon for the next build):**
- **Fingertip rotation noise:** 0.30-0.44 mean frame-to-frame quaternion delta on `*.03` tips. Body bones sit at 0.001-0.004 — fingertips are ~300× noisier. This is the next-build target. Three candidate levers in V2 HANDOFF item 1.b: palm-normal `side_ref` (recommended first), heavier tip One Euro, quaternion-aware post-bake smoothing.
- **Pelvis world position:** anchored at origin via rest_head_local. Puppet doesn't translate when the kid walks. MP `pose_world_landmarks` are hip-centered = no absolute position. V2.x territory; needs research doc.
- **Foot+floor contact:** feet inherit rest under occlusion, rotation-only (no IK). Ground plane clamp / IK rig / stance-blend are the candidate options. Couples with hip translation.
- **Default scene fps + frame_end:** still 24/250 in `Create V2 Rig`. Bake fps=30 + longer frame_end into the rig builder. Tiny task, bundle with another change.
- **iMac FPS test:** Pass 1 needs to hold 30 FPS on the deployment spec floor (David's 2023 iMac). Untested.

**Cross-references:**
- Source: `core/recorder.py` `_apply_median_hand_scale` — the per-class split logic
- Empirics: HANDOFF.md "Day 8d — Per-class estimator split" section (post-shipping diagnostics)
- Related memories: `feedback_blender_52_slotted_actions`, `project_v2_day8_median_hand_calibration`, `feedback_research_doc_first_pattern`

---

## Format reminder for future entries

When a future build dethrones the current benchmark, prepend a new entry above and DO NOT delete this one. The header line should be: `## 🎯 PPPARTY_V2_v2.0.0-dayNX.zip — YYYY-MM-DD`. Keep the same four sections (Title / Verified / Don't-regress properties / To-beat metrics / Cross-references). The historical record is part of what makes this useful for the dissertation later — it's literally a chronicle of design progression.
