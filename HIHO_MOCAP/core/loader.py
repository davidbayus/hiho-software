"""HIHO MOCAP — load body + hand landmarks, align, enforce, return positions.

End-to-end 1:1 with ajc27_freemocap_blender_addon's load pipeline:
- estimate_good_frame.py: picks the alignment reference frame (most still).
- put_skeleton_on_ground.py: computes body-frame translation+rotation from
  that frame's foot positions, applies to ALL components.
- fix_hand_data.py: per-frame translates MediaPipe-Hands data so each hand's
  wrist landmark sits on the body's wrist landmark.
- calculate_virtual_trajectories.py: computes head_center, hips_center, etc.
- enforce_rigid_bodies.py: clamps per-frame bone lengths to the median.

After load_aligned_data:
- body center sits at world origin, +Z is body-up, body-forward is -Y.
- right_hand_wrist == right_wrist (and same on the left).
- Virtual landmarks (head_center etc.) are computed and included.
- All bone lengths are constant frame-to-frame.

The "good frame" is the most-STILL frame — lowest foot velocity, with the
feet visible (reprojection error non-NaN). Picking a mid-motion frame
instead would compute the body frame from a non-neutral pose and the rig
comes out rotated around Z.
"""

import math
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from .enforce_rigid_bodies import enforce_rigid_bodies
from .topology import BONE_HEAD_TAIL_MAP


MM_TO_M = 1.0 / 1000.0


# 33 MediaPipe Pose landmark names, in the order they appear in the body npy's
# second axis. Lifted from ajc27 mediapipe_trajectory_names.py:25-59.
MEDIAPIPE_BODY_LANDMARK_NAMES = (
    "nose",
    "left_eye_inner", "left_eye", "left_eye_outer",
    "right_eye_inner", "right_eye", "right_eye_outer",
    "left_ear", "right_ear",
    "mouth_left", "mouth_right",
    "left_shoulder", "right_shoulder",
    "left_elbow", "right_elbow",
    "left_wrist", "right_wrist",
    "left_pinky", "right_pinky",
    "left_index", "right_index",
    "left_thumb", "right_thumb",
    "left_hip", "right_hip",
    "left_knee", "right_knee",
    "left_ankle", "right_ankle",
    "left_heel", "right_heel",
    "left_foot_index", "right_foot_index",
)

# Indices into MEDIAPIPE_BODY_LANDMARK_NAMES we need for the algorithms here
# (alignment + fix_hand_data). Other callers compute their own indices.
_LM = {
    "left_ear": 7, "right_ear": 8,
    "left_wrist": 15, "right_wrist": 16,
    "left_heel": 29, "right_heel": 30,
    "left_foot_index": 31, "right_foot_index": 32,
}


# 21 MediaPipe Hands landmarks per side, in the order they appear in the
# *_hand_3d_xyz.npy file's second axis. Source: ajc27
# data_models/mediapipe_names/mediapipe_trajectory_names.py:60-81.
_HAND_LANDMARK_SUFFIXES = (
    "wrist",
    "thumb_cmc", "thumb_mcp", "thumb_ip", "thumb_tip",
    "index_finger_mcp", "index_finger_pip", "index_finger_dip", "index_finger_tip",
    "middle_finger_mcp", "middle_finger_pip", "middle_finger_dip", "middle_finger_tip",
    "ring_finger_mcp", "ring_finger_pip", "ring_finger_dip", "ring_finger_tip",
    "pinky_mcp", "pinky_pip", "pinky_dip", "pinky_tip",
)

MEDIAPIPE_RIGHT_HAND_LANDMARK_NAMES = tuple(f"right_hand_{n}" for n in _HAND_LANDMARK_SUFFIXES)
MEDIAPIPE_LEFT_HAND_LANDMARK_NAMES = tuple(f"left_hand_{n}" for n in _HAND_LANDMARK_SUFFIXES)

# Both hand npys have wrist at index 0 by convention.
_HAND_WRIST_IDX = 0


# Virtual landmarks (computed by weighted mean of body landmarks) used by
# the bone rig — spine bones target trunk_center, head bone targets head_center,
# etc. Lifted verbatim from ajc27 mediapipe_names/virtual_trajectories.py.
# Note: right_hand_middle is a BODY-data midpoint (not a MediaPipe-Hands
# landmark) — ajc27 keeps the same definition even when hand data is present.
_VIRTUAL_LANDMARKS: Dict[str, List[Tuple[str, float]]] = {
    "head_center":  [("left_ear", 0.5), ("right_ear", 0.5)],
    "neck_center":  [("left_shoulder", 0.5), ("right_shoulder", 0.5)],
    "trunk_center": [
        ("left_shoulder", 0.25), ("right_shoulder", 0.25),
        ("left_hip", 0.25), ("right_hip", 0.25),
    ],
    "hips_center":  [("left_hip", 0.5), ("right_hip", 0.5)],
    "right_hand_middle": [("right_index", 0.5), ("right_pinky", 0.5)],
    "left_hand_middle":  [("left_index", 0.5), ("left_pinky", 0.5)],
}

