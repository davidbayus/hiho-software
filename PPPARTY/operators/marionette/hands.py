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
    build_hands(tree, group_in, sim_out, body_mats, hand_l_pos, hand_r_pos,
                snap_state)
        Build both hands' geometry (palm + 4 corners + 4 finger chains
        each, × 2 sides). Wrap with a "THE HANDS" frame. Return a dict
        with parts_geo (geometry sockets to join at assembly time) and
        snap_state (the post-section snapshot, so assembly can keep the
        "frame what's new" pattern running).

The signature mirrors build_body_parts's — same (tree, group_in, sim_out,
body_mats, …, snap_state) shape, same dict-return convention — so it
slots into assembly.py between build_body_parts and build_studio_track
with one call.
"""

import math

from ._common import (add_node, _frame_section,
                      _snap_nodes, _new_nodes)


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


def _yaw_mirror_for_side(vec, side):
    """Mirror X then yaw around Z, both keyed to hand side.

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
    yaw = -_PALM_YAW_RAD if side == 'l' else _PALM_YAW_RAD
    c = math.cos(yaw)
    s = math.sin(yaw)
    x = vec[0] * mx
    y = vec[1]
    return (x * c - y * s, x * s + y * c, vec[2])


def _palm_yaw_for_side(side):
    """Z-axis yaw angle (radians) applied to the palm plate per side."""
    return -_PALM_YAW_RAD if side == 'l' else _PALM_YAW_RAD


# =============================================================================
# PALM OFFSET HELPER — palm_pos + constant offset
# =============================================================================
# Every piece of hand geometry lives at a position of the form
#   palm_position + local_offset
# where palm_position is a *socket* (comes from body_parts.py — it's the
# hand_l_pos or hand_r_pos lerp output) and local_offset is a constant
# tuple we chose at code-write time. A three-node subtree does the sum:
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

    # --- Translate to palm center ---------------------------------------
    center_off = (0.0, 0.0, _PALM_CENTER_Z_BIAS)
    center_pos = _palm_offset_vec(
        tree, x, y + 100, f"Palm{side.upper()} C",
        palm_pos_socket, center_off)

    tf = add_node(tree, 'GeometryNodeTransform', x + 1000, y,
                  f"Palm {side} TF")
    tree.links.new(set_pos.outputs['Geometry'], tf.inputs['Geometry'])
    tree.links.new(center_pos, tf.inputs['Translation'])
    # Yaw the plate around Z so it matches the rotated corner/finger
    # offsets from _yaw_mirror_for_side. -45° for L, +45° for R.
    tf.inputs['Rotation'].default_value = (0.0, 0.0,
                                           _palm_yaw_for_side(side))

    sm = add_node(tree, 'GeometryNodeSetShadeSmooth', x + 1200, y,
                  f"Palm {side} Sm")
    tree.links.new(tf.outputs['Geometry'], sm.inputs['Geometry'])

    mt = add_node(tree, 'GeometryNodeSetMaterial', x + 1400, y,
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
                     palm_pos_socket, corner_offset, mat_socket,
                     radius=PALM_CORNER_RADIUS):
    """Small sphere at one palm corner. Adds 1 geo socket.

    `radius` defaults to the regular palm-corner bead size, but the SW
    corner (thumb knuckle) bumps up to THUMB_KNUCKLE_RADIUS so the thumb
    reads as a distinct, chunkier knuckle rather than a fourth corner.
    """
    corner_pos = _palm_offset_vec(
        tree, x, y + 100,
        f"Palm{side.upper()}.{corner_label}",
        palm_pos_socket, corner_offset)

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
    """Small UV sphere at a finger joint. Adds 1 geo socket."""
    sphere = add_node(tree, 'GeometryNodeMeshUVSphere', x, y, label)
    sphere.inputs['Segments'].default_value = 8
    sphere.inputs['Rings'].default_value = 6
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

