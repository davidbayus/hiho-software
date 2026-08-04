# SPDX-License-Identifier: GPL-3.0-or-later
"""Body parts — composition on top of the capsule primitive.

=============================================================================
What "body parts" means here
=============================================================================
Every piece of the marionette below the head is one of three shapes:

    1. A dynamic capsule — chest, pelvis, hand, foot, shoulder, cheek
    2. A small UV sphere — waist bead, hip bead, elbow, knee
    3. A curve tube — upper arm, forearm, thigh, shin, neck

capsules.py gives us the pill-shaped primitive. body_parts.py takes that
primitive (or a sphere, or a curve) and dresses it up into a named body
part: place it with a Transform node, shade it smooth, assign a material,
and append the result to the running list of geometry outputs that get
joined into the final puppet mesh at the end.

=============================================================================
Composition, not invention
=============================================================================
There is no new math in this file. Every function here is a recipe:
"take a primitive, put it here, paint it this color, remember you made it."
The interesting math lives in capsules.py (the Minkowski pill) and
physics.py (Verlet + IK). Body parts is the *layout* step — the page
designer, not the writer.

That split is deliberate. Reading this file should feel like watching the
same 4-node pattern (primitive → Transform → Set Shade Smooth → Set
Material) get applied to every limb and joint on the rig. Teaching goal:
each body part is three or four nodes of setup around one primitive —
everything else is repetition.

=============================================================================
Public entry points
=============================================================================
    add_capsule_part(tree, x_part, parts_geo, y, label, radius, pos_socket,
                     mat, ...)
        The workhorse. Dynamic capsule + Transform + Set Shade Smooth +
        Set Material. Supports optional driven rotation, tilt, depth
        offset, uniform scale, and a material socket override.

    add_sphere_part(tree, x_part, parts_geo, y, label, radius, pos_socket,
                    mat, ...)
        Small UV sphere for joint beads (waist, hips, elbows, knees).

    add_limb(tree, x_limb, profile, parts_geo, y, label, start_socket,
             end_socket, mat, ...)
        Line-to-tube between two socket positions, using the shared
        Curve Circle `profile` as the tube cross-section. Used for upper
        arms, forearms, thighs, shins, and the neck.

    _ensure_ik_group()
        Create (or retrieve) the PP_TwoBoneIK node group — analytical
        two-bone IK solver used for elbows and knees.

    _compute_mid_joint(tree, x, y, label, start, end, ratio, total_length,
                       bend_axis, bend_axis_socket=None)
        Drop a PP_TwoBoneIK instance into the tree wired to the caller's
        shoulder-hand or hip-foot pair. Returns the group node (its
        `.outputs['Vector']` is the elbow/knee position).

=============================================================================
Why the first parameters are always (tree, x, parts_geo)
=============================================================================
Originally these functions were nested inside build_marionette_tree —
they could reach up into the parent scope and read `tree`, `x_part`, and
`parts_geo` for free (what Python calls *closure variables*). When we
lifted them to module level for readability and reuse, those values had
to become explicit parameters.

    tree       — the geometry node tree we're adding nodes to
    x_part     — x-coordinate where the part's nodes land in the editor
                 (pure layout for human readers; no effect on the math)
    parts_geo  — a running list of every finished part's geometry output
                 socket. The assembly step at the end joins all of these
                 into the final puppet mesh.

Python lists are *mutable by reference* — every function here appends to
the SAME list that build_marionette_tree started building. No need to
return the list; the caller can read it after the last append. That's a
small CS idea worth naming: you can pass a container in, mutate it from
inside the function, and the caller sees the change.
"""

import math

import bpy

from ._common import (add_node, _frame_section, _vector_lerp,
                      _snap_nodes, _new_nodes)
from .capsules import add_dynamic_capsule


# =============================================================================
# BODY GEOMETRY CONSTANTS — the puppet's physical dimensions
# =============================================================================
# Everything below the head is built from a small set of radii and one
# rotation angle. Changing any value here reshapes the puppet globally.
# Kept together so a reader can see the puppet's "anatomy at a glance."
#
#    CHEST_RADIUS        upper-torso capsule radius
#    PELVIS_RADIUS       lower-torso capsule radius
#    WAIST_JOINT_RADIUS  bead where chest meets pelvis
#    WAIST_TUBE_RADIUS   thickness of the spine tube between them
#    HAND_RADIUS         hand capsule radius (also scaled by Hand Size)
#    FOOT_RADIUS         foot capsule radius (also scaled by Foot Size)
#    JOINT_RADIUS        shoulder + hip bead radius
#    LIMB_TUBE_RADIUS    arm/leg tube thickness
#    ELBOW/KNEE_JOINT_RADIUS   elbow + knee bead radii
#    FOOT_SPLAY_ANGLE    default outward toe rotation (15° in radians)

CHEST_RADIUS = 0.2
PELVIS_RADIUS = 0.17
WAIST_JOINT_RADIUS = 0.05
WAIST_TUBE_RADIUS = 0.04

HAND_RADIUS = 0.1
FOOT_RADIUS = 0.12
JOINT_RADIUS = 0.06
LIMB_TUBE_RADIUS = 0.03

ELBOW_JOINT_RADIUS = 0.05
KNEE_JOINT_RADIUS = 0.06
FOOT_SPLAY_ANGLE = 0.262       # 15 degrees in radians


# =============================================================================
# CAPSULE BODY PART — the workhorse
# =============================================================================
# Used for every pill-shaped part of the marionette: chest, pelvis, hands,
# feet, shoulders, cheeks. The call looks busy because the function carries
# every optional bell and whistle a body part might need (driven rotation,
# mirror rotation, driven tilt, depth offset, uniform scale, material
# socket override). Most call sites only use four or five of them — the
# rest stay at their defaults and get skipped inside the branches below.

