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

HIHO addition (1.5.7, FINGER_LENGTH_FIX_DESIGN_2026-10-04.md, bug #4): a badly
tracked hand can read a fingertip at 692 mm, and the mirror then spreads that
damage to the clean hand. So every finger bone now has a ceiling scaled to the
performer's own forearm, lengths are picked from the readings under it, and
only hands that tracked well are averaged; a bad hand copies the good one.

Pure function. Takes a positions dict (landmark_name → (frames, 3)) plus
the bone topology, returns a new positions dict with bone lengths
clamped. The hierarchy is module-level since it's a constant lifted
1:1 from ajc27.
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

# Ceiling per finger bone as a fraction of the performer's forearm (elbow to
# wrist, which the body tracker reads reliably). Generous on purpose: a real
# index fingertip is ~9% of the forearm, the ceiling allows 13%, so a large
# hand is never squeezed; only tracking garbage is excluded. Scaling by the
# forearm makes it fit a 6th grader and an adult without a setting.
_FINGER_CEILING_FRACTION: Dict[str, float] = {
    "thumb.carpal": 0.22,
    "thumb.01": 0.22,
    "thumb.02": 0.18,
    "thumb.03": 0.16,
    "palm": 0.45,
    ".01": 0.22,
    ".02": 0.15,
    ".03": 0.13,
}
_FOREARM_FALLBACK_M = 0.25
_HAND_CLEAN_SHARE = 2.0 / 3.0


def _finger_ceiling_fraction(bone_base: str) -> float:
    if bone_base in _FINGER_CEILING_FRACTION:
        return _FINGER_CEILING_FRACTION[bone_base]
    if bone_base.startswith("palm."):
        return _FINGER_CEILING_FRACTION["palm"]
    return _FINGER_CEILING_FRACTION[bone_base[-3:]]


def _forearm_length(positions: Dict[str, np.ndarray]) -> float:
    """Median elbow-to-wrist length over both arms and all frames (meters)."""
    samples = []
    for side in ("right", "left"):
        elbow = positions.get(f"{side}_elbow")
        wrist = positions.get(f"{side}_wrist")
        if elbow is None or wrist is None:
            continue
        lengths = np.linalg.norm(wrist - elbow, axis=1)
        lengths = lengths[~np.isnan(lengths)]
        if len(lengths):
            samples.append(lengths)
    if not samples:
        return _FOREARM_FALLBACK_M
    forearm = float(np.median(np.concatenate(samples)))
    return forearm if forearm > 0 else _FOREARM_FALLBACK_M


def _finger_targets(
    bone_lengths_per_frame: Dict[str, np.ndarray],
    forearm: float,
) -> Tuple[Dict[str, float], Dict[str, float]]:
    """Target length per finger bone, mirrored only across hands that tracked well.

    Returns (targets, hand_scores). A hand's score is the share of its finger
    readings under the ceiling. Both hands clean: average them. One hand bad:
    both hands copy the good one. Both bad: both copy the better one.
    """
    per_side: Dict[str, Dict[str, float]] = {"R": {}, "L": {}}
    under = {"R": 0, "L": 0}
    total = {"R": 0, "L": 0}
    for bone, lengths in bone_lengths_per_frame.items():
        if not bone.startswith(_FINGER_PREFIXES):
            continue
        side = bone[-1]
        base = bone[:-2]
        valid = lengths[~np.isnan(lengths)]
        if len(valid) == 0:
            continue
        ceiling = _finger_ceiling_fraction(base) * forearm
        clean = valid[valid <= ceiling]
        under[side] += len(clean)
        total[side] += len(valid)
        per_side[side][base] = (
            float(np.percentile(clean, _FINGER_PERCENTILE)) if len(clean) else ceiling
        )

    scores = {s: (under[s] / total[s] if total[s] else 0.0) for s in ("R", "L")}
    clean_hands = [s for s in ("R", "L") if scores[s] >= _HAND_CLEAN_SHARE]
    better = "R" if scores["R"] >= scores["L"] else "L"

    targets: Dict[str, float] = {}
    for base in set(per_side["R"]) | set(per_side["L"]):
        right = per_side["R"].get(base)
        left = per_side["L"].get(base)
        if right is not None and left is not None:
            if len(clean_hands) == 2:
                value = (right + left) / 2.0
            elif len(clean_hands) == 1:
                value = right if clean_hands[0] == "R" else left
            else:
                value = right if better == "R" else left
            targets[base + ".R"] = targets[base + ".L"] = value
        elif right is not None:
            targets[base + ".R"] = right
        elif left is not None:
            targets[base + ".L"] = left
    return targets, scores


def enforce_rigid_bodies(
    positions: Dict[str, np.ndarray],
    bone_to_empties: Dict[str, Tuple[str, str]],
) -> Dict[str, np.ndarray]:
    """Clamp per-frame bone lengths to one target per bone.

    Body bones: the median. Finger bones: see _finger_targets.

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
        if len(valid) > 0 and not bone.startswith(_FINGER_PREFIXES):
            bone_targets[bone] = float(np.median(valid))

    finger_targets, hand_scores = _finger_targets(
        bone_lengths_per_frame, _forearm_length(positions),
    )
    bone_targets.update(finger_targets)
    print(
        "HIHO MOCAP finger lengths: right hand {:.0%} clean, left hand {:.0%} clean"
        .format(hand_scores["R"], hand_scores["L"])
    )

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
