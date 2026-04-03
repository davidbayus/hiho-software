"""
UI Panels — Where the buttons live in Blender.

Shows up in the 3D Viewport sidebar (press N to open) under "PaWrappa."

V0.3.3 — Better hints pointing to Adjust Last Operation panel.
One big button, one slider, clear instructions.
"""

import bpy


class PAWRAPPA_PT_uv_panel(bpy.types.Panel):
    """Panel in the 3D Viewport sidebar for UV tools."""

    bl_label = "PaWrappa"
    bl_idname = "PAWRAPPA_PT_uv_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "PaWrappa"

    def draw(self, context):
        layout = self.layout
        obj = context.active_object

        if obj is None or obj.type != 'MESH':
            layout.label(text="Select a mesh to unwrap", icon='INFO')
            return

        mesh = obj.data

        # --- Main Button ---
        box = layout.box()
        col = box.column(align=True)
        col.label(text="Automatic UV Unwrap", icon='UV_DATA')

        # The big button
        row = col.row(align=True)
        row.scale_y = 2.0
        row.operator(
            "pawrappa.face_cluster",
            text="Auto Seams",
            icon='SHARPCURVE',
        )

        # --- Slider Hint ---
        col.separator()
        col.label(text="After clicking, adjust the slider at")
        col.label(text="  bottom-left of viewport (or press F9)")
        col.label(text="  Left = more pieces, Right = fewer")
        col.label(text="  Try 0.85 - 0.90 for characters")

        # --- Status ---
        layout.separator()
        box = layout.box()
        if mesh.uv_layers:
            uv_name = mesh.uv_layers.active.name if mesh.uv_layers.active else "None"
            box.label(text=f"UV Map: {uv_name}", icon='CHECKMARK')
            seam_count = sum(1 for e in mesh.edges if e.use_seam)
            box.label(text=f"Seams: {seam_count} edges")
        else:
            box.label(text="No UVs yet", icon='ERROR')
            seam_count = sum(1 for e in mesh.edges if e.use_seam)
            if seam_count > 0:
                box.label(text=f"Seams: {seam_count} (ready to unwrap)")
            else:
                box.label(text="Click Auto Seams to get started!")

        # Mesh info
        col = box.column(align=True)
        col.label(text=f"Verts: {len(mesh.vertices):,}  |  Faces: {len(mesh.polygons):,}")
