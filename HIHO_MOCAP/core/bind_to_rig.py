"""HIHO MOCAP — apply ajc27's constraint stack to a freemocap-style armature.

Pins each pose bone to one or two captured-motion empties via Copy
Location / Damped Track / Locked Track. The constraint table is verbatim
from ajc27_freemocap_blender_addon's bone_constraints.py — full body
bones + all finger bones (MediaPipe Holistic hand data is available).

Bone names match ajc27's freemocap armature exactly (`pelvis`, `spine`,
`spine.001`, `neck`, `face`, `thumb.01.R`, `f_index.02.L`, ...) — these
are the bones built by build_rig.py, not Rigify metarig names.

Constraints stay live (not baked) so students can adjust influence per
bone. Each HIHO-applied constraint is prefixed `HIHO_` so a clean
re-bind only wipes our work.
"""

from math import radians
from typing import Dict, List, Optional, Tuple

import bpy


def _finger_chain_constraints(side: str) -> Dict[str, List[Tuple[str, str, Dict]]]:
    """Per-side finger bone constraints. Side is 'R' or 'L'.

    Each finger bone gets a single DAMPED_TRACK pointing TRACK_Y toward
    the next landmark in chain. Verbatim from ajc27 bone_constraints.py.
    """
    prefix = "right_hand" if side == "R" else "left_hand"
    track_y = {"track_axis": "TRACK_Y"}
    return {
        f"thumb.carpal.{side}": [("DAMPED_TRACK", f"{prefix}_thumb_cmc", track_y)],
        f"thumb.01.{side}":     [("DAMPED_TRACK", f"{prefix}_thumb_mcp", track_y)],
        f"thumb.02.{side}":     [("DAMPED_TRACK", f"{prefix}_thumb_ip", track_y)],
        f"thumb.03.{side}":     [("DAMPED_TRACK", f"{prefix}_thumb_tip", track_y)],
        f"palm.01.{side}":      [("DAMPED_TRACK", f"{prefix}_index_finger_mcp", track_y)],
        f"f_index.01.{side}":   [("DAMPED_TRACK", f"{prefix}_index_finger_pip", track_y)],
        f"f_index.02.{side}":   [("DAMPED_TRACK", f"{prefix}_index_finger_dip", track_y)],
        f"f_index.03.{side}":   [("DAMPED_TRACK", f"{prefix}_index_finger_tip", track_y)],
        f"palm.02.{side}":      [("DAMPED_TRACK", f"{prefix}_middle_finger_mcp", track_y)],
        f"f_middle.01.{side}":  [("DAMPED_TRACK", f"{prefix}_middle_finger_pip", track_y)],
        f"f_middle.02.{side}":  [("DAMPED_TRACK", f"{prefix}_middle_finger_dip", track_y)],
        f"f_middle.03.{side}":  [("DAMPED_TRACK", f"{prefix}_middle_finger_tip", track_y)],
        f"palm.03.{side}":      [("DAMPED_TRACK", f"{prefix}_ring_finger_mcp", track_y)],
        f"f_ring.01.{side}":    [("DAMPED_TRACK", f"{prefix}_ring_finger_pip", track_y)],
        f"f_ring.02.{side}":    [("DAMPED_TRACK", f"{prefix}_ring_finger_dip", track_y)],
        f"f_ring.03.{side}":    [("DAMPED_TRACK", f"{prefix}_ring_finger_tip", track_y)],
        f"palm.04.{side}":      [("DAMPED_TRACK", f"{prefix}_pinky_mcp", track_y)],
        f"f_pinky.01.{side}":   [("DAMPED_TRACK", f"{prefix}_pinky_pip", track_y)],
        f"f_pinky.02.{side}":   [("DAMPED_TRACK", f"{prefix}_pinky_dip", track_y)],
        f"f_pinky.03.{side}":   [("DAMPED_TRACK", f"{prefix}_pinky_tip", track_y)],
    }


# ajc27's hand rotation limits (degrees, local space). ajc27 gates these behind
# an opt-in flag (use_limit_rotation, default off), so a 1:1 port left them off
# and the hand could roll-flip 180 degrees when the LOCKED_TRACK toward the thumb
# crossed its plane. Applying them clamps the roll so the flip can't happen.
# Values verbatim from ajc27 bone_constraints.py.
_HAND_ROT_LIMIT = {
    "use_limit_x": True, "min_x": -45, "max_x": 45,
    "use_limit_y": True, "min_y": -36, "max_y": 25,
    "use_limit_z": True, "min_z": -86, "max_z": 90,
    "owner_space": "LOCAL",
}


