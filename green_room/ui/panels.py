"""Green Room N-panel — the main UI for picking puppets, connecting, and performing."""

import bpy

from ..core.phone_connect import get_local_ip
from ..operators.customize_puppet import draw_customize_sliders


class GREENROOM_PT_puppet_panel(bpy.types.Panel):
    """Puppet selection and customization — the top panel."""

    bl_label = "Your Puppet"
    bl_idname = "GREENROOM_PT_puppet_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Green Room"
    bl_order = 0

    def draw(self, context):
        layout = self.layout
        settings = context.scene.greenroom

        # --- Pick Your Puppet button ---
        row = layout.row()
        row.scale_y = 1.8
        if settings.gr_active_template:
            row.operator("greenroom.pick_puppet",
                         text=f"Puppet: {settings.gr_active_template}",
                         icon='ARMATURE_DATA')
        else:
            row.operator("greenroom.pick_puppet", icon='ARMATURE_DATA')

        # --- Customization sliders (if a template is loaded) ---
        if settings.gr_active_template:
            layout.separator()
            draw_customize_sliders(layout, context)


class GREENROOM_PT_connect_panel(bpy.types.Panel):
    """Phone connection panel with step-by-step instructions."""

    bl_label = "Connect My Phone"
    bl_idname = "GREENROOM_PT_connect_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Green Room"
    bl_order = 1

    def draw(self, context):
        from .. import receiver

        layout = self.layout
        settings = context.scene.greenroom

        if not receiver.is_running:
            self._draw_disconnected(layout, settings)
        elif receiver.is_receiving:
            self._draw_receiving(layout)
        else:
            self._draw_waiting(layout, settings)

    def _draw_disconnected(self, layout, settings):
        """The starting screen — just the connect button."""
        # Port setting (usually leave at default)
        box = layout.box()
        box.label(text="Settings:", icon='PREFERENCES')
        box.prop(settings, "gr_port", text="Port")

        layout.separator()

        row = layout.row()
        row.scale_y = 2.0
        row.operator("greenroom.connect_phone", icon='PLAY')

    def _draw_waiting(self, layout, settings):
        """Connected and listening — show instructions for phone setup."""
        from .. import preview_collections

        layout.label(text="Waiting for your phone...", icon='SORTTIME')
        layout.separator()

        ip = get_local_ip() or "Could not detect IP"
        port = settings.gr_port

        # --- QR Code (if available) ---
        pcoll = preview_collections.get("main")
        if pcoll and "qr_code" in pcoll:
            row = layout.row()
            row.alignment = 'CENTER'
            row.template_icon(icon_value=pcoll["qr_code"].icon_id, scale=10.0)
            layout.separator()

        # --- Connection info (big and clear) ---
        box = layout.box()
        col = box.column(align=True)
        col.scale_y = 1.4
        col.label(text=f"IP Address:  {ip}")
        col.label(text=f"Port:  {port}")

        layout.separator()

        # --- ELI5 step-by-step instructions ---
        box = layout.box()
        box.label(text="How to connect your phone:", icon='INFO')
        col = box.column(align=True)
        col.scale_y = 1.2
        col.label(text='1.  Open "Live Link Face" on your iPhone')
        col.label(text="2.  Tap the gear icon for Settings")
        col.label(text=f'3.  Type this IP address:  {ip}')
        col.label(text=f'4.  Type this port number:  {port}')
        col.label(text='5.  Go back and tap "Live"')
        col.label(text="6.  Make a face — you should see numbers change!")

        layout.separator()
        layout.operator("greenroom.disconnect_phone", icon='CANCEL')

    def _draw_receiving(self, layout):
        """Phone is connected and sending data — show live values."""
        from .. import receiver

        layout.label(text="Phone connected!", icon='CHECKMARK')
        layout.separator()

        # Show key face tracking values as proof it's working
        values = receiver.get_latest_values()

        box = layout.box()
        box.label(text="Live face data:", icon='ARMATURE_DATA')
        col = box.column(align=True)

        jaw = values.get('jawOpen', 0.0)
        blink_l = values.get('eyeBlinkLeft', 0.0)
        blink_r = values.get('eyeBlinkRight', 0.0)
        smile = values.get('mouthSmileRight', 0.0)
        funnel = values.get('mouthFunnel', 0.0)

        col.label(text=f"Jaw open:    {jaw:.2f}")
        col.label(text=f"Blink L:     {blink_l:.2f}")
        col.label(text=f"Blink R:     {blink_r:.2f}")
        col.label(text=f"Smile:       {smile:.2f}")
        col.label(text=f"Mouth shape: {funnel:.2f}")

        layout.separator()
        layout.operator("greenroom.disconnect_phone", icon='CANCEL')
