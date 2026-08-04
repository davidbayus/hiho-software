"""Standalone FreeMoCap processor for HIHO MOCAP's headless build.

Runs INSIDE the freemocap-env (current FreeMoCap), launched by Blender as a
subprocess, so the version-sensitive solve never runs inside Blender. Writes
output_data/ into the recording folder.

FreeMoCap's own per-stage logging goes to stdout/stderr, which Blender captures
for the progress bar. This script adds explicit marker lines Blender keys on:
    HIHO_INFO::<msg>    progress note
    HIHO_DONE::<path>   success, payload is the recording folder
    HIHO_ERROR::<msg>   failure

Usage:
    python process_take.py --recording <folder> --calibration <toml> [--check]

--check verifies imports + folder + parameter construction, then exits BEFORE
the solve. Used to fast-validate the wiring without waiting for a full process.
"""
import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

DONE = "HIHO_DONE::"
ERROR = "HIHO_ERROR::"
INFO = "HIHO_INFO::"

# On-disk sentinels written into the recording folder. FreeMoCap spawns child
# processes that inherit our stdout and outlive us, so the pipe never reaches
# EOF and the watcher in Blender can miss the HIHO_DONE:: marker. A file on disk
# is an unambiguous done signal the watcher can poll for instead.
DONE_FILE = "HIHO_DONE.txt"
ERROR_FILE = "HIHO_ERROR.txt"
QUALITY_FILE = "PROCESS_QUALITY.txt"


def _emit(prefix: str, msg: str) -> None:
    print(f"{prefix}{msg}", flush=True)


def _clear_sentinels(recording: Path) -> None:
    """Remove sentinels from any prior run, so their presence always means THIS
    run finished (otherwise a stale file would report a false instant-done)."""
    for name in (DONE_FILE, ERROR_FILE, QUALITY_FILE):
        try:
            (recording / name).unlink()
        except OSError:
            pass


def _write_sentinel(recording: Path, name: str, content: str) -> None:
    """Write a sentinel atomically (temp file + rename) so the watcher never
    reads a half-written file."""
    try:
        fd, tmp = tempfile.mkstemp(dir=str(recording), prefix=".hiho_tmp_")
        with os.fdopen(fd, "w") as handle:
            handle.write(content)
        os.replace(tmp, recording / name)
    except OSError:
        pass


def _score_quality(reproj_npy: Path) -> str:
    """Verdict from MEDIAN reprojection error in pixels. Median, not mean:
    a handful of broken triangulation points at the volume edge can blow the
    mean up by orders of magnitude (4.5M px on 2026-07-17 while the median
    was a solidly-good 15.75px) and produce false "recalibrate" advice.
    Bands re-derived from all 20 takes on disk 2026-07-18
    (PROCESS_QUALITY_SCORE_DESIGN addendum): known-good era medians 8.7-22.9,
    bumped-camera takes 27.7/58.3, old no-groundplane rig 62-71.
    Bands are 720p60-specific - re-derive if format changes."""
    try:
        import numpy as np
        e = np.load(reproj_npy)
        mean = float(np.nanmean(e))
        median = float(np.nanmedian(e))
        p95 = float(np.nanpercentile(e, 95))
    except Exception as exc:
        return f"Quality: unknown (could not read reprojection error: {exc})\n"
    if median <= 25:
        verdict = f"Quality: GOOD (median reprojection {median:.1f}px)"
    elif median <= 50:
        verdict = (f"Quality: CHECK ({median:.1f}px) - worse than usual. Dim light / "
                   "low contrast, or a camera may have been nudged.")
    else:
        verdict = (f"Quality: BAD ({median:.1f}px) - cameras and calibration disagree. "
                   "A camera has likely moved: recalibrate.")
    return f"{verdict}\nmean {mean:.2f}px  median {median:.2f}px  p95 {p95:.2f}px\n"


