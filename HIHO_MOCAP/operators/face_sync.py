"""Line Up Face operators — flash-marker sync between body and face takes.

Four buttons in the Face section: Add Face Video puts the phone's reference
clip in the scene as one more plane beside the camera videos; the two Mark
Flash buttons store the playhead frame where the flash appears in each view;
Line Up Face shifts the face action and the face plane so the flashes land
on the same timeline frame. Zero typed numbers — the playhead does all the
math (FACE_CAPTURE_DESIGN_2026-07-20).
"""

import os

import bpy

from ..core import face_sync
from ..core.video_planes import (
    FACE_PLANE_NAME,
    find_face_video,
    load_face_video_plane,
    set_face_plane_offset,
)
from . import STATE, norm_path


class HIHO_MOCAP_OT_add_face_video(bpy.types.Operator):
    """Put the face take's reference video in the scene as a plane, beside
    the camera videos, so the flash can be found by scrubbing."""
    bl_idname = "hiho_mocap.add_face_video"
    bl_label = "Add Face Video"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return bool(context.scene.hiho_mocap.face_take_csv)

    def execute(self, context):
        csv_path = norm_path(context.scene.hiho_mocap.face_take_csv)
        if not csv_path or not os.path.isfile(csv_path):
            self.report({'ERROR'}, f"Face take CSV not found: {csv_path}")
            return {'CANCELLED'}
        video = find_face_video(csv_path)
        if video is None:
            self.report({'ERROR'},
                        "No video found next to the CSV. AirDrop the take's "
                        ".mov along with it (they arrive together).")
            return {'CANCELLED'}
        obj = load_face_video_plane(video)
        if obj is None:
            self.report({'ERROR'},
                        f"Blender could not load {os.path.basename(video)} "
                        "as a video plane.")
            return {'CANCELLED'}
        msg = f"Added the face video plane ({os.path.basename(video)})."
        STATE["status_text"] = msg
        self.report({'INFO'}, msg)
        return {'FINISHED'}


class HIHO_MOCAP_OT_mark_flash_body(bpy.types.Operator):
    """Scrub the timeline to the flash in the CAMERA video planes, then
    click: the playhead frame becomes the body side of the sync."""
    bl_idname = "hiho_mocap.mark_flash_body"
    bl_label = "Mark Flash (Body)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        settings = context.scene.hiho_mocap
        settings.flash_body_frame = context.scene.frame_current_final
        self.report({'INFO'},
                    f"Body flash marked at frame {settings.flash_body_frame:.0f}.")
        return {'FINISHED'}


class HIHO_MOCAP_OT_mark_flash_face(bpy.types.Operator):
    """Scrub the timeline to the flash in the FACE video plane, then click:
    the playhead frame becomes the face side of the sync."""
    bl_idname = "hiho_mocap.mark_flash_face"
    bl_label = "Mark Flash (Face)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        settings = context.scene.hiho_mocap
        settings.flash_face_frame = context.scene.frame_current_final
        # Remember how far the face content was already shifted when this
        # mark was taken, so a re-mark corrects instead of compounding.
        plane = bpy.data.objects.get(FACE_PLANE_NAME)
        if plane is not None:
            settings.face_flash_offset_at_mark = float(
                plane.get("hiho_applied_offset", 0.0))
        else:
            action = face_sync.find_face_action(
                face_sync.find_face_target(context))
            settings.face_flash_offset_at_mark = face_sync.applied_offset(action)
        self.report({'INFO'},
                    f"Face flash marked at frame {settings.flash_face_frame:.0f}.")
        return {'FINISHED'}


class HIHO_MOCAP_OT_line_up_face(bpy.types.Operator):
    """Shift the face take (action + video plane) so its flash lands on the
    body's flash. Re-runnable: re-mark either flash and click again to
    correct — it never compounds."""
    bl_idname = "hiho_mocap.line_up_face"
    bl_label = "Line Up Face"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        settings = context.scene.hiho_mocap
        return (settings.flash_body_frame >= 0.0
                and settings.flash_face_frame >= 0.0)

    def execute(self, context):
        settings = context.scene.hiho_mocap
        target = face_sync.find_face_target(context)
        action = face_sync.find_face_action(target)
        if action is None:
            self.report({'ERROR'},
                        "No face take loaded. Click Load Face Take first.")
            return {'CANCELLED'}

        goal = face_sync.target_offset(
            settings.flash_body_frame, settings.flash_face_frame,
            settings.face_flash_offset_at_mark)
        delta = goal - face_sync.applied_offset(action)

        if abs(delta) > 1e-6:
            _, last = face_sync.shift_action(action, delta)
            action[face_sync.ACTION_OFFSET_PROP] = goal
            if context.scene.frame_end < int(last) + 1:
                context.scene.frame_end = int(last) + 1

        plane = bpy.data.objects.get(FACE_PLANE_NAME)
        plane_moved = plane is not None and set_face_plane_offset(plane, goal)

        settings.face_applied_offset = goal

        if abs(delta) <= 1e-6:
            msg = "Face already lined up - nothing to move."
        else:
            msg = (f"Face lined up (moved {delta:+.1f} frames"
                   + ("" if plane_moved else "; no face video plane to move")
                   + "). Press Spacebar to watch them together.")
        if goal < 0:
            self.report({'WARNING'},
                        "The face take now starts before the timeline start; "
                        "its first moments won't play.")
        STATE["status_text"] = msg
        self.report({'INFO'}, msg)
        return {'FINISHED'}
