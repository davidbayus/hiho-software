# V2 Phase 0 — Afternoon Spike

**Goal:** Validate the V2_DESIGN FPS thesis — that running ONE landmarker at a time clears the 12–15 FPS hand-on-face cliff that motivated V2.

**Deliverable:** FPS table (filled in below) + go/no-go decision.

**Time budget:** 1–3 hours, including comparison runs.

---

## What we're testing

V1 runs face + body + hand landmarkers simultaneously on every frame. The hand-on-face scenario crashed FPS to 12–15 because the three landmarkers compete for the same pixel region.

V2 design says: run ONE landmarker per pass. Body-only should hold 30 FPS even in the worst-case V1 scenario.

The spike is a forked sender (`mediapipe_sender_spike.py`) with a `--mode {body,hands,face,all}` flag. We run the same scenarios under `--mode all` (V1 baseline) and `--mode body` (V2 thesis) and compare.

We are **only** measuring sender-side FPS — landmarker throughput. End-to-end Blender viewport FPS is a Phase 1 question; if body-only doesn't hold 30 here, the thesis is dead and the Blender side won't save it.

---

## How to run

The spike uses the same Python venv as the V1 sender (`~/.ppparty/venv`, mediapipe 0.10.33). Models are reused from `SOFTWARE/PPPARTY/models/` — no re-download.

From a terminal:

```bash
cd ~/Desktop/DR_BAYUS/SOFTWARE/PPPARTY_V2/spike

# Baseline — V1 behavior, all three landmarkers
~/.ppparty/venv/bin/python mediapipe_sender_spike.py \
    --mode all --scenario baseline_idle --duration 30

# Repeat for each scenario below.
```

Each invocation:
- Runs for 30 seconds (`--duration 30`), then auto-quits and prints summary stats.
- Appends one row per second to `results/spike_fps.csv`.
- Shows a preview window with FPS + `[mode] scenario` overlay so you can verify you're in the right scenario.
- Press `q` in the preview window to quit early.

---

## Test matrix

Run each scenario under **both** `--mode all` (baseline) and `--mode body` (V2 thesis). 30 seconds each. 8 runs total.

| # | Scenario tag           | What you do in front of the camera                                  |
|---|-------------------------|---------------------------------------------------------------------|
| 1 | `idle`                  | Sit still, hands at sides, neutral face. ~30s.                      |
| 2 | `body_moving`           | Wave arms, lean side-to-side, no hands near face. ~30s.             |
| 3 | `hand_near_face`        | One hand floating ~10cm from cheek/chin. Move slightly. ~30s.       |
| 4 | `hand_on_face`          | Hand fully covering one cheek, fingers near eye/mouth. ~30s.        |

**Run order suggestion** (so the CSV lines up cleanly):

```bash
PY=~/.ppparty/venv/bin/python
$PY mediapipe_sender_spike.py --mode all  --scenario idle           --duration 30
$PY mediapipe_sender_spike.py --mode all  --scenario body_moving    --duration 30
$PY mediapipe_sender_spike.py --mode all  --scenario hand_near_face --duration 30
$PY mediapipe_sender_spike.py --mode all  --scenario hand_on_face   --duration 30
$PY mediapipe_sender_spike.py --mode body --scenario idle           --duration 30
$PY mediapipe_sender_spike.py --mode body --scenario body_moving    --duration 30
$PY mediapipe_sender_spike.py --mode body --scenario hand_near_face --duration 30
$PY mediapipe_sender_spike.py --mode body --scenario hand_on_face   --duration 30
```

(If you want, also run `--mode hands` and `--mode face` against `idle` for completeness — useful for Phase 1 when we plan Pass 2 / Pass 3, but not required to make the V2 go/no-go call.)

---

## Results — fill in after running

The summary printed at quit is mean / p50 / p95 / min FPS. The first 1-second sample is dropped (cold start). Read those numbers off the terminal or compute from `results/spike_fps.csv`.

### Hardware

- **Machine:** Apple M3 iMac (`davidbayus@Davids-iMac`)
- **Camera:** built-in
- **Capture resolution:** 640×480
- **Date:** 2026-04-26

### V1 baseline — `--mode all`

