"""
K-12 Auto UV Unwrapper — Blender Addon
Automatically generates paintable UVs for character meshes.
One click. No seam marking. No UV editor. Just paint.

Three modes for three shape types:
- Character: symmetric bipeds (teddy bear surgery)
- Simple Shape: props and accessories (crack the walnut)
- Thingamabob: creatures and weirdness (the octopus)
"""

bl_info = {
    "name": "K-12 Auto UV Unwrapper",
    "author": "David Bayus / CADRE Lab / SJSU",
    "version": (0, 2, 0),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar > K-12 Tools",
    "description": "One-click automatic UV unwrapping with three shape modes",
    "category": "UV",
}

import bpy

from .operators.auto_uv import (
    KIDBLENDER_OT_auto_uv,
    KIDBLENDER_OT_auto_uv_simple,
    KIDBLENDER_OT_auto_uv_thingamabob,
)
from .ui.panels import KIDBLENDER_PT_uv_panel

classes = (
    KIDBLENDER_OT_auto_uv,
    KIDBLENDER_OT_auto_uv_simple,
    KIDBLENDER_OT_auto_uv_thingamabob,
    KIDBLENDER_PT_uv_panel,
)


def register():
    """Register all addon classes with Blender."""
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    """Unregister all addon classes from Blender."""
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