def add_capsule_part(tree, x_part, parts_geo, y, label, radius, pos_socket, mat,
                     scale=(1, 1, 1), rotation=(0, 0, 0),
                     width_output=None, ext_factor=0.3, axis='Z',
                     subdivs=6, uniform_scale_out=None,
                     rotation_output=None, rot_axis='Y',
                     negate_rot=False,
                     tilt_output=None, tilt_axis='X',
                     negate_tilt=False,
                     depth_output=None, depth_axis='Y',
                     mat_socket=None):
    """Create one body part: capsule + transform + material + smooth.

    uniform_scale_out: optional socket driving uniform XYZ scale
    rotation_output: optional socket driving rotation (degrees) on rot_axis
    negate_rot: if True, mirror the rotation (multiply by -1)
    tilt_output: optional SECOND rotation axis (degrees) on tilt_axis
    negate_tilt: if True, mirror the tilt (multiply by -1)
    depth_output: optional position offset along depth_axis
    mat_socket: optional group_in socket for material assignment
                (overrides hardcoded mat when provided)
    """
    _axis_idx = {'X': 0, 'Y': 1, 'Z': 2}

    capsule = add_dynamic_capsule(
        tree, x_part - 1200, y, label,
        radius=radius, subdivs=subdivs,
        width_output=width_output, ext_factor=ext_factor, axis=axis)

    tf = add_node(tree, 'GeometryNodeTransform', x_part + 200, y,
                  f"{label} TF")
    tree.links.new(capsule.outputs['Geometry'],
                   tf.inputs['Geometry'])

    # Position: optionally offset by depth along one axis
    if depth_output is not None:
        d_vec = add_node(tree, 'ShaderNodeCombineXYZ',
                         x_part + 50, y + 80, f"{label} DVec")
        tree.links.new(depth_output, d_vec.inputs[depth_axis])
        d_pos = add_node(tree, 'ShaderNodeVectorMath',
                         x_part + 200, y + 80, f"{label} D+P")
        d_pos.operation = 'ADD'
        tree.links.new(pos_socket, d_pos.inputs[0])
        tree.links.new(d_vec.outputs['Vector'], d_pos.inputs[1])
        tree.links.new(d_pos.outputs['Vector'],
                       tf.inputs['Translation'])
    else:
        tree.links.new(pos_socket, tf.inputs['Translation'])

    if rotation_output is not None or tilt_output is not None:
        # Build rotation vector: static base, driven axes add to base
        rot_vec = add_node(tree, 'ShaderNodeCombineXYZ',
                           x_part + 200, y - 160, f"{label} RotV")
        rot_vec.inputs['X'].default_value = rotation[0]
        rot_vec.inputs['Y'].default_value = rotation[1]
        rot_vec.inputs['Z'].default_value = rotation[2]

        if rotation_output is not None:
            rot_scale = (-math.pi / 180.0) if negate_rot else (math.pi / 180.0)
            rot_rad = add_node(tree, 'ShaderNodeMath',
                               x_part + 50, y - 160, f"{label} D→R")
            rot_rad.operation = 'MULTIPLY'
            rot_rad.inputs[1].default_value = rot_scale
            tree.links.new(rotation_output, rot_rad.inputs[0])

            # Add to static base if axis has a non-zero default
            base_val = rotation[_axis_idx[rot_axis]]
            if abs(base_val) > 1e-6:
                rot_add = add_node(tree, 'ShaderNodeMath',
                                   x_part + 50, y - 130,
                                   f"{label} R+B")
                rot_add.operation = 'ADD'
                rot_add.inputs[0].default_value = base_val
                tree.links.new(rot_rad.outputs[0],
                               rot_add.inputs[1])
                tree.links.new(rot_add.outputs[0],
                               rot_vec.inputs[rot_axis])
            else:
                tree.links.new(rot_rad.outputs[0],
                               rot_vec.inputs[rot_axis])

        if tilt_output is not None:
            tilt_scale = (-math.pi / 180.0) if negate_tilt else (math.pi / 180.0)
            tilt_rad = add_node(tree, 'ShaderNodeMath',
                                x_part + 50, y - 220, f"{label} T→R")
            tilt_rad.operation = 'MULTIPLY'
            tilt_rad.inputs[1].default_value = tilt_scale
            tree.links.new(tilt_output, tilt_rad.inputs[0])

            base_val_t = rotation[_axis_idx[tilt_axis]]
            if abs(base_val_t) > 1e-6:
                tilt_add = add_node(tree, 'ShaderNodeMath',
                                    x_part + 50, y - 250,
                                    f"{label} T+B")
                tilt_add.operation = 'ADD'
                tilt_add.inputs[0].default_value = base_val_t
                tree.links.new(tilt_rad.outputs[0],
                               tilt_add.inputs[1])
                tree.links.new(tilt_add.outputs[0],
                               rot_vec.inputs[tilt_axis])
            else:
                tree.links.new(tilt_rad.outputs[0],
                               rot_vec.inputs[tilt_axis])

        tree.links.new(rot_vec.outputs['Vector'],
                       tf.inputs['Rotation'])
    else:
        tf.inputs['Rotation'].default_value = rotation

    if uniform_scale_out is not None:
        # Build dynamic scale: static_scale * uniform_size
        sc_vec = add_node(tree, 'ShaderNodeCombineXYZ',
                          x_part + 50, y - 80, f"{label} ScV")
        sc_vec.inputs['X'].default_value = scale[0]
        sc_vec.inputs['Y'].default_value = scale[1]
        sc_vec.inputs['Z'].default_value = scale[2]
        sc_mul = add_node(tree, 'ShaderNodeVectorMath',
                          x_part + 200, y - 80, f"{label} Sc*")
        sc_mul.operation = 'SCALE'
        tree.links.new(sc_vec.outputs['Vector'], sc_mul.inputs[0])
        tree.links.new(uniform_scale_out, sc_mul.inputs['Scale'])
        tree.links.new(sc_mul.outputs['Vector'],
                       tf.inputs['Scale'])
    else:
        tf.inputs['Scale'].default_value = scale

    sm = add_node(tree, 'GeometryNodeSetShadeSmooth', x_part + 400,
                  y, f"{label} Sm")
    tree.links.new(tf.outputs['Geometry'], sm.inputs['Geometry'])

    mt = add_node(tree, 'GeometryNodeSetMaterial', x_part + 600, y,
                  f"{label} Mt")
    tree.links.new(sm.outputs['Geometry'], mt.inputs['Geometry'])
    if mat_socket is not None:
        tree.links.new(mat_socket, mt.inputs['Material'])
    else:
        mt.inputs['Material'].default_value = mat
    parts_geo.append(mt.outputs['Geometry'])


# =============================================================================
# SPHERE BODY PART — joint beads
# =============================================================================
# A plain UV sphere at a driven position. Used for every small bead on the
# marionette: the waist joint that connects chest to pelvis, the hip beads
# where thigh meets pelvis, and the elbow/knee beads on the limb chains.
# No capsule here — joints want a round bead, not a pill.

