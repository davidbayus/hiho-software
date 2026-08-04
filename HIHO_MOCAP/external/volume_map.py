"""Standalone volume turbulence map for HIHO MOCAP.

Runs in the freemocap-env. Answers "where in my capture volume does tracking
stay clean, and where does it fray?" for a PROCESSED take: colors the
performer's path by frame-to-frame jitter, bins jitter by distance from ring
center, and reports the clean radius. Generalized from
diagnostics/volume_noise_map.py (validated on the 2026-07-17 perimeter take);
the metrics are unchanged — only the hardcoded session facts (ring center,
camera positions, fps) are now derived from the take + calibration.

Per-frame jitter = median across body joints of the second-difference
magnitude of 3D position: second differencing kills smooth voluntary motion
and keeps frame-to-frame noise.

Usage:
    python volume_map.py --recording <take_dir> --calibration <calibration.toml>
                         [--out <map.png>]

Writes volume_map.png + VOLUME_MAP.txt into the take folder.
Markers: HIHO_INFO:: / HIHO_VOLMAP::<clean_radius_m|unknown>::<png> / HIHO_ERROR::
"""
import argparse
import json
import sys
from pathlib import Path

INFO = "HIHO_INFO::"
VOLMAP = "HIHO_VOLMAP::"
ERROR = "HIHO_ERROR::"

MAP_TXT = "VOLUME_MAP.txt"
MAP_PNG = "volume_map.png"

# Clean = jitter no worse than 2x the take's own central walking jitter.
CLEAN_FACTOR = 2.0
BIN_MM = 250.0


def _emit(prefix: str, msg: str) -> None:
    print(f"{prefix}{msg}", flush=True)


def _fail(msg: str, code: int = 1) -> int:
    _emit(ERROR, msg)
    return code


def _fps(recording: Path) -> float:
    try:
        with open(recording / "HIHO_RECORDING_INFO.json", encoding="utf-8") as fh:
            return float(json.load(fh)["fps"])
    except (OSError, KeyError, ValueError):
        return 60.0


def _camera_worlds(toml_path: Path):
    """World xy position per camera from the calibration: world = -R^T t."""
    import cv2
    import numpy as np
    import tomllib
    with open(toml_path, "rb") as fh:
        data = tomllib.load(fh)
    worlds = []
    for key in sorted(k for k in data if k.startswith("cam_")):
        cam = data[key]
        rot, trans = cam.get("rotation"), cam.get("translation")
        if rot is None or trans is None:
            continue
        R, _ = cv2.Rodrigues(np.asarray(rot, dtype=float))
        worlds.append((-R.T @ np.asarray(trans, dtype=float))[:2])
    return np.array(worlds)


