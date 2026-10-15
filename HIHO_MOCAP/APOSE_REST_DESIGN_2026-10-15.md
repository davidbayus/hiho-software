# A-pose rest pose for the HIHO rig: design note

*2026-10-15, laptop. Proposed build: **1.5.8**, three files (`core/build_rig.py`, `core/marker_fit.py`,
`properties.py`). David's decisions this morning: adopt upstream's A-pose numbers verbatim ("if there's an upstream
A-pose number, let's get it, and then I'll take a look and decide from there"); make it a choice like upstream's, with
A-pose as the HIHO default; keep the rig 1:1 with upstream.*

## 1. Why

David (10-15): the rig's rest pose is a T-pose today. He wants an A-pose rest pose "with the fingers properly distanced
from one another", so students can build their blockout around the rig at rest and, when ready, "bind directly to the
rest pose and start animating". A-pose is also what every rigging tool and marketplace expects (Mixamo, ActionForge,
Rigify's metarig, Auto-Rig Pro's reference). Upstream agrees: on 2026-09-24 they merged an "Armature Rest Pose: T-Pose
(default) or A-Pose (useful for retargeting)" option into the FreeMoCap 2.0 GUI (addon PR #77).

## 2. The numbers (verbatim from upstream, nothing invented)

Upstream's table lives in our vendored copy: `vendor/ajc27_freemocap_blender_addon/data_models/poses/freemocap_apose.py`
(unchanged on upstream main, 2026-10-15). Compared bone by bone with their T-pose (`RIG_PARITY_UPSTREAM_2026-10-15.md`
section 4), the A-pose differs on the arm chain only:

| Bones | T-pose | A-pose |
|---|---|---|
| upper_arm, forearm (R / L) | rotation Y -90 / 90, roll -90 / 90 | rotation Y **-135 / 135**, roll **-135 / 135** |
| hand (R / L) | rotation Y -90 / 90, roll -90 / 90 | rotation Y **-135 / 135**, roll **0** |
| every finger bone (40) | rotation Y -90 / 90, Z = its fan angle, roll 0 | rotation Y **-135 / 135**, same Z fan, roll 0 |
| pelvis, spine, neck, face, shoulders, legs, feet | | identical |

