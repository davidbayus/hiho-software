"""PPParty V2 — Start / Stop body mirror operators.

The user-facing buttons. Wires the rig + UDP receiver + sender
subprocess into a single Start/Stop pair so the kid only sees one
button — no separate "open port", "launch tracker", "create rig"
steps.
"""

import bpy

from ..core.receiver import get_receiver
from ..core.rig import RIG_OBJECT_NAME, build_v2_rig
from ..core.sender_launcher import get_sender_process
from ._nla import mute_pass_strips, restore_pass_strips


class PPPARTY_V2_OT_start_body_mirror(bpy.types.Operator):
    """Start body-mirror mode: webcam tracks body, V2 rig follows."""

    bl_idname = "ppparty_v2.start_body_mirror"
    bl_label = "Start Body Mirror"
    bl_description = (
        "Start tracking body from webcam. Spawns the V2 rig if it isn't "
        "already in the scene, opens a UDP receiver, and launches the "
        "MediaPipe sender as a separate Python process"
    )
    bl_options = {'REGISTER'}

    show_preview: bpy.props.BoolProperty(
        name="Show Tracker Preview",
        description="Open the MediaPipe tracker preview window so you can see what the camera sees",
        default=True,
    )

    def execute(self, context):
        # 1. Ensure the rig exists.
        rig = bpy.data.objects.get(RIG_OBJECT_NAME)
        if rig is None:
            rig = build_v2_rig(context)

        # 2. Mute any existing BodyPass NLA strips so they don't fight
        #    the live receiver. Restored on Stop Mirror (no recording);
        #    discarded on Stop Recording (the new strip wins).
        mute_pass_strips(rig, "BodyPass")

        # 3. Start the receiver (UDP listener + Blender timer).
        receiver = get_receiver()
        try:
            receiver.start()
        except OSError as e:
            self.report(
                {'ERROR'},
                f"UDP port busy ({e}). Stop any existing mirror first, "
                "then retry.",
            )
            return {'CANCELLED'}

        # 4. Launch the sender subprocess.
        sender = get_sender_process()
        ok, msg = sender.start(
            port=receiver.port,
            no_preview=not self.show_preview,
        )
        if not ok:
            receiver.stop()
            self.report({'ERROR'}, msg)
            return {'CANCELLED'}

        self.report({'INFO'}, "Body mirror running. Wave at the camera.")
        return {'FINISHED'}


class PPPARTY_V2_OT_stop_body_mirror(bpy.types.Operator):
    """Stop body-mirror mode: kill sender and shut down receiver."""

    bl_idname = "ppparty_v2.stop_body_mirror"
    bl_label = "Stop Body Mirror"
    bl_description = (
        "Stop the body mirror — kill the sender process and close the UDP receiver"
    )
    bl_options = {'REGISTER'}

    def execute(self, context):
        get_sender_process().stop()
        get_receiver().stop()
        # Restore the BodyPass NLA strips that Start Mirror muted, so
        # the previously-recorded take resumes playback.
        rig = bpy.data.objects.get(RIG_OBJECT_NAME)
        restore_pass_strips(rig, "BodyPass")
        self.report({'INFO'}, "Body mirror stopped.")
        return {'FINISHED'}
