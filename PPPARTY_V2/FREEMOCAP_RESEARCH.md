# FreeMoCap deep-dive — what's transferable to V2

**Author:** David Bayus + Claude Opus 4.7 (1M context)
**Date:** 2026-04-30
**Scope:** Survey [freemocap/freemocap](https://github.com/freemocap/freemocap) (latest v1.8.2, Apr 22, 2026) and the companion [freemocap/freemocap_blender_addon](https://github.com/freemocap/freemocap_blender_addon) (v2026.04.1041, Apr 20, 2026) for techniques worth porting into PPParty V2.
**Status:** Research-only. No code touched. Per `feedback_research_doc_first_pattern` — read first, design second, clean-room implement third.

---

## TL;DR

FreeMoCap and PPParty V2 are solving **different halves of the same problem**:

|                    | FreeMoCap                            | PPParty V2                          |
|--------------------|--------------------------------------|-------------------------------------|
| **Goal**           | Research-grade scientific mocap      | K-12 puppet performance             |
| **Camera count**   | 1–N (multi-cam triangulation)        | 1 (laptop webcam)                   |
| **Live or offline**| Offline-batch (record → process)     | Live mirror + real-time bake        |
| **Output**         | numpy + Blender + FBX/BVH            | Blender NLA strips                  |
| **License**        | AGPL-3.0                             | (TBD — none yet)                    |

**What's worth porting** (in priority order):

1. **Median-length bone calibration** — gold for hand sizing. Replace per-frame `scale_to_segment` with median-of-session length. ⭐⭐⭐
2. **Butterworth low-pass on baked clips** — extra polish pass after recording, complementing live One Euro. ⭐⭐
3. **Pose tracker abstraction** — long-term flexibility for swapping MediaPipe to other models. ⭐
4. **Empties-per-landmark debug viewer** — diagnostic visualization mode. ⭐ (only if we hit a debugging wall)

**What to skip:**

- Multi-camera triangulation, Charuco board calibration — wrong problem (we're single-cam).
- The full `Skeleton` Pydantic model with anthropometrics + center-of-mass — overkill for puppeteering.
- Their out-of-process Blender architecture — V2's in-process live mirror is the K-12 hook.

**Important license note:** FreeMoCap is **AGPL-3.0**. Any code copied verbatim would force V2 to be AGPL too. Treat their code as a **reference for techniques**, not source to copy. Read the algorithm, document the recipe, write our own.

---

## 1. Architecture comparison

### FreeMoCap pipeline (offline-batch)

```
  Record videos (1+ webcams)
        ↓
  Charuco board calibration (multi-cam volume)
        ↓
  MediaPipe (or YOLO etc.) per video → 2D landmarks
        ↓
  Multi-camera triangulation → 3D landmarks (numpy arrays)
        ↓
  Single-cam path: project to z-plane (fake the 3D)
        ↓
  Post-processing (skellyforge):
    • Interpolation (gap-fill missed detections)
    • Butterworth filter (low-pass smoothing)
    • Skeleton rotation (alignment)
    • Find good frame
        ↓
  enforce_rigid_bones: snap distal markers to median bone length per session
        ↓
  Save numpy → spawn Blender subprocess
        ↓
  ajc27_freemocap_blender_addon (separate Blender addon):
    • Load numpy
    • Create empties (one per landmark, animated per frame)
    • Build armature from empties (Rigify or custom)
    • Apply bone constraints
    • Generate body mesh
    • Optional FBX/BVH export
```

### PPParty V2 pipeline (live in-process)

```
  Webcam frame
        ↓
  MediaPipe (Pose + Hand async LIVE_STREAM, port 11111 sender process)
        ↓
  One Euro filter (real-time smoothing on sender side)
        ↓
  UDP packet → BodyReceiver in Blender
        ↓
  apply_landmarks_to_rig:
    • mid_hip, mid_shoulder, mid_chest computed live
    • _drive_bone_segment per body bone (rotates to match MP direction)
    • Hand bones scale.y = MP segment length / rest length (per frame)
        ↓
  pose_bone.matrix = LocRotScale(...) → viewport renders
        ↓
  If recording: keyframe_insert per bone per frame
        ↓
  Stop recording: action pushed to NLA strip
```

The two architectures are **not interchangeable**. FreeMoCap optimizes for accuracy after the fact; V2 optimizes for live mirror feedback. The K-12 hook ("wave at the screen, puppet waves back") requires V2's choice. Don't mix them.

---

## 2. Transferable techniques

### 2.1 Median-length bone calibration ⭐⭐⭐ (HIGH VALUE — confirmed urgent 2026-04-30)

**Update from David's review (2026-04-30):** "yes we still have tons of noise, and we havent applied any smoothing filters yet."

Verified post-review: One Euro IS wired in `mediapipe_sender.py` (line 174: `make_body_filters`, `make_arm_filters` lighter on landmarks 11–16, `make_hand_filters` per axis). What's NOT filtered is hand bone **size** — `scale_to_segment=True` in `_drive_bone_segment` recomputes Y-scale from raw MP segment length every tick, with no smoothing. One Euro filters the underlying landmark positions, but the receiver derives a NEW signal (segment length) from the filtered landmarks, and that derived signal can still jitter if MP gets two near-but-different filtered landmark estimates frame-to-frame.

The visible artifact: bone DIRECTIONS are smooth (One Euro at work), but bone LENGTHS pulse. Fingers visually appear to "vibrate in size" rather than direction. This is exactly the failure mode median-length calibration cures.



**Where:** [`freemocap/core_processes/post_process_skeleton_data/enforce_rigid_bones.py`](https://github.com/freemocap/freemocap/blob/main/freemocap/core_processes/post_process_skeleton_data/enforce_rigid_bones.py)

**What it does:** After capture, for each bone in the skeleton:
1. Measure the distance between the proximal and distal landmarks at every recorded frame.
2. Take the **median** of those distances (robust to outliers — beats mean).
3. For every frame where the actual distance differs from median, slide the distal landmark along the bone direction so the distance equals median.
4. Propagate the offset to all child landmarks recursively (so the limb stays connected).

**Why median, not mean:** MediaPipe occasionally produces wildly wrong frames (hand passes face → MP guesses for a few frames). Mean would average those into the rest length. Median ignores them.

**Fit for V2:** This is the **right answer for hand bone sizing**. Currently V2 hand bones use `scale_to_segment=True` — every frame, the bone's Y-scale is set to the live MP segment length. This means hand size jitters when MP tracking is shaky. Switching to median-of-session would:

- Stabilize hand proportions through a take.
- Still size to the actual performer (not a generic adult hand).
- Eliminate the per-frame Y-scale keyframes (recorder.py line 78–94 currently keys both rotation_quaternion AND scale for hand bones; with median sizing, scale is set once at the end of capture).

**What V2 doesn't need this for:** Body bones. V2 body bones have constant rest length and only rotate — no length variation to calibrate. The trick only helps where we currently allow length variation (= hand bones).

**Sketch implementation (V2.1 territory, not now):**

1. During `BodyRecorder` capture, in addition to keyframing rotation, log each hand bone's MP-derived segment length per frame to a per-bone list.
2. On `stop_recording()`, before pushing to NLA:
   - For each hand bone, compute `median_len = np.median(seg_lengths)`.
   - Set `pose_bone.scale.y = median_len / rest_length` ONCE.
   - Insert a single scale keyframe at frame_start (or just don't keyframe scale at all — let the constant value ride).
   - Clear all the per-frame scale fcurves we just baked.
3. Hand sizing is now session-stable.

**Risk:** if the kid changes hand pose dramatically mid-take (fist → open palm), MP segment lengths will vary too. Median absorbs this — fist segments are shorter, open segments longer, median lands sensibly between. Probably fine in practice; verify with a smoke test.

---

### 2.2 Butterworth low-pass filter on baked clips ⭐⭐

**Where:** [`freemocap/core_processes/post_process_skeleton_data/post_process_skeleton.py`](https://github.com/freemocap/freemocap/blob/main/freemocap/core_processes/post_process_skeleton_data/post_process_skeleton.py) — uses [skellyforge](https://github.com/freemocap/skellyforge), which wraps a standard SciPy Butterworth.

**What it does:** Offline low-pass filter applied to the entire numpy time-series after capture. Configurable cutoff frequency (default ~6 Hz for human motion), order (default 4), Butterworth response curve.

**Fit for V2:** Complement to live One Euro, not a replacement. Use case:

- Live mirror: One Euro filters tracker noise in real time. Tuning is conservative (don't over-smooth fast motion or the kid notices lag). Some residual jitter survives.
- Recorded clip polish: After Stop Recording, run a Butterworth pass over the captured fcurves. Tighter cutoff is OK because it's offline — no latency cost.

The two filters target different surfaces (per memory `feedback_three_smoothing_physics_surfaces`): One Euro on live tracker inputs, Butterworth on baked keyframes. Clean separation.

**Sketch implementation (V2.1 polish phase):**

1. After `stop_recording` pushes Action to NLA, extract the rotation_quaternion fcurves per bone.
2. For each fcurve, run scipy.signal.filtfilt with a Butterworth filter (low-pass, cutoff ~6 Hz, order 4).
3. Replace the fcurve with smoothed values.
4. NLA strip now plays back smoother than live capture.

**Risk:** Quaternion smoothing is non-trivial — can't just low-pass each component independently (introduces artifacts). Need slerp-aware smoothing or Euler-decompose-smooth-recompose. FreeMoCap operates on positions (vectors) not orientations (quaternions), so they sidestep this. We'd need to handle it.

**Alternative:** Smooth at the marker level (the underlying MP landmark stream stored as numpy) and re-derive bone rotations from the smoothed markers — basically duplicating FreeMoCap's pipeline post-hoc. More work, but cleaner.

---

### 2.3 Pose tracker abstraction ⭐

**Where:** FreeMoCap v1.4.7 generalized to multiple pose trackers via [skellytracker](https://github.com/freemocap/skellytracker). Trackers expose a uniform interface: `track(image) → landmarks_with_confidence`.

**What it does:** Plug-and-play swap of MediaPipe Pose ↔ YOLO Pose ↔ MMPose ↔ etc. Each tracker self-describes its `ModelInfo` (landmark names, schema) so downstream code doesn't hardcode "MediaPipe."

**Fit for V2:** Probably not now, but **worth knowing it exists** for future-proofing. If we ever want to:

- Swap MediaPipe to a smaller/faster model for the e-waste deployment target
- Try YOLO for body and keep MediaPipe for hands
- Run a custom ML model trained on classroom kids

…having a tracker abstraction layer means we don't have to rewrite the whole receiver. For now, V2 is MediaPipe-specific by design and that's fine — premature abstraction would slow us down.

**File a "consider when..." flag:** if we ever need to swap MP itself, look at skellytracker's `ModelInfo` pattern.

---

### 2.4 Empties-per-landmark debug viewer ⭐ (CONDITIONAL)

**Where:** [`ajc27_freemocap_blender_addon/core_functions/empties/`](https://github.com/freemocap/freemocap_blender_addon/tree/main/ajc27_freemocap_blender_addon/core_functions/empties)

**What it does:** Before building an armature, FreeMoCap creates one Blender Empty per MediaPipe landmark (33 body + 21×2 hand + 478 face = ~553 empties). Each empty's location is keyframed per frame from numpy data. The result: a "stick figure ghost" you can scrub in the timeline to see raw mocap.

**Fit for V2:** **Skip unless we hit a debugging wall.** We don't need this for the K-12 product — the puppet IS the visualization. But if we ever can't tell whether a tracking artifact is a sender bug or a receiver bug, an empties-per-landmark mode would let us see the raw data directly.

If we add it: a "Debug: Show Raw Landmarks" toggle in the panel that creates empties on receive instead of (or alongside) the rig drive.

---

## 3. What's deliberately not transferred

### 3.1 Multi-camera triangulation + Charuco calibration

FreeMoCap's core differentiator. Not relevant to V2 — we're single-cam by design (laptop webcam, deployable kit must be one device).

### 3.2 Center-of-mass + biomechanics analysis

FreeMoCap is a research tool — they compute segment center of mass, total body COM, joint angles for biomechanics studies. V2 is a puppeteering tool. These outputs aren't useful for our pedagogy.

### 3.3 Out-of-process Blender architecture

FreeMoCap saves numpy → spawns Blender subprocess → addon imports numpy. This is the right pattern when capture is offline-batch. V2's live mirror requires in-process — webcam frames must reach Blender at 30 FPS with low latency, not after the recording is done.

### 3.4 The full `Skeleton` Pydantic model

Their `Skeleton` model has `markers`, `segments`, `joint_hierarchy`, `virtual_marker_data`, `center_of_mass_definitions`. It's a generalized biomechanics data model. V2's `core/rig.py` has `BONE_REST_POSITIONS` and `BONE_PARENTS` — three orders of magnitude simpler, fits our needs exactly. Don't import their abstraction.

### 3.5 ajc27 armature creation

They build a Blender armature from empties (one Empty per landmark). V2 builds the armature directly from `BONE_REST_POSITIONS` in `create_rig.py`. Their pattern is more flexible (any tracker schema → empties → armature). Ours is more efficient (skips the empties step entirely). For our scope, ours wins.

---

## 4. Reference URLs (canonical, as of 2026-04-30)

**Main repos:**
- [freemocap/freemocap](https://github.com/freemocap/freemocap) — capture + processing pipeline (Python, Qt GUI). v1.8.2, Apr 22, 2026.
- [freemocap/freemocap_blender_addon](https://github.com/freemocap/freemocap_blender_addon) — Blender-side rig + export. v2026.04.1041, Apr 20, 2026.

**Companion libraries:**
- [freemocap/skellyforge](https://github.com/freemocap/skellyforge) — post-processing (interpolation + Butterworth + alignment).
- [freemocap/skellytracker](https://github.com/freemocap/skellytracker) — pose tracker abstraction (MediaPipe / YOLO / etc.).
- [freemocap/documentation](https://github.com/freemocap/documentation) — Writerside-built user docs.

**High-value files (in local copy at `R&D/freemocap-main/`):**
- `freemocap/core_processes/post_process_skeleton_data/enforce_rigid_bones.py` — median bone-length recipe
- `freemocap/core_processes/post_process_skeleton_data/post_process_skeleton.py` — Butterworth pipeline entry
- `freemocap/data_layer/skeleton_models/skeleton.py` — Skeleton Pydantic model (reference, don't import)
- `freemocap/core_processes/process_motion_capture_videos/processing_pipeline_functions/anatomical_data_pipeline_functions.py` — anatomical processing (didn't read in this dive)

**High-value files (online, in `freemocap_blender_addon`):**
- `ajc27_freemocap_blender_addon/core_functions/create_rig/add_rig_rigify_method.py` — Rigify-based rig generation. Worth a look when V2.1 export comes up.
- `ajc27_freemocap_blender_addon/core_functions/create_rig/apply_bone_constraints.py` — joint constraints (limit rotation, IK, etc.). Reference for V2's Phase 7 constraint pass.
- `ajc27_freemocap_blender_addon/core_functions/export_3d_model/` — FBX/BVH export. Direct read when V2.1 export ships.

**Local copy version mismatch:** local `freemocap-main` is v1.7.4 (from Apr 12). Latest is v1.8.2. The diff covers multi-cam triangulation outlier rejection (irrelevant to V2) and minor fixes. Local copy is fine for our purposes; no need to refresh.

---

## 5. Conclusion + next-steps

**Tier-of-applicability ranking** (revised after David's review):

1. **NEXT (urgent — hand jitter is real):** Median-length hand calibration. Per-frame `scale_to_segment` is the noise source David is seeing. Replace with median-of-session — straightforward, contained. Estimated ~2-3 hr including smoke test. **Promoted from Phase 7 backlog to immediate next work after Tier 1 rig additions (or instead of, if David wants to fix noise first).**
2. **V2.1 (export pipeline) — BVH-first:** Read `freemocap_blender_addon`'s **BVH** export path before designing V2's export. BVH is the priority because it's where cleanup + combining lives in animation tools (Blender's NLA/dopesheet, Cascadeur, etc.). FBX deferred to V2.2+ if game-engine targets ever come up.
3. **V2.1+ (polish):** Butterworth post-bake smoothing on recorded clips. Requires quaternion-aware filtering (slerp-based, not component-wise — can't just scipy.signal.filtfilt the quaternions independently or you get artifacts). Defer until live capture is rock-solid + hand calibration lands.
4. **Far future (research / e-waste deployment):** Pose tracker abstraction if we ever swap MediaPipe.

**Doesn't need a follow-up dive:** their multi-cam triangulation, biomechanics analysis, the `Skeleton` Pydantic model, the out-of-process Blender architecture, FBX export.

**David's answers (2026-04-30):**

1. **Hand sizing IS noisy.** Confirmed visually. Median-length calibration moves up to "do this next," not "Phase 7 backlog."
2. **BVH is the priority export format**, not FBX. BVH is "where cleanup and combining animations live" — it's the format that flows into Blender's animation editor and other DCCs for polish work. FBX targets game engines and is lower priority for the puppet-show pedagogy.
3. **License: open-source, free, no monetization.** Software stays free. Money comes from CACHE donations and physical class fees, not the codebase.

## 6. Licensing — what David's stance maps to

What David described is **open-source software** (broad sense). Within that umbrella, the specific options are:

| License family       | What it means in plain English                                              | Who picks it                              |
|----------------------|------------------------------------------------------------------------------|-------------------------------------------|
| **MIT / Apache 2.0** | "Use it for anything, including making money off it. Just credit me."        | Most academic open source. Permissive.    |
| **GPL-3.0**          | "Use it freely, but if you change it and ship it, your changes also go open." | Linux kernel, Blender. Copyleft.          |
| **AGPL-3.0**         | Same as GPL, *and* covers running it as a network service (closes the SaaS loophole). | FreeMoCap, Mastodon. Strongest copyleft.  |
| **CC0 / Unlicense**  | "I waive all my rights. Public domain."                                      | Some scientific datasets. Most permissive.|

**Recommendation for V2: AGPL-3.0.**

Reasoning:
- It matches your political stance (per `project_dissertation_breakaway_frame` and the CACHE refuse-pedagogy memories): **prevents Silicon Valley extraction**. A corporate fork into a paid product would be forced to share their changes back. MIT-licensed code can be vacuumed up and resold; AGPL can't.
- It matches FreeMoCap's choice — they thought through the same tradeoffs and landed there for the same kind of project (open scientific tool, anti-extraction).
- It still allows free use in classrooms, by other researchers, by hobbyists. The only thing it blocks is closed-source commercial forking.
- It's compatible with all the libraries we use (MediaPipe is Apache 2.0, OpenCV is BSD — both compatible with AGPL downstream).

**One caveat to know:** some K-12 districts have policies against AGPL software because of legal-team conservatism around copyleft. If we ever bump into that, a dual-license arrangement (AGPL for general public, separate permissive license for specific district use) is possible — but that's a 2027 problem, not a 2026 one.

**Pithier label for what you described:** the phrase you're reaching for is **"copyleft open-source."** Free, completely open, *and* protected against being closed-up by someone else.

**To actually adopt:** drop a `LICENSE` file in `SOFTWARE/PPPARTY_V2/` with the AGPL-3.0 text (Blender ships it; or copy from FreeMoCap), and add a one-line copyright header to top of each `.py` file (`# SPDX-License-Identifier: AGPL-3.0`). Maybe 30 minutes of work. No hurry — can do it any time before V2 leaves your machine.

---

End of research doc.
