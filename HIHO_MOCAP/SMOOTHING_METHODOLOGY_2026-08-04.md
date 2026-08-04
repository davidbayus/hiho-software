# Rig Noise Cleanup — Measurements and Design Direction

**Date:** 2026-08-04
**Data:** take `2026-08-01_17-22-03` — the perimeter walk on the remounted ring
(EXCELLENT 0.42 px calibration), 3600 frames at 60 fps, 63 bones, quaternion.
**Status:** measurement pass complete. Design direction proposed, not built.
Research-doc-first per the standing rule.

This answers two questions David raised: **is per-region smoothing strength a real
idea**, and **what replaces "feeling it out" as a method**.

---

## Part 1 — The per-region theory is correct, and it is measurable

David's theory: *"each area of the rig needs its own smoothing strength. Hands and feet
need the most, and the strength decreases as we near the center of the body — almost like
weight paints, but for noise smoothing."*

Splitting every rotation channel into a motion band and a noise band (real human motion
lives below about 6 Hz; anything above 8 Hz at 60 fps is essentially all noise), then
measuring how much noise each region carries relative to its real motion:

| Region | Noise relative to motion |
|---|---|
| Shoulders | 0.16% |
| Thighs | 0.12% |
| Spine | 0.28% |
| Neck | 0.29% |
| Pelvis (root) | ~0.00% |
| Upper arms | 0.22% |
| Shins | 1.08% |
| Forearms | 1.07% |
| Feet | 2.28% |
| Heels | 4.72% |
| Fingers | 9.05% |
| Thumbs | 22.13% |
| Palms | 30.29% |
| **Hands (wrist)** | **36.74%** |

**A clean gradient from the body's center outward, spanning more than two hundred to one.**
The theory is right.

### One refinement worth knowing

The gradient tracks **how well the cameras can see a landmark**, not purely distance from
the center. The shoulders are cleaner than the pelvis. The spine is cleaner than the
pelvis. The neck is noisier than the thighs.

That is MediaPipe's confidence map showing through: shoulders and hips are its most
reliable landmarks, hands are its worst. So the mental model is **"noisy where the tracking
is weak,"** which usually *is* the extremities, but not always. Worth keeping in mind when
the weights get authored — the feet, notably, are only moderately noisy, well below the
hands.

### The root is essentially clean

Pelvis translation carries **0.003%** noise relative to motion. It is the cleanest channel
in the take by a wide margin.

**Practical consequence: smoothing the root is close to pure loss.** There is nothing there
to remove, so any filtering just eats real travel — which is exactly what produces foot
sliding and mushy weight shifts. This is a rule worth adopting immediately, independent of
anything else built.

---

## Part 2 — Why "feeling it out" never converges

Here is the part that reframes the problem.

**A single filter is already partly self-adapting.** Apply one 6 Hz Butterworth to every
bone and it corrects the hands about ten times more than the pelvis, and roughly fifty
times more than the shoulders — because a filter can only remove what is actually there.

| Region | How far one 6 Hz filter moves it |
|---|---|
| Shoulders | 0.09° |
| Spine | 0.23° |
| Thighs | 0.39° |
| Pelvis | 0.41° |
| Shins | 0.47° |
| Upper arms | 0.54° |
| Neck | 0.74° |
| Feet | 0.85° |
| Forearms | 0.95° |
| Fingers | 3.14° |
| Hands | 4.16° |

So per-region strength is **not** about making the filter work harder on hands. It already
does. The real problem is different, and sharper:

> **One cutoff has to serve both ends of a two-hundred-to-one gradient, and it cannot.**
> Set it gentle enough to protect the body's core and the hands still shake. Set it strong
> enough to tame the hands and you start eating real motion out of the spine and hips.

That is precisely the experience of "feeling it out" each time and never quite landing it.
David has been hunting for a single number that does not exist.

### The head-to-head

Measured on this take. "Core motion kept" is how much of the real 0–6 Hz movement survives
in the hips, spine, thighs and shoulders. "Extremity shake" is the leftover frame-to-frame
twitch in hands, fingers and feet — lower is better.

| Setting | Core motion kept | Extremity shake |
|---|---|---|
| Raw, no smoothing | 100% | 1.482° |
| Global 3 Hz | 98.4% | 0.137° |
| Global 4 Hz | 99.2% | 0.213° |
| Global 6 Hz | 99.8% | 0.412° |
| Global 9 Hz | 100% | 0.767° |
| **Per-region — core 9, feet 6, fingers 4, hands 3** | **100%** | **0.204°** |

Per-region takes the core preservation of the gentlest global setting **and** essentially
the extremity cleanup of the most aggressive one. Global 9 Hz leaves nearly four times more
shake. Global 3 Hz buys its cleanup by eating real core motion.

**That is the whole argument for the idea, in one table, from David's own data.**

### The seam risk was tested, and it goes the other way

The obvious objection: filter the forearm at 6 Hz and the hand at 3 Hz and you might get a
visible step at the wrist. Measured on the wrist and ankle joints — the two worst seams in
the proposed plan:

| Setting | Joint stutter | Worst-case stutter |
|---|---|---|
| Raw | 1.332° | 50.18° |
| Uniform 6 Hz | 0.403° | 3.82° |
| Uniform 3 Hz | 0.137° | 1.07° |
| **Per-region plan** | **0.192°** | **1.62°** |

