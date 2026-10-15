# Rig parity check: HIHO MOCAP 1.5.7 vs the upstream FreeMoCap Blender addon (main, 2026-10-15)

*Laptop, 2026-10-15. Read-only comparison, nothing changed in the code. David's rule (10-15): the rig must be 1:1 with
upstream, "the only difference with ours is that we don't have a Skelly attached" (the bone-shaped mascot mesh), so that
bug reports and help in both directions talk about the same rig.*

**Upstream compared:** `github.com/freemocap/freemocap_blender_addon`, branch `main` at commit `549b0fd` (tree fetched
2026-10-15). Latest tagged release is still v2026.04.1041 (April 20); main is ahead of it. The files that define the
rig (`data_models/armatures/freemocap_armature_definition.py`, `data_models/poses/freemocap_tpose.py` and
`freemocap_apose.py`, `data_models/bones/bone_definitions.py`, `data_models/bones/bone_constraints.py`) were last
touched 2026-04-04, so the April release and today's main carry the SAME rig. Our vendored April copy is current for rig
purposes.

**Ours compared:** `core/build_rig.py` (armature + rest pose), `core/topology.py` (bone head/tail landmarks),
`core/bind_to_rig.py` (constraints), `core/enforce_rigid_bodies.py` (bone lengths). Scripts that did the comparison:
session scratch `parity.py` and `parity_constraints.py` (exec both sides' tables with Blender stubbed, diff per bone).

## 1. Verdict in one line

Skeleton and rest pose: identical (63 bones, 63 matching names, 63 matching T-pose rotations and rolls). Constraints:
identical targets and axes on all 63 bones. Four small differences remain, all on our side; two are worth fixing, two are
deliberate HIHO additions that should stay.

## 2. What matches, exactly

| Thing | Ours | Upstream | Result |
|---|---|---|---|
| Bone names | 63 | 63 | identical set |
| Parent of every bone | 63 | 63 | identical (root naming aside: upstream parents `pelvis` to a `root` bone, ours parents it to nothing) |
| T-pose rotation + roll, all 63 bones | | | **0 differences** |
| Head/tail landmark per bone | 62 named the same | 62 | identical. Upstream has an extra `head_nose` entry (head_center to nose) used only for length stats; ours calls that bone `face`, same landmarks |
| Constraint type + target per bone | 63 | 63 | identical on all 63 (damped tracks, locked tracks, copy locations) |
| Locked-track axes | | | identical for the freemocap T and A poses (upstream carries extra per-pose axis tables for Metahuman rigs; not our case) |
| Wrist (hand.R) limit rotation values | | | identical |

## 3. The four differences

### 3a. Left wrist limit is not mirrored (ours, a bug)
Upstream `hand.L` limit rotation: y from -25 to 36, z from -90 to 86. Ours applies the `hand.R` values to both hands
(y -36 to 25, z -86 to 90). Our table says "verbatim from ajc27"; it is verbatim for the right hand only. Effect: the
left wrist is clamped slightly off-center the wrong way. Fix: a mirrored `_HAND_ROT_LIMIT_L` in `bind_to_rig.py`.
Present since the first commit.

### 3b. Shoulder and heel bones are "unconnected" (ours, since the first commit)
Upstream's `ArmatureBoneInfo` defaults `connected=True` and `shoulder.R/L`, `heel.02.R/L` take the default. Our
`build_rig.py` sets them `connected=False`. The head still lands on the parent's tail at build time, so the rest rig
looks the same. During playback the difference is small but real: Blender ignores Copy Location on a connected bone, so
upstream's shoulder head stays glued to `spine.001`'s tail, while ours can slide to `neck_center` through its Copy
Location constraint. Fix: match upstream (`connected=True` on those four). No doc on our side explains the choice, so
it looks like a transcription slip, not a decision.

### 3c. Thirteen body bones lack upstream's rotation limits (ours, deferred on purpose in May)
Upstream adds a Limit Rotation constraint to `spine`, `spine.001`, `neck`, `upper_arm.R/L`, `forearm.R/L`,
`thigh.R/L`, `shin.R/L`, `foot.R/L` (joint ranges, local space; for example the forearm bends 0 to 146 degrees on Y and
cannot twist on Z). `HAND_BONES_DESIGN.md` (2026-05-27) put these in "Out: natural joint limits help animation but aren't
visually required". Only the wrist limit was later adopted, to stop a 180-degree wrist flip. Adopting the other thirteen
is a copy of upstream's table (values are in the comparison output; the script prints them). Note the limits change what
David sees: a knee can no longer hyperextend to follow a bad landmark, which is usually better, sometimes worse. One build,
testable on the ceiling take `2026-10-02_14-28-01`.

### 3d. Finger bone lengths (ours, keep)
Upstream sets every bone, fingers included, to its median length. HIHO uses the 90th percentile for finger bones,
mirrors hands, and since 1.5.7 caps each finger at a fraction of the performer's forearm and only mirrors hands that
tracked well (`FINGER_LENGTH_FIX_DESIGN_2026-10-04.md`). This is a motion-cleanup difference, not a rig difference: bone
names, parents, and rest pose are untouched, and any upstream user loading our output sees the same 63-bone rig. Upstream
has no equivalent; it is a finding worth sending them (gratitude first, David's call), not something to remove.

Upstream also sets `hand.R/L` tail to `right/left_hand_middle` for its length statistics. Ours does the same
(`topology.py`).

## 4. What upstream added to the rig since April that we do not have

Nothing in the rig tables themselves (unchanged since 2026-04-04). Around the rig:

- **A-pose rest option (PR #77, merged 2026-09-24).** The 2.0 GUI can now build the armature in `freemocap_apose`
  instead of `freemocap_tpose`. The A-pose table already exists in our vendored copy
  (`vendor/ajc27_freemocap_blender_addon/data_models/poses/freemocap_apose.py`). A-pose = T-pose with the arm chain
  rotated 45 degrees down (upper arm, forearm, hand and every finger bone go from Y -90 to Y -135 on the right, 90 to
  135 on the left; arm rolls follow) and the hand roll set to 0 instead of -90 / 90. **The finger fan (thumb 45 degrees,
  index palm 17, middle 5.5, ring -7.3, pinky -19) is the same in both poses; our T-pose already carries it.** See
  `APOSE_REST_DESIGN_2026-10-15.md`.
- **Hand range-of-motion limiter (PR #76, open) and the foot lock rewrite (#75, merged 08-18):** motion cleanup
  operators, off by default in their GUI; not rig definitions. HIHO's Lock Feet is the older method (noted 09-19).
- **Missing-hand survival (#69, #74, merged August):** `is_hand_bone()` in `bone_definitions.py` and NaN guards in the
  length statistics. Ours already skips bones with no valid readings.

## 5. Parity build: DONE as 1.5.9 the same day (3a + 3b, plus the wrist limit at influence 0; see BUGS_AND_BACKLOG 2026-10-15)

1.5.8 "parity": mirror the left wrist limit (3a) and connect the four bones (3b). Both are table edits. Check: load
`2026-09-19_16-06-36` (clean) before and after; shoulders and wrists should look the same or better. The thirteen body
limits (3c) are a separate decision and a separate build, because they change the look of every take.

The A-pose work (next doc) builds on this rig unchanged.
