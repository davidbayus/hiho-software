"""HIHO MOCAP — enforce rigid-bodies assumption.

1:1 with ajc27_freemocap_blender_addon's:
- enforce_rigid_bodies.py
- calculate_bone_length_statistics.py
- data_models/mediapipe_names/mediapipe_heirarchy.py

For each bone, pick a target length, then for each frame where the bone
differs, translate the tail landmark (and its hierarchical descendants) by
the delta that brings the bone back to target. Removes per-frame bone-length
jitter from triangulation noise without smoothing the captured motion.

Target = median for body bones. Fingers instead use a high percentile and
are mirrored left<->right: foreshortening makes per-frame finger lengths read
too short (and unevenly per hand), so the median builds stubby, asymmetric
hands; the percentile recovers the true length and the mirror keeps them even.

Pure function. Takes a positions dict (landmark_name → (frames, 3)) plus
the bone topology, returns a new positions dict with bone lengths
clamped. The hierarchy is module-level since it's a constant lifted
1:1 from ajc27.

Not wired into the load pipeline yet — exists as a ready-to-integrate
module so the next session can drop it in once we know the hand bone
output is otherwise correct.
"""

from typing import Dict, List, Tuple

import numpy as np


# Hierarchy of which landmarks move when a parent is translated. Verbatim
# from ajc27 mediapipe_heirarchy.py — keys are landmark names, values are
# direct children (translation cascades recursively).
LANDMARK_HIERARCHY: Dict[str, List[str]] = {
    # Torso
    "hips_center": ["right_hip", "left_hip", "trunk_center"],
    "trunk_center": ["neck_center"],
    "neck_center": ["right_shoulder", "left_shoulder", "head_center"],
    "head_center": [
        "nose", "mouth_right", "mouth_left",
        "right_eye", "right_eye_inner", "right_eye_outer",
        "left_eye", "left_eye_inner", "left_eye_outer",
        "right_ear", "left_ear",
    ],
    # Legs
    "right_hip": ["right_knee"],
    "right_knee": ["right_ankle"],
    "right_ankle": ["right_foot_index", "right_heel"],
    "left_hip": ["left_knee"],
    "left_knee": ["left_ankle"],
    "left_ankle": ["left_foot_index", "left_heel"],
    # Arms
    "right_shoulder": ["right_elbow"],
    "right_elbow": ["right_wrist"],
    "right_wrist": [
        "right_thumb", "right_index", "right_pinky",
        "right_hand_middle", "right_hand_wrist",
    ],
    "left_shoulder": ["left_elbow"],
    "left_elbow": ["left_wrist"],
    "left_wrist": [
        "left_thumb", "left_index", "left_pinky",
        "left_hand_middle", "left_hand_wrist",
    ],
    # Hand roots
    "right_hand_wrist": [
        "right_hand_thumb_cmc",
        "right_hand_index_finger_mcp",
        "right_hand_middle_finger_mcp",
        "right_hand_ring_finger_mcp",
        "right_hand_pinky_mcp",
    ],
    "left_hand_wrist": [
        "left_hand_thumb_cmc",
        "left_hand_index_finger_mcp",
        "left_hand_middle_finger_mcp",
        "left_hand_ring_finger_mcp",
        "left_hand_pinky_mcp",
    ],
    # Right hand finger chains
    "right_hand_thumb_cmc": ["right_hand_thumb_mcp"],
    "right_hand_thumb_mcp": ["right_hand_thumb_ip"],
    "right_hand_thumb_ip": ["right_hand_thumb_tip"],
    "right_hand_index_finger_mcp": ["right_hand_index_finger_pip"],
    "right_hand_index_finger_pip": ["right_hand_index_finger_dip"],
    "right_hand_index_finger_dip": ["right_hand_index_finger_tip"],
    "right_hand_middle_finger_mcp": ["right_hand_middle_finger_pip"],
    "right_hand_middle_finger_pip": ["right_hand_middle_finger_dip"],
    "right_hand_middle_finger_dip": ["right_hand_middle_finger_tip"],
    "right_hand_ring_finger_mcp": ["right_hand_ring_finger_pip"],
    "right_hand_ring_finger_pip": ["right_hand_ring_finger_dip"],
    "right_hand_ring_finger_dip": ["right_hand_ring_finger_tip"],
    "right_hand_pinky_mcp": ["right_hand_pinky_pip"],
    "right_hand_pinky_pip": ["right_hand_pinky_dip"],
    "right_hand_pinky_dip": ["right_hand_pinky_tip"],
    # Left hand finger chains
    "left_hand_thumb_cmc": ["left_hand_thumb_mcp"],
    "left_hand_thumb_mcp": ["left_hand_thumb_ip"],
    "left_hand_thumb_ip": ["left_hand_thumb_tip"],
    "left_hand_index_finger_mcp": ["left_hand_index_finger_pip"],
    "left_hand_index_finger_pip": ["left_hand_index_finger_dip"],
    "left_hand_index_finger_dip": ["left_hand_index_finger_tip"],
    "left_hand_middle_finger_mcp": ["left_hand_middle_finger_pip"],
    "left_hand_middle_finger_pip": ["left_hand_middle_finger_dip"],
    "left_hand_middle_finger_dip": ["left_hand_middle_finger_tip"],
    "left_hand_ring_finger_mcp": ["left_hand_ring_finger_pip"],
    "left_hand_ring_finger_pip": ["left_hand_ring_finger_dip"],
    "left_hand_ring_finger_dip": ["left_hand_ring_finger_tip"],
    "left_hand_pinky_mcp": ["left_hand_pinky_pip"],
    "left_hand_pinky_pip": ["left_hand_pinky_dip"],
    "left_hand_pinky_dip": ["left_hand_pinky_tip"],
}


