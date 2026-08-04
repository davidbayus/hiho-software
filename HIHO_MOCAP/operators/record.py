# RETIRED (2026-06-09): not registered, not imported by the addon. The live
# capture path is operators/external_capture.py + external/record_take.py;
# processing is core/external_runner.py + external/. Kept on disk per the
# never-delete policy; excluded from shipped zips. Do not re-wire without
# reading AUDIT_2026-06-09.md (finding L1) — this code predates the headless
# pivot and bypasses the per-camera rotation system.
"""Record operator — countdown, then frame-count-bounded recording.

Modal operator design (vs. a `bpy.app.timers` callback): we want ESC to cancel,
which only modal operators can intercept. The operator stays "running" for the
duration of countdown + recording (~75s with defaults) but yields PASS_THROUGH
so the user can still rotate the viewport / click around while it runs.
"""

import os
import time
from datetime import datetime
from os.path import expanduser

import bpy

from . import STATE


CALIBRATION_RECORDINGS_DIR = expanduser("~/Desktop/CALIBRATION_RECORDINGS")


def _redraw_panels(context):
    for area in context.screen.areas:
        if area.type == 'VIEW_3D':
            area.tag_redraw()


class HIHO_MOCAP_OT_record(bpy.types.Operator):
    """Count down, then record for the configured length. ESC cancels."""
    bl_idname = "hiho_mocap.record"
    bl_label = "Record"
    bl_options = {'REGISTER'}

    _timer = None
    _phase = "idle"          # "countdown" | "recording" | "done"
    _phase_start = 0.0

    @classmethod
    def poll(cls, context):
        return (
            STATE["manager"] is not None
            and not STATE["manager"].is_recording
            and not STATE.get("recording_modal_active", False)
        )

    def invoke(self, context, event):
        STATE["recording_modal_active"] = True
        STATE["recording_stop_requested"] = False
        self._phase = "countdown"
        self._phase_start = time.monotonic()

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.1, window=context.window)
        wm.modal_handler_add(self)
        _redraw_panels(context)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        # ESC always cancels.
        if event.type == 'ESC':
            self._stop_recording_if_active()
            return self._cleanup(context, {'CANCELLED'}, "Recording cancelled (ESC)")

        # Explicit Stop button.
        if STATE.get("recording_stop_requested", False):
            STATE["recording_stop_requested"] = False
            self._stop_recording_if_active()
            return self._cleanup(context, {'FINISHED'}, "Recording stopped early")

        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        # Cameras disappeared mid-flight (e.g. user clicked Cameras Down).
        if STATE["manager"] is None:
            return self._cleanup(context, {'CANCELLED'}, "Cameras went down")

        scene = context.scene.hiho_mocap
        now = time.monotonic()
        elapsed = now - self._phase_start

        if self._phase == "countdown":
            remaining = scene.countdown_seconds - elapsed
            if remaining > 0:
                STATE["status_text"] = f"Recording in {int(remaining + 0.999)}..."
            else:
                stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                out_dir = os.path.join(CALIBRATION_RECORDINGS_DIR, stamp)
                STATE["manager"].start_recording(
                    out_dir, duration_sec=scene.record_length_seconds
                )
                scene.last_take_path = out_dir
                self._phase = "recording"
                self._phase_start = now
                STATE["status_text"] = ""
            _redraw_panels(context)

        elif self._phase == "recording":
            mgr = STATE["manager"]
            if not mgr.is_recording:
                return self._cleanup(context, {'FINISHED'}, "Recording complete")
            elapsed_sec = mgr.recording_elapsed_sec
            STATE["status_text"] = (
                f"● Recording {int(elapsed_sec)}s / {scene.record_length_seconds}s"
            )
            _redraw_panels(context)

        return {'PASS_THROUGH'}

    def _stop_recording_if_active(self):
        mgr = STATE.get("manager")
        if mgr is not None and mgr.is_recording:
            mgr.stop_recording()

    def _cleanup(self, context, ret, message):
        wm = context.window_manager
        if self._timer is not None:
            wm.event_timer_remove(self._timer)
            self._timer = None
        STATE["recording_modal_active"] = False
        STATE["recording_stop_requested"] = False
        STATE["status_text"] = ""
        _redraw_panels(context)
        self.report({'INFO'}, message)
        return ret


class HIHO_MOCAP_OT_stop_record(bpy.types.Operator):
    """Stop recording early (or cancel countdown). Same effect as ESC."""
    bl_idname = "hiho_mocap.stop_record"
    bl_label = "Stop"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return STATE.get("recording_modal_active", False)

    def execute(self, context):
        STATE["recording_stop_requested"] = True
        return {'FINISHED'}
