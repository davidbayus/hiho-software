# RETIRED (2026-06-09): not registered, not imported by the addon. The live
# capture path is operators/external_capture.py + external/record_take.py;
# processing is core/external_runner.py + external/. Kept on disk per the
# never-delete policy; excluded from shipped zips. Do not re-wire without
# reading AUDIT_2026-06-09.md (finding L1) — this code predates the headless
# pivot and bypasses the per-camera rotation system.
"""Bind to Rig operator — pins a Rigify-metarig-style armature to the
captured-motion empties via Copy Location / Damped Track / Locked Track
constraints. See BIND_TO_RIG_DESIGN.md.
"""

import os

import bpy

from ..core.bind_to_rig import (
    apply_constraints,
    clear_hiho_constraints,
)
from ..core.virtual_landmarks import ensure_virtual_empties
from . import STATE


class HIHO_MOCAP_OT_bind_to_rig(bpy.types.Operator):
    """Bind the selected armature to the most recently processed mocap take."""
    bl_idname = "hiho_mocap.bind_to_rig"
    bl_label = "Bind to Rig"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        settings = context.scene.hiho_mocap
        if not settings.last_processed_path:
            return False
        if settings.target_rig is None or settings.target_rig.type != 'ARMATURE':
            return False
        return True

    def execute(self, context):
        settings = context.scene.hiho_mocap
        rig = settings.target_rig
        processed_path = settings.last_processed_path

        if rig is None or rig.type != 'ARMATURE':
            self.report({'ERROR'}, "Pick an armature in the Target Rig field.")
            return {'CANCELLED'}
        if not processed_path:
            self.report({'ERROR'}, "No processed mocap. Run Process Mocap first.")
            return {'CANCELLED'}

        recording_folder = os.path.dirname(os.path.dirname(processed_path))
        if not os.path.isdir(recording_folder):
            self.report({'ERROR'}, f"Recording folder missing: {recording_folder}")
            return {'CANCELLED'}

        skelly_root = _find_skelly_root(recording_folder)
        if skelly_root is None:
            self.report({'ERROR'}, "No HIHO_MOCAP_Skelly empty found. Run Spawn Rig first.")
            return {'CANCELLED'}

        try:
            ensure_virtual_empties(recording_folder, skelly_root)
        except Exception as exc:
            self.report({'ERROR'}, f"Virtual landmarks failed: {type(exc).__name__}: {exc}")
            return {'CANCELLED'}

        cleared = clear_hiho_constraints(rig)
        try:
            bound, skipped = apply_constraints(rig, skelly_root)
        except Exception as exc:
            self.report({'ERROR'}, f"Bind failed: {type(exc).__name__}: {exc}")
            return {'CANCELLED'}

        msg = f"Bound {len(bound)} bone(s) on {rig.name}"
        if cleared:
            msg += f" (cleared {cleared} prior HIHO constraint(s))"
        if skipped:
            preview = ", ".join(skipped[:4])
            more = f" +{len(skipped) - 4}" if len(skipped) > 4 else ""
            msg += f". Skipped {len(skipped)} missing bone(s): {preview}{more}"
        STATE["status_text"] = msg
        self.report({'INFO'}, msg + ". Press Spacebar to play.")
        return {'FINISHED'}


def _find_skelly_root(recording_folder: str):
    """Find the HIHO_MOCAP_Skelly_<takename> empty matching this recording.

    The Spawn Rig operator names roots `HIHO_MOCAP_Skelly_<folder_name>`,
    so we reconstruct the name from the recording folder and look it up.
    Returns None if not found.
    """
    folder_name = os.path.basename(os.path.normpath(recording_folder))
    expected_name = f"HIHO_MOCAP_Skelly_{folder_name}"
    return bpy.data.objects.get(expected_name)
