"""PPParty V2 rig — bones-only humanoid armature.

The V2 rig is a 12-bone humanoid body + 38 hand bones (19 per hand,
4 metacarpals + 15 phalanges). There is no mesh during capture — just
bones — so the per-frame budget goes entirely to tracking math, not
geometry re-eval. Mesh attaches post-bake.

Body bone hierarchy (parent -> child):

    pelvis
    |-- chest
    |   |-- neck
    |   |   `-- head
    |   |-- shoulder.L
    |   |   `-- upper_arm.L
    |   |       `-- lower_arm.L  <- wrist; palm bones parent from here
    |   `-- shoulder.R
    |       `-- upper_arm.R
    |           `-- lower_arm.R  <- wrist; palm bones parent from here
    |-- upper_leg.L
    |   `-- lower_leg.L
    |       `-- foot.L
    |           `-- toe.L
    `-- upper_leg.R
        `-- lower_leg.R
            `-- foot.R
                `-- toe.R

Hand chains (one set per side, .L = puppet-left, .R = puppet-right).
Structure follows Blender's Rigify convention: 4 metacarpal "palm"
bones bridge wrist → MCP knuckle, and finger phalanges parent off
their respective palm. This makes fingers pivot at the MCP (anatomy)
rather than the wrist.

    lower_arm.L
    |-- palm.01.L   (wrist → index MCP)
    |   |-- thumb.01.L   (cmc → mcp; thumb sits on palm.01 by Rigify convention)
    |   |   |-- thumb.02.L  (mcp → ip)
    |   |   `-- thumb.03.L  (ip → tip)
    |   |-- f_index.01.L  (mcp → pip)
    |   |   |-- f_index.02.L  (pip → dip)
    |   |   `-- f_index.03.L  (dip → tip)
    |-- palm.02.L   (wrist → middle MCP)
    |   `-- f_middle.01.L → ... → f_middle.03.L
    |-- palm.03.L   (wrist → ring MCP)
    |   `-- f_ring.01.L   → ... → f_ring.03.L
    `-- palm.04.L   (wrist → pinky MCP)
        `-- f_pinky.01.L  → ... → f_pinky.03.L

Mirror convention (same as body pass):
    MP "Left" hand  → puppet .R bones
    MP "Right" hand → puppet .L bones

Rest positions are in T-pose, scaled to roughly 1.75 m human height.
Phalanx + palm rest lengths are lifted from Blender's Rigify
metarig (anatomical adult-hand proportions). All numbers are in
Blender world units (meters).
"""

import bpy
from mathutils import Vector


RIG_OBJECT_NAME = "PP_V2_Rig"
ARMATURE_DATA_NAME = "PP_V2_Armature"


# Bone rest positions: name -> (head_xyz, tail_xyz) in meters.
# T-pose: feet on the ground (z=0), head top around z=1.75, arms out to the sides.
BONE_REST_POSITIONS = {
    "pelvis":      ((0.00, 0.00, 0.95), (0.00, 0.00, 1.20)),
    "chest":       ((0.00, 0.00, 1.20), (0.00, 0.00, 1.45)),
    "neck":        ((0.00, 0.00, 1.45), (0.00, 0.00, 1.55)),
    "head":        ((0.00, 0.00, 1.55), (0.00, 0.00, 1.75)),
    # Collarbones — bridge chest top to upper-arm root. Captures shrug.
    # Length 0.18m matches Rigify's metarig (0.175m).
    "shoulder.L":  ((0.00, 0.00, 1.45), (0.18, 0.00, 1.45)),
    "shoulder.R":  ((0.00, 0.00, 1.45), (-0.18, 0.00, 1.45)),
    "upper_arm.L": ((0.18, 0.00, 1.45), (0.45, 0.00, 1.45)),
    "lower_arm.L": ((0.45, 0.00, 1.45), (0.72, 0.00, 1.45)),
    "upper_arm.R": ((-0.18, 0.00, 1.45), (-0.45, 0.00, 1.45)),
    "lower_arm.R": ((-0.45, 0.00, 1.45), (-0.72, 0.00, 1.45)),
    "upper_leg.L": ((0.10, 0.00, 0.95), (0.10, 0.00, 0.50)),
    "lower_leg.L": ((0.10, 0.00, 0.50), (0.10, 0.00, 0.05)),
    "upper_leg.R": ((-0.10, 0.00, 0.95), (-0.10, 0.00, 0.50)),
    "lower_leg.R": ((-0.10, 0.00, 0.50), (-0.10, 0.00, 0.05)),
    # Foot — ankle to ball-of-foot, pointing forward (-Y) and slightly down.
    # Length 0.11m matches Rigify metarig (~0.13m) scaled to V2's smaller leg.
    "foot.L":      ((0.10, 0.00, 0.05), (0.10, -0.10, 0.00)),
    "foot.R":      ((-0.10, 0.00, 0.05), (-0.10, -0.10, 0.00)),
    # Toe — ball-of-foot to toe tip, continuing forward.
    "toe.L":       ((0.10, -0.10, 0.00), (0.10, -0.17, 0.00)),
    "toe.R":       ((-0.10, -0.10, 0.00), (-0.10, -0.17, 0.00)),
}

