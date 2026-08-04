# Ground-Plane Solve — Design Note (2026-07-02)

**Context:** BASEMENT recording-side session. David is re-rigging cameras (ring → front arc) and recalibrating. Discovery: FreeMoCap 1.8.2's ground-plane calibration (board flat on floor at the start of the calibration take = world origin + up-axis) is installed in `freemocap-env` but `external/calibrate.py` hardcodes it OFF (`use_charuco_as_groundplane=False`). Every calibration to date has used camera-0's optical center as the origin, which is part of why in-place takes needed the 5-second floor-standing workaround and skeletons tilted.

**Change (one file, `external/calibrate.py`):**
1. Flip `use_charuco_as_groundplane=True`. Keep `pin_camera_0_to_origin=True` — upstream applies pin first, then ground-plane on top, so pin is the automatic fallback.
2. Stop discarding the returned `GroundPlaneSuccess`. Emit an `HIHO_INFO::` line with the outcome and write `GROUNDPLANE_STATUS.txt` into the recording folder. Rationale: the June audit's #1 theme was silent failure; upstream *silently* reverts to camera-0 origin when the board's opening still view is missing, and David would have no way to know his floor didn't take.

**Failure behavior (verified in upstream source, `anipose_camera_calibrator.py`):** `CharucoVisibilityError` / `CharucoVelocityError` are caught upstream; the calibration reverts to the pinned camera-0 solve and returns `success=False` with a reason. So this change is strictly additive — worst case equals today's behavior, plus a visible explanation.

**New calibration ritual this enables:** board flat on the floor, center of volume, visible to all cameras and untouched for the first ~5 seconds of the recording; then pick it up for the normal pair-painting. One board only, ever, in frame.

**Not in this change (post-July-7 candidates):** surfacing ground-plane status as a panel badge next to the calibration-quality badge; a `--no-groundplane` escape flag if a use case appears.

**Test plan:** `py_compile` + `calibrate.py --check` headlessly (imports + board build); real-solve validation on today's first BASEMENT calibration take, watching for the `groundplane` INFO line and `GROUNDPLANE_STATUS.txt`. Version bump 1.4.11 → 1.4.12, fresh zip.
