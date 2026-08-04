"""Spawn Rig operator — the full FreeMoCap-canonical output.

Builds a freemocap-style armature from the captured empties + applies the
ajc27 constraint stack so the rig animates with the motion. Matches the
output users see in every FreeMoCap tutorial and Discord thread.

Idempotent: each click purges any prior HIHO_MOCAP_Skelly_<take> +
HIHO_MOCAP_Rig_<take> for this recording (including their child empties,
animation actions, and armature data), then rebuilds both fresh. Lets the
student iterate without manually cleaning the scene between attempts.
"""

import os

import bpy

from ..core.bind_to_rig import apply_constraints, clear_hiho_constraints
from ..core.build_rig import build_freemocap_armature
from ..core.output_rig import spawn_skelly_from_recording
from ..core.scene_clock import set_scene_clock_from_take
from ..core.virtual_landmarks import ensure_virtual_empties
from . import STATE, norm_path


class HIHO_MOCAP_OT_spawn_rig(bpy.types.Operator):
    """Build the freemocap-style armature for the most recently processed take."""
    bl_idname = "hiho_mocap.spawn_rig"
    bl_label = "Spawn Rig"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return bool(context.scene.hiho_mocap.last_processed_path)

    def execute(self, context):
        processed_path = norm_path(context.scene.hiho_mocap.last_processed_path)
        if not processed_path:
            self.report({'ERROR'}, "No processed take. Run Process Mocap first.")
            return {'CANCELLED'}

        recording_folder = os.path.dirname(os.path.dirname(processed_path))
        if not os.path.isdir(recording_folder):
            self.report({'ERROR'}, f"Recording folder missing: {recording_folder}")
            return {'CANCELLED'}

        folder_name = os.path.basename(os.path.normpath(recording_folder))
        rig_name = f"HIHO_MOCAP_Rig_{folder_name}"
        skelly_name = f"HIHO_MOCAP_Skelly_{folder_name}"

        _purge_existing(rig_name, skelly_name)

        try:
            skelly_root = spawn_skelly_from_recording(recording_folder)
        except Exception as exc:
            self.report({'ERROR'}, f"Spawn empties failed: {type(exc).__name__}: {exc}")
            return {'CANCELLED'}

        try:
            ensure_virtual_empties(recording_folder, skelly_root)
        except Exception as exc:
            self.report({'ERROR'}, f"Virtual landmarks failed: {type(exc).__name__}: {exc}")
            return {'CANCELLED'}

        try:
            rig = build_freemocap_armature(
                recording_folder=recording_folder,
                rig_name=rig_name,
                parent_object=skelly_root,
            )
        except Exception as exc:
            self.report({'ERROR'}, f"Build armature failed: {type(exc).__name__}: {exc}")
            return {'CANCELLED'}

        clear_hiho_constraints(rig)
        try:
            bound, skipped = apply_constraints(rig, skelly_root)
        except Exception as exc:
            self.report({'ERROR'}, f"Apply constraints failed: {type(exc).__name__}: {exc}")
            return {'CANCELLED'}

        bpy.ops.object.select_all(action='DESELECT')
        rig.select_set(True)
        context.view_layer.objects.active = rig
        try:
            bpy.ops.view3d.view_selected(use_all_regions=False)
        except RuntimeError:
            pass

        msg = f"Built {rig.name} ({len(bound)} bones bound"
        if skipped:
            msg += f", {len(skipped)} skipped"
        msg += "). Press Spacebar to play."
        untracked = skelly_root.get("hiho_untracked", "")
        if untracked:
            msg += f" Not tracked in this take: {untracked}."

        # Both student paths (Record→Process→Spawn and Load Take) converge
        # here, so this is where the take's true fps reaches the scene.
        clock_msg, clock_warning = set_scene_clock_from_take(
            context.scene, processed_path)
        msg += f" {clock_msg}"

        STATE["status_text"] = msg
        self.report({'WARNING'} if clock_warning else {'INFO'}, msg)
        return {'FINISHED'}


def _purge_existing(rig_name: str, skelly_name: str) -> None:
    """Delete the prior Skelly + Rig + their descendants/data-blocks.

    Without this, a re-click would either error (rig exists) or silently
    reuse stale empties from a broken earlier alignment, hiding the fix.
    """
    rig = bpy.data.objects.get(rig_name)
    if rig is not None:
        arm_data = rig.data
        bpy.data.objects.remove(rig, do_unlink=True)
        if arm_data is not None and arm_data.users == 0:
            bpy.data.armatures.remove(arm_data)

    skelly = bpy.data.objects.get(skelly_name)
    if skelly is not None:
        actions_to_purge = []
        for child in list(skelly.children_recursive):
            if child.animation_data is not None and child.animation_data.action is not None:
                actions_to_purge.append(child.animation_data.action)
            bpy.data.objects.remove(child, do_unlink=True)
        bpy.data.objects.remove(skelly, do_unlink=True)
        for action in actions_to_purge:
            if action.users == 0:
                bpy.data.actions.remove(action)
