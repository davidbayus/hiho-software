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

from ._common import add_node
from .capsules import add_dynamic_capsule


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
