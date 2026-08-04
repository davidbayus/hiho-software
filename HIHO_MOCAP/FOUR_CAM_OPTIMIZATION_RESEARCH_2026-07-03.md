# Four-Camera Setup Optimization — Research (2026-07-03, evening)

**Status:** RESEARCH ONLY — feeds future design notes, no code yet.
**Trigger:** David, heading home after the drift + groundplane-flip day: "see if
there's something we can do to better optimize our four camera setup." His
read that the pushed performance (fast movement, floor work) caused the extra
noise/dropout is CONFIRMED by the sources — that's the hardest case for this
pipeline, and 4 cameras is the lean end for it.

**Sources:** two parallel research passes — FreeMoCap official docs + Jon
Matthis's tutorial notes, and the adjacent projects (Pose2Sim, Anipose,
OpenCV/IPPE, C922 tooling). The Discord itself is login-walled; Matthis's
public HackMD notes and the docs' troubleshooting pages are its public echo.
Confidence tagged per item: [OFFICIAL] docs, [MAINTAINER] Matthis, [PAPER],
[ANECDOTE], [INFERENCE].

---

## 1. What we're already doing right (validated, don't churn)

- **40–60° neighbor spacing** — exactly the official recommendation. [OFFICIAL]
- **4 cameras is a legitimate rig** — Pose2Sim validated "very robust with as
  little as four cameras" (walking/running). But optimal for "complex motions
  with occlusions" is ~6; floor work at n=4 WILL drop joints sometimes. [PAPER]
- **720p is officially fine** (minimal accuracy loss vs 1080p); **60fps is the
  official minimum for fast motion** — we're at the floor, not above it. [OFFICIAL]
- **Portrait-rotated cameras are sanctioned**; subject should fill the frame. [OFFICIAL]
- **Outlier rejection is officially "recommended for 4+ cameras"** — shipped
  today in 1.4.17. [OFFICIAL]
- **Per-session calibration** — Matthis: camera movement of "even a few mm
  will cause issues"; no drift compensation exists. David's doctrine is the
  maintainer's position. [MAINTAINER]
- **Direct USB per camera, no hubs** — matches our known bandwidth wall. [OFFICIAL]

## 2. Highest-leverage next experiments (cheap, physical/settings)

### 2a. Exposure lock — THE official fast-motion lever
- Official guidance: manual exposure at **-6 maximum, -7 or -8 preferred**
  (UVC log2 scale: -7 ≈ 1/128s, -8 ≈ 1/256s), compensate with MORE LIGHT.
  Shorter shutter = less motion blur = cleaner joints on fast moves. [OFFICIAL]
- Auto-exposure/gain/white-balance drift per-camera and per-minute — lock all
  four manual and IDENTICAL. macOS has no built-in panel, but **`uvcc`**
  (github.com/joelpurra/uvcc, explicitly supports C922) is scriptable:
  set one camera, `uvcc export` JSON, apply to all four. **Settings reset on
  replug/reboot — re-apply at session start.** Natural fit: a
  `HIHO_CAMERA_SETTINGS.command` on the Desktop, part of the session ritual
  (double-click, like the speed test). [TOOL-CONFIRMED + INFERENCE]
