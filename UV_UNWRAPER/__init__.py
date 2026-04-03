"""
PaWrappa the UV Unwrapper — Blender Addon
Automatically generates paintable UVs for character meshes.
One click. No seam marking. No UV editor. Just paint.

Three modes for three shape types:
- Character: symmetric bipeds (teddy bear surgery)
- Simple Shape: props and accessories (crack the walnut)
- Thingamabob: creatures and weirdness (the octopus)
"""

bl_info = {
    "name": "PaWrappa the UV Unwrapper",
    "author": "David Bayus / CADRE Lab / SJSU",
    "version": (0, 3, 0),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar > PaWrappa",
    "description": "One-click automatic UV unwrapping with three shape modes",
    "category": "UV",
}

import bpy

from .operators.auto_uv import (
    PAWRAPPA_OT_auto_uv,
    PAWRAPPA_OT_auto_uv_simple,
    PAWRAPPA_OT_auto_uv_thingamabob,
)
from .operators.edge_scorer import PAWRAPPA_OT_edge_score
from .operators.face_cluster import PAWRAPPA_OT_face_cluster
from .ui.panels import PAWRAPPA_PT_uv_panel

classes = (
    PAWRAPPA_OT_auto_uv,
    PAWRAPPA_OT_auto_uv_simple,
    PAWRAPPA_OT_auto_uv_thingamabob,
    PAWRAPPA_OT_edge_score,
    PAWRAPPA_OT_face_cluster,
    PAWRAPPA_PT_uv_panel,
)


def register():
    """Register all addon classes with Blender."""
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.pw_show_legacy = bpy.props.BoolProperty(
        name="Show Legacy Modes",
        default=False,
    )


def unregister():
    """Unregister all addon classes from Blender."""
    if hasattr(bpy.types.Scene, "pw_show_legacy"):
        del bpy.types.Scene.pw_show_legacy
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
