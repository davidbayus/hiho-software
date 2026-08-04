"""
QUADRE — One-button quad remesher for character work.

Built by CADRE Lab at SJSU. Wraps QuadWild-BiMDF (via QRemeshify)
with defaults tuned for the K-12 / ART 102 character pipeline.

Select a mesh, hit "Clean Up My Shape", get clean quads.
"""

bl_info = {
    "name": "QUADRE",
    "description": "One-button quad remesher for character work — clean up messy shapes into animation-ready quads",
    "author": "Prof. David Bayus, CADRE Lab (SJSU)",
    "version": (0, 3, 0),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar > QUADRE",
    "category": "Mesh",
}

import bpy

from .operator import QUADRE_OT_cleanup
from .props import QuadreProperties
from .ui import QUADRE_PT_main

classes = [
    QuadreProperties,
    QUADRE_OT_cleanup,
    QUADRE_PT_main,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.kb_quadre = bpy.props.PointerProperty(type=QuadreProperties)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.kb_quadre


if __name__ == "__main__":
    register()
