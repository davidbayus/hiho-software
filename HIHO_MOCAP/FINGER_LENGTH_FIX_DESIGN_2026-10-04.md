# Finger Length Fix (bug #4) — Design Note

*2026-10-04, laptop. Proposed build: **1.5.7**, one file (`core/enforce_rigid_bodies.py`). Status: **awaiting David's OK. No code written.***

## What went wrong (10-02, take `15-27-28`)

After a camera got knocked, the right hand tracked badly for about half the take. The addon sets each finger bone to
one fixed length for the whole take. To get that length it takes the **longest 10% of readings** (because fingers
usually read too short when seen at an angle). On this take the longest 10% of the right hand was garbage: an index
fingertip reading 692 mm. Then the addon **averages left and right** so the hands match: (692 + 36) / 2 = 364 mm.
The clean left hand got the right hand's damage. Result: 36 cm fingers on both hands, all 60 seconds.

## The fix, three rules

1. **A ceiling scaled to the performer.** No finger bone may be longer than a set fraction of that performer's own
   forearm (elbow to wrist, which the body tracker reads reliably). Readings above the ceiling are ignored when the
   length is picked. The fraction is generous (an index fingertip may be up to 13% of the forearm; a real one is
   about 9%), so a large hand is never squeezed. Scaling by the forearm means it works for a 6th grader and for
   David without a setting. If the body is missing, it falls back to an adult forearm (250 mm).
2. **Pick the length from the readings under the ceiling** (still the long end, so the old "no stubby fingers"
   reason holds).
3. **Only mirror hands that both tracked well.** Each hand gets a score: the share of its finger readings under the
   ceiling. If both hands score 2/3 or better, average them as today. If one hand scored badly, **both hands copy the
   good hand.** If both scored badly, use the better one (still under the ceiling).

## Tested on seven real takes (outside the addon, numbers only)

Index fingertip length the rig would get:

| Take | Right hand under ceiling | Left | Today | With the fix |
|---|---|---|---|---|
| 10-02 `15-27-28` (the blow-up) | 54% | 97% | **364 mm** | **27 mm** (copied from the left hand) |
| 10-02 `14-28-01` (ceiling take) | 90% | 96% | 36 mm | 25 mm |
| 10-02 `14-49-21` | 84% | 94% | 55 mm | 26 mm |
| 10-02 `15-04-29` | 86% | 97% | n/a | 27 mm |
| 10-02 `14-07-34` | 92% | 96% | n/a | 24 mm |
| 09-19 `16-06-36` (clean) | 99% | 99% | 24 mm | 23 mm |
| 09-18 `13-42-27` | 98% | 100% | n/a | 21 mm |

The clean 09-19 take barely changes (every bone within 1 mm). The noisy 10-02 takes get slightly shorter, saner
fingers, because their noise was stretching them too. **The bad take's fingers go from 36 cm to normal.**

## What this does NOT fix

- **Frames where a finger flails.** The length gets fixed, but a badly tracked hand still points its fingers the wrong
  way in those frames. On the blow-up take the right hand will still look bad in about half the frames; it just
  won't be giant. A per-frame "finger sanity" cleanup belongs next to Lock Feet (backlog), as its own build.
- Bugs #1–#3 (progress clocks, a new file forgetting the calibration). Separate builds.

## How we'll check it

1. Terminal check: run the new function on all seven takes; numbers must match the table above.
2. Install 1.5.7, load `15-27-28` again in Blender, and David looks at both hands.
3. Load the 09-19 take as well, to make sure a good take looks the same as before.

## Questions for David

1. Go ahead and build this as 1.5.7?
2. When one hand tracks badly, should the rig **copy the good hand's lengths** (proposed) or **leave each hand on its
   own**? Copying keeps the hands matched, which is what the mirror was for.
