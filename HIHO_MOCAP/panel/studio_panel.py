"""HIHO MOCAP Studio Panel — the tools that are not ready for a student build yet.

Shown ONLY when "Studio tools" is ticked at the bottom of the main panel
(PANEL_REDESIGN_DESIGN_2026-09-19, section 9). These tools are not gone: they
need more design and testing before a public build. Off by default, remembered
per computer.

What lives here: Choose Take, Preview, the Character pipeline, and the
diagnostics (Map the Volume, Spawn Empties). What LEFT in 1.5.3: Bake + Export
is step 6 of the main panel now, and Lock Feet has its own checkbox as the
first tenant of Cleanup, so nothing is drawn twice.

Section labels per HIHO_MOCAP_WRAPPER_ARCHITECTURE.md section 8, decision 1.
Plain language only.
"""

import os

import bpy

from ..operators import norm_path


def _prefs(context):
    addon = context.preferences.addons.get(__package__.rsplit(".", 1)[0])
    return addon.preferences if addon is not None else None


class HIHO_MOCAP_PT_studio(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "HIHO MOCAP"
    bl_label = "Studio"
    bl_order = 1

    @classmethod
    def poll(cls, context):
        prefs = _prefs(context)
        return bool(prefs is not None and prefs.show_studio_tools)

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

        # DIAGNOSTICS — moved here from the main panel in 1.5.3: they inspect a
        # capture, they are not a step of making one.
        layout.separator()
        layout.label(text="Diagnostics", icon='VIEWZOOM')
        layout.operator("hiho_mocap.volume_map", icon='SHADING_RENDERED',
                        text="Map the Volume")
        if s.volume_verdict:
            box = layout.box()
            box.label(text=s.volume_verdict, icon='WORLD')
            map_path = norm_path(s.volume_map_path)
            if map_path and os.path.isfile(map_path):
                op = box.operator("wm.path_open", icon='IMAGE_DATA', text="Open Map")
                op.filepath = map_path
        layout.operator("hiho_mocap.spawn_output_rig", icon='EMPTY_AXIS',
                        text="Spawn Empties (debug)")