def add_sphere_part(tree, x_part, parts_geo, y, label, radius, pos_socket, mat,
                    segments=8, rings=6, mat_socket=None):
    """Small sphere for joints (no capsule needed)."""
    sphere = add_node(tree, 'GeometryNodeMeshUVSphere', x_part, y,
                      label)
    sphere.inputs['Segments'].default_value = segments
    sphere.inputs['Rings'].default_value = rings
    sphere.inputs['Radius'].default_value = radius

    tf = add_node(tree, 'GeometryNodeTransform', x_part + 200, y,
                  f"{label} TF")
    tree.links.new(sphere.outputs['Mesh'], tf.inputs['Geometry'])
    tree.links.new(pos_socket, tf.inputs['Translation'])

    sm = add_node(tree, 'GeometryNodeSetShadeSmooth', x_part + 400,
                  y, f"{label} Sm")
    tree.links.new(tf.outputs['Geometry'], sm.inputs['Geometry'])

    mt = add_node(tree, 'GeometryNodeSetMaterial', x_part + 600, y,
                  f"{label} Mt")
    tree.links.new(sm.outputs['Geometry'], mt.inputs['Geometry'])
    if mat_socket is not None:
        tree.links.new(mat_socket, mt.inputs['Material'])
    else:
        mt.inputs['Material'].default_value = mat
    parts_geo.append(mt.outputs['Geometry'])


# =============================================================================
# LIMB — line-to-tube between two endpoints
# =============================================================================
# Given two socket positions (say, shoulder and elbow), draw a 2-point
# curve between them, then sweep a shared circular `profile` along that
# curve to get a tube mesh. Used for upper arms, forearms, thighs, shins,
# and the neck. The `profile` argument is a GeometryNodeCurvePrimitiveCircle
# that build_marionette_tree creates once and reuses for every limb — one
# profile, many tubes, no redundant circle nodes.

def add_limb(tree, x_limb, profile, parts_geo, y, label, start_socket, end_socket, mat,
             mat_socket=None):
    """Curve line from start to end → tube mesh."""
    line = add_node(tree, 'GeometryNodeCurvePrimitiveLine', x_limb, y,
                    f"{label} Ln")
    line.mode = 'POINTS'
    tree.links.new(start_socket, line.inputs['Start'])
    tree.links.new(end_socket, line.inputs['End'])

    tube = add_node(tree, 'GeometryNodeCurveToMesh', x_limb + 200, y,
                    f"{label} Tube")
    tree.links.new(line.outputs['Curve'], tube.inputs['Curve'])
    tree.links.new(profile.outputs['Curve'],
                   tube.inputs['Profile Curve'])

    sm = add_node(tree, 'GeometryNodeSetShadeSmooth', x_limb + 400, y,
                  f"{label} Sm")
    tree.links.new(tube.outputs['Mesh'], sm.inputs['Geometry'])

    mt = add_node(tree, 'GeometryNodeSetMaterial', x_limb + 600, y,
                  f"{label} Mt")
    tree.links.new(sm.outputs['Geometry'], mt.inputs['Geometry'])
    if mat_socket is not None:
        tree.links.new(mat_socket, mt.inputs['Material'])
    else:
        mt.inputs['Material'].default_value = mat
    parts_geo.append(mt.outputs['Geometry'])


# =============================================================================
# TWO-BONE IK NODE GROUP — analytical elbow/knee solver
# =============================================================================
# Both elbows and both knees all use the exact same piece of math: given a
# start point, an end point, a total limb length, a segment ratio, and a
# "bend axis" direction, return the position where the middle joint should
# sit. That's analytical two-bone IK: no iterative solver, no simulation,
# just one closed-form formula.
#
# We build it once as a reusable Geometry Nodes *group* (PP_TwoBoneIK) and
# then drop one instance per joint into the marionette tree. Four instances
# cover both elbows and both knees. _compute_mid_joint is the thin wrapper
# that wires an instance into the calling tree.
#
# The math inside the group:
#   1. Law of cosines solves for cos(angle) at the start joint given the two
#      segment lengths and the straight-line distance to the end.
#   2. Project along the start->end direction by (upper_length * cos_angle)
#      to get the foot of the perpendicular.
#   3. Pythagoras gives the perpendicular distance h off that line.
#   4. Double cross product picks WHICH side the joint bends toward
#      (forward vs backward) using the Bend Axis input.
#   5. Final joint = foot_of_perpendicular + (perpendicular_unit * h).

