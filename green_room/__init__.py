# SPDX-License-Identifier: GPL-3.0-or-later
# Green Room — A virtual puppet show addon for K-12 students
# CADRE Lab @ San Jose State University

bl_info = {
    "name": "Green Room",
    "blender": (4, 5, 0),
    "category": "3D View",
    "description": "A virtual puppet show for K-12 students. Pick a puppet, connect your phone, and perform!",
    "author": "David Bayus, CADRE Lab @ SJSU",
    "version": (0, 1, 0),
}

import bpy
import bpy.utils.previews

from .core.osc_receiver import OSCReceiver
from .operators.connect_phone import (
    GREENROOM_OT_connect_phone,
    GREENROOM_OT_disconnect_phone,
)
from .ui.panels import GREENROOM_PT_connect_panel


# --- Shared addon state ---
receiver = OSCReceiver()
preview_collections = {}


class GreenRoomSettings(bpy.types.PropertyGroup):
    """Scene-level settings for Green Room."""

    gr_port: bpy.props.IntProperty(
        name="Port",
        default=11111,
        min=1024,
        max=65535,
        description="UDP port for receiving face tracking data",
    )


classes = (
    GreenRoomSettings,
    GREENROOM_OT_connect_phone,
    GREENROOM_OT_disconnect_phone,
    GREENROOM_PT_connect_panel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.greenroom = bpy.props.PointerProperty(type=GreenRoomSettings)

    pcoll = bpy.utils.previews.new()
    preview_collections["main"] = pcoll


def unregister():
    receiver.stop()

    for pcoll in preview_collections.values():
        bpy.utils.previews.remove(pcoll)
    preview_collections.clear()

    del bpy.types.Scene.greenroom

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
