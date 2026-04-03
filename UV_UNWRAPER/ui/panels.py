"""
UI Panels — Where the buttons live in Blender.

Shows up in the 3D Viewport sidebar (press N to open) under "PaWrappa."

Current layout (V0.3.0 testing):
- Auto Seams — curvature-based face clustering, one button for any shape
- Score Edges — debug tool to visualize curvature
- Status — seam count, UV info, mesh info
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

        # --- Auto Seams ---
        box = layout.box()
        col = box.column(align=True)
        col.label(text="Auto UV — Works on any shape", icon='UV_DATA')
        row = col.row(align=True)
        row.scale_y = 2.0
        row.operator(
            "pawrappa.face_cluster",
            text="Auto Seams",
            icon='SHARPCURVE',
        )

        # --- Debug: Edge Scorer ---
        layout.separator()
        box = layout.box()
        col = box.column(align=True)
        col.label(text="Debug Tools", icon='TOOL_SETTINGS')
        row = col.row(align=True)
        row.operator(
            "pawrappa.edge_score",
            text="Score Edges",
            icon='EDGESEL',
        )

        # --- Legacy modes (collapsed) ---
        box = layout.box()
        col = box.column(align=True)
        row = col.row(align=True)
        row.prop(
            context.scene, "pw_show_legacy",
            text="Legacy Modes",
            icon='TRIA_DOWN' if context.scene.get("pw_show_legacy", False) else 'TRIA_RIGHT',
            emboss=False,
        )
        if context.scene.get("pw_show_legacy", False):
            col.operator("pawrappa.auto_uv", text="Character", icon='MOD_ARMATURE')
            col.operator("pawrappa.auto_uv_simple", text="Simple Shape", icon='MESH_UVSPHERE')
            col.operator("pawrappa.auto_uv_thingamabob", text="Thingamabob", icon='OUTLINER_DATA_MESH')

        # --- Status ---
        layout.separator()
        mesh = obj.data
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
                box.label(text=f"Seams: {seam_count} edges (ready to unwrap)")
            else:
                box.label(text="Click Auto Seams above!")

        # Mesh info
        layout.separator()
        col = layout.column(align=True)
        col.label(text=f"Verts: {len(mesh.vertices):,}  |  Faces: {len(mesh.polygons):,}")
