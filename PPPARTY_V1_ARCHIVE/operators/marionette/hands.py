# SPDX-License-Identifier: GPL-3.0-or-later
"""Hands — palm plate, palm corners, and four finger chains per side.

=============================================================================
Where this fits in the 14-step hand-physics plan
=============================================================================
This module is **Step 7 of the NATIVE_PHYSICS_DESIGN.md plan**: build the
hand geometry in rest pose, *without any physics wired yet*. When the kid
clicks "Create Puppet" after this step, hands appear at each wrist and
fingers stick straight out from the palm. Nothing moves yet — that's on
purpose. Physics wiring lands in steps 10 (finger chains) and 11 (palm
corner jiggle).

Why build geometry first, physics later? Two reasons:

    1. Geometry is easy to eyeball. If a palm is in the wrong place or a
       finger points the wrong way, you can see it instantly. Physics
       bugs are much harder to diagnose when the geometry itself is
       suspect — so we lock the geometry first, then sim-drive it.
    2. The state items for the sim zone were already declared in
       physics.py (step 3) with passthrough wiring. This module does not
       *read* those state items yet — it computes every position inline
       from the palm's world position. When step 10 lands, the same
       inline positions become the Goal inputs of `PP_ChainVerletSegment`
       instances, and the geometry here gets re-sourced from sim_out.
       Nothing in this file is thrown away — it's a frame of scaffolding
       that later gets replaced node-by-node by the physics version.

=============================================================================
The hand layout (cartoon: 3 fingers + 1 thumb)
=============================================================================
Each hand has:

    * One palm plate — a small cuboid at the wrist, thin in depth, wider
      than it is tall (like a little pancake paddle).
    * Four palm-corner beads — small spheres at the four corners of the
      palm plate. These are the "ball joints where fingers meet palm"
      David asked for, and each one becomes a jiggle spring in step 11.
    * Four finger chains (fingerA, fingerB, fingerC, fingerD):
          fingerA = thumb          — anchored at SW corner, points sideways+down
          fingerB = middle finger  — anchored at N-edge center, tracked by MediaPipe
          fingerC = side-A finger  — anchored at N-edge, offset +X_local
          fingerD = side-B finger  — anchored at N-edge, offset -X_local
      Each chain has two segments (base → mid → tip). In rest pose all
      four chains hang straight down from their anchor — fingers dangle.

Compass convention (palm-local):

    +Y_local = toward fingertips (the "N" edge of the palm plate)
    +X_local = away from thumb (so thumb sits at the -X_local side)
    +Z_local = palm normal (facing forward / toward camera)

In step 7 there is no palm basis yet — the puppet's hands don't rotate
with tracking data, so palm-local IS just world axes with a side mirror:

    left  hand: thumb on +X_world (body-center side)
    right hand: thumb on -X_world (body-center side)

When hand tracking comes online (step 8), palm-local will be rebuilt
from MediaPipe wrist + thumb tip + index tip, and these same offsets
will transform through that basis. The compass labels stay constant.

=============================================================================
Shape synthesis pattern
=============================================================================
Same three primitives as body_parts.py — no new math, just different
positions and radii:

    palm plate  = GeometryNodeMeshCube → Transform → Shade Smooth → Material
    palm corner = GeometryNodeMeshUVSphere → Transform → ...
    finger seg  = GeometryNodeCurvePrimitiveLine → Curve to Mesh (shared
                  profile) → ... (pattern lifted from add_limb)

Both the palm plate and the palm-corner spheres read from the **palm
material** (Hand Material socket on the group input, same as the hand
capsules above us in the tree). Finger tubes and joint beads read from
the **limb** and **joint** materials (same as arm tubes and elbow beads).

=============================================================================
Public entry point
=============================================================================
    build_hands(tree, group_in, sim_out, body_mats,
                palm_l_pos, palm_r_pos, snap_state)
        Build both hands' geometry (palm + 4 corners + 4 finger chains
        each, × 2 sides). Wrap with a "THE HANDS" frame. Return a dict
        with parts_geo (geometry sockets to join at assembly time) and
        snap_state (the post-section snapshot, so assembly can keep the
        "frame what's new" pattern running).

    palm_l_pos / palm_r_pos are Vector sockets that set "where the palm
    lives" for each hand. In alpha.49+ they're wired to hand_l_pos /
    hand_r_pos from body_parts — the post-lerp arm endpoint that is the
    Verlet dangle-position when Body Tracking is 0, and shoulder +
    tracked_dir × arm_length when Body Tracking ramps up. That socket
    is never (0,0,0), so no palm-level safety switch is needed.

    Why we moved off bt_wrist_* for the palm anchor:
        alpha.47 wired palm_pos directly to bt_wrist_l/r, which
        teleported the hand to world origin before the first webcam
        packet arrived. alpha.48 added a zero-length switch to fall
        back to hand_l/r_pos — in practice the palm still landed at
        origin on David's smoke test. alpha.49 drops the switch and
        anchors on hand_l/r_pos unconditionally, which already carries
        MP wrist data through the body-movement blend. Precision loss
        is ~zero because tracked_hand_l = shoulder + norm(MP_wrist -
        shoulder) × arm_length, which agrees with MP_wrist up to the
        puppet/performer arm-length rescale.

The signature mirrors build_body_parts's — same (tree, group_in, sim_out,
body_mats, …, snap_state) shape, same dict-return convention — so it
slots into assembly.py between build_body_parts and build_studio_track
with one call.
"""

import math

from ._common import (add_node, _frame_section,
                      _snap_nodes, _new_nodes, _vector_lerp)
from . import physics_presets
from .physics import _ensure_chain_segment_group


# =============================================================================
# HAND GEOMETRY CONSTANTS — palm + finger dimensions
# =============================================================================
# The numbers below are the puppet's hand anatomy. Choosing them is an
# art-direction judgment (how chunky should fingers feel, how big should
# the palm read at viewing distance, etc.); the code itself is agnostic
# to the values. Changing any number here reshapes both hands globally.
#
#   PALM_PLATE_SIZE        palm rectangle dimensions, world units (X, Y, Z)
#                          X = thumb-to-pinky width
#                          Y = palm thickness (thin, since it's a "plate")
#                          Z = wrist-to-finger depth (tall, since fingers
#                              dangle in -Z)
#   PALM_CORNER_RADIUS     size of the four ball joints at palm corners
#   FINGER_SEG_RADIUS      thickness of the finger tube
#   FINGER_SEG_LENGTH      length of each finger segment (tube)
#   FINGER_JOINT_RADIUS    size of the joint beads at mid-finger and fingertip

PALM_PLATE_SIZE = (0.20, 0.035, 0.18)
PALM_CORNER_RADIUS = 0.028
THUMB_KNUCKLE_RADIUS = 0.035
FINGER_SEG_RADIUS = 0.020
FINGER_SEG_LENGTH = 0.08
FINGER_JOINT_RADIUS = 0.022
PALM_TAPER = 0.3

# Yaw the whole hand around Z so thumbs angle forward/outward instead of
# flat-forward — that's the natural relaxed-arm pose (palms face inward
# toward thighs, thumbs swing forward). LEFT hand yaws negative, RIGHT
# hand yaws positive; mirrored by _yaw_mirror_for_side.
PALM_YAW_DEG = 45.0
_PALM_YAW_RAD = math.radians(PALM_YAW_DEG)


# Palm-corner local-space offsets from palm center (= wrist position in V1).
# Compass convention is documented in the module docstring above. The N
# edge of the palm (+Z_world, which in our orientation means DOWN in
# world space since fingers dangle) is where the three non-thumb fingers
# emerge.
#
# In V1 there is no palm basis matrix: palm-local axes are aligned to
# world axes with the +X side mirrored per hand side, plus a fixed ±45°
# yaw around Z (forward-outward thumb pose). The offsets below are the
# pre-yaw left-hand version; _yaw_mirror_for_side applies both the X
# mirror and the per-side yaw in one call.
#
# Axes in world space for V1 rest pose:
#   palm-local +X  →  world +X (toward body center for LEFT hand)
#   palm-local +Y  →  world +Y (palm normal — faces forward)
#   palm-local +Z  →  world -Z (fingertip direction — fingers dangle down)
#
# So compass offsets in world coordinates (for the LEFT hand):

_PALM_HALF_X = PALM_PLATE_SIZE[0] * 0.5   # thumb-to-pinky half-width
_PALM_HALF_Z = PALM_PLATE_SIZE[2] * 0.5   # wrist-to-finger half-depth

# Shift the palm "center" slightly toward the finger side so the plate
# doesn't clip into the forearm tip. (Half of its Z extent toward -Z.)
_PALM_CENTER_Z_BIAS = -0.06

# Tapered wrist edge — SW/SE corners sit inboard of the raw palm edge by
# the same PALM_TAPER factor the plate cube uses, so the beads stay flush
# on the tapered shape instead of floating off the narrowed wrist side.
_WRIST_EDGE_X = (1.0 - PALM_TAPER) * _PALM_HALF_X

# Knuckle-row span (NW/NE corners). Wider than the old 0.5× so the NW/NE
# beads co-locate with the fingerC/D anchor positions and read as
# "knuckle beads where those fingers meet the palm."
_SIDE_SPREAD_X = _PALM_HALF_X * 0.8

PALM_CORNER_OFFSETS = {
    # (X_local_for_LEFT_hand, Y_local, Z_world — N means "+Z_local/-Z_world")
    'sw': (-_WRIST_EDGE_X, 0.0, _PALM_CENTER_Z_BIAS + _PALM_HALF_Z),
    'se': (+_WRIST_EDGE_X, 0.0, _PALM_CENTER_Z_BIAS + _PALM_HALF_Z),
    'nw': (-_SIDE_SPREAD_X, 0.0, _PALM_CENTER_Z_BIAS - _PALM_HALF_Z),
    'ne': (+_SIDE_SPREAD_X, 0.0, _PALM_CENTER_Z_BIAS - _PALM_HALF_Z),
}

