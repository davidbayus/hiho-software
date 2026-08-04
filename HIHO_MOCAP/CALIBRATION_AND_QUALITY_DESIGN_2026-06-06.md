# Calibration Button + Quality Readout — Design (2026-06-06)

**Status:** design, pre-code. David approved a **separate Calibrate button** (not a mode toggle) on 2026-06-06.
**Context:** refining the 1.3.0 headless addon from home. Extends the headless seam built 2026-06-01 ([HEADLESS_FREEMOCAP_DESIGN_2026-06-01.md](HEADLESS_FREEMOCAP_DESIGN_2026-06-01.md)). Closes Bug #9 + the "Capture operator" item in [BUGS_AND_BACKLOG.md](BUGS_AND_BACKLOG.md).

## 0. TL;DR

Two related features, very different testability today:

- **A) Quality readout** — recover the calibration's reprojection error (the pixel-accuracy number FreeMoCap never saves to disk) and show a green/yellow/red badge in the panel. Port of the proven `MOCAP_CALIBRATION_FILES/check_calibration_accuracy.py`. **Fully testable from home off existing files.**
- **B) Calibrate button** — record the Charuco board, run FreeMoCap's calibration solve, write a new calibration `.toml`, then auto-show the (A) badge. Recording needs the cameras, so the live loop is **verify-at-rig**; the code is buildable from home.

Both reuse the existing external-subprocess seam (`core/external_runner.py` + an `external/*.py` script) and the done-sentinel pattern just added for the done-detection fix.

## 1. FreeMoCap entry points (confirmed in 1.8.2, in the env)

- **Calibrate:** `freemocap.core_processes.capture_volume_calibration.run_anipose_capture_volume_calibration.run_anipose_capture_volume_calibration(charuco_board_definition, charuco_square_size, calibration_videos_folder_path, pin_camera_0_to_origin=True, use_charuco_as_groundplane=False, progress_callback=...) -> (toml_path, GroundPlaneSuccess)`. Returns the calibration TOML path directly.
- **Board model:** `...charuco_stuff.charuco_board_definition.CharucoBoardDefinition`. BASEMENT board = 5x3 squares, 100 mm. *Build-time: confirm constructor arg names (squares-wide / squares-tall).*
- **Quality math (already written):** `MOCAP_CALIBRATION_FILES/check_calibration_accuracy.py` — per-camera PnP residual against the known board, mean px error. Uses `aniposelib.cameras.CameraGroup.load(toml)` + the saved `charuco_2dData_...npy`.
- **Paths:** `...path_getters.get_last_successful_calibration_toml_path()` / `get_calibrations_folder_path()`. FreeMoCap's calibrator writes the TOML to the calibrations folder and updates "last successful" itself.

## 2. Verdict scale (from the proven prototype, BASEMENT 4-cam)

| mean reprojection error | verdict | badge |
|---|---|---|
| < 0.5 px | excellent | green |
| 0.5–1.0 px | good | green |
| 1.0–2.0 px | workable | yellow |
| > 2.0 px | recalibrate | red |

Student-facing copy avoids the term "reprojection error": show e.g. *"Calibration quality: Excellent (0.3)"* with the color, and a one-line tooltip ("how closely the cameras agree; lower is better").

## 3. New files

- `external/calibrate.py` — standalone, runs in freemocap-env (mirrors `process_take.py`):
  1. `_reshape()` Camera_*.mp4 -> `synchronized_videos/` (share/copy the helper already in `process_take.py`).
  2. `run_anipose_capture_volume_calibration(...)` on the videos folder.
  3. On success: write **DONE sentinel** (`HIHO_DONE.txt`) with the new toml path; emit `HIHO_DONE::<toml>`. On failure: ERROR sentinel + `HIHO_ERROR::`. (Same robust done-detection as the processing path.)
  4. `--check` validates imports + board construction, no solve.
