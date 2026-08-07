"""External capture operators — Preview + Record + Stop.

These launch the env-based script (external/record_take.py) as a subprocess so
all OpenCV / camera work runs OUTSIDE Blender. That is what lets the addon run
on current Blender (no OpenCV inside Blender). The script opens its own window
(live grid for preview; countdown + REC for recording).

The subprocess is WATCHED (audit S6): an ExternalProcessRunner reads its
HIHO_ERROR:: / HIHO_DONE:: markers and a poll timer surfaces them in the panel.
So launch failures ("nothing happened") become visible errors, take paths are
set only when a recording actually completed, double-launches are blocked, and
a stuck window can be closed from Blender (the X next to Record).
"""
import os
from datetime import datetime
from typing import Optional

import bpy

from ..core.external_runner import ExternalProcessRunner
from . import STATE, get_data_home, get_env_python

POLL_INTERVAL_SEC = 0.5

_SUCCESS_HINTS = {
    "preview": "Camera preview closed.",
    "record": "Take recorded. Click Process Mocap.",
    "calibration": "Calibration recorded. Click Solve Calibration.",
}


def _addon_root():
    # operators/ -> addon root
    return os.path.dirname(os.path.dirname(__file__))


def _record_script():
    return os.path.join(_addon_root(), "external", "record_take.py")


def _env_python_ok(self, context):
    env = get_env_python(context)
    if not env or not os.path.exists(env):
        self.report({'ERROR'}, f"FreeMoCap env Python not found: {env or '(blank)'}. "
                               "Set it in the panel (saved in Preferences).")
        return None
    return env


def _redraw_panels() -> None:
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()


def _poll_capture() -> Optional[float]:
    runner = STATE.get("capture")
    if runner is None:
        return None
    if not runner.is_done:
        return POLL_INTERVAL_SEC

    kind = STATE.get("capture_kind", "")
    take_attr = STATE.get("capture_take_attr", "")
    if runner.error == "cancelled":
        STATE["status_text"] = "Capture window closed."
    elif runner.error:
        STATE["status_text"] = f"Capture failed: {runner.error}"
    elif take_attr and runner.output_path:
        # Only now — on a confirmed completed recording — does the take path
        # land in the scene. Setting it optimistically at launch is what made
        # failed recordings look processable.
        setattr(bpy.context.scene.hiho_mocap, take_attr, runner.output_path)
        STATE["status_text"] = _SUCCESS_HINTS.get(kind, "")
    elif take_attr:
        # Clean exit but nothing on disk (e.g. cancelled during the countdown).
        STATE["status_text"] = "Capture closed - no take recorded."
    else:
        STATE["status_text"] = _SUCCESS_HINTS.get(kind, "")
        if kind == "preview":
            s = bpy.context.scene.hiho_mocap
            csv = runner.cameras_csv
            if csv:
                # The picker's selection becomes the recording list.
                s.camera_ids = csv
                STATE["status_text"] = f"Recording cameras {csv}."
            elif csv == "":
                # Everything was excluded. Keep the old list; Record refuses to
                # run on a blank box either way.
                if s.camera_ids:
                    STATE["status_text"] = (f"No cameras selected - kept "
                                            f"cameras {s.camera_ids}.")
                else:
                    STATE["status_text"] = ("No cameras selected - the Cameras "
                                            "box is still blank.")

    STATE["capture"] = None
    STATE["capture_kind"] = ""
    STATE["capture_take_attr"] = ""
    _redraw_panels()
    return None


