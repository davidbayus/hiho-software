"""HIHO MOCAP — build a FreeMoCap-style armature from the captured empties.

1:1 with ajc27_freemocap_blender_addon's BY_BONE path. We replicate ajc27's
full 63-bone topology (15 body + 8 leg + 40 finger) + T-pose orientation +
bone-length measurement so the rig matches what FreeMoCap exports.

Bone-length measurement: median of per-frame distance between the head and
tail source empties. Robust to NaN / dropped frames.

Topology + T-pose values lifted verbatim from:
- ajc27/data_models/armatures/freemocap_armature_definition.py
- ajc27/data_models/poses/freemocap_tpose.py
- ajc27/data_models/bones/bone_definitions.py (head/tail mapping)

See HAND_BONES_DESIGN.md for the full cross-reference + scope notes.
"""

import math
from typing import Dict, Optional, Tuple

import bpy
import mathutils
import numpy as np

from .loader import load_aligned_data
from .topology import BONE_HEAD_TAIL_MAP


# ---- ajc27 topology ---------------------------------------------------------
# Field order matches insertion order — parent bones must come before children
# so edit_bones.new() can resolve the parent reference at creation time.

def _finger_chain_armature(side: str) -> Dict[str, Dict]:
    """Per-side finger bone armature entries. Side is 'R' or 'L'.

    Branching pattern: hand → {thumb.carpal, palm.01, palm.02, palm.03, palm.04}
    each anchored at hand's head (not tail), then 3 distal phalanges connected
    in sequence. Verbatim from ajc27 freemocap_armature_definition.py.
    """
    return {
        f"thumb.carpal.{side}": {"parent": f"hand.{side}",       "connected": False, "parent_position": "head"},
        f"thumb.01.{side}":     {"parent": f"thumb.carpal.{side}","connected": True,  "parent_position": "tail"},
        f"thumb.02.{side}":     {"parent": f"thumb.01.{side}",   "connected": True,  "parent_position": "tail"},
        f"thumb.03.{side}":     {"parent": f"thumb.02.{side}",   "connected": True,  "parent_position": "tail"},
        f"palm.01.{side}":      {"parent": f"hand.{side}",       "connected": False, "parent_position": "head"},
        f"f_index.01.{side}":   {"parent": f"palm.01.{side}",    "connected": True,  "parent_position": "tail"},
        f"f_index.02.{side}":   {"parent": f"f_index.01.{side}", "connected": True,  "parent_position": "tail"},
        f"f_index.03.{side}":   {"parent": f"f_index.02.{side}", "connected": True,  "parent_position": "tail"},
        f"palm.02.{side}":      {"parent": f"hand.{side}",       "connected": False, "parent_position": "head"},
        f"f_middle.01.{side}":  {"parent": f"palm.02.{side}",    "connected": True,  "parent_position": "tail"},
        f"f_middle.02.{side}":  {"parent": f"f_middle.01.{side}","connected": True,  "parent_position": "tail"},
        f"f_middle.03.{side}":  {"parent": f"f_middle.02.{side}","connected": True,  "parent_position": "tail"},
        f"palm.03.{side}":      {"parent": f"hand.{side}",       "connected": False, "parent_position": "head"},
        f"f_ring.01.{side}":    {"parent": f"palm.03.{side}",    "connected": True,  "parent_position": "tail"},
        f"f_ring.02.{side}":    {"parent": f"f_ring.01.{side}",  "connected": True,  "parent_position": "tail"},
        f"f_ring.03.{side}":    {"parent": f"f_ring.02.{side}",  "connected": True,  "parent_position": "tail"},
        f"palm.04.{side}":      {"parent": f"hand.{side}",       "connected": False, "parent_position": "head"},
        f"f_pinky.01.{side}":   {"parent": f"palm.04.{side}",    "connected": True,  "parent_position": "tail"},
        f"f_pinky.02.{side}":   {"parent": f"f_pinky.01.{side}", "connected": True,  "parent_position": "tail"},
        f"f_pinky.03.{side}":   {"parent": f"f_pinky.02.{side}", "connected": True,  "parent_position": "tail"},
    }


