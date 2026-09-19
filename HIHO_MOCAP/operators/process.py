"""Process Mocap operator — runs the chosen tracker on the last take.

Kicks an `ExternalProcessRunner`, polls it from `bpy.app.timers`, drives the
panel status text + `wm.progress_begin/update/end`. The operator itself
returns immediately; progress lives in the panel + status bar.

The Tracker menu picks the pipeline (V2_CHANGEOVER_DESIGN_2026-09-18):
RTMPose = external/process_take_fmc2.py in the FreeMoCap 2.0 env, MediaPipe =
external/process_take.py in the 1.8.2 env. Both speak the same protocol and
leave the same four loader files, so everything after Process is unchanged.
There is NEVER a silent fallback from one to the other: a silent fallback to
the slow tracker is a student waiting 13 minutes without knowing why.
"""

import os
import time
from os.path import expanduser
from typing import Optional

import bpy

from ..core.external_runner import ExternalProcessRunner
from . import STATE, get_env_python, get_fmc2_env_python, norm_path


DEFAULT_CALIBRATION_TOML = expanduser(
    "~/freemocap_data/logs_info_and_settings/last_successful_calibration.toml"
)
POLL_INTERVAL_SEC = 0.5

TRACKER_LABELS = {'RTMPOSE': "RTMPose", 'MEDIAPIPE': "MediaPipe"}
FMC2_MISSING = ("The fast tracker (RTMPose) is not installed on this computer. "
                "Pick MediaPipe (classic) in the Tracker menu, or run HIHO Setup.")


def _redraw_panels() -> None:
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()


def _read_quality(recording_dir: str) -> str:
    """First line of the solve's PROCESS_QUALITY.txt ('' if absent —
    never guess). Full numbers stay in the file."""
    try:
        with open(os.path.join(recording_dir, "PROCESS_QUALITY.txt")) as fh:
            return fh.readline().strip()
    except OSError:
        return ""


def _clock(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


def _poll_processor() -> Optional[float]:
    runner = STATE.get("processor")
    if runner is None:
        return None

    wm = bpy.context.window_manager
    wm.progress_update(runner.progress_pct)
    tracker = STATE.get("processor_tracker", "")

    if runner.is_done:
        wm.progress_end()
        if runner.error:
            STATE["status_text"] = f"Processing failed: {runner.error}"
        else:
            scene = bpy.context.scene.hiho_mocap
            if runner.output_path:
                scene.last_processed_path = runner.output_path
            verdict = _read_quality(runner.recording_dir)
            scene.process_verdict = verdict
            scene.process_badge_take = os.path.basename(
                os.path.normpath(runner.recording_dir))
            scene.process_badge_tracker = tracker
            done = f"Processing complete. {tracker}." if tracker else "Processing complete."
            STATE["status_text"] = f"{done} {verdict}" if verdict else done
        STATE["processor"] = None
        STATE["processor_tracker"] = ""
        _redraw_panels()
        return None

    if tracker == TRACKER_LABELS['RTMPOSE']:
        # The six-at-once path has no honest percentage yet (that is the next
        # build), so show a clock that visibly ticks instead of a bar parked
        # on 0% — a frozen number reads as a hang.
        elapsed = time.time() - STATE.get("processor_started", time.time())
        STATE["status_text"] = f"RTMPose: all cameras at once ({_clock(elapsed)} so far)"
    else:
        STATE["status_text"] = f"{runner.current_stage} ({runner.progress_pct}%)"
    _redraw_panels()
    return POLL_INTERVAL_SEC


class HIHO_MOCAP_OT_process_mocap(bpy.types.Operator):
    """Turn the recorded take into 3D motion, using the tracker picked in the
    Tracker menu. Progress shows in the panel."""
    bl_idname = "hiho_mocap.process_mocap"
    bl_label = "Process Mocap"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return (
            STATE.get("processor") is None
            and bool(context.scene.hiho_mocap.last_take_path)
        )

    def _refuse(self, msg: str):
        # Reports vanish in seconds; the panel status line stays. A refusal
        # that only whispers reads as a hang (live finding, 2026-08-12).
        STATE["status_text"] = msg
        _redraw_panels()
        self.report({'ERROR'}, msg)
        return {'CANCELLED'}

    def execute(self, context):
        scene = context.scene.hiho_mocap

        take_dir = norm_path(scene.last_take_path)
        if not take_dir or not os.path.isdir(take_dir):
            return self._refuse("No take folder. Record something first.")

        calib = norm_path(scene.calibration_toml_path) or DEFAULT_CALIBRATION_TOML
        if not os.path.isfile(calib):
            return self._refuse(
                f"No calibration file at {calib}. "
                "Run FreeMoCap's calibration recorder first, "
                "or set a path in the panel.")

        external = os.path.join(os.path.dirname(os.path.dirname(__file__)), "external")
        label = TRACKER_LABELS.get(scene.tracker, scene.tracker)
        if scene.tracker == 'RTMPOSE':
            env_python = get_fmc2_env_python(context)
            if not env_python or not os.path.isfile(env_python):
                return self._refuse(FMC2_MISSING)
            script_path = os.path.join(external, "process_take_fmc2.py")
            # The annotated-videos disk watcher counts cameras finishing ONE AT
            # A TIME; this path runs them all at once, so it would mislead.
            watch_detection = False
        else:
            env_python = get_env_python(context)
            script_path = os.path.join(external, "process_take.py")
            watch_detection = True

        runner = ExternalProcessRunner(
            env_python=env_python,
            script_path=script_path,
            recording_dir=take_dir,
            calibration_toml=calib,
            watch_detection=watch_detection,
        )
        runner.start()
        STATE["processor"] = runner
        STATE["processor_tracker"] = label
        STATE["processor_started"] = time.time()

        # The badge describes a RESULT; a starting run has none yet. Leaving the
        # previous take's green badge up under "Processing failed" is exactly the
        # stale-badge trap the calibration badges were hardened against.
        scene.process_verdict = ""
        scene.process_badge_take = ""
        scene.process_badge_tracker = ""

        wm = context.window_manager
        wm.progress_begin(0, 100)
        wm.progress_update(0)
        STATE["status_text"] = f"Processing with {label}: preparing..."
        _redraw_panels()

        # persistent: loading another .blend mid-run must not kill the poll —
        # the subprocess keeps going either way, and an orphaned STATE entry
        # locked the buttons until restart (audit M7).
        bpy.app.timers.register(_poll_processor, first_interval=POLL_INTERVAL_SEC,
                                persistent=True)

        self.report({'INFO'}, f"Processing started ({label}).")
        return {'FINISHED'}


class HIHO_MOCAP_OT_cancel_process(bpy.types.Operator):
    """Cancel an in-progress mocap run."""
    bl_idname = "hiho_mocap.cancel_process"
    bl_label = "Cancel"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        runner = STATE.get("processor")
        return runner is not None and not runner.is_done

    def execute(self, context):
        runner = STATE.get("processor")
        if runner is not None:
            runner.stop()
            self.report({'INFO'}, "Cancellation requested.")
        return {'FINISHED'}
