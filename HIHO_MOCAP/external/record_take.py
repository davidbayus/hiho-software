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
# 1.4.48: the writers are frame-count bounded (FreeMoCap needs equal counts), but a camera
# delivering slow frames must never hold the take open (2026-08-01 5 fps, 08-22 25 fps,
# 09-05 28 fps: each ran the recording past its length). Stop at the clock too.
STOP_GRACE_SEC = 2.0            # past the set length: normal one-frame stagger + equalize
STOP_KEYS = (27, ord("q"), ord("Q"))   # ESC or Q closes the recording window
END_COUNTDOWN_SEC = 5   # 1.4.49: "ENDING IN 5..1", on screen and aloud, so the performer knows


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


def _write_recording_report(out_dir, counts, expected, elapsed, fps, stopped_by, board_reads=None):
    """RECORDING_REPORT.txt in the take folder: what every camera actually delivered, in
    plain words. Returns (verdict, slow_text); slow_text names the laggards for the panel."""
    top = max(counts.values()) if counts else 0
    how = {"target": "every camera reached its frame target",
           "clock": "the clock (a camera fell behind)",
           "key": "ESC/Q"}.get(stopped_by, stopped_by)
    lines = [f"HIHO recording report  {time.strftime('%Y-%m-%d %H:%M:%S')}",
             f"take: {out_dir}",
             f"length set: {expected / fps:.0f} s at {fps} fps = {expected} frames per camera",
             f"elapsed: {elapsed:.1f} s   stopped by: {how}"]
    slow = []
    for cid in sorted(counts):
        n = counts[cid]
        rate = n / elapsed if elapsed > 0 else 0.0
        if n < top:
            slow.append(f"Camera {cid} delivered {n} of {expected} frames (~{rate:.0f} fps)")
            lines.append(f"  Camera {cid}: {n:5d} / {expected} frames  ~{rate:.0f} fps   SLOW")
        else:
            lines.append(f"  Camera {cid}: {n:5d} / {expected} frames  on time")
    if slow:
        slow_text = "; ".join(slow) + ": check its light, cable, or hub."
        verdict = "MISMATCH, this take will not process. " + slow_text
    elif top < expected:
        slow_text = ""
        verdict = f"short take: every camera stopped at {top} of {expected} frames ({how})"
    else:
        slow_text = ""
        verdict = "ok: every camera delivered its frames"
    lines.append(f"verdict: {verdict}")
    if board_reads:
        lines.append("board read while recording (share of samples this camera read the board at 6+ corners):")
        for cid, pct in board_reads:
            lines.append(f"  Camera {cid}: {pct:3d}%" + ("   LOW, give this camera more board time" if pct < 25 else ""))
    try:
        with open(Path(out_dir) / "RECORDING_REPORT.txt", "w") as fh:
            fh.write("\n".join(lines) + "\n")
    except OSError as exc:
        _emit(INFO, f"could not write RECORDING_REPORT.txt: {exc}")
    return verdict, slow_text


