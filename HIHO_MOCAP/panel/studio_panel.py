"""HIHO MOCAP Studio Panel — the artist-facing UI.

Section labels and order per HIHO_MOCAP_WRAPPER_ARCHITECTURE.md section 8,
decision 1: Choose Take, Preview, Send to Character, Polish, Save Out.
Plain language only. Glossary in the architecture doc maps these to the
technical terms used in code.

Amendment 1.4.40 (blessed 2026-08-05, see STATUS.md "UI PRUNE/ADD QUEUE"):
the Polish section is hidden until per-region smoothing ships for real
(Track 3) — its three buttons were stubs and two had gone stale. Visible
sections renumber 1-4. No other stub buttons remain in the student view.
"""

import bpy


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

        # 2. PREVIEW
        layout.separator()
        layout.label(text="2. Preview", icon='HIDE_OFF')
        layout.operator("screen.animation_play", text="Play", icon='PLAY')

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

        # 4. POLISH — section hidden 1.4.40: all three buttons were stubs, and
        # two went stale (wrist flips now self-repair inside Bake; per-region
        # smoothing replaced the One Euro idea). Returns when Track 3 ships.

        # 5. EXPORT
        layout.separator()
        layout.label(text="4. Export", icon='EXPORT')
        layout.operator("hiho_mocap.bake_animation", icon='ACTION')
        layout.prop(s, "export_format", expand=True)
        layout.operator("hiho_mocap.save_out", icon='FILE_TICK')
