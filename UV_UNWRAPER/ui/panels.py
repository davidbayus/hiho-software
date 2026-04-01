"""
UI Panels — Where the buttons live in Blender.

Three big buttons in the sidebar:
1. Character — for people and bipeds
2. Simple Shape — for props and accessories
3. Thingamabob — for creatures and weird shapes

Shows up in the 3D Viewport sidebar (press N to open) under "K-12 Tools."
"""

import bpy


class KIDBLENDER_PT_uv_panel(bpy.types.Panel):
    """Panel in the 3D Viewport sidebar for UV tools."""

    bl_label = "Auto UV Unwrap"
    bl_idname = "KIDBLENDER_PT_uv_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "K-12 Tools"

    def draw(self, context):
        layout = self.layout
        obj = context.active_object

        if obj is None or obj.type != 'MESH':
            layout.label(text="Select a mesh to unwrap", icon='INFO')
            return

        # Header
        layout.label(text="What kind of shape is this?")

        # --- Button 1: Character ---
        box = layout.box()
        col = box.column(align=True)
        col.label(text="People, bipeds, symmetric characters", icon='ARMATURE_DATA')
        row = col.row(align=True)
        row.scale_y = 1.8
        row.operator(
            "kidblender.auto_uv",
            text="Character",
            icon='MOD_ARMATURE',
        )

        # --- Button 2: Simple Shape ---
        box = layout.box()
        col = box.column(align=True)
        col.label(text="Props, weapons, potions, hats, rocks", icon='MESH_CUBE')
        row = col.row(align=True)
        row.scale_y = 1.8
        row.operator(
            "kidblender.auto_uv_simple",
            text="Simple Shape",
            icon='MESH_UVSPHERE',
        )

        # --- Button 3: Thingamabob ---
        box = layout.box()
        col = box.column(align=True)
        col.label(text="Creatures, monsters, anything weird", icon='GHOST_ENABLED')
        row = col.row(align=True)
        row.scale_y = 1.8
        row.operator(
            "kidblender.auto_uv_thingamabob",
            text="Thingamabob",
            icon='OUTLINER_DATA_MESH',
        )

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
            box.label(text="Pick a shape type above!")

        # Mesh info
        layout.separator()
        col = layout.column(align=True)
        col.label(text=f"Vertices: {len(mesh.vertices):,}")
        col.label(text=f"Faces: {len(mesh.polygons):,}")
