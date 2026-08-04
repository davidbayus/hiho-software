"""HIHO MOCAP — headless processing seam.

Launches the standalone FreeMoCap processor (external/process_take.py) in the
external freemocap-env as a subprocess, so the version-sensitive solve runs
OUTSIDE Blender. Reads the subprocess's combined output on a worker thread and
exposes the same progress surface as the old in-Blender FreeMocapRunner
(progress_pct / current_stage / is_done / error / output_path), so the Process
operator's bpy.app.timers polling is unchanged.

No bpy imports — testable standalone.
"""
import json
import os
import signal
import subprocess
import threading
import time
from collections import deque
from pathlib import Path
from typing import Optional


# Lowercased substring -> (human label, bar %), in FreeMoCap 1.8.2 pipeline
# order. Matched against FreeMoCap's own stage log lines. Kept SPECIFIC so
# incidental lines (the intermediate "saving: <path>" logged right after
# triangulation) can't jump the bar ahead — that bug made it read 100% while
# still mid-pipeline. Detection owns 5-90% of the bar because it is ~90% of
# the wall time (one MediaPipe pass per camera, sequential); within it the
# disk watcher drives the number (HONEST_PROGRESS_CLOCK_DESIGN_2026-07-18).
# The later stages are quick and stay line-driven. 100% is reserved for DONE.
STAGES = (
    ("detecting 2d", "Detecting 2D landmarks", 5),
    ("triangulating 3d", "Triangulating 3D points", 92),
    ("post-processing", "Cleaning up the motion", 94),
    ("center of mass", "Computing center of mass", 96),
    ("splitting and saving", "Saving output", 98),
)

# Seed for per-camera detection pace before the first camera finishes:
# seconds of processing per second of recording, per camera. Measured on the
# BASEMENT rig at 720p60 (120s take -> ~9.3 min/cam, 60s -> ~4.9 min/cam).
# Replaced by the live-measured pace as soon as one camera lands.
DETECTION_PACE_SEED = 4.5

DONE = "HIHO_DONE::"
ERROR = "HIHO_ERROR::"
CAMERAS = "HIHO_CAMERAS::"

# Sentinel files process_take.py drops in the recording folder. We poll for
# these as the reliable done signal: FreeMoCap's child processes hold the stdout
# pipe open, so the reader thread may never see EOF on long takes and can miss
# the HIHO_DONE:: marker.
DONE_FILE = "HIHO_DONE.txt"
ERROR_FILE = "HIHO_ERROR.txt"


