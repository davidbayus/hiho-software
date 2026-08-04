"""
PPParty Camera Manager — synchronized multi-webcam capture with live preview.

Replaces the standalone record_calibration.py script with a reusable class that
supports BOTH a continuous preview stream (for Blender thumbnails or cv2.imshow)
AND frame-count-bounded recording (for FreeMoCap-compatible synchronized takes).

No Blender dependency — pure OpenCV + threading + numpy. Can run standalone for
testing outside Blender or as a CLI recorder.

See ../CAMERA_MANAGER_DESIGN.md for the full design rationale.
"""

import os
import sys
import time
import threading
from datetime import datetime

import cv2


# 720p60 verified live on the 4-cam BASEMENT rig 2026-07-02 (HIHO_SPEED_TEST);
# fps > resolution for tracking quality, and 60fps forces shorter exposures.
DEFAULT_RESOLUTION = (1280, 720)
DEFAULT_FPS = 60
WARMUP_FRAMES = 5  # discard first N frames so auto-exposure settles
CAMERA_OPEN_TIMEOUT_SEC = 10.0


def rotate_frame(frame, degrees):
    """Rotate a frame clockwise by degrees (0/90/180/270). Anything else: no-op.

    Cameras mounted sideways (or, in a ring rig, alternating orientations) need
    their footage turned upright before MediaPipe sees it — sideways people track
    badly. This runs at capture time so both the recorded files and the calibration
    are rotated identically.
    """
    code = {
        90: cv2.ROTATE_90_CLOCKWISE,
        180: cv2.ROTATE_180,
        270: cv2.ROTATE_90_COUNTERCLOCKWISE,
    }.get(int(degrees) % 360)
    return frame if code is None else cv2.rotate(frame, code)


def _open_capture(cam_id: int):
    """Try CAP_ANY first; on macOS, fall back to CAP_AVFOUNDATION explicitly.

    The proven record_calibration.py hardcoded CAP_AVFOUNDATION because the
    fallback wasn't there yet. CAP_ANY is supposed to auto-pick AVFoundation
    on macOS / DSHOW on Windows / V4L2 on Linux, but if it doesn't, we don't
    want to be debugging that on a treadmill.
    """
    cap = cv2.VideoCapture(cam_id)
    if not cap.isOpened() and sys.platform == "darwin":
        cap = cv2.VideoCapture(cam_id, cv2.CAP_AVFOUNDATION)
    return cap if cap.isOpened() else None


class _CameraThread(threading.Thread):
    """One thread per camera. Reads frames continuously, optionally writes to disk.

    Internal — not part of the public API. Use CameraManager instead.
    """

    def __init__(self, cam_id: int, resolution, fps: int, rotate: int = 0):
        super().__init__(daemon=True, name=f"CameraThread-{cam_id}")
        self.cam_id = cam_id
        self.resolution = resolution
        self.fps = fps
        self.rotate = int(rotate) % 360

        self._cap = None
        self.actual_w = 0
        self.actual_h = 0
        self.opened_ok = False

        self._latest_frame = None
        self._frame_lock = threading.Lock()

        self._writer = None
        self._frame_count = 0
        self._target_frames = 0  # 0 = unbounded
        self._writer_lock = threading.Lock()

        self._stop_event = threading.Event()
        self.ready_event = threading.Event()  # signaled when open succeeds OR fails

    def run(self):
        self._cap = _open_capture(self.cam_id)
        if self._cap is None:
            self.ready_event.set()
            return

        # Order matters on macOS: FOURCC first, then resolution + fps
        self._cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.resolution[0])
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.resolution[1])
        self._cap.set(cv2.CAP_PROP_FPS, self.fps)

        self.actual_w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.actual_h = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        for _ in range(WARMUP_FRAMES):
            self._cap.read()

        self.opened_ok = True
        self.ready_event.set()

        while not self._stop_event.is_set():
            ret, frame = self._cap.read()
            if not ret:
                continue
            self._handle_frame(frame)

        # Shutdown
        with self._writer_lock:
            if self._writer is not None:
                self._writer.release()
                self._writer = None
        self._cap.release()

    def _handle_frame(self, frame):
        """Store + (while recording) write one captured frame. Factored out of
        run() so the writer machinery is testable without a live camera."""
        if self.rotate:
            frame = rotate_frame(frame, self.rotate)

        with self._frame_lock:
            self._latest_frame = frame

        with self._writer_lock:
            if self._writer is not None:
                if self._target_frames == 0 or self._frame_count < self._target_frames:
                    self._writer.write(frame)
                    self._frame_count += 1
                if self._target_frames > 0 and self._frame_count >= self._target_frames:
                    # Hit the target — auto-stop this camera's writer
                    self._writer.release()
                    self._writer = None

    def get_latest_frame(self):
        with self._frame_lock:
            if self._latest_frame is None:
                return None
            return self._latest_frame.copy()

    def start_writing(self, output_path: str, target_frames: int) -> bool:
        with self._writer_lock:
            if self._writer is not None:
                return False
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            # A 90/270 rotation swaps width and height; the writer must match the
            # frames we're about to feed it or it silently writes a broken file.
            if self.rotate in (90, 270):
                out_w, out_h = self.actual_h, self.actual_w
            else:
                out_w, out_h = self.actual_w, self.actual_h
            writer = cv2.VideoWriter(
                output_path, fourcc, self.fps, (out_w, out_h)
            )
            if not writer.isOpened():
                return False
            self._writer = writer
            self._frame_count = 0
            self._target_frames = target_frames
            return True

    def retarget(self, new_target: int) -> None:
        """Change the frame target mid-write (early-stop equalization). The
        writer auto-closes in _handle_frame on reaching it; if this camera is
        already at/past the new target, close now."""
        with self._writer_lock:
            if self._writer is None:
                return
            self._target_frames = new_target
            if self._frame_count >= new_target:
                self._writer.release()
                self._writer = None

    def stop_writing(self) -> int:
        with self._writer_lock:
            count = self._frame_count
            if self._writer is not None:
                self._writer.release()
                self._writer = None
            return count

    @property
    def frame_count(self) -> int:
        with self._writer_lock:
            return self._frame_count

    @property
    def is_writing(self) -> bool:
        with self._writer_lock:
            return self._writer is not None

    def stop(self):
        self._stop_event.set()