# Substring-matched against `hiho_<name>` empties under the skelly root.
# Same approach as ajc27 (apply_bone_constraints.py line ~102).
_CONSTRAINTS: Dict[str, List[Tuple[str, Optional[str], Dict]]] = {
    "pelvis": [
        ("COPY_LOCATION", "hips_center", {}),
        ("LOCKED_TRACK", "right_hip", {"track_axis": "TRACK_NEGATIVE_X", "lock_axis": "LOCK_Z"}),
        ("LOCKED_TRACK", "right_hip", {"track_axis": "TRACK_NEGATIVE_X", "lock_axis": "LOCK_Y"}),
        ("LOCKED_TRACK", "trunk_center", {"track_axis": "TRACK_Z", "lock_axis": "LOCK_X"}),
    ],
    "pelvis.R": [("DAMPED_TRACK", "right_hip", {"track_axis": "TRACK_Y"})],
    "pelvis.L": [("DAMPED_TRACK", "left_hip", {"track_axis": "TRACK_Y"})],
    "spine": [
        ("COPY_LOCATION", "hips_center", {}),
        ("DAMPED_TRACK", "trunk_center", {"track_axis": "TRACK_Y"}),
    ],
    "spine.001": [
        ("DAMPED_TRACK", "neck_center", {"track_axis": "TRACK_Y"}),
        ("LOCKED_TRACK", "right_shoulder", {"track_axis": "TRACK_NEGATIVE_X", "lock_axis": "LOCK_Y"}),
    ],
    "neck": [
        ("DAMPED_TRACK", "head_center", {"track_axis": "TRACK_Y"}),
        ("LOCKED_TRACK", "nose", {"track_axis": "TRACK_Z", "lock_axis": "LOCK_Y"}),
    ],
    "face": [("DAMPED_TRACK", "nose", {"track_axis": "TRACK_Y"})],
    "shoulder.R": [
        ("COPY_LOCATION", "neck_center", {}),
        ("DAMPED_TRACK", "right_shoulder", {"track_axis": "TRACK_Y"}),
    ],
    "shoulder.L": [
        ("COPY_LOCATION", "neck_center", {}),
        ("DAMPED_TRACK", "left_shoulder", {"track_axis": "TRACK_Y"}),
    ],
    "upper_arm.R": [("DAMPED_TRACK", "right_elbow", {"track_axis": "TRACK_Y"})],
    "upper_arm.L": [("DAMPED_TRACK", "left_elbow", {"track_axis": "TRACK_Y"})],
    "forearm.R": [("DAMPED_TRACK", "right_wrist", {"track_axis": "TRACK_Y"})],
    "forearm.L": [("DAMPED_TRACK", "left_wrist", {"track_axis": "TRACK_Y"})],
    "hand.R": [
        ("DAMPED_TRACK", "right_hand_middle", {"track_axis": "TRACK_Y"}),
        ("LOCKED_TRACK", "right_hand_thumb_cmc", {"track_axis": "TRACK_Z", "lock_axis": "LOCK_Y"}),
        ("LIMIT_ROTATION", None, _HAND_ROT_LIMIT),  # clamps the 180-degree wrist flip
    ],
    "hand.L": [
        ("DAMPED_TRACK", "left_hand_middle", {"track_axis": "TRACK_Y"}),
        ("LOCKED_TRACK", "left_hand_thumb_cmc", {"track_axis": "TRACK_Z", "lock_axis": "LOCK_Y"}),
        ("LIMIT_ROTATION", None, _HAND_ROT_LIMIT),  # clamps the 180-degree wrist flip
    ],
    "thigh.R": [
        ("COPY_LOCATION", "right_hip", {}),
        ("DAMPED_TRACK", "right_knee", {"track_axis": "TRACK_Y"}),
    ],
    "thigh.L": [
        ("COPY_LOCATION", "left_hip", {}),
        ("DAMPED_TRACK", "left_knee", {"track_axis": "TRACK_Y"}),
    ],
    "shin.R": [("DAMPED_TRACK", "right_ankle", {"track_axis": "TRACK_Y"})],
    "shin.L": [("DAMPED_TRACK", "left_ankle", {"track_axis": "TRACK_Y"})],
    "foot.R": [("DAMPED_TRACK", "right_foot_index", {"track_axis": "TRACK_Y"})],
    "foot.L": [("DAMPED_TRACK", "left_foot_index", {"track_axis": "TRACK_Y"})],
    "heel.02.R": [("DAMPED_TRACK", "right_heel", {"track_axis": "TRACK_Y"})],
    "heel.02.L": [("DAMPED_TRACK", "left_heel", {"track_axis": "TRACK_Y"})],
    **_finger_chain_constraints("R"),
    **_finger_chain_constraints("L"),
}


