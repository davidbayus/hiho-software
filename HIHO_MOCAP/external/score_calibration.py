"""Standalone calibration quality scorer for HIHO MOCAP.

Runs in the freemocap-env. Recovers the mean reprojection error (in pixels) that
FreeMoCap computes during calibration but never saves to disk, and prints a
plain-English verdict. The addon runs this as a subprocess and reads the
HIHO_QUALITY:: line to draw the quality badge.

Math is a clean-room port of MOCAP_CALIBRATION_FILES/check_calibration_accuracy.py:
per camera, PnP-solve the known Charuco board against the saved 2D detections,
then measure the pixel residual. Kept self-contained (no import from that
prototype) so the addon ships standalone in the Extensions zip.

Usage:
    python score_calibration.py --toml <calibration.toml> [--charuco-npy <2dData.npy>]
                                [--board-cols 5 --board-rows 3 --square-mm 100]

If --charuco-npy is omitted it is derived from the TOML's session, matching
FreeMoCap's layout (recording_sessions/<session>/output_data/raw_data/).

Markers: HIHO_INFO:: / HIHO_QUALITY::<mean_px>::<verdict> / HIHO_DONE:: / HIHO_ERROR::
"""
import argparse
import os
import sys
import warnings
from pathlib import Path

INFO = "HIHO_INFO::"
QUALITY = "HIHO_QUALITY::"
DONE = "HIHO_DONE::"
ERROR = "HIHO_ERROR::"


def _emit(prefix: str, msg: str) -> None:
    print(f"{prefix}{msg}", flush=True)


def verdict_for(mean_px: float) -> str:
    """BASEMENT 4-cam scale (from the proven prototype)."""
    if mean_px < 0.5:
        return "excellent"
    if mean_px < 1.0:
        return "good"
    if mean_px < 2.0:
        return "workable"
    return "recalibrate"


def _board_3d(cols: int, rows: int, square_mm: float):
    import numpy as np
    nx, ny = cols - 1, rows - 1  # inner corners only
    return np.array(
        [[i * square_mm, j * square_mm, 0.0] for j in range(ny) for i in range(nx)],
        dtype=np.float64,
    )


NPY_NAME = "charuco_2dData_numCams_numFrames_numTrackedPoints_pixelXY.npy"


def _candidate_npys(toml_path: Path, recording: str) -> list:
    """Where the Charuco 2D npy might live, best guess first. Our calibrate flow
    writes it into the calibration take folder's output_data/raw_data/; FreeMoCap's
    full-processing flow writes it under recording_sessions/<name>/. Check both."""
    name = toml_path.name.replace("_camera_calibration.toml", "")
    cands = []
    if recording:
        cands.append(Path(recording).expanduser() / "output_data" / "raw_data" / NPY_NAME)
    # The toml is also dumped into the recording folder, so its parent may be the take.
    cands.append(toml_path.parent / "output_data" / "raw_data" / NPY_NAME)
    # HIHO MOCAP's calibrate flow records to ~/Desktop/HIHO_CALIBRATIONS/<stamp>, and
    # <stamp> == the toml name prefix — so a fresh-solve toml is found even with no hint
    # (e.g. after a Blender restart dropped the in-memory take path).
    cands.append(Path(os.path.expanduser("~/Desktop/HIHO_CALIBRATIONS"))
                 / name / "output_data" / "raw_data" / NPY_NAME)
    # FreeMoCap's full-processing layout.
    cands.append(Path(os.path.expanduser("~/freemocap_data/recording_sessions"))
                 / name / "output_data" / "raw_data" / NPY_NAME)
    return cands


def _find_npy(toml_path: Path, recording: str, explicit: str):
    if explicit:
        p = Path(explicit).expanduser()
        return p if p.is_file() else None
    for c in _candidate_npys(toml_path, recording):
        if c.is_file():
            return c
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--toml", required=True)
    ap.add_argument("--charuco-npy", default="")
    ap.add_argument("--recording", default="",
                    help="calibration take folder; its output_data/raw_data/ is searched for the 2D npy")
    ap.add_argument("--board-cols", type=int, default=5)
    ap.add_argument("--board-rows", type=int, default=3)
    ap.add_argument("--square-mm", type=float, default=100.0)
    args = ap.parse_args()

    toml_path = Path(args.toml).expanduser()
    if not toml_path.is_file():
        _emit(ERROR, f"calibration toml not found: {toml_path}")
        return 2
    npy_path = _find_npy(toml_path, args.recording, args.charuco_npy)
    if npy_path is None:
        tried = ([args.charuco_npy] if args.charuco_npy
                 else [str(c) for c in _candidate_npys(toml_path, args.recording)])
        _emit(ERROR, "charuco 2D data not found; looked in: " + " | ".join(tried))
        return 2

    warnings.filterwarnings("ignore")
    try:
        import numpy as np
        import cv2
        from aniposelib.cameras import CameraGroup
    except Exception as exc:
        _emit(ERROR, f"import failed: {type(exc).__name__}: {exc}")
        return 3

    cg = CameraGroup.load(str(toml_path))
    raw = np.load(str(npy_path), allow_pickle=True)
    p2ds = (np.array(raw.tolist(), dtype=np.float64) if raw.dtype == object
            else raw.astype(np.float64))
    n_cams, n_frames, n_pts, _ = p2ds.shape

    board = _board_3d(args.board_cols, args.board_rows, args.square_mm)
    if n_pts != len(board):
        _emit(INFO, f"warning: data has {n_pts} corners, board model has {len(board)}")

    residuals = []
    for c in range(n_cams):
        cam = cg.cameras[c]
        K = np.array(cam.get_camera_matrix(), dtype=np.float64)
        dist = np.array(cam.get_distortions(), dtype=np.float64).flatten()
        for f in range(n_frames):
            d2d = p2ds[c, f]
            valid = ~np.isnan(d2d[:, 0])
            if np.sum(valid) < 6:  # solvePnP DLT needs >= 6 points
                continue
            obj = board[valid].reshape(-1, 1, 3)
            img = d2d[valid].reshape(-1, 1, 2)
            ok, rvec, tvec = cv2.solvePnP(obj, img, K, dist, flags=cv2.SOLVEPNP_ITERATIVE)
            if not ok:
                continue
            proj, _ = cv2.projectPoints(obj, rvec, tvec, K, dist)
            diff = proj.reshape(-1, 2) - img.reshape(-1, 2)
            residuals.extend(np.sqrt(np.sum(diff ** 2, axis=-1)))

    if not residuals:
        _emit(ERROR, "no usable frames to score")
        return 4

    mean_px = float(np.mean(np.array(residuals)))
    verdict = verdict_for(mean_px)
    _emit(INFO, f"{n_cams} cams x {n_frames} frames scored")
    _emit(QUALITY, f"{mean_px:.3f}::{verdict}")
    _emit(DONE, f"scored: {mean_px:.3f} px ({verdict})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
