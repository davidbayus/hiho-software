"""Connect My Phone — one-button phone connection for face tracking."""

import bpy

from ..core.phone_connect import get_local_ip, generate_qr_png


class GREENROOM_OT_connect_phone(bpy.types.Operator):
    """Start listening for your phone's face tracking data"""

    bl_idname = "greenroom.connect_phone"
    bl_label = "Connect My Phone"

    def execute(self, context):
        from .. import receiver, preview_collections
        from ..core.osc_receiver import ensure_dummy_mesh

        if receiver.is_running:
            self.report({'WARNING'}, "Already connected!")
            return {'CANCELLED'}

        # Make sure the dummy mesh exists to receive face data
        ensure_dummy_mesh()

        # Get connection settings
        settings = context.scene.greenroom
        port = settings.gr_port

        # Find the armature with a "head" bone for head rotation
        target_armature = None
        target_bone = None
        for obj in context.scene.objects:
            if obj.type == 'ARMATURE':
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
            self.report({'ERROR'}, f"Could not start — port {port} may be in use")
            return {'CANCELLED'}

        # Detect our IP and generate QR code
        # Plain text format so phones display it as text, not try to open a URL
        ip = get_local_ip() or "unknown"
        qr_text = f"Green Room\nIP: {ip}\nPort: {port}"
        qr_path = generate_qr_png(qr_text)

        # Load QR image into preview collection for panel display
        pcoll = preview_collections.get("main")
        if pcoll is not None:
            import bpy.utils.previews
            bpy.utils.previews.remove(pcoll)
            pcoll = bpy.utils.previews.new()
            preview_collections["main"] = pcoll
            pcoll.load("qr_code", qr_path, 'IMAGE')

        self.report({'INFO'}, f"Listening on {ip}:{port} — connect your phone!")

        # Force panel redraw
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()

        return {'FINISHED'}


class GREENROOM_OT_disconnect_phone(bpy.types.Operator):
    """Stop listening for face tracking data"""

    bl_idname = "greenroom.disconnect_phone"
    bl_label = "Disconnect"

    def execute(self, context):
        from .. import receiver

        receiver.stop()
        self.report({'INFO'}, "Disconnected")

        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()

        return {'FINISHED'}