# Finger-chain bone prefixes — these get the percentile + mirror treatment.
_FINGER_PREFIXES = ("thumb.", "palm.", "f_index.", "f_middle.", "f_ring.", "f_pinky.")
_FINGER_PERCENTILE = 90


def _symmetrize_fingers(targets: Dict[str, float]) -> None:
    """Average each finger bone's left and right target so the hands match.

    Real hands are mirror images; per-hand measurement drifts apart when one
    hand tracks worse than the other. Mutates `targets` in place.
    """
    for bone in list(targets):
        if bone.endswith(".R") and bone.startswith(_FINGER_PREFIXES):
            mate = bone[:-2] + ".L"
            if mate in targets:
                avg = (targets[bone] + targets[mate]) / 2.0
                targets[bone] = targets[mate] = avg


def enforce_rigid_bodies(
    positions: Dict[str, np.ndarray],
    bone_to_empties: Dict[str, Tuple[str, str]],
) -> Dict[str, np.ndarray]:
    """Clamp per-frame bone lengths to their median.

    For each bone in `bone_to_empties`, computes the per-frame head-to-tail
    distance across all frames and takes the median. For each frame, computes
    a position delta that would restore the bone to median length, then
    applies that delta to the tail landmark AND its hierarchical descendants
    (via LANDMARK_HIERARCHY). The bone direction is preserved; only its
    length is corrected.

    Pure function — does not mutate `positions`. Returns a fresh dict.
    Bones with all-NaN or zero-length lengths arrays are skipped.

    NaN handling: per-frame, if either head or tail is NaN OR the computed
    length is zero, that frame is skipped for that bone (no translation).
    """
    bone_lengths_per_frame: Dict[str, np.ndarray] = {}
    bone_targets: Dict[str, float] = {}

    for bone, (head, tail) in bone_to_empties.items():
        if head not in positions or tail not in positions:
            continue
        head_traj = positions[head]
        tail_traj = positions[tail]
        lengths = np.linalg.norm(tail_traj - head_traj, axis=1)
        bone_lengths_per_frame[bone] = lengths
        valid = lengths[~np.isnan(lengths)]
        if len(valid) > 0:
            # Fingers read too short most frames (foreshortening collapses the
            # triangulated depth), so take a high percentile — the length from
            # the best-tracked frames. Body bones are long enough that the
            # median is fine, and real left/right asymmetry should be kept.
            if bone.startswith(_FINGER_PREFIXES):
                bone_targets[bone] = float(np.percentile(valid, _FINGER_PERCENTILE))
            else:
                bone_targets[bone] = float(np.median(valid))

    _symmetrize_fingers(bone_targets)

    updated = {name: traj.copy() for name, traj in positions.items()}

    for bone, (head, tail) in bone_to_empties.items():
        desired_length = bone_targets.get(bone)
        if desired_length is None or desired_length <= 0:
            continue
        lengths = bone_lengths_per_frame[bone]

        for frame_idx in range(lengths.shape[0]):
            raw_length = float(lengths[frame_idx])
            if np.isnan(raw_length) or raw_length == 0:
                continue

            head_pos = positions[head][frame_idx]
            tail_pos = positions[tail][frame_idx]
            bone_vec = tail_pos - head_pos
            bone_vec_norm = bone_vec / raw_length
            position_delta = bone_vec_norm * (desired_length - raw_length)

            _translate_with_children(tail, position_delta, frame_idx, updated)

    return updated


def _translate_with_children(
    name: str,
    position_delta: np.ndarray,
    frame_idx: int,
    updated_positions: Dict[str, np.ndarray],
) -> None:
    """Add position_delta to the named trajectory at frame_idx, recursing
    into all hierarchical children. Silently skips landmarks not in the dict
    (e.g., virtual landmarks the hierarchy might reference but we don't
    spawn).
    """
    if name not in updated_positions:
        return
    updated_positions[name][frame_idx] += position_delta
    for child in LANDMARK_HIERARCHY.get(name, ()):
        _translate_with_children(child, position_delta, frame_idx, updated_positions)
