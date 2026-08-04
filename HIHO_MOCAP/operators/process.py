"""Process Mocap operator — runs FreeMoCap on the last take.

Kicks a `FreeMocapRunner` worker thread, polls it from `bpy.app.timers`, drives
the panel status text + `wm.progress_begin/update/end`. The operator itself
returns immediately; progress lives in the panel + status bar.
"""

import os
from os.path import expanduser
from typing import Optional

import bpy

from ..core.external_runner import ExternalProcessRunner
from . import STATE, get_env_python, norm_path


DEFAULT_CALIBRATION_TOML = expanduser(
    "~/freemocap_data/logs_info_and_settings/last_successful_calibration.toml"
)
POLL_INTERVAL_SEC = 0.5


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


def _poll_processor() -> Optional[float]:
    runner = STATE.get("processor")
    if runner is None:
        return None

    wm = bpy.context.window_manager
    wm.progress_update(runner.progress_pct)

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
            STATE["status_text"] = (f"Processing complete. {verdict}" if verdict
                                    else "Processing complete.")
        STATE["processor"] = None
        _redraw_panels()
        return None

    STATE["status_text"] = f"{runner.current_stage} ({runner.progress_pct}%)"
    _redraw_panels()
    return POLL_INTERVAL_SEC


class HIHO_MOCAP_OT_process_mocap(bpy.types.Operator):
    """Run FreeMoCap on the last recorded take. Progress shows in the panel."""
    bl_idname = "hiho_mocap.process_mocap"
    bl_label = "Process Mocap"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return (
            STATE.get("processor") is None
            and bool(context.scene.hiho_mocap.last_take_path)
        )

    def execute(self, context):
        scene = context.scene.hiho_mocap

        take_dir = norm_path(scene.last_take_path)
        if not take_dir or not os.path.isdir(take_dir):
            self.report({'ERROR'}, "No take folder. Record something first.")
            return {'CANCELLED'}

        calib = norm_path(scene.calibration_toml_path) or DEFAULT_CALIBRATION_TOML
        if not os.path.isfile(calib):
            self.report(
                {'ERROR'},
                f"No calibration file at {calib}. "
                "Run FreeMoCap's calibration recorder first, "
                "or set a path in the panel.",
            )
            return {'CANCELLED'}

        script_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "external", "process_take.py"
        )
        runner = ExternalProcessRunner(
            env_python=get_env_python(context),
            script_path=script_path,
            recording_dir=take_dir,
            calibration_toml=calib,
            watch_detection=True,
        )
        runner.start()
        STATE["processor"] = runner

        # The badge describes a RESULT; a starting run has none yet. Leaving the
        # previous take's green badge up under "Processing failed" is exactly the
        # stale-badge trap the calibration badges were hardened against.
        scene.process_verdict = ""
        scene.process_badge_take = ""

        wm = context.window_manager
        wm.progress_begin(0, 100)
        wm.progress_update(0)
        STATE["status_text"] = "Processing: preparing..."
        _redraw_panels()

        # persistent: loading another .blend mid-run must not kill the poll —
        # the subprocess keeps going either way, and an orphaned STATE entry
        # locked the buttons until restart (audit M7).
        bpy.app.timers.register(_poll_processor, first_interval=POLL_INTERVAL_SEC,
                                persistent=True)

        self.report({'INFO'}, "Processing started.")
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
