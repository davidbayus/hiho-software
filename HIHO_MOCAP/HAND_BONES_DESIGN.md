# HIHO MOCAP — Hand Bones Design

**Date:** 2026-05-27
**Driver:** v1.1 testing revealed two issues — alignment was wrong (fixed earlier today via `estimate_good_frame` port) and the rig has only stub `hand.R/L` bones instead of full finger bones like the FreeMoCap-exported `.blend` reference David uses for FRIENDS.

**Root cause for "no hand bones":** last night's v1.1 handoff said "Body-only subset — Holistic-hand fingers need landmarks we don't capture." That was wrong. FreeMoCap captures full MediaPipe Holistic (body + 2 hands + face). The hand npys are sitting in `output_data/` unused.

## Purpose

Port the missing pieces of ajc27's rig pipeline so HIHO MOCAP's Spawn Rig output matches what a FreeMoCap `.blend` exports — body bones + full finger bones, all animated.

## Scope

**In:**
- Load `mediapipe_left_hand_3d_xyz.npy` and `mediapipe_right_hand_3d_xyz.npy`.
- Apply the same alignment (translation + rotation) to hand data as to body.
- Apply `fix_hand_data` per-frame: translate each hand so its `wrist` landmark lands on the body's `wrist`.
- Spawn 21 empties per hand (42 total) under the existing Skelly root.
- Extend armature definition with ajc27's full finger bone topology (~40 finger bones across both hands).
- Extend T-pose table with ajc27's finger bone rotations.
- Extend bone-to-empties mapping to measure finger bone lengths.
- Extend constraint stack with one Damped Track per finger bone.