class ExternalProcessRunner:
    """Runs external/process_take.py in the freemocap-env via subprocess."""

    def __init__(self, env_python: str, script_path: str, recording_dir: str,
                 calibration_toml: Optional[str] = None,
                 script_args: Optional[list] = None,
                 start_new_session: bool = True,
                 watch_detection: bool = False):
        self.env_python = str(env_python)
        self.script_path = str(script_path)
        self.recording_dir = str(recording_dir)
        self.calibration_toml = str(calibration_toml) if calibration_toml is not None else None
        # When set, these args are passed to the script verbatim (e.g. calibrate.py
        # which takes --board/--square-mm, not --calibration). When None, the
        # default --recording/--calibration form is used (process_take.py).
        self._script_args = script_args
        # False for GUI children (the capture window must stay in Blender's
        # session to reach the screen); True for headless processing, where
        # stop() must be able to kill FreeMoCap's whole process group.
        self._start_new_session = bool(start_new_session)

        self._progress_pct = 0
        self._current_stage = "queued"
        self._is_done = False
        self._error: Optional[str] = None
        self._output_path: Optional[str] = None
        self._cameras_csv: Optional[str] = None
        self._stage_idx = -1  # highest STAGES index reached, for monotonic progress
        # Crash forensics: the helper's stack trace arrives on the same pipe as
        # the markers and used to be discarded — every mystery failure was a
        # dead end. Keep the last lines to attach to the error.
        self._tail = deque(maxlen=20)

        # Detection disk watcher (process path only — the calibrate solve
        # keeps plain line-driven progress).
        self._watch_detection = bool(watch_detection)
        self._start_time: Optional[float] = None
        self._watch_cameras: Optional[int] = None
        self._watch_duration: Optional[float] = None
        self._watch_last_check = 0.0

        recording = Path(self.recording_dir)
        self._done_sentinel = recording / DONE_FILE
        self._error_sentinel = recording / ERROR_FILE

        self._proc: Optional[subprocess.Popen] = None
        self._reader: Optional[threading.Thread] = None

    @property
    def progress_pct(self) -> int:
        self._refresh_detection()
        return self._progress_pct

    @property
    def current_stage(self) -> str:
        self._refresh_detection()
        return self._current_stage

    def _refresh_detection(self) -> None:
        """Drive the bar from annotated_videos/ while 2D detection runs.

        FreeMoCap writes one annotated video per camera, sequentially, and
        detection is ~90% of the wall time — the stage log lines alone leave
        the bar parked on one number for most of an hour. Counting the files
        that have landed is the honest clock. Only files newer than this
        run's start count (a reprocess of an already-annotated take must not
        read near-done instantly). Throttled to ~1s; a listdir of a tiny
        folder plus a few stats."""
        if not self._watch_detection or self._stage_idx != 0 or self._is_done:
            return
        now = time.time()
        if now - self._watch_last_check < 1.0:
            return
        self._watch_last_check = now

        self._load_watch_meta()
        n = self._watch_cameras
        if not n:
            return

        start = self._start_time or now
        try:
            annotated = Path(self.recording_dir) / "annotated_videos"
            mtimes = sorted(
                m for m in (p.stat().st_mtime for p in annotated.glob("*.mp4"))
                if m > start
            )
        except OSError:
            return

        complete = max(0, len(mtimes) - 1)
        # Per-camera pace: measured once cameras have landed, seeded from the
        # recording length before that (see DETECTION_PACE_SEED).
        if complete >= 1:
            pace = (mtimes[complete - 1] - start) / complete
        elif self._watch_duration:
            pace = self._watch_duration * DETECTION_PACE_SEED
        else:
            pace = None

        # The newest file is the camera being written right now; its start is
        # the previous camera's finish (or the run start for the first).
        current_started = mtimes[complete - 1] if complete >= 1 else start
        if pace:
            partial = min(0.9, max(0.0, (now - current_started) / pace))
        else:
            partial = 0.3 if mtimes else 0.0

        pct = int(5 + 85 * (complete + partial) / n)
        self._progress_pct = max(self._progress_pct, min(90, pct))

        current_cam = min(n, len(mtimes) + (0 if mtimes else 1))
        text = f"Detecting: camera {max(1, current_cam)} of {n}"
        if pace:
            remaining = pace * (n - complete - partial)
            minutes = int(round(remaining / 60))
            text += " (almost done)" if minutes < 1 else f" (~{minutes} min left)"
        self._current_stage = text

    def _load_watch_meta(self) -> None:
        """Camera count + take length, read once. HIHO_RECORDING_INFO.json is
        the recorder's own record; fall back to counting source videos."""
        if self._watch_cameras:
            return
        recording = Path(self.recording_dir)
        try:
            with open(recording / "HIHO_RECORDING_INFO.json", encoding="utf-8") as fh:
                info = json.load(fh)
            self._watch_cameras = len(info.get("camera_ids", [])) or None
            duration = info.get("duration_sec")
            self._watch_duration = float(duration) if duration else None
        except (OSError, ValueError):
            pass
        if not self._watch_cameras:
            for folder in (recording / "synchronized_videos", recording):
                count = len(list(folder.glob("Camera_*.mp4"))) if folder.is_dir() else 0
                if count:
                    self._watch_cameras = count
                    break

    @property
    def is_done(self) -> bool:
        # The reader thread sets _is_done at pipe EOF (short takes), but on long
        # takes EOF may never arrive, so also treat either sentinel as done.
        return (
            self._is_done
            or self._done_sentinel.exists()
            or self._error_sentinel.exists()
        )

    @property
    def error(self) -> Optional[str]:
        if self._error is None and self._error_sentinel.exists():
            try:
                self._error = self._error_sentinel.read_text().strip() or "processing failed"
            except OSError:
                self._error = "processing failed"
        return self._error

    @property
    def cameras_csv(self) -> Optional[str]:
        """Camera picker result from the preview window. None = never reported
        (window killed / older script); "" = student excluded every camera."""
        return self._cameras_csv

    @property
    def output_path(self) -> Optional[str]:
        if self._output_path is None and self._done_sentinel.exists():
            try:
                payload = self._done_sentinel.read_text().strip()
            except OSError:
                payload = ""
            if payload and Path(payload).exists():
                self._output_path = payload
        return self._output_path

    def start(self) -> None:
        if self._proc is not None:
            raise RuntimeError("ExternalProcessRunner already started")
        # is_file, not exists: a blank path ('' -> '.') and a folder both pass
        # exists() and then crash raw at Popen (audit 08-04 smaller item #9).
        if not Path(self.env_python).is_file():
            self._error = f"FreeMoCap env python not found: {self.env_python}"
            self._current_stage = "error"
            self._is_done = True
            return
        if not Path(self.script_path).is_file():
            self._error = f"processor script not found: {self.script_path}"
            self._current_stage = "error"
            self._is_done = True
            return

        # Clear sentinels from a previous run of this folder HERE, not just in
        # the child: the child clears them too, but only after conda startup
        # (seconds), while Blender's first poll fires at 0.5 s — fast enough to
        # read the previous run's DONE/ERROR as this run's result.
        for sentinel in (self._done_sentinel, self._error_sentinel):
            try:
                sentinel.unlink(missing_ok=True)
            except OSError as exc:
                self._error = (
                    f"could not clear stale status file {sentinel.name}: {exc}"
                )
                self._current_stage = "error"
                self._is_done = True
                return

        if self._script_args is not None:
            cmd = [self.env_python, self.script_path, *self._script_args]
        else:
            cmd = [
                self.env_python, self.script_path,
                "--recording", self.recording_dir,
                "--calibration", self.calibration_toml,
            ]
        self._current_stage = "starting backend"
        self._start_time = time.time()
        # Own session/process group (when requested), so stop() can kill
        # FreeMoCap's multiprocessing children along with the parent script.
        # POSIX-only parameter; ignored on Windows.
        self._proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            # One undecodable byte in helper output used to raise in the reader
            # thread and kill it — Record stayed greyed out with no message.
            errors="replace",
            bufsize=1,
            start_new_session=self._start_new_session,
        )
        self._reader = threading.Thread(target=self._read_output, daemon=True)
        self._reader.start()

    def stop(self) -> None:
        """Cancel the run and close the runner out.

        Kill the whole process group, not just the parent script — FreeMoCap's
        multiprocessing children survive a parent-only terminate() and keep
        burning CPU. And mark done HERE: the killed parent is the only thing
        that would have written the DONE/ERROR sentinel, so without this the
        poll timer would spin forever and the UI would stay locked.
        """
        # Mark cancelled BEFORE killing: pipe EOF lands in the reader thread
        # the instant the process dies, and its exit-code branch must find
        # _error already set — not race us to a "backend exited with code -15".
        if not self._is_done:
            if self._error is None:
                self._error = "cancelled"
            self._current_stage = "cancelled"
            self._is_done = True
        proc = self._proc
        if proc is not None and proc.poll() is None:
            # Group-kill ONLY when we own a separate group — without
            # start_new_session the child shares Blender's process group, and
            # killpg would SIGTERM Blender itself.
            if self._start_new_session and hasattr(os, "killpg"):
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                except OSError:
                    proc.terminate()
            else:
                proc.terminate()

    def _read_output(self) -> None:
        proc = self._proc
        if proc is None or proc.stdout is None:
            return
        # readline (not `for line in stdout`) so each line is handled the moment
        # it is flushed, instead of waiting for a read-ahead buffer to fill —
        # that buffering is what froze the bar on one stage then flashed it.
        for raw in iter(proc.stdout.readline, ""):
            line = raw.rstrip("\n")
            if line:
                self._consume_line(line)
        code = proc.wait()
        if code != 0 and self._error is None:
            self._error = f"backend exited with code {code}"
            tail = "\n".join(self._tail).strip()
            if tail:
                print(f"HIHO backend crash (exit {code}) — last output:\n{tail}")
                self._error += f". Last output:\n{tail}"
        if self._error is not None:
            self._current_stage = "error"
        self._is_done = True

    def _consume_line(self, line: str) -> None:
        self._tail.append(line)
        if line.startswith(ERROR):
            self._error = line[len(ERROR):].strip()
            return
        if line.startswith(CAMERAS):
            self._cameras_csv = line[len(CAMERAS):].strip()
            return
        if line.startswith(DONE):
            payload = line[len(DONE):].strip()
            if Path(payload).exists():
                self._output_path = payload
            self._progress_pct = 100
            self._current_stage = "done"
            return
        # Advance only forward through the known stages. 100% is reserved for
        # actual completion (the DONE marker), so a partial bar never reads 100%.
        lower = line.lower()
        for idx, (needle, label, pct) in enumerate(STAGES):
            if needle in lower:
                if idx > self._stage_idx:
                    self._stage_idx = idx
                    self._current_stage = label
                    self._progress_pct = max(self._progress_pct, pct)
                break