# Bone parenting: child name -> parent name. Pelvis is the root (no parent).
BONE_PARENTS = {
    "chest":       "pelvis",
    "neck":        "chest",
    "head":        "neck",
    "shoulder.L":  "chest",
    "shoulder.R":  "chest",
    "upper_arm.L": "shoulder.L",
    "lower_arm.L": "upper_arm.L",
    "upper_arm.R": "shoulder.R",
    "lower_arm.R": "upper_arm.R",
    "upper_leg.L": "pelvis",
    "lower_leg.L": "upper_leg.L",
    "upper_leg.R": "pelvis",
    "lower_leg.R": "upper_leg.R",
    "foot.L":      "lower_leg.L",
    "foot.R":      "lower_leg.R",
    "toe.L":       "foot.L",
    "toe.R":       "foot.R",
}

# ---------------------------------------------------------------------------
# Hand bones — 19 per hand (4 palms + 15 phalanges), 38 total.
#
# Wrist anchor points (= lower_arm.L/R tails in T-pose):
_WR_L = (0.72, 0.00, 1.45)
_WR_R = (-0.72, 0.00, 1.45)

# Rest positions are display-only — `apply_landmarks_to_rig` overrides
# every bone's rotation (and Y-scale, for hand bones) on each captured
# frame. Lengths are lifted from Blender's Rigify metarig so an
# unposed rig already shows anatomical proportions.
#
# Coordinate convention for the T-pose left hand:
#   • Hand extends in +X from the wrist (0.72, 0, 1.45).
#   • Y is the spread axis: -Y = thumb side, +Y = pinky side.
#   • Z stays at wrist height (1.45) until phalanges curl.
#
# Palm (metacarpal) rest lengths from Rigify (cm): 7.0 / 6.8 / 7.0 / 7.5.
# Phalanx rest lengths from Rigify, per finger:
#   index  4.5 / 2.8 / 2.3
#   middle 5.0 / 3.2 / 2.3
#   ring   4.5 / 3.2 / 1.9
#   pinky  2.8 / 2.3 / 1.5
#   thumb  4.2 / 3.3 / 2.1   (CMC→MCP / MCP→IP / IP→tip)
HAND_BONE_REST_POSITIONS = {
    # ---- Left hand (puppet-left = MP-Right) ----
    # Palms — 4 metacarpals branching from the wrist toward each MCP.
    "palm.01.L":     (_WR_L,                  (0.790, -0.005, 1.450)),  # index
    "palm.02.L":     (_WR_L,                  (0.790,  0.005, 1.450)),  # middle
    "palm.03.L":     (_WR_L,                  (0.790,  0.020, 1.450)),  # ring
    "palm.04.L":     (_WR_L,                  (0.795,  0.040, 1.450)),  # pinky

    # Thumb — head sits on the thumb side of the palm, not at the wrist
    # exactly (Rigify convention). Parented to palm.01.
    "thumb.01.L":    ((0.730, -0.025, 1.450), (0.760, -0.055, 1.450)),
    "thumb.02.L":    ((0.760, -0.055, 1.450), (0.783, -0.078, 1.450)),
    "thumb.03.L":    ((0.783, -0.078, 1.450), (0.798, -0.093, 1.450)),

    # Index — head at palm.01 tail (index MCP knuckle).
    "f_index.01.L":  ((0.790, -0.005, 1.450), (0.835, -0.005, 1.450)),
    "f_index.02.L":  ((0.835, -0.005, 1.450), (0.863, -0.005, 1.450)),
    "f_index.03.L":  ((0.863, -0.005, 1.450), (0.886, -0.005, 1.450)),

    # Middle — head at palm.02 tail.
    "f_middle.01.L": ((0.790,  0.005, 1.450), (0.840,  0.005, 1.450)),
    "f_middle.02.L": ((0.840,  0.005, 1.450), (0.872,  0.005, 1.450)),
    "f_middle.03.L": ((0.872,  0.005, 1.450), (0.895,  0.005, 1.450)),

    # Ring — head at palm.03 tail.
    "f_ring.01.L":   ((0.790,  0.020, 1.450), (0.835,  0.020, 1.450)),
    "f_ring.02.L":   ((0.835,  0.020, 1.450), (0.867,  0.020, 1.450)),
    "f_ring.03.L":   ((0.867,  0.020, 1.450), (0.886,  0.020, 1.450)),

    # Pinky — head at palm.04 tail.
    "f_pinky.01.L":  ((0.795,  0.040, 1.450), (0.823,  0.040, 1.450)),
    "f_pinky.02.L":  ((0.823,  0.040, 1.450), (0.846,  0.040, 1.450)),
    "f_pinky.03.L":  ((0.846,  0.040, 1.450), (0.861,  0.040, 1.450)),

    # ---- Right hand (puppet-right = MP-Left) — X-mirrored ----
    "palm.01.R":     (_WR_R,                   (-0.790, -0.005, 1.450)),
    "palm.02.R":     (_WR_R,                   (-0.790,  0.005, 1.450)),
    "palm.03.R":     (_WR_R,                   (-0.790,  0.020, 1.450)),
    "palm.04.R":     (_WR_R,                   (-0.795,  0.040, 1.450)),

    "thumb.01.R":    ((-0.730, -0.025, 1.450), (-0.760, -0.055, 1.450)),
    "thumb.02.R":    ((-0.760, -0.055, 1.450), (-0.783, -0.078, 1.450)),
    "thumb.03.R":    ((-0.783, -0.078, 1.450), (-0.798, -0.093, 1.450)),

    "f_index.01.R":  ((-0.790, -0.005, 1.450), (-0.835, -0.005, 1.450)),
    "f_index.02.R":  ((-0.835, -0.005, 1.450), (-0.863, -0.005, 1.450)),
    "f_index.03.R":  ((-0.863, -0.005, 1.450), (-0.886, -0.005, 1.450)),

    "f_middle.01.R": ((-0.790,  0.005, 1.450), (-0.840,  0.005, 1.450)),
    "f_middle.02.R": ((-0.840,  0.005, 1.450), (-0.872,  0.005, 1.450)),
    "f_middle.03.R": ((-0.872,  0.005, 1.450), (-0.895,  0.005, 1.450)),

    "f_ring.01.R":   ((-0.790,  0.020, 1.450), (-0.835,  0.020, 1.450)),
    "f_ring.02.R":   ((-0.835,  0.020, 1.450), (-0.867,  0.020, 1.450)),
    "f_ring.03.R":   ((-0.867,  0.020, 1.450), (-0.886,  0.020, 1.450)),

    "f_pinky.01.R":  ((-0.795,  0.040, 1.450), (-0.823,  0.040, 1.450)),
    "f_pinky.02.R":  ((-0.823,  0.040, 1.450), (-0.846,  0.040, 1.450)),
    "f_pinky.03.R":  ((-0.846,  0.040, 1.450), (-0.861,  0.040, 1.450)),
}

