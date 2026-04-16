# SPDX-License-Identifier: GPL-3.0-or-later
# PPParty — The People's Puppet Party
# Full-body digital marionette addon for Blender 5.0+
# CADRE Lab @ San Jose State University

bl_info = {
    "name": "The People's Puppet Party",
    "author": "David Bayus — CADRE Lab, SJSU",
    "version": (1, 0, 0),
    "blender": (5, 0, 0),
    "location": "View3D > Sidebar > PPPARTY",
    "description": "Face + body tracked marionette — webcam via MediaPipe,"
                   " node groups, material slots, head design",
    "category": "Animation",
}

import bpy

from .core.osc_receiver import TrackingReceiver
from .operators.create_marionette import (
    PPPARTY_OT_create_marionette,
    PPPARTY_OT_reset_physics,
)
from .operators.connect_phone import (
    PPPARTY_OT_connect_phone,
    PPPARTY_OT_disconnect_phone,
)
from .operators.start_webcam import (
    PPPARTY_OT_start_webcam,
    PPPARTY_OT_stop_webcam,
)
from .operators.debug_modifier import PPPARTY_OT_debug_modifier
from .ui.panels import (
    PPPARTY_PT_main_panel,
    PPPARTY_PT_connect_panel,
    PPPARTY_PT_debug_panel,
    PPPARTY_PT_instructions_panel,
)

# Shared tracking receiver — handles both MediaPipe and Live Link Face
receiver = TrackingReceiver()


class PPPartySettings(bpy.types.PropertyGroup):
    """Scene-level settings for PPParty."""

    pp_active_puppet: bpy.props.StringProperty(
        name="Active Puppet",
        default="",
        description="Name of the currently active marionette object",
    )

    pp_port: bpy.props.IntProperty(
        name="Port",
        default=11111,
        min=1024,
        max=65535,
        description="UDP port for tracking data (webcam or phone)",
    )

    pp_show_preview: bpy.props.BoolProperty(
        name="Show Tracker Window",
        default=True,
        description="Show webcam preview with face/body tracking overlay",
    )


classes = (
    PPPartySettings,
    PPPARTY_OT_create_marionette,
    PPPARTY_OT_reset_physics,
    PPPARTY_OT_start_webcam,
    PPPARTY_OT_stop_webcam,
    PPPARTY_OT_connect_phone,
    PPPARTY_OT_disconnect_phone,
    PPPARTY_OT_debug_modifier,
    PPPARTY_PT_main_panel,
    PPPARTY_PT_connect_panel,
    PPPARTY_PT_debug_panel,
    PPPARTY_PT_instructions_panel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.ppparty = bpy.props.PointerProperty(type=PPPartySettings)


def unregister():
    # Stop receiver if running (cleanup on addon disable)
    receiver.stop()

    del bpy.types.Scene.ppparty
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
