# Hand Rotation Noise — Research Doc (V2 Item 1.b)

> ⚠️ **Cross-doc note — 2026-05-01:** This doc was written without first finding [`HAND_SIDE_REF_RESEARCH.md`](HAND_SIDE_REF_RESEARCH.md) (dated 2026-04-30, an earlier session's deep-dive on Lever A specifically). That doc has the canonical sign analysis showing `palm_normal` flips between hands without correction while `across_palm` (= `pinky_MCP - index_MCP`) does not. Shipped v2.0.1 uses `across_palm` per the earlier doc. The Lever A math sketch in §"Lever A" of THIS doc proposed `palm_normal` and is therefore *suboptimal as written* — read it as background on the broader three-lever framing, not as the canonical implementation recipe.

Pre-code research per `feedback_research_doc_first_pattern`. Written 2026-05-01 against the day8d benchmark. Goal: pick the right first lever to attack fingertip rotation noise, ship one focused change, measure, decide on the next move.

This doc has three layers:
1. **TL;DR** — what we're doing and why, in plain English.
2. **Diagnosis** — what's actually causing the noise (multiple root causes, distinct from each other).
3. **The three levers** — each one's *what / why / math / cost / risk / predicted gain*. Then a recommendation.

---

## TL;DR (plain English)

When you record a take in V2, the puppet's fingertips wiggle even when your real fingertips are still. The body, arms, and palm don't have this problem — only the fingers, and especially the very tips. Measurement: fingertips wiggle about **300 times more** than body bones from one frame to the next. That's not subtle.

The wiggle isn't one problem — it's at least three problems stacked on top of each other:

1. **Tiny pixels.** MediaPipe's fingertip dots sit on just a few pixels in the camera image. A small mistake in pixel-space becomes a big mistake in 3D angle.
2. **Compounding chain.** Each finger bone's angle depends on the previous bone's tail position. So noise at the knuckle gets passed forward to the middle, and to the tip — by the time you reach the fingertip, you're seeing piled-up noise from three joints.
3. **A geometric fluke.** When a bone points nearly straight up (or down), the math we use to figure out its "twist" picks an arbitrary direction each frame. Tiny noise → arbitrary twist → frame-to-frame flicker. Body bones avoid this by passing a stable "sideways" reference. Hand bones don't, today.

The third one is fixable cleanly without changing anything about how MediaPipe works — we just need to compute and pass a stable hand-side reference. That's the recommended **first lever**: **palm-normal as `side_ref`**.

The first two are harder. We can soften them with smoothing (heavier for fingertips than for palms), but smoothing trades crispness for stability — heavy smoothing makes finger flicks feel rubbery. So we ship the geometric fix first, re-measure, and only escalate to smoothing if the residual noise is still too much for the rig.

---

## Diagnosis — Where the Noise Comes From

### Measurement baseline (from day8b post-install diagnostics)

Mean frame-to-frame quaternion delta, by bone class:

| Bone class                              | Δq         |
|-----------------------------------------|------------|
| pelvis / chest                          | 0.001-0.004|
| upper / lower arm                       | 0.02-0.03  |
| palm + thumb base                       | 0.08-0.10  |
| thumb tip (`.03`)                       | 0.19       |
| index/middle/ring/pinky tips (`.03`)    | **0.30-0.44** |

Fingertip Δq is roughly **100-300× body bones**. Even palm/thumb base sits at 20-100× body. The hand is a different noise regime than the body.

### Root cause taxonomy

The noise has multiple distinct sources. They don't have a single fix.

#### 1. Tracker-side: small pixel footprint (MP intrinsic)

MediaPipe's fingertip landmarks (indices 4, 8, 12, 16, 20) cover few pixels in the camera image. Per-frame pixel measurement uncertainty in image space is roughly constant — but a pixel error on a small thing rotates that thing more than a pixel error on a big thing. So fingertips have higher angular uncertainty than knuckles, even before any chain effects.

**Mitigations:** software smoothing (lever B). Cannot be eliminated tracker-side without higher-resolution input or a different model.

#### 2. Tracker-side: low confidence on tip landmarks (MP intrinsic)

MediaPipe's hand model fits palm structure first (the model has explicit palm anchors) and infers tips by extrapolation. Per-landmark visibility scores reflect this — palm/MCP landmarks have higher confidence than tip landmarks. The model is more confident in its knuckle predictions than its fingertip predictions.

**Mitigations:** software smoothing (lever B), or confidence-weighted drive (out of scope here, possible future work).

#### 3. Chain inheritance (geometric, V2-side)

Each finger bone's rotation in V2 is computed from a vector that depends on the previous bone's tail position. So noise at `f_*.01` propagates into `f_*.02`'s direction calculation, which propagates into `f_*.03`. By the time we reach `.03`, we're integrating noise from three joints.

This is why `.03` is so much noisier than `.01`-`.02` — even if every joint had the same per-frame noise individually, the chain compounds it.

**Mitigations:** root-fixing chain noise requires a fundamentally different rig drive (e.g., absolute world positions per joint instead of segment-by-segment vectors). That's V2.x territory. For now, mitigations of #1 and #2 partially address this by reducing the input noise.

#### 4. Geometric ambiguity in `to_track_quat('Y', 'Z')` near vertical (V2-side, fixable)

`_drive_bone_segment` falls through to `to_track_quat('Y', 'Z')` for hand bones because no `side_ref` is currently passed. This Blender API behavior:

- Given a target direction (the vector from bone head → tail), produces a quaternion that aims bone-Y at that direction
- For "twist around bone-Y" (the roll), it picks an axis perpendicular to bone-Y by snapping bone-Z to world-Z (or world-X if bone-Y is parallel to world-Z)
- **The fallback is degenerate when the bone direction is parallel to world +Z or -Z** — Blender picks an arbitrary axis perpendicular to bone-Y

For a finger pointing nearly straight up, the bone direction wobbles by tiny amounts due to MP noise. That tiny wobble can flip the fallback's choice of perpendicular axis from one frame to the next, producing visible **roll flicker** that has nothing to do with how the kid is actually moving their finger.

This is the root cause that day7e fixed for body bones via `side_ref=hip_lateral`. Hand bones inherited the un-fixed version.

**Mitigations:** pass a stable `side_ref` to hand bone drives. THIS IS LEVER A.

#### 5. No `side_ref` for hand bones (V2-side, root cause of #4)

Body bones in `apply_landmarks_to_rig` pass `side_ref=hip_lateral` to `_drive_bone_segment` for the 12 near-vertical bones. Hand bones don't pass anything, so they fall through to (4) above.

The fix is structural: compute a stable hand-side reference from landmarks MediaPipe does report stably (wrist + MCP joints), pass it to the hand bone drives.

### What the diagnosis tells us about prioritization

- Causes 1-3 are tracker-side or compounding — software smoothing helps, but trades latency / crispness for stability
- Causes 4-5 are V2-side and CORRECTLY-FIXABLE — adding `side_ref` removes the geometric ambiguity without ANY tradeoff against latency or crispness
- The right first move is the cause we can fix without tradeoffs. **Then re-measure** to see how much of the residual noise is genuinely from causes 1-3 vs. how much was being amplified by the geometric ambiguity.

---

## The Three Levers

### Lever A — Palm-Normal as `side_ref` (RECOMMENDED FIRST)

**What it does in plain English:** Computes a stable "out of the back of your palm" direction for each hand, passes it as the side reference for the hand bones' rotation math. Hand bones stop flickering when they point near-vertical because the math now has a non-degenerate axis to anchor against.

**The math:**

For each hand, compute three palm-frame basis vectors from MP landmarks 0 (wrist), 5 (index MCP), and 17 (pinky MCP):

```
wrist        = landmarks[0]
index_mcp    = landmarks[5]
pinky_mcp    = landmarks[17]

palm_aim     = ((index_mcp + pinky_mcp) * 0.5 - wrist).normalized()  # forward through palm
palm_x       = (pinky_mcp - index_mcp).normalized()                  # lateral across palm
palm_normal  = palm_x.cross(palm_aim).normalized()                   # dorsal direction (back of hand)
```

`palm_normal` is the stable side reference. Pass it as `side_ref=palm_normal` (with a sign flip for the right hand, mirroring how `hip_lateral` works for body L/R) to all 19 hand bone drives per hand in `_drive_bone_segment`.

**What it fixes:**
- Roll instability on thumb base + finger bases (root cause #4)
- Fingertip orientation flicker that was caused by parent-chain roll inheritance (chain effect of #4 propagating through #3)
- Open Issue 1.c (thumb-joint orientation weirdness) — free fix as a side effect

**What it does NOT fix:**
- Direct pixel-noise on fingertip POSITIONS (root causes #1, #2 — those need lever B)
- Position-noise propagation (root cause #3 — V2.x territory)

**Cost:**
- ~10 lines added in `apply_landmarks_to_rig`: compute palm basis once per hand per frame
- ~20 lines modifying hand bone drive calls in `core/receiver.py` to pass `side_ref=palm_normal_L` or `palm_normal_R`
- Zero new compute in sender (everything stays receiver-side)
- Zero new dependencies
- Zero latency cost

**Risk:**
- Palm basis itself may have its own noise — wrist (lm 0) sometimes jitters. NEEDS measurement: log palm_normal frame-to-frame variance and confirm it's stable enough to serve as `side_ref`. If palm_normal Δ is itself >0.05, this lever's value is reduced.
- **Degenerate case: palm flat-on to the camera.** When the palm faces the camera directly, `palm_aim` is nearly parallel to the camera's Z axis, so `palm_normal = palm_x.cross(palm_aim)` is nearly perpendicular to the screen plane. Math is fine in that case. The actual degenerate case is when the kid's wrist, index_MCP, and pinky_MCP are colinear (e.g., hand edge-on to camera with fingers pressed together). Should never happen anatomically. Add a length check on the cross product anyway and fall back to previous-frame palm_normal if degenerate.
- **Open question: should the thumb use the same `side_ref` as fingers?** Anatomically, the thumb's natural "side" axis isn't the palm normal — the thumb rotates around its own axis quite independently. May need a separate thumb-specific side_ref derivation, or just accept that thumb still has some roll noise. Test empirically post-shipment.

**Predicted improvement:**
- Palm + thumb base (currently 0.08-0.10): expect drop to 0.02-0.04 (closer to arm noise levels). The roll-fallback was the dominant noise source for these bones.
- Finger bases (`f_*.01`): expect drop from contributing chain to ~50% of current level
- Fingertips (`.03` at 0.30-0.44): expect modest drop, maybe to 0.15-0.25, because their noise is dominated by position noise (causes #1, #2), not roll choice. **The post-shipping measurement will tell us how much of the tip noise was being amplified by upstream roll-fallback choice — that number is the key data point that decides whether lever B is needed at all.**

### Lever B — Heavier One Euro on Tip Landmarks Specifically

**What it does in plain English:** MediaPipe's hand landmarks already pass through a One Euro filter on the sender side — that's an adaptive smoothing filter that cuts noise more aggressively when the hand is still and less aggressively when it's moving fast. Today every landmark uses the same filter settings. This lever splits the filter pool: tip landmarks get heavier smoothing (more cut, more lag), palm landmarks keep current settings.

**The math:**

One Euro filter has two main parameters:
- `min_cutoff` (Hz): higher = less smoothing during slow motion, more responsive; lower = more smoothing during slow motion, more lag
- `beta` (dimensionless): higher = adapts faster to fast motion; lower = stays in smoothed mode longer during slow motion

Current values in `mediapipe_sender.py` `make_hand_filters` (across all 21 landmarks): roughly `min_cutoff=1.0, beta=0.05` — TODO confirm by reading code.

Proposed split:
- Palm/base landmarks (indices 0, 1, 2, 5, 9, 13, 17): keep current values
- Mid landmarks (indices 3, 6, 7, 10, 11, 14, 15, 18, 19): keep current values OR slightly heavier
- Tip landmarks (indices 4, 8, 12, 16, 20): `min_cutoff=0.5, beta=0.005` (heavier)

Tuning is empirical — these starting values are educated guesses, not derived from first principles.

**What it fixes:**
- Per-frame jitter on tip POSITIONS (root cause #1 directly)
- Reduces noise propagation downstream into chain inheritance (root cause #3 indirectly)

**What it does NOT fix:**
- Roll instability on near-vertical bones (root causes #4, #5 — that's lever A)
- Fundamental MP confidence issues (root cause #2 — smoothing trades latency for stability, doesn't solve the underlying confidence gap)

**Cost:**
- ~20-30 lines in `mediapipe_sender.py`: split `make_hand_filters` into per-class filter pools, classify landmarks by index
- Zero new compute in steady state — One Euro is already running per-landmark, just with different parameters
- **Adds ~15-50ms of smoothing latency on tip landmarks** — kid's puppet finger arrives slightly behind kid's actual finger during fast motion

**Risk:**
- Heavier smoothing = more lag during fast motion. Kid does a sharp finger snap; puppet snaps a few frames later. May feel "rubbery" — exactly the artifact David already saw when trying Blender's Smooth modifier on the bake.
- Tuning `min_cutoff` and `beta` requires empirical iteration — no clean theoretical answer.
- **Tradeoff is real:** the lever is papering over a tracker-side problem, not solving it.

**Predicted improvement:**
- Tip noise (currently 0.30-0.44): expect drop to 0.10-0.20 with the proposed parameters — substantial improvement, but with measurable lag tradeoff during fast finger motion.
- Best effect on still-hand poses (when puppet performance is paused for emphasis); worst tradeoff during fast finger flicks or finger-spelling-style rapid changes.

### Lever C — Quaternion-Aware Post-Bake Smoothing

**What it does in plain English:** After the kid stops recording, run a smoothing pass over the recorded rotation data — but using quaternion-aware math (slerp) instead of component-wise averaging, so the smoothing doesn't break the quaternions' unit-length property. Blender's built-in Smooth modifier smooths each component (W, X, Y, Z) independently, which is the artifact David saw — broken unit length means visibly wrong rotations.

**The math:**

For each rotation fcurve set on a hand bone (4 fcurves: W, X, Y, Z keyframes), at each keyframe time t:
1. Read the four components → form quaternion q(t)
2. Read q(t-1), q(t+1), and possibly q(t-2), q(t+2)
3. Apply iterative slerp: q_smoothed(t) = slerp(slerp(q(t-1), q(t+1), 0.5), q(t), 1-α) where α is the smoothing strength
4. Write the smoothed components back into the four fcurves at frame t

Or use a windowed approach: collect N keyframes around each target keyframe, slerp them all together with a Gaussian-weighted kernel.

The implementation lives in a new `_apply_quaternion_smooth(rig, action)` method, similar in shape to `_apply_median_hand_scale`. Has to navigate the same Slotted-Actions API for fcurve enumeration as day8b.

**What it fixes:**
- Persistent jitter that survives lever A and lever B
- Roll noise that comes from real direction noise, not just degenerate fallbacks

**What it does NOT fix:**
- Live mirror noise — only affects the bake. Kid still sees jittery puppet during recording.
- The root cause; just smooths the symptom further along the pipeline.

**Cost:**
- Substantially more code than A or B — new method, fcurve navigation, smoothing kernel choice
- Choice of smoothing kernel (Gaussian, sliding average, etc.) affects character of result and needs tuning
- Window size tuning
- Has to handle keyframe boundary conditions (start of strip, end of strip)
- Slotted-Actions API enumeration

**Risk:**
- Smoothing the bake = puppet feels "smooth" but loses snap on intentional finger flicks
- Visibly softens finger movements that the kid intended to be sharp — directly opposed to the puppet-show pedagogical goal of "your gesture becomes the puppet's gesture"
- Adds processing time before NLA strip is ready (modest, but the kid is waiting)

**Predicted improvement:**
- Could drop bake-time tip noise to body-bone levels (0.001-0.004) at the cost of motion crispness
- The cost-benefit is most favorable when paired with already-aggressive A and B (i.e., as the LAST lever to ship)
- Lower-window-size variants (e.g., ±1 frame slerp) preserve crispness but offer less noise reduction. There's a knob.

---

## Recommendation

**Ship Lever A first** (palm-normal as `side_ref`). Then re-measure. Decide on B and C from data, not theory.

### Why A first

1. **Only lever that addresses a fixable root cause without tradeoffs.** A removes geometric ambiguity that's purely a math fallback choice — no latency cost, no crispness cost, no compute cost. B and C trade latency or crispness for noise reduction.
2. **Free side fix:** Open Issue 1.c (thumb roll weirdness) is the same root cause and gets resolved as a side effect.
3. **Pattern is proven on body bones.** `side_ref=hip_lateral` already works for the spine + arms + legs. Lever A is a transplant of a proven pattern, not a new design.
4. **Lowest risk per shipped change.** ~30 lines, all receiver-side, no sender changes, no Blender API surprises (this isn't Slotted-Actions territory).
5. **Generates the data we need to decide on B vs C.** Post-shipping, the new measurement of fingertip Δq tells us how much of the tip noise was being amplified upstream by roll-fallback choice. Without that measurement, choosing between B and C is guesswork.

### After A ships and is measured

If post-A fingertip Δq is `< 0.10` → A was sufficient. Probably done with this work item; revisit if classroom testing surfaces new complaints.

If post-A fingertip Δq is `0.10-0.20` → noticeable but tolerable for K-12 puppet shows. Consider deferring B + C to a future cycle. The current goal is "good enough for under-resourced classrooms," not "movie-quality finger fidelity."

If post-A fingertip Δq is `> 0.20` → ship B (lighter smoothing variant, e.g., `min_cutoff=0.7` not 0.5, to keep most crispness). Re-measure.

If post-B fingertip Δq is still `> 0.10` → consider C as the last resort, with a small smoothing window (±1 frame slerp) to preserve crispness. C is V2.1 territory — non-trivial implementation, accepts a real artistic tradeoff.

### What I'd avoid

- **Don't ship A and B simultaneously.** Two changes at once = can't tell which one helped or hurt. The "one change at a time, test, decide" rule (`feedback_dr_bayus_hard_rules`) applies hard here.
- **Don't ship C without first trying A and B.** C is the lever with the highest artistic cost (motion crispness loss). If A and B can get us to "good enough for the classroom," C should stay on the shelf.
- **Don't tune the One Euro parameters by intuition alone.** When B is queued, do a 5-minute measurement: log tip Δq at three parameter sets, pick the one with best noise/lag tradeoff for your taste. The lab is the test bench.

---

## Open Questions (flag for next session if any block A)

1. **Palm basis stability:** is `palm_normal` itself stable enough (Δ < 0.05) to serve as `side_ref`? Need to either log it pre-implementation, or just trust the proof-by-anatomy (wrist + MCP landmarks are MP's most-confident points) and measure post-implementation.

2. **Thumb-specific side_ref:** does the thumb need its own side reference, or is palm_normal good enough? The thumb's natural rotation axis differs from finger axes anatomically. **Default plan: ship A using palm_normal for all hand bones, observe thumb behavior, file follow-up if it's still weird.**

3. **MediaPipe per-landmark confidence:** we currently don't consult MP's visibility/presence scores when driving bones. Could add confidence-weighted drives in a future cross-cutting lever — applies to both body and hand bones. Not urgent. Note in `Phase 7 calibration backlog`.

4. **Sign flip for right hand:** body bones use `hip_lateral` and the lateral direction naturally flips L/R via MP landmark math. Hand drive code already handles L/R explicitly. Need to confirm: is `palm_normal` for the right hand the negation of palm_normal-as-computed-from-mirrored-landmarks, or a separate computation? Implementation detail; trivial; flag during design.

5. **Live mirror behavior:** does palm_normal need to be smoothed via One Euro on the sender side, or is the natural smoothness of MP wrist + MCP landmarks enough? **Default plan: don't add smoothing initially; add only if palm_normal frame-to-frame variance turns out to be the new bottleneck.**

---

## Cross-References

- **Source files lever A would touch:** `core/receiver.py` (`apply_landmarks_to_rig`, `_drive_bone_segment` callsites for hand bones)
- **Existing pattern to transplant from:** body bone handling in `apply_landmarks_to_rig`, look for `hip_lateral` computation and the 12 callsites that pass it as `side_ref`
- **Source files lever B would touch:** `mediapipe_sender.py` (`make_hand_filters`, the per-landmark filter dict)
- **Source files lever C would touch:** `core/recorder.py` (new method sibling to `_apply_median_hand_scale`)
- **Related research docs:** `BLENDARMOCAP_FOOT_MATH.md` (similar pre-code design pattern); `FREEMOCAP_RESEARCH.md` (multi-cam alternative parked 2026-05-01 — see `BENCHMARKS.md` and `project_v2_dual_cam_spike.md` memory for that decision context)
- **Related memories:** `feedback_research_doc_first_pattern`, `feedback_three_smoothing_physics_surfaces` (One Euro / Goo / Verlet are different problems — critical to not conflate them when designing lever B), `feedback_blender_52_slotted_actions` (lever C will need this)

---

## Decision Point

**David: this doc's recommendation is to ship Lever A as the next V2 build. Confirm or redirect.**

If confirmed → next step is the design doc for Lever A specifically (not implementation yet) — exact API additions, exact callsite changes, the L/R sign-flip detail, the degenerate-case fallback, and the post-shipping measurement protocol. THEN code.
