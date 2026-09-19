"""Standalone FreeMoCap 2.0 + RTMPose processor for HIHO MOCAP (the fast path).

Runs INSIDE the FreeMoCap 2.0 env, launched as a subprocess, the same way
process_take.py runs inside the 1.8.2 env. It speaks the same protocol
(HIHO_INFO:: / HIHO_DONE:: / HIHO_ERROR:: lines plus HIHO_DONE.txt /
HIHO_ERROR.txt / PROCESS_QUALITY.txt in the recording folder) and hands
core/loader.py the same four files, so nothing on the Blender side has to know
which tracker ran. Design: V2_CHANGEOVER_DESIGN_2026-09-18.md.

A port of the three eval-kit pieces proven on five takes (HIHO_ALL/RTMPOSE_EVAL:
warm_model_cache.py, run_fmc2_posthoc.py, shim_fmc2_to_hiho.py). Each piece still
runs as its own process, because that is the shape that was proven: this file
re-launches itself with --stage warm | run | shim and watches the result.

Usage (2.0 env python):
    python process_take_fmc2.py --recording <folder> --calibration <toml> [--check]

--check verifies the folder, the calibration, the 2.0 imports and the pipeline
settings, then exits BEFORE any work. It reads only: no status file is cleared,
no result is moved.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Optional

DONE = "HIHO_DONE::"
ERROR = "HIHO_ERROR::"
INFO = "HIHO_INFO::"

DONE_FILE = "HIHO_DONE.txt"
ERROR_FILE = "HIHO_ERROR.txt"
QUALITY_FILE = "PROCESS_QUALITY.txt"
RUN_INFO_FILE = "FMC2_RUN_INFO.json"
SHIM_INFO_FILE = "HIHO_SHIM_INFO.json"
# Lives INSIDE output_data/ so the stamp travels with the results it describes
# when another tracker's run moves them aside.
TRACKER_FILE = "HIHO_TRACKER.json"

TRACKER = "rtmpose"
DEFAULT_MODEL = "rtmw-x-l_256x192"

MP_BODY = [
    "nose", "left_eye_inner", "left_eye", "left_eye_outer", "right_eye_inner", "right_eye",
    "right_eye_outer", "left_ear", "right_ear", "mouth_left", "mouth_right", "left_shoulder",
    "right_shoulder", "left_elbow", "right_elbow", "left_wrist", "right_wrist", "left_pinky",
    "right_pinky", "left_index", "right_index", "left_thumb", "right_thumb", "left_hip",
    "right_hip", "left_knee", "right_knee", "left_ankle", "right_ankle", "left_heel",
    "right_heel", "left_foot_index", "right_foot_index",
]
TORSO = ("left_shoulder", "right_shoulder", "left_hip", "right_hip")
# MediaPipe 21-point hand order, as RTMPose (COCO-WholeBody) name suffixes.
HAND_SUFFIX = ["root", "thumb1", "thumb2", "thumb3", "thumb4",
               "forefinger1", "forefinger2", "forefinger3", "forefinger4",
               "middle_finger1", "middle_finger2", "middle_finger3", "middle_finger4",
               "ring_finger1", "ring_finger2", "ring_finger3", "ring_finger4",
               "pinky_finger1", "pinky_finger2", "pinky_finger3", "pinky_finger4"]
# iBUG 68-point face indices (image-left = subject's RIGHT).
FACE = {"right_eye_outer": 36, "right_eye_inner": 39, "left_eye_inner": 42,
        "left_eye_outer": 45, "mouth_right": 48, "mouth_left": 54}


def _emit(prefix: str, msg: str) -> None:
    print(f"{prefix}{msg}", flush=True)


def _write_sentinel(folder: Path, name: str, content: str) -> None:
    """Atomic write (temp file + rename) so the watcher never reads half a file."""
    try:
        fd, tmp = tempfile.mkstemp(dir=str(folder), prefix=".hiho_tmp_")
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        os.replace(tmp, folder / name)
    except OSError:
        pass


def _unlink_quiet(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        pass


def _camera_videos(recording: Path) -> list:
    """The videos 2.0 will read, after making sure synchronized_videos/ exists.
    The recorder writes Camera_*.mp4 flat; FreeMoCap wants them in a subfolder.
    Symlink, non-destructively (same as process_take.py). A copied or moved take
    can carry symlinks that point nowhere, so only files that really open count."""
    sync = recording / "synchronized_videos"
    if not sync.exists():
        flat = sorted(recording.glob("Camera_*.mp4"))
        if flat:
            sync.mkdir()
            for mp4 in flat:
                link = sync / mp4.name
                try:
                    link.symlink_to(mp4)
                except OSError:
                    import shutil
                    shutil.copy2(mp4, link)
    if not sync.is_dir():
        return []
    return sorted(p for p in sync.glob("Camera_*.mp4") if p.is_file())


def _take_fps(recording: Path, videos: list) -> tuple:
    """(fps, where it came from). The recorder's own record first, never an
    assumed 30: a wrong clock here half-filters the take (AUDIT_2026-08-04)."""
    try:
        with open(recording / "HIHO_RECORDING_INFO.json", encoding="utf-8") as fh:
            fps = float(json.load(fh)["fps"])
        if fps > 0:
            return fps, "the recorder's sidecar"
    except (OSError, ValueError, KeyError, TypeError):
        pass
    try:
        import cv2
        cap = cv2.VideoCapture(str(videos[0]))
        fps = float(cap.get(cv2.CAP_PROP_FPS))
        cap.release()
        if fps > 0:
            return fps, "the video file (no recorder sidecar in this take)"
    except Exception:
        pass
    return 30.0, "a fallback (no sidecar, and the video would not say)"


def _existing_tracker(recording: Path) -> Optional[str]:
    """Which tracker made the results already in output_data/, or None when
    there are none. The stamp is the truth when present; older results are
    recognised by the files each pipeline leaves."""
    out = recording / "output_data"
    if not out.is_dir():
        return None
    try:
        with open(out / TRACKER_FILE, encoding="utf-8") as fh:
            name = str(json.load(fh).get("tracker", "")).strip().lower()
        if name:
            return re.sub(r"[^a-z0-9]+", "-", name).strip("-") or "unknown"
    except (OSError, ValueError, AttributeError):
        pass
    if (out / "rtmpose_body_3d_xyz.npy").is_file():
        return "rtmpose"
    if (out / "mediapipe_body_3d_xyz.npy").is_file():
        return "mediapipe"
    return "unknown" if any(out.iterdir()) else None


def _move_results_aside(recording: Path, tracker: str) -> Path:
    """Another tracker's results get MOVED to output_data_<tracker>_<when they
    were made>/, never deleted and never overwritten. 2.0 does not clear
    output_data/ (checked in its source, alpha.23), and both pipelines use the
    same four loader file names, so without this an RTMPose run would silently
    replace a MediaPipe result. The old quality line goes along: it describes
    those results, not the new ones."""
    out = recording / "output_data"
    try:
        made = datetime.fromtimestamp((out / "mediapipe_body_3d_xyz.npy").stat().st_mtime)
    except OSError:
        made = datetime.now()
    base = f"output_data_{tracker}_{made:%Y-%m-%d_%H-%M-%S}"
    aside = recording / base
    n = 2
    while aside.exists():
        aside = recording / f"{base}_{n}"
        n += 1
    out.rename(aside)
    quality = recording / QUALITY_FILE
    if quality.is_file():
        quality.rename(aside / QUALITY_FILE)
    return aside


def _run_stage(stage: str, extra: list) -> tuple:
    """Run one stage of this same file as a child process. Its output is passed
    straight through, line by line, so whoever watches us sees 2.0's live
    per-camera progress. Returns (exit code, last lines)."""
    cmd = [sys.executable, os.path.abspath(__file__), "--stage", stage, *extra]
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        errors="replace", bufsize=1, env=dict(os.environ, PYTHONUNBUFFERED="1"),
    )
    tail = deque(maxlen=15)

    def _pump() -> None:
        for raw in iter(proc.stdout.readline, ""):
            line = raw.rstrip("\r\n")
            if line:
                tail.append(line)
                print(line, flush=True)

    # A thread, so a grandchild that keeps the pipe open can never hang us:
    # the child's exit is what ends the stage, not end-of-file on its output.
    reader = threading.Thread(target=_pump, daemon=True)
    reader.start()
    code = proc.wait()
    reader.join(timeout=5.0)
    return code, list(tail)


def _addon_version() -> str:
    try:
        manifest = Path(__file__).resolve().parent.parent / "blender_manifest.toml"
        match = re.search(r'^version\s*=\s*"([^"]+)"', manifest.read_text(encoding="utf-8"), re.M)
        return match.group(1) if match else "?"
    except OSError:
        return "?"


# --- stages (each runs in its own process) ----------------------------------

def _stage_warm(model: str) -> int:
    """Download + convert the RTMPose/YOLOX models ONCE, in one process. On a
    first run 2.0's six camera workers race to download the model and one of
    them reads a half-written file (2026-09-04)."""
    import logging
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    from freemocap.core.tracking.tracker_factory import build_skeleton_onnx_session
    t0 = time.perf_counter()
    session = build_skeleton_onnx_session(batch_size=1, model_name=model)
    print(f"WARM OK model={model} in {time.perf_counter() - t0:.1f}s "
          f"active_provider={getattr(session, 'active_provider', '?')}", flush=True)
    try:
        session.close()
    except Exception as exc:  # noqa: BLE001
        print(f"close: {exc}", flush=True)
    return 0


def _build_config(args, calibration: Path, fps: float):
    from skellyforge.post_processing.filters.filter_config import FilterConfig
    from freemocap.core.tasks.mocap.mocap_task_config import PosthocMocapPipelineConfig
    return PosthocMocapPipelineConfig(
        detector_type="rtmpose",
        rtmpose_model_name=args.model,
        video_fps=fps,
        calibration_toml_path=str(calibration),
        filter_config=FilterConfig(cutoff=args.cutoff, sampling_rate=fps, order=args.order),
        export_to_blender=False,
        auto_open_blend_file=False,
    )


def _stage_run(args) -> int:
    """2.0's posthoc mocap pipeline, headless: the same calls its own end-to-end
    tests make. No UI, no server."""
    import logging
    import multiprocessing
    import platform

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    log = logging.getLogger("hiho.fmc2")
    rec = Path(args.recording).expanduser().resolve()
    calib = Path(args.calibration).expanduser().resolve()

    import freemocap
    import onnxruntime
    import skellytracker
    from skellycam.core.ipc.process_management.managed_worker import WorkerMode
    from skellycam.core.ipc.process_management.worker_registry import WorkerRegistry
    from skellycam.core.recorders.videos.recording_info import RecordingInfo
    from freemocap.core.pipeline.posthoc.posthoc_pipeline_manager import PosthocPipelineManager

    info = {
        "started": time.strftime("%Y-%m-%d %H:%M:%S"),
        "recording": str(rec), "calibration": str(calib),
        "freemocap": getattr(freemocap, "__version__", "?"),
        "skellytracker": getattr(skellytracker, "__version__", "?"),
        "onnxruntime": onnxruntime.__version__,
        "onnx_providers": onnxruntime.get_available_providers(),
        "python": sys.version.split()[0], "machine": platform.platform(),
        "detector": "rtmpose", "rtmpose_model": args.model,
        "video_fps": args.fps,
        "filter": {"cutoff_hz": args.cutoff, "order": args.order, "sampling_rate": args.fps},
    }
    log.info("run info: %s", json.dumps(info, indent=1))

    recording_info = RecordingInfo(
        recording_directory=str(rec.parent), recording_name=rec.name, mic_device_index=-1,
    )
    kill_flag = multiprocessing.Value("b", False)
    registry = WorkerRegistry(global_kill_flag=kill_flag, worker_mode=WorkerMode.THREAD)
    manager = PosthocPipelineManager(global_kill_flag=kill_flag, worker_registry=registry)
    config = _build_config(args, calib, args.fps)

    t0 = time.perf_counter()
    code = 0
    try:
        pipeline = manager.create_mocap_pipeline(recording_info=recording_info, mocap_config=config)
        log.info("pipeline %s created; waiting (timeout %.0f s)", pipeline.id, args.timeout)
        last = t0
        while pipeline.alive:
            # 2.0's workers shut down after 300 s without a parent heartbeat
            # (the first 120 s take died at 56 %, 2026-09-11). Refresh it by
            # hand: registry.start_heartbeat() also starts a monitor that can
            # SIGTERM this very process.
            with registry.heartbeat_timestamp.get_lock():
                registry.heartbeat_timestamp.value = time.perf_counter()
            elapsed = time.perf_counter() - t0
            if elapsed > args.timeout:
                pipeline.shutdown()
                log.error("TIMEOUT after %.0f s", elapsed)
                info["error"] = f"timed out after {elapsed:.0f} s"
                code = 3
                break
            if time.perf_counter() - last >= 30:
                log.info("... running, %.0f s elapsed", elapsed)
                last = time.perf_counter()
            time.sleep(1.0)
    except Exception as exc:  # noqa: BLE001
        log.exception("pipeline failed")
        info["error"] = f"{type(exc).__name__}: {exc}"
        code = 1
    finally:
        try:
            manager.shutdown()
        except Exception:  # noqa: BLE001
            log.exception("manager shutdown failed")

    info["elapsed_s"] = round(time.perf_counter() - t0, 1)
    info["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
    info["return_code"] = code
    (rec / RUN_INFO_FILE).write_text(json.dumps(info, indent=2), encoding="utf-8")
    log.info("run finished rc=%s in %.1f s", code, info["elapsed_s"])

    # 2.0's THREAD-mode workers keep the interpreter alive after "Posthoc mocap
    # complete". Everything is on disk by now, so leave hard.
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)


def _model_names(tracker: str) -> dict:
    import skellyforge
    import yaml
    path = (Path(skellyforge.__file__).parent / "skellymodels" / "tracker_info"
            / f"{tracker}_model_info.yaml")
    cfg = yaml.safe_load(path.read_text())
    names = {}
    for aspect, spec in cfg["aspects"].items():
        tracked = spec["tracked_points"]
        if tracked["type"] == "list":
            names[aspect] = list(tracked["names"])
        else:
            convention, count = tracked["names"]["convention"], tracked["names"]["count"]
            names[aspect] = [convention.format(i) for i in range(count)]
    return names


def _stage_shim(recording: str) -> int:
    """Write the four files core/loader.py needs, from 2.0's RTMPose output.
    The loader itself is not touched in this wave."""
    import numpy as np

    rec = Path(recording).expanduser().resolve()
    out = rec / "output_data"
    names = _model_names("rtmpose")
    body = np.load(out / "rtmpose_body_3d_xyz.npy")
    n = body.shape[0]
    report = {"tracker": "rtmpose", "frames": n, "body_points_in": body.shape[1]}

    bidx = {nm: i for i, nm in enumerate(names["body"])}
    face_path = out / "rtmpose_face_3d_xyz.npy"
    face = np.load(face_path) if face_path.is_file() else None
    raw = {side: np.load(out / f"rtmpose_{side}_hand_3d_xyz.npy") for side in ("left", "right")}

    # 2.0 alpha.23 BLOCK SCRAMBLE (upstream report #5): skellytracker writes the
    # flat wholebody array as body(23) + right_hand(21) + left_hand(21) +
    # face(68); skellyforge slices it as body(23) + face(68) + left_hand(21) +
    # right_hand(21). Net effect in the saved files: 'face'[0:21] = right hand,
    # 'face'[21:42] = left hand, 'face'[42:68] = face 0-25, 'left_hand' = face
    # 26-46, 'right_hand' = face 47-67. DETECT it first (the labeled hand roots
    # sit near the NOSE, not the wrists) so the fix turns itself off the day
    # upstream fixes it.
    scrambled = False
    if face is not None and face.shape[1] == 68:
        nose = body[:, bidx["nose"]]
        wrist = {"left": body[:, bidx["left_wrist"]], "right": body[:, bidx["right_wrist"]]}

        def med(a, c):
            return float(np.nanmedian(np.linalg.norm(a - c, axis=1)))

        labeled_near_nose = all(med(raw[s][:, 0], nose) < med(raw[s][:, 0], wrist[s]) for s in raw)
        face_blocks_near_wrists = (med(face[:, 0], wrist["right"]) < 300
                                   and med(face[:, 21], wrist["left"]) < 300)
        scrambled = labeled_near_nose and face_blocks_near_wrists
    if scrambled:
        true_right, true_left = face[:, 0:21], face[:, 21:42]
        face = np.concatenate([face[:, 42:68], raw["left"], raw["right"]], axis=1)
        raw = {"left": true_left, "right": true_right}
    report["fmc2_block_scramble_detected"] = bool(scrambled)

    hands = {}
    for side in ("left", "right"):
        hand_names = names[f"{side}_hand"]

        def _find(suffix, hand_names=hand_names, side=side):
            for i, nm in enumerate(hand_names):
                if nm == suffix or nm.endswith("_" + suffix) or nm.endswith(suffix):
                    return i
            raise KeyError(f"{side} hand: no marker for {suffix!r} in {hand_names}")

        order = list(range(21)) if scrambled else [_find(s) for s in HAND_SUFFIX]
        hands[side] = raw[side][:, order, :]

    # 2.0's own fix_hands_to_wrist fails for RTMPose ("Wrist markers missing":
    # the hand aspect names its wrist hand_root), so a hand can sit far from
    # the body wrist. Attach each hand to the body wrist, every frame.
    for side, wrist_name in (("left", "left_wrist"), ("right", "right_wrist")):
        delta = body[:, bidx[wrist_name]] - hands[side][:, 0]
        hands[side] = hands[side] + delta[:, None, :]
    left_hand, right_hand = hands["left"], hands["right"]

    mp_body = np.full((n, 33, 3), np.nan, dtype=body.dtype)
    direct = {nm: nm for nm in ("nose", "left_eye", "right_eye", "left_ear", "right_ear",
                                "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
                                "left_wrist", "right_wrist", "left_hip", "right_hip",
                                "left_knee", "right_knee", "left_ankle", "right_ankle",
                                "left_heel", "right_heel")}
    direct.update({"left_foot_index": "left_big_toe", "right_foot_index": "right_big_toe"})
    filled = []
    for j, nm in enumerate(MP_BODY):
        if nm in direct and direct[nm] in bidx:
            mp_body[:, j] = body[:, bidx[direct[nm]]]
            filled.append(nm)
        elif nm in FACE and face is not None:
            mp_body[:, j] = face[:, FACE[nm]]
            filled.append(nm + "<-face")
        elif nm.endswith(("_pinky", "_index", "_thumb")):
            side, finger = nm.split("_")[0], nm.split("_")[1]
            suffix = {"pinky": "pinky_finger1", "index": "forefinger1", "thumb": "thumb2"}[finger]
            mp_body[:, j] = hands[side][:, HAND_SUFFIX.index(suffix)]
            filled.append(nm + "<-hand")
    report["body_filled"] = filled
    report["body_left_nan"] = [nm for j, nm in enumerate(MP_BODY) if np.isnan(mp_body[:, j]).all()]

    np.save(out / "mediapipe_body_3d_xyz.npy", mp_body)
    np.save(out / "mediapipe_right_hand_3d_xyz.npy", right_hand)
    np.save(out / "mediapipe_left_hand_3d_xyz.npy", left_hand)
    raw_dir = out / "raw_data"
    raw_dir.mkdir(exist_ok=True)
    # A PLACEHOLDER, not a measurement: 2.0 alpha.23 saves no usable
    # reprojection error (its column is 100 % NaN). 0 where a point was tracked
    # keeps the loader's file contract; PROCESS_QUALITY.txt says so in words.
    placeholder = np.where(np.isfinite(mp_body).all(axis=2), 0.0, np.nan).astype(np.float64)
    np.save(raw_dir / "mediapipe_3dData_numFrames_numTrackedPoints_reprojectionError.npy", placeholder)
    report["written"] = ["mediapipe_body_3d_xyz.npy", "mediapipe_right_hand_3d_xyz.npy",
                         "mediapipe_left_hand_3d_xyz.npy", "raw_data/...reprojectionError.npy"]
    report["nan_fraction_body"] = round(float(np.isnan(mp_body).mean()), 4)
    (rec / SHIM_INFO_FILE).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)
    return 0


# --- the run the panel (or Terminal) starts ---------------------------------

def _tracked_share(body_npy: Path) -> tuple:
    """(frames, % of frames where shoulders and hips were all found). The one
    honest number this path has today; same definition as the take log."""
    import numpy as np
    body = np.load(body_npy)
    torso = [MP_BODY.index(name) for name in TORSO]
    share = 100.0 * float(np.isfinite(body[:, torso]).all(axis=(1, 2)).mean())
    return int(body.shape[0]), share


def _check(args, recording: Path, calibration: Path, videos: list) -> int:
    _emit(INFO, "check: importing FreeMoCap 2.0")
    try:
        import freemocap
        import onnxruntime  # noqa: F401
        import skellytracker
        from skellycam.core.ipc.process_management.worker_registry import WorkerRegistry  # noqa: F401
        from skellycam.core.recorders.videos.recording_info import RecordingInfo  # noqa: F401
        from freemocap.core.pipeline.posthoc.posthoc_pipeline_manager import PosthocPipelineManager  # noqa: F401
        fps, source = _take_fps(recording, videos)
        _build_config(args, calibration, fps)
    except Exception as exc:  # noqa: BLE001
        _emit(ERROR, f"FreeMoCap 2.0 check failed: {type(exc).__name__}: {exc}")
        return 3
    _emit(DONE, f"check: imports + settings OK (freemocap {getattr(freemocap, '__version__', '?')}, "
                f"skellytracker {getattr(skellytracker, '__version__', '?')}, "
                f"{len(videos)} cameras, {fps:g} fps from {source})")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--recording")
    ap.add_argument("--calibration")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--cutoff", type=float, default=7.0)
    ap.add_argument("--order", type=int, default=4)
    ap.add_argument("--timeout", type=float, default=4 * 3600)
    ap.add_argument("--fps", type=float, default=0.0, help=argparse.SUPPRESS)
    ap.add_argument("--stage", choices=("warm", "run", "shim"), help=argparse.SUPPRESS)
    args = ap.parse_args()

    if args.stage == "warm":
        return _stage_warm(args.model)
    if args.stage == "run":
        return _stage_run(args)
    if args.stage == "shim":
        return _stage_shim(args.recording)

    if not args.recording or not args.calibration:
        _emit(ERROR, "--recording and --calibration are both required")
        return 2
    recording = Path(args.recording).expanduser().resolve()
    calibration = Path(args.calibration).expanduser().resolve()
    if not recording.is_dir():
        _emit(ERROR, f"recording folder not found: {recording}")
        return 2

    if args.check:
        if not calibration.is_file():
            _emit(ERROR, f"calibration not found: {calibration}")
            return 2
        sync = recording / "synchronized_videos"
        videos = sorted(p for p in (sync if sync.is_dir() else recording).glob("Camera_*.mp4")
                        if p.is_file())
        if not videos:
            _emit(ERROR, f"no Camera_*.mp4 videos in {recording}")
            return 2
        return _check(args, recording, calibration, videos)

    # From here on the recording folder exists, so every exit drops a status
    # file. Clear the last run's first: their presence must mean THIS run.
    for name in (DONE_FILE, ERROR_FILE):
        _unlink_quiet(recording / name)

    aside: Optional[Path] = None

    def _fail(msg: str, code: int) -> int:
        if aside is not None:
            msg += f" (The earlier results are safe in {aside.name}.)"
        _emit(ERROR, msg)
        _write_sentinel(recording, ERROR_FILE, msg)
        return code

    if not calibration.is_file():
        return _fail(f"calibration not found: {calibration}", 2)
    videos = _camera_videos(recording)
    if not videos:
        return _fail(f"no camera videos could be opened in {recording} "
                     "(looked for Camera_*.mp4)", 2)

    previous = _existing_tracker(recording)
    if previous is not None and previous != TRACKER:
        try:
            aside = _move_results_aside(recording, previous)
        except OSError as exc:
            return _fail(f"could not move the earlier {previous} results aside, so nothing "
                         f"was processed and nothing was overwritten: {exc}", 6)
        _emit(INFO, f"earlier {previous} results moved aside to {aside.name} (nothing deleted)")
    _unlink_quiet(recording / QUALITY_FILE)

    fps, source = _take_fps(recording, videos)
    _emit(INFO, f"tracker RTMPose ({args.model}), {len(videos)} cameras at once, "
                f"{fps:g} fps from {source}")
    started = time.perf_counter()

    _emit(INFO, "warming the RTMPose model (one-time download on a first run)")
    code, tail = _run_stage("warm", ["--model", args.model])
    if code != 0 or not any("WARM OK" in line for line in tail):
        last = tail[-1] if tail else "no output"
        return _fail("Could not load the RTMPose model. On a first run it needs a one-time "
                     "download: connect to the internet once, or run HIHO Setup. "
                     f"(Last line: {last})", 3)

    _emit(INFO, f"detecting: all {len(videos)} cameras at once")
    run_began = time.time()
    code, tail = _run_stage("run", [
        "--recording", str(recording), "--calibration", str(calibration),
        "--model", args.model, "--fps", f"{fps:g}", "--cutoff", f"{args.cutoff:g}",
        "--order", str(args.order), "--timeout", f"{args.timeout:g}",
    ])
    out = recording / "output_data"
    # 2.0 reports a failed camera worker only as a progress message: the
    # pipeline just stops being alive and the run exits 0. And 2.0 never clears
    # output_data/, so after a quiet failure the PREVIOUS run's files are still
    # sitting there. A result counts only if 2.0 wrote it during THIS run.
    fmc2_body = out / "rtmpose_body_3d_xyz.npy"
    try:
        fresh = fmc2_body.stat().st_mtime >= run_began - 2.0
    except OSError:
        fresh = False
    if code != 0 or not fresh:
        detail = ""
        try:
            with open(recording / RUN_INFO_FILE, encoding="utf-8") as fh:
                detail = str(json.load(fh).get("error", ""))
        except (OSError, ValueError):
            pass
        if not detail:
            detail = (tail[-1] if tail else "no output") if code != 0 else \
                "it stopped without writing a new RTMPose result"
        return _fail(f"FreeMoCap 2.0 did not finish this take: {detail}", 4)

    _emit(INFO, "converting the result for the rig loader")
    code, tail = _run_stage("shim", ["--recording", str(recording)])
    if code != 0:
        last = tail[-1] if tail else "no output"
        return _fail(f"the RTMPose result could not be converted for the rig loader: {last}", 5)

    # Validate the SAME file set the Blender-side loader requires, so an
    # incomplete result fails here, with the cause in view, not at Spawn Rig.
    required = {
        "body": out / "mediapipe_body_3d_xyz.npy",
        "right hand": out / "mediapipe_right_hand_3d_xyz.npy",
        "left hand": out / "mediapipe_left_hand_3d_xyz.npy",
        "reprojection error": out / "raw_data" / "mediapipe_3dData_numFrames_numTrackedPoints_reprojectionError.npy",
    }
    missing = [label for label, path in required.items() if not path.is_file()]
    if missing:
        return _fail(f"finished but the output is incomplete (missing: {', '.join(missing)}) "
                     f"in {out}", 5)

    elapsed = time.perf_counter() - started
    try:
        frames, share = _tracked_share(required["body"])
        shown = "100" if share >= 99.95 else f"{share:.1f}"
        tracked = f"Body tracked in {shown}% of frames."
        detail = (f"tracker rtmpose ({args.model})  frames {frames}  body tracked {share:.2f}% "
                  f"(shoulders and hips all found)  processed in {elapsed:.0f} s\n")
    except Exception as exc:  # noqa: BLE001
        tracked = "Tracked share could not be read."
        detail = f"tracker rtmpose ({args.model})  tracked share unreadable: {exc}\n"
    # The panel picks its badge icon from three verdict words. None of them may
    # appear here: this path has no real quality number yet (2.0 alpha.23 saves
    # an empty reprojection column), so it must never borrow a verdict.
    quality = f"Quality: not measured yet. {tracked}\n{detail}"
    # Quality and stamp go on disk BEFORE the done file, so a watcher can read
    # both the moment it sees HIHO_DONE.txt.
    _write_sentinel(recording, QUALITY_FILE, quality)

    versions = {}
    try:
        with open(recording / RUN_INFO_FILE, encoding="utf-8") as fh:
            run_info = json.load(fh)
        versions = {key: run_info.get(key, "?") for key in ("freemocap", "skellytracker", "onnxruntime")}
    except (OSError, ValueError):
        pass
    stamp = {
        "tracker": TRACKER,
        "model": args.model,
        "backend": f"freemocap {versions.get('freemocap', '?')}",
        "versions": versions,
        "video_fps": fps,
        "filter": {"cutoff_hz": args.cutoff, "order": args.order},
        "processed": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "elapsed_s": round(elapsed, 1),
        "hiho_mocap": _addon_version(),
        "script": os.path.basename(__file__),
    }
    _write_sentinel(out, TRACKER_FILE, json.dumps(stamp, indent=2))

    _emit(INFO, quality.splitlines()[0])
    body = str(required["body"])
    _write_sentinel(recording, DONE_FILE, body)
    _emit(DONE, body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
