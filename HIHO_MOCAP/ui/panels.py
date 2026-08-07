"""HIHO MOCAP N-panel — the only UI the student sees.

Sections always visible:
- Cameras
- Process (works on disk paths — doesn't need cameras live)
- Output (works on disk paths)

Sections gated by cameras live (need a CameraManager + frames coming in):
- Live indicator + Open Camera Views
- Record

This split exists because Process and Output are pure post-capture work —
a student processing yesterday's take or rebuilding a rig shouldn't need
to bring cameras up first.
"""

import os

import bpy

from ..operators import STATE, norm_path


def _badge_take(name: str) -> str:
    """Compact display form of a take folder name: drop the year prefix
    (2026-07-17_13-17-18 → 07-17_13-17-18)."""
    if len(name) > 5 and name[:4].isdigit() and name[4] == "-":
        return name[5:]
    return name


def _board_take_unsolved(take_path: str) -> bool:
    """True when the Board take field names a real folder that has no
    calibration toml in it yet. A solve writes
    <take>_camera_calibration.toml into the take folder — its absence is
    the on-disk truth that Solve hasn't run. This check is the stale-badge
    trap-killer (STALE_BADGE_DESIGN_2026-07-18)."""
    folder = norm_path(take_path)
    if not folder or not os.path.isdir(folder):
        return False
    take = os.path.basename(os.path.normpath(folder))
    return not os.path.isfile(os.path.join(folder, f"{take}_camera_calibration.toml"))


