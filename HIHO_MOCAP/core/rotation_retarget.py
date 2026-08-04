"""HIHO MOCAP — rotation-copy retarget from the skelly rig to a character rig.

Why rotations, not the empty-targeting constraint stack: aiming a character's
bones at position targets only works when the skeleton was BUILT at the
performer's measured proportions (ajc27's rig is; auto-rigged characters are
built at the CHARACTER's proportions). On a chibi, hip-matched uniform scale
leaves the head target above the crown and the ankle targets below the shoes,
so chains fold reaching for them — David's 2026-07-01 head-collapse /
foot-crumple find. World-space COPY_ROTATION from the (correctly playing)
skelly rig gives every character bone the performer's orientation while the
character keeps its own proportions. Pelvis additionally copies world
location so the character travels. The skelly rig's own ajc27 constraint
recipe is untouched.
"""

from typing import List, Tuple

import bpy

PELVIS_BONE = "pelvis"


def apply_rotation_retarget(char_rig: bpy.types.Object,
                            skelly_rig: bpy.types.Object) -> Tuple[List[str], List[str]]:
    """Add HIHO_-prefixed constraints driving char_rig from skelly_rig.

    Returns (bound bone names, skipped bone names). Caller clears prior
    HIHO_ constraints first (core.bind_to_rig.clear_hiho_constraints).
    """
    skelly_bones = {b.name for b in skelly_rig.data.bones}
    bound: List[str] = []
    skipped: List[str] = []

    for pose_bone in char_rig.pose.bones:
        if pose_bone.name not in skelly_bones:
            skipped.append(pose_bone.name)
            continue
        rot = pose_bone.constraints.new('COPY_ROTATION')
        rot.name = "HIHO_CopyRot"
        rot.target = skelly_rig
        rot.subtarget = pose_bone.name
        rot.target_space = 'WORLD'
        rot.owner_space = 'WORLD'
        if pose_bone.name == PELVIS_BONE:
            loc = pose_bone.constraints.new('COPY_LOCATION')
            loc.name = "HIHO_CopyLoc"
            loc.target = skelly_rig
            loc.subtarget = PELVIS_BONE
            loc.target_space = 'WORLD'
            loc.owner_space = 'WORLD'
        bound.append(pose_bone.name)

    return bound, skipped