**Out (deferred to v1.2):**
- `LimitRotation` constraints on body and finger bones (ajc27 has these, we don't). Natural joint limits help animation but aren't visually required.
- `enforce_rigid_bodies` per-frame bone-length clamping (separate task, follows this one).
- Face data + face empties + face bones.
- `bone.category` distinctions (palm/proximal_phalanx/intermediate_phalanx/distal_phalanx) — these matter for ajc27's `new_head_metacarpal_ratio` palm-offset logic, which we're skipping for now.
- ajc27's "second pass" `reorient_empties` step (not used in his default pipeline either).

## Data sources

### npy files in `output_data/`
- `mediapipe_body_3d_xyz.npy` — (frames, 33, 3) — already used.
- `mediapipe_right_hand_3d_xyz.npy` — (frames, 21, 3) — NEW use.
- `mediapipe_left_hand_3d_xyz.npy` — (frames, 21, 3) — NEW use.
- `raw_data/mediapipe_3dData_numFrames_numTrackedPoints_reprojectionError.npy` — already used for `estimate_good_frame`.

### 21 hand landmark names (per side)
Order matches the npy's second axis. Source: `mediapipe_trajectory_names.py:60-81`.

```
0  wrist
1  thumb_cmc          5  index_finger_mcp     9  middle_finger_mcp    13 ring_finger_mcp    17 pinky_mcp
2  thumb_mcp          6  index_finger_pip     10 middle_finger_pip    14 ring_finger_pip    18 pinky_pip
3  thumb_ip           7  index_finger_dip     11 middle_finger_dip    15 ring_finger_dip    19 pinky_dip
4  thumb_tip          8  index_finger_tip     12 middle_finger_tip    16 ring_finger_tip    20 pinky_tip
```

Each is prefixed `right_hand_` or `left_hand_` to namespace from body landmarks (which have their own `right_thumb`, `right_index`, `right_pinky`).

## Pipeline order (matches ajc27 `main_controller.load_data`)

1. Load body npy + reprojection error npy.
2. Load right_hand npy + left_hand npy. (NEW)
3. Compute alignment from BODY foot data via `estimate_good_frame` + `put_skeleton_on_ground`.
4. Apply alignment translation + rotation to ALL components (body, right_hand, left_hand). (NEW)
5. Apply `fix_hand_data`: per-frame, translate each hand so `{side}_hand_wrist` sits on `{side}_wrist`. (NEW)
6. Return body + hands as separate arrays. Callers spawn empties + measure bone lengths from each.

ajc27's order also has `enforce_rigid_bones` between steps 4 and 5; we defer that to the next task.

## Naming conventions (Blender objects)

All landmark empties remain children of `HIHO_MOCAP_Skelly_<take>`:

- `hiho_<body_name>` — 33 body landmark empties (existing).
- `hiho_<virtual_name>` — 6 virtual landmarks (existing): `hiho_head_center`, `hiho_neck_center`, `hiho_trunk_center`, `hiho_hips_center`, `hiho_right_hand_middle`, `hiho_left_hand_middle`. Note `right_hand_middle` is a BODY-data midpoint (avg of `right_index` + `right_pinky`), not a hand-21 landmark. Same in ajc27 (`virtual_trajectories.py:20-27`).
- `hiho_<right_hand_name>` / `hiho_<left_hand_name>` — 21 hand-data empties per side (NEW). e.g., `hiho_right_hand_wrist`, `hiho_right_hand_thumb_cmc`, ..., `hiho_left_hand_pinky_tip`.

The constraint table references targets like `right_hand_thumb_cmc` — bind_to_rig's `_index_skelly_empties` strips the `hiho_` prefix when building the lookup, so it Just Works.

## Data structures (lifted verbatim from ajc27)

These four tables are the heart of the port. All lifted from ajc27 — no judgment, no improvement.

### Armature definition
Source: `data_models/armatures/freemocap_armature_definition.py`. The full 63-bone topology (15 body + 8 leg + 40 finger). Adds `parent`, `connected`, `parent_position`, optional `default_length`.

Key finger-bone parent chains (per side, .R shown):
- `thumb.carpal.R → thumb.01.R → thumb.02.R → thumb.03.R` (parent: hand.R)
- `palm.01.R → f_index.01.R → f_index.02.R → f_index.03.R` (parent: hand.R)
- `palm.02.R → f_middle.01.R → f_middle.02.R → f_middle.03.R` (parent: hand.R)
- `palm.03.R → f_ring.01.R → f_ring.02.R → f_ring.03.R` (parent: hand.R)
- `palm.04.R → f_pinky.01.R → f_pinky.02.R → f_pinky.03.R` (parent: hand.R)

Each palm/thumb-carpal bone has `connected=False, parent_position="head"` (it branches off the hand's head). All distal finger bones default to `connected=True, parent_position="tail"`.

### T-pose
Source: `data_models/poses/freemocap_tpose.py`. Euler XYZ rotation per bone applied to a `(0, 0, length)` base vector, plus optional roll. All finger bones use `(0, ±π/2, 0)` rotation (pointing along ±X like the arms), with side-specific roll. Palm bones add a small Z-rotation offset (17°, 5.5°, -7.3°, -19° for palm.01-04 respectively) to spread the fingers naturally in T-pose.

### Bone-to-empties (head/tail)
Source: `data_models/bones/bone_definitions.py`. Each bone's head and tail map to a named empty (body, virtual, or hand). Bone length = median over frames of `‖tail - head‖`. Example finger chain:
```
thumb.carpal.R:  head=right_hand_wrist,         tail=right_hand_thumb_cmc
thumb.01.R:      head=right_hand_thumb_cmc,     tail=right_hand_thumb_mcp
thumb.02.R:      head=right_hand_thumb_mcp,     tail=right_hand_thumb_ip
thumb.03.R:      head=right_hand_thumb_ip,      tail=right_hand_thumb_tip
```

### Constraints
Source: `data_models/bones/bone_constraints.py`. Each finger bone gets a single `DampedTrackConstraint` with `track_axis=TRACK_Y` targeting the next landmark in the chain. `hand.R/L` keeps its existing Damped Track to `right_hand_middle` (body-data midpoint) + Locked Track to `right_hand_thumb_cmc` (hand-21 landmark, replacing the body `right_thumb` we currently use as a workaround).

## fix_hand_data

Source: `freemocap_data_handler/operations/fix_hand_data.py:10-66`. Just the translation step; ajc27's rotation block is commented out and we skip it too.

```
for side in ("right", "left"):
    body_wrist     = body_trajectory[f"{side}_wrist"]            # (frames, 3)
    hand_wrist     = hand_trajectory[f"{side}_hand_wrist"]       # (frames, 3)
    delta_per_frame = body_wrist - hand_wrist                    # (frames, 3)
    hand_data += delta_per_frame[:, np.newaxis, :]               # broadcast over 21 landmarks
```

Net effect: hand-21 data gets rigidly translated each frame so its `wrist` landmark coincides with the body's `wrist` landmark. The hand's internal geometry (fingers' relative positions) is preserved.

## File-by-file plan

### `core/loader.py` (extend)
- New module-level constants: `MEDIAPIPE_RIGHT_HAND_LANDMARK_NAMES`, `MEDIAPIPE_LEFT_HAND_LANDMARK_NAMES` (tuples of 21 prefixed names each).
- New function: `load_aligned_data(recording_folder) -> dict[str, np.ndarray]` returning `{"body": (frames,33,3), "right_hand": (frames,21,3), "left_hand": (frames,21,3)}`. Internally: load each npy, apply same translation+rotation, then `fix_hand_data`. Keep `load_aligned_body_data` as a thin wrapper that returns only body for callers that don't need hands.
- New private function: `_apply_fix_hand_data(body, right_hand, left_hand)` — pure numpy, per-frame translation as described above.

### `core/output_rig.py` (extend)
- Extend `spawn_skelly_from_recording` to also spawn the 42 hand empties under the same Skelly root.
- Loop through `MEDIAPIPE_RIGHT_HAND_LANDMARK_NAMES` and `MEDIAPIPE_LEFT_HAND_LANDMARK_NAMES`, using `_create_keyframed_empty` with `empty_display_type='SPHERE'` and a smaller `EMPTY_SCALE` (e.g., 0.015 for fingers vs 0.05 for body — fingers are small).

### `core/virtual_landmarks.py` (no change)
The virtual landmarks (`right_hand_middle`, `left_hand_middle`) stay computed from BODY data per ajc27. We don't need to recompute them when full hand data is available.

### `core/build_rig.py` (extend)
- Extend `_ARMATURE_DEFINITION` dict with ajc27's finger bone topology (40 new entries).
- Extend `_TPOSE` dict with ajc27's finger T-pose rotations (40 new entries).
- Extend `_BONE_TO_EMPTIES` dict with finger bone head/tail mappings (40 new entries).
- `measure_bone_lengths` needs access to hand-21 landmark positions. Easiest: have it accept the full data dict (body + hands), build a unified `positions` dict keyed by landmark name (body + virtual + right_hand + left_hand).

### `core/bind_to_rig.py` (extend)
- Update `hand.R` / `hand.L` constraints: change `LOCKED_TRACK` target from `right_thumb`/`left_thumb` (body fallback we used pre-hand-data) to `right_hand_thumb_cmc`/`left_hand_thumb_cmc` (hand-21 canonical).
- Add 40 new finger bone entries to `_CONSTRAINTS`, each a single `DAMPED_TRACK` to the next landmark in chain, `TRACK_Y`.

### `operators/spawn_rig.py` (idempotency check)
- `_purge_existing` already deletes the Skelly root + all its children recursively, so adding 42 more child empties doesn't break it. No change needed.

## Test plan

1. Build zip, install in Blender 5.0, point at the existing `2026-05-26_12-10-19` take, run Spawn Rig.
2. Expected: rig now has visible finger bones (small octahedrons at each finger joint). Hands should animate along with the body during playback.
3. If fingers look static/rigid: check that the per-frame hand trajectories are non-degenerate (run `load_aligned_data` in plain Python and inspect motion variance per landmark).
4. If fingers move but in wrong places: check `fix_hand_data` is applied AFTER alignment, not before.
5. Compare visually to a FreeMoCap-exported reference `.blend` David has from earlier work. Should match in structure (bone count, topology).

## What this doesn't fix

- Lean/jitter — likely needs `enforce_rigid_bodies` (next task).
- Body bone wobble — same.
- Visible finger jitter — also `enforce_rigid_bodies`.
- Face animation — face data exists, not addressed here.
- LimitRotation joint limits — ajc27 has them, we skip them here for scope.