def _reshape(recording: Path) -> None:
    """Ensure synchronized_videos/ exists. FreeMoCap expects the videos there;
    the recorder writes them flat as Camera_*.mp4. Symlink, non-destructively."""
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
    ap.add_argument("--calibration", required=True)
    ap.add_argument("--check", action="store_true")
    # Default must be the desired behavior: the Blender panel passes no flags
    # (1.4.14 lesson), so whatever this defaults to is what students get.
    ap.add_argument("--outlier-rejection", choices=("on", "off"), default="on")
    args = ap.parse_args()

    recording = Path(args.recording).expanduser()
    calibration = Path(args.calibration).expanduser()

    if not recording.is_dir():
        _emit(ERROR, f"recording folder not found: {recording}")
        return 2

    # From here on the recording folder exists, so every exit can drop a
    # sentinel. Clear any from a prior run first.
    _clear_sentinels(recording)

    def _fail(msg: str, code: int) -> int:
        _emit(ERROR, msg)
        _write_sentinel(recording, ERROR_FILE, msg)
        return code

    if not calibration.is_file():
        return _fail(f"calibration not found: {calibration}", 2)

    _reshape(recording)

    _emit(INFO, "importing freemocap")
    try:
        from freemocap.core_processes.process_motion_capture_videos.process_recording_folder import (
            process_recording_folder,
        )
        from freemocap.data_layer.recording_models.post_processing_parameter_models import (
            ProcessingParameterModel,
        )
        from freemocap.data_layer.recording_models.recording_info_model import (
            RecordingInfoModel,
        )
    except Exception as exc:
        return _fail(f"freemocap import failed: {type(exc).__name__}: {exc}", 3)

    recording_info = RecordingInfoModel(recording_folder_path=str(recording))
    recording_info.calibration_toml_path = str(calibration)
    params = ProcessingParameterModel(recording_info_model=recording_info)
    params.anipose_triangulate_3d_parameters_model.use_triangulate_outlier_rejection = (
        args.outlier_rejection == "on"
    )
    _emit(INFO, f"outlier rejection: {args.outlier_rejection}")

    # FreeMoCap's position pre-filter defaults to 30 fps; our takes are 60. Left
    # at the default, the intended 7 Hz cleanup effectively cuts ~14 Hz and the
    # surviving 8-14 Hz band is exactly where hand jitter lives (AUDIT_2026-08-04).
    fps = 30.0
    try:
        with open(recording / "HIHO_RECORDING_INFO.json", encoding="utf-8") as fh:
            fps = float(json.load(fh)["fps"]) or 30.0
    except (OSError, ValueError, KeyError):
        pass  # pre-sidecar take: FreeMoCap's own default stands
    params.post_processing_parameters_model.framerate = fps
    params.post_processing_parameters_model.butterworth_filter_parameters.sampling_rate = fps
    _emit(INFO, f"position pre-filter clocked at {fps:g} fps")

    if args.check:
        _emit(DONE, "check: imports + params OK")
        return 0

    _emit(INFO, "processing")
    try:
        process_recording_folder(
            recording_processing_parameter_model=params,
            use_tqdm=False,
        )
    except Exception as exc:
        return _fail(f"process failed: {type(exc).__name__}: {exc}", 4)

    # Validate the SAME file set the Blender-side loader requires, so an
    # incomplete solve fails here — at processing time, with the cause in
    # view — rather than later at Spawn Rig (audit M13).
    out = recording / "output_data"
    required = {
        "body": out / "mediapipe_body_3d_xyz.npy",
        "right hand": out / "mediapipe_right_hand_3d_xyz.npy",
        "left hand": out / "mediapipe_left_hand_3d_xyz.npy",
        "reprojection error": out / "raw_data" / "mediapipe_3dData_numFrames_numTrackedPoints_reprojectionError.npy",
    }
    missing = [label for label, p in required.items() if not p.is_file()]
    if missing:
        return _fail(
            f"finished but the output is incomplete (missing: {', '.join(missing)}) "
            f"in {out}", 5,
        )
    # Quality verdict goes on disk BEFORE the done sentinel, so the Blender
    # watcher can always read it the moment it sees HIHO_DONE.txt.
    quality = _score_quality(required["reprojection error"])
    _write_sentinel(recording, QUALITY_FILE, quality)
    _emit(INFO, quality.splitlines()[0])

    body = required["body"]
    _write_sentinel(recording, DONE_FILE, str(body))
    _emit(DONE, str(body))
    return 0


if __name__ == "__main__":
    sys.exit(main())