HAND_BONE_PARENTS = {
    # ---- Left hand ----
    # Palms parent to the wrist; fingers parent to their palm; thumb
    # sits on palm.01 (Rigify convention).
    "palm.01.L":     "lower_arm.L",
    "palm.02.L":     "lower_arm.L",
    "palm.03.L":     "lower_arm.L",
    "palm.04.L":     "lower_arm.L",

    "thumb.01.L":    "palm.01.L",
    "thumb.02.L":    "thumb.01.L",
    "thumb.03.L":    "thumb.02.L",

    "f_index.01.L":  "palm.01.L",
    "f_index.02.L":  "f_index.01.L",
    "f_index.03.L":  "f_index.02.L",

    "f_middle.01.L": "palm.02.L",
    "f_middle.02.L": "f_middle.01.L",
    "f_middle.03.L": "f_middle.02.L",

    "f_ring.01.L":   "palm.03.L",
    "f_ring.02.L":   "f_ring.01.L",
    "f_ring.03.L":   "f_ring.02.L",

    "f_pinky.01.L":  "palm.04.L",
    "f_pinky.02.L":  "f_pinky.01.L",
    "f_pinky.03.L":  "f_pinky.02.L",

    # ---- Right hand (mirror) ----
    "palm.01.R":     "lower_arm.R",
    "palm.02.R":     "lower_arm.R",
    "palm.03.R":     "lower_arm.R",
    "palm.04.R":     "lower_arm.R",

    "thumb.01.R":    "palm.01.R",
    "thumb.02.R":    "thumb.01.R",
    "thumb.03.R":    "thumb.02.R",

    "f_index.01.R":  "palm.01.R",
    "f_index.02.R":  "f_index.01.R",
    "f_index.03.R":  "f_index.02.R",

    "f_middle.01.R": "palm.02.R",
    "f_middle.02.R": "f_middle.01.R",
    "f_middle.03.R": "f_middle.02.R",

    "f_ring.01.R":   "palm.03.R",
    "f_ring.02.R":   "f_ring.01.R",
    "f_ring.03.R":   "f_ring.02.R",

    "f_pinky.01.R":  "palm.04.R",
    "f_pinky.02.R":  "f_pinky.01.R",
    "f_pinky.03.R":  "f_pinky.02.R",
}


