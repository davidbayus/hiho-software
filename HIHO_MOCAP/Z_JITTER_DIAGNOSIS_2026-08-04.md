# The One-Frame Z Snap — Solved

**Take:** `2026-08-01_17-22-03` (the perimeter walk on the new ring, EXCELLENT 0.42 px calibration)
**File:** `HIHO_TESTING&CALIBRATION_BLENDS/HIHO_NEWRING_TESTWALK2_DIAGNOSTIC.blend`
**Date:** 2026-08-04
**Verdict:** Confirmed, root-caused, fixed, and verified. It is the root bone — David's suspicion was right.

---

## The symptom

Smooth the take with Butterworth or Gaussian and it looks good, except the whole rig
snaps around on Z for a single frame and then returns to normal. Before smoothing
the take is clean. The Graph Editor shows nothing obviously wrong.

## The cause: two spellings of the same pose

A rotation stored as a quaternion has two equally valid spellings. `q` and `-q`
describe **the exact same pose**. Both are correct; nothing in Blender prefers one.

The bake writes whichever spelling the solver produced on that frame. Seven times
across this take, the pelvis silently switched spelling mid-motion:

**Frames 557, 1433, 1539, 1858, 1889, 1905, 2813.**

That switch is invisible. The pose is identical either side of it. This was verified
directly: the pelvis world matrix is bit-for-bit unchanged across every flip.

Smoothing does not know any of this. A filter averages the raw numbers in the
channel. At a flip it averages `+q` against `-q`, the average lands near zero, and
zero is not a rotation the body was ever in. The bone swings, drags the whole rig
with it (it is the root), and recovers as soon as the filter window clears the flip.

**One flip = one wild frame. Seven flips = the seven snaps.**

The reason it reads specifically as a Z-axis turn: expressed as yaw, each flip is a
±357–358° step. A full-turn wrap on Z. Exactly "the whole rig turns on the Z axis by
a number of degrees and then goes back."

## The measurement

Running Blender's own Butterworth (order 4, 3 Hz cutoff, 60 fps) on the pelvis:

| | Worst error | Error at the seven flip frames | Everywhere else |
|---|---|---|---|
| **Take as baked** | **78.7°** | 25.7°, 48.0°, 14.0°, 36.1°, 29.1°, 58.3°, 78.7° | 0.98° |
| **After continuity repair** | 8.2° | 2.2°, 1.5°, 1.7°, 3.6°, 1.1°, 4.1°, 5.7° | 0.94° |

The error is not spread across the take. It sits entirely on the flip frames, and it
is enormous there — 78.7° at frame 2813. Away from the flips, smoothing behaves
identically before and after the repair (0.98° vs 0.94°), which confirms the repair
touches the bug and nothing else.

Frame 2813 is the worst of the seven. The file was parked on frame 2814 — David had
already hunted it down to the exact spot.

## Why the Graph Editor hid it

Three reasons, all worth knowing for next time:

1. **There is no Z channel to look at.** The rig is quaternion, so the pelvis has
   W/X/Y/Z channels that do not map to visible axes. The Z-axis snap the eye sees in
   the viewport has no single curve behind it.
2. **A flip looks like a crossing, not a spike.** All four channels mirror across
   zero simultaneously. Zoomed out over 3600 frames that reads as curves crossing —
   the shape the eye is trained to ignore.
3. **The bug is invisible until you smooth.** Scrubbing the raw take shows nothing,
   because the raw take genuinely is fine.

**And the built-in tool for this does not apply.** Blender's **Euler Filter** exists
precisely to repair rotation discontinuities — but it only operates on Euler
channels. On a quaternion mocap rig it silently does nothing. That is the trap.

## The fix

Walk each rotation channel and negate whole keyframes so the sequence stays on one
spelling. The pose never changes; only the numbers do.

Delivered as a standalone script:
**`HIHO_TESTING&CALIBRATION_BLENDS/HIHO_quaternion_continuity_repair.py`**
Scripting tab → Open → Run Script. Select an armature first, or leave nothing
selected to do every armature in the file.

Verified three ways:
- **No-op when clean** — reports "Already continuous. Safe to smooth."
- **Repairs when broken** — the pelvis was deliberately re-broken with the same seven
  flips; the script found and fixed all seven.
