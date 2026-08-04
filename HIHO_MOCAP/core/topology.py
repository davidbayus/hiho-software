"""HIHO MOCAP — shared bone topology data, lifted 1:1 from ajc27.

The bone head/tail mapping is used by:
- build_rig.measure_bone_lengths (to compute per-bone median length)
- enforce_rigid_bodies (to clamp per-frame lengths to median)

Lifted verbatim from
ajc27/data_models/bones/bone_definitions.py (head + tail fields per bone).

Pure data, no Blender or numpy dependencies — safe to import from anywhere.
"""

from typing import Dict, Tuple


def _finger_chain_bone_to_empties(side: str) -> Dict[str, Tuple[str, str]]:
    """Per-side finger bone head/tail mapping. Side is 'R' or 'L'.

    Each finger chain attaches to the hand wrist (or a parent palm bone) and
    walks distal landmark by distal landmark out to the fingertip.
    """
    prefix = "right_hand" if side == "R" else "left_hand"
    return {
        f"thumb.carpal.{side}": (f"{prefix}_wrist",              f"{prefix}_thumb_cmc"),
        f"thumb.01.{side}":     (f"{prefix}_thumb_cmc",          f"{prefix}_thumb_mcp"),
        f"thumb.02.{side}":     (f"{prefix}_thumb_mcp",          f"{prefix}_thumb_ip"),
        f"thumb.03.{side}":     (f"{prefix}_thumb_ip",           f"{prefix}_thumb_tip"),
        f"palm.01.{side}":      (f"{prefix}_wrist",              f"{prefix}_index_finger_mcp"),
        f"f_index.01.{side}":   (f"{prefix}_index_finger_mcp",   f"{prefix}_index_finger_pip"),
        f"f_index.02.{side}":   (f"{prefix}_index_finger_pip",   f"{prefix}_index_finger_dip"),
        f"f_index.03.{side}":   (f"{prefix}_index_finger_dip",   f"{prefix}_index_finger_tip"),
        f"palm.02.{side}":      (f"{prefix}_wrist",              f"{prefix}_middle_finger_mcp"),
        f"f_middle.01.{side}":  (f"{prefix}_middle_finger_mcp",  f"{prefix}_middle_finger_pip"),
        f"f_middle.02.{side}":  (f"{prefix}_middle_finger_pip",  f"{prefix}_middle_finger_dip"),
        f"f_middle.03.{side}":  (f"{prefix}_middle_finger_dip",  f"{prefix}_middle_finger_tip"),
        f"palm.03.{side}":      (f"{prefix}_wrist",              f"{prefix}_ring_finger_mcp"),
        f"f_ring.01.{side}":    (f"{prefix}_ring_finger_mcp",    f"{prefix}_ring_finger_pip"),
        f"f_ring.02.{side}":    (f"{prefix}_ring_finger_pip",    f"{prefix}_ring_finger_dip"),
        f"f_ring.03.{side}":    (f"{prefix}_ring_finger_dip",    f"{prefix}_ring_finger_tip"),
        f"palm.04.{side}":      (f"{prefix}_wrist",              f"{prefix}_pinky_mcp"),
        f"f_pinky.01.{side}":   (f"{prefix}_pinky_mcp",          f"{prefix}_pinky_pip"),
        f"f_pinky.02.{side}":   (f"{prefix}_pinky_pip",          f"{prefix}_pinky_dip"),
        f"f_pinky.03.{side}":   (f"{prefix}_pinky_dip",          f"{prefix}_pinky_tip"),
    }


# Bone-name → (head_landmark, tail_landmark). Bone length is the median
# per-frame distance between head and tail landmark positions. Lifted from
# ajc27 bone_definitions.py — names are bare (no `hiho_` prefix), they're
# keys into the in-memory trajectory dict (positions[name] → (frames, 3)).
BONE_HEAD_TAIL_MAP: Dict[str, Tuple[str, str]] = {
    "pelvis.R":    ("hips_center", "right_hip"),
    "pelvis.L":    ("hips_center", "left_hip"),
    "spine":       ("hips_center", "trunk_center"),
    "spine.001":   ("trunk_center", "neck_center"),
    "neck":        ("neck_center", "head_center"),
    "face":        ("head_center", "nose"),
    "shoulder.R":  ("neck_center", "right_shoulder"),
    "shoulder.L":  ("neck_center", "left_shoulder"),
    "upper_arm.R": ("right_shoulder", "right_elbow"),
    "upper_arm.L": ("left_shoulder", "left_elbow"),
    "forearm.R":   ("right_elbow", "right_wrist"),
    "forearm.L":   ("left_elbow", "left_wrist"),
    "hand.R":      ("right_wrist", "right_hand_middle"),
    "hand.L":      ("left_wrist", "left_hand_middle"),
    **_finger_chain_bone_to_empties("R"),
    **_finger_chain_bone_to_empties("L"),
    "thigh.R":     ("right_hip", "right_knee"),
    "thigh.L":     ("left_hip", "left_knee"),
    "shin.R":      ("right_knee", "right_ankle"),
    "shin.L":      ("left_knee", "left_ankle"),
    "foot.R":      ("right_ankle", "right_foot_index"),
    "foot.L":      ("left_ankle", "left_foot_index"),
    "heel.02.R":   ("right_ankle", "right_heel"),
    "heel.02.L":   ("left_ankle", "left_heel"),
}