def _rolling_median(x, w):
    import numpy as np
    half = w // 2
    out = np.full_like(x, np.nan)
    for i in range(len(x)):
        seg = x[max(0, i - half):i + half + 1]
        if np.any(np.isfinite(seg)):
            out[i] = np.nanmedian(seg)
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--recording", required=True)
    parser.add_argument("--calibration", required=True)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    recording = Path(args.recording).expanduser()
    toml_path = Path(args.calibration).expanduser()
    if not recording.is_dir():
        return _fail(f"take folder not found: {recording}")
    if not toml_path.is_file():
        return _fail(f"calibration file not found: {toml_path}")

    out = recording / "output_data"
    needed = {
        "body": out / "mediapipe_body_3d_xyz.npy",
        "center of mass": out / "center_of_mass" / "mediapipe_total_body_center_of_mass_xyz.npy",
        "reprojection error": out / "raw_data" / "mediapipe_3dData_numFrames_numTrackedPoints_reprojectionError.npy",
    }
    missing = [name for name, path in needed.items() if not path.is_file()]
    if missing:
        return _fail(f"take has no {', '.join(missing)} data - process this take first")

    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    body = np.load(needed["body"])
    com = np.load(needed["center of mass"])
    rpe = np.load(needed["reprojection error"])
    fps = _fps(recording)
    frames = body.shape[0]
    _emit(INFO, f"{frames} frames ({frames / fps:.1f}s at {fps:g}fps)")

    cams = _camera_worlds(toml_path)
    if len(cams) < 2:
        return _fail(f"could not read camera positions from {toml_path.name}")
    center = cams.mean(axis=0)
    _emit(INFO, f"{len(cams)} cameras, ring center ({center[0]:.0f}, {center[1]:.0f})mm")

    d2 = body[2:] - 2 * body[1:-1] + body[:-2]
    mag = np.linalg.norm(d2, axis=2)
    frame_jitter = np.concatenate([[np.nan], np.nanmedian(mag, axis=1), [np.nan]])
    window = max(3, int(round(fps / 2)) | 1)  # ~0.5s, odd
    jit_s = _rolling_median(frame_jitter, window)
    rpe_s = _rolling_median(np.nanmean(rpe, axis=1), window)

    xy = com[:, :2]
    r = np.linalg.norm(xy - center, axis=1)

    ok = np.isfinite(jit_s)
    if not np.any(ok):
        return _fail("no usable frames (all jitter values empty)")

    central = (r < 500) & ok
    if central.sum() < int(fps):
        return _fail("less than a second of the take is near ring center - "
                     "can't set a baseline. Start takes inside the ring.")
    walk_base = float(np.nanmedian(jit_s[central]))

    bins = np.arange(0, np.nanmax(r) + BIN_MM, BIN_MM)
    rows = []
    for lo, hi in zip(bins[:-1], bins[1:]):
        m = (r >= lo) & (r < hi) & ok
        if m.sum() < 30:
            continue
        rows.append((lo, hi,
                     float(np.nanmedian(jit_s[m])),
                     float(np.nanmedian(rpe_s[m])),
                     m.sum() / fps))

    clean_edges = [hi for lo, hi, mj, _, _ in rows if mj <= CLEAN_FACTOR * walk_base]
    clean_m = max(clean_edges) / 1000 if clean_edges else None
    take_name = recording.name

    if clean_m is not None:
        headline = f"Clean radius ~{clean_m:.2f} m - {take_name}"
    else:
        headline = f"No clean zone found (check the map) - {take_name}"

    lines = [headline,
             f"central walking jitter (r<0.5m): {walk_base:.2f}mm",
             f"clean = jitter <= {CLEAN_FACTOR:g}x central walking jitter",
             "",
             "radius(m)  median_jitter(mm)  xBase  reproj(px)  time(s)"]
    for lo, hi, mj, mr, secs in rows:
        lines.append(f"{lo / 1000:.2f}-{hi / 1000:.2f}   {mj:8.2f}        "
                     f"{mj / walk_base:4.1f}x  {mr:8.2f}    {secs:5.1f}")
    (recording / MAP_TXT).write_text("\n".join(lines) + "\n", encoding="utf-8")

    png = Path(args.out).expanduser() if args.out else recording / MAP_PNG
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    ax = axes[0]
    sc = ax.scatter(xy[ok, 0] / 1000, xy[ok, 1] / 1000,
                    c=np.clip(jit_s[ok], 0, 8.0), s=6, cmap="RdYlGn_r")
    ax.scatter(cams[:, 0] / 1000, cams[:, 1] / 1000, marker="s", s=90, c="k", zorder=5)
    for i, (cx, cy) in enumerate(cams / 1000):
        ax.annotate(f"cam{i}", (cx, cy), textcoords="offset points",
                    xytext=(6, 6), fontsize=9)
    if clean_m is not None:
        ax.add_patch(plt.Circle((center[0] / 1000, center[1] / 1000), clean_m,
                                fill=False, color="k", ls="--"))
    ax.set_title(f"{take_name}\nTop-down: your path, colored by jitter "
                 "(green = clean, red = turbulent)")
    ax.set_xlabel("x (m)")
    ax.set_ylabel("y (m)")
    ax.set_aspect("equal")
    plt.colorbar(sc, ax=ax, label="jitter (mm/frame², clipped)")

    ax = axes[1]
    ax.scatter(r[ok] / 1000, jit_s[ok], s=4, alpha=0.3)
    if rows:
        ax.plot([(lo + hi) / 2000 for lo, hi, *_ in rows],
                [mj for _, _, mj, _, _ in rows],
                "r-o", lw=2, label="median per 25cm ring")
    ax.axhline(CLEAN_FACTOR * walk_base, color="orange", ls="--",
               label=f"{CLEAN_FACTOR:g}x central walking jitter")
    ax.set_title("Jitter vs distance from ring center")
    ax.set_xlabel("distance from center (m)")
    ax.set_ylabel("jitter (mm/frame²)")
    ax.set_ylim(0, np.nanpercentile(jit_s[ok], 98) * 1.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(png, dpi=110)

    _emit(VOLMAP, f"{clean_m:.2f}::{png}" if clean_m is not None else f"unknown::{png}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
