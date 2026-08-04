# CADRE Student Research Project Brief — Multi-Camera Hand-Tracking Fusion

**Status:** Open research idea, parked from V2 main path 2026-05-01. Suitable for CADRE Lab undergrad capstone or Studio Track research project. ~one semester scope.

## The pitch (one sentence)

Can we drive down MediaPipe's hand-tracking noise by combining the data from two ordinary webcams pointed at the same hands, **without any camera calibration**?

## Background — what's already known

PPParty V2 (David's puppet-show Blender addon, single-webcam version) tracks fingers via Google MediaPipe. The tracker works, but fingertip joint angles are about **300× noisier than body bones** (measured 2026-04-30: fingertip mean frame-to-frame quaternion delta 0.30-0.44, body bones 0.001-0.004). On the rig, this looks like fingers vibrating even when the hand is held still.

A side-experiment ran in the basement on 2026-05-01: two cameras pointed at the same hand, eyeball-comparing the per-camera MediaPipe overlay. Per-camera quality looked identical, so the spike was parked from the V2 main path.

But the eyeball test didn't actually test the interesting hypothesis. The interesting hypothesis is **fusion**: even if each camera alone has the same noise floor, if the per-frame errors between cameras are *independent* (different angles → different per-frame errors on the same finger), averaging the two streams can reduce noise by ~30% (1/√2). The eyeball test only looked at each camera alone.

## The "no calibration" trick

Traditional multi-camera tracking (FreeMoCap-style) requires a Charuco-board calibration to compute where each camera is in 3D world space. That's a barrier to deployment.

MediaPipe's `hand_world_landmarks` are different: they're already in **wrist-local 3D coordinates in meters**. Origin = the wrist of the hand it's tracking. So both cameras produce the same 21 finger-joint coordinates relative to the same wrist (plus noise) without ever needing to know where the cameras are in space. **Fusion in hand-local frame is calibration-free for hands specifically.**

## Why it matters

- **For HIHO/CACHE deployment:** if fusion works, e-waste webcams cost effectively nothing — kids could plug in two old USB cams for cleaner puppet performances. (Caveat: compute load is real — see "deployment caveat" below.)
- **For the dissertation:** quantifiable noise reduction on a tractable open-source pipeline is publishable in either direction (positive or negative result).
- **For the student:** bounded scope, clean experimental design, every phase is measurable.

## What a clean version of the project looks like

### Phase 1 — Capture (~2 weeks)

Modify both senders to log landmark data to JSON files at 30 Hz:
- `mediapipe_sender.py` (Cam 1) and `hand_sender.py` (Cam 2)
- Each frame writes: timestamp, all 21 `hand_world_landmarks` (x/y/z), MediaPipe's per-landmark visibility scores
- ~50 lines per sender; the existing senders are already structured to make this easy

Run synchronized capture sessions: hold hand still in different poses (open palm, fist, peace sign, finger spell letters), 30-60 seconds each, multiple lighting conditions, multiple camera angle pairs.

### Phase 2 — Analysis (~3 weeks, no Blender involvement)

Python notebook (Jupyter, pandas, numpy):
- Pair frames across cameras by closest timestamp (max ~33ms drift at 30fps)
- Per landmark per camera: compute frame-to-frame variance (the noise metric)
- Per landmark across cameras: compute correlation of the per-frame error
- **The big question:** is the noise independent (correlation near 0) or correlated (correlation near 1)?
- Visualize where on the hand the cameras agree vs. disagree

If correlations are near 1 across the board, fusion can't help — write up the negative result and ship.

### Phase 3 — Fusion prototype (~3 weeks)

Three algorithms, increasing in cleverness:
1. **Simple mean** — average each landmark coordinate across the two cameras. Baseline.
2. **Confidence-weighted mean** — MediaPipe gives per-landmark visibility scores. Weight each cam's contribution by its own confidence.
3. **Outlier rejection** — if the two cameras strongly disagree on a landmark, throw out the lower-confidence one or fall back to the previous frame.

Compare each fused output against single-camera baseline using the same noise metric from Phase 2.

### Phase 4 — Rig demo (optional, ~2 weeks)

If fusion shows real noise reduction in the numbers, write a small Blender receiver that consumes the fused stream and drives PPParty V2's hand bones. Watch the puppet's fingers actually move. This is the "wow factor" deliverable but not strictly necessary for the research result.

## What success looks like

**Publishable in either direction:**

- **Positive:** "Confidence-weighted fusion of two uncalibrated MediaPipe streams reduces fingertip noise by Xx without any camera calibration step" → method paper, applicable beyond just puppets.
- **Negative:** "Per-frame errors between MediaPipe streams from independent cameras are highly correlated; naive fusion does not improve noise floor" → useful negative result; tells the field where NOT to spend effort.

## Deployment caveat (for honest framing in the writeup)

Even if fusion works on the M3 development machine, the basement test showed **24-27 FPS at 2× full Pose+Hand compute** — already over the 30 FPS target. On HIHO/CACHE deployment hardware (e-waste laptops, ~8 GB RAM, integrated GPU), this is worse. So: a positive result is publishable but doesn't immediately ship to PPParty V2.

The unwritten "hand-only sender variant" (~30 lines stripping Pose from `hand_sender.py`) would land closer to 1.4× compute and might fit. That's a worthwhile sub-task either way.

## Prerequisites for the student

- Python comfortable (no ML/CV expertise needed — MediaPipe handles the hard parts)
- Pandas / numpy basic familiarity
- Jupyter notebook
- Willing to learn MediaPipe Tasks API (the senders already use it; reading the existing code is the tutorial)
- Blender knowledge optional — only needed for Phase 4

## Existing artifacts (already in tree)

- [`spike/dual_cam_test.py`](dual_cam_test.py) — launcher that runs both senders simultaneously (30 lines, parse-clean)
- [`spike/IPHONE_CONTINUITY_CAMERA_HOWTO.md`](IPHONE_CONTINUITY_CAMERA_HOWTO.md) — setup guide for using an iPhone as Cam 2
- [`spike/SPIKE_PLAN.md`](SPIKE_PLAN.md) — original design document
- `mediapipe_sender.py` and `hand_sender.py` (one folder up) — the two senders to instrument with JSON logging
- `FREEMOCAP_RESEARCH.md` (one folder up) — covers the multi-cam triangulation literature; useful background

## Why this idea got parked from V2 main path

Not because the hypothesis was disproven — the proper fusion test was never run. Parked for pragmatic reasons: FPS budget, operational complexity for K-12 deployment, and unfavorable cost-benefit vs. the queued single-cam noise levers (palm-normal `side_ref` as a guaranteed win on existing Pass 1).

The research question stands. It's just decoupled from PPParty V2's near-term deliverable timeline. That decoupling is exactly what makes it a good student project — they can succeed or fail without affecting the addon shipping.