_ARMATURE_DEFINITION: Dict[str, Dict] = {
    "pelvis":      {"parent": None,         "connected": False, "parent_position": "head", "default_length": 0.05},
    "pelvis.R":    {"parent": "pelvis",     "connected": False, "parent_position": "head"},
    "pelvis.L":    {"parent": "pelvis",     "connected": False, "parent_position": "head"},
    "spine":       {"parent": "pelvis",     "connected": False, "parent_position": "head"},
    "spine.001":   {"parent": "spine",      "connected": True,  "parent_position": "tail"},
    "neck":        {"parent": "spine.001",  "connected": True,  "parent_position": "tail"},
    "face":        {"parent": "neck",       "connected": True,  "parent_position": "tail", "default_length": 0.1},
    "shoulder.R":  {"parent": "spine.001",  "connected": False, "parent_position": "tail"},
    "shoulder.L":  {"parent": "spine.001",  "connected": False, "parent_position": "tail"},
    "upper_arm.R": {"parent": "shoulder.R", "connected": True,  "parent_position": "tail"},
    "upper_arm.L": {"parent": "shoulder.L", "connected": True,  "parent_position": "tail"},
    "forearm.R":   {"parent": "upper_arm.R","connected": True,  "parent_position": "tail"},
    "forearm.L":   {"parent": "upper_arm.L","connected": True,  "parent_position": "tail"},
    "hand.R":      {"parent": "forearm.R",  "connected": True,  "parent_position": "tail"},
    "hand.L":      {"parent": "forearm.L",  "connected": True,  "parent_position": "tail"},
    **_finger_chain_armature("R"),
    **_finger_chain_armature("L"),
    "thigh.R":     {"parent": "pelvis.R",   "connected": True,  "parent_position": "tail"},
    "thigh.L":     {"parent": "pelvis.L",   "connected": True,  "parent_position": "tail"},
    "shin.R":      {"parent": "thigh.R",    "connected": True,  "parent_position": "tail"},
    "shin.L":      {"parent": "thigh.L",    "connected": True,  "parent_position": "tail"},
    "foot.R":      {"parent": "shin.R",     "connected": True,  "parent_position": "tail"},
    "foot.L":      {"parent": "shin.L",     "connected": True,  "parent_position": "tail"},
    "heel.02.R":   {"parent": "shin.R",     "connected": False, "parent_position": "tail"},
    "heel.02.L":   {"parent": "shin.L",     "connected": False, "parent_position": "tail"},
}


# Bone head/tail mapping lives in core/topology.py — shared with
# enforce_rigid_bodies so both paths see the same definitions.
_BONE_TO_EMPTIES = BONE_HEAD_TAIL_MAP


def _finger_chain_tpose(side: str) -> Dict[str, Tuple[Tuple[float, float, float], float]]:
    """Per-side finger T-pose rotations. Side is 'R' or 'L'.

    All finger bones rotate ±90° around Y to align with the arm direction.
    Palm bones add a small Z offset so the fingers fan out naturally in
    T-pose; thumb bones add a 45° Z rotation for thumb opposition. Verbatim
    from ajc27 freemocap_tpose.py.
    """
    y = math.radians(-90 if side == "R" else 90)
    z_sign = 1 if side == "R" else -1
    thumb_z = math.radians(45 * z_sign)
    palm1_z = math.radians(17 * z_sign)
    palm2_z = math.radians(5.5 * z_sign)
    palm3_z = math.radians(-7.3 * z_sign)
    palm4_z = math.radians(-19 * z_sign)
    return {
        f"thumb.carpal.{side}": ((0, y, thumb_z), 0.0),
        f"thumb.01.{side}":     ((0, y, thumb_z), 0.0),
        f"thumb.02.{side}":     ((0, y, thumb_z), 0.0),
        f"thumb.03.{side}":     ((0, y, thumb_z), 0.0),
        f"palm.01.{side}":      ((0, y, palm1_z), 0.0),
        f"f_index.01.{side}":   ((0, y, 0), 0.0),
        f"f_index.02.{side}":   ((0, y, 0), 0.0),
        f"f_index.03.{side}":   ((0, y, 0), 0.0),
        f"palm.02.{side}":      ((0, y, palm2_z), 0.0),
        f"f_middle.01.{side}":  ((0, y, 0), 0.0),
        f"f_middle.02.{side}":  ((0, y, 0), 0.0),
        f"f_middle.03.{side}":  ((0, y, 0), 0.0),
        f"palm.03.{side}":      ((0, y, palm3_z), 0.0),
        f"f_ring.01.{side}":    ((0, y, 0), 0.0),
        f"f_ring.02.{side}":    ((0, y, 0), 0.0),
        f"f_ring.03.{side}":    ((0, y, 0), 0.0),
        f"palm.04.{side}":      ((0, y, palm4_z), 0.0),
        f"f_pinky.01.{side}":   ((0, y, 0), 0.0),
        f"f_pinky.02.{side}":   ((0, y, 0), 0.0),
        f"f_pinky.03.{side}":   ((0, y, 0), 0.0),
    }


