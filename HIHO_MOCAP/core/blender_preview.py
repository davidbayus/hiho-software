# RETIRED (2026-06-09): not registered, not imported by the addon. The live
# capture path is operators/external_capture.py + external/record_take.py;
# processing is core/external_runner.py + external/. Kept on disk per the
# never-delete policy; excluded from shipped zips. Do not re-wire without
# reading AUDIT_2026-06-09.md (finding L1) — this code predates the headless
# pivot and bypasses the per-camera rotation system.
"""
HIHO MOCAP Blender Preview — bridges CameraManager frames into Blender Images.

A Blender timer (~10 Hz) pulls the latest frame from each camera, downscales,
converts BGR→RGBA float, and writes into bpy.data.images["HIHO_MOCAP_Cam_N"].
The N-panel reads from these datablocks.

CameraManager's capture threads are pure OpenCV — they never touch bpy. This
module is the only place Blender's API is called for camera frames. Blender's
Python API isn't thread-safe; running bpy.* on the timer callback (main thread)
keeps that contract.

See ../CAMERA_MANAGER_DESIGN.md for the full design rationale.
"""

import bpy
import cv2
import numpy as np


PREVIEW_WIDTH = 320
PREVIEW_HEIGHT = 240
PREVIEW_HZ = 10
IMAGE_NAME_FMT = "HIHO_MOCAP_Cam_{cam_id}"


class BlenderCameraPreview:
    """Bridge CameraManager frames into Blender Image datablocks.

    Usage:
        preview = BlenderCameraPreview(mgr)
        preview.start()           # creates 4 images + registers 10 Hz timer
        # ... Image Editor refreshes live ...
        preview.stop()            # unregisters timer; images stay in bpy.data
        preview.remove_images()   # optional: also delete the datablocks
    """

    def __init__(self, camera_manager, preview_width=PREVIEW_WIDTH, preview_height=PREVIEW_HEIGHT):
        self.mgr = camera_manager
        self.preview_w = preview_width
        self.preview_h = preview_height
        self._image_names = []
        self._pixel_bufs = {}  # reused each tick so we don't realloc 40 MB/s of float32
        self._timer_fn = None

    def start(self):
        if self._timer_fn is not None:
            return

        for cam_id in self.mgr.camera_ids:
            name = IMAGE_NAME_FMT.format(cam_id=cam_id)
            img = bpy.data.images.get(name)
            if img is None:
                img = bpy.data.images.new(
                    name=name,
                    width=self.preview_w,
                    height=self.preview_h,
                    alpha=True,
                    float_buffer=False,
                )
            elif img.size[0] != self.preview_w or img.size[1] != self.preview_h:
                img.scale(self.preview_w, self.preview_h)
            self._image_names.append(name)
            self._pixel_bufs[cam_id] = np.zeros(
                self.preview_w * self.preview_h * 4, dtype=np.float32
            )

        self._timer_fn = self._timer_tick
        bpy.app.timers.register(self._timer_fn, first_interval=1.0 / PREVIEW_HZ)

    def stop(self):
        if self._timer_fn is not None and bpy.app.timers.is_registered(self._timer_fn):
            bpy.app.timers.unregister(self._timer_fn)
        self._timer_fn = None

    def remove_images(self):
        for name in self._image_names:
            img = bpy.data.images.get(name)
            if img is not None:
                bpy.data.images.remove(img)
        self._image_names.clear()
        self._pixel_bufs.clear()

    def _timer_tick(self):
        frames = self.mgr.get_latest_frames()
        for cam_id, frame in frames.items():
            if frame is None:
                continue
            img = bpy.data.images.get(IMAGE_NAME_FMT.format(cam_id=cam_id))
            if img is None:
                continue

            small = cv2.resize(
                frame, (self.preview_w, self.preview_h), interpolation=cv2.INTER_AREA
            )
            rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)

            buf = self._pixel_bufs[cam_id]
            view = buf.reshape(self.preview_h, self.preview_w, 4)
            # OpenCV stores top-row-first; Blender Image stores bottom-row-first.
            # Reverse-index the destination's row axis to flip on assignment.
            view[::-1, :, :3] = rgb.astype(np.float32) / 255.0
            view[..., 3] = 1.0

            img.pixels.foreach_set(buf)
            img.update()

        return 1.0 / PREVIEW_HZ