VIRTUAL_LANDMARK_NAMES = tuple(_VIRTUAL_LANDMARKS.keys())


def load_aligned_data(recording_folder: str) -> Dict[str, object]:
    """Load body + hands, align, fix_hand_data, virtuals, enforce. Returns dict.

    Returned dict has:
    - 'body'       : (frames, 33, 3) float32 — enforced + aligned body landmarks.
    - 'right_hand' : (frames, 21, 3) float32 — enforced + aligned right hand.
    - 'left_hand'  : (frames, 21, 3) float32 — enforced + aligned left hand.
    - 'virtuals'   : dict[name -> (frames, 3) float32] — 6 virtual landmarks.
    - 'positions'  : dict[name -> (frames, 3) float32] — unified flat lookup
                     of every landmark (body + virtuals + hands), for callers
                     like build_rig.measure_bone_lengths that key by name.
    """
    output_dir = Path(recording_folder) / "output_data"

    # Check the full file set upfront with one actionable message — a raw
    # FileNotFoundError deep in the load reads as a crash, far from the cause
    # (legacy takes, or output_data copied without raw_data/). Audit M13.
    required = (
        output_dir / "mediapipe_body_3d_xyz.npy",
        output_dir / "mediapipe_right_hand_3d_xyz.npy",
        output_dir / "mediapipe_left_hand_3d_xyz.npy",
        output_dir / "raw_data" / "mediapipe_3dData_numFrames_numTrackedPoints_reprojectionError.npy",
    )
    missing = [p.name for p in required if not p.is_file()]
    if missing:
        raise FileNotFoundError(
            f"this take's output_data is missing {', '.join(missing)} - it may "
            "be from an older HIHO MOCAP version, or copied without its "
            "raw_data folder. Re-run Process Mocap on the take folder to "
            "rebuild the full set."
        )

    body = np.load(str(output_dir / "mediapipe_body_3d_xyz.npy"))  # (frames, 33, 3) mm
    body_m = (body * MM_TO_M).astype(np.float32)

    right_hand = np.load(str(output_dir / "mediapipe_right_hand_3d_xyz.npy"))  # (frames, 21, 3) mm
    left_hand = np.load(str(output_dir / "mediapipe_left_hand_3d_xyz.npy"))
    right_hand_m = (right_hand * MM_TO_M).astype(np.float32)
    left_hand_m = (left_hand * MM_TO_M).astype(np.float32)

    error_npy = output_dir / "raw_data" / "mediapipe_3dData_numFrames_numTrackedPoints_reprojectionError.npy"
    body_error = np.load(str(error_npy))

    good_frame = _estimate_good_frame(body_m, body_error)
    translation, rotation = _compute_alignment(body_m, good_frame)

    aligned_body = ((body_m - translation) @ rotation.T).astype(np.float32)
    aligned_right_hand = ((right_hand_m - translation) @ rotation.T).astype(np.float32)
    aligned_left_hand = ((left_hand_m - translation) @ rotation.T).astype(np.float32)

    aligned_right_hand, aligned_left_hand = _apply_fix_hand_data(
        aligned_body, aligned_right_hand, aligned_left_hand,
    )

    positions = _build_positions_dict(aligned_body, aligned_right_hand, aligned_left_hand)
    positions = enforce_rigid_bodies(positions, BONE_HEAD_TAIL_MAP)

    # Re-slice enforced positions back into body/hand arrays so existing callers
    # keep working (output_rig.py iterates by index).
    enforced_body = np.stack(
        [positions[name] for name in MEDIAPIPE_BODY_LANDMARK_NAMES], axis=1,
    ).astype(np.float32)
    enforced_right_hand = np.stack(
        [positions[name] for name in MEDIAPIPE_RIGHT_HAND_LANDMARK_NAMES], axis=1,
    ).astype(np.float32)
    enforced_left_hand = np.stack(
        [positions[name] for name in MEDIAPIPE_LEFT_HAND_LANDMARK_NAMES], axis=1,
    ).astype(np.float32)
    virtuals = {name: positions[name] for name in VIRTUAL_LANDMARK_NAMES}

    return {
        "body": enforced_body,
        "right_hand": enforced_right_hand,
        "left_hand": enforced_left_hand,
        "virtuals": virtuals,
        "positions": positions,
    }