So the arms swing 45 degrees down from horizontal, the hands and fingers follow, and the wrist roll changes from
-90 to 0 (their choice; the hand's live orientation is fixed by two tracking constraints anyway, see 4b).

**The finger fan is the same in both poses and our T-pose already has it:** thumb 45 degrees out, index metacarpal 17,
middle 5.5, ring -7.3, pinky -19 (all about the local Z). Measured on the 1.5.7 rig at rest (take `2026-10-02_15-27-28`),
adjacent fingertips sit 21.6 / 27.6 / 31.1 mm apart and the thumb tip is 126 mm from the index tip. Picture:
`SOFTWARE/MEDIA/HIHO_REST_HAND_TPOSE_2026-10-15.png` (top view, right hand, rest position). Nothing overlaps at rest.
**The overlap David sees must be in playback** (the fingers are posed by the take, and a noisy hand folds them through
each other), or on a bound character. A-pose does not change that; a per-frame finger cleanup would (backlog, next to
Lock Feet). If David wants a wider fan than upstream's at rest, that is a deliberate departure from 1:1 and the right
move is to propose it upstream first.

## 3. What changes in the addon

1. **A preference, "Rig rest pose": A-pose (default) or T-pose.** Addon Preferences, next to "HIHO data home". Per
   machine, like the other preferences, so a classroom laptop keeps its choice across files. Upstream defaults to T; HIHO
   defaults to A because our students build characters around the rig and A is what their tools expect.
2. **`build_rig.py` carries both tables.** `_TPOSE` stays as is. `_APOSE` is added, verbatim. `rest_pose_table()`
   returns the one the preference names; `build_freemocap_armature` uses it. Bone names, parents, lengths, and the
   constraint stack are untouched (upstream pairs both poses with the same constraints; the locked-track axes are
   identical for the two poses, checked 10-15).
3. **`marker_fit.py` follows the same table.** The Studio auto-rig aligns each fitted bone's roll to the canonical rig's
   local Z, read off the pose table. It must read the same table the mocap rig is built from, or a Studio character and
   the mocap rig disagree on twist. One import changes.
4. Nothing else. Load Take, Spawn Rig, Bake, Save Out and Send to Character do not know which pose the rig was built in.

## 4. What this does and does not affect

- **4a. Playback.** The constraints aim every bone at its landmarks; rest pose only moves the "zero". Bones with a
  single Damped Track (arms, fingers) keep the rest roll, so their twist in playback changes with the pose. Upstream
  ships the A-pose with the same constraint table, so the A rig plays as upstream's A rig plays; we are copying a tested
  configuration, not designing one. Check in Blender: the same take built both ways, arm and finger directions must
  match frame for frame (direction, not roll).
- **4b. The wrist limit.** Limit Rotation works in the bone's local space, so the same wrist limits mean something
  different once the hand's rest roll is 0 instead of -90. Upstream applies one limit table to both poses; we do the
  same (1:1). If the A-pose wrist clamps wrong on a real take, that is a finding for upstream, not a HIHO patch.
- **4c. Baked clips are rest-pose specific.** A baked action stores rotations relative to rest. A clip baked on a
  T-pose rig will not play on an A-pose rig of the same take. The two library files in `HIHO_MOCAP_LIBRARY/DAY_1` carry
  their own rig inside, so they keep working. But a shared clip library (the Studio "starter clips" idea) needs one rest
  pose for all time. **Deciding A now, before that library exists, is the cheap moment.**
- **4d. Old scenes.** A scene with a T-pose rig keeps it; nothing is rebuilt. Spawn Rig rebuilds in whatever the
  preference says.
- **4e. Upstream exchange.** A HIHO take reported upstream is built in A unless the preference is flipped; their GUI has
  the same option, so a report can name the pose and they can reproduce it. Bone names and constraints stay identical.

## 5. The blockout workflow (next builds, not 1.5.8)

David's intent, confirmed 10-15: a student models a character around the rig at rest, then binds straight to it, no
markers. ActionForge calls this door "make a character on our skeleton". Pieces, each its own build after 1.5.8:

1. **A shipped rest-pose rig, `HIHO_Rig_Apose.blend`** (new asset, no addon code): the 63-bone rig at A-pose rest,
   bone lengths from a clean adult take (`2026-09-19_16-06-36`, David, standing height 1.42 m pelvis), no animation, no
   constraints, no empties, posed at the origin facing -Y. The student appends or links it and models around it, or
   scales it to the character. A second, child-proportioned rig can follow once a student take exists.
2. **"Bind to the HIHO rig" in Studio**: select mesh parts + the shipped rig, pick Voxel or Automatic skinning (both
   exist), done. Because the rig IS the mocap rig (same names, same rest), **Send to Character works unchanged**: it
   copies world rotations bone by bone, and the pelvis location, so proportions can differ from the performer's. Fingers
   come for free (63 names match), which the marker auto-rig (23 bones) cannot offer.
3. **Starter clips**: A-pose only, from this point on.

## 6. How we check 1.5.8

1. Install, flip nothing: Spawn Rig on `2026-09-19_16-06-36`; upper_arm.R rest direction must be 45 degrees below
   horizontal, wrist roll 0, 63 bones bound, plays.
2. Same take with the preference on T-pose: identical to 1.5.7 (regression).
3. Studio auto-rig on the chibi (markers) still builds and binds (roll references now read the A table).
4. David looks at the A-pose rig at rest, hands included, and decides.

## 7. Questions for David

1. Default A-pose, with T-pose one click away in Preferences: confirmed 10-15.
2. Keep upstream's finger fan at rest (1:1), and treat the playback overlap as the separate cleanup it is? (My
   recommendation.)
3. Proportions for the shipped blockout rig: David's own clean take, or wait for a student take?

## 8. Build result, 1.5.8 (same day)

Built and installed on the laptop (commit `f8a3836`). Checks from section 6: (1) A-pose rig on `2026-09-19_16-06-36`:
upper_arm.R rests 45.0 degrees below horizontal, wrist local Z rotated as upstream's table says, 63 of 63 bones bound,
plays. (2) T-pose preference: identical to 1.5.7 (0.0 degrees up-arm drop, same bones bound). (3) The Studio roll
references read the active table (23 refs). (4) Picture for David: `SOFTWARE/MEDIA/HIHO_RIG_APOSE_REST_2026-10-15.png`.

Playback comparison, A build vs T build, same take, same frames: upper arm, forearm, finger, thigh and spine bones point
the same way to 0.00 degrees on every sampled frame. **The wrist does not** (3.7 / 80 / 47 / 20 degrees apart at frames
1 / 300 / 900 / 1500), and the cause is section 4b exactly: the wrist Limit Rotation acts in the bone's local frame, which
the A-pose changes. Measured over the whole take with the limit switched off, both builds aim the hand perfectly on every
frame and the clean take has no flips; with it on, the hand points more than 10 degrees away from its target on 43%
(T) / 64% (A) of frames. Full table and options: `BUGS_AND_BACKLOG.md`, 2026-10-15. **So the A-pose is correct and
1:1, but it makes a pre-existing wrist problem more visible. David's pick for the next build: wrist limit off by
default (recommended), or A-pose off by default until then.**