- **Pose-neutral** — across 13 bones and every third frame of the take, the resulting
  rotation matrices differ by exactly zero.

### The subtle part, for whoever maintains this

The obvious implementation is wrong. Comparing each frame against the *raw* previous
frame only fixes the first frame of a flipped run, then the comparison flips back and
the rest of the run is left broken. Each frame must be compared against the previous
frame **as already corrected**. The first attempt at this repair made exactly that
mistake and reported success while changing nothing — caught only because the
re-scan still found all seven flips.

## Twelve more bones had it too

The pelvis is the one that matters, because it is the root and its error moves the
whole body. But the same flips are present in twelve finger bones:

`f_index.03.R`, `f_middle.02.R`, `f_ring.02.R`, `f_pinky.02.R`, `f_index.02.L`,
`f_index.03.L`, `f_middle.02.L`, `f_middle.03.L`, `f_ring.02.L`, `f_ring.03.L`,
`f_pinky.02.L`, `f_pinky.03.L`

Same mechanism, smaller stage. Worth fixing in the same pass — the script does all of
them.

## THE ADDON CREATES THIS — and will do it again on every turning take

This is not a data glitch in one unlucky take. It is manufactured by our own Bake
step, and the exact line is:

**`operators/bake_animation.py:59`** — `pb.matrix_basis = samples[f][pb.name]`

The bake samples each frame's pose as a matrix, then assigns it back frame by frame.
Assigning a matrix makes Blender decompose it into location / rotation / scale — and
**matrix decomposition always returns the canonical spelling with `w` ≥ 0**. Each
frame is decomposed on its own, with no memory of the frame before it.

So whenever a bone's rotation passes through 180°, `w` crosses zero, the canonical
choice flips to the other spelling, and the curve jumps. Verified two ways in
isolation:

- Sweeping a rotation through a full 360° turn produces a sign flip at **185°** — the
  first sample after `w` passes through zero at 180°.
- An explicitly negative quaternion `(-0.707, 0, 0, -0.707)` assigned to a bone comes
  back as `(+0.707, 0, 0, +0.707)` after a `matrix_basis` round-trip. The sign is
  re-canonicalized, exactly as the bake does 3600 times per bone.

**This take walked the perimeter of the ring.** The pelvis yaw therefore swept the
full ±180° range (measured: −179.5° to +179.7°) and crossed the boundary seven times.
Seven crossings, seven flips. The numbers line up exactly.

The consequence is the part that matters for the semester:

> **Any take where the performer turns around is guaranteed to carry this bug, and it
> only shows up once the artist does the right thing and smooths.**

A recorded workflow demo in which David turns around — which a perimeter walk or any
natural performance will do — will break under smoothing unless this is fixed. That
makes it the highest-priority item found today.

## Where this belongs long-term

Inside the Bake step, not in a script David remembers to run. Two viable shapes:

1. **Continuity pass at the end of the bake** — run the repair over the newly written
   curves before the operator returns. Simplest, provably correct, matches the
   delivered script exactly.
2. **Continuity during the bake** — in pass 2, after setting `matrix_basis`, compare
   the resulting quaternion against the previously keyed one and negate before
   inserting. Avoids a second pass over 630 curves.

Recommend shape 1: it is the already-validated code, it also repairs takes baked by
earlier builds, and it keeps the bake loop untouched.

Design-doc-first per the standing rule; natural home is the ARTIST_INTUITION cycle.
Cost is trivial, risk is near zero (provably pose-neutral), and the payoff is that
this class of bug can never reach a student.

**Related paper cut:** the take is otherwise clean, so the bug is invisible until the
artist smooths. Same silent-failure theme the 2026-06-09 audit named.

**Separate, noticed in the same file:** the bake writes keys one call at a time —
63 bones × 3600 frames × 3 channels is roughly 680,000 individual `keyframe_insert`
calls for this take (`bake_animation.py:60-65`). That is why baking a long take is
slow. Batching the writes is a real speed win but a separate change.

## State of the diagnostic file

The repair is **applied in memory** in the open `HIHO_NEWRING_TESTWALK2_DIAGNOSTIC.blend`
and is **not saved**. Blender does not flag the file as modified (bulk keyframe writes
do not set the dirty flag), so there will be no save prompt on close.

- **To keep it:** save the file.
- **To discard it:** File → Revert.

Either way the script reproduces it in a few seconds.