# Per-chain anchor offset (where the finger roots on the palm) and rest
# direction (unit vector from anchor toward fingertip). Pre-yaw values
# for the LEFT hand; _yaw_mirror_for_side applies X mirror + ±45° yaw.
#
#   fingerA = thumb — anchored at SW corner of the palm (thumb-side,
#       wrist-side). Thumb points slightly outward and down.
#   fingerB = middle/tracked — anchored at the N-edge center (bottom
#       center of palm plate). Points straight down.
#   fingerC = side-A — offset +X along the N edge. Points down + slight
#       outward splay.
#   fingerD = side-B — offset -X along the N edge. Points down + slight
#       inward splay (toward thumb side).
#
# Step 7 uses the simplest possible rest directions — straight-down for
# the three fingers, diagonally for the thumb. Step 10 replaces these
# with physics-driven positions; step 8/9 replaces fingerB's tip with
# MediaPipe-tracked coordinates.

_N_EDGE_Z = _PALM_CENTER_Z_BIAS - _PALM_HALF_Z    # Z coord of palm's N edge
# (_SIDE_SPREAD_X is now defined above so PALM_CORNER_OFFSETS can use it.)

CHAIN_REST = {
    'fingerA': {
        'anchor': PALM_CORNER_OFFSETS['sw'],
        'dir':    (-0.3, 0.0, -0.95),
    },
    'fingerB': {
        'anchor': (0.0, 0.0, _N_EDGE_Z),
        'dir':    (0.0, 0.0, -1.0),
    },
    'fingerC': {
        'anchor': (+_SIDE_SPREAD_X, 0.0, _N_EDGE_Z),
        'dir':    (+0.2, 0.0, -0.98),
    },
    'fingerD': {
        'anchor': (-_SIDE_SPREAD_X, 0.0, _N_EDGE_Z),
        'dir':    (-0.2, 0.0, -0.98),
    },
}

# Mirror constants — the physics.py state-item scheme uses these exact
# names, so the constants here MUST match one-for-one. If physics.py
# changes these, this file must change in lockstep.
HAND_SIDES = ('l', 'r')
HAND_CHAINS = ('fingerA', 'fingerB', 'fingerC', 'fingerD')
FINGER_SEGMENTS = 2
PALM_CORNERS = ('ne', 'nw', 'se', 'sw')

# Render-only bead set — which corners get a visible sphere in the
# geometry pass. A subset of PALM_CORNERS: the SE corner is a physics
# reservation only (jiggle state in step 11), not something a cartoon
# palm needs to look at. If step 11 decides SE deserves a visible bump
# later, promote it back into PALM_BEAD_CORNERS.
PALM_BEAD_CORNERS = ('ne', 'nw', 'sw')


# =============================================================================
# CHAIN-PHYSICS PER-SEGMENT FACTORS (alpha.54 / step 3d)
# =============================================================================
# `PP_ChainVerletSegment` exposes a per-segment Root Falloff Factor + End
# Factor Scale. The chain algorithm wants seg 0 (the mid joint) to stay
# half-pinned to its rest pose and seg 1 (the tip) to dangle freely. Cody
# Winchester's Goo formulas:
#
#     rff[i] = rf  * (1 - i / (n - 1))    # 1.0 at root, 0.0 at tip
#     efs[i] = 1 + (sef - 1) * (i / (n - 1))  # 1.0 at root, sef at tip
#
# For our 2-segment fingers with HAIRSIDE preset (rf = 0.5, sef = 0.2):
#     seg 0 → rff = 0.5, efs = 1.0   (50% blend toward Goal — soft pin)
#     seg 1 → rff = 0.0, efs = 0.2   (free, weak goal pull on tip)
#
# Pre-baked at import time so each `_add_chain_segment_physics` call
# can hardcode them as `default_value` on the chain-segment instance —
# no runtime tuning, no runtime math. Same status as `MIDLINE_MARGIN`
# in physics.py: build-time constants from the role-mapped preset.

_CHAIN_PRESET_NAME = physics_presets.CHAIN_PRESET_BY_ROLE['finger']
_CHAIN_PRESET = physics_presets.CHAIN_PRESETS[_CHAIN_PRESET_NAME]
_HAIRSIDE_RF = _CHAIN_PRESET['Root Falloff']
_HAIRSIDE_SEF = _CHAIN_PRESET['Stiff End Fac']

# Guard for n=1 chains (would divide by zero) — V1 fingers are always 2.
_SEG_DENOM = max(FINGER_SEGMENTS - 1, 1)
RFF_PER_SEG = tuple(
    _HAIRSIDE_RF * (1.0 - i / _SEG_DENOM) for i in range(FINGER_SEGMENTS))
EFS_PER_SEG = tuple(
    1.0 + (_HAIRSIDE_SEF - 1.0) * (i / _SEG_DENOM)
    for i in range(FINGER_SEGMENTS))

# Sanity: design doc spec for HAIRSIDE / 2-seg chain.
assert FINGER_SEGMENTS == 2 and abs(RFF_PER_SEG[0] - 0.5) < 1e-6
assert abs(RFF_PER_SEG[1] - 0.0) < 1e-6
assert abs(EFS_PER_SEG[0] - 1.0) < 1e-6
assert abs(EFS_PER_SEG[1] - 0.2) < 1e-6

# Modifier-interface chain-param sockets (declared in assembly.py's
# Physics panel, alpha.54). Wired into every chain segment instance
# via `group_in.outputs[name]` — runtime-tunable. Order matters only
# for readability; the wiring is by name.
CHAIN_PARAM_SOCKETS = (
    'Chain Velocity', 'Chain Dampening', 'Chain Gravity',
    'Chain Stiffness', 'Stiff Vel Fac', 'Stiff Vel Min', 'Stiff Vel Max',
)


def _yaw_mirror_for_side(vec, side):
    """Mirror X then yaw around Z, both keyed to hand side.

    DEPRECATED in alpha.57 — replaced by `_palm_offset_vec_basis`
    which rotates offsets by the live palm basis from MediaPipe.
    Kept defined (not deleted) so any stale handoff or design doc
    that references it stays buildable. No call sites remain in V1.

    Two transforms rolled into one so every call site doesn't have to
    chain them. Applied to palm-local offsets (corner beads, finger
    anchors, finger rest-direction vectors) so geometry on both hands
    ends up in the natural relaxed-arm pose: palms turned inward
    toward the body, thumbs swinging forward and outward.

        LEFT  hand: mirror X unchanged, yaw = -PALM_YAW_RAD
        RIGHT hand: mirror X flipped,   yaw = +PALM_YAW_RAD

    The palm plate itself gets the same yaw via its Transform node's
    Rotation input (see _add_palm_plate) so the corner beads, finger
    anchors, and the plate geometry all rotate together around the
    palm center. Z is untouched — fingers still dangle down in world.
    """
    mx = 1.0 if side == 'l' else -1.0
    yaw = _PALM_YAW_RAD if side == 'l' else -_PALM_YAW_RAD
    c = math.cos(yaw)
    s = math.sin(yaw)
    x = vec[0] * mx
    y = vec[1]
    return (x * c - y * s, x * s + y * c, vec[2])


def _palm_yaw_for_side(side):
    """Z-axis yaw angle (radians) applied to the palm plate per side."""
    return _PALM_YAW_RAD if side == 'l' else -_PALM_YAW_RAD


# =============================================================================
# PALM OFFSET HELPER — palm_pos + constant offset
# =============================================================================
# Every piece of untracked hand geometry lives at a position of the form
#   palm_position + local_offset
# where palm_position is a *socket* (alpha.47+: bt_wrist_l / bt_wrist_r,
# MediaPipe hand-landmark wrist; earlier alphas: hand_l/r_pos, the
# Verlet-blended arm endpoint) and local_offset is a constant tuple
# chosen at code-write time. A three-node subtree does the sum:
#   Combine XYZ (constant offset) → Vector Math ADD (+palm_pos) → Vector out
# Wrapped in a helper to keep the call sites short.

def _palm_offset_vec(tree, x, y, label, palm_pos_socket, offset):
    """Return a Vector socket = palm_pos_socket + offset (constant)."""
    combo = add_node(tree, 'ShaderNodeCombineXYZ', x, y, f"{label} Off")
    combo.inputs['X'].default_value = offset[0]
    combo.inputs['Y'].default_value = offset[1]
    combo.inputs['Z'].default_value = offset[2]
    add = add_node(tree, 'ShaderNodeVectorMath', x + 180, y, f"{label} Pos")
    add.operation = 'ADD'
    tree.links.new(palm_pos_socket, add.inputs[0])
    tree.links.new(combo.outputs['Vector'], add.inputs[1])
    return add.outputs['Vector']


# =============================================================================
# PALM BASIS HELPERS — alpha.57: tracked palm rotation
# =============================================================================
# Replaces the V1-era `_yaw_mirror_for_side` per-side constant rotation with
# a per-frame basis matrix driven by MediaPipe (palm_x_<S> / palm_y_<S>
# vector sockets pushed by the receiver in alpha.56).
#
# AXIS MAPPING — read carefully, this is the seam where two conventions
# meet, and there is ONE SIGN FLIP that bit alpha.57a in install-test:
#
#     V1 local axis              ←→  alpha.56 basis socket
#     ---------------------------    -------------------------------
#     local X  (thumb→pinky)         palm_x   (radial→ulnar)
#     local Y  (palm normal)         palm_z   = cross(palm_x, palm_y)
#     local Z  (WRIST SIDE)          -palm_y  (NEGATED — sender's
#                                              palm_y points
#                                              wrist→fingers, V1's
#                                              +Z_local points the
#                                              OTHER way: wrist side)
#
# So a constant V1 offset (lx, ly, lz) gets rotated by the live basis as
#     world = palm_x * lx + palm_z * ly + (-palm_y) * lz
#           = palm_x * lx + palm_z * ly - palm_y * lz
#
# This is critical: V1's CHAIN_REST['fingerB']['dir'] = (0, 0, -1) means
# "fingers extend toward -Z_local," and -Z_local in the new convention is
# +palm_y (wrist→fingers). Without the sign flip, fingers extended in
# +palm_y * -1 = -palm_y direction = AWAY from fingertips → fingers
# inverted from rest pose, palm bias pushed into the arm, palm flopped
# the wrong way under tracked rotation. Fixed in alpha.57b by negating
# the local-Z scale at every basis-rotate call.
#
# palm_z (the cross product result, palm normal) is unchanged — the
# right-handed cross is taken from RAW palm_y so the normal stays
# correct; only the V1-local-Z multiplications get the sign flip.

