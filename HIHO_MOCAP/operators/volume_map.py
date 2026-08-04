"""Map the Volume operator.

Runs external/volume_map.py in the freemocap-env on a processed take: where
in the capture volume does tracking stay clean, and where does it fray?
Writes volume_map.png + VOLUME_MAP.txt into the take folder and puts the
clean-radius verdict on the panel. Synchronous like Check Calibration — the
math is seconds, not the minutes-long solves.
"""
import os
import subprocess
from os.path import expanduser

import bpy

from . import get_env_python, norm_path

VOLMAP = "HIHO_VOLMAP::"
ERROR = "HIHO_ERROR::"

DEFAULT_CALIBRATION_TOML = expanduser(
    "~/freemocap_data/logs_info_and_settings/last_successful_calibration.toml"
)


def _addon_root():
    return os.path.dirname(os.path.dirname(__file__))


class HIHO_MOCAP_OT_volume_map(bpy.types.Operator):
    """Map where in the capture volume tracking stays clean. Needs a processed
    take; saves a map image + report into the take folder."""
    bl_idname = "hiho_mocap.volume_map"
    bl_label = "Map the Volume"
    bl_options = {'REGISTER'}

    def execute(self, context):
        s = context.scene.hiho_mocap

        env = get_env_python(context)
        if not env or not os.path.exists(env):
            self.report({'ERROR'}, f"FreeMoCap env Python not found: {env or '(blank)'}. "
                                   "Set it in the panel (saved in Preferences).")
            return {'CANCELLED'}

        take = norm_path(s.last_take_path)
        if not take or not os.path.isdir(take):
            self.report({'ERROR'}, "No take folder. Set the Take field to a processed take.")
            return {'CANCELLED'}

        toml = norm_path(s.calibration_toml_path) or DEFAULT_CALIBRATION_TOML
        if not os.path.isfile(toml):
            self.report({'ERROR'}, f"No calibration file at {toml}. "
                                   "Camera positions on the map come from it.")
            return {'CANCELLED'}

        script = os.path.join(_addon_root(), "external", "volume_map.py")
        cmd = [env, script, "--recording", take, "--calibration", toml]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        except subprocess.TimeoutExpired:
            self.report({'ERROR'}, "volume map timed out")
            return {'CANCELLED'}
        except OSError as exc:
            self.report({'ERROR'}, f"could not launch volume map: {exc}")
            return {'CANCELLED'}

        png = None
        err = None
        for line in proc.stdout.splitlines():
            if line.startswith(VOLMAP):
                parts = line[len(VOLMAP):].strip().split("::")
                if len(parts) == 2:
                    png = parts[1]
            elif line.startswith(ERROR):
                err = line[len(ERROR):].strip()

        if png is None:
            self.report({'ERROR'}, err or "no volume map result (see system console)")
            return {'CANCELLED'}

        # The verdict line lives in VOLUME_MAP.txt (on-disk truth, same
        # pattern as PROCESS_QUALITY.txt) — the panel badge mirrors it.
        try:
            with open(os.path.join(take, "VOLUME_MAP.txt"), encoding="utf-8") as fh:
                verdict = fh.readline().strip()
        except OSError:
            verdict = ""

        s.volume_verdict = verdict
        s.volume_map_path = png
        self.report({'INFO'}, verdict or "Volume map saved.")
        return {'FINISHED'}
