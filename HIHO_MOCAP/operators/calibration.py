"""Calibration operators.

Check Calibration scores the current calibration's accuracy and stores a verdict
for the panel badge. It reads a calibration already on disk, so it needs no
cameras (works from home). The live Calibrate (record board + solve) operator
will live here too; recording needs the rig.
"""
import os
import subprocess
from datetime import datetime
from os.path import expanduser

import bpy

from . import STATE, get_data_home, get_env_python, norm_path
from .external_capture import launch_capture
from ..core.calibration_quality import run_score
from ..core.external_runner import ExternalProcessRunner


DEFAULT_CALIBRATION_TOML = expanduser(
    "~/freemocap_data/logs_info_and_settings/last_successful_calibration.toml"
)

TOML_TAKE_SUFFIX = "_camera_calibration.toml"


def _take_from_toml_name(toml_path: str) -> str:
    """Board-take name a calibration toml describes, from its filename
    (<take>_camera_calibration.toml). '' for generic names like
    last_successful_calibration.toml — blank badge suffix, never a guess."""
    name = os.path.basename(toml_path)
    if name.endswith(TOML_TAKE_SUFFIX):
        return name[:-len(TOML_TAKE_SUFFIX)]
    return ""


def _addon_root():
    return os.path.dirname(os.path.dirname(__file__))


def _score_script():
    return os.path.join(_addon_root(), "external", "score_calibration.py")


class HIHO_MOCAP_OT_check_calibration(bpy.types.Operator):
    """Score the current calibration's accuracy and show a quality badge.
    Works on a calibration already on disk, so no cameras are needed."""
    bl_idname = "hiho_mocap.check_calibration"
    bl_label = "Check Calibration"
    bl_options = {'REGISTER'}

    def execute(self, context):
        s = context.scene.hiho_mocap

        env = get_env_python(context)
        if not env or not os.path.exists(env):
            self.report({'ERROR'}, f"FreeMoCap env Python not found: {env or '(blank)'}. "
                                   "Set it in the panel (saved in Preferences).")
            return {'CANCELLED'}

        toml = norm_path(s.calibration_toml_path) or DEFAULT_CALIBRATION_TOML
        if not os.path.isfile(toml):
            self.report({'ERROR'}, f"No calibration file at {toml}. "
                                   "Calibrate first, or set a path in the panel.")
            return {'CANCELLED'}

        result = run_score(env, _score_script(), toml,
                           recording=(norm_path(s.calibration_take_path) or None),
                           square_mm=s.charuco_square_mm)
        if result["ok"]:
            s.calibration_quality_px = result["px"]
            s.calibration_verdict = result["verdict"]
            s.calibration_badge_take = _take_from_toml_name(toml)
            self.report({'INFO'}, f"Calibration quality: {result['verdict']} "
                                  f"({result['px']:.2f} px)")
            return {'FINISHED'}

        s.calibration_quality_px = -1.0
        s.calibration_verdict = ""
        s.calibration_badge_take = ""
        self.report({'ERROR'}, result["error"])
        return {'CANCELLED'}


def _redraw_panels() -> None:
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()


def _record_script():
    return os.path.join(_addon_root(), "external", "record_take.py")


def _calibrate_script():
    return os.path.join(_addon_root(), "external", "calibrate.py")


class HIHO_MOCAP_OT_record_calibration(bpy.types.Operator):
    """Record the cameras while you move the Charuco board through the capture
    volume, to capture a calibration take. Opens a separate window; needs cameras."""
    bl_idname = "hiho_mocap.record_calibration"
    bl_label = "Record Calibration"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return STATE.get("capture") is None

    def execute(self, context):
        s = context.scene.hiho_mocap
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        out = os.path.join(get_data_home(context), "HIHO_CALIBRATIONS", stamp)
        cams = (s.camera_ids or "").strip() or "0,1,2,3"
        args = [
            "--output", out, "--cameras", cams,
            "--countdown", str(s.countdown_seconds),
            "--duration", str(s.record_length_seconds),
            "--show",
        ]
        # Board-take path fills in on completion (watched launch) — Solve's
        # poll unlocks exactly when there is a finished take to solve.
        if not launch_capture(self, context, "calibration", args,
                              watch_dir=out, take_attr="calibration_take_path"):
            return {'CANCELLED'}
        STATE["status_text"] = "Calibration recording window opening..."
        self.report({'INFO'}, "Recording calibration in a separate window. Move the board "
                              "through the capture volume; Solve unlocks when it finishes.")
        return {'FINISHED'}