class _BoardReader:
    """Live 'can this camera READ the board' badge (1.4.50). Same board and detector calls as
    the solver (freemocap charuco_5x3 + aniposelib detect_image), so the corner count is the
    solver's count. Samples every camera at most RATE_HZ times a second on a downscaled frame."""
    RATE_HZ = 3
    KEEP = 6           # aniposelib keeps a frame at 6+ corners (our 7 -> 6 patch)
    LONG_SIDE = 1280   # full 720p60 frames: a 640 px downscale lost corners on the far cameras,
                       # which are exactly the ones the badge exists for (tested 09-05, frame 180)

    def __init__(self):
        import cv2
        self.cv2 = cv2
        self.aruco = cv2.aruco
        self.dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_250)
        self.board = cv2.aruco.CharucoBoard(size=[5, 3], squareLength=1, markerLength=0.8,
                                            dictionary=self.dictionary)
        self.total = (5 - 1) * (3 - 1)
        self.params = cv2.aruco.DetectorParameters()
        self.last = {}          # cid -> corners read at the last sample
        self.samples = {}       # cid -> [kept, taken] since counting began
        self._next = 0.0
        # 1.4.51: a solo performer cannot see the laptop, so the number of cameras
        # currently reading the board is spoken when it changes ("four cameras").
        self.speak = _say
        self._said = None
        self._say_after = 0.0
        self.SAY_GAP = 2.0

    def announce(self, total):
        """Speak the count of cameras reading the board (6+ corners) when it changes,
        at most every SAY_GAP seconds. Returns the count."""
        green = sum(1 for n in self.last.values() if n >= self.KEEP)
        now = time.monotonic()
        if green != self._said and now >= self._say_after:
            self._said = green
            self._say_after = now + self.SAY_GAP
            if green == 0:
                self.speak("no cameras")
            elif green == total:
                self.speak(f"all {total}")
            else:
                self.speak(f"{green} camera" + ("s" if green != 1 else ""))
        return green

    def summary(self):
        """[(cid, kept %)] since counting began, for the recording report."""
        return [(cid, 100 * k // n if n else 0) for cid, (k, n) in sorted(self.samples.items())]

    def count(self, frame):
        cv2, aruco = self.cv2, self.aruco
        h, w = frame.shape[:2]
        s = self.LONG_SIDE / max(h, w)
        if s < 1.0:
            frame = cv2.resize(frame, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
        corners, ids, _ = aruco.detectMarkers(gray, self.dictionary, parameters=self.params)
        if ids is None or len(ids) == 0:
            return 0
        n, _, _ = aruco.interpolateCornersCharuco(corners, ids, gray, self.board)
        return int(n or 0)

    def update(self, frames_by_id, counting=False):
        now = time.monotonic()
        if now < self._next:
            return self.last
        self._next = now + 1.0 / self.RATE_HZ
        for cid, f in frames_by_id.items():
            if f is None:
                continue
            try:
                n = self.count(f)
            except Exception:
                n = -1
            self.last[cid] = n
            if counting and n >= 0:
                kept, taken = self.samples.get(cid, [0, 0])
                self.samples[cid] = [kept + (1 if n >= self.KEEP else 0), taken + 1]
        return self.last

    def label(self, cid):
        n = self.last.get(cid)
        if n is None:
            return None, None
        if n < 0:
            return "board ?", (0, 200, 255)
        color = (0, 220, 0) if n >= self.KEEP else ((0, 200, 255) if n > 0 else (0, 0, 255))
        text = f"board {n}/{self.total}"
        kept, taken = self.samples.get(cid, [0, 0])
        if taken:
            text += f"   read {100 * kept // taken}%"
        return text, color


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


def _grid(frames_by_id, cam_ids, rotations=None, overlay=None, excluded=None, reader=None):
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
        if reader is not None:
            text, color = reader.label(cid)
            if text:
                cv2.rectangle(tile, (0, TILE - 30), (TILE, TILE), (0, 0, 0), -1)
                cv2.putText(tile, text, (8, TILE - 9), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
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


def _preview(CameraManager, cam_ids, selected_raw="", reader=None) -> int:
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
            frames = mgr.get_latest_frames()
            if reader is not None:
                reader.update(frames)
                reader.announce(len(cam_ids))
            grid = _grid(frames, cam_ids, rotations=rotations,
                         excluded=set(cam_ids) - selected, reader=reader)
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
    ap.add_argument("--board-overlay", action="store_true",
                    help="live 'board n/8' badge per camera (calibration recordings and Show Cameras)")
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
        return _preview(CameraManager, cam_ids, selected_raw=args.selected,
                        reader=_BoardReader() if args.board_overlay else None)

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
    reader = None
    if args.board_overlay and show:
        try:
            reader = _BoardReader()
        except Exception as exc:
            _emit(INFO, f"board badge unavailable: {type(exc).__name__}: {exc}")

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
            frames = mgr.get_latest_frames()
            if reader is not None:
                reader.update(frames)
                reader.announce(len(cam_ids))
            cv2.imshow(win, _grid(frames, cam_ids, overlay=f"REC IN {n}", reader=reader))
            if (cv2.waitKey(30) & 0xFF) in STOP_KEYS:
                # ESC/Q during the countdown: abort before anything is written.
                mgr.stop()
                cv2.destroyAllWindows()
                _emit(INFO, "cancelled during countdown - nothing recorded")
                _emit(DONE, "cancelled")
                return 0
        _say("recording")

    _emit(INFO, f"recording {args.duration}s from cameras {cam_ids} "
                f"at {args.width}x{args.height}@{args.fps}fps rotations={rotations}")
    mgr.start_recording(args.output, duration_sec=args.duration)
    deadline = args.duration + STOP_GRACE_SEC
    stopped_by = "target"
    ending_last = [None]

    def _ending(elapsed):
        """Last-seconds countdown (1.4.49). Returns the overlay text, or None outside it."""
        import math
        remaining = args.duration - elapsed
        if 0 < remaining <= END_COUNTDOWN_SEC:
            n = math.ceil(remaining)
            if n != ending_last[0]:
                ending_last[0] = n
                _say(str(n))
            return f"ENDING IN {n}"
        return None

    if show:
        import cv2
        while mgr.is_recording:
            elapsed = mgr.recording_elapsed_sec
            if elapsed >= deadline:
                stopped_by = "clock"
                break
            overlay = _ending(elapsed) or f"REC {int(elapsed)}s / {args.duration}s"
            frames = mgr.get_latest_frames()
            if reader is not None:
                reader.update(frames, counting=True)
                if not _ending(elapsed):      # the end countdown owns the voice in the last 5 s
                    reader.announce(len(cam_ids))
            cv2.imshow(win, _grid(frames, cam_ids, overlay=overlay, reader=reader))
            if (cv2.waitKey(30) & 0xFF) in STOP_KEYS:
                stopped_by = "key"
                break
        cv2.destroyAllWindows()
    else:
        while mgr.is_recording:
            elapsed = mgr.recording_elapsed_sec
            if elapsed >= deadline:
                stopped_by = "clock"
                break
            _ending(elapsed)
            time.sleep(0.2)
    if stopped_by != "target":
        # Healthy cameras already closed at their target; a laggard is cut where it
        # is so the mismatch is exposed below, not hidden.
        mgr.stop_recording()

    elapsed = mgr.recording_elapsed_sec
    counts = mgr.frame_counts
    mgr.stop()
    _say("done")
    expected = args.duration * args.fps
    verdict, slow_text = _write_recording_report(args.output, counts, expected, elapsed,
                                                 args.fps, stopped_by,
                                                 board_reads=reader.summary() if reader else None)
    _emit(INFO, f"frame counts: {counts} ({verdict})")
    if len(set(counts.values())) > 1:
        # A camera fell behind or died. FreeMoCap hard-rejects mismatched takes, so
        # fail loudly now, in plain words, not at Process.
        _emit(ERROR, f"{slow_text} Stopped at {elapsed:.0f} s. This take will not process.")
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
