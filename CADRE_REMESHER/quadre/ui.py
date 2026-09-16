"""
QUADRE — UI Panel.

Minimal by design. One button, a quad count, symmetry toggles.
"""

import bpy
from bpy.types import Panel
from .operator import QUADRE_OT_cleanup


class QUADRE_PT_main(Panel):
    """Main QUADRE panel — the one button a student sees"""
    bl_idname = "QUADRE_PT_main"
    bl_label = "QUADRE"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "QUADRE"

    def draw(self, context):
        layout = self.layout
        props = context.scene.kb_quadre

        # The one button
        layout.operator(
            QUADRE_OT_cleanup.bl_idname,
            text="Clean Up My Shape",
            icon="MESH_GRID",
        )

        # While a job runs the button greys out and this line counts up,
        # so students can see Blender is working, not frozen
        job = QUADRE_OT_cleanup.active_job
        obj = context.active_object
        usable = (
            obj is not None and obj.type == 'MESH' and context.mode == 'OBJECT'
        )
        if job is not None:
            box = layout.box()
            box.label(text=job.status_line(), icon="TIME")
            box.label(text="Blender stays usable — Esc to cancel")
        elif not usable:
            # Mirrors the operator's poll — when the button greys out,
            # say why instead of leaving the student guessing
            layout.label(text="Select your shape in Object Mode to begin", icon="INFO")
        elif bpy.data.is_dirty:
            # A rare engine crash takes unsaved work with it — say so
            # BEFORE the press (a report at press only shows afterwards)
            layout.label(text="Tip: save your file first — just in case", icon="INFO")

        layout.separator()

        # Quad Count — the number students already know from the demos:
        # type how many quads you want, exactly like the paid tool
        layout.prop(props, "quad_count")

        layout.separator()

        # Symmetry toggles
        row = layout.row(align=True, heading="Symmetry")
        row.prop(props, "symmetry_x", toggle=True, icon="MOD_MIRROR")
        row.prop(props, "symmetry_y", toggle=True, icon="MOD_MIRROR")
