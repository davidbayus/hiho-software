"""HIHO MOCAP — calibration quality seam (bpy-free, testable standalone).

Runs external/score_calibration.py in the freemocap-env as a subprocess and
parses its HIHO_QUALITY:: line into a verdict. Scoring is quick (seconds), so
this runs synchronously, unlike the minutes-long processing/calibration solves.
"""
import subprocess
from typing import Optional

QUALITY = "HIHO_QUALITY::"
ERROR = "HIHO_ERROR::"


def run_score(env_python: str, script_path: str, toml_path: str,
              charuco_npy: Optional[str] = None, recording: Optional[str] = None,
              square_mm: Optional[float] = None, timeout: int = 120) -> dict:
    """Score a calibration TOML. Returns
    {"ok": True, "px": float, "verdict": str} or {"ok": False, "error": str}.

    recording: the calibration take folder, so the scorer can find the Charuco 2D
    npy our calibrate flow leaves in <take>/output_data/raw_data/.
    square_mm: physical board square size — must match what the solve used, or
    the reprojection error comes out inflated.
    """
    cmd = [str(env_python), str(script_path), "--toml", str(toml_path)]
    if charuco_npy:
        cmd += ["--charuco-npy", str(charuco_npy)]
    if recording:
        cmd += ["--recording", str(recording)]
    if square_mm is not None:
        cmd += ["--square-mm", f"{square_mm:g}"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "scoring timed out"}
    except OSError as exc:
        return {"ok": False, "error": f"could not launch scorer: {exc}"}

    px: Optional[float] = None
    verdict: Optional[str] = None
    err: Optional[str] = None
    for line in proc.stdout.splitlines():
        if line.startswith(QUALITY):
            parts = line[len(QUALITY):].strip().split("::")
            if len(parts) == 2:
                try:
                    px = float(parts[0])
                except ValueError:
                    px = None
                verdict = parts[1]
        elif line.startswith(ERROR):
            err = line[len(ERROR):].strip()

    if px is not None and verdict:
        return {"ok": True, "px": px, "verdict": verdict}
    return {"ok": False, "error": err or "no quality result (see system console)"}