- C922 gotcha worth an A/B: reviewers report **heavy noise reduction kicks in
  at 720p60 specifically**, smearing fast motion. Test whether locked short
  exposure + bright light beats the smear; also worth one 1080p30 vs 720p60
  comparison on a fast take (60fps still favored for temporal resolution —
  measure, don't assume). [ANECDOTE, testable with existing tools]

### 2b. Camera height diversity — the floor-work fix
- **David's clarification (2026-07-03):** the cameras are on articulating
  clamp mounts on various pipes/boards along the ceiling — varied hardware,
  but the calibration-solved lens heights still landed within ~9cm of each
  other (1.57–1.66m). "Height diversity" here means a much bigger spread
  (one camera ~0.7–1m lower, waist-ish). Upside of the clamp mounts: the
  experiment needs no new hardware, just a lower clamping point.
- Four lenses at ~1.6m in a front arc = the low-vertical-diversity config
  the multi-view literature warns about: weak vertical baselines (worse Z /
  floor-contact precision than XY) and, during floor work, every camera sees
  a prone body foreshortened from the same elevation. [PAPER + INFERENCE]
- FreeMoCap docs are SILENT on height; closest official rule is "≥2, prefer 3,
  cameras must see every body part" — which an all-high arc violates for
  prone poses. Matthis: "skeleton solvers prefer upright human figures."
  [OFFICIAL + MAINTAINER]
- **Do NOT go overhead** — top-down views officially "do not yield good
  results" (MediaPipe trained on upright people). [OFFICIAL/Pose2Sim]
- Experiment when remounting is palatable: **drop 1–2 cameras to waist/knee
  height** and/or widen the arc so one view sees floor work side-on. This is
  a real remount (ceiling mounts, rotations, enumeration re-check, fresh
  calibration) — David's call on when. [PAPER-backed]

### 2c. Calibration board upgrade — kills two birds
- Official: **bigger board is better**, poster-print endorsed; **5x3 is
  recommended over 7x5** (bigger squares, trackable from farther) — we
  already default 5x3. Measure the printed square edge in mm and use the
  measured value, not nominal. [OFFICIAL + MAINTAINER]
- **The groundplane flip is the OpenCV planar-pose two-fold ambiguity** —
  near-affine views (board small in frame / grazing angle, i.e. a floor board
  seen from ceiling cams) have two valid pose solutions; solvers pick wrong
  ~50% in that regime. FreeMoCap docs list visibility/velocity failures for
  groundplane but NOT the flip — undocumented upstream failure mode, which is
  why it reported OK. [OpenCV/IPPE docs]
- Mitigations, in leverage order: **poster-size board, opening spot central
  and as head-on to cameras as a floor placement allows** (bigger in frame =
  ambiguity vanishes); our queued cameras-above-floor sanity check catches
  the rest. Groundplane searches the **first 120 frames** for a still board
  with 3 corner markers visible — the opening beat of the ritual is exactly
  right. [OFFICIAL + PAPER]

## 3. Software dials to test (in the stack we already ship)

- **Minimum Cameras for Triangulation** (default 3): with 4 cams and floor
  occlusion, a joint seen by only 2 cameras drops out entirely. Lowering to 2
  is the one in-app lever for floor work — accuracy tradeoff, A/B it on a
  floor-work take like today's. [OFFICIAL params + INFERENCE]
- **Target Reprojection Error** (outlier rejection aggressiveness) — soft
  exponential weighting, not binary; tunable if wrists still misbehave. [OFFICIAL]
- **skellytracker confidence** (`min_detection/tracking_confidence`, default
  0.5) and MediaPipe `model_complexity` (default 1; 2 = more accurate,
  slower). Community anecdote: raise tracking confidence to 0.6–0.7 if fast
  motion causes landmark "freezing" — unverified for FreeMoCap, cheap A/B.
  [SOURCE-CODE + ANECDOTE]
- **Pose2Sim's error gates as accept/reject numbers**: intrinsic <0.5px,
  extrinsic <1–2cm. Our calibration score + process score already embody the
  idea; these give literature-backed thresholds to calibrate our bands
  against. [OFFICIAL/Pose2Sim]

## 4. Deeper pipeline candidates (NOT drop-in — design + pipeline work)

- **Anipose's Viterbi filter** (n_back=5; recovers most-likely keypoint paths
  through brief occlusions instead of dropping them) and **limb-length
  constraints** (scale_length=2; stabilizes joints seen by few cameras).
  These live in the anipose CLI layer, NOT in FreeMoCap's pipeline — adopting
  means real integration work. Log under adoptable innovations; revisit
  post-sprint or as a 4D ART CLUB / CS-student project. [OFFICIAL anipose]
- **IPPE_SQUARE solver + ambiguity detection** for the groundplane (returns
  BOTH pose solutions with errors, so a flip is detectable, not silent).
  Upstream-shaped fix — see §5. [OpenCV]

## 5. Upstream opportunity (FreeMoCap relationship)

Nobody has publicly connected the groundplane flip to the planar-ambiguity
literature — the docs don't list it as a failure mode and no issue exists.
After our cameras-above-floor check ships and is field-tested, this is a
ready-made, well-evidenced upstream report (issue + our check as the
suggested fix). Fits the FreeMoCap University arts-collaborator lane and the
adoptable-innovations give-back ethic. Today's calibration folder is the
reproduction case.

## 6. Suggested order of attack (all design-first, post-Jul-7 unless trivial)

1. **uvcc exposure-lock .command** — cheapest, attacks fast-motion blur AND
   appearance drift; official guidance, session-ritual shaped.
2. **Poster-size board + central opening placement** — print cost, kills the
   flip's odds and helps distant detection. (Sanity check build is already
   queued regardless.)
3. **A/B: min-cameras 2 vs 3 on today's floor-work take** — pure reprocess,
   no capture needed, directly targets David's dropout complaint.
4. **Height-diversity remount experiment** — biggest expected floor-work win,
   biggest disruption; schedule deliberately.
5. Anipose filters / IPPE — long-horizon, log and defer.

**Also captured:** session checklist grows — calibrate first; board opening
central; power brick off USB; (future) run camera-settings .command.
