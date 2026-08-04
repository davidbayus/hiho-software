"""Standalone calibration solver for HIHO MOCAP's headless build.

Runs INSIDE the freemocap-env, launched by Blender as a subprocess, so the
version-sensitive anipose solve never runs inside Blender. Reads the recorded
Charuco-board videos and produces a camera calibration .toml. FreeMoCap saves
that toml to the calibrations folder, the recording folder, AND as
last_successful_calibration.toml (so it becomes the default calibration).

The solve uses the board's opening position — flat on the floor, still,
visible to all cameras for the first ~5 seconds — as the world origin and
up-axis (ground-plane calibration). If that opening view is missing, it falls
back to the camera-0 origin and records why in GROUNDPLANE_STATUS.txt.

Markers Blender keys on: HIHO_INFO:: / HIHO_DONE::<toml path> / HIHO_ERROR::<msg>
Also drops HIHO_DONE.txt / HIHO_ERROR.txt sentinels in the recording folder, the
same robust done-detection process_take.py uses (FreeMoCap's child processes can
hold the stdout pipe open). The sentinel helpers mirror process_take.py.

Usage:
    python calibrate.py --recording <folder> [--board 5x3|7x5] [--square-mm 100] [--check]

--check verifies imports + board construction, then exits BEFORE the solve.
"""
import argparse
import os
import sys
import tempfile
from pathlib import Path

DONE = "HIHO_DONE::"
ERROR = "HIHO_ERROR::"
INFO = "HIHO_INFO::"
DONE_FILE = "HIHO_DONE.txt"
ERROR_FILE = "HIHO_ERROR.txt"


def _emit(prefix: str, msg: str) -> None:
    print(f"{prefix}{msg}", flush=True)


def _clear_sentinels(recording: Path) -> None:
    for name in (DONE_FILE, ERROR_FILE):
        try:
            (recording / name).unlink()
        except OSError:
            pass


def _write_sentinel(recording: Path, name: str, content: str) -> None:
    try:
        fd, tmp = tempfile.mkstemp(dir=str(recording), prefix=".hiho_tmp_")
        with os.fdopen(fd, "w") as handle:
            handle.write(content)
        os.replace(tmp, recording / name)
    except OSError:
        pass


def _camera_heights_m(toml_path: Path) -> list:
    """Solved camera heights above the floor, in meters (world z of each
    camera center, -R^T t). Only meaningful for a groundplane-success solve,
    where the board's floor position IS the world origin/up."""
    import tomllib

    import cv2
    import numpy as np

    with open(toml_path, "rb") as fh:
        data = tomllib.load(fh)
    heights = []
    for key in sorted(data):
        cam = data[key]
        if not key.startswith("cam") or "rotation" not in cam:
            continue
        rot, _ = cv2.Rodrigues(np.array(cam["rotation"], dtype=float))
        center = -rot.T @ np.array(cam["translation"], dtype=float)
        heights.append(round(float(center[2]) / 1000.0, 2))
    return heights


def _groundplane_flip_status(toml_path: Path) -> str:
    """'' if cameras sit above the floor; a loud FAILED message if the
    charuco groundplane picked the flipped side of the planar pose ambiguity
    (all cameras underground, 2026-07-03 incident). A parse hiccup must never
    fail a good calibration: returns a skipped-note instead of raising."""
    try:
        heights = _camera_heights_m(toml_path)
        if not heights:
            return " (height check skipped: no cameras found in toml)"
        listed = ", ".join(f"{h}m" for h in heights)
        if min(heights) <= 0:
            return (f"FAILED: world is flipped upside down (camera heights "
                    f"read {listed} — all cameras should be ABOVE the floor). "
                    "The board was seen too small or too edge-on. Re-record "
                    "calibration with the board's opening spot central and "
                    "large in every camera's view.")
        return f"; cameras above floor at {listed}"
    except Exception as exc:  # noqa: BLE001 — never sink a good solve
        return f" (height check skipped: {type(exc).__name__}: {exc})"


