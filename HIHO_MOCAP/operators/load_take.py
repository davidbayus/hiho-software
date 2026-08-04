"""Load Take operator — point at any processed HIHO recording folder and
bring its motion into the scene.

Wraps the shipped Spawn Rig path: validates the folder is a processed take,
sets last_processed_path to its body npy, and runs hiho_mocap.spawn_rig
(empties + skelly armature + constraints). Works with takes from this
machine or copied from any other HIHO rig.
"""

import os

import bpy

from ..core.scene_clock import set_scene_clock_from_take
from . import STATE


def _find_view3d_override(context):
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                region = next((r for r in area.regions if r.type == 'WINDOW'), None)
                if region:
                    return {"window": window, "area": area, "region": region}
    return None


class HIHO_MOCAP_OT_load_take(bpy.types.Operator):
    """Pick a processed take folder (from any HIHO recording) and load its motion"""
    bl_idname = "hiho_mocap.load_take"
    bl_label = "Load Take"
    bl_options = {'REGISTER', 'UNDO'}

    directory: bpy.props.StringProperty(subtype='DIR_PATH')
    filter_folder: bpy.props.BoolProperty(default=True, options={'HIDDEN'})

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        take_folder = os.path.normpath(os.path.expanduser(bpy.path.abspath(self.directory)))
        if not os.path.isdir(take_folder):
            self.report({'ERROR'}, f"Not a folder: {take_folder}")
            return {'CANCELLED'}

        body_npy = os.path.join(take_folder, "output_data", "mediapipe_body_3d_xyz.npy")
        if not os.path.isfile(body_npy):
            # student may have picked output_data itself, or one level above the take
            candidates = [
                os.path.join(take_folder, "mediapipe_body_3d_xyz.npy"),
            ]
            for name in sorted(os.listdir(take_folder)):
                candidates.append(os.path.join(take_folder, name, "output_data",
                                               "mediapipe_body_3d_xyz.npy"))
            found = next((c for c in candidates if os.path.isfile(c)), None)
            if found is None:
                self.report({'ERROR'},
                            "That folder isn't a processed take (no output_data/"
                            "mediapipe_body_3d_xyz.npy inside). Pick the take's "
                            "own folder, e.g. import_2026-05-16_11-34-07.")
                return {'CANCELLED'}
            body_npy = found

        context.scene.hiho_mocap.last_processed_path = body_npy

        # This execute runs in the FILE BROWSER's context (fileselect_add
        # callback), where spawn_rig's armature_add poll fails ("context is
        # incorrect" — David hit this on 1.4.8). Hand it a real 3D viewport.
        override = _find_view3d_override(context)
        if override:
            with context.temp_override(**override):
                if context.mode != 'OBJECT' and context.active_object:
                    bpy.ops.object.mode_set(mode='OBJECT')
                result = bpy.ops.hiho_mocap.spawn_rig()
        else:
            result = bpy.ops.hiho_mocap.spawn_rig()
        if result != {'FINISHED'}:
            return result

        take_name = os.path.basename(os.path.dirname(os.path.dirname(body_npy)))
        msg = f"Loaded take {take_name}. Press Spacebar to preview, or Send to Character."

        # Scene clock from the recorder's sidecar (shared helper; spawn_rig
        # already ran it — idempotent, see SIDECAR_ON_SPAWN_DESIGN_2026-07-04).
        clock_msg, clock_warning = set_scene_clock_from_take(
            context.scene, body_npy)
        if clock_warning:
            STATE["status_text"] = clock_msg
            self.report({'WARNING'}, f"{msg} {clock_msg}")
        else:
            msg += f" {clock_msg}"
            STATE["status_text"] = msg
            self.report({'INFO'}, msg)
        return {'FINISHED'}