def launch_capture(operator, context, kind: str, script_args: list,
                   watch_dir: str, take_attr: str = "") -> bool:
    """Start record_take.py under a watched runner. False on launch failure."""
    if STATE.get("capture") is not None:
        operator.report({'ERROR'}, "A camera window is already open. "
                                   "Close it (or click the X next to Record) first.")
        return False
    env = _env_python_ok(operator, context)
    if env is None:
        return False

    runner = ExternalProcessRunner(
        env_python=env,
        script_path=_record_script(),
        recording_dir=watch_dir,
        script_args=script_args,
        # The capture window must stay in Blender's session to reach the
        # screen, and record_take has no long-lived children — a plain
        # terminate() is the right stop for it.
        start_new_session=False,
    )
    runner.start()
    if runner.is_done and runner.error:
        operator.report({'ERROR'}, f"Could not start capture: {runner.error}")
        return False

    STATE["capture"] = runner
    STATE["capture_kind"] = kind
    STATE["capture_take_attr"] = take_attr
    bpy.app.timers.register(_poll_capture, first_interval=POLL_INTERVAL_SEC,
                            persistent=True)
    return True


class HIHO_MOCAP_OT_preview_cameras(bpy.types.Operator):
    """Open a live view of every camera in a separate window. Right-click a camera
    to include/exclude it from recording, left-click to rotate it. Closing the
    window (Q) fills the Cameras list below with what you picked."""
    bl_idname = "hiho_mocap.preview_cameras"
    bl_label = "Show Cameras"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return STATE.get("capture") is None

    def execute(self, context):
        # The picker shows EVERY camera it can find — an excluded or shuffled
        # camera has to stay visible to be re-includable. The panel's list rides
        # along as --selected (those tiles start included); right-clicks in the
        # window edit it, and the result comes back via the HIHO_CAMERAS marker.
        args = ["--preview"]
        cams = (context.scene.hiho_mocap.camera_ids or "").strip()
        if cams:
            args += ["--selected", cams]
        if not launch_capture(self, context, "preview", args,
                              watch_dir=os.path.expanduser("~/.hiho_mocap")):
            return {'CANCELLED'}
        STATE["status_text"] = "Camera picker opening..."
        self.report({'INFO'}, "Camera picker opening in a separate window. "
                              "Right-click a camera to include/exclude it, "
                              "left-click to rotate. Press Q there when done.")
        return {'FINISHED'}


class HIHO_MOCAP_OT_record_external(bpy.types.Operator):
    """Record the rig cameras via the external env. A separate window shows an
    audible countdown, then records for the set length."""
    bl_idname = "hiho_mocap.record_external"
    bl_label = "Record"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return STATE.get("capture") is None

    def execute(self, context):
        s = context.scene.hiho_mocap
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        out = os.path.join(get_data_home(context), "HIHO_CAPTURES", stamp)
        # A blank box used to fall back to "0,1,2,3" (four-camera era) — on the
        # six-camera ring that silently records the wrong cameras and the take
        # looks normal until the solve comes back worse than it should.
        cams = (s.camera_ids or "").strip()
        if not cams:
            self.report({'ERROR'}, "The Cameras box is blank. Click Show Cameras "
                                   "and pick your ring first - camera numbers "
                                   "shuffle, so recording never guesses.")
            return {'CANCELLED'}
        args = [
            "--output", out,
            "--cameras", cams,
            "--countdown", str(s.countdown_seconds),
            "--duration", str(s.record_length_seconds),
            "--show",
        ]
        if not launch_capture(self, context, "record", args,
                              watch_dir=out, take_attr="last_take_path"):
            return {'CANCELLED'}
        STATE["status_text"] = "Recording window opening..."
        self.report(
            {'INFO'},
            f"Recording in a separate window: countdown, then {s.record_length_seconds}s "
            f"from cameras {cams}. The take path fills in when it finishes.",
        )
        return {'FINISHED'}


class HIHO_MOCAP_OT_stop_capture(bpy.types.Operator):
    """Close the external camera window (preview or recording)."""
    bl_idname = "hiho_mocap.stop_capture"
    bl_label = "Stop Capture"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        runner = STATE.get("capture")
        return runner is not None and not runner.is_done

    def execute(self, context):
        runner = STATE.get("capture")
        if runner is not None:
            runner.stop()
        self.report({'INFO'}, "Closing the capture window.")
        return {'FINISHED'}
