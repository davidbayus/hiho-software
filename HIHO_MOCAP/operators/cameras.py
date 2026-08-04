# RETIRED (2026-06-09): not registered, not imported by the addon. The live
# capture path is operators/external_capture.py + external/record_take.py;
# processing is core/external_runner.py + external/. Kept on disk per the
# never-delete policy; excluded from shipped zips. Do not re-wire without
# reading AUDIT_2026-06-09.md (finding L1) — this code predates the headless
# pivot and bypasses the per-camera rotation system.
"""Start / stop the 4-camera live preview, plus the camera-grid window opener."""

import bpy

from ..core.camera_manager import CameraManager
from ..core.blender_preview import BlenderCameraPreview, IMAGE_NAME_FMT
from . import STATE


# Hardcoded for v1.0. Per v1 plan, camera detection / selection UI is parked
# for v1.1+. USB enumeration isn't stable across reboots — if the wrong cameras
# open, run this in Blender's Python console to see what's available:
#     from HIHO_MOCAP.core.camera_manager import CameraManager
#     print(CameraManager.detect_cameras())
# Then edit this list to the four C922 indices (exclude the MacBook webcam).
DEFAULT_CAMERA_IDS = [0, 1, 2, 3]


def _redraw_ui(context):
    for area in context.screen.areas:
        if area.type == 'VIEW_3D':
            area.tag_redraw()


class HIHO_MOCAP_OT_start_cameras(bpy.types.Operator):
    """Open the cameras and start the live preview."""
    bl_idname = "hiho_mocap.start_cameras"
    bl_label = "Cameras Up"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return STATE["manager"] is None

    def execute(self, context):
        mgr = CameraManager(DEFAULT_CAMERA_IDS)
        results = mgr.start()

        failed = [cid for cid, ok in results.items() if not ok]
        if failed:
            mgr.stop()
            self.report(
                {'ERROR'},
                f"Camera(s) failed to open: {failed}. "
                f"If your built-in webcam is at index 0, edit DEFAULT_CAMERA_IDS in operators/cameras.py.",
            )
            return {'CANCELLED'}

        preview = BlenderCameraPreview(mgr)
        preview.start()

        STATE["manager"] = mgr
        STATE["preview"] = preview

        _redraw_ui(context)
        self.report({'INFO'}, f"Cameras up: {list(results.keys())}")
        return {'FINISHED'}


class HIHO_MOCAP_OT_stop_cameras(bpy.types.Operator):
    """Stop the live preview and release the cameras."""
    bl_idname = "hiho_mocap.stop_cameras"
    bl_label = "Cameras Down"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return STATE["manager"] is not None

    def execute(self, context):
        if STATE["preview"] is not None:
            STATE["preview"].stop()
            STATE["preview"] = None
        if STATE["manager"] is not None:
            STATE["manager"].stop()
            STATE["manager"] = None

        _redraw_ui(context)
        self.report({'INFO'}, "Cameras released")
        return {'FINISHED'}


class HIHO_MOCAP_OT_open_camera_views(bpy.types.Operator):
    """Open a new window with a 2x2 grid of Image Editors showing each camera live."""
    bl_idname = "hiho_mocap.open_camera_views"
    bl_label = "Open Camera Views"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return STATE["manager"] is not None

    def execute(self, context):
        cam_ids = STATE["manager"].camera_ids
        if not cam_ids:
            self.report({'ERROR'}, "No cameras live.")
            return {'CANCELLED'}

        # Spawn a new top-level window. Blender clones the current screen into it.
        bpy.ops.wm.window_new()
        new_window = context.window_manager.windows[-1]
        screen = new_window.screen

        self.report({'INFO'}, f"[HIHO] new window: {len(screen.areas)} areas")

        def biggest_view3d():
            v3ds = [a for a in screen.areas if a.type == 'VIEW_3D']
            return max(v3ds, key=lambda a: a.width * a.height, default=None)

        def split_biggest(direction, label):
            """Split the biggest VIEW_3D area in the new window.

            Always picks the largest unsplit area so we never re-target one that
            was just split (the failure mode from step2c/d). Cursor-warps inside
            it first — area_split is sometimes cursor-position-dependent.
            """
            area = biggest_view3d()
            if area is None:
                self.report({'WARNING'}, f"[HIHO] {label}: no VIEW_3D left")
                return False
            ptrs_before = {a.as_pointer() for a in screen.areas}
            # Cursor warp inside the target — area_split looks at cursor in some builds
            cx = area.x + area.width // 2
            cy = area.y + area.height // 2
            new_window.cursor_warp(cx, cy)
            region = next((r for r in area.regions if r.type == 'WINDOW'), None)
            override = {"window": new_window, "screen": screen, "area": area}
            if region is not None:
                override["region"] = region
            try:
                with context.temp_override(**override):
                    bpy.ops.screen.area_split(direction=direction, factor=0.5)
            except Exception as exc:
                self.report({'ERROR'}, f"[HIHO] {label}: raised {exc!r}")
                return False
            new_areas = [a for a in screen.areas if a.as_pointer() not in ptrs_before]
            ok = len(new_areas) == 1
            self.report(
                {'INFO' if ok else 'WARNING'},
                f"[HIHO] {label}: now {len(screen.areas)} areas (new={len(new_areas)})",
            )
            return ok

        # 3 splits → 2x2. Vertical first (left | right), then horizontal on
        # whichever column is the biggest unsplit VIEW_3D each time.
        split_biggest('VERTICAL', "split 1 vert")
        split_biggest('HORIZONTAL', "split 2 horiz")
        split_biggest('HORIZONTAL', "split 3 horiz")

        # Collect every VIEW_3D in the new window — these are our final cells.
        cells = [a for a in screen.areas if a.type == 'VIEW_3D']
        self.report({'INFO'}, f"[HIHO] collected {len(cells)} VIEW_3D cells")

        assigned = 0
        for area, cam_id in zip(cells, cam_ids):
            area.type = 'IMAGE_EDITOR'
            space = next((s for s in area.spaces if s.type == 'IMAGE_EDITOR'), None)
            if space is None:
                continue
            img = bpy.data.images.get(IMAGE_NAME_FMT.format(cam_id=cam_id))
            if img is not None:
                space.image = img
                assigned += 1

        self.report({'INFO'}, f"Opened camera grid: {assigned} views assigned.")
        return {'FINISHED'}
