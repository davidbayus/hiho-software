# Per-Region Smoothing and Mocap Noise Removal — Prior-Art Research

Research sweep, 2026-08-04 (background agent, sources cited inline).
Companion to `SMOOTHING_METHODOLOGY_2026-08-04.md` (this session's measurements on the
08-01 perimeter-walk take) and `Z_JITTER_DIAGNOSIS_2026-08-04.md`.

---

## VERIFICATION NOTES (added after the sweep, laptop session 2026-08-04)

Claims below were independently checked before filing:

1. **The frame-rate bug (§0.1) is CONFIRMED ON THE LIVE PATH.** The sweep partially
   traced it through the retired vendored copy, but the live chain has the same hole:
   `external/process_take.py:158` builds `ProcessingParameterModel` with pure defaults →
   the conda env's freemocap 1.8.2 has `framerate: float = 30.0`
   (`post_processing_parameter_models.py:32`) → the filter consumes exactly that value
   (`post_process_skeleton.py:50`) → nothing anywhere in
   `core_processes/process_motion_capture_videos/` ever sets it. Our takes are 60 fps.
   **Effective consequence: the intended 7 Hz position pre-filter actually cuts around
   14 Hz — every HIHO take arrives roughly half as filtered as FreeMoCap intends, and
   the surviving 8–14 Hz band is precisely where hand jitter lives.** Fix is one line in
   OUR file (`process_take.py`): set `params.post_processing_parameters_model.framerate`
   (and the sibling `butterworth_filter_parameters.sampling_rate`) from the take's real
   fps. Queued as a build; see AUDIT_2026-08-04.md.