The joints come out *better* under the per-region plan than under uniform 6 Hz, and close
to uniform 3 Hz. And comparing each bone against its own parent, nothing steps: hands end
up slightly **smoother** than their forearms (0.83× and 0.89× the stutter), feet only
slightly rougher than their shins (1.22× and 1.26×).

**This points at the cleanest way to think about the whole idea:**

> Per-region smoothing does not *create* a gradient of smoothness. It *removes* one.

The raw capture arrives with a two-hundred-to-one noise gradient baked in. A single global
filter preserves that gradient — the hands stay roughly ten times noisier than the core no
matter what number you pick. Per-region filtering flattens it, so the whole rig ends up
evenly smooth. That is why there is no seam: everything lands in the same place.

---

## Part 3 — Where it can actually live in Blender

Three things were checked directly against Blender 5.2 to find out what shape this can
take.

### The NLA strip is the wrong layer

Blender's own description of a strip modifier: *"Modifiers affecting all the F-Curves in
the referenced Action."*

A modifier on an NLA strip is uniform across every channel in the strip, by definition.
There is no per-bone hook at that level. So "a smoothing modifier for the NLA editor that
varies by body region" cannot be built as stated — the NLA layer has no idea which curve
belongs to which bone.

### Custom modifier types cannot be written in Python

F-Modifiers are not subclassable from Python. A genuinely new modifier type would mean
patching and shipping a modified Blender — off the table.

### But the per-curve layer has exactly the knob needed

Every individual F-Modifier carries an **`influence`** value from 0 to 1, plus
`use_influence` to switch it on. And Blender 5.2's stock **Smooth** modifier is a real
Gaussian with `sigma` and `filter_width`.

So this is achievable with entirely stock Blender data:

> **Put a Smooth modifier on each rotation curve, and set its influence from a per-bone
> weight.**

That is the weight-paint model, exactly as David described it, and it is **non-destructive
and live** — the weights stay adjustable, the original curves are never overwritten, and
the whole thing can be turned off. Which is better than what Butterworth currently offers,
since that bakes destructively.

Pose bones support custom properties, so the weights themselves have a natural home on the
bones.

### The honest caveat

The stock Smooth modifier is a Gaussian, not a Butterworth. Butterworth holds the overall
shape of a motion better and is the right tool for gait-style data, which is why it is the
current habit. The non-destructive route means accepting a Gaussian; the Butterworth route
means baking. **That is a real trade-off and it should be tested by eye before committing** —
it is exactly the kind of call that is David's to make, not a spreadsheet's.

---

## Part 4 — Proposed method, to replace feeling it out

Order matters here. Each step assumes the previous one is done.

**1. Repair rotation continuity first — always, before anything else.**
Non-negotiable, and it is the lesson of today's jitter hunt. Smoothing a take with
quaternion sign flips produces 78.7° of error at the flip frames. Every other step is
built on sand until this is done. Should live inside the Bake step; script available
meanwhile.

**2. Do not smooth the root.**
Pelvis translation is essentially noise-free. Filtering it only removes real travel and
creates foot sliding.

**3. Pick strength by body region, not by one global number.**
Starting points measured from this take, as a first draft to be judged by eye:

| Region | Starting cutoff |
|---|---|
| Pelvis, spine, shoulders, thighs | 9 Hz — barely touch these |
| Shins, upper arms, neck | 8 Hz |
| Feet, forearms | 6 Hz |
| Fingers | 4 Hz |
| Hands, palms, thumbs | 3 Hz |

**4. Judge by watching, not by numbers.**
The numbers pick the starting point. The eye makes the call. The failure mode of any
filter is that it makes motion *pleasant* — floaty, weightless, ironed-out. Feet planting
and weight shifts are where over-smoothing shows first.

**5. Re-check the feet last.**
Filtering moves contact points. If the feet slide after cleanup, the fix is contact
pinning, not less smoothing everywhere.

---

## What to build first, if anything

The smallest version that would settle it: **an operator that applies a per-region cutoff
using the table above, with the regions defined by bone name, and nothing else.** No
authoring UI, no weight painting, no custom modifier. Run it on this take, look at it next
to a global-Butterworth version, and see whether the eye agrees with the measurements.

If it does, the weight-paint version is worth designing properly. If it does not, that is a
cheap answer and nothing was wasted.

**This is a proposal, not a plan.** It goes in the queue behind the audit's demo-blocking
fixes, and it wants a proper design doc before any code — same as everything else.

---

## Open questions and things needing a live look

- **Gaussian versus Butterworth by eye.** The non-destructive route requires the Gaussian.
  Is the difference visible on this footage? Only David can answer that.
- **Do the measured cutoffs match what looks right?** These numbers come from one take, one
  performer, one ring. They are a starting point, not a law.
- ~~Does per-region smoothing create seams?~~ **Tested — it does not, numerically.** The
  joints come out better than uniform 6 Hz and neighbours land within 0.83×–1.26× of each
  other. Still worth one look by eye, since "no measurable step" and "reads right" are not
  the same claim.
- **Where does gap-filling belong in the order?** The generative-infill research already
  covers the blink window; how it interacts with filtering is unexamined.
- **Should the weights be per-bone or per-region?** Per-region is simpler and probably
  enough. Per-bone is the fuller weight-paint metaphor but a lot more authoring.