- `external/score_calibration.py` — thin standalone wrapper around the existing `check_calibration_accuracy.py` math. Input: a calibration TOML + its `charuco_2dData_...npy`. Output: one line `HIHO_QUALITY::<mean_px>::<verdict>`. Keeps heavy numpy/cv2/aniposelib work in the env, out of Blender.
  - *Decision:* copy the scoring math into this script (clean-room from the prototype) rather than import from `MOCAP_CALIBRATION_FILES/` so the addon stays self-contained for the Extensions build. Prototype stays as the reference.

## 4. New operators (`operators/calibration.py`)

- `HIHO_MOCAP_OT_calibrate` — Popen `external/calibrate.py` with the calibration take folder + board params; reuse `ExternalProcessRunner` (or a slim sibling) for polling + sentinel done-detection. On done, store the new toml into `calibration_toml_path` and kick the quality check.
- `HIHO_MOCAP_OT_check_calibration` — Popen `external/score_calibration.py` on the current `calibration_toml_path`; parse `HIHO_QUALITY::` and store `calibration_quality_px` + `calibration_verdict` for the badge. Also runnable on its own (score an existing calibration without re-solving) — this is the from-home-testable path.

Recording a calibration take reuses the existing `external/record_take.py` via a thin "calibration capture" path (same recorder; the human moves the board). No new recorder.

## 5. New properties (`properties.py`)

- `calibration_quality_px: FloatProperty` (default -1 = unknown)
- `calibration_verdict: StringProperty` ("", "excellent", "good", "workable", "recalibrate")
- (calibration take folder can reuse `last_take_path`, or add `calibration_take_path` if we want both a calibration take and a body take staged at once — *decide at build*.)

## 6. UI (`ui/panels.py`) — separate Calibrate button

New **Calibrate** sub-section, above Process (calibration precedes capture in the real workflow):

```
Calibrate
  [ Show Cameras ]            (reuses existing preview op)
  Board: 5x3 @ 100mm          (read-only label for now; props later)
  [ Calibrate ]               -> records board, solves, writes toml
  Calibration quality: Excellent (0.3)   <- colored badge, when known
  [ Check Calibration ]       -> re-scores current toml (no re-solve)
```

Capture / Process / Output sections unchanged.

## 7. Testable today (from home) vs. at-rig

- **Today, off existing files:**
  - `external/score_calibration.py` against the existing May 12 calibration TOML + the `charuco_2dData` npy on disk (under `~/freemocap_data/...`). Confirms the badge number matches the prototype's number.
  - `external/calibrate.py` re-solving an **existing** Charuco recording on disk (the `import_2026-05-09_16-10-40` session has real `synchronized_videos/`). Confirms the solve runs headless + writes the sentinel + produces a TOML, without cameras.
  - `--check` paths for both scripts in the env.
- **At the rig (verify-at-rig):**
  - The full Calibrate button loop: live board recording -> solve -> badge.

## 8. Build order (one change at a time, test after each)

1. `external/score_calibration.py` + a quick number-parity test vs. the prototype. (testable today)
2. `external/calibrate.py` + re-solve an existing charuco session. (testable today)
3. `operators/calibration.py` + `properties.py` props + `ui/panels.py` section. (registers + draws today; live loop at rig)
4. Wire auto-score after calibrate. Verify-at-rig.

## 9. Open / build-time lookups

- `CharucoBoardDefinition` constructor arg names in 1.8.2.
- Where the `charuco_2dData_...npy` lands relative to a take processed via our headless path (the prototype expects FreeMoCap's session-folder layout; our captures live under `~/Desktop/HIHO_CAPTURES/<stamp>/`). Confirm the 2D charuco data path for our folder shape, or have `calibrate.py` emit the score directly at solve time (it has the calibrator object in hand).
- Whether to expose board size as editable props now or keep hardcoded to BASEMENT's 5x3/100mm until a second board exists.
