# RETIRED (2026-06-09): not registered, not imported by the addon. The live
# capture path is operators/external_capture.py + external/record_take.py;
# processing is core/external_runner.py + external/. Kept on disk per the
# never-delete policy; excluded from shipped zips. Do not re-wire without
# reading AUDIT_2026-06-09.md (finding L1) — this code predates the headless
# pivot and bypasses the per-camera rotation system.
"""HIHO MOCAP — place the capture cameras in the scene at their real positions.

Clean-room port of ajc27's add_capture_cameras: read each camera's saved place +
angle from the calibration .toml and create a Blender camera there, with the lens
matched from the calibration's focal length.

Unlike ajc27 (which only runs after a groundplane calibration and places cameras
in FreeMoCap's raw world frame), we run each camera through the SAME stand-up
transform the skelly gets (core/loader.recording_alignment). That lines the
cameras up with the skelly on ANY calibration, groundplane or not, and is the
built-in correctness check: look through a camera and the skelly is framed exactly
as the real camera saw the performer. See ../CAPTURE_CAMERAS_DESIGN_2026-06-06.md.
"""

import math

import bpy
from mathutils import Matrix, Quaternion, Vector

try:
    import tomllib
except ModuleNotFoundError:  # Blender 5.2 ships Python 3.11+, so this never fires.
    tomllib = None

CAMERA_COLLECTION = "HIHO MOCAP Cameras"
SENSOR_WIDTH_MM = 36.0  # ajc27 assumes a fixed sensor and derives lens from focal px
MM_TO_M = 1.0 / 1000.0
# Calibration cameras look down +Z (computer-vision convention); Blender cameras
# look down -Z. ajc27's verbatim fix is a 180° spin about X (also flips up axis).
_FLIP_X_180 = Quaternion((1.0, 0.0, 0.0), math.pi)


def _load_toml(path):
    with open(path, "rb") as f:
        return tomllib.load(f)


def _camera_sections(data):
    """The cam_* tables in calibration order (cam_0, cam_1, ...)."""
    cams = [(k, v) for k, v in data.items() if k.startswith("cam_")]
    cams.sort(key=lambda kv: int(kv[0].split("_")[1]))
    return cams


def _cameras_collection():
    coll = bpy.data.collections.get(CAMERA_COLLECTION)
    if coll is None:
        coll = bpy.data.collections.new(CAMERA_COLLECTION)
        bpy.context.scene.collection.children.link(coll)
    return coll


def add_capture_cameras(toml_path, alignment, parent=None):
    """Create one Blender camera per calibration camera, aligned to the skelly.

    toml_path : path to the FreeMoCap calibration .toml (has world_position +
                world_orientation per cam_N — present on every calibration).
    alignment : (translation, rotation) from loader.recording_alignment — the
                stand-up transform that moves cameras into the skelly's frame.
    parent    : optional object (the take's skelly root) to parent cameras under.
                It sits at identity, so each camera's local transform IS its world
                pose; parenting just keeps cameras locked to the skelly.

    Returns the list of created camera object names.
    """
    data = _load_toml(toml_path)
    translation, rotation = alignment
    t = Vector((float(translation[0]), float(translation[1]), float(translation[2])))
    # rows of `rotation` are the body x/y/z basis in raw-world coords (loader.py).
    R = Matrix([[float(rotation[r][c]) for c in range(3)] for r in range(3)])

    coll = _cameras_collection()
    created = []
    for key, cam in _camera_sections(data):
        name = cam.get("name", key)

        # Position: same formula the landmarks get — R @ (P_raw_m - translation).
        p_raw_m = Vector((float(cam["world_position"][0]),
                          float(cam["world_position"][1]),
                          float(cam["world_position"][2]))) * MM_TO_M
        loc = R @ (p_raw_m - t)

        # Orientation: rotate the camera's world basis by R, then the CV->Blender flip.
        cam_to_world = Matrix([[float(cam["world_orientation"][r][c]) for c in range(3)]
                               for r in range(3)])
        quat = (R @ cam_to_world).to_quaternion() @ _FLIP_X_180

        cam_data = bpy.data.cameras.new(name)
        obj = bpy.data.objects.new(name, cam_data)
        obj.location = loc
        obj.rotation_mode = 'QUATERNION'
        obj.rotation_quaternion = quat

        # Lens from focal length in pixels (ajc27's recipe). max(w,h) handles
        # landscape vs portrait. Intrinsics are unaffected by the rigid world move.
        fx = float(cam["matrix"][0][0])
        w_px, h_px = float(cam["size"][0]), float(cam["size"][1])
        cam_data.sensor_width = SENSOR_WIDTH_MM
        cam_data.lens_unit = 'MILLIMETERS'
        cam_data.lens = fx * (SENSOR_WIDTH_MM / max(w_px, h_px))
        cam_data.display_size = 0.3  # smaller gizmo; cosmetic, no effect on render

        obj.show_name = True
        coll.objects.link(obj)
        if parent is not None:
            obj.parent = parent  # parent is at identity → local pose == world pose
        created.append(obj.name)

    return created