def _palm_basis_z(tree, x, y, label, basis_x_socket, basis_y_socket):
    """Compute basis_z = cross(basis_x, basis_y). Returns Vector socket.

    Reused per side — call once at the top of build_hands for L and R,
    then thread the resulting socket down into every basis-rotate call.
    The receiver already enforces orthogonality post-filter so the result
    is unit-length to within filter noise (~0.1% drift, invisible).
    """
    cross = add_node(tree, 'ShaderNodeVectorMath', x, y,
                     f"{label} basisZ")
    cross.operation = 'CROSS_PRODUCT'
    tree.links.new(basis_x_socket, cross.inputs[0])
    tree.links.new(basis_y_socket, cross.inputs[1])
    return cross.outputs['Vector']


def _palm_offset_vec_basis(tree, x, y, label, palm_pos_socket,
                           basis_x_socket, basis_y_socket, basis_z_socket,
                           offset):
    """Return Vector socket = palm_pos + basis_rotate(offset).

    Replaces the alpha.56-and-earlier pattern of
        `_palm_offset_vec(palm, _yaw_mirror_for_side(offset, side))`
    with a per-frame basis multiply driven by tracked palm orientation.
    See module-level "AXIS MAPPING" block for the local→basis component
    mapping.

    Six nodes per call (3 SCALEs + 2 ADDs + 1 final ADD). At ~9 call
    sites total per side that's ~108 added nodes across both hands —
    real but small next to the chain-physics overhead.

    `offset` is a Python tuple of 3 floats (constant local-space offset).
    """
    # Each component scales the corresponding basis vector. Note the
    # mapping: V1 local Y (offset[1]) reads palm_z; V1 local Z (offset[2])
    # reads palm_y. See module AXIS MAPPING block.
    sx = add_node(tree, 'ShaderNodeVectorMath', x, y, f"{label} bX*x")
    sx.operation = 'SCALE'
    tree.links.new(basis_x_socket, sx.inputs[0])
    sx.inputs['Scale'].default_value = offset[0]

    sz = add_node(tree, 'ShaderNodeVectorMath', x, y - 60, f"{label} bZ*y")
    sz.operation = 'SCALE'
    tree.links.new(basis_z_socket, sz.inputs[0])
    sz.inputs['Scale'].default_value = offset[1]

    sy = add_node(tree, 'ShaderNodeVectorMath', x, y - 120, f"{label} bY*z")
    sy.operation = 'SCALE'
    tree.links.new(basis_y_socket, sy.inputs[0])
    # NEGATED — see module AXIS MAPPING block. V1's +Z_local axis is the
    # WRIST SIDE; sender's palm_y points wrist→fingers (opposite). The
    # sign flip lives here so every caller can keep passing CHAIN_REST
    # and PALM_CORNER_OFFSETS values verbatim.
    sy.inputs['Scale'].default_value = -offset[2]

    sum1 = add_node(tree, 'ShaderNodeVectorMath', x + 180, y,
                    f"{label} S1")
    sum1.operation = 'ADD'
    tree.links.new(sx.outputs['Vector'], sum1.inputs[0])
    tree.links.new(sz.outputs['Vector'], sum1.inputs[1])

    sum2 = add_node(tree, 'ShaderNodeVectorMath', x + 360, y,
                    f"{label} S2")
    sum2.operation = 'ADD'
    tree.links.new(sum1.outputs['Vector'], sum2.inputs[0])
    tree.links.new(sy.outputs['Vector'], sum2.inputs[1])

    final = add_node(tree, 'ShaderNodeVectorMath', x + 540, y,
                     f"{label} Pos")
    final.operation = 'ADD'
    tree.links.new(palm_pos_socket, final.inputs[0])
    tree.links.new(sum2.outputs['Vector'], final.inputs[1])

    return final.outputs['Vector']


# =============================================================================
# ZERO-VECTOR FALLBACK — switch to `fallback` when `primary` is (0,0,0)
# =============================================================================
# MediaPipe tracking sockets (bt_wrist_l/r, bt_thumb_l/r, bt_index_l/r)
# all default to Vector(0,0,0) before the first tracking packet arrives.
# That would teleport the palm + finger tips to world origin for a beat
# at addon startup — fine for the UDP receiver's steady-state (once a
# packet lands it freezes at last value, even if the hand leaves frame),
# but ugly on first puppet spawn when no webcam is running yet.
#
# Pattern: length-check the primary socket, branch on >epsilon, Switch
# between primary (tracking live) and fallback (pre-tracking rest pose).
# Epsilon is tiny — real tracked positions are never at the exact origin,
# so any non-zero length means "tracking has seen this landmark at least
# once." Three nodes total: Vector Length → Float Compare → Vector Switch.

_ZERO_EPSILON = 0.0001


def _with_fallback(tree, x, y, label, primary_socket, fallback_socket):
    """Return a Vector socket = primary if len(primary) > eps, else fallback.

    Used to bridge the initial zero state of MediaPipe tracking sockets
    (bt_wrist / bt_thumb / bt_index) to a sensible rest pose. After the
    first tracking packet arrives the socket holds the last-tracked
    value — the receiver leaves it frozen even when the hand leaves the
    frame — so this switch is only "active" for the brief window between
    Create Puppet and the first webcam packet.
    """
    length = add_node(tree, 'ShaderNodeVectorMath', x, y,
                      f"{label} Len")
    length.operation = 'LENGTH'
    tree.links.new(primary_socket, length.inputs[0])

    compare = add_node(tree, 'FunctionNodeCompare', x + 180, y,
                       f"{label} ?")
    compare.data_type = 'FLOAT'
    compare.operation = 'GREATER_THAN'
    tree.links.new(length.outputs['Value'], compare.inputs[0])
    compare.inputs[1].default_value = _ZERO_EPSILON

    switch = add_node(tree, 'GeometryNodeSwitch', x + 360, y,
                      f"{label} Sw")
    switch.input_type = 'VECTOR'
    # Pick the enabled Vector False/True sockets by type. Blender's Switch
    # node keeps typed socket pairs around in inputs[] but only enables the
    # ones matching input_type. Indexing with Python False/True coerces to
    # inputs[0]/[1] — which is the Bool Switch and first typed False,
    # overwriting the Switch link and mis-routing the data. Filter by type
    # instead so the right Vector pair is always picked.
    vec_inputs = [s for s in switch.inputs if s.type == 'VECTOR']
    false_in, true_in = vec_inputs[0], vec_inputs[1]
    tree.links.new(compare.outputs['Result'], switch.inputs['Switch'])
    tree.links.new(fallback_socket, false_in)
    tree.links.new(primary_socket, true_in)
    return switch.outputs['Output']


# =============================================================================
# PALM PLATE — one static cuboid at the wrist
# =============================================================================
# The palm is built as a plain mesh cube (the Geometry Nodes primitive,
# not a dynamic Minkowski capsule — palm is NOT a pill, it's a plate).
# Five nodes: Cube → Transform (translate to palm_pos, rotated if side
# mirroring ever adds a rotation) → Shade Smooth → Set Material → append.
#
# In V1 the palm rotation is identity (faces +Y world / forward). When
# step 9 wires in the tracked hand basis, the rotation socket gets driven
# by a 3×3 basis matrix → Euler conversion computed outside this helper.