def _reshape(recording: Path) -> None:
    """Ensure synchronized_videos/ exists (FreeMoCap expects the board videos
    there; the recorder writes them flat as Camera_*.mp4). Symlink, non-destructively."""
    sync = recording / "synchronized_videos"
    if sync.exists():
        return
    flat = sorted(recording.glob("Camera_*.mp4"))
    if not flat:
        return
    sync.mkdir()
    for mp4 in flat:
        link = sync / mp4.name
        try:
            link.symlink_to(mp4)
        except OSError:
            import shutil
            shutil.copy2(mp4, link)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--recording", required=True)
    ap.add_argument("--board", default="5x3", choices=["5x3", "7x5"])
    ap.add_argument("--square-mm", type=float, default=100.0)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    recording = Path(args.recording).expanduser()
    if not recording.is_dir():
        _emit(ERROR, f"recording folder not found: {recording}")
        return 2

    _clear_sentinels(recording)

    def _fail(msg: str, code: int) -> int:
        _emit(ERROR, msg)
        _write_sentinel(recording, ERROR_FILE, msg)
        return code

    _reshape(recording)
    sync = recording / "synchronized_videos"
    if not sync.is_dir() or not list(sync.glob("Camera_*.mp4")):
        return _fail(f"no synchronized_videos/Camera_*.mp4 in {recording}", 2)

    _emit(INFO, "importing freemocap")
    try:
        from freemocap.core_processes.capture_volume_calibration.run_anipose_capture_volume_calibration import (
            run_anipose_capture_volume_calibration,
        )
        from freemocap.core_processes.capture_volume_calibration.charuco_stuff.charuco_board_definition import (
            charuco_5x3,
            charuco_7x5,
        )
    except Exception as exc:
        return _fail(f"freemocap import failed: {type(exc).__name__}: {exc}", 3)

    board = charuco_5x3() if args.board == "5x3" else charuco_7x5()

    if args.check:
        _emit(INFO, f"board={board.name} "
                    f"squares={board.number_of_squares_width}x{board.number_of_squares_height} "
                    f"square_mm={args.square_mm}")
        _emit(DONE, "check: imports + board OK")
        return 0

    _emit(INFO, f"calibrating ({board.name}, {args.square_mm}mm squares)")
    try:
        toml_path, groundplane = run_anipose_capture_volume_calibration(
            charuco_board_definition=board,
            charuco_square_size=args.square_mm,
            calibration_videos_folder_path=str(sync),
            # Pin stays on: upstream applies it first, then the groundplane on
            # top, so a failed floor detection falls back to today's behavior.
            pin_camera_0_to_origin=True,
            use_charuco_as_groundplane=True,
            progress_callback=lambda m: _emit(INFO, str(m)),
        )
    except Exception as exc:
        return _fail(f"calibration failed: {type(exc).__name__}: {exc}", 4)

    toml_path = Path(toml_path)
    if not toml_path.is_file():
        return _fail(f"finished but no calibration toml at {toml_path}", 5)

    # Upstream reverts to the camera-0 origin SILENTLY when the board's opening
    # floor view is missing; say so loudly (see GROUNDPLANE_SOLVE_DESIGN doc).
    if groundplane is not None and getattr(groundplane, "success", False):
        gp_status = "OK: origin and up-axis set from the board's opening floor position"
        # Upstream also reports OK when the planar pose ambiguity flipped the
        # whole world underground (2026-07-03 incident). Cameras-above-floor
        # is the invariant that catches it at solve time
        # (GROUNDPLANE_SANITY_CHECK_DESIGN_2026-07-04.md).
        flip = _groundplane_flip_status(toml_path)
        gp_status = flip if flip.startswith("FAILED") else gp_status + flip
    else:
        reason = (getattr(groundplane, "error", None)
                  or "no still, all-camera view of the board at the start")
        gp_status = (f"FAILED: {reason}. Calibration is still valid (camera-0 "
                     "origin). For a floor-true solve, re-record with the board "
                     "flat on the floor, still and visible to all cameras for "
                     "the first 5 seconds.")
    _emit(INFO, f"groundplane {gp_status}")
    _write_sentinel(recording, "GROUNDPLANE_STATUS.txt", gp_status)
    _write_sentinel(recording, DONE_FILE, str(toml_path))
    _emit(DONE, str(toml_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
