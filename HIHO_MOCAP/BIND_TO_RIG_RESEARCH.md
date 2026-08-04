# BIND_TO_RIG_RESEARCH.md — empties → Rigify metarig binder

**Status:** research, not design. Lifts the recipe from ajc27_freemocap_blender_addon. Design doc translates this into HIHO MOCAP's operator. Code follows after David signs off the design.

**Date:** 2026-05-26
**Prereq:** HIHO MOCAP v1.0 ships 33 keyframed empties (`hiho_<name>`) parented to `HIHO_MOCAP_Skelly_<takename>`.

---

## Problem statement

v1.0 outputs motion as 33 empties. To get a rigged character animation, students need those empties to drive an armature's bones. The bridge is a set of pose-bone constraints (Copy Location, Damped Track, Locked Track) that pin each bone to one or two empties, so when the empties play their keyframes the bones follow.

The reference implementation already exists in ajc27_freemocap_blender_addon. We lift the recipe (constraint pattern, bone-name table, virtual-landmark formulas), not the code.

---

## Source map — ajc27 binder

All paths relative to `/SOFTWARE/R&D/freemocap_blender_addon/ajc27_freemocap_blender_addon/`.

| File | What's in it |
|---|---|
| `core_functions/create_rig/create_rig.py` | Orchestrator. Creates a rig, applies constraints, bakes the result. We skip rig creation (user provides) and bake (see below). |
| `core_functions/create_rig/apply_bone_constraints.py` | The constraint applier — pose mode, iterate constraint defs, create constraints. **Substring match** on target empty name (`if constraint.target in obj.name`). |
| `data_models/bones/bone_constraints.py` | THE table. ~80 bones × constraint stacks. We lift this verbatim. |
| `data_models/armatures/bone_name_map.py` | Maps the table's logical bone names to actual armature bone names. For Rigify (`FREEMOCAP_ARMATURE`) it's an identity map. For UE Metahuman it renames (`upper_arm.R` → `upperarm_r`). |
| `data_models/mediapipe_names/virtual_trajectories.py` | The 6 virtual landmark formulas (center/midpoint definitions). |

---

## Constraint pattern (what each bone needs)

Three constraint types do the work. LimitRotation is opt-in joint clamps.

### Copy Location
Pins the bone's **head** to an empty's location. Used for the "root" bones of chains: pelvis, spine, shoulder.R/L, thigh.R/L. Without this, the bone would only rotate, not translate.

### Damped Track (TRACK_Y)
Rotates the bone so its **+Y axis** (Blender bones grow along +Y) points at a target empty. This is the workhorse — used for ~90% of bones. Example: `upper_arm.R` Damped-Tracks `right_elbow` so the upper arm points at the elbow.

### Locked Track
Like Damped Track but only rotates around one locked axis. Used for **twist** control: rotates the bone so an axis points at a target while keeping another axis locked. Example: spine Locked-Tracks shoulder while locked on Y — gives torso twist without flipping. Track/lock axes vary per "pose" (T-pose, A-pose, UE default). For our case we use the FREEMOCAP_TPOSE entries.

### LimitRotation (opt-in)
Per-bone min/max degrees on X/Y/Z, LOCAL space. Prevents anatomically impossible poses (knee bending backwards). Numbers in ajc27's table are tuned for the FREEMOCAP_ARMATURE specifically — applying them to a user's Rigify metarig may clamp legitimate poses if bone orientations differ.

**v1.1 default: OFF.** Add a toggle in v1.2 if students need it.

### IK
Defined in the enum but never instantiated in the constraint table. Skip.

---

## Bone constraint table (filtered to what we can drive)

ajc27's table has ~80 bones. About half are finger phalanges that need MediaPipe **Holistic** hand landmarks (`right_hand_thumb_cmc`, `right_hand_index_finger_pip`, etc.). HIHO MOCAP uses **Pose** landmarks only — no full finger articulation. So we drop fingers and bind the body.

Bones we can drive (body, head, hands as one rigid block):

