# Process Quality Score — Design Note (2026-07-03, BASEMENT)

**Status:** Shipped in 1.4.19. **Amended 2026-07-18: verdict now keys off MEDIAN, not mean — see addendum at bottom.**
**Why now:** today a camera moved sometime before the 14:26 take. Nothing in
the addon said so. The solve completed "successfully" with 4× the geometric
error of yesterday and heels 6.6cm underground — invisible until Claude
hand-measured the npy. David's ask, verbatim: "we need to know in the addon
if we get reprojection errors at that level... put a score on the board for
when processing completes." Same silent-failure theme as the 2026-06-09
audit and the groundplane fix: never guess silently, report loudly.

## What the score is

Mean reprojection error, in pixels, across the whole take — how well the
four cameras' views agree with each other through the calibration. It's
already computed by every solve and saved in
`output_data/raw_data/mediapipe_3dData_..._reprojectionError.npy`; we're
just reading what's already on disk and saying it out loud. High score with
good lighting = the calibration no longer matches physical reality (a
camera moved). This is the number that caught today's problem.

## Verdict bands (from every processed take on disk, 2026-07-03)

Real data, 4-cam BASEMENT rig:

| Era | Takes | Mean reprojection |
|---|---|---|
| Floor-true 720p60 (the good recipe) | Jul 2 ×3, Jun 7 | 15–22 |
| Today's bumped-camera takes | Jul 3 ×2 | 47, 68 |
| Old ring arrangement, no groundplane | Jun 1 ×3 | 74–84 |

Bands, with daylight between clusters:

- **≤ 30 → GOOD** — "Quality: GOOD (mean reprojection 17.4px)"
- **30–50 → CHECK** — "Quality: CHECK (41px) — worse than usual. Dim light /
  low contrast, or a camera may have been nudged."
- **> 50 → BAD** — "Quality: BAD (68px) — cameras and calibration disagree.
  A camera has likely moved: recalibrate."

**Caveat recorded here:** bands are calibrated for 720p60 4-cam. Pixel
errors scale with resolution — if the format ever changes, re-derive the
bands (the table above is the recipe: measure known-good takes, split the
clusters).

## The change (1.4.19)

1. **`external/process_take.py`** — after the existing output validation
   (it already touches the reprojection npy path), load it, compute
   mean/median/p95, pick the verdict, then:
   - write **`PROCESS_QUALITY.txt`** into the take folder (the
     GROUNDPLANE_STATUS.txt pattern — on-disk truth, survives everything),
   - emit the verdict as an INFO line.
2. **Blender side (`operators/process.py` + panel)** — when the DONE
   sentinel lands, read `PROCESS_QUALITY.txt` and put the verdict line on
   the board: panel status text, and a `process_verdict` scene property
   displayed the same way `calibration_verdict` already is. CHECK/BAD show
   as warnings. Missing file (legacy takes) = show nothing, no guess.

No solve behavior changes. No new dependencies (numpy already required in
the env; Blender side only reads a text file).

## Verification plan (user's path)

Free test, already scheduled: David is recalibrating right now. Reprocess
today's `14-38-05` take copy against the new calibration via the panel —
the board should read GOOD with a score near yesterday's ~17. The existing
bad solve (68px) reprocessed pre-recalibration would read BAD. Both bands
exercised on real data, no extra takes needed.

## Out of scope

- Per-joint or per-camera breakdown (points at WHICH camera moved — nice
  Tier-2 idea, logged, not now).
- Auto-blocking Send to Character on BAD (report loudly, let the artist
  decide — dogfooding rule: David is user #1).
- The sidecar read on the Spawn Rig path (that's the next build, 1.4.20).

---

## Addendum 2026-07-18 — verdict keys off MEDIAN (1.4.26)

**The bug (found live 2026-07-17, perimeter take `13-28-17`):** a handful of
catastrophically broken triangulation points at the volume edge produced
near-infinite reprojection values. The raw mean read **4,506,749px** and the
badge said "BAD — recalibrate." The same take's **median was 15.75px —
solidly GOOD** — and the calibration was verifiably fine (same-hour board
solve: 0.40px Excellent). David caught it by eye: "motion is better than
expected — I think the reader is wrong." Third documented eyes-beat-instrument
incident. The mean is not a robust statistic; one broken point can poison it.

**The fix:** the verdict keys off the **median**, which the scorer already
computes and prints. The full mean/median/p95 line stays in
`PROCESS_QUALITY.txt` unchanged — only which number drives the verdict (and
appears in the badge) changes.

**Median bands, re-derived from every take on disk (20 takes, 2026-07-18):**

| Era | Takes | Median reprojection |
|---|---|---|
| Known-good (floor-true 720p60 recipe) | Jun 7, Jul 2 ×3, Jul 5 ×2, Jul 13, Jul 15 ×3, Jul 17 ×2 | 8.7 – 22.9 |
| Bumped-camera day (what the score exists to catch) | Jul 3 `14-26-11`, `14-38-05` | 27.7, 58.3 |
| Old ring, no groundplane | Jun 1 ×3 | 62 – 71 |

- **≤ 25 → GOOD**
- **25 – 50 → CHECK**
- **> 50 → BAD**

Every historical verdict that was CORRECT under the mean stays the same under
these bands. The two false alarms flip to GOOD:

- Jul 13 `12-20-00`: mean 915px (poisoned) → median 22.9px GOOD
- Jul 17 `13-28-17`: mean 4.5Mpx (poisoned) → median 15.8px GOOD

Both bumped-camera takes still flag (27.7 CHECK, 58.3 BAD); all June 1
no-groundplane takes still read BAD.

**Same caveat as before:** bands are 720p60-specific. If the format changes,
re-derive by the same recipe — measure known-good takes, split the clusters.

**Out of scope, logged:** a companion "a few points exploded" note when mean
diverges wildly from median (e.g. mean > 10× median) — could point at
volume-edge excursions. Wait for the volume-checker panel work; don't bolt it
on here.
