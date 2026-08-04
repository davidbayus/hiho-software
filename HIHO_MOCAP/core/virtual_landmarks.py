"""HIHO MOCAP — spawn virtual-landmark empties under the Skelly root.

The virtual landmarks themselves (head_center, neck_center, trunk_center,
hips_center, right_hand_middle, left_hand_middle) are computed inside
loader.load_aligned_data so that enforce_rigid_bodies can operate on them
along with the rest of the positions dict. This module just spawns the
keyframed Empty objects from those precomputed trajectories.

Same slotted-actions keyframe recipe as output_rig.py (Blender 4.4+ API).
"""

from typing import List

import bpy
import numpy as np

from .bind_to_rig import strip_dup_suffix
from .loader import VIRTUAL_LANDMARK_NAMES, fill_untracked_frames, load_aligned_data
from .output_rig import EMPTY_SCALE


def ensure_virtual_empties(
    recording_folder: str,
    skelly_root: bpy.types.Object,
) -> List[str]:
    """Spawn the 6 virtual-landmark empties if they don't already exist.

    Idempotent — if all 6 are present under skelly_root, returns [] and
    does no work. Returns the names of the empties that were newly created.
    """
    # Suffix-tolerant: a second take's empties are auto-renamed 'hiho_*.001',
    # which made this check miss forever and re-create 6 empties per click.
    existing = {
        strip_dup_suffix(child.name)
        for child in skelly_root.children_recursive
        if child.type == 'EMPTY'
    }
    missing = [vname for vname in VIRTUAL_LANDMARK_NAMES if f"hiho_{vname}" not in existing]
    if not missing:
        return []

    data = load_aligned_data(recording_folder)
    virtuals = data["virtuals"]

    created = []
    untracked = []
    for vname in missing:
        traj = fill_untracked_frames(virtuals[vname])
        if traj is None:
            untracked.append(vname)
        empty = _create_keyframed_virtual_empty(
            name=f"hiho_{vname}",
            traj_fr_xyz=traj,
            parent=skelly_root,
        )
        created.append(empty.name)
    if untracked:
        prior = skelly_root.get("hiho_untracked", "")
        skelly_root["hiho_untracked"] = ", ".join(
            ([prior] if prior else []) + untracked
        )
    return created


def _create_keyframed_virtual_empty(
    name: str,
    traj_fr_xyz,
    parent: bpy.types.Object,
) -> bpy.types.Object:
    """Same slotted-actions recipe as output_rig._create_keyframed_empty,
    but with a smaller display size and a distinct PLAIN_AXES shape so
    students can tell virtual midpoints apart from the 33 body sphere empties."""
    empty = bpy.data.objects.new(name, None)
    empty.empty_display_type = 'PLAIN_AXES'
    empty.empty_display_size = EMPTY_SCALE * 0.7
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