def load_aligned_body_data(recording_folder: str) -> np.ndarray:
    """Backwards-compat: body-only return for callers that don't need hands."""
    return load_aligned_data(recording_folder)["body"]


def recording_alignment(recording_folder: str) -> Tuple[np.ndarray, np.ndarray]:
    """Return the (translation, rotation) that stands the captured skeleton up at
    the origin — the SAME transform load_aligned_data applies to the landmarks.

    Exposed so capture-camera placement can move the cameras into the skelly's
    frame (see ../CAPTURE_CAMERAS_DESIGN_2026-06-06.md). Deterministic: same npys
    in, same transform out, so the cameras and the skelly stay locked together.

    translation: (3,) meters — the good-frame foot center.
    rotation:    (3,3) — rows are the body x/y/z basis expressed in raw-world.
    """
    output_dir = Path(recording_folder) / "output_data"
    body = np.load(str(output_dir / "mediapipe_body_3d_xyz.npy"))
    body_m = (body * MM_TO_M).astype(np.float32)
    error_npy = output_dir / "raw_data" / "mediapipe_3dData_numFrames_numTrackedPoints_reprojectionError.npy"
    body_error = np.load(str(error_npy))
    good_frame = _estimate_good_frame(body_m, body_error)
    return _compute_alignment(body_m, good_frame)


def fill_untracked_frames(traj_fr_xyz: np.ndarray) -> Optional[np.ndarray]:
    """Replace NaN frames with the nearest tracked frame — freeze, don't
    invent motion. MediaPipe leaves NaNs where tracking dropped, and writing
    those into keyframes NaN-poisons the constraint math (audit M12); a
    frozen segment is an honest, visible "the cameras lost this here".
    Returns None if the landmark was never tracked at all.
    """
    finite = np.isfinite(traj_fr_xyz).all(axis=1)
    if not finite.any():
        return None
    if finite.all():
        return traj_fr_xyz
    valid = np.flatnonzero(finite)
    idx = np.arange(traj_fr_xyz.shape[0])
    last_valid = np.clip(np.searchsorted(valid, idx, side="right") - 1, 0, valid.size - 1)
    return traj_fr_xyz[valid[last_valid]]


def _build_positions_dict(
    body: np.ndarray,
    right_hand: np.ndarray,
    left_hand: np.ndarray,
) -> Dict[str, np.ndarray]:
    """Unified landmark-name → (frames, 3) lookup for body + virtuals + hands."""
    positions: Dict[str, np.ndarray] = {}
    for idx, name in enumerate(MEDIAPIPE_BODY_LANDMARK_NAMES):
        positions[name] = body[:, idx, :]
    name_to_idx = {name: idx for idx, name in enumerate(MEDIAPIPE_BODY_LANDMARK_NAMES)}
    for vname, sources in _VIRTUAL_LANDMARKS.items():
        positions[vname] = _compute_virtual_trajectory(body, name_to_idx, sources)
    for idx, name in enumerate(MEDIAPIPE_RIGHT_HAND_LANDMARK_NAMES):
        positions[name] = right_hand[:, idx, :]
    for idx, name in enumerate(MEDIAPIPE_LEFT_HAND_LANDMARK_NAMES):
        positions[name] = left_hand[:, idx, :]
    return positions


def _compute_virtual_trajectory(
    body_meters: np.ndarray,
    name_to_index: Dict[str, int],
    sources: List[Tuple[str, float]],
) -> np.ndarray:
    """Weighted mean over source body landmarks, per frame."""
    traj = np.zeros_like(body_meters[:, 0, :])
    for src_name, weight in sources:
        traj += body_meters[:, name_to_index[src_name], :] * weight
    return traj


def _apply_fix_hand_data(
    body: np.ndarray,
    right_hand: np.ndarray,
    left_hand: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray]:
    """1:1 with ajc27 fix_hand_data.py — translate each hand per-frame so its
    wrist coincides with the body's wrist. The rotation block in ajc27's source
    is commented out; we skip it too.
    """
    delta_right = body[:, _LM["right_wrist"], :] - right_hand[:, _HAND_WRIST_IDX, :]
    delta_left = body[:, _LM["left_wrist"], :] - left_hand[:, _HAND_WRIST_IDX, :]

    right_hand_fixed = right_hand + delta_right[:, np.newaxis, :]
    left_hand_fixed = left_hand + delta_left[:, np.newaxis, :]
    return right_hand_fixed.astype(np.float32), left_hand_fixed.astype(np.float32)


