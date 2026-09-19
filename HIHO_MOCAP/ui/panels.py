"""HIHO MOCAP N-panel — the steps a student follows, in the order of a session.

1. Cameras, 2. Calibrate, 3. Record, 4. Process, 5. Rig, then Face.
Order and names follow the work (David, 2026-08-07: capture and calibration
are step one of every session, never an "advanced" view). Design:
PANEL_REDESIGN_DESIGN_2026-09-19.md.

Nothing here needs live cameras to draw: Process and Rig work on disk paths,
so a student processing yesterday's take never has to bring cameras up first.
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


def _wrap(text: str, width: int = 40, max_rows: int = 4) -> list:
    """Break the status line into panel-width rows. A Blender label never
    wraps, so a long message (an error most of all) used to run off the edge
    exactly when it mattered."""
    rows, line = [], ""
    for word in " ".join(text.split()).split(" "):
        if line and len(line) + 1 + len(word) > width:
            rows.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    if line:
        rows.append(line)
    if len(rows) > max_rows:
        rows = rows[:max_rows]
        rows[-1] = rows[-1][:width - 3].rstrip() + "..."
    return rows


def _rows(text: str, width: int = 38) -> list:
    """A badge line as panel rows: split into sentences first, so a row break
    lands where a reader would pause, then wrap what is still too long."""
    rows = []
    for sentence in text.replace(". ", ".\n").split("\n"):
        rows.extend(_wrap(sentence, width=width, max_rows=3))
    return rows[:5]


class HIHO_MOCAP_PT_main(bpy.types.Panel):
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "HIHO MOCAP"
    bl_label = "HIHO MOCAP"

    def draw(self, context):
        layout = self.layout
        scene_settings = context.scene.hiho_mocap
        # The set-once computer paths (Save to, the two tracker envs) are NOT
        # drawn here any more: they live in Edit > Preferences > Add-ons >
        # HIHO MOCAP, so the panel holds only the steps of a session.
        addon = context.preferences.addons.get(__package__.rsplit(".", 1)[0])
        prefs = addon.preferences if addon is not None else None

        # One status line, always in the same place, whichever step is talking.
        # It used to sit under Record even when the news was about processing.
        status = STATE.get("status_text", "")
        if status:
            box = layout.box()
            col = box.column(align=True)
            col.alert = "fail" in status.lower() or "not installed" in status
            for i, line in enumerate(_wrap(status)):
                col.label(text=line, icon='INFO' if i == 0 else 'BLANK1')

        # --- 1. Cameras ------------------------------------------------------
        layout.label(text="1. Cameras", icon='OUTLINER_OB_CAMERA')
        layout.operator("hiho_mocap.preview_cameras", icon='OUTLINER_OB_CAMERA', text="Show Cameras")
        layout.prop(scene_settings, "camera_ids")

        # --- 2. Calibrate (start of every session) ---------------------------
        layout.separator()
        layout.label(text="2. Calibrate", icon='MESH_GRID')
        col = layout.column(align=True)
        col.prop(scene_settings, "countdown_seconds")
        col.prop(scene_settings, "calibration_length_seconds")
        # A grid, never the record dot: the panel has exactly ONE record dot,
        # and it belongs to the performance.
        layout.operator("hiho_mocap.record_calibration", icon='MESH_GRID',
                        text="Record Calibration")
        row = layout.row(align=True)
        row.operator("hiho_mocap.solve_calibration", icon='CAMERA_DATA', text="Solve")
        row.operator("hiho_mocap.check_calibration", icon='SEQ_HISTOGRAM', text="Check")
        layout.prop(scene_settings, "calibration_take_path", text="Board take")
        layout.prop(scene_settings, "charuco_square_mm", text="Square size (mm)")
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

        # --- 3. Record -------------------------------------------------------
        layout.separator()
        layout.label(text="3. Record", icon='REC')
        col = layout.column(align=True)
        # The same Countdown as step 2 (time to walk to your spot): one number.
        col.prop(scene_settings, "countdown_seconds")
        col.prop(scene_settings, "record_length_seconds")
        row = layout.row(align=True)
        row.operator("hiho_mocap.record_external", icon='REC', text="Record Mocap")
        row.operator("hiho_mocap.stop_capture", icon='X', text="")

        # --- 4. Process (works on disk paths) --------------------------------
        layout.separator()
        layout.label(text="4. Process", icon='PLAY')
        layout.prop(scene_settings, "last_take_path", text="Take")
        layout.prop(scene_settings, "calibration_toml_path", text="Calib")
        # Always visible, so which tracker is about to run is never a surprise.
        layout.prop(scene_settings, "tracker", text="Tracker")
        row = layout.row(align=True)
        row.operator("hiho_mocap.process_mocap", icon='PLAY', text="Process Mocap")
        row.operator("hiho_mocap.cancel_process", icon='X', text="")
        quality = scene_settings.process_verdict
        if quality:
            # "not measured" = the RTMPose path, which has no quality number
            # yet: a neutral icon, never the error one on a good run.
            icon = 'CHECKMARK' if "GOOD" in quality else (
                'INFO' if ("CHECK" in quality or "not measured" in quality) else 'ERROR')
            take = _badge_take(scene_settings.process_badge_take)
            made_by = scene_settings.process_badge_tracker
            box = layout.box()
            if made_by or take:
                head = box.row()
                head.scale_y = 0.8
                head.label(text=" - ".join(part for part in (made_by, take) if part))
            # One sentence per row, wrapped to the panel: a Blender label never
            # wraps, and every one of these lines used to run off the edge.
            col = box.column(align=True)
            col.alert = "BAD" in quality
            for i, line in enumerate(_rows(quality)):
                col.label(text=line, icon=icon if i == 0 else 'BLANK1')

        # --- 5. Rig (works on disk paths) ------------------------------------
        layout.separator()
        layout.label(text="5. Rig", icon='ARMATURE_DATA')
        layout.prop(scene_settings, "last_processed_path", text="Processed")
        layout.operator("hiho_mocap.spawn_rig", icon='ARMATURE_DATA', text="Spawn Rig")
        layout.operator("hiho_mocap.add_camera_videos", icon='IMAGE_DATA',
                        text="Add Camera Videos")

        # --- Cleanup (opt-in; Lock Feet is its first tenant) ------------------
        # Only when its checkbox at the bottom is ticked. It edits the tracking
        # empties, so it has to sit BEFORE Bake. One slot, two states
        # (UNLOCK_TOGGLE_DESIGN_2026-08-12): while the current take is locked
        # the slot shows Unlock, for before/after comparison.
        if prefs is not None and prefs.show_lock_feet:
            layout.separator()
            layout.label(text="Cleanup (optional)", icon='BRUSH_DATA')
            stash = STATE.get("lock_feet_stash")
            locked_here = False
            if stash and stash["locked"] and scene_settings.last_processed_path:
                folder = os.path.basename(os.path.dirname(os.path.dirname(
                    norm_path(scene_settings.last_processed_path))))
                locked_here = stash["take"] == f"HIHO_MOCAP_Skelly_{folder}"
            if locked_here:
                layout.operator("hiho_mocap.unlock_feet", icon='SNAP_OFF')
            else:
                layout.operator("hiho_mocap.lock_feet", icon='SNAP_ON')

        # --- 6. Bake + Export (moved up from the Studio panel) -----------------
        # Both work on the selected rig, and Spawn Rig selects the rig it just
        # built, so Bake is live the moment step 5 finishes.
        layout.separator()
        layout.label(text="6. Bake + Export", icon='EXPORT')
        layout.operator("hiho_mocap.bake_animation", icon='ACTION')
        layout.prop(scene_settings, "export_format", expand=True)
        layout.operator("hiho_mocap.save_out", icon='FILE_TICK')

        # --- Face Sync: last, and folded shut by default ----------------------
        # (The face workflow is still being learned, so it stays out of the way.)
        layout.separator()
        header, face = layout.panel("HIHO_MOCAP_face_sync", default_closed=True)
        header.label(text="Face Sync", icon='USER')
        if face is not None:
            face.operator("hiho_mocap.spawn_test_face", icon='USER',
                            text="Spawn Test Face")
            face.prop(scene_settings, "face_take_csv", text="Face take")
            face.operator("hiho_mocap.load_face_take", icon='IMPORT',
                            text="Load Face Take")
            col = face.column()
            col.scale_y = 0.7
            col.label(text="Pick the take's _cal.csv (AirDropped from the phone)")
            face.operator("hiho_mocap.add_face_video", icon='IMAGE_DATA',
                            text="Add Face Video")
            row = face.row(align=True)
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
                col = face.column()
                col.scale_y = 0.7
                col.label(text="Flash marked: " + ", ".join(marks))
            face.operator("hiho_mocap.line_up_face", icon='SORTTIME',
                            text="Line Up Face")
            if scene_settings.face_applied_offset:
                box = face.box()
                box.label(text=f"Face lined up: moved "
                               f"{scene_settings.face_applied_offset:+.0f} frames",
                          icon='CHECKMARK')

        # --- Opt-in extras, remembered per computer ---------------------------
        # Never the steps of a session: only unfinished tools ADDED on top.
        if prefs is not None:
            layout.separator()
            layout.prop(prefs, "show_lock_feet")
            layout.prop(prefs, "show_studio_tools")