def _add_palm_plate(tree, x, y, parts_geo, side, palm_pos_socket,
                    basis_x_socket, basis_y_socket, basis_z_socket,
                    mat_socket):
    """Build the palm rectangle mesh at palm_pos. Adds 1 geo socket.

    The cube is tapered along X as a linear function of Z before it's
    translated into place — the wrist end (+Z_local) gets narrower by
    PALM_TAPER, the finger end (-Z_local) stays full width. With only
    2×2×2 verts the result is a clean trapezoidal prism (4 finger-side
    verts at full X, 4 wrist-side verts at (1-PALM_TAPER)*X). The
    PALM_CORNER_OFFSETS already use _WRIST_EDGE_X for SW/SE so the
    corner beads sit flush on the tapered edge.

    Taper multiplier for an X coord at Z_local is:
        f(Z) = 1 - PALM_TAPER * (Z + _PALM_HALF_Z) / (2 * _PALM_HALF_Z)
             = Z * rate + base          (Multiply-Add, one node)
    where rate = -PALM_TAPER / (2 * _PALM_HALF_Z) and base = 1 - PALM_TAPER/2.

    alpha.57: the palm plate is built directly in basis space — no
    Transform node, no Euler conversion. After the taper Set Position,
    a second Set Position rewrites every vertex as
        palm_pos + basis_y * Z_BIAS + basis_x * v.x
                                    + basis_z * v.y
                                    + basis_y * v.z
    where the basis sockets carry the live tracked palm orientation
    (alpha.56 receiver push). This is option 2 from the design call —
    the plate is built right the first time, no compensating rotation.
    Same axis mapping as _palm_offset_vec_basis (V1 local Y → basis_z,
    V1 local Z → basis_y).
    """
    cube = add_node(tree, 'GeometryNodeMeshCube', x, y, f"Palm {side}")
    cube.inputs['Size'].default_value = PALM_PLATE_SIZE
    # Low subdivs — it's a little rectangle, not a character.
    cube.inputs['Vertices X'].default_value = 2
    cube.inputs['Vertices Y'].default_value = 2
    cube.inputs['Vertices Z'].default_value = 2

    # --- Taper network (6 nodes): shrink X based on Z_local -------------
    taper_rate = -PALM_TAPER / (2.0 * _PALM_HALF_Z)
    taper_base = 1.0 - PALM_TAPER * 0.5

    in_pos = add_node(tree, 'GeometryNodeInputPosition', x, y - 160,
                      f"Palm {side} InPos")

    sep = add_node(tree, 'ShaderNodeSeparateXYZ', x + 160, y - 160,
                   f"Palm {side} Sep")
    tree.links.new(in_pos.outputs['Position'], sep.inputs[0])

    mul_fac = add_node(tree, 'ShaderNodeMath', x + 320, y - 160,
                       f"Palm {side} Fac")
    mul_fac.operation = 'MULTIPLY_ADD'
    mul_fac.inputs[1].default_value = taper_rate
    mul_fac.inputs[2].default_value = taper_base
    tree.links.new(sep.outputs['Z'], mul_fac.inputs[0])

    mul_x = add_node(tree, 'ShaderNodeMath', x + 480, y - 160,
                     f"Palm {side} X*F")
    mul_x.operation = 'MULTIPLY'
    tree.links.new(sep.outputs['X'], mul_x.inputs[0])
    tree.links.new(mul_fac.outputs['Value'], mul_x.inputs[1])

    comb = add_node(tree, 'ShaderNodeCombineXYZ', x + 640, y - 160,
                    f"Palm {side} Cmb")
    tree.links.new(mul_x.outputs['Value'], comb.inputs['X'])
    tree.links.new(sep.outputs['Y'], comb.inputs['Y'])
    tree.links.new(sep.outputs['Z'], comb.inputs['Z'])

    set_pos = add_node(tree, 'GeometryNodeSetPosition', x + 800, y,
                       f"Palm {side} Tpr")
    tree.links.new(cube.outputs['Mesh'], set_pos.inputs['Geometry'])
    tree.links.new(comb.outputs['Vector'], set_pos.inputs['Position'])

    # --- Basis-space transform (alpha.57) ------------------------------
    # Read each tapered vertex's local position, decompose into x/y/z,
    # scale each basis vector by the corresponding component, sum + add
    # palm_pos and the per-side Z-bias (V1's _PALM_CENTER_Z_BIAS, now
    # along basis_y so the bias rotates WITH the palm).
    in_pos2 = add_node(tree, 'GeometryNodeInputPosition', x + 1000, y - 200,
                       f"Palm {side} BPos")
    sep2 = add_node(tree, 'ShaderNodeSeparateXYZ', x + 1180, y - 200,
                    f"Palm {side} BSep")
    tree.links.new(in_pos2.outputs['Position'], sep2.inputs[0])

    # Per-vertex contributions: basis_x * v.x, basis_z * v.y, basis_y * v.z.
    # Each Vector Math SCALE takes the basis vector and multiplies it by
    # the per-vertex float. Three nodes.
    bx_v = add_node(tree, 'ShaderNodeVectorMath', x + 1360, y - 100,
                    f"Palm {side} bX*x")
    bx_v.operation = 'SCALE'
    tree.links.new(basis_x_socket, bx_v.inputs[0])
    tree.links.new(sep2.outputs['X'], bx_v.inputs['Scale'])

    bz_v = add_node(tree, 'ShaderNodeVectorMath', x + 1360, y - 200,
                    f"Palm {side} bZ*y")
    bz_v.operation = 'SCALE'
    tree.links.new(basis_z_socket, bz_v.inputs[0])
    tree.links.new(sep2.outputs['Y'], bz_v.inputs['Scale'])

    # Per-vertex local-Z multiplier — NEGATED before scaling basis_y.
    # See module AXIS MAPPING block: V1's +Z_local = wrist side, but
    # sender's palm_y points wrist→fingers (opposite). One Math node
    # to flip the sign of the per-vertex Z float before it scales the
    # basis_y vector.
    neg_z = add_node(tree, 'ShaderNodeMath', x + 1240, y - 300,
                     f"Palm {side} -z")
    neg_z.operation = 'MULTIPLY'
    tree.links.new(sep2.outputs['Z'], neg_z.inputs[0])
    neg_z.inputs[1].default_value = -1.0

    by_v = add_node(tree, 'ShaderNodeVectorMath', x + 1420, y - 300,
                    f"Palm {side} bY*-z")
    by_v.operation = 'SCALE'
    tree.links.new(basis_y_socket, by_v.inputs[0])
    tree.links.new(neg_z.outputs['Value'], by_v.inputs['Scale'])

    sum_xy = add_node(tree, 'ShaderNodeVectorMath', x + 1540, y - 100,
                      f"Palm {side} Sxy")
    sum_xy.operation = 'ADD'
    tree.links.new(bx_v.outputs['Vector'], sum_xy.inputs[0])
    tree.links.new(bz_v.outputs['Vector'], sum_xy.inputs[1])

    sum_xyz = add_node(tree, 'ShaderNodeVectorMath', x + 1720, y - 100,
                       f"Palm {side} Sxyz")
    sum_xyz.operation = 'ADD'
    tree.links.new(sum_xy.outputs['Vector'], sum_xyz.inputs[0])
    tree.links.new(by_v.outputs['Vector'], sum_xyz.inputs[1])

    # Per-frame, per-side translation: palm_pos + basis_y * _PALM_CENTER_Z_BIAS.
    # The bias is now along basis_y (palm-local "wrist→fingers"), so it
    # rotates with the tracked palm — bias still pushes the plate "toward
    # the fingertip side" regardless of palm orientation. Two nodes,
    # constant per frame, shared across all 8 verts.
    bias_off = add_node(tree, 'ShaderNodeVectorMath', x + 1000, y + 80,
                        f"Palm {side} Bias")
    bias_off.operation = 'SCALE'
    tree.links.new(basis_y_socket, bias_off.inputs[0])
    # NEGATED — see module AXIS MAPPING. _PALM_CENTER_Z_BIAS = -0.06
    # in V1 means "shift palm CENTER toward fingertips" (V1 -Z_local
    # is the finger side). Sender's palm_y already points toward
    # fingers, so the bias sign flips: -(-0.06) = +0.06 along palm_y
    # = "toward fingers." Without the flip the bias pushed the plate
    # AWAY from the fingers and INTO the arm.
    bias_off.inputs['Scale'].default_value = -_PALM_CENTER_Z_BIAS

    palm_plus_bias = add_node(tree, 'ShaderNodeVectorMath',
                              x + 1180, y + 80,
                              f"Palm {side} Ctr")
    palm_plus_bias.operation = 'ADD'
    tree.links.new(palm_pos_socket, palm_plus_bias.inputs[0])
    tree.links.new(bias_off.outputs['Vector'], palm_plus_bias.inputs[1])

    final_pos = add_node(tree, 'ShaderNodeVectorMath', x + 1900, y,
                         f"Palm {side} Final")
    final_pos.operation = 'ADD'
    tree.links.new(palm_plus_bias.outputs['Vector'], final_pos.inputs[0])
    tree.links.new(sum_xyz.outputs['Vector'], final_pos.inputs[1])

    set_basis = add_node(tree, 'GeometryNodeSetPosition', x + 2080, y,
                         f"Palm {side} BSP")
    tree.links.new(set_pos.outputs['Geometry'], set_basis.inputs['Geometry'])
    tree.links.new(final_pos.outputs['Vector'], set_basis.inputs['Position'])

    sm = add_node(tree, 'GeometryNodeSetShadeSmooth', x + 2280, y,
                  f"Palm {side} Sm")
    tree.links.new(set_basis.outputs['Geometry'], sm.inputs['Geometry'])

    mt = add_node(tree, 'GeometryNodeSetMaterial', x + 2480, y,
                  f"Palm {side} Mt")
    tree.links.new(sm.outputs['Geometry'], mt.inputs['Geometry'])
    tree.links.new(mat_socket, mt.inputs['Material'])
    parts_geo.append(mt.outputs['Geometry'])


# =============================================================================
# PALM CORNER BEAD — small sphere at one corner of the palm
# =============================================================================
# A plain UV sphere at (palm_pos + corner_offset). Same recipe as the
# hip/elbow/knee beads in body_parts.add_sphere_part — re-implemented
# here only because the corner position needs a palm-offset computation,
# not just a direct socket.

def _add_palm_corner(tree, x, y, parts_geo, side, corner_label,
                     palm_pos_socket,
                     basis_x_socket, basis_y_socket, basis_z_socket,
                     corner_offset, mat_socket,
                     radius=PALM_CORNER_RADIUS):
    """Small sphere at one palm corner. Adds 1 geo socket.

    `radius` defaults to the regular palm-corner bead size, but the SW
    corner (thumb knuckle) bumps up to THUMB_KNUCKLE_RADIUS so the thumb
    reads as a distinct, chunkier knuckle rather than a fourth corner.

    alpha.57: corner_offset is a CONSTANT palm-local tuple; basis
    rotation maps it to world space each frame so beads ride the
    tracked palm rotation.
    """
    corner_pos = _palm_offset_vec_basis(
        tree, x - 600, y + 100,
        f"Palm{side.upper()}.{corner_label}",
        palm_pos_socket,
        basis_x_socket, basis_y_socket, basis_z_socket, corner_offset)

    sphere = add_node(tree, 'GeometryNodeMeshUVSphere', x, y,
                      f"Corner {side}.{corner_label}")
    sphere.inputs['Segments'].default_value = 8
    sphere.inputs['Rings'].default_value = 6
    sphere.inputs['Radius'].default_value = radius

    tf = add_node(tree, 'GeometryNodeTransform', x + 200, y,
                  f"Corner {side}.{corner_label} TF")
    tree.links.new(sphere.outputs['Mesh'], tf.inputs['Geometry'])
    tree.links.new(corner_pos, tf.inputs['Translation'])

    sm = add_node(tree, 'GeometryNodeSetShadeSmooth', x + 400, y,
                  f"Corner {side}.{corner_label} Sm")
    tree.links.new(tf.outputs['Geometry'], sm.inputs['Geometry'])

    mt = add_node(tree, 'GeometryNodeSetMaterial', x + 600, y,
                  f"Corner {side}.{corner_label} Mt")
    tree.links.new(sm.outputs['Geometry'], mt.inputs['Geometry'])
    tree.links.new(mat_socket, mt.inputs['Material'])
    parts_geo.append(mt.outputs['Geometry'])