def _ensure_ik_group():
    """Create or retrieve the PP_TwoBoneIK node group.

    Analytical two-bone IK via law of cosines + double cross product.
    Finds elbow/knee position from shoulder-to-hand or hip-to-foot.
    Replaces ~25 inline nodes per joint.
    """
    existing = bpy.data.node_groups.get("PP_TwoBoneIK")
    if existing:
        return existing

    g = bpy.data.node_groups.new("PP_TwoBoneIK", 'GeometryNodeTree')
    g.interface.clear()

    g.interface.new_socket(
        "Start", in_out='INPUT', socket_type='NodeSocketVector')
    g.interface.new_socket(
        "End", in_out='INPUT', socket_type='NodeSocketVector')
    s = g.interface.new_socket(
        "Upper Ratio", in_out='INPUT', socket_type='NodeSocketFloat')
    s.default_value = 0.5
    s.min_value = 0.3
    s.max_value = 0.7
    s = g.interface.new_socket(
        "Total Length", in_out='INPUT', socket_type='NodeSocketFloat')
    s.default_value = 0.7
    g.interface.new_socket(
        "Bend Axis", in_out='INPUT', socket_type='NodeSocketVector')
    # Named 'Vector' so callers can use .outputs['Vector'] unchanged
    g.interface.new_socket(
        "Vector", in_out='OUTPUT', socket_type='NodeSocketVector')

    dx = 200
    gin = add_node(g, 'NodeGroupInput', 0, 0, "In")

    # --- Limb segment lengths ---
    upper = add_node(g, 'ShaderNodeMath', dx, 0, "ULen")
    upper.operation = 'MULTIPLY'
    g.links.new(gin.outputs['Total Length'], upper.inputs[0])
    g.links.new(gin.outputs['Upper Ratio'], upper.inputs[1])

    lower = add_node(g, 'ShaderNodeMath', dx, -100, "LLen")
    lower.operation = 'SUBTRACT'
    g.links.new(gin.outputs['Total Length'], lower.inputs[0])
    g.links.new(upper.outputs['Value'], lower.inputs[1])

    _frame_section(g,
        "SEGMENT LENGTHS — Split total limb length into upper"
        " and lower segments by ratio",
        'attach', [upper, lower])

    # --- Shoulder-to-hand vector ---
    ab = add_node(g, 'ShaderNodeVectorMath', dx * 2, 0, "AB")
    ab.operation = 'SUBTRACT'
    g.links.new(gin.outputs['End'], ab.inputs[0])
    g.links.new(gin.outputs['Start'], ab.inputs[1])

    d_len = add_node(g, 'ShaderNodeVectorMath', dx * 3, 0, "|AB|")
    d_len.operation = 'LENGTH'
    g.links.new(ab.outputs['Vector'], d_len.inputs[0])

    ab_dir = add_node(g, 'ShaderNodeVectorMath', dx * 3, -100, "ABdir")
    ab_dir.operation = 'NORMALIZE'
    g.links.new(ab.outputs['Vector'], ab_dir.inputs[0])

    # --- Law of cosines: cos(a) = (u² + d² - l²) / (2·u·d) ---
    u2 = add_node(g, 'ShaderNodeMath', dx * 4, 80, "u2")
    u2.operation = 'MULTIPLY'
    g.links.new(upper.outputs['Value'], u2.inputs[0])
    g.links.new(upper.outputs['Value'], u2.inputs[1])

    d2 = add_node(g, 'ShaderNodeMath', dx * 4, 0, "d2")
    d2.operation = 'MULTIPLY'
    g.links.new(d_len.outputs['Value'], d2.inputs[0])
    g.links.new(d_len.outputs['Value'], d2.inputs[1])

    l2 = add_node(g, 'ShaderNodeMath', dx * 4, -80, "l2")
    l2.operation = 'MULTIPLY'
    g.links.new(lower.outputs['Value'], l2.inputs[0])
    g.links.new(lower.outputs['Value'], l2.inputs[1])

    u2_d2 = add_node(g, 'ShaderNodeMath', dx * 5, 40, "u2+d2")
    u2_d2.operation = 'ADD'
    g.links.new(u2.outputs['Value'], u2_d2.inputs[0])
    g.links.new(d2.outputs['Value'], u2_d2.inputs[1])

    numer = add_node(g, 'ShaderNodeMath', dx * 5, -40, "Num")
    numer.operation = 'SUBTRACT'
    g.links.new(u2_d2.outputs['Value'], numer.inputs[0])
    g.links.new(l2.outputs['Value'], numer.inputs[1])

    two_u = add_node(g, 'ShaderNodeMath', dx * 5, -120, "2u")
    two_u.operation = 'MULTIPLY'
    two_u.inputs[0].default_value = 2.0
    g.links.new(upper.outputs['Value'], two_u.inputs[1])

    two_ud = add_node(g, 'ShaderNodeMath', dx * 6, -120, "2ud")
    two_ud.operation = 'MULTIPLY'
    g.links.new(two_u.outputs['Value'], two_ud.inputs[0])
    g.links.new(d_len.outputs['Value'], two_ud.inputs[1])

    denom = add_node(g, 'ShaderNodeMath', dx * 6, -200, "Den")
    denom.operation = 'MAXIMUM'
    g.links.new(two_ud.outputs['Value'], denom.inputs[0])
    denom.inputs[1].default_value = 0.001

    cos_a = add_node(g, 'ShaderNodeMath', dx * 6, -40, "CosA")
    cos_a.operation = 'DIVIDE'
    g.links.new(numer.outputs['Value'], cos_a.inputs[0])
    g.links.new(denom.outputs['Value'], cos_a.inputs[1])

    ca_min = add_node(g, 'ShaderNodeMath', dx * 7, -40, "Ca<1")
    ca_min.operation = 'MINIMUM'
    g.links.new(cos_a.outputs['Value'], ca_min.inputs[0])
    ca_min.inputs[1].default_value = 1.0

    ca_clamp = add_node(g, 'ShaderNodeMath', dx * 7, -120, "Ca>-1")
    ca_clamp.operation = 'MAXIMUM'
    g.links.new(ca_min.outputs['Value'], ca_clamp.inputs[0])
    ca_clamp.inputs[1].default_value = -1.0

    _frame_section(g,
        "LAW OF COSINES — Find the angle at the shoulder/hip"
        " where two limb-length spheres intersect",
        'physics', [u2, d2, l2, u2_d2, numer, two_u, two_ud,
                    denom, cos_a, ca_min, ca_clamp])

    # --- Projection along AB + height off line ---
    proj = add_node(g, 'ShaderNodeMath', dx * 8, 0, "Proj")
    proj.operation = 'MULTIPLY'
    g.links.new(upper.outputs['Value'], proj.inputs[0])
    g.links.new(ca_clamp.outputs['Value'], proj.inputs[1])

    p2 = add_node(g, 'ShaderNodeMath', dx * 8, -80, "p2")
    p2.operation = 'MULTIPLY'
    g.links.new(proj.outputs['Value'], p2.inputs[0])
    g.links.new(proj.outputs['Value'], p2.inputs[1])

    h2 = add_node(g, 'ShaderNodeMath', dx * 8, -160, "h2")
    h2.operation = 'SUBTRACT'
    g.links.new(u2.outputs['Value'], h2.inputs[0])
    g.links.new(p2.outputs['Value'], h2.inputs[1])

    h2_safe = add_node(g, 'ShaderNodeMath', dx * 9, -160, "h2+")
    h2_safe.operation = 'MAXIMUM'
    g.links.new(h2.outputs['Value'], h2_safe.inputs[0])
    h2_safe.inputs[1].default_value = 0.0

    h_val = add_node(g, 'ShaderNodeMath', dx * 9, -80, "h")
    h_val.operation = 'SQRT'
    g.links.new(h2_safe.outputs['Value'], h_val.inputs[0])

    along_sc = add_node(g, 'ShaderNodeVectorMath', dx * 9, 0, "Alng")
    along_sc.operation = 'SCALE'
    g.links.new(ab_dir.outputs['Vector'], along_sc.inputs[0])
    g.links.new(proj.outputs['Value'], along_sc.inputs['Scale'])

    along = add_node(g, 'ShaderNodeVectorMath', dx * 10, 0, "AlP")
    along.operation = 'ADD'
    g.links.new(gin.outputs['Start'], along.inputs[0])
    g.links.new(along_sc.outputs['Vector'], along.inputs[1])

    _frame_section(g,
        "PROJECTION — Distance along the shoulder-hand line"
        " and perpendicular height where the joint sits",
        'control', [proj, p2, h2, h2_safe, h_val, along_sc, along])

    # --- Bend direction via double cross product ---
    side = add_node(g, 'ShaderNodeVectorMath', dx * 9, -260, "Side")
    side.operation = 'CROSS_PRODUCT'
    g.links.new(ab_dir.outputs['Vector'], side.inputs[0])
    g.links.new(gin.outputs['Bend Axis'], side.inputs[1])

    bend = add_node(g, 'ShaderNodeVectorMath', dx * 10, -260, "Bend")
    bend.operation = 'CROSS_PRODUCT'
    g.links.new(ab_dir.outputs['Vector'], bend.inputs[0])
    g.links.new(side.outputs['Vector'], bend.inputs[1])

    bend_n = add_node(g, 'ShaderNodeVectorMath', dx * 10, -160, "BNrm")
    bend_n.operation = 'NORMALIZE'
    g.links.new(bend.outputs['Vector'], bend_n.inputs[0])

    perp = add_node(g, 'ShaderNodeVectorMath', dx * 11, -120, "Perp")
    perp.operation = 'SCALE'
    g.links.new(bend_n.outputs['Vector'], perp.inputs[0])
    g.links.new(h_val.outputs['Value'], perp.inputs['Scale'])

    _frame_section(g,
        "BEND DIRECTION — Double cross product picks which"
        " side the elbow/knee bends toward (forward or backward)",
        'float', [side, bend, bend_n, perp])

    # --- Final joint position ---
    mid = add_node(g, 'ShaderNodeVectorMath', dx * 11, 0, "Mid")
    mid.operation = 'ADD'
    g.links.new(along.outputs['Vector'], mid.inputs[0])
    g.links.new(perp.outputs['Vector'], mid.inputs[1])

    gout = add_node(g, 'NodeGroupOutput', dx * 12, 0, "Out")
    g.links.new(mid.outputs['Vector'], gout.inputs['Vector'])

    return g


