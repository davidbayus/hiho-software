# SPDX-License-Identifier: GPL-3.0-or-later
"""PPParty N-panel — radically simplified.

One panel, two buttons: Create Puppet and Start/Stop Webcam. Everything
else (sliders, materials, Studio Track Object slots) lives on the
Geometry Nodes modifier in the Properties panel — no need to duplicate
it here. The N-panel is a stage, not a cockpit.
"""

import bpy


class PPPARTY_PT_main_panel(bpy.types.Panel):
    """PPParty control panel — Create Puppet + Start Webcam only."""

    bl_label = "PPParty"
    bl_idname = "PPPARTY_PT_main_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "PPPARTY"

    def draw(self, context):
        layout = self.layout

        # One row, one column — the two buttons the student needs.
        layout.operator("ppparty.create_marionette", text="Create Puppet")

        from .. import receiver
        if receiver.is_running:
            # Tracking source is live — offer the stop button matching the source
            if receiver.source == 'mediapipe':
                layout.operator("ppparty.stop_webcam", text="Stop Webcam")
            else:
                layout.operator("ppparty.disconnect_phone",
                                text="Stop Webcam")
        else:
            layout.operator("ppparty.start_webcam", text="Start Webcam")