HIHO_CONSTRAINT_PREFIX = "HIHO_"


def strip_dup_suffix(name: str) -> str:
    """Strip Blender's '.001'-style duplicate suffix from a landmark EMPTY name.

    Blender object names are globally unique, so a second take's empties arrive
    as e.g. 'hiho_right_wrist.001'. Landmark names never contain dots, so the
    strip is safe here. Do NOT use on bone names — 'spine.001' is a real,
    canonical bone name.
    """
    base, dot, suffix = name.rpartition(".")
    if dot and suffix.isdigit():
        return base
    return name


def clear_hiho_constraints(rig: bpy.types.Object) -> int:
    """Remove every HIHO_-prefixed constraint from every pose bone. Returns the count."""
    removed = 0
    for pose_bone in rig.pose.bones:
        to_remove = [c for c in pose_bone.constraints if c.name.startswith(HIHO_CONSTRAINT_PREFIX)]
        for con in to_remove:
            pose_bone.constraints.remove(con)
            removed += 1
    return removed


def apply_constraints(
    rig: bpy.types.Object,
    skelly_root: bpy.types.Object,
) -> Tuple[List[str], List[str]]:
    """Apply the ajc27 constraint stack to the rig. Returns (bound, skipped)."""
    empties = _index_skelly_empties(skelly_root)

    bound: List[str] = []
    skipped: List[str] = []

    for bone_name, specs in _CONSTRAINTS.items():
        pose_bone = rig.pose.bones.get(bone_name)
        if pose_bone is None:
            skipped.append(bone_name)
            continue

        targeted_created = 0
        for idx, (ctype, target_substring, extras) in enumerate(specs):
            # LIMIT_ROTATION is targetless — apply it before the target lookup.
            if ctype == "LIMIT_ROTATION":
                con = pose_bone.constraints.new(ctype)
                con.name = f"{HIHO_CONSTRAINT_PREFIX}{idx}_{_short_type(ctype)}"
                con.use_limit_x = extras.get("use_limit_x", False)
                con.min_x = radians(extras.get("min_x", 0.0))
                con.max_x = radians(extras.get("max_x", 0.0))
                con.use_limit_y = extras.get("use_limit_y", False)
                con.min_y = radians(extras.get("min_y", 0.0))
                con.max_y = radians(extras.get("max_y", 0.0))
                con.use_limit_z = extras.get("use_limit_z", False)
                con.min_z = radians(extras.get("min_z", 0.0))
                con.max_z = radians(extras.get("max_z", 0.0))
                con.owner_space = extras.get("owner_space", "LOCAL")
                continue

            target_obj = empties.get(target_substring)
            if target_obj is None:
                continue

            con = pose_bone.constraints.new(ctype)
            con.name = f"{HIHO_CONSTRAINT_PREFIX}{idx}_{_short_type(ctype)}"
            con.target = target_obj

            if ctype == "DAMPED_TRACK":
                con.track_axis = extras["track_axis"]
            elif ctype == "LOCKED_TRACK":
                con.track_axis = extras["track_axis"]
                con.lock_axis = extras["lock_axis"]
                con.influence = extras.get("influence", 1.0)
            targeted_created += 1

        # Only count the bone as bound if a tracking constraint actually
        # landed — appending unconditionally reported "63 bones bound" even
        # when every target lookup had silently missed (the two-takes bug).
        if targeted_created:
            bound.append(bone_name)
        else:
            skipped.append(bone_name)

    return bound, skipped


def _index_skelly_empties(skelly_root: bpy.types.Object) -> Dict[str, bpy.types.Object]:
    table: Dict[str, bpy.types.Object] = {}
    for child in skelly_root.children_recursive:
        if child.type != 'EMPTY':
            continue
        if child.name.startswith("hiho_"):
            # Key by the canonical landmark name, tolerating Blender's '.001'
            # rename on a second take's empties. Scoped to ONE skelly root, so
            # stripping can't cross-match another take. First-wins on dupes.
            key = strip_dup_suffix(child.name[len("hiho_"):])
            table.setdefault(key, child)
    return table


_SHORT_TYPE = {
    "COPY_LOCATION": "CopyLoc",
    "DAMPED_TRACK": "DampedTrack",
    "LOCKED_TRACK": "LockedTrack",
    "LIMIT_ROTATION": "LimitRot",
}


def _short_type(ctype: str) -> str:
    return _SHORT_TYPE.get(ctype, ctype)