# =============================================================================
# MID-JOINT WRAPPER — drop a PP_TwoBoneIK instance into the caller's tree
# =============================================================================
# The group exists once. Each elbow or knee instantiates it, wires its own
# shoulder/hand (or hip/foot) sockets in, and reads the resulting joint
# position out. This wrapper is the one-liner that every body-composition
# call site wants: label the instance, hand in the two endpoints, get back
# the elbow/knee socket.

def _compute_mid_joint(tree, x, y, label,
                      start_socket, end_socket,
                      upper_ratio_out, total_length_out,
                      bend_axis, bend_axis_socket=None):
    """Compute elbow/knee position via the PP_TwoBoneIK node group.

    Law of cosines + double cross product finds the joint position.
    bend_axis: default direction tuple (fallback when no socket wired).
    bend_axis_socket: optional dynamic socket overriding the static default.
    Returns the group node (.outputs['Vector'] = mid-joint position).
    """
    ik_tree = _ensure_ik_group()
    grp = add_node(tree, 'GeometryNodeGroup', x, y, label)
    grp.node_tree = ik_tree
    tree.links.new(start_socket, grp.inputs['Start'])
    tree.links.new(end_socket, grp.inputs['End'])
    tree.links.new(upper_ratio_out, grp.inputs['Upper Ratio'])
    tree.links.new(total_length_out, grp.inputs['Total Length'])
    if bend_axis_socket is not None:
        tree.links.new(bend_axis_socket, grp.inputs['Bend Axis'])
    else:
        grp.inputs['Bend Axis'].default_value = (
            bend_axis[0] + 0.001, bend_axis[1], bend_axis[2])
    return grp


# =============================================================================
# BUILD_BODY_PARTS — the full visual skeleton, composed from the helpers above
# =============================================================================
# Everything above this line is vocabulary. build_body_parts is the sentence
# that uses it: it reads like a recipe for the marionette's body.
#
#    1. Chest, pelvis, waist bead, spine tube — the torso.
#    2. Direct-placement math for hands so webcam tracking feels responsive
#       (bypass the Verlet simulation when body tracking is live).
#    3. Hand capsules + foot capsules + shoulder + hip beads.
#    4. Two-bone IK for elbows and knees.
#    5. Limb tubes (upper arm, forearm, thigh, shin).
#    6. Neck + elbow/knee beads to finish the skeleton.
#
# The function wraps its work in two colored Frames in the GN editor: THE
# PUPPET'S BODY (chest/pelvis/hands/feet/shoulders/hips) and THE SKELETON
# (elbows/knees/limbs/neck/spine). The caller can plug its own sections
# directly in front of and after this one; the frames here stay local to
# body composition.
#
# Returns a dict so the caller can thread the results into the downstream
# Studio Track (custom-mesh override) and Assembly (mesh join) sections:
#     parts_geo  — list of Geometry sockets to join in Assembly
#     _idx_*     — index into parts_geo for each capsule the Studio Track
#                  might need to swap out (chest, pelvis, hands, feet)
#     hand_l_pos, hand_r_pos — the final (post-lerp) hand position sockets
#                              so custom-mesh hands follow the same target
#     snap_state — the node-snapshot taken just before Section 10 begins,
#                  so the caller can keep the "frame what's new" pattern
#                  running seamlessly.