def _read_groundplane_status(recording_dir) -> str:
    try:
        path = os.path.join(recording_dir, "GROUNDPLANE_STATUS.txt")
        with open(path, encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return ""


def _poll_calibration():
    runner = STATE.get("processor")
    if runner is None:
        return None
    wm = bpy.context.window_manager
    wm.progress_update(runner.progress_pct)
    if runner.is_done:
        wm.progress_end()
        scene = bpy.context.scene.hiho_mocap
        if runner.error:
            STATE["status_text"] = f"Calibration failed: {runner.error}"
        else:
            gp = _read_groundplane_status(runner.recording_dir)
            scene.groundplane_status = gp
            scene.groundplane_badge_take = os.path.basename(
                os.path.normpath(runner.recording_dir))
            # Fresh solve = new active calibration; its quality is unknown
            # until Check Calibration runs. A lingering badge would describe
            # the PREVIOUS calibration as if it were this one.
            scene.calibration_verdict = ""
            scene.calibration_quality_px = -1.0
            scene.calibration_badge_take = ""
            if gp.startswith("FAILED"):
                STATE["status_text"] = ("Calibration solved, but the FLOOR CHECK FAILED. "
                                        "Re-record - details in GROUNDPLANE_STATUS.txt.")
            else:
                STATE["status_text"] = "Calibration complete. Click Check Calibration for quality."
            if runner.output_path:
                scene.calibration_toml_path = runner.output_path
        STATE["processor"] = None
        _redraw_panels()
        return None
    STATE["status_text"] = f"{runner.current_stage} ({runner.progress_pct}%)"
    _redraw_panels()
    return 0.5


class HIHO_MOCAP_OT_solve_calibration(bpy.types.Operator):
    """Turn a recorded Charuco-board take into a camera calibration. Runs on disk
    in the FreeMoCap env, so no cameras are needed."""
    bl_idname = "hiho_mocap.solve_calibration"
    bl_label = "Solve Calibration"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return (STATE.get("processor") is None
                and bool(context.scene.hiho_mocap.calibration_take_path))

    def execute(self, context):
        s = context.scene.hiho_mocap
        env = get_env_python(context)
        if not env or not os.path.exists(env):
            self.report({'ERROR'}, f"FreeMoCap env Python not found: {env or '(blank)'}. "
                                   "Set it in the panel (saved in Preferences).")
            return {'CANCELLED'}

        take = norm_path(s.calibration_take_path)
        if not take or not os.path.isdir(take):
            self.report({'ERROR'}, "No calibration take folder. Record Calibration first.")
            return {'CANCELLED'}

        s.groundplane_status = ""
        runner = ExternalProcessRunner(
            env_python=env,
            script_path=_calibrate_script(),
            recording_dir=take,
            script_args=["--recording", take, "--board", "5x3",
                         "--square-mm", f"{s.charuco_square_mm:g}"],
        )
        runner.start()
        STATE["processor"] = runner

        wm = context.window_manager
        wm.progress_begin(0, 100)
        wm.progress_update(0)
        STATE["status_text"] = "Calibrating..."
        _redraw_panels()

        bpy.app.timers.register(_poll_calibration, first_interval=0.5,
                                persistent=True)
        self.report({'INFO'}, "Calibration started.")
        return {'FINISHED'}