| Bone | Constraints | Targets (logical name → our empty) |
|---|---|---|
| `pelvis` | CopyLoc + 2× LockedTrack + LockedTrack | `hips_center`, `right_hip` (x2), `trunk_center` |
| `pelvis.R` | DampedTrack | `right_hip` |
| `pelvis.L` | DampedTrack | `left_hip` |
| `spine` | CopyLoc + DampedTrack | `hips_center`, `trunk_center` |
| `spine.001` | DampedTrack + LockedTrack | `neck_center`, `right_shoulder` |
| `neck` | DampedTrack + LockedTrack | `head_center`, `nose` |
| `face` | DampedTrack | `nose` |
| `shoulder.R` | CopyLoc + DampedTrack | `neck_center`, `right_shoulder` |
| `shoulder.L` | CopyLoc + DampedTrack | `neck_center`, `left_shoulder` |
| `upper_arm.R` | DampedTrack | `right_elbow` |
| `upper_arm.L` | DampedTrack | `left_elbow` |
| `forearm.R` | DampedTrack | `right_wrist` |
| `forearm.L` | DampedTrack | `left_wrist` |
| `hand.R` | DampedTrack + LockedTrack | `right_hand_middle`, `right_thumb` (substituted from ajc27's `right_hand_thumb_cmc` which we don't have) |
| `hand.L` | DampedTrack + LockedTrack | `left_hand_middle`, `left_thumb` (same substitution) |
| `thigh.R` | CopyLoc + DampedTrack | `right_hip`, `right_knee` |
| `thigh.L` | CopyLoc + DampedTrack | `left_hip`, `left_knee` |
| `shin.R` | DampedTrack | `right_ankle` |
| `shin.L` | DampedTrack | `left_ankle` |
| `foot.R` | DampedTrack | `right_foot_index` |
| `foot.L` | DampedTrack | `left_foot_index` |
| `heel.02.R` | DampedTrack | `right_heel` |
| `heel.02.L` | DampedTrack | `left_heel` |

**20 body bones, 33 constraints total.** Hand twist falls back to `right_thumb`/`left_thumb` instead of finger-MCP midpoints.

---

## Virtual landmarks (6 extra empties we compute at bind time)

ajc27's constraints reference midpoints/averages of multiple MediaPipe landmarks. These don't exist in the raw 33; we compute them as additional empties keyframed alongside.

Formulas (all are simple weighted averages, weights sum to 1.0):

| Name | Source landmarks | Weights |
|---|---|---|
| `head_center` | `left_ear`, `right_ear` | 0.5, 0.5 |
| `neck_center` | `left_shoulder`, `right_shoulder` | 0.5, 0.5 |
| `trunk_center` | `left_shoulder`, `right_shoulder`, `left_hip`, `right_hip` | 0.25 × 4 |
| `hips_center` | `left_hip`, `right_hip` | 0.5, 0.5 |
| `right_hand_middle` | `right_index`, `right_pinky` | 0.5, 0.5 |
| `left_hand_middle` | `left_index`, `left_pinky` | 0.5, 0.5 |

We name these with the `hiho_` prefix to match our convention: `hiho_head_center`, `hiho_hips_center`, etc.

**Implementation note:** Compute from the already-loaded body landmark array (33 × frames × 3), write keyframes via the same slotted-actions API we used in `core/output_rig.py`. ~30 lines.

---

## Rigify metarig — bone name truth

ajc27's `FREEMOCAP_ARMATURE` map (lines 86–158 of `bone_name_map.py`) is an identity map. The bone names IT uses ARE the Rigify metarig names. Cross-checked against Blender's built-in Rigify metarig add (`Object > Add > Armature > Human (Meta-Rig)`):

- Spine chain: `spine`, `spine.001`, `spine.002`, `spine.003`, `spine.004`, `spine.005`, `spine.006`
- Pelvis: `pelvis.L`, `pelvis.R`
- Neck: ajc27 says `neck` — Rigify metarig actually has `spine.004` for neck, `spine.005`/`spine.006` for head. **POTENTIAL MISMATCH — design doc must address.**
- Arms: `shoulder.L/R`, `upper_arm.L/R`, `forearm.L/R`, `hand.L/R` ✓
- Legs: `thigh.L/R`, `shin.L/R`, `foot.L/R`, `toe.L/R`, `heel.02.L/R` ✓
- Face/head: ajc27 says `face` — Rigify metarig has separate face sub-rig with many bones, no single `face` bone.