def build_body_parts(tree, group_in, sim_out, body_mats,
                     chest_pos, pelvis_pos, waist_mid,
                     hipl_visual, hipr_visual,
                     shl_visual, shr_visual,
                     arm_l_factor, arm_r_factor,
                     snap_state):
    """Build Sections 8 (body parts) and 9 (skeleton) of the marionette tree.

    Returns a dict with parts_geo (list of Geometry sockets), capsule
    indices (_idx_chest/pelvis/hand_l/hand_r/foot_l/foot_r), the two hand
    position sockets, x_part + x_limb layout coordinates, and the
    node-snapshot state to hand back to the caller.
    """
    # ------------------------------------------------------------------
    # SECTION 8 — Visual body parts (capsules + customization colors)
    # ------------------------------------------------------------------
    # V0.8.0: Dynamic Minkowski capsules replace UV Spheres. Body Width
    # slider drives chest/pelvis extension. Hand/Foot Size scales radii.
    # Colors from Group Input customization sockets.
    x_part = 1800
    parts_geo = []

    # --- Color materials: created once, assigned via Set Material node ---
    # Materials use hardcoded colors as defaults, but the kid can change
    # them via the customization panel color sockets.
    # For now, materials are static (same as before) because GN can't
    # change material base color per-instance. Color sockets are reserved
    # for a future build using Attribute nodes or vertex color painting.

    # --- Capsule body parts ---
    # Track indices for Studio Track custom object replacement
    _idx_chest = len(parts_geo)
    # Chest: dynamic capsule, extends along X (wider torso)
    add_capsule_part(tree, x_part, parts_geo, 0, "Chest", CHEST_RADIUS,
                      chest_pos.outputs['Vector'], body_mats['body'],
                      scale=(1.1, 0.8, 1.05),
                      width_output=group_in.outputs['Body Width'],
                      ext_factor=0.15, axis='X',
                      mat_socket=group_in.outputs['Body Part Material'])

    # Pelvis: dynamic capsule, same width driver (slightly less extension)
    _idx_pelvis = len(parts_geo)
    add_capsule_part(tree, x_part, parts_geo, -280, "Pelvis", PELVIS_RADIUS,
                      pelvis_pos.outputs['Vector'], body_mats['body'],
                      scale=(1.0, 0.85, 0.9),
                      width_output=group_in.outputs['Body Width'],
                      ext_factor=0.12, axis='X',
                      mat_socket=group_in.outputs['Body Part Material'])

    # Waist joint (small sphere)
    add_sphere_part(tree, x_part, parts_geo, -460, "Waist Jnt", WAIST_JOINT_RADIUS,
                     waist_mid.outputs['Vector'], body_mats['joint'],
                     mat_socket=group_in.outputs['Joint Material'])

    # --- Direct hand placement: bypass Verlet when body tracking active ---
    # When arms are tracked by the webcam, place hands directly at the
    # tracked position (shoulder + wrist-shoulder delta from MediaPipe).
    # When not tracked, fall back to Verlet physics output (marionette feel).
    # Lerp factor = arm visibility × Body Tracking.
    # Proportional hand placement — match the performer's arm extension
    # ratio rather than raw tracking distance. This ensures the IK solver
    # has room to compute proper elbow bend angles, regardless of the
    # puppet's arm length vs the performer's arm length.
    # Hand = shoulder + normalize(delta) × extension_ratio × ArmLength
    x_dh = x_part - 600

    # Left hand: direction + scaled reach
    dir_l = add_node(tree, 'ShaderNodeVectorMath', x_dh, -620, "Dir HL")
    dir_l.operation = 'NORMALIZE'
    tree.links.new(group_in.outputs['bt_shl_delta'], dir_l.inputs[0])

    reach_l = add_node(tree, 'ShaderNodeMath', x_dh + 200, -560,
                        "Reach L")
    reach_l.operation = 'MULTIPLY'
    tree.links.new(group_in.outputs['bt_arm_l_ext'], reach_l.inputs[0])
    tree.links.new(group_in.outputs['Arm Length'], reach_l.inputs[1])

    hand_off_l = add_node(tree, 'ShaderNodeVectorMath', x_dh + 200, -620,
                           "Hand Off L")
    hand_off_l.operation = 'SCALE'
    tree.links.new(dir_l.outputs['Vector'], hand_off_l.inputs[0])
    tree.links.new(reach_l.outputs['Value'], hand_off_l.inputs['Scale'])

    tracked_hand_l = add_node(tree, 'ShaderNodeVectorMath', x_dh + 400,
                              -620, "Tracked HL")
    tracked_hand_l.operation = 'ADD'
    tree.links.new(shl_visual.outputs['Vector'],
                   tracked_hand_l.inputs[0])
    tree.links.new(hand_off_l.outputs['Vector'],
                   tracked_hand_l.inputs[1])

    # Right hand: direction + scaled reach
    dir_r = add_node(tree, 'ShaderNodeVectorMath', x_dh, -780, "Dir HR")
    dir_r.operation = 'NORMALIZE'
    tree.links.new(group_in.outputs['bt_shr_delta'], dir_r.inputs[0])

    reach_r = add_node(tree, 'ShaderNodeMath', x_dh + 200, -720,
                        "Reach R")
    reach_r.operation = 'MULTIPLY'
    tree.links.new(group_in.outputs['bt_arm_r_ext'], reach_r.inputs[0])
    tree.links.new(group_in.outputs['Arm Length'], reach_r.inputs[1])

    hand_off_r = add_node(tree, 'ShaderNodeVectorMath', x_dh + 200, -780,
                           "Hand Off R")
    hand_off_r.operation = 'SCALE'
    tree.links.new(dir_r.outputs['Vector'], hand_off_r.inputs[0])
    tree.links.new(reach_r.outputs['Value'], hand_off_r.inputs['Scale'])

    tracked_hand_r = add_node(tree, 'ShaderNodeVectorMath', x_dh + 400,
                              -780, "Tracked HR")
    tracked_hand_r.operation = 'ADD'
    tree.links.new(shr_visual.outputs['Vector'],
                   tracked_hand_r.inputs[0])
    tree.links.new(hand_off_r.outputs['Vector'],
                   tracked_hand_r.inputs[1])

    hand_l_lerp = _vector_lerp(tree, x_dh + 200, -620, "HandL",
                               sim_out.outputs['pos_hand_l'],
                               tracked_hand_l.outputs['Vector'],
                               arm_l_factor.outputs['Value'])
    hand_l_pos = hand_l_lerp.outputs['Vector']

    hand_r_lerp = _vector_lerp(tree, x_dh + 200, -780, "HandR",
                               sim_out.outputs['pos_hand_r'],
                               tracked_hand_r.outputs['Vector'],
                               arm_r_factor.outputs['Value'])
    hand_r_pos = hand_r_lerp.outputs['Vector']

    # Hands are drawn separately in marionette/hands.py (alpha.48+):
    # palm plate + palm-corner beads + 4 finger chains. The old
    # cartoon-capsule hand was removed — `hand_l_pos` / `hand_r_pos`
    # survive as the FALLBACK for the new hand's palm socket when
    # bt_wrist_* is still zero (pre-tracking). See build_hands().

    # Feet: capsules with Width + Rotation on Z (mirrored) + Depth
    _idx_foot_l = len(parts_geo)
    add_capsule_part(tree, x_part, parts_geo, -940, "Foot L", FOOT_RADIUS,
                      sim_out.outputs['pos_foot_l'], body_mats['foot'],
                      rotation=(0, 0, FOOT_SPLAY_ANGLE),
                      width_output=group_in.outputs['Foot Width'],
                      ext_factor=0.3, axis='Y', subdivs=4,
                      uniform_scale_out=group_in.outputs['Foot Size'],
                      rotation_output=group_in.outputs['Foot Rotation'],
                      rot_axis='Z',
                      depth_output=group_in.outputs['Foot Depth'],
                      depth_axis='Y',
                      mat_socket=group_in.outputs['Foot Material'])
    _idx_foot_r = len(parts_geo)
    add_capsule_part(tree, x_part, parts_geo, -1100, "Foot R", FOOT_RADIUS,
                      sim_out.outputs['pos_foot_r'], body_mats['foot'],
                      rotation=(0, 0, -FOOT_SPLAY_ANGLE),
                      width_output=group_in.outputs['Foot Width'],
                      ext_factor=0.3, axis='Y', subdivs=4,
                      uniform_scale_out=group_in.outputs['Foot Size'],
                      rotation_output=group_in.outputs['Foot Rotation'],
                      rot_axis='Z', negate_rot=True,
                      depth_output=group_in.outputs['Foot Depth'],
                      depth_axis='Y',
                      mat_socket=group_in.outputs['Foot Material'])

    # Shoulder joints: capsules with Width + Rotation
    add_capsule_part(tree, x_part, parts_geo, -1260, "Jnt ShL", JOINT_RADIUS,
                      sim_out.outputs['floated_shl'], body_mats['joint'],
                      width_output=group_in.outputs['Shoulder Width'],
                      ext_factor=0.3, axis='Z', subdivs=3,
                      rotation_output=group_in.outputs['Shoulder Rotation'],
                      mat_socket=group_in.outputs['Joint Material'])
    add_capsule_part(tree, x_part, parts_geo, -1360, "Jnt ShR", JOINT_RADIUS,
                      sim_out.outputs['floated_shr'], body_mats['joint'],
                      width_output=group_in.outputs['Shoulder Width'],
                      ext_factor=0.3, axis='Z', subdivs=3,
                      rotation_output=group_in.outputs['Shoulder Rotation'],
                      mat_socket=group_in.outputs['Joint Material'])

    # Hip joints (small spheres — stay spherical)
    add_sphere_part(tree, x_part, parts_geo, -1460, "Jnt HipL", JOINT_RADIUS,
                     hipl_visual.outputs['Vector'], body_mats['joint'],
                     mat_socket=group_in.outputs['Joint Material'])
    add_sphere_part(tree, x_part, parts_geo, -1560, "Jnt HipR", JOINT_RADIUS,
                     hipr_visual.outputs['Vector'], body_mats['joint'],
                     mat_socket=group_in.outputs['Joint Material'])

    _frame_section(tree,
        "THE PUPPET'S BODY — Minkowski capsules (chest, pelvis,"
        " hands, feet, shoulders) + sphere joints + materials",
        'body', _new_nodes(tree, snap_state))
    snap_state = _snap_nodes(tree)

    # ------------------------------------------------------------------
    # SECTION 9 — Limb curves + neck
    # ------------------------------------------------------------------
    x_limb = 2600

    profile = add_node(tree, 'GeometryNodeCurvePrimitiveCircle',
                       x_limb - 200, -1400, "Tube Profile")
    profile.mode = 'RADIUS'
    profile.inputs['Radius'].default_value = LIMB_TUBE_RADIUS
    profile.inputs['Resolution'].default_value = 6

    # --- Analytical mid-joints (two-bone IK for elbows/knees) ---
    x_mid = x_limb - 2400  # mid-joint computation nodes to the left

    # Elbow bend hints: blend between default backward bend and
    # tracked elbow direction from body landmarks
    elbow_default = add_node(tree, 'ShaderNodeCombineXYZ',
                             x_mid - 800, -200, "Elbow Default")
    elbow_default.inputs['X'].default_value = 0.001
    elbow_default.inputs['Y'].default_value = -1.0
    elbow_default.inputs['Z'].default_value = 0.0

    elbow_l_bend = _vector_lerp(
        tree, x_mid - 600, -200, "ELB",
        elbow_default.outputs['Vector'],
        group_in.outputs['bt_elbow_l_hint'],
        arm_l_factor.outputs['Value'])

    elbow_r_bend = _vector_lerp(
        tree, x_mid - 600, -550, "ERB",
        elbow_default.outputs['Vector'],
        group_in.outputs['bt_elbow_r_hint'],
        arm_r_factor.outputs['Value'])

    elbow_l = _compute_mid_joint(
        tree, x_mid, -200, "Elbow L",
        start_socket=sim_out.outputs['floated_shl'],
        end_socket=hand_l_pos,
        upper_ratio_out=group_in.outputs['Upper Arm Ratio'],
        total_length_out=group_in.outputs['Arm Length'],
        bend_axis=(0, -1, 0),
        bend_axis_socket=elbow_l_bend.outputs['Vector'])

    elbow_r = _compute_mid_joint(
        tree, x_mid, -550, "Elbow R",
        start_socket=sim_out.outputs['floated_shr'],
        end_socket=hand_r_pos,
        upper_ratio_out=group_in.outputs['Upper Arm Ratio'],
        total_length_out=group_in.outputs['Arm Length'],
        bend_axis=(0, -1, 0),
        bend_axis_socket=elbow_r_bend.outputs['Vector'])

    knee_l = _compute_mid_joint(
        tree, x_mid, -900, "Knee L",
        start_socket=hipl_visual.outputs['Vector'],
        end_socket=sim_out.outputs['pos_foot_l'],
        upper_ratio_out=group_in.outputs['Upper Leg Ratio'],
        total_length_out=group_in.outputs['Leg Length'],
        bend_axis=(0, 1, 0))  # knees bend forward

    knee_r = _compute_mid_joint(
        tree, x_mid, -1250, "Knee R",
        start_socket=hipr_visual.outputs['Vector'],
        end_socket=sim_out.outputs['pos_foot_r'],
        upper_ratio_out=group_in.outputs['Upper Leg Ratio'],
        total_length_out=group_in.outputs['Leg Length'],
        bend_axis=(0, 1, 0))

    # --- Split limbs: upper segment → joint sphere → lower segment ---
    # Arms (floated shoulders → elbow → hand)
    add_limb(tree, x_limb, profile, parts_geo, -100, "UArm L",
              sim_out.outputs['floated_shl'],
              elbow_l.outputs['Vector'], body_mats['limb'],
              mat_socket=group_in.outputs['Limb Material'])
    add_limb(tree, x_limb, profile, parts_geo, -170, "FArm L",
              elbow_l.outputs['Vector'],
              hand_l_pos, body_mats['limb'],
              mat_socket=group_in.outputs['Limb Material'])
    add_limb(tree, x_limb, profile, parts_geo, -240, "UArm R",
              sim_out.outputs['floated_shr'],
              elbow_r.outputs['Vector'], body_mats['limb'],
              mat_socket=group_in.outputs['Limb Material'])
    add_limb(tree, x_limb, profile, parts_geo, -310, "FArm R",
              elbow_r.outputs['Vector'],
              hand_r_pos, body_mats['limb'],
              mat_socket=group_in.outputs['Limb Material'])

    # Legs (hips → knee → foot)
    add_limb(tree, x_limb, profile, parts_geo, -410, "Thigh L",
              hipl_visual.outputs['Vector'],
              knee_l.outputs['Vector'], body_mats['limb'],
              mat_socket=group_in.outputs['Limb Material'])
    add_limb(tree, x_limb, profile, parts_geo, -480, "Shin L",
              knee_l.outputs['Vector'],
              sim_out.outputs['pos_foot_l'], body_mats['limb'],
              mat_socket=group_in.outputs['Limb Material'])
    add_limb(tree, x_limb, profile, parts_geo, -550, "Thigh R",
              hipr_visual.outputs['Vector'],
              knee_r.outputs['Vector'], body_mats['limb'],
              mat_socket=group_in.outputs['Limb Material'])
    add_limb(tree, x_limb, profile, parts_geo, -620, "Shin R",
              knee_r.outputs['Vector'],
              sim_out.outputs['pos_foot_r'], body_mats['limb'],
              mat_socket=group_in.outputs['Limb Material'])

    # Elbow/knee joint spheres
    add_sphere_part(tree, x_part, parts_geo, -1420, "Elbow L", ELBOW_JOINT_RADIUS,
                     elbow_l.outputs['Vector'], body_mats['joint'],
                     mat_socket=group_in.outputs['Joint Material'])
    add_sphere_part(tree, x_part, parts_geo, -1520, "Elbow R", ELBOW_JOINT_RADIUS,
                     elbow_r.outputs['Vector'], body_mats['joint'],
                     mat_socket=group_in.outputs['Joint Material'])
    add_sphere_part(tree, x_part, parts_geo, -1620, "Knee L", KNEE_JOINT_RADIUS,
                     knee_l.outputs['Vector'], body_mats['joint'],
                     mat_socket=group_in.outputs['Joint Material'])
    add_sphere_part(tree, x_part, parts_geo, -1720, "Knee R", KNEE_JOINT_RADIUS,
                     knee_r.outputs['Vector'], body_mats['joint'],
                     mat_socket=group_in.outputs['Joint Material'])

    # Neck (chest top → head bottom) — tracks chest sway
    neck_top_off = add_node(tree, 'ShaderNodeCombineXYZ',
                            x_limb - 400, -900, "Neck Top Off")
    neck_top_off.inputs['Z'].default_value = 0.15  # above chest center
    neck_top = add_node(tree, 'ShaderNodeVectorMath',
                        x_limb - 200, -900, "Neck Top")
    neck_top.operation = 'ADD'
    tree.links.new(chest_pos.outputs['Vector'], neck_top.inputs[0])
    tree.links.new(neck_top_off.outputs['Vector'], neck_top.inputs[1])

    neck_bot_off = add_node(tree, 'ShaderNodeCombineXYZ',
                            x_limb - 400, -1050, "Neck Bot Off")
    neck_bot_off.inputs['Z'].default_value = 0.28  # toward head
    neck_bot = add_node(tree, 'ShaderNodeVectorMath',
                        x_limb - 200, -1050, "Neck Bot")
    neck_bot.operation = 'ADD'
    tree.links.new(chest_pos.outputs['Vector'], neck_bot.inputs[0])
    tree.links.new(neck_bot_off.outputs['Vector'], neck_bot.inputs[1])

    add_limb(tree, x_limb, profile, parts_geo, -800, "Neck",
              neck_top.outputs['Vector'],
              neck_bot.outputs['Vector'], body_mats['body'],
              mat_socket=group_in.outputs['Body Part Material'])

    # Spine / waist connector (chest → pelvis, thicker than limbs)
    waist_profile = add_node(tree, 'GeometryNodeCurvePrimitiveCircle',
                             x_limb - 200, -1550, "Waist Profile")
    waist_profile.mode = 'RADIUS'
    waist_profile.inputs['Radius'].default_value = WAIST_TUBE_RADIUS
    waist_profile.inputs['Resolution'].default_value = 6

    spine_ln = add_node(tree, 'GeometryNodeCurvePrimitiveLine',
                        x_limb, -1200, "Spine Ln")
    spine_ln.mode = 'POINTS'
    tree.links.new(chest_pos.outputs['Vector'], spine_ln.inputs['Start'])
    tree.links.new(pelvis_pos.outputs['Vector'], spine_ln.inputs['End'])

    spine_tube = add_node(tree, 'GeometryNodeCurveToMesh',
                          x_limb + 200, -1200, "Spine Tube")
    tree.links.new(spine_ln.outputs['Curve'], spine_tube.inputs['Curve'])
    tree.links.new(waist_profile.outputs['Curve'],
                   spine_tube.inputs['Profile Curve'])

    spine_sm = add_node(tree, 'GeometryNodeSetShadeSmooth',
                        x_limb + 400, -1200, "Spine Sm")
    tree.links.new(spine_tube.outputs['Mesh'], spine_sm.inputs['Geometry'])

    spine_mt = add_node(tree, 'GeometryNodeSetMaterial',
                        x_limb + 600, -1200, "Spine Mt")
    tree.links.new(spine_sm.outputs['Geometry'], spine_mt.inputs['Geometry'])
    tree.links.new(group_in.outputs['Body Part Material'],
                   spine_mt.inputs['Material'])
    parts_geo.append(spine_mt.outputs['Geometry'])

    _frame_section(tree,
        "THE SKELETON — Two-bone IK (law of cosines) for"
        " elbows/knees + limb tubes + neck + spine",
        'skeleton', _new_nodes(tree, snap_state))
    snap_state = _snap_nodes(tree)

    return {
        'parts_geo': parts_geo,
        '_idx_chest': _idx_chest,
        '_idx_pelvis': _idx_pelvis,
        '_idx_foot_l': _idx_foot_l,
        '_idx_foot_r': _idx_foot_r,
        'hand_l_pos': hand_l_pos,
        'hand_r_pos': hand_r_pos,
        'x_part': x_part,
        'x_limb': x_limb,
        'snap_state': snap_state,
    }
