"""Connect My Phone — one-button phone connection for PPParty face tracking."""

import bpy

from ..core.phone_connect import get_local_ip


class PPPARTY_OT_connect_phone(bpy.types.Operator):
    """Start listening for your phone's face tracking data"""

    bl_idname = "ppparty.connect_phone"
    bl_label = "Connect My Phone"

    def execute(self, context):
        from .. import receiver
        from ..core.osc_receiver import ensure_dummy_mesh

        if receiver.is_running:
            self.report({'WARNING'}, "Already connected!")
            return {'CANCELLED'}

        # Make sure the dummy mesh exists to receive face data
        ensure_dummy_mesh()

        # Get port from scene settings
        settings = context.scene.ppparty
        port = settings.pp_port

        # Find the PPParty armature with a "head" bone
        target_armature = None
        target_bone = None
        for obj in context.scene.objects:
            if obj.type == 'ARMATURE' and obj.name.startswith('PP_'):
                for bone in obj.data.bones:
                    if bone.name == 'head':
                        target_armature = obj
                        target_bone = 'head'
                        break
                if target_armature:
                    break

        # Start the OSC receiver
        if not receiver.start(port=port,
                              target_armature=target_armature,
                              target_bone=target_bone):
            self.report({'ERROR'}, f"Could not start -- port {port} may be in use")
            return {'CANCELLED'}

        ip = get_local_ip() or "unknown"
        self.report({'INFO'}, f"Listening on {ip}:{port} -- connect your phone!")

        # Force panel redraw
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()

        return {'FINISHED'}


class PPPARTY_OT_disconnect_phone(bpy.types.Operator):
    """Stop listening for face tracking data"""

    bl_idname = "ppparty.disconnect_phone"
    bl_label = "Disconnect"

    def execute(self, context):
        from .. import receiver

        receiver.stop()
        self.report({'INFO'}, "Disconnected")

        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()

        return {'FINISHED'}
