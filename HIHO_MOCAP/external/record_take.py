"""Standalone multi-camera preview + recorder for HIHO MOCAP's headless build.

Runs INSIDE the freemocap-env (which has OpenCV), so the version-sensitive
camera work never touches Blender. Reuses the proven CameraManager from the
addon's core/ (pure OpenCV).

Modes:
    --preview [--selected 0,1,2,3]     live grid of ALL detected cameras, each
                                       labeled by index. Left-click rotates a camera,
                                       right-click includes/excludes it from recording.
                                       Q/ESC closes and reports the included cameras
                                       back to Blender (HIHO_CAMERAS::<csv>).
                                       Blank --selected = everything starts included.
                                       (--cameras still limits which cameras open,
                                       for CLI diagnostics.)
    --output D --cameras 0,1,2,3 --duration 15 [--countdown 7] [--show]
                                       record. With --countdown, an audible + on-screen
                                       countdown plays first (so a performer away from
                                       the screen can hear it), then it records. With
                                       --show, a live window shows a REC indicator.
                                       ESC stops early.
    --check                            detect cameras, print the list, exit.

Marker lines Blender keys on: HIHO_INFO:: / HIHO_DONE::<dir> / HIHO_ERROR::<msg>
/ HIHO_CAMERAS::<csv>
"""
import argparse
import json
import sys
import time
from pathlib import Path

DONE = "HIHO_DONE::"
ERROR = "HIHO_ERROR::"
INFO = "HIHO_INFO::"
CAMERAS = "HIHO_CAMERAS::"

# Per-camera rotation, set by clicking in the preview and remembered here, so every
# Record + Record Calibration uses the same upright framing. One file per machine —
# it describes how the physical cameras are mounted, not any one project.
ROTATIONS_FILE = Path.home() / ".hiho_mocap" / "camera_rotations.json"
TILE = 240   # preview tile size; square so portrait + landscape both fit cleanly
COLS = 3     # cameras per preview row


def _emit(prefix: str, msg: str) -> None:
    print(f"{prefix}{msg}", flush=True)


def _load_rotations() -> dict:
    """{cam_id: degrees clockwise}. Empty if never set."""
    try:
        with open(ROTATIONS_FILE) as fh:
            return {int(k): int(v) for k, v in json.load(fh).items()}
    except Exception:
        return {}


def _save_rotations(rotations: dict) -> None:
    try:
        ROTATIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(ROTATIONS_FILE, "w") as fh:
            json.dump({str(k): int(v) for k, v in rotations.items()}, fh)
    except Exception:
        pass


def _say(text: str) -> None:
    """Audible cue via macOS `say`, so a performer away from the screen hears the
    countdown. Best-effort; never blocks or raises."""
    import subprocess
    try:
        subprocess.Popen(["say", text])
    except Exception:
        pass


def _load_camera_manager():
    # camera_manager.py has no relative imports (cv2 + stdlib only), so import it
    # directly from core/ without triggering the addon package __init__.
    core_dir = str(Path(__file__).resolve().parent.parent / "core")
    if core_dir not in sys.path:
        sys.path.insert(0, core_dir)
    import camera_manager
    return camera_manager.CameraManager


def _parse_selected(raw, detected):
    """--selected csv -> the initially-included camera set. Blank means everything
    detected starts included (matches the old blank-box-means-all semantics; the
    student then right-clicks the laptop cam out). Ids not currently detected are
    dropped — you can't record what isn't plugged in. A malformed csv falls back
    to all-included rather than erroring: the picker exists to FIX a bad box."""
    raw = (raw or "").strip()
    if not raw:
        return set(detected)
    try:
        wanted = {int(c) for c in raw.split(",") if c.strip() != ""}
    except ValueError:
        return set(detected)
    return wanted & set(detected)


def _selection_csv(selected):
    return ",".join(str(c) for c in sorted(selected))


def _fit_tile(frame, size=TILE):
    """Letterbox a frame into a square tile, preserving aspect — so a rotated
    (portrait) camera shows upright and un-squished next to landscape ones."""
    import cv2
    import numpy as np
    h, w = frame.shape[:2]
    scale = min(size / w, size / h)
    nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
    canvas = np.zeros((size, size, 3), dtype=np.uint8)
    y0, x0 = (size - nh) // 2, (size - nw) // 2
    canvas[y0:y0 + nh, x0:x0 + nw] = cv2.resize(frame, (nw, nh))
    return canvas