# =============================================================================
# FINGER TUBE — line-to-mesh between two sockets
# =============================================================================
# Exactly the same pattern as body_parts.add_limb but with a smaller,
# hand-scale curve profile. Given a start socket and an end socket,
# draw a 2-point line between them and sweep `profile` along it.

def _add_finger_tube(tree, x, y, parts_geo, label, profile,
                     start_socket, end_socket, mat_socket):
    """Curve line → tube mesh → material. Adds 1 geo socket."""
    line = add_node(tree, 'GeometryNodeCurvePrimitiveLine', x, y,
                    f"{label} Ln")
    line.mode = 'POINTS'
    tree.links.new(start_socket, line.inputs['Start'])
    tree.links.new(end_socket, line.inputs['End'])

    tube = add_node(tree, 'GeometryNodeCurveToMesh', x + 200, y,
                    f"{label} Tube")
    tree.links.new(line.outputs['Curve'], tube.inputs['Curve'])
    tree.links.new(profile.outputs['Curve'],
                   tube.inputs['Profile Curve'])

    sm = add_node(tree, 'GeometryNodeSetShadeSmooth', x + 400, y,
                  f"{label} Sm")
    tree.links.new(tube.outputs['Mesh'], sm.inputs['Geometry'])

    mt = add_node(tree, 'GeometryNodeSetMaterial', x + 600, y,
                  f"{label} Mt")
    tree.links.new(sm.outputs['Geometry'], mt.inputs['Geometry'])
    tree.links.new(mat_socket, mt.inputs['Material'])
    parts_geo.append(mt.outputs['Geometry'])


# =============================================================================
# FINGER JOINT BEAD — small sphere at a finger segment endpoint
# =============================================================================
# Tiny bead at either the mid-joint or the fingertip. Radius smaller than
# the palm-corner bead — matches the smaller finger-tube radius so the
# proportions read as "knuckles on a finger."

def _add_finger_joint(tree, x, y, parts_geo, label, pos_socket,
                      mat_socket):
    """Small UV sphere at a finger joint. Adds 1 geo socket.

    Density is intentionally coarser (6×4) than palm corner beads
    (8×6) — finger joints are tiny at viewing distance, so the
    extra rings weren't earning their poly cost. The hex silhouette
    at 6 segments still reads as a sphere once shade-smoothed.
    """
    sphere = add_node(tree, 'GeometryNodeMeshUVSphere', x, y, label)
    sphere.inputs['Segments'].default_value = 6
    sphere.inputs['Rings'].default_value = 4
    sphere.inputs['Radius'].default_value = FINGER_JOINT_RADIUS

    tf = add_node(tree, 'GeometryNodeTransform', x + 200, y,
                  f"{label} TF")
    tree.links.new(sphere.outputs['Mesh'], tf.inputs['Geometry'])
    tree.links.new(pos_socket, tf.inputs['Translation'])

    sm = add_node(tree, 'GeometryNodeSetShadeSmooth', x + 400, y,
                  f"{label} Sm")
    tree.links.new(tf.outputs['Geometry'], sm.inputs['Geometry'])

    mt = add_node(tree, 'GeometryNodeSetMaterial', x + 600, y,
                  f"{label} Mt")
    tree.links.new(sm.outputs['Geometry'], mt.inputs['Geometry'])
    tree.links.new(mat_socket, mt.inputs['Material'])
    parts_geo.append(mt.outputs['Geometry'])


# =============================================================================
# FINGER CHAIN — anchor → seg0 → seg1
# =============================================================================
# Compute the three positions (anchor, mid, tip) for one finger from its
# rest-direction unit vector and FINGER_SEG_LENGTH. Then add:
#   * tube from anchor → seg0
#   * tube from seg0 → seg1
#   * joint bead at seg0
#   * joint bead at seg1
# (The anchor itself gets covered by the palm corner bead for fingerA,
# or sits flush with the palm plate for B/C/D — so no extra anchor bead.)
#
# Rest positions come from palm_pos + direction * length, NOT from the
# sim zone. State-item values are passthrough-wired to Vector(0,0,0)
# until step 10, so reading them here would place everything at the
# origin. The inline rest computation is what makes step 7 validation
# visible.

# =============================================================================
# IN-ZONE PALM POSITION (alpha.54 / step 3d)
# =============================================================================
# Chain physics lives INSIDE the sim zone (between sim_in and sim_out) so
# each segment can carry Verlet state across frames. That means it cannot
# read the post-zone `hand_l_pos` / `hand_r_pos` blend that body_parts.py
# computes (sim_out.outputs[...] is downstream of this zone — circular).
# Instead, we recompute the same blend INSIDE the zone using:
#
#     verlet_half  = sim_in.outputs['pos_hand_<S>']    (previous frame)
#     tracked_half = shoulder_visual + normalize(bt_sh<S>_delta)
#                                       * (bt_arm_<S>_ext * Arm Length)
#     factor       = arm_<S>_factor (= Body Tracking * vis_arm_<S>)
#     palm_pos     = lerp(verlet_half, tracked_half, factor)
#
# Mirrors body_parts.py lines 729–772 exactly except for the Verlet
# half: post-zone uses sim_out (current frame), in-zone uses sim_in
# (one frame ago). At 30 FPS that's a 33 ms lag, which is well inside
# the chain's own settle time — the eye reads the chain physics motion
# and treats the 33 ms anchor lag as part of it. Zero perceived lag in
# BT=1 (tracked half has no lag, fully overrides Verlet).
#
# Why bother with the blend at all instead of just using sim_in directly?
# In BT=1, the body Verlet keeps computing dangle positions that have
# nothing to do with where the visible (tracked) hand is — so a chain
# anchored at sim_in.outputs['pos_hand_l'] would float free of the palm
# geometry by tens of cm. Lerping in the tracked half locks the chain
# anchor to the visible palm whenever tracking is on.

def _palm_pos_inside_zone(tree, x, y, label, side, group_in,
                          shoulder_visual_socket,
                          arm_factor_socket,
                          sim_in_pos_socket,
                          rest_socket,
                          init_cmp_out,
                          not_first_out):
    """Return a palm-position Vector socket usable INSIDE the sim zone.

    Layout span: ~10 nodes across 7 columns (x .. x + 1400).
    Returns the post-init Vector socket so callers can chain
    `_palm_offset_vec` on top of it the same way they used to with the
    post-zone palm_l_pos.

    alpha.55: wraps the lerp output in a first-frame init mix so the
    palm doesn't collapse to the world origin on frame 1. Without this,
    `sim_in.outputs[pos_hand_<S>]` is at default (0,0,0) on frame 1
    (the sim zone hasn't run yet), and with `arm_factor = 0` (BT off,
    default) the lerp result is also (0,0,0). All chain Goals would
    then be palm + offset = offset (tiny near-origin), and fingers
    would spawn near the world origin instead of at the rest dangle.
    Snapping to `rest_socket` on frame 1 mirrors the body Verlet's
    `_add_verlet_endpoint` pattern (physics.py:1304+).
    """
    bt_delta = group_in.outputs[f'bt_sh{side}_delta']
    bt_ext = group_in.outputs[f'bt_arm_{side}_ext']
    arm_len = group_in.outputs['Arm Length']

    # Direction (normalized shoulder→hand delta, frame-fresh)
    dir_n = add_node(tree, 'ShaderNodeVectorMath', x, y, f"{label} Dir")
    dir_n.operation = 'NORMALIZE'
    tree.links.new(bt_delta, dir_n.inputs[0])

    # Reach = bt_arm_ext * Arm Length
    reach = add_node(tree, 'ShaderNodeMath', x, y - 100, f"{label} Rch")
    reach.operation = 'MULTIPLY'
    tree.links.new(bt_ext, reach.inputs[0])
    tree.links.new(arm_len, reach.inputs[1])

    # Offset = direction * reach
    off = add_node(tree, 'ShaderNodeVectorMath', x + 200, y, f"{label} Off")
    off.operation = 'SCALE'
    tree.links.new(dir_n.outputs['Vector'], off.inputs[0])
    tree.links.new(reach.outputs['Value'], off.inputs['Scale'])

    # Tracked = shoulder + offset
    tracked = add_node(
        tree, 'ShaderNodeVectorMath', x + 400, y, f"{label} Trk")
    tracked.operation = 'ADD'
    tree.links.new(shoulder_visual_socket, tracked.inputs[0])
    tree.links.new(off.outputs['Vector'], tracked.inputs[1])

    # Lerp(prev_verlet, tracked, factor) — _vector_lerp itself spans
    # 3 columns (x+600 .. x+1000).
    lerp_node = _vector_lerp(
        tree, x + 600, y, f"{label} Plm",
        a_out=sim_in_pos_socket,
        b_out=tracked.outputs['Vector'],
        factor_out=arm_factor_socket)

    # First-frame init mix: rest on frame 1, lerp thereafter. Mirrors
    # the body Verlet's snap-to-rest-on-init pattern. Without this the
    # whole palm cluster snaps to ~origin on Create Marionette because
    # sim_in is still at default (0,0,0).
    rest_sc = add_node(
        tree, 'ShaderNodeVectorMath', x + 1200, y, f"{label} rSc")
    rest_sc.operation = 'SCALE'
    tree.links.new(rest_socket, rest_sc.inputs[0])
    tree.links.new(init_cmp_out, rest_sc.inputs['Scale'])

    run_sc = add_node(
        tree, 'ShaderNodeVectorMath', x + 1200, y - 120, f"{label} nSc")
    run_sc.operation = 'SCALE'
    tree.links.new(lerp_node.outputs['Vector'], run_sc.inputs[0])
    tree.links.new(not_first_out, run_sc.inputs['Scale'])

    init_sum = add_node(
        tree, 'ShaderNodeVectorMath', x + 1400, y - 60, f"{label} Init")
    init_sum.operation = 'ADD'
    tree.links.new(rest_sc.outputs['Vector'], init_sum.inputs[0])
    tree.links.new(run_sc.outputs['Vector'], init_sum.inputs[1])

    return init_sum.outputs['Vector']


