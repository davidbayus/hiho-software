# Hand Tip Smoothing — Lever B Design Doc (v2.0.3 trial → reverted in v2.0.4)

> ⚠️ **Status (2026-05-06 evening): REVERTED in v2.0.4.** Lever B shipped at the proposed `tip_min_cutoff=0.5, tip_beta=0.005` parameters; David tested gestures and judged it rubbery — the lag tradeoff cost more crispness than the noise reduction earned back. Defaults reverted to global values (`1.2, 0.04`) in v2.0.4, which makes the tip-class filters behave identically to non-tip filters. **CLI knobs + `make_hand_filters` filter-class plumbing retained as an inert escape valve** so Lever B can be re-enabled at any aggressiveness via CLI args without code changes.
>
> The reframe context: this revert sits inside David's broader "ground moving beneath our feet" identity reframe (see `project_software_identity_reframe_2026-05-06.md` in memory) — V2 may fold into a Green Room revival as a step-by-step bake-oriented take-home tool, where Lever B's lag tradeoff stops mattering because there's no live performance. **Don't strip the code path.**
>
> The decision tree and parameter recommendations below are correct as written. The "predicted gain" section is now empirically wrong: at the proposed parameters Lever B traded too much crispness for the noise reduction. A lighter retune (e.g., `0.7, 0.01`) was offered but David chose straight revert and to surface the bigger-picture reframe instead.

---



Pre-code design per `feedback_research_doc_first_pattern`. Implements Lever B from `HAND_ROTATION_NOISE_RESEARCH.md`. Companion to (not replacement of) v2.0.1's Lever A (`HAND_SIDE_REF_DESIGN.md`).

## Decision: ship Lever B

**Measurement on v2.0.2 (2026-05-06, post-Lever-A):**

| class | day8d baseline | v2.0.2 measured | drop |
|---|---|---|---|
| palm.* | 0.08–0.10 | 0.049 | -50% |
| f_*.01 | — | 0.082 | new |
| f_*.02 | — | 0.124 | new |
| **f_*.03 (tips)** | **0.30–0.44** | **0.200** | **-37 to -55%** |
| pelvis / chest | 0.001–0.004 | 0.003 | unchanged |
| upper_arm | 0.02–0.03 | 0.012 | unchanged |

Fingertips landed exactly on the 0.20 boundary in the script's decision tree. **Two reasons we're shipping B anyway:**

1. **Audience reframe (2026-05-06).** V2's current testing audience is HS students, not K-12. The "tolerable for K-12 puppet show" framing in the original measurement script and v2.0.2 docs was set for a more forgiving audience than V2 currently serves. HS observers are more discerning of fingertip jitter. See `feedback_v2_audience_is_hs_not_k12.md`.
2. **David's classroom intuition** is that *some* form of additional smoothing is needed regardless of where the boundary falls. We test the proposed parameter values, re-measure, and decide whether to keep them, retune, or escalate to Lever C.

## What changes (scope)

**Touched:** `mediapipe_sender.py` only. Receiver-side, recorder-side, rig builder — all unchanged. Lever B is a sender-side smoothing tweak; it propagates through the existing pipeline automatically.

**Untouched:**
- `core/receiver.py` — keeps the v2.0.1 across-palm `side_ref` math.
- `core/recorder.py` — keeps the v2.0.2 per-class hand calibration.
- `core/rig.py` — keeps the v2.0.2 floor constraint + constant-stance.
- `__init__.py` — version bump only (2.0.2 → 2.0.3).

**One-change-at-a-time rule:** Lever B is the ONLY change in v2.0.3. If the new measurement is worse OR the puppet feels rubbery, revert is `git checkout` v2.0.2's `mediapipe_sender.py`.

## The change in `mediapipe_sender.py`

### make_hand_filters: split filter pool by landmark class

Today (v2.0.2):
```python
def make_hand_filters(min_cutoff=1.2, beta=0.04):
    """One Euro filters for 2 hands × 21 landmarks × 3 axes."""
    return [
        [[OneEuroFilter(min_cutoff, beta) for _ in range(3)]
         for _ in range(N_HAND_LANDMARKS)]
        for _ in range(2)
    ]
```

v2.0.3:
```python
# Tip landmarks per MediaPipe Hand topology — the bones we want to smooth harder.
# Indices 4/8/12/16/20 = thumb tip / index tip / middle tip / ring tip / pinky tip.
HAND_TIP_INDICES = frozenset({4, 8, 12, 16, 20})

def make_hand_filters(min_cutoff=1.2, beta=0.04,
                      tip_min_cutoff=None, tip_beta=None):
    """One Euro filters for 2 hands × 21 landmarks × 3 axes.

    Tip landmarks (4/8/12/16/20) get heavier smoothing when
    tip_min_cutoff/tip_beta are provided — Lever B from
    HAND_ROTATION_NOISE_RESEARCH.md. The tradeoff is real: heavier
    smoothing adds lag during fast motion. Tune via CLI flags.

    With tip_min_cutoff=None and tip_beta=None, all 21 landmarks
    use the same parameters (v2.0.2 behavior).
    """
    tmc = min_cutoff if tip_min_cutoff is None else tip_min_cutoff
    tb  = beta       if tip_beta       is None else tip_beta

    def landmark_filters(j):
        if j in HAND_TIP_INDICES:
            return [OneEuroFilter(tmc, tb) for _ in range(3)]
        return [OneEuroFilter(min_cutoff, beta) for _ in range(3)]

    return [
        [landmark_filters(j) for j in range(N_HAND_LANDMARKS)]
        for _ in range(2)
    ]
```