2. **`bpy.ops.pose.quaternions_flip()` (§2.4) was checked live in 5.2:** it exists, but
   its RNA is a bare pose-mode operator — no frame range, no scan options ("Flip
   quaternion values to achieve desired rotations, while maintaining the same
   orientations"). It fixes the CURRENT pose only. It is not a timeline unroll, so HIHO
   cannot lean on it.
3. **Open questions #3 and #4 are already answered.** Baked takes DO contain sign flips
   — the 08-01 walk has 7 on the pelvis and flips on 12 finger bones — and the unroll
   pass is written and validated
   (`HIHO_TESTING&CALIBRATION_BLENDS/HIHO_quaternion_continuity_repair.py`). Root cause
   is our own bake's per-frame matrix decomposition (`bake_animation.py:59`), full story
   in `Z_JITTER_DIAGNOSIS_2026-08-04.md`. The sweep's recommendation — unroll
   automatically after every bake — is exactly the queued fix.
4. **On the cutoff table (§2.2) vs this session's measured cutoffs:** the sweep's table
   has cutoffs RISING toward the extremities (motion-content reasoning). The Winter
   residual analysis run on the actual walk take gave the OPPOSITE ranking (core ≈9 Hz,
   hands ≈5.2 Hz) — because in a walking take the hands only swing, and their enormous
   noise pushes the residual elbow down. Both are right: **optimal cutoffs are
   take-dependent**, which is exactly why the "Suggest Cutoffs" residual-analysis button
   (Stage 2 below) is the feature that matters, not any fixed table. Note ALL measured
   numbers from this session were taken on data that passed through the misconfigured
   pre-filter (item 1) — re-derive them after that fix lands.

---

# The research document (as delivered by the sweep)

## 0. Read this first: two things in your own pipeline change every number below

**Takeaway: your data arrives in Blender roughly half as filtered as FreeMoCap intends,
and that is almost certainly why Butterworth has felt like guesswork every time.**

### 0.1 The pre-filter is running at the wrong frame rate

Your vendored FreeMoCap already low-pass filters the 3D landmark positions before
anything reaches Blender. The actual filter lives in your conda environment at
`.../skellyforge/freemocap_utils/postprocessing_widgets/postprocessing_functions/filter_data.py`,
and it is a textbook zero-lag Butterworth (SciPy `butter` plus `filtfilt`, applied per
landmark, per axis, in position space).

The problem is the sampling rate it is told to assume:

```python
class PostProcessingParametersModel(BaseModel):
    framerate: float = 30.0
```

Nothing ever overwrites that value, and HIHO builds the parameter model without setting
it. So the filter is told "this footage is 30 frames per second" while the footage is 60.
The corner it actually applies sits up around 14 Hz instead of the intended 7 Hz. It is
doing roughly half the smoothing it was designed to do. Every take cleaned by hand in
Blender has been compensating for this.

This is a one-line fix and it should happen before tuning anything else, because it
changes what "noisy" means for the data.

### 0.2 The gap filler can teleport a landmark

Same package, `interpolate_data.py`. Gaps are filled with straight-line interpolation
with no length limit, and then any remaining holes (typically at the very start of a
take, before a landmark is ever seen) are filled with **the average position of that
landmark across the entire take**. A hand that was out of frame for the first thirty
frames gets parked at the middle of everywhere it ever went, then a straight line runs
from there to the first real reading. Filtering afterward smears that invented motion
into the surrounding second of animation.

Practical rule for now: trim the head of every take to the first frame where all
landmarks are actually seen, before filtering anything. Longer term this is a candidate
for a HIHO-side patch.

### 0.3 What this means for the rest of this document

The rig is baked from landmark positions that have already been low-pass filtered once
(badly parameterized, but filtered). So filtering again in Blender is a **second,
corrective pass**, not a first pass. That is fine, and it is actually the right place for
per-region work, because the pre-filter treats all 500-plus landmarks identically and
cannot know that a fingertip needs different handling from a hip.

---

# Q1: Per-region smoothing strength

## 1.1 Verdict, up front

**The theory is correct in its core claim and correct about the direction of the
gradient. It needs one structural correction: "smoothing strength" is not one dial, it is
two, and only one of them follows the gradient.**

- **How much noise you take out** (call it *amount*): follows the gradient exactly. Most
  at the extremities, tapering to almost nothing at the pelvis. Confirmed by this
  session's measurements, by the markerless-mocap literature, and by the geometry of how
  rotations are derived.
- **Where you draw the line between "noise" and "real motion"** (the cutoff frequency):
  runs the *other* way in general. Fingers and hands genuinely move faster than a pelvis
  does, so their line has to sit higher, not lower. A single "more smoothing at the
  extremities" dial that lowers the cutoff on hands is precisely how you get dead,
  rubbery hands. (See verification note 4: on slow takes the measured optimum can
  invert — the point is the two dials are independent.)

Get those two apart and the idea is not just sound, it is better than what most
commercial packages ship.

## 1.2 Is this recognized prior art? Yes, in three separate forms

**Takeaway: nobody in the consumer or open-source world ships this as a clean,
physically-motivated tool. The pieces exist, scattered.**

**Form 1: explicit per-body-part filter strength.** iPi Soft is the one commercial
markerless package that ships a per-body-part strength control. Their
[Automatic Refinement and Filtering docs](https://docs.ipisoft.com/Automatic_Refinement_and_Filtering)
state: "You can configure Jitter Removal options for specific body parts."

The honest complication: **iPi recommends the opposite gradient** — "slightly more
aggressive Jitter Removal for torso and legs," less for "sharp motions like martial arts
moves." That does not refute the theory, and the reason is the whole point of 1.1: iPi's
advice is a statement about *headroom*, not about *noise level*. The torso is slow and
heavy, so there is almost no real high-frequency content to damage, which means the dial
is safe to crank. Hands move fast, so cranking it there destroys motion. That is the
cutoff axis in disguise. It says nothing about where the noise actually is.

**Form 2: per-node application in the professional packages.** MotionBuilder filters
(Butterworth, Smooth, Key Reducing, Peak Removal, Gimbal Killer, Resample, Unroll
Rotations, Constant Key Reducer) are applied to whatever is selected
([Filters window](https://help.autodesk.com/cloudhelp/2017/ENU/MotionBuilder/files/GUID-B1768B7C-9469-485D-9636-707205CEB4C7.htm)).
Working animators use this exactly as proposed:
[MoCap Online's cleanup guide](https://mocaponline.com/blogs/mocap-news/motionbuilder-motion-capture-guide)
describes using Butterworth "selectively, for example on a bouncing root or noisy
rotations, rather than flattening everything." Vicon Shogun exposes
[object presets](https://help.vicon.com/space/Shogun16/13341237) per object, overriding
globals.

So the technique is standard practice. What is missing everywhere is the automation:
nobody hands you a pre-authored gradient and says "here is where the noise lives on a
human body."

**Form 3: the compression world, where it is formalized and reversed.** See 1.4 — this
is the direct answer to the lever-arm question.

**Form 4: adaptive filters, which do this automatically per-moment instead of
per-region.** The [One Euro filter](https://dl.acm.org/doi/10.1145/2207676.2208639)
(Casiez, Roussel, Vogel, CHI 2012) raises its own cutoff when a point is moving fast and
lowers it when nearly still — a per-joint, per-frame version of the same insight. Its
limitation is that it is causal (built for real-time, so it lags), which matters less
than expected because it could run forward and backward like a Butterworth to cancel the
lag.

## 1.3 Why the extremities really are noisier: the divide-by-bone-length effect

**Takeaway: the 37 percent figure on hand rotation is not a MediaPipe failure. It is
mostly geometry, and it would happen with perfect landmarks and a slightly shaky
camera.**

Cameras measure **positions**. The rig needs **rotations**. A bone's rotation is worked
out from where its two ends are — "the direction from this landmark to that landmark."

Each landmark has a small wobble, roughly the same size everywhere (same cameras, same
solver). What that wobble does to the *angle*:

- A **thigh** is around 40 cm long. A few millimetres of wobble barely tilts a 40 cm
  stick. The angle comes out clean.
- A **finger segment** is around 2.5 cm. The *same* wobble tilts that stick wildly. The
  angle comes out filthy.

Rule of thumb: **rotational noise is roughly positional noise divided by bone length.**
Short bone, big angular noise. This is arithmetic, not a bug.

This is exactly the measured monotonic gradient, landing where predicted: worst at
fingers and toes, best at the pelvis. Pelvis translation is the cleanest thing in the
file for four compounding reasons: it is a *position* (never divided by a bone length),
it is the midpoint of two hip landmarks (averaging cuts the wobble), the hips are large
and rarely occluded, and six cameras triangulating a well-seen point is the best case
the rig offers.

The independent literature agrees. A 2026 study on
[biomechanical reconstruction from multiview markerless mocap](https://arxiv.org/html/2502.06486v1)
reports uncertainty "increases systematically from proximal to distal joints" and "the
parameters of the distal arm are poorly tracked" without hand-specific models. A
[review of markerless clinical gait methods](https://peerj.com/articles/12995/) notes
"relatively poor reliability in measurements of the ankle joint" and that the worst
keypoint detections are toes and heels.
[Evaluations of MediaPipe for sign language](https://arxiv.org/pdf/2604.24609) find
temporal jitter concentrated "particularly in the hand subset."

## 1.4 The lever arm: the crux, answered

**Takeaway: the lever arm does NOT argue for smoothing parents more. It argues that the
parent's setting is the one you are least allowed to get wrong. Weak, but chosen with
care, not weak because you stopped caring.**

The question: since a small rotation error at the shoulder becomes a big positional
error at the fingertip, do parents need *more* smoothing?

**Step one: filtering does not remove error. It trades one kind for another.** A
low-pass filter takes away high-frequency error (jitter) and gives back low-frequency
error (peaks rounded, sharp changes softened). "Smooth harder" always means "accept more
shape error in exchange for less jitter."

**Step two: the lever arm amplifies both kinds equally.** Whatever error is left at the
shoulder — jitter you failed to remove, or shape damage you introduced — gets multiplied
by the reach of the arm on its way to the fingertip. The lever arm is a reason to be
*accurate* at the parent, in both directions at once.

**Step three: what decides it is the noise ratio, and that is where the gradient wins.**
Parents arrive nearly clean (1.3), so aggressive filtering there buys almost nothing
while risking real shape damage that gets multiplied down the whole chain. Extremities
arrive filthy, there is a great deal to remove, and damage stays local because nothing
hangs off a fingertip.

**Conclusion: smooth the extremities more. The lever arm reinforces this, but adds a
discipline: the parent's dial is near zero because the parent has the tightest tolerance
in the rig, and the correct response to a tight tolerance is a light, precise, verified
touch.**

**The formal version exists.** Riot Games hit the identical problem in animation
compression — "how much error may I introduce at each joint." From
[Compressing Skeletal Animation Data](https://www.riotgames.com/en/news/compressing-skeletal-animation-data):
error "accumulates as the animation affects segments farther from the root joint," so
they "tighten the error threshold if the joint has a longer chain of descendants." Their
rule:

> an end effector uses given margins as they are, but its parent halves them, its
> grandparent divides them by three, and so on

That is the same statement seen from the other end: at the root you may disturb the data
least, therefore you filter it least. Riot arrived at divide-by-successive-integers
purely from the amplification geometry, and report it fixed their most visible artifact
— foot sliding. A defensible, citable falloff shape for free (do not adopt the exact
numbers blindly; their problem is compression error, ours is measurement noise — the
*shape* is what is well-motivated).

## 1.5 The one correction: strength and cutoff are different dials

**Takeaway: build two sliders, not one. Conflating them is the single mistake that would
sink this tool.**

References on cutoff by body part:
[MoCap Online](https://mocaponline.com/blogs/mocap-news/mocap-data-cleanup-workflow):
"typical cutoff: 6 to 12 Hz for body motion, higher for fingers." A wheelchair-propulsion
study found
[optimal cutoffs from about 5.5 to 9.8 Hz across body segments](https://www.rehab.research.va.gov/jour/02/39/3/cooper.htm).
Physiological finger tremor sits [at 8 to 12 Hz](https://pubmed.ncbi.nlm.nih.gov/943474/)
— real motion a capture may see, above where a torso cutoff would ever sit.

The clean way to hold both ideas at once:

| Dial | What it answers | Direction across the body |
|---|---|---|
| **Cutoff frequency** | "Above what speed of wiggle is nothing real happening here?" | Set by the REAL motion content of the region and the take |
| **Amount / blend** | "Of the stuff above that line, how much do I actually take out?" | Rises toward the extremities — that is where the noise is (the gradient) |

In one sentence: **the cutoff is where you draw the line, the blend is how much you
trust the line.** Blender's Butterworth operator exposes both (`cutoff_frequency` and
`blend`).

## 1.6 Should you smooth the root or pelvis at all?

**Takeaway: leave root translation alone by default. If anything, treat the up-down
channel separately from the travel channels and never touch travel.**

1. It measures clean — filtering a clean signal can only subtract.
2. It is the extreme case of the lever-arm argument — root error moves the entire
   character.
3. It is the classic cause of foot skate — the feet were solved against the unsmoothed
   body path.
4. It carries all the timing — rounding a sharp direction change reads as the whole
   performance going soft.

One exception worth testing: **vertical bounce** (height is the root channel most likely
to carry genuine triangulation noise; a gentle low-blend pass on Z only is a reasonable
experiment). And **pelvis rotation is a different question from pelvis translation** —
pelvis yaw is derived from the short left-right hip baseline, so by the
divide-by-bone-length rule it is probably the noisiest thing about an otherwise pristine
pelvis. (Extrapolated, cheap to check — open question.)

## 1.7 The weight-paint metaphor: what the actual authoring UI should be

**Takeaway: bone collections as tiers, pre-authored by HIHO, with an auto-seed button
that reads BONE LENGTH rather than hierarchy depth. Not per-bone number fields, not a
depth-based falloff.**

- **Option A, per-bone custom property:** truly continuous, but sixty-three invisible
  number fields is the worst possible interface for an artist. Fine as the storage
  format underneath, not the front door.
- **Option B, bone collections as tiers (RECOMMENDED):** Blender 4+ replaced bone layers
  with [Bone Collections](https://docs.blender.org/api/current/bpy.types.BoneCollection.html)
  — nameable, nestable, already how Rigify organizes rigs. Ship four or five collections
  with the HIHO rig (`SMOOTH_None` … `SMOOTH_Max`). Reassigning a bone = dragging it
  between collections. Tiers show in the armature panel with zero custom UI. Discrete
  beats continuous here: five tiers is enough resolution for a body and is far easier to
  teach and debug.
- **Option C, auto-falloff from hierarchy depth:** gets the body wrong (the head is deep
  but clean; upper arm and thigh sit at similar depths but behave differently).
- **Option C-prime, auto-seed from BONE LENGTH (build this):** section 1.3 established
  the physical driver is bone length, and bone length is sitting right there in the
  armature. Sort bones by length; short bones fall into heavy tiers, long into light.
  The head comes out right, fingers come out right, feet come out right. One button,
  grounded in the actual mechanism, artist can override anything.

---

# Q2: A repeatable method for removing markerless noise in Blender

## 2.1 The Blender toolbox: what each tool is and when it is the right one

**Takeaway: Butterworth Smooth is the correct primary tool and almost everything else on
the list is for a different job.**

(Parameter names/behaviors from the Blender 5.2 manual and API;
[editing docs](https://docs.blender.org/manual/en/latest/editors/graph_editor/fcurves/editing.html).)

- **Butterworth Smooth** (Key → Smooth → Butterworth): "ideal for smoothing large
  amounts of data because it preserves the peaks." Params: **Frequency Cutoff (Hz)**
  (with an "implicit maximum … at half the sample rate" — Nyquist, spelled out),
  **Filter Order** (steepness; 4 is sane), **Samples per Frame**, **Blend** ("between the
  original curve and the smoothed one" — **the per-region strength dial, and it already
  exists**), **Blend In/Out** (eases back to the original at the selection borders). Two
  implementation facts that matter: it is **zero-phase** (run forward then backward per
  [the original patch](https://projects.blender.org/blender/blender/pulls/106952)) so it
  introduces **no lag**, and the double pass makes the dial read slightly stronger than
  the typed number (the biomechanics
  [dual-pass correction](https://biomch-l.isbweb.org/forum/biomch-l-forums/general-discussion/29899-filtering-of-the-inverse-kinematics-results)
  — small enough to ignore, just know the dial is a touch stronger than it reads).
- **Gaussian Smooth**: a weighted blur (Factor, Sigma, Filter Width). Localized touch-ups
  on a hand-selected passage. Not frequency-aware; not the primary tool.
- **Smooth (Legacy)** (Alt-O): the manual itself warns the algorithm is crude and strong.
  This is the "Smooth" worth replacing. **Avoid.**
- **Clean Keyframes**: deletes redundant keys; "likely to change the shape." Use only to
  strip dead channels after a bake so the Graph Editor is navigable.
- **Decimate**: **Error Margin mode is the correct mode for mocap** (a guarantee, not a
  percentage). Destructive; last step or never. Riot's per-joint tolerance rule applies
  here too: tighter margins on parents.
- **Bake Keyframes / Keys ↔ Samples**: baked mocap already has a key per frame; whether
  Butterworth works on sampled curves is unconfirmed — assume keys.
- **Discontinuity (Euler) Filter**: Euler channels only. Irrelevant on a quaternion rig —
  but the *category* of problem is exactly the sign-flip bug, and the quaternion
  equivalent is the HIHO unroll pass (see verification notes).
- **Smooth F-Modifier** (`FModifierSmooth`): Gaussian, **non-destructive and live**, with
  Sigma, Filter Width, plus inherited **Influence** and frame-range restriction. Catches:
  must be FIRST in the modifier list, incompatible with Cycles modifier, and the manual
  warns it is resource-heavy across many F-curves (63 quaternion bones is many).
- **Noise F-Modifier**: ADDS noise. Useful only for putting a little life back into an
  over-smoothed take — a legitimate artistic move.
- **NLA strip modifiers**: "Modifiers affecting **all** the F-Curves in the referenced
  Action." **This one line kills the NLA framing** — structurally incapable of
  per-region. Strip `influence`/blends remain useful for whole-take dialing and
  crossfades.
- **Bake Action**: Visual Keying on, **Clean Curves OFF** for mocap; also the bridge that
  makes an F-Modifier permanent.
- **Motion Paths**: the best free verification instrument — jitter shows as a fuzzy or
  scalloped path, over-smoothing as a glassy one. Before and after every pass.

| Tool | Destructive? | Primary use |
|---|---|---|
| Butterworth Smooth | Yes | Main noise removal |
| Gaussian Smooth | Yes | Local touch-up |
| Smooth (Legacy) | Yes | Avoid |
| Clean / Decimate | Yes | Post-bake tidy / final reduction |
| Euler Filter | Yes | N/A on quaternions |
| Smooth F-Modifier | **No** | Live per-curve option |
| Noise F-Modifier | **No** | Adding life back |
| NLA strip modifiers | **No** | Whole-take dialing only |
| Bake Action | Yes | Committing modifiers |
| Motion Paths | No | Verification |

## 2.2 How to choose a cutoff instead of guessing

**Takeaway: residual analysis (Winter) is a rigorous, teachable method; ten minutes on
one representative curve per region turns cleanup from a feeling into a defensible
number.**

The ceiling in artist terms: at 60 fps the fastest wiggle that can exist is 30 per
second, so 30 Hz is the absolute ceiling — and everything that matters in human motion
happens in roughly the bottom fifth of that range. The performance and the noise live in
almost completely separate parts of the range; the job is finding the line.

[Winter's residual analysis](https://engineeredathletics.com/2020/08/31/determining-filter-cutoff-frequency-with-residual-analysis-for-variable-biomechanics-applications/),
in plain English: filter one representative channel at a whole range of cutoffs; for
each, measure how far the curve moved (the residual); plot residual against cutoff. Near
the top, nothing changes. Coming down, the residual rises along a **straight line** —
noise is spread evenly, so every extra Hz removed costs the same: pure noise removal.
Then the line **bends upward** — real motion is piled up at the low end, and the bend is
the moment the filter starts eating the performance. **The elbow is the answer.**
(Formally: extend the straight section back to the axis to find the noise level; the
optimum is where the actual residual equals it.)

The artist mapping: it is the same move as pushing a setting until grain stops being
grain and starts being picture — measured instead of eyeballed.

Published motion-content anchors (all marker-based, adjust upward for markerless noise):
[walking = 6 Hz standard](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC3916920/) since
Winter; whole-body activity
["no useful signal power above 6 Hz"](https://www.rehab.research.va.gov/jour/02/39/3/cooper.htm)
with per-segment optima 5.5–9.8 Hz; reaching fundamentals under 2 Hz; finger tremor
[8–12 Hz](https://pubmed.ncbi.nlm.nih.gov/943474/) with a mechanical peak
[at 20–25 Hz](https://pubmed.ncbi.nlm.nih.gov/11018494/); practical animation guidance
[6–12 Hz body, higher for fingers](https://mocaponline.com/blogs/mocap-news/mocap-data-cleanup-workflow);
IMU practice [5–20 Hz by dynamism](https://www.mdpi.com/1424-8220/21/13/4580).

Generic starting table for 60 fps six-camera markerless (verify per take with residual
analysis — see verification note 4; these are motion-content priors, not measurements):

| Region | Cutoff (Hz) | Blend |
|---|---|---|
| Root translation, travel (X/Y) | do not filter | 0 |
| Root translation, height (Z) | 5 | 0.3 |
| Pelvis / spine rotation | 5 | 0.3 |
| Chest, neck, head | 6 | 0.4 |
| Upper arm, thigh | 6 | 0.4 |
| Forearm, shin | 7 | 0.6 |
| Hand, foot | 8 | 0.8 |
| Fingers, toes | 10 | 1.0 |

The two columns move for different reasons: cutoff tracks how fast the real motion is;
blend tracks where the noise is. Fast take: raise cutoffs by a third, keep blends. Slow
take: lower them. If the whole rig still shimmers, the answer is calibration and
lighting, not a lower cutoff.

Caveat, honestly flagged: residual analysis assumes evenly-spread noise. Occlusion
dropouts and solver failures are spikes, not noise — reject spikes first or the plot
distorts.

## 2.3 Order of operations, and why

**Takeaway: filtering goes late, gap-filling and spike rejection go early, contact
fixing goes after filtering, key reduction dead last. Getting the order wrong costs more
quality than getting the cutoff wrong.**

1. **Fix the capture** (calibration, light, coverage — existing doctrine).
2. **Gap fill** — before filtering (a filter rings across holes). FreeMoCap enforces
   this order internally. Watch the mean-fill behavior (§0.2).
3. **Spike/outlier rejection** — before filtering. **A spike is not noise, it is a wrong
   measurement**; a low-pass filter does not remove it, it SPREADS it into twenty
   slightly-bad frames. Anipose's median-compare approach is the model; HIHO's existing
   outlier-rejection design doc is this step.
4. **Rigid-body/bone-length enforcement** (`enforce_rigid_bodies.py`) — a constraint,
   not a filter; constraints beat filters where they apply.
5. **Filter positions** — the highest-value place to filter (measurements are
   independent; rotations are jointly constrained). This is where the frame-rate fix
   pays off most.
6. **Solve / bake to rotations.**
7. **Rotation continuity repair (unroll)** — non-negotiable, before any rotation
   filtering (see Z_JITTER doc).
8. **Filter rotations, per region** — the corrective pass; cleans what survived step 5.
9. **Foot contact fixing** — after filtering, because filtering is what breaks contacts.
10. **Root motion** — left alone by default.
11. **Key reduction** — last, Error Margin mode, only for hand-edit takes.
12. **Verify** — motion paths on a wrist and ankle + a locked-off camera render (viewport
    orbiting hides jitter; a locked camera does not).

Cross-check: iPi's documented order is tracking → cleanup → refinement → jitter removal
→ trajectory filtering → export; MoCap Online's is gaps → solve → filter → foot contact
→ hands → QA. No disagreement in the field about this order.

## 2.4 Filtering rotations correctly: the quaternion question

**Takeaway: the theoretically-wrong thing works fine at these noise levels, with exactly
one exception that will absolutely bite: sign continuity. Fix that, then stop
worrying.**

Filtering W/X/Y/Z as four independent curves is technically wrong (the four numbers must
keep unit length; Blender does not renormalize). But Daniel Holden's
[Filtering, Convolutions, and Quaternions](https://www.theorangeduck.com/page/filtering-convolutions-quaternions)
— the definitive practical treatment — says naive per-channel filtering "is going to
work 99% of the time" provided: sign-continuous, densely sampled relative to motion
speed, no sudden jumps. At 60 fps with small-amplitude noise, all three hold.

**The non-negotiable: sign continuity (unrolling).** A quaternion and its negative are
the same pose; a flip is invisible until a filter averages across it and produces
near-zero — "I smoothed the mocap and one bone snapped to a crazy angle" is a sign
problem smoothing exposes, not a smoothing problem. (Answered for HIHO: flips confirmed,
unroll written, root cause in the bake — verification notes.) MotionBuilder ships
"Unroll Rotations" as a filter, which tells you how standard this is.

Upgrades if ever wanted: **log/tangent-space filtering** (SLERP-equivalent averaging,
the "correct" version); **swing-twist separation** — genuinely interesting because
forearm/wrist TWIST is nearly invisible to a landmark solver and is likely the noisiest
single component in the arm — filtering twist harder than swing is the per-region idea
one level finer; **filter positions instead** (step 5), which sidesteps the whole
question.

## 2.5 Foot sliding and contact preservation

**Takeaway: filtering breaks foot plants by design (a plant is a flat line with hard
corners; filters round corners). Fix contacts after filtering — and the tool already
exists, vendored.**

Standard fix: detect contacts (height+velocity thresholds; learned detection like
[UnderPressure](https://github.com/InterDigitalInc/UnderPressure) exists but is
overkill), then pin with eased edges.

**Already vendored and underused:**
`vendor/ajc27_freemocap_blender_addon/blender_ui/operators/animation/foot_locking/`
implements height-threshold locking on the marker empties, pre-bake, with thoughtful
controls: `z_threshold` (0.02 m), `frame_window_min_size` (10, anti-flicker),
attenuation counts (quadratic ease in/out), toe/heel targeting, `lock_xy_at_ground_level`
(with an honest sticky-feet warning), `knee_hip_compensation_coefficient`, and
`compensate_upper_body` — that last pair is the lever-arm principle running the other
way: an ankle correction must be paid for up the chain, and these decide whether the
knee or the whole body pays.

**Recommendation: surface this in the HIHO panel as standard step 9.** It works on
empties (pre-bake), so the pipeline order is: filter positions → foot-lock positions →
bake → per-region rotation smoothing (gentle on the leg chain, so plants should survive
— assumption flagged for live test).

Also vendored: `limit_markers_range_of_motion` and `set_bone_rotation_limits` —
constraint-based cleanup; a knee that cannot bend backwards will never jitter backwards.

## 2.6 Ecosystem scan

**Takeaway: nothing out there does what is wanted. The free options are thin; the
closest commercial match is paywalled and unusable under the zero-paid-deps rule.
Building this is justified.**

Free/open: Blender's Butterworth (genuinely good, underappreciated), Motion Paths,
FModifierSmooth, ajc27's foot locking + limits (vendored), skellyforge's position
Butterworth (live, currently misconfigured — §0.1),
[QuickMocap-BlenderAddon](https://github.com/vltmedia/QuickMocap-BlenderAddon) (crude
per-bone-name smoothing — prior art for the interface question),
[SnowMocap](https://github.com/liaochikon/SnowMocap) (camera-array mocap with per-bone
smoothing parameters — closest existing architecture, worth reading),
[UnderPressure](https://github.com/InterDigitalInc/UnderPressure) (check license).

Paid, flagged clearly, unusable: **Rokoko Studio's smoothing** (Plus/Pro plans only; the
free Blender plugin is streaming/retargeting only), **Mocap Bone Lock** (Blender Market;
ajc27 free equivalent exists), **MotionBuilder / Vicon Shogun / Blade / iPi / Captury /
Xsens / Noitom** (reference-only).

---

# (a) Recommended default cleanup recipe (60 fps, six cameras)

0. Calibrate this session (unchanged doctrine).
1. **[Fix the framerate handoff]** so the position pre-filter knows 60 fps. One line.
   First, before tuning anything.
2. Position pre-filter at 7 Hz / order 4 once actually at 60. A broad first pass.
3. **[Outlier rejection]** before the pre-filter (existing design doc).
4. Trim take heads to the first all-landmarks-seen frame (mean-fill dodge).
5. Bake (Visual Keying ON, Clean Curves OFF).
6. **Duplicate the baked action; keep `TAKE_raw`, work in `TAKE_clean`** — cheap
   non-destructive re-dialing without any modifier.
7. **[Unroll quaternions]** — automatic, silent, always (the bone-snap insurance).
8. Clean Keyframes lightly, only to strip never-moving bones.
9. **Per-region Butterworth** per the tier table (order 4; only Cutoff and Blend vary).
   Root travel excluded.
10. Check: motion paths on one wrist + one ankle; locked-camera render at speed.
11. Foot locking (ajc27 operator, on empties, with a re-bake) — or in its native
    pre-bake slot with the ordering caveat.
12. Root: alone. If hips shimmer vertically: Z only, 5 Hz, blend 0.3.
13. (If needed) Decimate, Error Margin, parents tighter.
14. (If too clean) whisper of Noise F-Modifier on a few extremity channels — a
    legitimate artistic move, not a failure.

# (b) Verdict on the per-region idea

**Sound. Better-motivated than what any free tool ships. Needs one structural change and
one discipline.**

Right: gradient direction (matches the data), physical mechanism (noise ÷ bone length),
independent literature agreement, lever-arm reinforcement, and a formalized cousin
(Riot's per-joint error budgets) providing a citable falloff shape.

**The structural change: split "strength" into two dials** — cutoff (where the line is)
and blend (how much you trust the line). A single conflated dial would kill the hands.

**The discipline: parents are the tightest tolerance in the rig, not the least important
part.** Weak settings there, chosen carefully and verified.

**Build order:**
- **Stage 0, no code, one session:** select bones by region, "Only Show Selected" in the
  Graph Editor, run Butterworth by hand with four cutoff-and-blend pairs on one real
  take. The entire idea, tested today, zero engineering.
- **Stage 1, the tool:** `Smooth by Region` operator driven by 4-5 bone collections
  created at bake time, seeded from bone length, running the existing Butterworth once
  per tier. No new filter math. Non-destructive via `TAKE_raw`/`TAKE_clean`.
- **Stage 2, the research feature:** a "Suggest Cutoffs" button running residual
  analysis per tier. The step that turns "I felt it out" into a number with a method —
  and the part that belongs in a dissertation.

**Do not build it as an NLA strip modifier** (uniform across the action by API design).
The instinct about *where* it lives was the one part that does not survive contact with
the API; the instinct about *what* it does survives intact.

# (c) Open questions / live tests

1. ~~Confirm the framerate bug on a real take~~ — **CONFIRMED in code on the live path**
   (verification note 1); the reprocess-and-compare is still worth doing as the visible
   proof.
2. Measure pelvis ROTATION noise separately from translation (prediction: yaw is the
   noisy part, short hip baseline).
3. ~~Does `pose.quaternions_flip` unroll a timeline?~~ — **No** (verification note 2).
   HIHO implements its own; done.
4. ~~Do baked takes contain sign flips?~~ — **Yes, 7 pelvis + 12 fingers on 08-01**
   (verification note 3).
5. Residual analysis per tier on a real take — partially done this session on the walk
   take; re-derive after the framerate fix, and check whether the elbow is sharp enough
   to read on markerless data.
6. Butterworth on sampled (vs keyed) F-curves — untested.
7. Does per-region rotation smoothing after foot-locking re-break plants? (Assumed no —
   long bones, low blend on the leg chain.)
8. Riot's divide-by-integers falloff vs a bone-length-derived falloff on real data.
9. FModifierSmooth performance at 63 quaternion bones (manual warns it is heavy) — if
   fast enough, a live non-destructive preview becomes the nicer interface.
10. Forward-backward One Euro as an emergent alternative to tiers (legibility argues for
    tiers in a teaching tool; preference, not finding).
11. Swing-twist separation on the forearm (twist is the invisible-to-solver component).
12. Is markerless triangulation noise actually spectrally flat? (Residual analysis
    assumes it; check on the plot from item 5.)
13. Does the head-trim workaround (§0.2) need to become a real patch?
14. Pre-filter and per-region pass should be co-designed: once the pre-filter runs
    correctly at 60 fps, all the measured blends likely come down. **Re-derive the
    measured tables after the framerate fix lands.**

---

**Sources** (as delivered by the sweep): Blender 5.2 manual & API (F-curve editing,
graph operators, PR #106952, PR #105635) · Riot Games "Compressing Skeletal Animation
Data" · Daniel Holden "Filtering, Convolutions, and Quaternions" · iPi Soft docs ·
Autodesk MotionBuilder docs · Vicon Shogun docs · MoCap Online cleanup guides · Casiez
et al. 1€ Filter (CHI 2012) · SmoothNet (ECCV 2022) · Mourot et al. UnderPressure ·
arXiv 2502.06486 (markerless confidence intervals) · PeerJ 12995 (markerless clinical
gait) · arXiv 2604.24609 (MediaPipe sign-language evaluation) · Winter residual analysis
(Engineered Athletics explainer; Biomch-L dual-pass thread) · PMC 3916920 · VA rehab
39/3 (wheelchair filter selection) · MDPI Sensors 21(13):4580 · PubMed 943474, 11018494
(finger tremor) · Anipose tutorial · Rokoko product/pricing pages · QuickMocap /
SnowMocap / Open Mocap GitHub repos. Local files: `external/process_take.py`,
`core/enforce_rigid_bodies.py`, vendored ajc27 foot_locking, conda-env freemocap 1.8.2
(`post_processing_parameter_models.py`, `post_process_skeleton.py`) and skellyforge
(`filter_data.py`, `interpolate_data.py`).
