# ESC Early-Stop Design — frame-count equalization (audit S5)

**Date:** 2026-06-09 · **Status:** implemented in 1.3.14 · **Scope:** `core/camera_manager.py`, `external/record_take.py`

## Problem

FreeMoCap rejects a take whose cameras differ by even one frame (BUGS_AND_BACKLOG #5). The recorder guarantees equal counts only on the auto-stop path (every camera writes exactly `duration × fps` frames). The ESC early-stop path closed each camera's writer at whatever count it happened to have reached — at an arbitrary instant the four counters almost never agree — so a normal, UI-advertised action produced an unprocessable take that failed minutes later at Process with a cryptic error. Bonus defect: ESC was dead during the countdown (key events discarded), so an accidental Record couldn't be aborted at all.

## Options considered

1. **Trim down (rewrite files post-stop).** Re-open each overlong mp4 and rewrite it at the minimum count. Rejected: re-encoding costs quality (mp4v generation loss) and time proportional to take length, and adds a whole new failure surface (partial rewrites) on students' recorded data.
2. **Equalize up (let laggards finish).** At ESC time the capture threads are still running and frames are still flowing. So: snapshot the highest frame count any camera has reached, re-target every still-writing camera to that count, and let them write the few extra frames (~one frame interval of wall time). This rides the *same* target-frames auto-stop machinery the full-duration path already uses — proven live at the rig — and never touches bytes already on disk.

**Chosen: equalize up.** No re-encode, no rewrite, minimal new code, and the equalization mechanism is the existing, rig-proven stop condition.

## Failure handling

- A camera that can't reach the target within `timeout_sec` (default 3 s — e.g. it died mid-take) is cut off where it is. The mismatch is then **reported loudly**: `record_take.py` checks the final counts and emits `HIHO_ERROR::cameras ended with mismatched frame counts {...}` instead of `HIHO_DONE`, so the panel (S6 watch) shows a real failure instead of a take that quietly won't process. The files stay on disk for inspection.
- ESC during the countdown now aborts cleanly: cameras stop, window closes, `HIHO_DONE::cancelled` (not a path) — the S6 poll reports "no take recorded" and sets no take path.

## Also in this change

`ExternalProcessRunner.stop()` sets the cancelled state **before** killing the process (was: after). The pipe EOF lands in the reader thread the instant the process dies, and its exit-code branch must find `_error` already set — otherwise a fast EOF could race in a "backend exited with code -15" message where "Capture window closed." belongs. Same mechanism family (clean stopping), cosmetic-level impact.

## Test plan

- `MOCAP_CALIBRATION_FILES/test_equalize_stop.py` (run with the freemocap-env python; no cameras — capture threads are simulated by pump threads feeding synthetic frames through the real writer machinery):
  1. Three "cameras" with deliberately diverged counts, pumps running → `stop_recording()` → all counts equal, and the **mp4 files on disk** verified frame-accurate via cv2.
  2. Dead camera (no pump) → `stop_recording(timeout_sec=0.5)` returns fast (no hang) with the mismatch exposed.
- Countdown-ESC and the live window behavior can't be exercised headless → **Verify-at-BASEMENT list**: ESC mid-take must produce a processable take; ESC during countdown must abort with "no take recorded"; pull a USB cable mid-take and confirm the loud mismatch error.