def _estimate_good_frame(
    body_m: np.ndarray,
    body_error: np.ndarray,
    velocity_threshold: float = 0.1,
) -> int:
    """Pick the most-still frame for alignment. 1:1 with ajc27's estimate_good_frame.

    Per foot trajectory: intersect frames that are (a) above the q-th
    percentile of velocity, (b) have non-NaN reprojection error, (c) have
    non-zero velocity. Intersect those sets across all 4 feet. From the
    survivors, pick the frame with the lowest mean foot velocity.

    Without (a), the algorithm picks frames at the noise floor where the
    body isn't actually being tracked. Without (c), it picks NaN-gap
    frames. Without (b), it picks frames the camera couldn't see.
    """
    foot_idxs = [
        _LM["left_heel"], _LM["right_heel"],
        _LM["left_foot_index"], _LM["right_foot_index"],
    ]

    all_good_frames: Optional[set] = None
    per_foot_velocities = {}

    for foot_idx in foot_idxs:
        traj = body_m[:, foot_idx, :]  # (frames, 3)
        vel_xyz = np.diff(traj, axis=0)
        vel_xyz = np.insert(vel_xyz, 0, np.nan, axis=0)
        vel_mag = np.sqrt(np.sum(vel_xyz ** 2, axis=1))
        per_foot_velocities[foot_idx] = vel_mag

        error = body_error[:, foot_idx]
        vel_q_threshold = np.nanpercentile(vel_mag, q=velocity_threshold * 100)
        float_eps_floor = math.ulp(1.0) * 10

        above_threshold = set(np.where(vel_mag > vel_q_threshold)[0].tolist())
        error_not_nan = set(np.where(~np.isnan(error))[0].tolist())
        not_zero = set(np.where(vel_mag > float_eps_floor)[0].tolist())

        good = above_threshold & error_not_nan & not_zero
        if not good:
            continue

        all_good_frames = good if all_good_frames is None else all_good_frames & good

    if not all_good_frames:
        return 0

    good_list = sorted(all_good_frames)
    vels_on_good = np.array([per_foot_velocities[idx][good_list] for idx in foot_idxs])
    mean_vels = np.mean(vels_on_good, axis=0)
    return int(good_list[int(np.argmin(mean_vels))])


def _compute_alignment(body_m: np.ndarray, frame: int) -> Tuple[np.ndarray, np.ndarray]:
    """Compute (translation, rotation_matrix) for the canonical body frame.

    Variable names mirror ajc27's `put_skeleton_on_ground.py` even where
    they're technically misleading (`x_forward` actually points from the
    left half of the body toward center, i.e. rightward) — keeping the
    names lets us cross-check against the reference.
    """
    p = body_m[frame]  # (33, 3)

    center = np.nanmean([
        p[_LM["right_heel"]], p[_LM["left_heel"]],
        p[_LM["right_foot_index"]], p[_LM["left_foot_index"]],
    ], axis=0)
    y_leftward_ref = np.nanmean([p[_LM["left_heel"]], p[_LM["left_foot_index"]]], axis=0)
    x_forward_ref = np.nanmean([p[_LM["left_foot_index"]], p[_LM["right_foot_index"]]], axis=0)
    z_upward_ref = (p[_LM["left_ear"]] + p[_LM["right_ear"]]) / 2.0

    x_forward = center - y_leftward_ref
    y_left = x_forward_ref - center
    # z_up not used directly — recomputed via cross product below for orthogonality.

    z_hat = np.cross(x_forward, y_left)
    y_hat = np.cross(x_forward, z_hat)
    x_hat = np.cross(y_hat, z_hat)

    x_hat = x_hat / np.linalg.norm(x_hat)
    y_hat = y_hat / np.linalg.norm(y_hat)
    z_hat = z_hat / np.linalg.norm(z_hat)

    rotation_matrix = np.array([x_hat, y_hat, z_hat], dtype=np.float32)

    # A NaN here would silently NaN-poison every landmark on every frame
    # downstream and "succeed" into an invisible rig (audit M11) — feet that
    # were never tracked make the nanmean above all-NaN. Fail loud + teachable.
    if not (np.isfinite(center).all() and np.isfinite(rotation_matrix).all()):
        raise ValueError(
            "couldn't find a frame where both feet were tracked, so the "
            "skeleton can't be stood up at the origin. Start every take with "
            "about 5 seconds of standing still, feet visible to the cameras."
        )
    return center.astype(np.float32), rotation_matrix
