# SPDX-License-Identifier: GPL-3.0-or-later
# PPParty — The People's Puppet Party
# Full-body digital marionette addon for Blender 5.0+
# CADRE Lab @ San Jose State University

bl_info = {
    "name": "The People's Puppet Party",
    "author": "David Bayus — CADRE Lab, SJSU",
    "version": (0, 9, 4),
    "blender": (5, 0, 0),
    "location": "View3D > Sidebar > PPPARTY",
    "description": "Face-tracked marionette — material slots, head design, "
                   "capsule body, customization, knee lift, arm gestures",
    "category": "Animation",
}

import bpy

from .core.osc_receiver import OSCReceiver
from .operators.create_marionette import (
    PPPARTY_OT_create_marionette,
    PPPARTY_OT_reset_physics,
)
from .operators.connect_phone import (
    PPPARTY_OT_connect_phone,
    PPPARTY_OT_disconnect_phone,
)
from .operators.debug_modifier import PPPARTY_OT_debug_modifier
from .ui.panels import (
    PPPARTY_PT_main_panel,
    PPPARTY_PT_connect_panel,
    PPPARTY_PT_debug_panel,
    PPPARTY_PT_instructions_panel,
)

# Shared OSC receiver instance — one receiver for the whole addon
receiver = OSCReceiver()


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
        description="UDP port for receiving Live Link Face data",
    )


classes = (
    PPPartySettings,
    PPPARTY_OT_create_marionette,
    PPPARTY_OT_reset_physics,
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