| Scenario          | mean FPS | p50   | p95   | min   |
|-------------------|---------:|------:|------:|------:|
| idle              |    29.94 | 29.97 | 30.20 | 28.92 |
| body_moving       |    29.99 | 29.98 | 30.19 | 29.75 |
| hand_near_face    |    29.94 | 29.97 | 30.08 | 29.06 |
| hand_on_face      |    29.76 | 29.96 | 30.03 | 28.06 |

### V2 thesis — `--mode body`

| Scenario          | mean FPS | p50   | p95   | min   |
|-------------------|---------:|------:|------:|------:|
| idle              |    29.94 | 29.97 | 30.22 | 28.88 |
| body_moving       |    29.83 | 29.95 | 30.11 | 28.95 |
| hand_near_face    |    29.97 | 29.98 | 30.10 | 29.82 |
| hand_on_face      |    29.75 | 29.96 | 30.01 | 28.95 |

### Body-vs-all delta (mean FPS)

| Scenario          | all   | body  | body − all |
|-------------------|------:|------:|-----------:|
| idle              | 29.94 | 29.94 |     +0.00  |
| body_moving       | 29.99 | 29.83 |     −0.16  |
| hand_near_face    | 29.94 | 29.97 |     +0.03  |
| hand_on_face      | 29.76 | 29.75 |     −0.01  |

---

## Go / No-Go decision

**Decision:** **INCONCLUSIVE on M3 — proceed with V2 design, but do not treat the FPS thesis as validated.**

### What the data shows

1. **The V1 12–15 FPS cliff does not reproduce on M3 in `--mode all`.** Worst case was `hand_on_face` at 29.76 mean / 28.06 min — no cliff.
2. **`--mode body` produces no measurable FPS gain on M3.** Body-vs-all delta is within ±0.16 FPS in every scenario. The body-only run did not unlock anything because there was nothing to unlock.
3. **Sender is camera-locked at ~30 FPS.** Three landmarkers fit comfortably inside the 33 ms frame budget on this hardware. There is no headroom to gain or lose.

### What this means

- **The "pixel-region competition between simultaneous landmarkers" hypothesis in V2_DESIGN §3.1 is not the bottleneck on M3-class hardware.** It may still be true on weaker machines — see follow-ups below.
- **The original V1 12–15 FPS cliff almost certainly lived on the Blender side, not the sender side.** Likely culprits: 217 GN nodes re-evaluating (V2_DESIGN §3.5), Verlet sim zone on the tracked armature, modifier dirty propagation on every blend-shape write. None of these are measured by this spike.
- **Single-stream pass architecture is still defensible** for the other reasons in V2_DESIGN — Holistic transform-matrix gap (§3.2), Rose-vs-mocap dynamics conflict (§3.4), pedagogical layered-capture narrative (§14), MetaHuman-Animator precedent (§3.3). None of those are FPS arguments.

### What changes vs the original 5–9 day plan

- **Phase 1 must add a Blender-side viewport FPS measurement** before committing to Phases 2–5. That is where the actual cliff lives. If dropping Verlet + gating modifier writes on the tracked rig recovers 30 FPS in V1's failure scenarios, V2 is justified by *that* measurement, not this spike.
- **Phase 1 must also repeat this sender spike on the e-waste target** (oldest available laptop / Chromebook + Linux). On weaker hardware the camera-lock may not hide landmarker contention, and the sender-side thesis may yet hold.
- **Do not advance Phase 0's deliverable into V2_DESIGN as "FPS thesis validated."** Update §3.1 to say the sender thesis is hardware-conditional, validated only after the e-waste repeat.

### One-line summary

Sender FPS is camera-locked at 30 on M3 in every mode/scenario combo, so the spike neither proves nor disproves V2's FPS thesis — the real cliff is on the Blender side, and the e-waste hardware test still needs to happen before we lock the design.

---

## What's NOT in this spike

- **Blender viewport FPS.** End-to-end FPS depends on the GN tree too. If the spike validates, Phase 1 should add a viewport-side measurement before we commit to all of Phase 2–5.
- **E-waste hardware.** This runs on whatever you ran V1 on. If body-only barely holds 30 on a fast laptop, we already know an old machine will struggle. Plan to repeat this spike on the oldest available laptop before locking V2.
- **Verlet drop FPS gain.** V2 also drops Verlet sim on the tracked armature. That's a separate FPS lever (open question #2 in V2_DESIGN). Measuring it requires the Blender side.
- **Cross-pass constraint setup.** That's Phase 1+ design work; it doesn't affect the FPS thesis.
