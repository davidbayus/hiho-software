# Honest Processing Progress Clock — Design Note (2026-07-18)

**Status:** 1.4.28 candidate. Backlog item 2 from the 2026-07-17 session
(after the scorer median fix, before the volume-checker panel work).

## The problem

The progress bar is stage-based: five FreeMoCap log lines map to
20/40/60/80/95%. But the first stage — 2D detection — is ~90% of the wall
time (one MediaPipe pass per camera, sequential). On a 6-camera 120s take
the bar sits at "Detecting 2D landmarks (20%)" for ~55 minutes, then
sprints to done in the last two or three. The number on the board is fake
for most of the run. Same silent-state family as the badge work: the panel
should tell the truth or say nothing.

## What's observable (verified on disk, 2026-07-17 takes)

FreeMoCap writes `annotated_videos/Camera_X_mediapipe.mp4` one camera at a
time as detection proceeds:

- 120s take `13-28-17`: files land 13:40, 13:49, 13:58, 14:07, 14:17,
  14:27 — one every ~9.3 min.
- 60s take `15-23-33`: one every ~4.9 min.
- **Camera order is NOT guaranteed** (the 60s take finished Camera_2
  first, Camera_1 last). Count files; never assume order.
- The file being written already exists in the folder and grows, so at any
  moment: files with older mtimes are complete, the newest is in-progress.
- `HIHO_RECORDING_INFO.json` in the take folder has `camera_ids` (count)
  and `duration_sec`.

## The design

The disk watcher lives in `ExternalProcessRunner` behind a
`watch_detection=True` flag that only the Process operator passes (the
calibrate solve keeps the plain line-driven behavior). One source of truth:
the runner's existing `progress_pct` / `current_stage` surface; the poll
timer and panel don't change.

**Counting rule:** only annotated files with mtime AFTER the runner
started count (reprocessing a take that already has annotated videos from
a previous run must not read 6/6 instantly). Among counted files, all but
the newest are complete; the newest is the camera in progress.

**Bar mapping (monotonic, 100% reserved for the DONE sentinel as today):**

- Detection owns 5% → 90%:
  `pct = 5 + 85 × (complete + partial) / N`
  where `partial` is the in-progress camera's elapsed time over the
  per-camera pace, capped at 0.9.
- Later stages are quick and stay line-driven, rescaled:
  triangulating 92, post-processing 94, center of mass 96, saving 98.

**Per-camera pace:** measured live — first completed file's mtime minus
detection start gives the real pace, refined as more cameras land
(average). Before any camera completes, seeded by the rule of thumb
measured above: `duration_sec × 4.5` seconds per camera (720p60; same
caveat as the quality bands — re-derive if the format changes).

**Stage text (this is the part David actually reads):**

    Detecting: camera 3 of 6 (~25 min left)

Minutes-left = pace × cameras remaining (including the rest of the current
one), rounded to whole minutes, "~" prefix. Under a minute: "almost done".
No decimals, no seconds — a number a person glances at, not a stopwatch.

## Cost

The watcher is a `listdir` of a ≤10-file folder + a few `stat` calls per
poll (0.5s). Nothing.

## Out of scope

- Progress % inside a single camera from file-size growth (bytes vs
  completed-camera sizes). The elapsed/pace interpolation is honest enough;
  revisit only if the in-camera crawl bothers anyone.
- Streaming FreeMoCap's tqdm output (uses \r rewrites the line reader
  never sees; not worth fighting).
- ETA on calibrate solves (fast; not where the lie was).

## Verification plan (user's path, at BASEMENT today)

Process a real take with the panel visible:
1. Bar leaves 5% only when the first annotated file lands; text counts
   cameras up: 1 of 6, 2 of 6, ...
2. Minutes-left shrinks and stays plausible against a wall clock.
3. After detection, stages tick 92 → 94 → 96 → 98, DONE → 100.
4. Reprocess the SAME take immediately: bar must start at 5%, not 90%
  (stale-file guard).
