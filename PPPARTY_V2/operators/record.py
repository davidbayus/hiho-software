"""PPParty V2 — Start / Stop body recording operators.

The user-facing buttons. Recording can only run while a body-mirror
session is live (the recorder hooks into the receiver's tick loop).
The operator's poll() enforces that gate so the buttons grey out
when there's no live mirror.
"""

import bpy

from ..core.receiver import get_receiver
from ..core.recorder import get_recorder
from ..core.rig import RIG_OBJECT_NAME
from ..core.sender_launcher import get_sender_process
from ._nla import discard_pass_mutes


class PPPARTY_V2_OT_start_body_recording(bpy.types.Operator):
    """Start recording the live body-mirror performance to keyframes."""

    bl_idname = "ppparty_v2.start_body_recording"
    bl_label = "Start Recording"
    bl_description = (
        "Capture the live body-mirror performance to keyframes on the V2 rig. "
        "Each pose update writes one keyframe; the result is a Blender Action "
        "named 'PP_V2_BodyPass'"
    )
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return get_receiver().running and not get_recorder().is_recording

    def execute(self, context):
        ok, msg = get_recorder().start_recording(context.scene)
        if not ok:
            self.report({'ERROR'}, msg)
            return {'CANCELLED'}
        self.report({'INFO'}, msg)
        return {'FINISHED'}


class PPPARTY_V2_OT_stop_body_recording(bpy.types.Operator):
    """Stop recording, push to NLA, and close the camera (end of pass)."""

    bl_idname = "ppparty_v2.stop_body_recording"
    bl_label = "Stop Recording"
    bl_description = (
        "Stop body-pass recording. The captured pose data is pushed to a "
        "new NLA strip and the camera closes — Stop Recording is the end "
        "of the pass. Click Start Mirror again for a re-take."
    )
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return get_recorder().is_recording

    def execute(self, context):
        ok, msg = get_recorder().stop_recording(context.scene)
        if not ok:
            self.report({'ERROR'}, msg)
            return {'CANCELLED'}

        # Auto-close camera + receiver: Stop Recording = end of pass.
        # The new strip is canonical; prior strips muted by Start Mirror
        # stay muted as drafts.
        get_sender_process().stop()
        get_receiver().stop()
        discard_pass_mutes("BodyPass")

        self.report({'INFO'}, msg)
        return {'FINISHED'}