### Wire CLI args

Add after the existing `--smooth-beta` arg:
```python
parser.add_argument("--smooth-tip-min-cutoff", type=float, default=0.5,
                    help="One Euro min cutoff Hz for fingertip landmarks "
                         "(4/8/12/16/20). Lower = heavier smoothing on tips. "
                         "v2.0.3 Lever B default: 0.5")
parser.add_argument("--smooth-tip-beta", type=float, default=0.005,
                    help="One Euro beta for fingertip landmarks. Lower = "
                         "stays in smoothed mode longer. v2.0.3 Lever B "
                         "default: 0.005")
```

### Wire into `run()`
```python
hand_filters = make_hand_filters(
    min_cutoff=args.smooth_min_cutoff,
    beta=args.smooth_beta,
    tip_min_cutoff=args.smooth_tip_min_cutoff,
    tip_beta=args.smooth_tip_beta,
)
```

## Why these specific parameter values

Per `HAND_ROTATION_NOISE_RESEARCH.md` Lever B section:

- **`tip_min_cutoff = 0.5`** (default of 1.2 / ~2.4×). Lower min_cutoff = heavier smoothing when the hand is still — exactly when fingertip jitter is most visible.
- **`tip_beta = 0.005`** (default of 0.04 / 8× lower). Lower beta = adapts more slowly to fast motion, so smoothing doesn't drop out the moment the hand twitches. Cost: ~15-50ms lag on tip landmarks during fast motion.

These are educated starting values. If David finds them too rubbery on fast hand motion, the tuning escape valves (in order from "still helpful" to "back to v2.0.2"):

1. **Less aggressive tips:** `--smooth-tip-min-cutoff 0.7 --smooth-tip-beta 0.01`
2. **Even less:** `--smooth-tip-min-cutoff 0.9 --smooth-tip-beta 0.02`
3. **Disable Lever B:** `--smooth-tip-min-cutoff 1.2 --smooth-tip-beta 0.04` (matches global = no per-class effect)

## Predicted gain (sets the bar for "did it work")

Research doc said: "Tip noise (currently 0.30-0.44): expect drop to 0.10-0.20 with proposed parameters."

Lever A already got us from 0.30-0.44 → 0.20. The remaining noise after Lever A is the part Lever A *can't* fix — pixel uncertainty + low confidence on tip landmarks, exactly what Lever B targets.

**Predicted v2.0.3 fingertip Δq:**
- Optimistic: 0.05–0.10 (tip-specific smoothing absorbs most of the residual pixel noise)
- Realistic: 0.10–0.15
- Pessimistic: 0.18–0.20 (smoothing barely moves the needle — if so, the residual is chain-inheritance, not pixel uncertainty, and Lever C is on the table)

If new measurement shows `< 0.15` → ship as v2.0.3, classroom-test, defer Lever C.
If new measurement shows `0.15-0.20` → tune the knobs, retake, re-measure.
If new measurement shows `> 0.20` (i.e., regression or no movement) → revert / investigate; don't ship.

## Test protocol (post-install)

Same as v2.0.2 measurement protocol. David runs:
1. Install v2.0.3 via Blender's Install dialog.
2. Click **Create V2 Rig** if no PP_V2_Rig in scene.
3. Click **Start Body Mirror** — confirm hands track.
4. Click **Start Recording (Pass 1)**.
5. Hold both hands STILL in front of camera, palms forward, fingers slightly spread, 10 seconds. No gestures.
6. Click **Stop Recording.**
7. Claude re-runs `spike/measure_hand_rotation_noise.py` via the Blender connector.

After the still-hands measurement, recommend a **second take with deliberate gestures** (waving, finger flicks, pointing) to subjectively check whether the tip lag feels rubbery. Numbers tell us if the noise dropped; eyes tell us if the lag tradeoff is acceptable.

## What this doesn't fix

- **Chain inheritance noise** (root cause #3 in the research doc) — `.02` and `.01` phalanges aren't directly tip-smoothed, but their `.03` children inherit smoother input. Lever B's effect on `.02`/`.01` is indirect.
- **Live mirror "feel"** during fast motion — the kid will see their puppet's fingertips lag slightly. May or may not bother an HS performer.
- **Roll noise** — Lever A already covered that.

## Cross-references

- **Research:** [HAND_ROTATION_NOISE_RESEARCH.md](HAND_ROTATION_NOISE_RESEARCH.md) §"Lever B"
- **Lever A predecessor:** [HAND_SIDE_REF_DESIGN.md](HAND_SIDE_REF_DESIGN.md), [HAND_SIDE_REF_RESEARCH.md](HAND_SIDE_REF_RESEARCH.md)
- **Measurement:** [spike/measure_hand_rotation_noise.py](spike/measure_hand_rotation_noise.py)
- **Benchmark ledger:** [BENCHMARKS.md](BENCHMARKS.md) — append entry for v2.0.3 if and only if measurement passes.
- **Memory:** `feedback_v2_audience_is_hs_not_k12.md` (HS framing), `feedback_three_smoothing_physics_surfaces.md` (don't conflate One Euro with Goo or Verlet).