# =============================================================================
# CHAIN SEGMENT PHYSICS (alpha.54 / step 3d)
# =============================================================================
# One PP_ChainVerletSegment instance + Jakobsen distance constraint +
# first-frame init, all wired to a pair of sim-zone state items
# (`pos_<chain>_<side>_seg<N>` / `prev_<chain>_<side>_seg<N>`).
#
# This is the work that NATIVE_PHYSICS_DESIGN.md called "Step 10 — Wire
# chain physics," with the dropout-delta wiring from §Delta 3 layered on:
# tracked chains (fingerA, fingerB) wire `Tracked Tip` ← bt_thumb/index
# and `Tip Pull Live` ← Hand <S> Live; untracked chains (fingerC, fingerD)
# leave both at sub-group default (Live=0.0 zeroes the term).
#
# Caller responsibilities (mirrors NATIVE_PHYSICS_DESIGN.md §Reusable GN
# Sub-Groups for `PP_ChainVerletSegment` — kept identical so the existing
# unit-test against the Python prototype still applies):
#   - Goal: world-space rest pose (palm-pos + yaw-mirrored offset).
#   - Parent Pos: anchor for seg 0, previous segment's constrained pos
#     for seg 1+. The Jakobsen pass projects new pos onto a sphere of
#     `seg_length` around this socket.
#   - Per-segment RFF + EFS pre-baked from preset (hardcoded as
#     default_value on the sub-group inputs — see RFF_PER_SEG above).
#   - First-frame init: handled here (mix to Goal on frame 1) so the
#     sub-group stays pure and unit-testable for any mid-sim frame.

def _add_chain_segment_physics(
        tree, x, y, label,
        sim_in, sim_out, group_in,
        pos_name, prev_name,
        parent_pos_socket, goal_socket,
        rff, efs, seg_length,
        init_cmp_out, not_first_out,
        tracked_tip_socket=None,
        hand_live_socket=None):
    """Instantiate one chain segment + constraint + init. Returns its
    constrained pos socket so the next segment can use it as Parent Pos.

    Layout span: ~13 columns × 200 = 2600 px wide, 3 rows tall.
        row 0  (y)         chain group + Jakobsen
        row 1  (y - 220)   first-frame init (pos)
        row 2  (y - 360)   first-frame init (prev)
    """
    chain_group = _ensure_chain_segment_group()
    dx = 200

    pos_in = sim_in.outputs[pos_name]
    prev_in = sim_in.outputs[prev_name]

    # --- PP_ChainVerletSegment instance (collapses ~22 nodes into one) ---
    grp = add_node(tree, 'GeometryNodeGroup', x, y, f"{label} Chain")
    grp.node_tree = chain_group

    tree.links.new(pos_in, grp.inputs['Pos'])
    tree.links.new(prev_in, grp.inputs['Prev'])
    tree.links.new(parent_pos_socket, grp.inputs['Parent Pos'])
    tree.links.new(goal_socket, grp.inputs['Goal'])

    # Per-segment factors hardcoded (no runtime tuning — see RFF_PER_SEG).
    grp.inputs['Root Falloff Factor'].default_value = rff
    grp.inputs['End Factor Scale'].default_value = efs

    # Frame timestep — sim_in already exposes it as the zone's Delta Time.
    tree.links.new(sim_in.outputs['Delta Time'], grp.inputs['Delta Time'])

    # 7 runtime-tunable chain params from the modifier interface.
    for param in CHAIN_PARAM_SOCKETS:
        tree.links.new(group_in.outputs[param], grp.inputs[param])

    # Tip pull — wire only for tracked chains. Sub-group defaults
    # (Tip Pull Live = 0.0, Tracked Tip = (0,0,0), Tip Pull Strength
    # = 0.6) leave the term identically zero for untracked chains, so
    # there's no need to plug in fingerC / fingerD.
    if tracked_tip_socket is not None and hand_live_socket is not None:
        tree.links.new(tracked_tip_socket, grp.inputs['Tracked Tip'])
        tree.links.new(hand_live_socket, grp.inputs['Tip Pull Live'])
        grp.inputs['Tip Pull Strength'].default_value = (
            physics_presets.TIP_PULL_STRENGTH)

    new_pos_raw = grp.outputs['New Pos']

    # --- Jakobsen distance constraint: project new pos onto sphere of
    #     `seg_length` around Parent Pos. Same pattern as the body
    #     Verlet endpoints (off → normalize → scale → add). ---
    off = add_node(
        tree, 'ShaderNodeVectorMath', x + dx * 1, y - 80, f"{label} Off")
    off.operation = 'SUBTRACT'
    tree.links.new(new_pos_raw, off.inputs[0])
    tree.links.new(parent_pos_socket, off.inputs[1])

    nrm = add_node(
        tree, 'ShaderNodeVectorMath', x + dx * 2, y - 80, f"{label} Nrm")
    nrm.operation = 'NORMALIZE'
    tree.links.new(off.outputs['Vector'], nrm.inputs[0])

    scl = add_node(
        tree, 'ShaderNodeVectorMath', x + dx * 3, y - 80, f"{label} *L")
    scl.operation = 'SCALE'
    tree.links.new(nrm.outputs['Vector'], scl.inputs[0])
    scl.inputs['Scale'].default_value = seg_length

    con = add_node(
        tree, 'ShaderNodeVectorMath', x + dx * 4, y - 80, f"{label} Con")
    con.operation = 'ADD'
    tree.links.new(parent_pos_socket, con.inputs[0])
    tree.links.new(scl.outputs['Vector'], con.inputs[1])

    constrained_pos = con.outputs['Vector']

    # --- First-frame init (mirror of _add_verlet_endpoint pattern) ---
    # On frame 1 we snap to Goal; otherwise we use the constrained
    # physics result. Same trick: scale Goal by is_first, scale physics
    # by not_first, sum the two — exactly one is non-zero so the sum
    # is just the chosen branch with no Switch node + no socket-index
    # fragility.
    rest_sc = add_node(
        tree, 'ShaderNodeVectorMath', x + dx * 1, y - 220, f"{label} rSc")
    rest_sc.operation = 'SCALE'
    tree.links.new(goal_socket, rest_sc.inputs[0])
    tree.links.new(init_cmp_out, rest_sc.inputs['Scale'])

    con_sc = add_node(
        tree, 'ShaderNodeVectorMath', x + dx * 2, y - 220, f"{label} cSc")
    con_sc.operation = 'SCALE'
    tree.links.new(constrained_pos, con_sc.inputs[0])
    tree.links.new(not_first_out, con_sc.inputs['Scale'])

    fp = add_node(
        tree, 'ShaderNodeVectorMath', x + dx * 3, y - 220, f"{label} Pos")
    fp.operation = 'ADD'
    tree.links.new(con_sc.outputs['Vector'], fp.inputs[0])
    tree.links.new(rest_sc.outputs['Vector'], fp.inputs[1])

    pos_sc = add_node(
        tree, 'ShaderNodeVectorMath', x + dx * 2, y - 360, f"{label} pSc")
    pos_sc.operation = 'SCALE'
    tree.links.new(pos_in, pos_sc.inputs[0])
    tree.links.new(not_first_out, pos_sc.inputs['Scale'])

    fpr = add_node(
        tree, 'ShaderNodeVectorMath', x + dx * 3, y - 360, f"{label} Prv")
    fpr.operation = 'ADD'
    tree.links.new(pos_sc.outputs['Vector'], fpr.inputs[0])
    tree.links.new(rest_sc.outputs['Vector'], fpr.inputs[1])

    # --- Wire to sim_out (replaces physics.py's passthrough wiring) ---
    tree.links.new(fp.outputs['Vector'], sim_out.inputs[pos_name])
    tree.links.new(fpr.outputs['Vector'], sim_out.inputs[prev_name])

    return fp.outputs['Vector']


# =============================================================================
# FINGER CHAIN PHYSICS (alpha.54 / step 3d) — 2-seg chain per finger
# =============================================================================
# Wires up both segments of one finger. Computes:
#   - anchor_pos (seg 0's parent)         — palm + anchor offset
#   - goal_seg0  (seg 0's rest pose)      — palm + (anchor + dir × L)
#   - goal_seg1  (seg 1's rest pose)      — palm + (anchor + dir × 2L)
# All three are palm-relative offsets baked through `_palm_offset_vec`,
# which is the same helper the geometry side uses — keeps the chain
# physics's "where is the palm right now" and the geometry's "where to
# anchor the tube" sourced from the same compute path (the in-zone
# palm position lerp), so the visual finger root and the physics
# anchor stay co-located.