def _add_finger_chain(tree, x, y, parts_geo, side, chain_name,
                      palm_pos_socket, profile, mat_limb_socket,
                      mat_joint_socket):
    """Build one finger's two segments + two joint beads. Adds 4 geo sockets."""
    rest = CHAIN_REST[chain_name]
    anchor_off = _yaw_mirror_for_side(rest['anchor'], side)
    rest_dir = _yaw_mirror_for_side(rest['dir'], side)

    # Cumulative offsets for each segment endpoint (from palm center).
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

    label = f"{chain_name}.{side}"
    anchor_pos = _palm_offset_vec(
        tree, x - 200, y, f"{label} A", palm_pos_socket, anchor_off)
    seg0_pos = _palm_offset_vec(
        tree, x - 200, y - 60, f"{label} S0", palm_pos_socket, seg0_off)
    seg1_pos = _palm_offset_vec(
        tree, x - 200, y - 120, f"{label} S1", palm_pos_socket, seg1_off)

    # Two tubes: anchor → seg0, seg0 → seg1
    _add_finger_tube(tree, x + 200, y, parts_geo, f"{label} T0",
                     profile, anchor_pos, seg0_pos, mat_limb_socket)
    _add_finger_tube(tree, x + 200, y - 60, parts_geo, f"{label} T1",
                     profile, seg0_pos, seg1_pos, mat_limb_socket)

    # Two joint beads: one at mid (seg0), one at tip (seg1)
    _add_finger_joint(tree, x + 200, y - 120, parts_geo,
                      f"{label} J0", seg0_pos, mat_joint_socket)
    _add_finger_joint(tree, x + 200, y - 180, parts_geo,
                      f"{label} J1", seg1_pos, mat_joint_socket)


# =============================================================================
# BUILD_HANDS — the section entry point
# =============================================================================
# Compose both hands:
#   for each side in (l, r):
#       palm plate + 4 corner beads + 4 finger chains
#
# The whole section gets wrapped in a "body"-colored Frame labeled
# THE HANDS so the GN editor reads as one visual block.

def build_hands(tree, group_in, sim_out, body_mats,
                hand_l_pos, hand_r_pos, snap_state):
    """Build Section 9.5: palm plates + palm corners + 4 finger chains per side.

    Called between build_body_parts and build_studio_track in assembly.py.
    Returns a dict with parts_geo (geometry sockets to join at assembly
    time) and snap_state (post-section snapshot for downstream framing).

    Step 7 of the 14-step NATIVE_PHYSICS_DESIGN plan: geometry only.
    Physics wiring (chain sim on fingers, jiggle on corners) lands in
    steps 10 and 11 — this module will be revisited then to read
    sim_out's hand state items instead of computing positions inline.
    """
    _s = snap_state
    x_hands = 2900
    parts_geo = []

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
        ('l', hand_l_pos),
        ('r', hand_r_pos),
    )
    for side_idx, (side, palm_pos) in enumerate(sides):
        y_base = -1900 - side_idx * 900

        # Palm plate (1 geo socket)
        _add_palm_plate(tree, x_hands, y_base, parts_geo, side,
                        palm_pos, mat_hand)

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
        for c_idx, corner in enumerate(PALM_BEAD_CORNERS):
            # Mirror + yaw the offset per side so left/right palms
            # end up in the relaxed-arm pose with thumbs swinging
            # forward and outward.
            corner_off = _yaw_mirror_for_side(
                PALM_CORNER_OFFSETS[corner], side)
            radius = (THUMB_KNUCKLE_RADIUS if corner == 'sw'
                      else PALM_CORNER_RADIUS)
            _add_palm_corner(tree, x_hands, y_base - 120 - c_idx * 80,
                             parts_geo, side, corner, palm_pos,
                             corner_off, mat_hand, radius=radius)

        # 4 finger chains, 4 geo sockets each (2 tubes + 2 joint beads)
        # → 16 per side. Stack them below the corner block.
        for f_idx, chain in enumerate(HAND_CHAINS):
            y_chain = y_base - 480 - f_idx * 60
            _add_finger_chain(tree, x_hands, y_chain, parts_geo,
                              side, chain, palm_pos, profile,
                              mat_limb, mat_joint)

    _frame_section(tree,
        "THE HANDS — Palm plate + 4 corner beads + 4 finger chains"
        " per side (rest pose; physics wiring in steps 10/11)",
        'body', _new_nodes(tree, _s))
    snap_state = _snap_nodes(tree)

    return {
        'parts_geo': parts_geo,
        'snap_state': snap_state,
    }
