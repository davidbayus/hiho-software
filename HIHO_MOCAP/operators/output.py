"""Spawn Rig operator — drops the captured motion into the scene as
keyframed empties parented to a HIHO MOCAP Skelly root.
"""

import os

import bpy

from ..core.output_rig import spawn_skelly_from_recording
from . import STATE, norm_path


class HIHO_MOCAP_OT_spawn_output_rig(bpy.types.Operator):
    """Spawn the captured motion as a parented set of 33 keyframed empties.

    Debug/inspection feature. The canonical FreeMoCap output is `Spawn Rig`
    (operators/spawn_rig.py), which builds an armature + constraints on top.
    """
    bl_idname = "hiho_mocap.spawn_output_rig"
    bl_label = "Spawn Empties"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return bool(context.scene.hiho_mocap.last_processed_path)

    def execute(self, context):
        processed_path = norm_path(context.scene.hiho_mocap.last_processed_path)
        if not processed_path:
            self.report({'ERROR'}, "No processed take. Run Process Mocap first.")
            return {'CANCELLED'}

        # last_processed_path points at output_data/<file>.npy — the recording
        # folder is two parents up.
        recording_folder = os.path.dirname(os.path.dirname(processed_path))
        if not os.path.isdir(recording_folder):
            self.report({'ERROR'}, f"Recording folder missing: {recording_folder}")
            return {'CANCELLED'}

        try:
            root = spawn_skelly_from_recording(recording_folder)
        except Exception as exc:
            self.report({'ERROR'}, f"Spawn failed: {type(exc).__name__}: {exc}")
            return {'CANCELLED'}

        bpy.ops.object.select_all(action='DESELECT')
        root.select_set(True)
        context.view_layer.objects.active = root
        try:
            bpy.ops.view3d.view_selected(use_all_regions=False)
        except RuntimeError:
            pass  # No 3D view context (e.g. headless). Non-fatal.

        msg = f"Spawned {root.name}. Press Spacebar to play."
        untracked = root.get("hiho_untracked", "")
        if untracked:
            msg += f" Not tracked in this take: {untracked}."
        STATE["status_text"] = msg
        self.report({'INFO'}, msg)
        return {'FINISHED'}
