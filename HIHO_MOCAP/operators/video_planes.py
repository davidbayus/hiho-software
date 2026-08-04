"""Add Camera Videos operator — load the take's videos as planes.

Recreates the FreeMoCap-reference look (camera videos in the shot) using
Blender's native image-as-planes, via core/video_planes.py. Works on disk, so
no cameras are needed.
"""
import os

import bpy

from ..core.video_planes import load_camera_video_planes


class HIHO_MOCAP_OT_add_camera_videos(bpy.types.Operator):
    """Load this take's camera videos (the MediaPipe-overlay clips) into the
    scene as animated planes, like the FreeMoCap reference. No cameras needed."""
    bl_idname = "hiho_mocap.add_camera_videos"
    bl_label = "Add Camera Videos"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return bool(context.scene.hiho_mocap.last_take_path)

    def execute(self, context):
        take = context.scene.hiho_mocap.last_take_path
        if not take or not os.path.isdir(take):
            self.report({'ERROR'}, "No take folder set. Record/process a take first, "
                                   "or set the Take path in the panel.")
            return {'CANCELLED'}

        created, vdir = load_camera_video_planes(take)
        if not created:
            self.report({'ERROR'}, "No Camera_*.mp4 found in the take's "
                                   "annotated_videos or synchronized_videos folder.")
            return {'CANCELLED'}

        self.report({'INFO'}, f"Added {len(created)} camera video plane(s) "
                              f"from {os.path.basename(vdir)}.")
        return {'FINISHED'}
