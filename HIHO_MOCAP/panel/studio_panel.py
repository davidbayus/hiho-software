"""HIHO MOCAP Studio Panel — the artist-facing 5-section UI.

Section labels and order are locked per HIHO_MOCAP_WRAPPER_ARCHITECTURE.md
section 8, decision 1: Choose Take, Preview, Send to Character, Polish,
Save Out. Plain language only. Glossary in the architecture doc maps these
to the technical terms used in code.

This is the v1.2 skeleton: layout + property wiring is real, but every
operator points to HIHO_MOCAP_OT_studio_stub. Real operators land in
tasks #4 through #6 (Bake Take, Polish, Save Out).
"""

import bpy


class HIHO_MOCAP_OT_studio_stub(bpy.types.Operator):
    """Stub for v1.2 Studio Panel buttons. Reports the feature name and exits.

    Once tasks #4 through #6 ship, the panel rebinds each button to a real
    operator and this stub goes away.
    """

    bl_idname = "hiho_mocap.studio_stub"
    bl_label = "HIHO MOCAP Studio (stub)"
    bl_description = "Placeholder; not yet implemented"

    feature: bpy.props.StringProperty()

    def execute(self, context):
        self.report({'INFO'}, f"Coming soon: {self.feature}")
        return {'FINISHED'}


class HIHO_MOCAP_PT_studio(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "HIHO MOCAP"
    bl_label = "Studio"
    bl_order = 0

    def draw(self, context):
        layout = self.layout
        s = context.scene.hiho_mocap

        # 1. CHOOSE TAKE
        layout.label(text="1. Choose Take", icon='FILE_FOLDER')
        col = layout.column(align=True)
        col.operator("hiho_mocap.load_take", icon='FILE_FOLDER')
        col.prop(s, "last_processed_path", text="")
        op = col.operator("hiho_mocap.studio_stub", text="Pick from library...", icon='ASSET_MANAGER')
        op.feature = "Pick from library (v2.0)"

        # 2. PREVIEW
        layout.separator()
        layout.label(text="2. Preview", icon='HIDE_OFF')
        op = layout.operator("hiho_mocap.studio_stub", text="Play", icon='PLAY')
        op.feature = "Preview (empties-only load)"

        # 3. CHARACTER
        layout.separator()
        layout.label(text="3. Character", icon='ARMATURE_DATA')
        col = layout.column(align=True)
        col.operator("hiho_mocap.import_character", icon='IMPORT')
        col.operator("hiho_mocap.add_markers", icon='OUTLINER_OB_EMPTY')
        row = col.row(align=True)
        row.label(text="Mirror:")
        row.prop(s, "marker_mirror_axis", expand=True)
        row = col.row(align=True)
        op = row.operator("hiho_mocap.mirror_markers", text="Left → Right")
        op.direction = 'L2R'
        op = row.operator("hiho_mocap.mirror_markers", text="Right → Left")
        op.direction = 'R2L'
        row = col.row(align=True)
        row.label(text="Skinning:")
        row.prop(s, "skinning_mode", expand=True)
        col.operator("hiho_mocap.auto_rig", icon='ARMATURE_DATA')
        layout.prop(s, "character_target", text="")
        layout.operator("hiho_mocap.send_to_character", icon='EXPORT')

        # 4. POLISH
        layout.separator()
        layout.label(text="4. Polish", icon='MODIFIER')
        col = layout.column(align=True)
        op = col.operator("hiho_mocap.studio_stub", text="Smooth hands", icon='SMOOTHCURVE')
        op.feature = "Smooth hands (One Euro)"
        op = col.operator("hiho_mocap.studio_stub", text="Fix wrist flips", icon='CONSTRAINT')
        op.feature = "Fix wrist flips (LIMIT_ROTATION)"
        op = col.operator("hiho_mocap.studio_stub", text="Trim frames", icon='ARROW_LEFTRIGHT')
        op.feature = "Trim frames (scene range)"

        # 5. EXPORT
        layout.separator()
        layout.label(text="5. Export", icon='EXPORT')
        layout.operator("hiho_mocap.bake_animation", icon='ACTION')
        layout.prop(s, "export_format", expand=True)
        layout.operator("hiho_mocap.save_out", icon='FILE_TICK')

        # Science Mode toggle
        layout.separator()
        layout.prop(s, "show_science_mode", icon='LIGHT_DATA', text="Show Science Mode")