def _build_finger_chain_physics(
        tree, x, y, side, chain_name,
        sim_in, sim_out, group_in,
        palm_pos_inside_zone_socket,
        basis_x_socket, basis_y_socket, basis_z_socket,
        init_cmp_out, not_first_out,
        tracked_tip_socket=None,
        hand_live_socket=None):
    """Build the 2-segment chain physics for one finger.

    Vertical span: 2 segments × 480 = 960 px.
    Horizontal span: ~13 cols × 200 = 2600 px (set by chain segment helper).

    alpha.57: anchor + per-segment goals are now computed via
    `_palm_offset_vec_basis` (palm + tracked_basis × local_offset). The
    local offsets remain Python tuples — only the rotation has moved
    from a per-side constant (`_yaw_mirror_for_side`) to a per-frame
    basis matrix from the receiver.
    """
    rest = CHAIN_REST[chain_name]
    # Local-space (palm-frame) offsets — constants. The basis rotation
    # at _palm_offset_vec_basis takes them into world space each frame.
    anchor_off = rest['anchor']
    rest_dir = rest['dir']

    label = f"{chain_name}.{side}"

    # Per-segment local offsets — anchor + (N + 1) × seg_length × rest_dir.
    # All in palm-local frame; basis rotation happens at the offset_vec call.
    seg0_off = (
        anchor_off[0] + rest_dir[0] * FINGER_SEG_LENGTH,
        anchor_off[1] + rest_dir[1] * FINGER_SEG_LENGTH,
        anchor_off[2] + rest_dir[2] * FINGER_SEG_LENGTH,
    )
    seg1_off = (
        seg0_off[0] + rest_dir[0] * FINGER_SEG_LENGTH,
        seg0_off[1] + rest_dir[1] * FINGER_SEG_LENGTH,
        seg0_off[2] + rest_dir[2] * FINGER_SEG_LENGTH,
    )

    # Anchor + per-segment goals (world-space). Each one rotates the
    # constant local offset by the live palm basis and adds palm pos.
    anchor_pos = _palm_offset_vec_basis(
        tree, x, y, f"{label} A", palm_pos_inside_zone_socket,
        basis_x_socket, basis_y_socket, basis_z_socket, anchor_off)
    goal_seg0 = _palm_offset_vec_basis(
        tree, x, y - 200, f"{label} G0",
        palm_pos_inside_zone_socket,
        basis_x_socket, basis_y_socket, basis_z_socket, seg0_off)
    goal_seg1 = _palm_offset_vec_basis(
        tree, x, y - 400, f"{label} G1",
        palm_pos_inside_zone_socket,
        basis_x_socket, basis_y_socket, basis_z_socket, seg1_off)

    pos_name_0 = f'pos_{chain_name}_{side}_seg0'
    prev_name_0 = f'prev_{chain_name}_{side}_seg0'
    pos_name_1 = f'pos_{chain_name}_{side}_seg1'
    prev_name_1 = f'prev_{chain_name}_{side}_seg1'

    # Seg 0 — parent is the palm anchor.
    seg0_pos = _add_chain_segment_physics(
        tree, x + 400, y, f"{label} S0",
        sim_in, sim_out, group_in,
        pos_name_0, prev_name_0,
        parent_pos_socket=anchor_pos,
        goal_socket=goal_seg0,
        rff=RFF_PER_SEG[0], efs=EFS_PER_SEG[0],
        seg_length=FINGER_SEG_LENGTH,
        init_cmp_out=init_cmp_out,
        not_first_out=not_first_out,
        tracked_tip_socket=tracked_tip_socket,
        hand_live_socket=hand_live_socket)

    # Seg 1 — parent is seg 0's constrained pos. Tip pull pulls toward
    # the same tracked tip socket so the 2-link arm orients toward
    # the tracker; the Jakobsen pass keeps both segments at FINGER_SEG_LENGTH
    # from their parent so the chain stays at the right total length.
    _add_chain_segment_physics(
        tree, x + 400, y - 480, f"{label} S1",
        sim_in, sim_out, group_in,
        pos_name_1, prev_name_1,
        parent_pos_socket=seg0_pos,
        goal_socket=goal_seg1,
        rff=RFF_PER_SEG[1], efs=EFS_PER_SEG[1],
        seg_length=FINGER_SEG_LENGTH,
        init_cmp_out=init_cmp_out,
        not_first_out=not_first_out,
        tracked_tip_socket=tracked_tip_socket,
        hand_live_socket=hand_live_socket)


def _add_finger_chain(tree, x, y, parts_geo, side, chain_name,
                      palm_pos_socket,
                      basis_x_socket, basis_y_socket, basis_z_socket,
                      profile, mat_limb_socket,
                      mat_joint_socket, sim_out):
    """Build one finger's two tubes + one mid-joint bead. Adds 3 geo sockets.

    The fingertip bead (J1) was dropped as a perf cut — the tube's
    Curve-to-Mesh endpoint already closes off cleanly, so J1 was
    just a decorative cap that cost ~16 tris per finger × 8 fingers.
    Mid-joint bead (J0) is kept — it's the visible knuckle and reads
    as an articulation point when fingers bend.

    alpha.54 (step 3d): seg 0 + seg 1 positions now come straight from
    `sim_out.outputs[pos_<chain>_<side>_seg{0,1}]` — the chain physics
    sub-zone wired in by `_build_finger_chain_physics` writes the
    constrained Verlet positions there. The previous `_with_fallback`
    branch on tracked tips is gone: when MediaPipe drops a hand, the
    receiver ramps `Hand <S> Live` to 0, the chain's tip-pull term
    zeroes out, and the chain dangles freely under gravity + goal
    pull. That IS the fallback now — Live = 0 doesn't snap to a
    constant rest pose, it just lets physics take over. Untracked
    chains (fingerC, fingerD) leave Live at the sub-group default
    (0.0) so they always run as plain chain sim.
    """
    rest = CHAIN_REST[chain_name]
    # alpha.57: palm-local anchor (constant tuple); basis rotation at
    # _palm_offset_vec_basis takes it to world space using the live
    # tracked palm orientation.
    anchor_off = rest['anchor']

    label = f"{chain_name}.{side}"
    anchor_pos = _palm_offset_vec_basis(
        tree, x - 600, y, f"{label} A", palm_pos_socket,
        basis_x_socket, basis_y_socket, basis_z_socket, anchor_off)

    # Read the chain physics output. Each segment's pos socket on
    # sim_out is wired by `_build_finger_chain_physics` (Jakobsen-
    # constrained physics result, mixed with rest pose on frame 1).
    seg0_pos = sim_out.outputs[f'pos_{chain_name}_{side}_seg0']
    seg1_pos = sim_out.outputs[f'pos_{chain_name}_{side}_seg1']

    # Two tubes: anchor → seg0, seg0 → seg1.
    # The anchor end is computed from the post-zone palm position
    # (`palm_pos_socket = hand_l/r_pos` from body_parts.py); the seg
    # end is the in-zone physics result. The two could be 33ms out of
    # phase under fast BT toggling — invisible at 30 FPS, well inside
    # the chain's own settle response.
    _add_finger_tube(tree, x + 200, y, parts_geo, f"{label} T0",
                     profile, anchor_pos, seg0_pos, mat_limb_socket)
    _add_finger_tube(tree, x + 200, y - 60, parts_geo, f"{label} T1",
                     profile, seg0_pos, seg1_pos, mat_limb_socket)

    # One joint bead at the mid-knuckle (seg0). The fingertip (seg1)
    # relies on the tube's cap alone — see docstring.
    _add_finger_joint(tree, x + 200, y - 120, parts_geo,
                      f"{label} J0", seg0_pos, mat_joint_socket)


# =============================================================================
# BUILD_HANDS — the section entry point
# =============================================================================
# Compose both hands in two passes:
#
#   PASS 1 (alpha.54 / step 3d) — Chain physics INSIDE the sim zone.
#       For each side, compute an in-zone palm position (mirrors the
#       post-zone hand_<S>_pos blend with one frame of Verlet lag),
#       then instantiate `PP_ChainVerletSegment` per finger segment
#       (4 fingers × 2 segs × 2 sides = 16 instances). Each instance
#       writes its constrained pos + prev to the matching state items
#       on sim_out, replacing the passthrough wiring physics.py set up
#       as a defensive default.
#
#   PASS 2 — Geometry OUTSIDE the sim zone.
#       Palm plate + 4 corner beads + 4 finger tubes per side, reading
#       the physics-driven seg positions back out of sim_out.outputs.
#
# The whole section gets wrapped in a "body"-colored Frame labeled
# THE HANDS so the GN editor reads as one visual block.