def _grid(frames_by_id, cam_ids, rotations=None, overlay=None, excluded=None):
    """Tile each camera's latest frame into one labeled image.

    rotations ({cam_id: degrees}) is applied for DISPLAY only — use it in the
    preview, where frames arrive raw. During recording the manager already rotates
    the frames, so leave rotations=None to avoid turning them twice.

    excluded (set of cam_ids) dims those tiles and banners them, for the picker.
    Recording never passes it — every recorded camera is included by definition.
    """
    import cv2
    import numpy as np
    import camera_manager  # core/ is on sys.path by now (see _load_camera_manager)
    rotations = rotations or {}
    excluded = excluded or set()
    tiles = []
    for cid in cam_ids:
        f = frames_by_id.get(cid)
        if f is None:
            tiles.append(np.zeros((TILE, TILE, 3), dtype=np.uint8))
            continue
        rot = int(rotations.get(cid, 0))
        if rot:
            f = camera_manager.rotate_frame(f, rot)
        tile = _fit_tile(f)
        if cid in excluded:
            tile = (tile * 0.35).astype(np.uint8)
        label = f"cam {cid}" + (f"  {rot} deg" if rot else "")
        cv2.putText(tile, label, (8, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        if cid in excluded:
            cv2.putText(tile, "EXCLUDED", (8, TILE // 2), cv2.FONT_HERSHEY_SIMPLEX,
                        0.8, (0, 0, 255), 2)
            cv2.putText(tile, "right-click to include", (8, TILE // 2 + 26),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
        tiles.append(tile)
    while len(tiles) % COLS != 0:
        tiles.append(np.zeros((TILE, TILE, 3), dtype=np.uint8))
    rows = [np.hstack(tiles[i:i + COLS]) for i in range(0, len(tiles), COLS)]
    grid = np.vstack(rows)
    if overlay:
        cv2.putText(grid, overlay, (20, grid.shape[0] - 22),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 255), 4)
    return grid


def _preview(CameraManager, cam_ids, selected_raw="") -> int:
    import cv2
    rotations = _load_rotations()
    selected = _parse_selected(selected_raw, cam_ids)
    mgr = CameraManager(cam_ids)  # raw frames; rotate for display + persist for record
    res = mgr.start()
    _emit(INFO, f"preview cameras {cam_ids} open={res} rotations={rotations} "
                f"selected={sorted(selected)}")
    win = "HIHO Cameras"

    def _title():
        try:
            cv2.setWindowTitle(win, f"HIHO Cameras  -  recording {len(selected)} "
                                    f"of {len(cam_ids)}  -  Q = done")
        except cv2.error:
            pass  # cosmetic; some OpenCV builds lack setWindowTitle

    def _bump(cid):
        rotations[cid] = (rotations.get(cid, 0) + 90) % 360
        _save_rotations(rotations)

    def _tile_at(x, y):
        idx = (y // TILE) * COLS + (x // TILE)
        return cam_ids[idx] if 0 <= idx < len(cam_ids) else None

    def on_mouse(event, x, y, flags, param):
        cid = _tile_at(x, y)
        if cid is None:
            return
        if event == cv2.EVENT_LBUTTONDOWN:
            _bump(cid)
        elif event == cv2.EVENT_RBUTTONDOWN:
            selected.symmetric_difference_update({cid})
            _title()

    cv2.namedWindow(win)
    cv2.setMouseCallback(win, on_mouse)
    _title()
    try:
        while True:
            grid = _grid(mgr.get_latest_frames(), cam_ids, rotations=rotations,
                         excluded=set(cam_ids) - selected)
            cv2.putText(grid,
                        "Left-click: rotate 90 deg   Right-click: include/exclude   Q = done",
                        (12, grid.shape[0] - 14),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
            cv2.imshow(win, grid)
            key = cv2.waitKey(30) & 0xFF
            if key in (ord('q'), 27):
                break
            # Keyboard fallback: a camera's index digit rotates it (matches labels).
            if ord('0') <= key <= ord('9') and (key - ord('0')) in cam_ids:
                _bump(key - ord('0'))
    finally:
        mgr.stop()
        cv2.destroyAllWindows()
    _save_rotations(rotations)
    # Report the picked cameras to Blender BEFORE the done marker. Empty payload
    # means "student excluded everything" — Blender keeps its old list and says so.
    _emit(CAMERAS, _selection_csv(selected))
    _emit(DONE, "preview")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output")
    ap.add_argument("--cameras", default="")
    ap.add_argument("--duration", type=int, default=60)
    ap.add_argument("--countdown", type=int, default=0)
    ap.add_argument("--preview", action="store_true")
    ap.add_argument("--selected", default="",
                    help="csv of cameras that start INCLUDED in the preview picker; "
                         "blank = all detected")
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--check", action="store_true")
    # Keep in sync with core/camera_manager.py DEFAULT_RESOLUTION / DEFAULT_FPS —
    # the panel launches with no flags, so THESE are the values students get.
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--fps", type=int, default=60)
    args = ap.parse_args()

    try:
        CameraManager = _load_camera_manager()
    except Exception as exc:
        _emit(ERROR, f"could not load camera module: {type(exc).__name__}: {exc}")
        return 3

    def parse_ids(detect_if_empty):
        raw = args.cameras.strip()
        if raw:
            try:
                return [int(c) for c in raw.split(",") if c.strip() != ""]
            except ValueError:
                _emit(ERROR, f"bad camera list {raw!r} - use comma-separated "
                             "numbers like 0,1,2,3")
                sys.exit(2)
        return CameraManager.detect_cameras() if detect_if_empty else []

    if args.check:
        _emit(INFO, f"cameras that open and grab a frame: {CameraManager.detect_cameras()}")
        _emit(DONE, "check")
        return 0

    if args.preview:
        # The picker shows EVERYTHING it can find (an excluded or forgotten camera
        # must stay visible to be re-includable); --cameras still narrows the view
        # for CLI diagnostics. Which cameras get RECORDED is --selected's job.
        cam_ids = parse_ids(detect_if_empty=True)
        if not cam_ids:
            _emit(ERROR, "no cameras detected")
            return 2
        return _preview(CameraManager, cam_ids, selected_raw=args.selected)

    # --- recording ---
    if not args.output:
        _emit(ERROR, "--output is required when not using --preview/--check")
        return 2
    cam_ids = parse_ids(detect_if_empty=False)
    if not cam_ids:
        _emit(ERROR, "--cameras is required for recording")
        return 2

    rotations = _load_rotations()
    mgr = CameraManager(cam_ids, resolution=(args.width, args.height),
                        fps=args.fps, rotations=rotations)
    res = mgr.start()
    failed = [cid for cid, ok in res.items() if not ok]
    if failed:
        mgr.stop()
        _emit(ERROR, f"cameras failed to open: {failed}")
        return 2

    show = args.show or args.countdown > 0
    win = "HIHO Recording  (ESC stops early)"

    if args.countdown > 0:
        import cv2
        _say("get ready")
        start = time.monotonic()
        last = None
        while True:
            remaining = args.countdown - (time.monotonic() - start)
            if remaining <= 0:
                break
            n = int(remaining) + 1
            if n != last:
                last = n
                _say(str(n))
            cv2.imshow(win, _grid(mgr.get_latest_frames(), cam_ids, overlay=f"REC IN {n}"))
            if (cv2.waitKey(30) & 0xFF) == 27:
                # ESC during the countdown: abort before anything is written.
                mgr.stop()
                cv2.destroyAllWindows()
                _emit(INFO, "cancelled during countdown - nothing recorded")
                _emit(DONE, "cancelled")
                return 0
        _say("recording")

    _emit(INFO, f"recording {args.duration}s from cameras {cam_ids} "
                f"at {args.width}x{args.height}@{args.fps}fps rotations={rotations}")
    mgr.start_recording(args.output, duration_sec=args.duration)
    if show:
        import cv2
        while mgr.is_recording:
            cv2.imshow(win, _grid(mgr.get_latest_frames(), cam_ids,
                                  overlay=f"REC {int(mgr.recording_elapsed_sec)}s / {args.duration}s"))
            if (cv2.waitKey(30) & 0xFF) == 27:
                mgr.stop_recording()
                break
        cv2.destroyAllWindows()
    else:
        while mgr.is_recording:
            time.sleep(0.2)

    counts = mgr.frame_counts
    mgr.stop()
    _say("done")
    _emit(INFO, f"frame counts: {counts}")
    if len(set(counts.values())) > 1:
        # Equalization timed out (a camera likely died mid-take). FreeMoCap
        # hard-rejects mismatched takes, so fail loudly now, not at Process.
        _emit(ERROR, f"cameras ended with mismatched frame counts {counts} - "
                     "a camera may have died mid-take; this take will not process")
        return 1
    # Sidecar so Load Take can set the scene clock to match the take
    # (LOAD_TAKE_FPS_DESIGN_2026-07-02). Also the future landing spot for
    # per-frame timestamps (Tier 1.1).
    info = {
        "fps": args.fps,
        "width": args.width,
        "height": args.height,
        "camera_ids": cam_ids,
        "duration_sec": args.duration,
    }
    try:
        with open(Path(args.output) / "HIHO_RECORDING_INFO.json", "w") as fh:
            json.dump(info, fh, indent=2)
    except OSError as exc:
        _emit(INFO, f"could not write HIHO_RECORDING_INFO.json: {exc}")
    _emit(DONE, str(args.output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
