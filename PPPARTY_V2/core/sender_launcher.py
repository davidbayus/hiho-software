"""PPParty V2 — sender subprocess launcher.

Launches `mediapipe_sender.py` as a separate Python process. The sender
runs in system Python (NOT inside Blender), captures the webcam, runs
MediaPipe Pose, and sends UDP packets to the V2 receiver inside Blender.

We launch from Blender by finding a Python interpreter that has
`mediapipe` + `opencv` installed. Strategy (in order):

  1. ~/.ppparty/venv/bin/python3 — V1's documented venv pattern.
  2. python3 on PATH — fallback for hand-managed environments.

A future installer operator can create the venv and pip-install the
deps. For now the launcher reuses V1's venv if present.
"""

import os
import shutil
import subprocess


BODY_SENDER_SCRIPT = "mediapipe_sender.py"
FACE_SENDER_SCRIPT = "face_sender.py"
SENDER_SCRIPT = BODY_SENDER_SCRIPT  # legacy alias

# hand_sender.py retired in two-pass refactor (2026-04-29). The Pass 1
# body sender now runs PoseLandmarker + HandLandmarker together, so
# there is no separate hand sender process to launch.


def find_python_interpreter():
    """Locate a Python interpreter with mediapipe + opencv available.

    Returns the absolute path to a python3 executable, or None if no
    suitable interpreter was found.
    """
    # 1. V1 venv at the documented path.
    candidate = os.path.expanduser("~/.ppparty/venv/bin/python3")
    if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
        return candidate
    # 2. Fall back to whichever python3 is on PATH.
    return shutil.which("python3")


def sender_script_path(script_name=BODY_SENDER_SCRIPT):
    """Absolute path to a sender script inside the installed addon."""
    here = os.path.dirname(os.path.abspath(__file__))   # .../PPPARTY_V2/core
    addon_root = os.path.dirname(here)                   # .../PPPARTY_V2
    return os.path.join(addon_root, script_name)


class SenderProcess:
    """Manages the sender subprocess lifecycle.

    `start()` launches the process, `stop()` terminates it and waits
    briefly for clean shutdown, `running` reflects the current state.
    A single instance is reused across start/stop cycles.
    """

    def __init__(self, script_name=BODY_SENDER_SCRIPT):
        self._script_name = script_name
        self._proc = None

    @property
    def running(self):
        return self._proc is not None and self._proc.poll() is None

    def start(self, port=11111, no_preview=False):
        """Launch the sender process.

        Returns (ok: bool, message: str). On failure, no process is
        started; the operator surfaces `message` to the user.
        """
        if self.running:
            return True, "sender already running"
        python = find_python_interpreter()
        if python is None:
            return False, (
                "No Python interpreter with MediaPipe found. "
                "Expected ~/.ppparty/venv/bin/python3 or python3 on PATH."
            )
        script = sender_script_path(self._script_name)
        if not os.path.isfile(script):
            return False, f"Sender script not found at {script}"
        cmd = [python, script, "--port", str(port)]
        if no_preview:
            cmd.append("--no-preview")
        try:
            self._proc = subprocess.Popen(cmd)
        except OSError as e:
            return False, f"Failed to launch sender: {e}"
        return True, f"sender launched (PID {self._proc.pid})"

    def stop(self):
        """Terminate the sender process and wait briefly for cleanup."""
        if self._proc is None:
            return
        if self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                # Sender ignored SIGTERM — escalate to SIGKILL.
                self._proc.kill()
                try:
                    self._proc.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    pass
        self._proc = None


# ---------------------------------------------------------------------------
# Singletons — one per pass sender
# ---------------------------------------------------------------------------

_sender_process = None
_face_sender_process = None


def get_sender_process():
    """Return the Pass 1 body-and-hands SenderProcess singleton."""
    global _sender_process
    if _sender_process is None:
        _sender_process = SenderProcess(BODY_SENDER_SCRIPT)
    return _sender_process


def get_face_sender_process():
    """Return the Pass 2 face SenderProcess singleton."""
    global _face_sender_process
    if _face_sender_process is None:
        _face_sender_process = SenderProcess(FACE_SENDER_SCRIPT)
    return _face_sender_process
