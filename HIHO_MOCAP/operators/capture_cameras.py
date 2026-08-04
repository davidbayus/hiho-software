# RETIRED (2026-06-09): not registered, not imported by the addon. The live
# capture path is operators/external_capture.py + external/record_take.py;
# processing is core/external_runner.py + external/. Kept on disk per the
# never-delete policy; excluded from shipped zips. Do not re-wire without
# reading AUDIT_2026-06-09.md (finding L1) — this code predates the headless
# pivot and bypasses the per-camera rotation system.
"""Add Cameras operator — place the capture cameras at their real positions.

Reads the take's calibration .toml and drops one Blender camera per real camera,
lined up with the spawned skelly (see ../core/capture_cameras.py). Works entirely
on disk — no cameras, no calibration rig needed. Look through any camera afterward
and the skelly is framed exactly as that real camera saw the performer.
"""
import os

import bpy

from ..core.capture_cameras import add_capture_cameras
from ..core.loader import recording_alignment

_LAST_SUCCESSFUL = os.path.expanduser(
    "~/freemocap_data/logs_info_and_settings/last_successful_calibration.toml"
)


def _resolve_recording_folder(settings):
    """The processed take whose skelly the cameras should line up with.

    Prefer last_processed_path (guarantees the npys + a matching skelly exist),
    fall back to the take folder the student picked.
    """
    processed = settings.last_processed_path
    if processed:
        return os.path.dirname(os.path.dirname(processed))
    take = settings.last_take_path
    return take or None


def _resolve_calibration(settings, recording_folder):
    """Override → last_successful → any *.toml in the take folder (ajc27's spot)."""
    override = settings.calibration_toml_path
    if override and os.path.isfile(override):
        return override
    if os.path.isfile(_LAST_SUCCESSFUL):
        return _LAST_SUCCESSFUL
    if recording_folder and os.path.isdir(recording_folder):
        tomls = sorted(f for f in os.listdir(recording_folder) if f.endswith(".toml"))
        if tomls:
            return os.path.join(recording_folder, tomls[0])
    return None


class HIHO_MOCAP_OT_add_capture_cameras(bpy.types.Operator):
    """Add the capture cameras where your real cameras stood, lined up with the
    skelly. Look through a camera to see the motion from that angle. No cameras
    needed — works on an already-processed take."""
    bl_idname = "hiho_mocap.add_capture_cameras"
    bl_label = "Add Cameras"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        s = context.scene.hiho_mocap
        return bool(s.last_processed_path or s.last_take_path)

    def execute(self, context):
        settings = context.scene.hiho_mocap

        recording_folder = _resolve_recording_folder(settings)
        if not recording_folder or not os.path.isdir(recording_folder):
            self.report({'ERROR'}, "No take found. Process a take, or set the Take path.")
            return {'CANCELLED'}

        toml_path = _resolve_calibration(settings, recording_folder)
        if not toml_path:
            self.report({'ERROR'}, "No calibration found. Pick one in 'Calib', or "
                                   "check ~/freemocap_data for last_successful_calibration.toml.")
            return {'CANCELLED'}

        try:
            alignment = recording_alignment(recording_folder)
        except Exception as exc:
            self.report({'ERROR'}, f"Couldn't read this take's motion data "
                                   f"({type(exc).__name__}). Process it first?")
            return {'CANCELLED'}

        # Parent under the take's skelly root if it's in the scene, so the cameras
        # move/scale/purge with it. Absent (no rig spawned) → cameras stand alone.
        folder_name = os.path.basename(os.path.normpath(recording_folder))
        skelly_root = bpy.data.objects.get(f"HIHO_MOCAP_Skelly_{folder_name}")

        try:
            created = add_capture_cameras(toml_path, alignment, parent=skelly_root)
        except Exception as exc:
            self.report({'ERROR'}, f"Add Cameras failed: {type(exc).__name__}: {exc}")
            return {'CANCELLED'}

        if not created:
            self.report({'ERROR'}, "Calibration had no cameras to add.")
            return {'CANCELLED'}

        hint = "" if skelly_root else " Spawn Rig to see them framing the skelly."
        self.report({'INFO'}, f"Added {len(created)} camera(s) from "
                              f"{os.path.basename(toml_path)}.{hint}")
        return {'FINISHED'}
