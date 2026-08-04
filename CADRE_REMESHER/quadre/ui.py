"""
QUADRE — UI Panel.

Minimal by design. One button, a detail slider, symmetry toggles.
"""

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
        if job is not None:
            box = layout.box()
            box.label(text=job.status_line(), icon="TIME")
            box.label(text="Blender stays usable — Esc to cancel")

        layout.separator()

        # Detail slider — left is low poly, right is high detail
        col = layout.column()
        col.label(text="Detail:")
        row = col.row(align=True)
        row.label(text="Low")
        row.prop(props, "detail", text="", slider=True)
        row.label(text="High")

        layout.separator()

        # Symmetry toggles
        row = layout.row(align=True, heading="Symmetry")
        row.prop(props, "symmetry_x", toggle=True, icon="MOD_MIRROR")
        row.prop(props, "symmetry_y", toggle=True)
