"""HIHO MOCAP — spawn the captured motion in the scene as keyframed empties.

For v1.0 the output is one Empty per MediaPipe body landmark (33 total),
parented to a single "HIHO MOCAP Skelly" root, with location keyframes
written via the Blender 4.4+ slotted-actions fcurves API. The student can
press Spacebar and see the dots play back the motion. A real armature
(bones + IK) lands in v1.1.

Lift the bulk-keyframe recipe from ajc27_freemocap_blender_addon's
create_empty_from_trajectory.py (4.4+ branch). Per-frame keyframe_insert is
60-100x slower for our frame counts.

Unit conversion: FreeMoCap 3D landmarks are in millimeters. Blender's default
unit is meters. Divide by 1000.

Coordinate orientation: FreeMoCap and Blender both use +Z up. We align the
captured data to a canonical body frame first (via core/loader.py) so the
rig built from it stands upright at world origin, regardless of how the
calibration board happened to be sitting during recording.
"""

from pathlib import Path
from typing import Optional

import bpy
import numpy as np

from .loader import (
    MEDIAPIPE_BODY_LANDMARK_NAMES,
    MEDIAPIPE_LEFT_HAND_LANDMARK_NAMES,
    MEDIAPIPE_RIGHT_HAND_LANDMARK_NAMES,
    fill_untracked_frames,
    load_aligned_body_data,
    load_aligned_data,
)


MM_TO_M = 1.0 / 1000.0
EMPTY_SCALE = 0.05  # 5cm display dots for body landmarks
HAND_EMPTY_SCALE = 0.012  # 1.2cm display dots for finger landmarks (smaller scale)


def spawn_skelly_from_recording(recording_folder: str) -> bpy.types.Object:
    """Load body + hand landmarks and spawn keyframed empties under a Skelly root.

    Spawns 33 body empties + 21 right-hand empties + 21 left-hand empties = 75
    landmark empties total, all parented to a single root so the student can
    move/rotate/scale the skeleton as a unit. Hand data has been per-frame
    translated by fix_hand_data so each hand's wrist coincides with the body's
    wrist (1:1 with ajc27's pipeline).
    """
    body_npy_path = Path(recording_folder) / "output_data" / "mediapipe_body_3d_xyz.npy"
    if not body_npy_path.is_file():
        raise FileNotFoundError(
            f"No body landmarks at {body_npy_path}. "
            "Did processing complete successfully?"
        )

    data = load_aligned_data(recording_folder)
    body_meters = data["body"]
    right_hand_meters = data["right_hand"]
    left_hand_meters = data["left_hand"]

    if body_meters.ndim != 3 or body_meters.shape[1] != 33 or body_meters.shape[2] != 3:
        raise ValueError(
            f"Unexpected body landmark shape {body_meters.shape}; expected (frames, 33, 3)."
        )
    if right_hand_meters.shape[1] != 21 or left_hand_meters.shape[1] != 21:
        raise ValueError(
            f"Unexpected hand landmark shape: right={right_hand_meters.shape}, "
            f"left={left_hand_meters.shape}; expected (frames, 21, 3)."
        )
    num_frames = body_meters.shape[0]

    root = _make_root_empty(recording_folder, num_frames)
    untracked = []

    def _spawn_set(names, array, display_size):
        for landmark_idx, name in enumerate(names):
            traj = fill_untracked_frames(array[:, landmark_idx, :])
            if traj is None:
                untracked.append(name)
            # Create the empty even when never tracked (traj None, no
            # animation) so the constraint stack still has its target.
            _create_keyframed_empty(
                name=f"hiho_{name}",
                traj_fr_xyz=traj,
                parent=root,
                display_size=display_size,
            )

    _spawn_set(MEDIAPIPE_BODY_LANDMARK_NAMES, body_meters, EMPTY_SCALE)
    _spawn_set(MEDIAPIPE_RIGHT_HAND_LANDMARK_NAMES, right_hand_meters, HAND_EMPTY_SCALE)
    _spawn_set(MEDIAPIPE_LEFT_HAND_LANDMARK_NAMES, left_hand_meters, HAND_EMPTY_SCALE)

    if untracked:
        # Read by the Spawn operators for the status message; saved with the
        # .blend so the take carries its own "what the cameras never saw".
        root["hiho_untracked"] = ", ".join(untracked)

    bpy.context.scene.frame_end = max(bpy.context.scene.frame_end, num_frames)

    return root


def _make_root_empty(recording_folder: str, num_frames: int) -> bpy.types.Object:
    folder_label = Path(recording_folder).name
    name = f"HIHO_MOCAP_Skelly_{folder_label}"
    root = bpy.data.objects.new(name, None)
    root.empty_display_type = 'ARROWS'
    root.empty_display_size = 0.3
    bpy.context.collection.objects.link(root)
    return root


def _create_keyframed_empty(
    name: str,
    traj_fr_xyz: Optional[np.ndarray],
    parent: bpy.types.Object,
    display_size: float = EMPTY_SCALE,
) -> bpy.types.Object:
    empty = bpy.data.objects.new(name, None)
    empty.empty_display_type = 'SPHERE'
    empty.empty_display_size = display_size
    empty.parent = parent
    bpy.context.collection.objects.link(empty)

    if traj_fr_xyz is None:
        # Never tracked: leave the empty static at the root, unanimated.
        return empty

    action = bpy.data.actions.new(name=f"{name}_Action")
    empty.animation_data_create()
    empty.animation_data.action = action

    slot = action.slots.new(id_type='OBJECT', name=name)
    layer = action.layers.new("Layer")
    strip = layer.strips.new(type='KEYFRAME')
    channelbag = strip.channelbag(slot, ensure=True)
    empty.animation_data.action_slot = slot

    num_frames = traj_fr_xyz.shape[0]
    start_frame = bpy.context.scene.frame_start
    frames = np.arange(start_frame, start_frame + num_frames, dtype=np.float32)

    for axis_idx in range(3):
        fcurve = channelbag.fcurves.new(data_path="location", index=axis_idx)
        fcurve.keyframe_points.add(count=num_frames)
        co = np.empty(2 * num_frames, dtype=np.float32)
        co[0::2] = frames
        co[1::2] = traj_fr_xyz[:, axis_idx]
        fcurve.keyframe_points.foreach_set("co", co)
        fcurve.update()

    return empty
