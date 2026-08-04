# Hand Bone `side_ref` — Research Note for Rotation-Noise + Thumb-Roll Fix

**Date:** 2026-04-30
**Purpose:** Identify the math, edge cases, and decisions for replacing the unstable `to_track_quat('Y', 'Z')` fallback on V2's hand bones with a stable palm-derived `side_ref`. The change should kill (a) the high frame-to-frame quaternion delta on fingertips and (b) the arbitrary thumb roll David has been seeing since Day 6.
**Status:** Research doc, pre-code. Sits before any code edits to `core/receiver.py`. Pattern: research → design delta → code, per `feedback_research_doc_first_pattern` memory. No code changes are proposed in this document — only a recipe and a list of decisions for the next session to make.
**Authors:** David Bayus + Claude (Opus 4.7).
**License posture:** All math in this document is Claude-derived from the existing V2 codebase + standard MediaPipe landmark conventions. No third-party source is being read or paraphrased.

---

## 1. Why This Doc Exists

V2 currently passes `side_ref=hip_lateral` to spine, leg, and arm bones — a stability fix landed in day7e for the upper-body 90°-flip bug. **Hand bones get nothing.** [`core/receiver.py:651`](core/receiver.py:651) calls `_drive_bone_segment(pb[bone_name], projected[head_idx], projected[tail_idx], scale_to_segment=True)` with no `side_ref` argument, falling through to the default `to_track_quat('Y', 'Z')` path.

That default path is mathematically degenerate when the bone's aim direction approaches world ±Z. Blender's fallback picks an arbitrary perpendicular axis, and tiny MediaPipe noise in the bone direction wiggles it across the degenerate boundary frame-to-frame. The visible artifacts are two:

- **Rotation jitter on tips.** Day 8b diagnostic measured mean frame-to-frame quaternion delta on finger tips (`.03` bones) at **0.30–0.44**, vs. body bones at 0.001–0.004 — roughly 100–400× more noise. Some of that is real MediaPipe landmark noise on the smallest features, but a substantial fraction is the basis-flipping amplifier described above.
- **Thumb-roll arbitrariness.** Thumb bones often sit near-vertical at rest (the kid's hand at the desk, thumb pointing up). The fallback rolls them randomly each frame. Day 8c diagnostic flagged this as item 1.c in [`HANDOFF.md:122`](HANDOFF.md:122).

The same fix kills both. That makes it the highest-leverage hand fix on the queue (memory `project_v2_day8_median_hand_calibration` open follow-up #1).

This doc captures the recipe so the next coding session can implement it without re-deriving the geometry.

---

## 2. What We Want To End Up With

For each hand bone driven in [`core/receiver.py`](core/receiver.py)'s `# --- Fingers ---` block (currently lines 612–659), pass a `side_ref` Vector that is:

1. **Stable** across small landmark noise — does not flip 90° when MediaPipe's wrist or knuckle estimates wiggle by a millimeter.
2. **Anatomically meaningful** — represents the actual lateral direction of the hand the bone belongs to, so bone-X ends up across the palm (matching Rigify's rest-pose convention).
3. **Mirror-correct** — left and right hands produce palm bases that mirror each other naturally, so the same code path works for both sides.
4. **Available per-frame** — derivable from the same `projected[]` landmark array we already have inside the per-hand loop.

The output is a single `Vector` per hand, computed once at the top of the per-hand block and passed to every `_drive_bone_segment` call inside it.

---

## 3. The MediaPipe Hand Landmarks We Have

MediaPipe's `hand_world_landmarks` give 21 landmarks per hand, in a hand-local coordinate frame (already translated so the geometric center is near origin — V2 also subtracts `lms_raw[0]` per [`receiver.py:638`](core/receiver.py:638) to anchor at wrist). The standard MP hand landmark layout, abbreviated:

| MP idx | Landmark | Notes |
|---|---|---|
| 0 | `wrist` | Origin point; joint between forearm and palm |
| 5 | `index_finger_mcp` | Knuckle at the base of the index finger |
| 9 | `middle_finger_mcp` | Knuckle at the base of the middle finger |
| 13 | `ring_finger_mcp` | Knuckle at the base of the ring finger |
| 17 | `pinky_mcp` | Knuckle at the base of the pinky |
| 1 | `thumb_cmc` | Carpometacarpal joint at the base of the thumb |
| 2 | `thumb_mcp` | Knuckle of the thumb (one joint up from CMC) |

Indices 5, 9, 13, 17 form the four MCP knuckles across the palm. Together with wrist (0), these five points define the **palm plane** — the flat region from wrist to the row of knuckles.

Three of these — wrist (0), index_MCP (5), pinky_MCP (17) — span a triangle that:

- Has **non-degenerate area** in any natural hand pose. The palm is never crumpled to a line.
- Sits in the **palm plane**. Cross product of two of its edges is the **palm normal**.
- **Mirrors correctly** between left and right hands: lm 5 → lm 17 sweeps across the knuckles in opposite directions for L vs R, so the cross product flips sign — exactly what we want for a per-hand basis.

This is the same trick BlendArMocap uses for the foot triangle (knee/ankle/foot_index) per [`BLENDARMOCAP_FOOT_MATH.md`](BLENDARMOCAP_FOOT_MATH.md).

---

## 4. The Math — Palm Basis Construction

Inside the per-hand loop (after `projected` is built but before the per-bone drive loop), compute:

```
P_wrist  = projected[0]
P_index  = projected[5]
P_pinky  = projected[17]

across_palm  = (P_pinky - P_index)              # raw across-knuckles vector
along_palm   = (((P_index + P_pinky) * 0.5) - P_wrist)  # wrist → mid-knuckles

palm_normal  = along_palm.cross(across_palm)    # right-hand rule
                                                # — sign discussed below
```

`palm_normal` is perpendicular to the palm plane. If we orient `along_palm` (wrist-to-knuckles) and `across_palm` (index-to-pinky) consistently, `along_palm × across_palm` points **out the back of the hand** for both left and right hands — the cross product flips because `across_palm`'s direction flips between L and R, but `along_palm` flips the other ingredient too, and the two flips cancel into a consistent "back-of-hand" direction.

Wait — that's wrong. Let me re-derive. Both vectors flip between L and R hand:
- For the LEFT hand viewed from outside: index is on the right side of the hand, pinky on the left → `across_palm = pinky - index` points LEFT in image.
- For the RIGHT hand viewed from outside: index is on the left side, pinky on the right → `across_palm` points RIGHT in image.
- `along_palm` (wrist → mid-knuckles) does NOT flip — it points toward the fingers in both hands.

So `palm_normal = along_palm × across_palm` will indeed point in **opposite** directions for L and R. For one hand it points out the back, for the other it points out the palm.

**This means `palm_normal` is NOT directly usable as `side_ref` without sign correction.** Two options for fixing this:

- **Option A — sign by handedness.** When `puppet_side == 'L'`, negate `palm_normal`. (The `handedness_str` is already known in the loop — [`receiver.py:628`](core/receiver.py:628).)
- **Option B — use a different basis vector.** Instead of `palm_normal`, use `across_palm` directly (or its perpendicular projection). `across_palm` is itself a meaningful "side" direction — it points across the knuckles, which is one valid choice for bone-X. It also flips sign with handedness, but that's fine because each hand's bones live on their own side and the flip aligns with the bones.

**Recommended:** Option B with `across_palm` as the source for `side_ref`. Reasoning:

1. **Physical interpretation.** `across_palm` IS the bone-X direction we want for finger phalanges — across the row of knuckles. When `_drive_bone_segment` projects it perpendicular to bone-Y (along the finger), the result is "the part of across-palm that's still across-palm given this finger's bend angle" — exactly the right local-X for each finger.
2. **Avoids sign confusion.** `palm_normal` requires a sign rule that's easy to get wrong. `across_palm` derives from the bones it's serving.
3. **One vector for all bones in the hand.** Same `side_ref` works for all 19 bones per side (4 palms + 3 thumb + 4×3 finger phalanges). No per-bone basis math.

The math reduces to:

```
across_palm = projected[17] - projected[5]    # pinky_MCP - index_MCP
side_ref = across_palm                        # passed to _drive_bone_segment
```

That's two lines per hand iteration. The existing `_drive_bone_segment` projection (`bone_x_proj = side_ref - target_y * side_ref.dot(target_y)`, [`receiver.py:260`](core/receiver.py:260)) handles the rest.

---

## 5. Per-Bone Strategy

Three bone classes in the hand. The recipe for each:

### 5.1 Finger phalanges (`f_*.01`, `f_*.02`, `f_*.03` — 12 bones per hand)

**Pass `across_palm` as `side_ref`.** This is the cleanest case:

- Bone Y aims down the finger (changes per phalange — proximal vs middle vs distal — but all stay roughly perpendicular to `across_palm` in any natural pose).
- Bone X (= `across_palm` projected perpendicular to Y) ends up across the knuckles, perpendicular to the finger.
- Bone Z (= X × Y) ends up palm-normal-ish.
- This matches Rigify's rest-pose convention where finger bones have local X across the palm and local Z out the back.

**Expected impact on rotation noise:** large reduction. The fingertip rotation jitter (mean delta 0.30–0.44) has two sources: (a) real MP landmark noise, and (b) basis flipping in `to_track_quat`. This fix removes (b) entirely, leaving only (a). David's day8d data will tell us how much was (a) vs (b); the prediction is 50–80% reduction in mean delta on tips.

### 5.2 Palm bones (`palm.01–.04` — 4 per hand)

**Pass `across_palm` as `side_ref` (same as phalanges).**

Palms aim from wrist to their finger's MCP — they sit IN the palm plane, roughly perpendicular to `across_palm`. The projection gives a clean basis with bone-Z out the back of the hand.

**Expected impact:** small — palms are short and don't sit near-vertical, so `to_track_quat` was already mostly stable. Worth doing for consistency, not for noise.

### 5.3 Thumb (`thumb.01–.03` — 3 per hand)

**Pass `across_palm` as `side_ref`, BUT expect this to be approximate.**

The thumb is anatomically off-axis from the rest of the hand by ~30–45°. Its true rest plane is rotated about an axis from CMC to MCP. Using `across_palm` for the thumb gives a **deterministic but anatomically imperfect** basis — better than the current arbitrary fallback, but the thumb bones may still look slightly tilted.

A thumb-specific `side_ref` would derive from the thumb's own landmarks (e.g., `(lm[2] - lm[1]) × (lm[3] - lm[2])` or a vector from CMC to the index_MCP). **Defer this**: ship `across_palm` for the thumb first, see how it looks, decide whether the residual tilt is worth a thumb-specific code path.

The Day 8 diagnostic showed thumb scale calibration was already gnarly (thumb.01 underreporting at 70–75%, thumb.03 over at 134–139%). Some of that is the same arbitrary-roll bug — a deterministic basis should make the projected thumb segment lengths more consistent, which feeds back into the calibration stat.

---

## 6. Edge Cases & Failure Modes

### 6.1 Degenerate palm triangle

If `across_palm.length < epsilon`, the kid's index and pinky MCPs are reported at nearly the same point — extreme occlusion or an MP failure. `_drive_bone_segment` already handles a degenerate `side_ref` ([`receiver.py:271–274`](core/receiver.py:271)) by falling back to `to_track_quat('Y', 'Z')`. So passing a near-zero `side_ref` is safe — we get the OLD broken behavior on that frame, not a crash.

The doc-level decision: **don't bother guarding for it in the hand drive loop.** The existing fallback in `_drive_bone_segment` is enough.

### 6.2 Palm flat-on-camera

When the kid holds the palm directly toward the camera, `across_palm` is well-defined but `palm_normal` would point straight at the camera (if we were using it). For `across_palm`, this is the IDEAL case — `across_palm` is fully visible and accurate. No special handling needed.

### 6.3 Palm edge-on to camera (back of hand toward camera)

`across_palm` is foreshortened in this pose — its 3D length is right but its projected 2D length onto the image is short. **MediaPipe still reports correct 3D coords for `hand_world_landmarks`** (they're in the hand-local frame, not image-projected), so this is fine for our purposes. The vector we compute is correct.

### 6.4 Hand visibility loss

V2 already resets hand bones to identity when MP loses a hand ([`receiver.py:666–673`](core/receiver.py:666)). The new code lives BEFORE that reset, inside the `if hands:` block, so the side_ref computation only runs when MP saw a hand. No interaction with the reset path.

### 6.5 Multi-hand frames

If MP returns two hands, we compute one `across_palm` per hand. Each hand's landmarks are in their own local frame (already translated to wrist). This works as-is.

---

## 7. Open Questions

1. **Palm-x vs palm-normal vs both.** §4 recommends `across_palm` (the simplest). Worth a quick A/B in the next session: try `across_palm` first, then if thumbs still look wrong, try `palm_normal` (with handedness sign correction) as an alternative. The two choices give different roll conventions; one will match the rig's rest pose better.

2. **Should the calibration cohort split (median vs percentile) get re-evaluated after this lands?** The Day 8d diagnostic numbers were measured WITH the unstable basis. Some of the "noise tail" that pulled palms to 156% under uniform pct90 was probably basis-flip noise leaking into the segment-length measurement. After the fix, the median/percentile balance might shift. **Action:** re-measure scale.y per cohort after install-test, decide whether the cohort split still earns its keep.

3. **Does fixing the basis change the FPS budget?** Two extra Vector ops per hand frame, times 30 fps, times two hands = ~120 cheap ops/sec. Negligible. No FPS concern.

4. **Does the new basis interact with the day8d hand-bone scale calibration?** The recorder logs `seg_length` from `(projected[tail_idx] - projected[head_idx]).length` ([`receiver.py:658`](core/receiver.py:658)) — that calculation is purely from the projected landmark positions, independent of the bone's basis. The basis fix should NOT change segment lengths, only their orientations. Calibration stays valid.

5. **Should we also pass the `side_ref` to the recorder for any reason?** No. The recorder only needs scalar segment length. Basis is consumed entirely inside the live drive path.

---

## 8. Implementation Sketch

The change is small and lives in one place: [`core/receiver.py`](core/receiver.py)'s `# --- Fingers ---` block.

**Where:** between lines 642 (where `projected` is built) and 644 (where the per-bone loop begins), inside the `for handedness_str, lms_raw in hands:` loop body.

**What:** add two lines computing `across_palm` from `projected[5]` and `projected[17]`, and pass it into the existing `_drive_bone_segment` call as `side_ref`.

**Conceptual diff** (not code — just for the next session's reference):

```
inside the per-hand loop, after `projected` is built:

    palm_side_ref = projected[17] - projected[5]   # pinky_MCP - index_MCP

then inside the per-bone loop:

    _drive_bone_segment(
        pb[bone_name], projected[head_idx], projected[tail_idx],
        scale_to_segment=True,
        side_ref=palm_side_ref,         # <-- new
    )
```

**Validation plan after install:**

1. Visual: thumb roll should be deterministic — pinch the thumb to index, the thumb shouldn't wobble in roll between frames.
2. Live diagnostic via Anthropic Blender Connector: re-measure mean frame-to-frame quaternion delta on `f_*.03.*` bones across a take. Predict drop from 0.30–0.44 to under 0.10.
3. Live mirror feel: fingertip jitter visibly reduced. David's qualitative "feels stable" should rise another notch.
4. Calibration re-check: re-run the scale.y diagnostic from Day 8d. Determine whether tip overshoots (102–132%) tighten now that the basis is no longer feeding noise back into segment length.

**Build artifact:** ship as `day9.zip` — this is the start of a new diagnostic-driven cycle, parallel to Day 8's calibration arc. Day 8's three ships (8b/8c/8d) closed out hand size; Day 9 opens hand orientation.

---

## 9. What This Doc Does NOT Cover

- **Quaternion-aware post-bake smoothing.** The third lever in [`HANDOFF.md:121`](HANDOFF.md:121) for rotation noise. Slerp- or Euler-decompose-based smoothing of the BAKED action's quaternion fcurves. Real, but it's V2.1+ territory — its own research doc when we get there. Not interacting with the live-drive basis fix.
- **Heavier One Euro on tip landmarks.** The first lever in [`HANDOFF.md:120`](HANDOFF.md:120) — splitting `make_hand_filters` in `mediapipe_sender.py` into "palm/base" (lighter) vs "tip" (heavier) filter pools. Independent of the basis fix and probably worth doing anyway. Could ship in parallel as a separate change. Not in scope here.
- **Thumb anatomy correction.** Per-bone thumb-specific `side_ref` derived from thumb landmarks. Deferred per §5.3.
- **Hand-translation in world space.** The "hip translation" elephant in [`HANDOFF.md:124`](HANDOFF.md:124). Different problem, different doc.

---

## 10. References

- [`HANDOFF.md`](HANDOFF.md) §"Open issues David flagged" → item 1.b "Rotation noise on tips" — lists this fix as one of three candidate levers, recommends it as first to ship.
- [`core/receiver.py`](core/receiver.py) `_drive_bone_segment` (lines 205–304) — the function that consumes `side_ref`. Already supports it; this fix just starts passing it for hand bones.
- [`core/receiver.py`](core/receiver.py) `# --- Fingers ---` block (lines 612–673) — where the change lands.
- [`BLENDARMOCAP_FOOT_MATH.md`](BLENDARMOCAP_FOOT_MATH.md) — analogous research doc for foot orientation math. Same pattern: three landmarks → triangle → orthonormal basis → bone basis.
- Memory `feedback_research_doc_first_pattern` — the rule that produced this doc.
- Memory `project_v2_day8_median_hand_calibration` — open follow-up #1 names this fix as "recommended first lever" for rotation noise because it ALSO fixes the thumb-roll weirdness for free.
- MediaPipe Hand Landmark reference: [`developers.google.com/mediapipe/solutions/vision/hand_landmarker`](https://developers.google.com/mediapipe/solutions/vision/hand_landmarker) — canonical 21-landmark layout.

---

**Decision queue for next session:**

1. Confirm the Option B recommendation (`across_palm` as `side_ref`) vs Option A (`palm_normal` with handedness sign).
2. Confirm thumb gets the same `side_ref` as fingers in V1 of this fix (defer thumb-specific basis).
3. Greenlight the diff sketched in §8.
4. Approve `day9.zip` as the artifact name for the start of the new diagnostic cycle.

When David greenlights, the next session implements §8's diff — single file, ~3 lines of real change — builds the zip, install-tests, runs §8's validation plan via the Blender connector, and saves a memory capturing the rotation-delta before/after numbers.

End of doc.