def build_hands(tree, group_in, sim_in, sim_out, body_mats,
                shl_visual, shr_visual,
                arm_l_factor, arm_r_factor,
                palm_l_pos, palm_r_pos,
                rest_hl, rest_hr,
                init_cmp_out, not_first_out,
                snap_state):
    """Build Section 9.5: chain physics + palm/finger geometry per side.

    Called between build_body_parts and build_studio_track in assembly.py.
    Returns a dict with parts_geo (geometry sockets to join at assembly
    time) and snap_state (post-section snapshot for downstream framing).

    Parameters
    ----------
    sim_in, sim_out
        Simulation zone endpoints from build_physics. Chain segment
        instances read pos/prev state from sim_in and write back to
        sim_out for both hands' 32 finger-chain state items.
    shl_visual, shr_visual
        Shoulder visual position nodes (computed pre-zone in
        assembly.py). Read inside the zone for the in-zone palm
        position blend (recomputes the body_parts.py tracked-hand
        formula with frame-fresh group_in values).
    arm_l_factor, arm_r_factor
        Math nodes (Body Tracking × vis_arm_<S>) from body_movement.py.
        Reused as the lerp factor for the in-zone palm blend so the
        chain anchor matches body_parts.py's post-zone hand position
        whenever BT is active.
    palm_l_pos, palm_r_pos
        Post-zone hand positions (`hand_<S>_pos` from body_parts.py).
        Used by the geometry pass for the palm plate, palm corner
        beads, and the anchor end of finger tube T0.
    rest_hl, rest_hr
        Rest-pose hand positions (the dead-hang dangle from each
        shoulder). alpha.55: passed into `_palm_pos_inside_zone` as
        the frame-1 fallback so the in-zone palm doesn't collapse to
        origin while sim_in is still at its default (0,0,0).
    init_cmp_out, not_first_out
        First-frame init plumbing from build_physics. On frame 1 the
        chain segments snap to their rest-pose Goal; thereafter they
        run physics. Same convention as `_add_verlet_endpoint`. Also
        used by the in-zone palm-pos init mix (alpha.55).

    alpha.54 (step 3d) is the structural change that activates the
    dropout fix: each tracked finger segment now wires `Tip Pull Live`
    ← `Hand <S> Live` (the receiver-driven liveness float). When MP
    drops the hand, the receiver ramps Live to 0, the chain's tip-pull
    term zeroes out, and the chain runs as a free Verlet rope under
    gravity + goal pull — that IS the fallback. The previous
    `_with_fallback` switch (which snapped to a constant rest pose)
    is gone.
    """
    _s = snap_state
    parts_geo = []

    # ----------------------------------------------------------------------
    # PASS 1 — Chain physics inside the sim zone
    # ----------------------------------------------------------------------
    # Layout: each side gets its own column of 4 fingers × 2 segments
    # stacked vertically below body_parts.py's last y. x range fits
    # within the sim zone's visual bounds (-600 .. 1400) so the editor
    # reads as "physics nodes inside the zone, geometry past it."
    #
    # Per-side header — palm pos blend node cluster (~7 nodes), then
    # 4 fingers × 2 segments below it. Per-finger Y stride is 1000
    # (480 between segs of one finger + ~500 padding before next).
    x_chain_phys = 200
    y_chain_top = -3500
    y_per_side = 4400
    y_per_finger = 1000

    # Per-side tracked-tip mapping. fingerA (cartoon thumb) follows
    # MediaPipe THUMB_TIP (landmark 4); fingerB (cartoon pointer/middle)
    # follows MediaPipe INDEX_TIP (landmark 8) per HAND_TRACKING_DESIGN.md
    # (the anatomical index drives the visually-centered cartoon finger).
    # fingerC and fingerD are untracked — chain sim only.
    tracked_tips_by_side = {
        'l': {
            'fingerA': group_in.outputs['bt_thumb_l'],
            'fingerB': group_in.outputs['bt_index_l'],
        },
        'r': {
            'fingerA': group_in.outputs['bt_thumb_r'],
            'fingerB': group_in.outputs['bt_index_r'],
        },
    }
    hand_live_by_side = {
        'l': group_in.outputs['Hand L Live'],
        'r': group_in.outputs['Hand R Live'],
    }
    shoulder_visual_by_side = {
        'l': shl_visual.outputs['Vector'],
        'r': shr_visual.outputs['Vector'],
    }
    arm_factor_by_side = {
        'l': arm_l_factor.outputs['Value'],
        'r': arm_r_factor.outputs['Value'],
    }
    rest_pos_by_side = {
        'l': rest_hl.outputs['Vector'],
        'r': rest_hr.outputs['Vector'],
    }

    # Palm basis sockets (alpha.56 receiver push). palm_x = across the
    # palm (radial→ulnar), palm_y = wrist→fingers in palm plane; the
    # third basis vector palm_z is computed here once per side via cross
    # product (1 node × 2 sides) and reused across every basis-rotate
    # call below — saves ~10 redundant cross products per build.
    basis_x_by_side = {
        'l': group_in.outputs['palm_x_l'],
        'r': group_in.outputs['palm_x_r'],
    }
    basis_y_by_side = {
        'l': group_in.outputs['palm_y_l'],
        'r': group_in.outputs['palm_y_r'],
    }
    basis_z_by_side = {
        side: _palm_basis_z(
            tree, x_chain_phys - 400, y_chain_top + 200 - i * 100,
            f"Plm{side.upper()}",
            basis_x_by_side[side], basis_y_by_side[side])
        for i, side in enumerate(HAND_SIDES)
    }

    for side_idx, side in enumerate(HAND_SIDES):
        y_side_top = y_chain_top - side_idx * y_per_side

        # In-zone palm position (~10 nodes — alpha.55 added 3 for the
        # first-frame init mix). Mirror of body_parts.py's hand_<S>_pos
        # blend, computed with sim_in (one-frame Verlet lag) and
        # frame-fresh group_in values, then snapped to rest on frame 1.
        # Reused across all 8 of this side's segments so the cluster
        # pays for itself.
        palm_inside_zone = _palm_pos_inside_zone(
            tree, x_chain_phys, y_side_top + 400,
            f"Plm{side.upper()}", side, group_in,
            shoulder_visual_socket=shoulder_visual_by_side[side],
            arm_factor_socket=arm_factor_by_side[side],
            sim_in_pos_socket=sim_in.outputs[f'pos_hand_{side}'],
            rest_socket=rest_pos_by_side[side],
            init_cmp_out=init_cmp_out,
            not_first_out=not_first_out)

        tracked_tips = tracked_tips_by_side[side]
        for f_idx, chain in enumerate(HAND_CHAINS):
            y_chain = y_side_top - f_idx * y_per_finger

            tracked_tip = tracked_tips.get(chain)
            hand_live = (
                hand_live_by_side[side] if tracked_tip is not None else None)

            _build_finger_chain_physics(
                tree, x_chain_phys, y_chain, side, chain,
                sim_in, sim_out, group_in,
                palm_pos_inside_zone_socket=palm_inside_zone,
                basis_x_socket=basis_x_by_side[side],
                basis_y_socket=basis_y_by_side[side],
                basis_z_socket=basis_z_by_side[side],
                init_cmp_out=init_cmp_out,
                not_first_out=not_first_out,
                tracked_tip_socket=tracked_tip,
                hand_live_socket=hand_live)

    _frame_section(tree,
        "HAND PHYSICS — Per-finger 2-segment chain Verlet."
        " Tracked chains reach for MP tips (Live-gated tip pull);"
        " untracked chains dangle freely under gravity + goal pull.",
        'verlet', _new_nodes(tree, _s))
    _s = _snap_nodes(tree)

    # ----------------------------------------------------------------------
    # PASS 2 — Geometry outside the sim zone
    # ----------------------------------------------------------------------
    # Palm plate + corner beads + finger tubes/joints. The seg
    # positions read straight from sim_out — we don't recompute or
    # `_with_fallback` anything here. Live-gated chain physics IS the
    # fallback now.
    x_hands = 2900

    # Shared finger profile — one curve circle, reused across all eight
    # finger tubes (4 chains × 2 segments each, × 2 sides = 16 tubes).
    profile = add_node(tree, 'GeometryNodeCurvePrimitiveCircle',
                       x_hands - 400, -2400, "Finger Profile")
    profile.mode = 'RADIUS'
    profile.inputs['Radius'].default_value = FINGER_SEG_RADIUS
    profile.inputs['Resolution'].default_value = 6

    # Material sockets we'll pass down into every helper below.
    mat_hand = group_in.outputs['Hand Material']
    mat_limb = group_in.outputs['Limb Material']
    mat_joint = group_in.outputs['Joint Material']

    # Build each side. Same recipe, different palm position socket +
    # side label. Y-stride = 900 per side gives enough vertical room
    # for the 4 finger rows (60 apart) + corner row + palm row.
    sides = (
        ('l', palm_l_pos),
        ('r', palm_r_pos),
    )
    for side_idx, (side, palm_pos) in enumerate(sides):
        y_base = -1900 - side_idx * 900
        bx = basis_x_by_side[side]
        by = basis_y_by_side[side]
        bz = basis_z_by_side[side]

        # Palm plate (1 geo socket) — built directly in basis space so
        # plate + corners + finger anchors all share one orientation.
        _add_palm_plate(tree, x_hands, y_base, parts_geo, side,
                        palm_pos, bx, by, bz, mat_hand)

        # 3 palm beads render (4 geo sockets). Stacked rows below the
        # palm plate so the GN editor is readable. SW corner is the
        # thumb knuckle and gets a bigger bead than the other two
        # — cartoon proportions, not corner-of-a-rectangle proportions.
        #
        # The SE corner gets NO bead: real palms don't have a bony
        # bump on the pinky-side wrist, and the tapered palm edge
        # reads fine on its own there. The state-item slot for 'se'
        # is still reserved in physics.py's PALM_CORNERS (for future
        # jiggle math in step 11) — just nothing to render on it here.
        # alpha.57: corner_offset is the constant palm-local offset;
        # _add_palm_corner basis-rotates it to world space each frame.
        for c_idx, corner in enumerate(PALM_BEAD_CORNERS):
            corner_off = PALM_CORNER_OFFSETS[corner]
            radius = (THUMB_KNUCKLE_RADIUS if corner == 'sw'
                      else PALM_CORNER_RADIUS)
            _add_palm_corner(tree, x_hands, y_base - 120 - c_idx * 80,
                             parts_geo, side, corner, palm_pos,
                             bx, by, bz,
                             corner_off, mat_hand, radius=radius)

        # 4 finger chains, 3 geo sockets each (2 tubes + 1 mid-joint
        # bead). The seg positions come from the physics pass above.
        for f_idx, chain in enumerate(HAND_CHAINS):
            y_chain = y_base - 480 - f_idx * 60
            _add_finger_chain(tree, x_hands, y_chain, parts_geo,
                              side, chain, palm_pos,
                              bx, by, bz,
                              profile,
                              mat_limb, mat_joint, sim_out)

    _frame_section(tree,
        "THE HANDS — Palm plate + 4 corner beads + 4 finger chains"
        " per side (geometry; seg positions read from chain physics)",
        'body', _new_nodes(tree, _s))
    snap_state = _snap_nodes(tree)

    return {
        'parts_geo': parts_geo,
        'snap_state': snap_state,
    }