# T-pose rotation (Euler XYZ radians) + roll per bone. Verbatim from ajc27.
_TPOSE: Dict[str, Tuple[Tuple[float, float, float], float]] = {
    "pelvis":      ((math.radians(-90), 0, 0), 0.0),
    "pelvis.R":    ((0, math.radians(-90), 0), 0.0),
    "pelvis.L":    ((0, math.radians(90), 0), 0.0),
    "spine":       ((0, 0, 0), 0.0),
    "spine.001":   ((0, 0, 0), 0.0),
    "neck":        ((0, 0, 0), 0.0),
    "face":        ((math.radians(110), 0, 0), 0.0),
    "shoulder.R":  ((0, math.radians(-90), 0), 0.0),
    "shoulder.L":  ((0, math.radians(90), 0), 0.0),
    "upper_arm.R": ((0, math.radians(-90), 0), math.radians(-90)),
    "upper_arm.L": ((0, math.radians(90), 0), math.radians(90)),
    "forearm.R":   ((0, math.radians(-90), math.radians(1)), math.radians(-90)),
    "forearm.L":   ((0, math.radians(90), math.radians(-1)), math.radians(90)),
    "hand.R":      ((0, math.radians(-90), 0), math.radians(-90)),
    "hand.L":      ((0, math.radians(90), 0), math.radians(90)),
    **_finger_chain_tpose("R"),
    **_finger_chain_tpose("L"),
    "thigh.R":     ((math.radians(1), math.radians(180), 0), 0.0),
    "thigh.L":     ((math.radians(1), math.radians(180), 0), 0.0),
    "shin.R":      ((math.radians(-1), math.radians(180), 0), 0.0),
    "shin.L":      ((math.radians(-1), math.radians(180), 0), 0.0),
    "foot.R":      ((math.radians(113), 0, 0), 0.0),
    "foot.L":      ((math.radians(113), 0, 0), 0.0),
    "heel.02.R":   ((math.radians(195), 0, 0), 0.0),
    "heel.02.L":   ((math.radians(195), 0, 0), 0.0),
}


# ---- Public API -------------------------------------------------------------

def measure_bone_lengths(recording_folder: str) -> Dict[str, float]:
    """Median bone length (meters) per bone.

    Reads the unified positions dict from load_aligned_data — already aligned,
    fix_hand_data'd, and (since enforce_rigid_bodies is wired in) clamped to
    per-bone medians. After enforce, every frame's length equals the median
    so this is technically redundant for the post-enforce pass — but it's
    still the function build_freemocap_armature uses to set rest-pose bone
    lengths.
    """
    data = load_aligned_data(recording_folder)
    positions = data["positions"]

    lengths: Dict[str, float] = {}
    for bone, (head_name, tail_name) in _BONE_TO_EMPTIES.items():
        head_traj = positions.get(head_name)
        tail_traj = positions.get(tail_name)
        if head_traj is None or tail_traj is None:
            continue
        dists = np.linalg.norm(head_traj - tail_traj, axis=1)
        valid = dists[~np.isnan(dists)]
        if len(valid) > 0:
            lengths[bone] = float(np.median(valid))
    return lengths


def build_freemocap_armature(
    recording_folder: str,
    rig_name: str,
    parent_object: Optional[bpy.types.Object] = None,
) -> bpy.types.Object:
    """Build a freemocap-style armature in canonical T-pose at world origin.

    Bone lengths measured from the recording. Returns the rig object.
    If parent_object is given, the rig is parented to it (typically the
    HIHO_MOCAP_Skelly empty so the rig + mocap empties move as a unit).
    """
    bone_lengths = measure_bone_lengths(recording_folder)

    # Pelvis sits at standing height = avg foot projection + avg shin + avg thigh,
    # using a 23° foot-declination assumption (ajc27 convention).
    avg_ankle_proj = math.sin(math.radians(23)) * (
        bone_lengths.get("foot.R", 0.2) + bone_lengths.get("foot.L", 0.2)
    ) / 2.0
    avg_shin = (bone_lengths.get("shin.R", 0.4) + bone_lengths.get("shin.L", 0.4)) / 2.0
    avg_thigh = (bone_lengths.get("thigh.R", 0.4) + bone_lengths.get("thigh.L", 0.4)) / 2.0
    pelvis_z = avg_ankle_proj + avg_shin + avg_thigh

    bpy.ops.object.armature_add(enter_editmode=False, align="WORLD", location=(0, 0, 0))
    rig = bpy.context.active_object
    rig.name = rig_name
    rig.data.name = f"{rig_name}_data"

    bpy.ops.object.mode_set(mode="EDIT")

    # Remove the default bone Blender creates with armature_add.
    for default in list(rig.data.edit_bones):
        rig.data.edit_bones.remove(default)

    for bone_name, info in _ARMATURE_DEFINITION.items():
        edit_bone = rig.data.edit_bones.new(bone_name)

        if bone_name == "pelvis":
            edit_bone.head = mathutils.Vector((0.0, 0.0, pelvis_z))
        else:
            parent_eb = rig.data.edit_bones[info["parent"]]
            edit_bone.head = (
                parent_eb.head if info["parent_position"] == "head" else parent_eb.tail
            )

        length = bone_lengths.get(bone_name, info.get("default_length", 0.05))
        bone_vector = mathutils.Vector((0.0, 0.0, length))
        rotation, roll = _TPOSE[bone_name]
        rot_matrix = mathutils.Euler(rotation, "XYZ").to_matrix()
        edit_bone.tail = edit_bone.head + rot_matrix @ bone_vector
        edit_bone.roll = roll

        if info["parent"] is not None:
            edit_bone.parent = rig.data.edit_bones[info["parent"]]
            edit_bone.use_connect = info["connected"]

    bpy.ops.object.mode_set(mode="OBJECT")

    if parent_object is not None:
        rig.parent = parent_object

    return rig