class HIHO_MOCAP_PT_main(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "HIHO MOCAP"
    bl_label = "HIHO MOCAP"

    def draw(self, context):
        layout = self.layout
        scene_settings = context.scene.hiho_mocap
        # Machine-level settings — drawn from AddonPreferences so they survive
        # new files and restarts (scene props reset per file; audit M18).
        addon = context.preferences.addons.get(__package__.rsplit(".", 1)[0])

        # --- Capture (launches your FreeMoCap env in a separate window) ----
        layout.label(text="Capture")
        layout.operator("hiho_mocap.preview_cameras", icon='OUTLINER_OB_CAMERA', text="Show Cameras")
        hint = layout.column(align=True)
        hint.scale_y = 0.7
        hint.label(text="Right-click a camera there to include/exclude it,")
        hint.label(text="left-click to rotate. Picks fill the list below.")
        col = layout.column(align=True)
        col.prop(scene_settings, "camera_ids")
        col.prop(scene_settings, "countdown_seconds")
        col.prop(scene_settings, "record_length_seconds")
        if addon is not None and addon.preferences is not None:
            layout.prop(addon.preferences, "data_home", text="Save to")
        row = layout.row(align=True)
        row.operator("hiho_mocap.record_external", icon='RADIOBUT_ON', text="Record")
        row.operator("hiho_mocap.stop_capture", icon='X', text="")

        status = STATE.get("status_text", "")
        if status:
            layout.label(text=status)

        # --- Calibrate -----------------------------------------------------
        layout.separator()
        layout.label(text="Calibrate")
        layout.prop(scene_settings, "calibration_take_path", text="Board take")
        layout.prop(scene_settings, "charuco_square_mm", text="Square size (mm)")
        row = layout.row(align=True)
        row.operator("hiho_mocap.record_calibration", icon='RADIOBUT_ON',
                     text="Record Calibration")
        row.operator("hiho_mocap.solve_calibration", icon='CAMERA_DATA', text="Solve")
        layout.operator("hiho_mocap.check_calibration", icon='SEQ_HISTOGRAM',
                        text="Check Calibration")
        verdict = scene_settings.calibration_verdict
        if verdict:
            px = scene_settings.calibration_quality_px
            icon = {
                'excellent': 'CHECKMARK', 'good': 'CHECKMARK',
                'workable': 'INFO', 'recalibrate': 'ERROR',
            }.get(verdict, 'INFO')
            take = _badge_take(scene_settings.calibration_badge_take)
            suffix = f" - {take}" if take else ""
            box = layout.box()
            row = box.row()
            row.alert = (verdict == 'recalibrate')
            row.label(text=f"Quality: {verdict.capitalize()} ({px:.2f} px){suffix}",
                      icon=icon)
        floor = scene_settings.groundplane_status
        if floor:
            floor_ok = floor.startswith("OK")
            take = _badge_take(scene_settings.groundplane_badge_take)
            suffix = f" - {take}" if take else ""
            box = layout.box()
            row = box.row()
            row.alert = not floor_ok
            row.label(text=f"Floor: OK (set from board){suffix}" if floor_ok
                      else f"Floor: FAILED - re-record calibration{suffix}",
                      icon='CHECKMARK' if floor_ok else 'ERROR')
        if _board_take_unsolved(scene_settings.calibration_take_path):
            box = layout.box()
            row = box.row()
            row.alert = True
            row.label(text="Board take not solved yet - click Solve", icon='ERROR')

        # --- Process (always visible — works on disk paths) ----------------
        layout.separator()
        layout.label(text="Process")
        layout.prop(scene_settings, "last_take_path", text="Take")
        layout.prop(scene_settings, "calibration_toml_path", text="Calib")
        if addon is not None and addon.preferences is not None:
            layout.prop(addon.preferences, "freemocap_env_python", text="FreeMoCap")
        col = layout.column()
        col.scale_y = 0.7
        col.label(text="Calib blank = use last_successful_calibration.toml")
        row = layout.row(align=True)
        row.operator("hiho_mocap.process_mocap", icon='PLAY', text="Process Mocap")
        row.operator("hiho_mocap.cancel_process", icon='X', text="")
        quality = scene_settings.process_verdict
        if quality:
            icon = 'CHECKMARK' if "GOOD" in quality else (
                'INFO' if "CHECK" in quality else 'ERROR')
            take = _badge_take(scene_settings.process_badge_take)
            suffix = f" - {take}" if take else ""
            box = layout.box()
            row = box.row()
            row.alert = "BAD" in quality
            row.label(text=f"{quality}{suffix}", icon=icon)
        layout.operator("hiho_mocap.volume_map", icon='SHADING_RENDERED',
                        text="Map the Volume")
        if scene_settings.volume_verdict:
            box = layout.box()
            box.label(text=scene_settings.volume_verdict, icon='WORLD')
            map_path = norm_path(scene_settings.volume_map_path)
            if map_path and os.path.isfile(map_path):
                op = box.operator("wm.path_open", icon='IMAGE_DATA', text="Open Map")
                op.filepath = map_path

        # --- Output (always visible) ---------------------------------------
        layout.separator()
        layout.label(text="Output")
        layout.prop(scene_settings, "last_processed_path", text="Processed")
        layout.operator("hiho_mocap.spawn_rig", icon='ARMATURE_DATA', text="Spawn Rig")
        layout.operator("hiho_mocap.add_camera_videos", icon='IMAGE_DATA',
                        text="Add Camera Videos")
        col = layout.column()
        col.scale_y = 0.7
        col.label(text="Empties only (debug):")
        layout.operator("hiho_mocap.spawn_output_rig", icon='EMPTY_AXIS', text="Spawn Empties")

        # --- Face (iPhone / Live Link Face interim path) -------------------
        layout.separator()
        layout.label(text="Face")
        layout.operator("hiho_mocap.spawn_test_face", icon='USER',
                        text="Spawn Test Face")
        layout.prop(scene_settings, "face_take_csv", text="Face take")
        layout.operator("hiho_mocap.load_face_take", icon='IMPORT',
                        text="Load Face Take")
        col = layout.column()
        col.scale_y = 0.7
        col.label(text="Pick the take's _cal.csv (AirDropped from the phone)")
        layout.operator("hiho_mocap.add_face_video", icon='IMAGE_DATA',
                        text="Add Face Video")
        row = layout.row(align=True)
        row.operator("hiho_mocap.mark_flash_body", icon='MARKER',
                     text="Flash (Body)")
        row.operator("hiho_mocap.mark_flash_face", icon='MARKER_HLT',
                     text="Flash (Face)")
        marks = []
        if scene_settings.flash_body_frame >= 0.0:
            marks.append(f"body {scene_settings.flash_body_frame:.0f}")
        if scene_settings.flash_face_frame >= 0.0:
            marks.append(f"face {scene_settings.flash_face_frame:.0f}")
        if marks:
            col = layout.column()
            col.scale_y = 0.7
            col.label(text="Flash marked: " + ", ".join(marks))
        layout.operator("hiho_mocap.line_up_face", icon='SORTTIME',
                        text="Line Up Face")
        if scene_settings.face_applied_offset:
            box = layout.box()
            box.label(text=f"Face lined up: moved "
                           f"{scene_settings.face_applied_offset:+.0f} frames",
                      icon='CHECKMARK')