Per [[use-rigify-as-bone-reference]]: design doc step 1 is to **drop a Rigify metarig in scene and verify bone names directly**, not from ajc27's map alone. Two known suspect bones: `neck`, `face`.

---

## Blender 5.0 compatibility check

Constraint API (`pose_bone.constraints.new(type_string)`, attribute assignment): unchanged in 5.0. ✓

ajc27's risky parts:
- `bpy.ops.nla.bake()` at line 51 of `create_rig.py` — converts constraint-driven motion to raw keyframes. Slotted-actions API change makes this **likely to break or produce non-slotted output**. **Decision: skip the bake.** Leave constraints live. Benefit: user can disable/scale constraints. Cost: armature has constraint stack instead of clean fcurves (resolvable later).
- `mode_set("POSE")`: unchanged.
- `bpy.data.objects[name]` for target resolution: unchanged.

---

## Comparison with our v1.0 output

| Aspect | v1.0 (empties) | v1.1 (bind) |
|---|---|---|
| What it outputs | 33 named empties, keyframed | Same empties + 6 virtual ones + constraint stack on user's rig |
| Data flow | npy → keyframed empties | Same source, empties unchanged; constraints reference them |
| Re-runnable | Re-process recomputes empties | Re-bind clears old constraints, adds new ones (toggle) |
| Blender API risk | Slotted actions fcurves (solved in `output_rig.py`) | Pose bone constraints — unchanged, low risk. Bake — skipped. |
| User-facing | `Spawn Rig` button | `Bind to Rig` button (new) |

---

## Open questions for design doc

1. **Source empties root:** auto-detect from `last_processed_path`, picker, or both? (Per [[operator-file-pickers]] — picker mandatory.)
2. **Target armature picker:** PointerProperty with poll filter for `ARMATURE` type. Where to place in the panel.
3. **Neck/face bone mismatch:** Use `spine.004` for neck? Skip face constraint entirely? Let user remap?
4. **Virtual landmarks:** Compute lazily (only when Bind is clicked) or eagerly (in `output_rig.py` alongside the 33)? Tradeoff: eager adds 6 extra empties cluttering the outliner; lazy adds compute time to Bind.
5. **Clear-before-bind:** If user runs Bind twice, do we wipe existing HIHO MOCAP constraints first or stack new ones? (Strong default: clear, with override toggle.)
6. **Pre-pose state:** Force rig to rest pose (Pose → Clear → User Transform) before applying constraints? Most likely YES — constraints work relative to current pose, so a mid-animation rig would bind weirdly.
7. **Rigify-only or "any armature with these bone names"?** Probably the latter — the bone-name check IS the filter.

---

## What we're NOT doing in v1.1

- Generating a new rig from bone measurements (ajc27's `add_rig_by_method`). User provides their own.
- Baking constraints to keyframes. Leave live. (v1.2 candidate.)
- Finger articulation. Hands move as rigid blocks. (Needs MediaPipe Holistic.)
- LimitRotation joint clamps. Opt-in flag in v1.2 if students request.
- UE Metahuman or non-Rigify rig support. Rigify metarig only for v1.1.
- IK constraints. Add later if needed.

---

## Pull-quotes from upstream

- "If pose bone does not exist, skip it" (ajc27 line 67) — **lift this verbatim**. Makes the binder forgiving for partial rigs.
- "Substring match on target empty name" (ajc27 line 102-105) — works, but watch for false matches. Our empties have a stable `hiho_` prefix so collisions are minimal.
- "track_axis varies per pose_name" (ajc27 line 138) — we hardcode `freemocap_tpose`. T-pose is the Rigify metarig default.

---

## Next step

Design doc: `BIND_TO_RIG_DESIGN.md`. Resolves the 7 open questions. After David signoff, implement.