class CameraManager:
    """Manages N webcams: continuous preview + frame-count-bounded recording.

    Two modes share the same continuously-running capture threads:
      - Preview: get_latest_frames() returns the most recent frame from each cam
      - Record: start_recording() opens writers; threads write each new frame to
                disk in addition to the preview buffer. Cameras stay open between
                recordings (no warmup delay on subsequent takes).

    Usage:
        mgr = CameraManager([0, 1, 2, 3])
        results = mgr.start()                          # {0: True, 1: True, ...}
        mgr.start_recording('/path/to/take', 60)       # 60 seconds at fps
        # ... wait, or call get_latest_frames() for live preview ...
        # Auto-stops at duration; or stop early:
        counts = mgr.stop_recording()                  # {0: 1800, 1: 1800, ...}
        mgr.stop()
    """

    def __init__(self, camera_ids, resolution=DEFAULT_RESOLUTION, fps: int = DEFAULT_FPS,
                 rotations=None):
        self.camera_ids = list(camera_ids)
        self.resolution = resolution
        self.fps = fps
        # {cam_id: degrees} clockwise. Missing / 0 = upright as-is. Each camera in
        # a ring rig can need a different turn, so this is per-camera, not global.
        self.rotations = dict(rotations) if rotations else {}
        self._threads = {}
        self._recording = False
        self._record_start_time = 0.0
        self._record_duration_sec = 0
        self._output_dir = None
        self._last_output_dir = None

    # --- Lifecycle ---

    def start(self) -> dict:
        """Open all cameras + start capture threads. Returns {cam_id: True/False}."""
        if self._threads:
            return {cid: t.opened_ok for cid, t in self._threads.items()}

        for cam_id in self.camera_ids:
            t = _CameraThread(cam_id, self.resolution, self.fps,
                              rotate=self.rotations.get(cam_id, 0))
            self._threads[cam_id] = t
            t.start()

        for t in self._threads.values():
            t.ready_event.wait(timeout=CAMERA_OPEN_TIMEOUT_SEC)

        return {cid: t.opened_ok for cid, t in self._threads.items()}

    def stop(self):
        """Stop all threads + release all cameras. Safe to call multiple times."""
        if self._recording:
            self.stop_recording()
        for t in self._threads.values():
            t.stop()
        for t in self._threads.values():
            t.join(timeout=2.0)
        self._threads.clear()

    # --- Recording ---

    def start_recording(self, output_dir: str, duration_sec: int = 60) -> str:
        """Open writers and begin recording. Returns the output directory.

        Frame-count-bounded: each camera will write exactly duration_sec * fps
        frames before its writer auto-closes. This guarantees identical frame
        counts across cameras (FreeMoCap rejects mismatched takes).
        """
        if self._recording:
            return self._output_dir
        os.makedirs(output_dir, exist_ok=True)
        target_frames = duration_sec * self.fps

        # Open writers in quick succession to minimize per-camera start stagger.
        # Inter-camera stagger is bounded by one frame interval (~33ms @ 30fps);
        # FreeMoCap synchronizes in post, so this is acceptable.
        for cam_id, t in self._threads.items():
            if not t.opened_ok:
                continue
            out_path = os.path.join(output_dir, f"Camera_{cam_id}.mp4")
            t.start_writing(out_path, target_frames)

        self._recording = True
        self._record_start_time = time.time()
        self._record_duration_sec = duration_sec
        self._output_dir = output_dir
        self._last_output_dir = output_dir
        return output_dir

    def stop_recording(self, equalize: bool = True, timeout_sec: float = 3.0) -> dict:
        """Stop recording early, equalizing frame counts across cameras.

        FreeMoCap rejects takes whose cameras differ by even one frame, and at
        an arbitrary stop instant the writers almost never agree. Frames are
        still flowing (capture threads keep running), so instead of cutting
        writers off mid-disagreement, re-target every still-writing camera to
        the highest count any camera reached and let them write up to it —
        typically one extra frame interval. A camera that can't get there
        within timeout_sec (e.g. it died mid-take) is cut off where it is, and
        the returned counts expose the mismatch instead of hiding it.

        Returns {cam_id: frame_count}.
        """
        if equalize:
            writing = [t for t in self._threads.values() if t.is_writing]
            if writing:
                target = max(t.frame_count for t in self._threads.values())
                for t in writing:
                    t.retarget(target)
                deadline = time.time() + timeout_sec
                while time.time() < deadline and any(t.is_writing for t in writing):
                    time.sleep(0.02)
        counts = {}
        for cam_id, t in self._threads.items():
            counts[cam_id] = t.stop_writing()
        self._recording = False
        return counts

    # --- Preview ---

    def get_latest_frames(self) -> dict:
        """Most recent frame from each camera. Values may be None if no frame yet.

        Returns full-resolution frames. Caller is responsible for downscaling
        for preview display.
        """
        return {cid: t.get_latest_frame() for cid, t in self._threads.items()}

    # --- Status ---

    @property
    def is_recording(self) -> bool:
        """True while at least one camera is still writing.

        Auto-flips to False when all cameras have hit their frame target,
        without requiring an explicit stop_recording() call.
        """
        if not self._recording:
            return False
        if not any(t.is_writing for t in self._threads.values()):
            self._recording = False
            return False
        return True

    @property
    def camera_count(self) -> int:
        return sum(1 for t in self._threads.values() if t.opened_ok)

    @property
    def frame_counts(self) -> dict:
        return {cid: t.frame_count for cid, t in self._threads.items()}

    @property
    def recording_elapsed_sec(self) -> float:
        if self._record_start_time == 0:
            return 0.0
        return time.time() - self._record_start_time

    @property
    def last_output_dir(self):
        return self._last_output_dir

    # --- Detection ---

    @staticmethod
    def detect_cameras(max_index: int = 10) -> list:
        """Probe indices 0..max_index-1; return list that opens AND grabs a frame.

        isOpened() alone produces false positives on macOS — some indices report
        open but can't actually grab frames. We do a real read() to filter those.
        """
        available = []
        for i in range(max_index):
            cap = _open_capture(i)
            if cap is None:
                continue
            ret, _ = cap.read()
            if ret:
                available.append(i)
            cap.release()
        return available


# --- Standalone CLI fallback ----------------------------------------------
# Lets you sanity-check the module without writing a test driver:
#     python core/camera_manager.py
# Records 10 seconds from the first 4 detected cameras. No preview window.

if __name__ == "__main__":
    print("Detecting cameras...")
    available = CameraManager.detect_cameras()
    print(f"  Found: {available}")
    if not available:
        sys.exit("No cameras detected.")

    use = available[:4]
    print(f"\nOpening {len(use)} cameras...")
    mgr = CameraManager(use)
    results = mgr.start()
    print(f"  Open results: {results}")

    session = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    out_dir = os.path.expanduser(f"~/Desktop/calibration_recordings/{session}")
    print(f"\nRecording 10 seconds to {out_dir} ...")
    mgr.start_recording(out_dir, duration_sec=10)

    # Poll until done (auto-stops at frame target)
    while mgr.is_recording:
        time.sleep(0.1)

    counts = mgr.frame_counts
    print(f"\nFrame counts: {counts}")
    mgr.stop()
    print("Done.")
