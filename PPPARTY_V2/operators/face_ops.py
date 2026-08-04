"""PPParty V2 — Pass 2 face operators.

Same four-button pattern as the body pass:
    Start Face Mirror  / Stop Face Mirror
    Start Face Record  / Stop Face Record

Face mirror is gated on Pass 1 being done (a body NLA strip must
exist on the rig). Pass 1 captures body + arms + hands together,
so the gate only checks for a BodyPass strip — no separate hand
gate after the two-pass refactor.

During face mirror, the body NLA strip plays back so the kid sees
their full prior performance (spine, legs, arms, fingers) while
they record face on top.
"""

import bpy

from ..core.receiver import get_face_receiver
from ..core.recorder import get_face_recorder
from ..core.sender_launcher import get_face_sender_process
from ..core.rig import RIG_OBJECT_NAME
from ._nla import (
    body_pass_baked,
    discard_pass_mutes,
    mute_pass_strips,
    restore_pass_strips,
)


# ---------------------------------------------------------------------------
# Face Mirror operators
# ---------------------------------------------------------------------------

class PPPARTY_V2_OT_start_face_mirror(bpy.types.Operator):
    """Start the face-pass sender and receiver (Pass 2 mirror)."""

    bl_idname = "ppparty_v2.start_face_mirror"
    bl_label = "Start Face Mirror"
    bl_description = (
        "Launch face_sender.py and open the face UDP receiver so your "
        "head rotation drives the head bone live. The body NLA strip "
        "plays back so you see your full prior performance while you "
        "add face on top."
    )
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return (
            body_pass_baked()
            and not get_face_receiver().running
        )

    def execute(self, context):
        # Mute any existing FacePass NLA strips so they don't fight
        # the live receiver during a re-take.
        rig = bpy.data.objects.get(RIG_OBJECT_NAME)
        mute_pass_strips(rig, "FacePass")

        proc = get_face_sender_process()
        ok, msg = proc.start(port=11113)
        if not ok:
            restore_pass_strips(rig, "FacePass")
            self.report({'ERROR'}, msg)
            return {'CANCELLED'}

        get_face_receiver().start()

        # Play back the body NLA strip so the kid sees their full prior
        # performance while recording the face pass.
        context.scene.use_preview_range = False
        bpy.ops.screen.animation_play()

        self.report({'INFO'}, f"Face mirror live — {msg}")
        return {'FINISHED'}


class PPPARTY_V2_OT_stop_face_mirror(bpy.types.Operator):
    """Stop the face-pass sender and receiver."""

    bl_idname = "ppparty_v2.stop_face_mirror"
    bl_label = "Stop Face Mirror"
    bl_description = "Stop the face-pass sender and UDP receiver."
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return get_face_receiver().running

    def execute(self, context):
        rec = get_face_recorder()
        recording_was_active = rec.is_recording
        if recording_was_active:
            ok, msg = rec.stop_recording(context.scene)
            if ok:
                self.report({'INFO'}, f"Auto-stopped recording: {msg}")

        if context.screen.is_animation_playing:
            bpy.ops.screen.animation_play()

        get_face_receiver().stop()
        get_face_sender_process().stop()

        # If recording happened mid-mirror, the new strip is canonical;
        # otherwise restore the strips that Start Mirror muted.
        rig = bpy.data.objects.get(RIG_OBJECT_NAME)
        if recording_was_active:
            discard_pass_mutes("FacePass")
        else:
            restore_pass_strips(rig, "FacePass")

        self.report({'INFO'}, "Face mirror stopped")
        return {'FINISHED'}


# ---------------------------------------------------------------------------
# Face Recording operators
# ---------------------------------------------------------------------------

class PPPARTY_V2_OT_start_face_recording(bpy.types.Operator):
    """Start recording the live face-mirror performance to keyframes."""

    bl_idname = "ppparty_v2.start_face_recording"
    bl_label = "Start Recording"
    bl_description = (
        "Capture the live face-mirror performance to keyframes. Each pose "
        "update writes one keyframe on the head bone. Saved as "
        "'PP_V2_FacePass' and pushed to its own NLA track on Stop — sits "
        "above the body track and owns the head bone (disjoint fcurves)."
    )
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return get_face_receiver().running and not get_face_recorder().is_recording

    def execute(self, context):
        ok, msg = get_face_recorder().start_recording(context.scene)
        if not ok:
            self.report({'ERROR'}, msg)
            return {'CANCELLED'}
        self.report({'INFO'}, msg)
        return {'FINISHED'}


class PPPARTY_V2_OT_stop_face_recording(bpy.types.Operator):
    """Stop face recording, push to NLA, and close the camera (end of pass)."""

    bl_idname = "ppparty_v2.stop_face_recording"
    bl_label = "Stop Recording"
    bl_description = (
        "Stop face-pass recording. The captured head rotation data is "
        "pushed to a new NLA strip and the camera closes — Stop Recording "
        "is the end of the pass. Click Start Face Mirror again for a re-take."
    )
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return get_face_recorder().is_recording

    def execute(self, context):
        ok, msg = get_face_recorder().stop_recording(context.scene)
        if not ok:
            self.report({'ERROR'}, msg)
            return {'CANCELLED'}

        # Auto-close camera + animation playback. Stop Recording = end
        # of pass. The new strip is canonical; prior strips muted by
        # Start Mirror stay muted as drafts.
        if context.screen.is_animation_playing:
            bpy.ops.screen.animation_play()
        get_face_receiver().stop()
        get_face_sender_process().stop()
        discard_pass_mutes("FacePass")

        self.report({'INFO'}, msg)
        return {'FINISHED'}