def build_v2_rig(context: bpy.types.Context) -> bpy.types.Object:
    """Create (or rebuild) the PPParty V2 bones-only rig.

    If a rig of the same name already exists in the file it is
    removed first so this operator is idempotent — clicking the
    button twice gives a fresh rig, not a duplicate.

    Returns the new rig Object so callers can drive its pose bones.
    """
    # Make sure we're in Object mode before touching data blocks.
    if context.active_object is not None and context.active_object.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

    # Remove any prior rig + its armature data block.
    existing_object = bpy.data.objects.get(RIG_OBJECT_NAME)
    if existing_object is not None:
        bpy.data.objects.remove(existing_object, do_unlink=True)
    existing_armature = bpy.data.armatures.get(ARMATURE_DATA_NAME)
    if existing_armature is not None:
        bpy.data.armatures.remove(existing_armature)

    # Fresh armature data + object.
    armature_data = bpy.data.armatures.new(ARMATURE_DATA_NAME)
    armature_data.display_type = 'OCTAHEDRAL'
    armature_data.show_names = True

    rig_object = bpy.data.objects.new(RIG_OBJECT_NAME, armature_data)
    rig_object.show_in_front = True
    context.collection.objects.link(rig_object)

    # Activate + select so we can enter Edit mode to add bones.
    context.view_layer.objects.active = rig_object
    rig_object.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')

    edit_bones = armature_data.edit_bones

    # Pass 1: create every body bone with its rest head/tail.
    for bone_name, (head_xyz, tail_xyz) in BONE_REST_POSITIONS.items():
        bone = edit_bones.new(bone_name)
        bone.head = Vector(head_xyz)
        bone.tail = Vector(tail_xyz)

    # Pass 1b: create hand bones (30 total, 15 per side).
    for bone_name, (head_xyz, tail_xyz) in HAND_BONE_REST_POSITIONS.items():
        bone = edit_bones.new(bone_name)
        bone.head = Vector(head_xyz)
        bone.tail = Vector(tail_xyz)

    # Pass 2: wire ALL parent hierarchies now that every bone exists.
    for child_name, parent_name in BONE_PARENTS.items():
        edit_bones[child_name].parent = edit_bones[parent_name]
    for child_name, parent_name in HAND_BONE_PARENTS.items():
        edit_bones[child_name].parent = edit_bones[parent_name]

    # Back to Object mode so the rig settles into its rest pose.
    bpy.ops.object.mode_set(mode='OBJECT')

    # v2.0.2: ground-plane (Floor) clamp via LimitLocation constraint.
    # Prevents foot bones from dipping below the puppet's "stage floor"
    # when (a) MP loses lower-body tracking (kid sits at desk), or
    # (b) MP estimates a foot below ground (extreme poses, occlusion
    # noise). The constraint reads the rest-pose foot head Z (0.05m
    # per BONE_REST_POSITIONS) so it self-calibrates if the rig
    # dimensions ever change.
    #
    # Owner space = WORLD: clamps the bone's world-space location.
    # With the armature at world origin (V2's default), this matches
    # the rig comment "T-pose: feet on the ground (z=0)."
    #
    # Clamps the bone HEAD (ankle). Foot tail (toe) can still dip
    # slightly below floor when toes-pointed-down — that's a v2.0.3
    # candidate (second constraint or driver targeting the tail).
    #
    # Bone constraints chosen over imperative receiver-side clamping
    # per V2_0_2_DESIGN.md "Why Constraint, Not Imperative" — applies
    # during live drive AND NLA playback AND timeline scrubbing,
    # survives in rig state for inspection.
    for foot_name in ('foot.L', 'foot.R'):
        pb_foot = rig_object.pose.bones[foot_name]
        rest_head_z = pb_foot.bone.head_local.z
        constraint = pb_foot.constraints.new('LIMIT_LOCATION')
        constraint.name = "Floor (v2.0.2)"
        constraint.use_min_z = True
        constraint.min_z = rest_head_z
        constraint.owner_space = 'WORLD'

    return rig_object
