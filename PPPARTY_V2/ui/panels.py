"""PPParty V2 — N-panel UI.

Two-pass UI (refactored 2026-04-29):
    Pass 1 — Body Mirror + Body Recording
        Captures full body, arms, AND hands together. The "wave at
        the screen, puppet waves back" demo.
    Pass 2 — Face Mirror + Face Recording
        Captures head rotation over the baked Pass-1 strip.

Face Mirror is gated on Pass 1 being baked (PP_V2_BodyPass NLA strip
must exist on the rig).
"""

import bpy

from ..core.receiver import get_receiver, get_face_receiver
from ..core.recorder import get_recorder, get_face_recorder
from ..operators._nla import body_pass_baked


class PPPARTY_V2_PT_main(bpy.types.Panel):
    """Main N-panel for PPParty V2."""

    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "PPPARTY V2"
    bl_label = "PPParty V2"

    def draw(self, context):
        layout = self.layout
        receiver = get_receiver()
        recorder = get_recorder()
        face_receiver = get_face_receiver()
        face_recorder = get_face_recorder()
        body_baked = body_pass_baked()

        # --- Rig section ---
        col = layout.column(align=True)
        col.label(text="Rig", icon='ARMATURE_DATA')
        col.operator("ppparty_v2.create_rig", icon='OUTLINER_OB_ARMATURE')

        layout.separator()

        # --- Pass 1: Body Mirror section ---
        col = layout.column(align=True)
        col.label(text="Body Mirror (Pass 1)", icon='OUTLINER_OB_ARMATURE')
        if receiver.running:
            col.operator(
                "ppparty_v2.stop_body_mirror",
                icon='PAUSE',
                text="Stop Body Mirror",
            )
            col.label(text="Status: live", icon='REC')
        else:
            col.operator(
                "ppparty_v2.start_body_mirror",
                icon='PLAY',
                text="Start Body Mirror",
            )
            col.label(text="Status: idle", icon='RADIOBUT_OFF')

        layout.separator()

        # --- Pass 1: Body Recording section ---
        col = layout.column(align=True)
        col.label(text="Body Recording (Pass 1)", icon='RENDER_ANIMATION')
        if recorder.is_recording:
            col.operator(
                "ppparty_v2.stop_body_recording",
                icon='SNAP_FACE',
                text="Stop Recording",
            )
            col.label(
                text=f"Recording: {recorder.frame_count} frames",
                icon='REC',
            )
        elif receiver.running:
            col.operator(
                "ppparty_v2.start_body_recording",
                icon='RADIOBUT_ON',
                text="Start Recording",
            )
            col.label(text="Mirror live — ready to record",
                      icon='RADIOBUT_OFF')
        else:
            row = col.row()
            row.enabled = False
            row.operator(
                "ppparty_v2.start_body_recording",
                icon='RADIOBUT_ON',
                text="Start Recording",
            )
            col.label(text="Start body mirror first",
                      icon='INFO')

        layout.separator()

        # --- Pass 2: Face Mirror section ---
        col = layout.column(align=True)
        col.label(text="Face Mirror (Pass 2)", icon='HIDE_OFF')

        if not body_baked:
            col.label(text="Record body pass first", icon='INFO')
            row = col.row()
            row.enabled = False
            row.operator(
                "ppparty_v2.start_face_mirror",
                icon='PLAY',
                text="Start Face Mirror",
            )
        elif face_receiver.running:
            col.operator(
                "ppparty_v2.stop_face_mirror",
                icon='PAUSE',
                text="Stop Face Mirror",
            )
            col.label(text="Status: live", icon='REC')
        else:
            col.operator(
                "ppparty_v2.start_face_mirror",
                icon='PLAY',
                text="Start Face Mirror",
            )
            col.label(text="Status: idle", icon='RADIOBUT_OFF')

        layout.separator()

        # --- Pass 2: Face Recording section ---
        col = layout.column(align=True)
        col.label(text="Face Recording (Pass 2)", icon='RENDER_ANIMATION')

        if face_recorder.is_recording:
            col.operator(
                "ppparty_v2.stop_face_recording",
                icon='SNAP_FACE',
                text="Stop Recording",
            )
            col.label(
                text=f"Recording: {face_recorder.frame_count} frames",
                icon='REC',
            )
        elif face_receiver.running:
            col.operator(
                "ppparty_v2.start_face_recording",
                icon='RADIOBUT_ON',
                text="Start Recording",
            )
            col.label(text="Face mirror live — ready to record",
                      icon='RADIOBUT_OFF')
        else:
            row = col.row()
            row.enabled = False
            row.operator(
                "ppparty_v2.start_face_recording",
                icon='RADIOBUT_ON',
                text="Start Recording",
            )
            col.label(text="Start face mirror first",
                      icon='INFO')
