# SPDX-License-Identifier: GPL-3.0-or-later
"""PPParty — Create Marionette V0.9.6: Node groups + tree organization.

V0.9.6:
- Three reusable node groups with internal frames and descriptions:
  PP_DynCapsule (Minkowski capsule), PP_TwoBoneIK (elbow/knee solver),
  PP_ShoulderFloat (Jim Rose drift). Collapses ~244 inline nodes into
  14 group instances. Each group has labeled sub-frames explaining the math.
- Colored Frame nodes around every section of the GN tree for readability.
- 12 labeled sections: Face, Control Bar, Strings, Attachments, Rest Pose,
  Sim Zone, Physics Core, Shoulder Float, Verlet, Body, Skeleton, Assembly.

V0.9.5:
- Colored Frame nodes around every section of the GN tree for readability.
- Each label explains the section's role in the marionette design.
- Zero functional changes — same connections, same physics, same behavior.

V0.9.0:
- Head customization passthrough: all 27 blob head sliders (eyes, mouth,
  nose, ears, eyebrows, lips, head shape) automatically read from the
  blob template's interface and exposed on PPParty's modifier.
- Green Room's blob head is now fully designable inside PPParty.
- "Head Design" section in N-panel with organized sub-groups.

V0.8.0:
- Minkowski capsule body parts (chest, pelvis, hands, feet) — same math
  as Green Room blob puppet. Width sliders morph spheres → pill shapes.
- Customization panel: Body Width, Hand Size, Foot Size, colors for each
  body part. "Make It Yours" section in N-panel.
- All body parts shade smooth + dynamic capsule geometry.
- Hand Size / Foot Size scale the transform on those parts.
- FIXED backward foot drag: ground friction now only pins X (sideways),
  leaving Y free for the hinge forward-bias to pull feet forward.
  LEG_HINGE_BIAS doubled from 0.06 to 0.12.

V0.7.0 (REMOVED):
- Torso momentum was attempted but created a circular dependency in the
  sim zone (sim_out → chest_pos → attachments → zone → sim_out).
  Will be re-implemented at the Python/OSC level. Momentum slider
  remains in interface for future use.

V0.5.0:
- Contralateral knee lift: mouthLeft raises right foot, mouthRight raises
  left foot. New deliberate stepping expression channel.
- Step Strength slider in Body Movement panel (default 0.4).
- Arm gestures: smile lifts hands (celebration), frown drops them (defeat).
- headRotZ → slight torso rotation.

V0.3.5:
- Mouth left/right → torso lateral shift, jaw open → Z lift booster,
  ground friction, walking bob bumped.

Architecture:
- Blob head loaded from blob_puppet.blend as a GN Group node
- Chest + pelvis body with waist joint (V0.2.1)
- Verlet physics in sim zone with hinge constraints on all 4 endpoints
- Shoulder float modifies attachment points using previous-frame endpoint positions
- Elbows/knees computed analytically outside sim zone (no extra state items)
- Body: head → neck → chest → waist joint → pelvis chain
"""

import bpy
from mathutils import Vector

from .marionette._common import (
    add_node,
    FRAME_COLORS,
    _snap_nodes,
    _new_nodes,
    _frame_section,
    _vector_lerp,
)
from .marionette.capsules import add_dynamic_capsule
from .marionette.materials import (
    make_material,
    create_body_materials,
    create_blob_head_materials,
)
from .marionette.blob_head import (
    load_blob_head_tree,
    enumerate_blob_custom_sockets,
    add_head_customization_sockets,
    build_blob_group,
)
from .marionette.body_parts import (
    add_capsule_part,
    add_sphere_part,
    add_limb,
    build_body_parts,
)
from .marionette.face_tracking import (
    FACE_INPUTS,
    build_face_tracking_interface,
)


# ===================================================================
# CONSTANTS
# ===================================================================

# Fixed body position (no empties — head rotation drives everything)
BODY_CENTER = Vector((0.0, 0.0, 0.0))
HEAD_OFFSET = Vector((0.0, 0.0, 0.48))
SHOULDER_L_OFFSET = Vector((-0.42, 0.0, 0.15))
SHOULDER_R_OFFSET = Vector((0.42, 0.0, 0.15))
HIP_L_OFFSET = Vector((-0.2, 0.0, -0.3))
HIP_R_OFFSET = Vector((0.2, 0.0, -0.3))

# Two-part torso: chest (shoulders attach here) + pelvis (hips attach here)
# Connected by a waist joint — matches real marionette anatomy (Jim Rose).
# Body-geometry radii (CHEST_RADIUS, PELVIS_RADIUS, HAND_RADIUS, etc.)
# live with their consumer in marionette/body_parts.py.
CHEST_OFFSET = Vector((0.0, 0.0, 0.07))
PELVIS_OFFSET = Vector((0.0, 0.0, -0.22))

BLOB_HEAD_SCALE = 0.6  # Blob head scaled to sit on marionette body

# Cheek capsules — reactive puffs that respond to smiling
CHEEK_RADIUS = 0.06
CHEEK_LOCAL_X = 0.17     # left/right offset from head center (in world units)
CHEEK_LOCAL_Y = -0.06    # slightly forward (toward camera/face)
CHEEK_LOCAL_Z = -0.04    # slightly below head center (cheek level)
CHEEK_PUFF_SCALE = 0.6   # max additional scale from smile (60% bigger at full smile)

# Joint constraints (Jim Rose marionette research)
SHOULDER_FLOAT_SLACK = 0.08    # max drift distance (digital 5/8" slack)
SHOULDER_FLOAT_ENGAGE = 0.5    # fraction of arm length before float engages
HINGE_LIMIT = 0.04             # max Y-component in forbidden direction (was 0.08)
INWARD_LIMIT = 0.3             # max X-direction toward body center (~17°)
MIDLINE_MARGIN = 0.18          # hard X clamp — keeps hands outside chest (radius 0.2)
ARM_BEND_BIAS = 0.0            # removed: was accumulating drift per frame
LEG_BEND_BIAS = 0.0            # removed: was accumulating drift per frame
FOOT_SPREAD_DIR = 0.5          # max X-direction away from body (limits lateral splay)
FOOT_MIDLINE = 0.08            # wider than hand midline — feet stay under hips
LEG_HINGE_BIAS = -0.12         # negative so -(-0.12)=+0.12 → feet forced forward (fixes backward drag)

# State items for sim zone
POS_NAMES = ['pos_hand_l', 'pos_hand_r', 'pos_foot_l', 'pos_foot_r']
PREV_NAMES = ['prev_hand_l', 'prev_hand_r', 'prev_foot_l', 'prev_foot_r']

# FACE_INPUTS (the 18 ARKit blend shape names) now lives with the face
# tracking interface builder in marionette/face_tracking.py. Re-exported
# at the top of this file for callers that still reference it.



# ===================================================================
# REUSABLE NODE GROUPS — collapse repeated math into single nodes
# ===================================================================
# Note: PP_DynCapsule (the Minkowski capsule group) lives in
# marionette/capsules.py. PP_TwoBoneIK (elbow/knee solver) lives in
# marionette/body_parts.py (sibling of the body composition it serves).
# PP_ShoulderFloat (Jim Rose shoulder drift) is still defined below
# and will move with physics.py in a later refactor step.
# See REFACTOR_PLAN.md for the curriculum order.

def _ensure_float_group():
    """Create or retrieve the PP_ShoulderFloat node group.

    Jim Rose shoulder float: attachment drifts toward the hand when
    the arm is pulled past an engage threshold. Max drift = float_amount.
    Replaces ~12 inline nodes per shoulder.
    """
    existing = bpy.data.node_groups.get("PP_ShoulderFloat")
    if existing:
        return existing

    g = bpy.data.node_groups.new("PP_ShoulderFloat", 'GeometryNodeTree')
    g.interface.clear()

    g.interface.new_socket(
        "Base Attach", in_out='INPUT', socket_type='NodeSocketVector')
    g.interface.new_socket(
        "Endpoint Pos", in_out='INPUT', socket_type='NodeSocketVector')
    s = g.interface.new_socket(
        "Float Amount", in_out='INPUT', socket_type='NodeSocketFloat')
    s.default_value = SHOULDER_FLOAT_SLACK
    s = g.interface.new_socket(
        "Arm Length", in_out='INPUT', socket_type='NodeSocketFloat')
    s.default_value = 0.7
    # Named 'Vector' so callers can use .outputs['Vector'] unchanged
    g.interface.new_socket(
        "Vector", in_out='OUTPUT', socket_type='NodeSocketVector')

    dx = 200
    gin = add_node(g, 'NodeGroupInput', 0, 0, "In")

    # --- Drift measurement ---
    drift = add_node(g, 'ShaderNodeVectorMath', dx, 0, "Drift")
    drift.operation = 'SUBTRACT'
    g.links.new(gin.outputs['Endpoint Pos'], drift.inputs[0])
    g.links.new(gin.outputs['Base Attach'], drift.inputs[1])

    dist = add_node(g, 'ShaderNodeVectorMath', dx * 2, 0, "Dist")
    dist.operation = 'LENGTH'
    g.links.new(drift.outputs['Vector'], dist.inputs[0])

    d_dir = add_node(g, 'ShaderNodeVectorMath', dx * 2, -120, "Dir")
    d_dir.operation = 'NORMALIZE'
    g.links.new(drift.outputs['Vector'], d_dir.inputs[0])

    _frame_section(g,
        "DRIFT — How far and which direction the hand"
        " is pulling from the shoulder base position",
        'control', [drift, dist, d_dir])

    # --- Engage threshold + clamped excess ---
    engage = add_node(g, 'ShaderNodeMath', dx * 3, 0, "Engage")
    engage.operation = 'MULTIPLY'
    g.links.new(gin.outputs['Arm Length'], engage.inputs[0])
    engage.inputs[1].default_value = SHOULDER_FLOAT_ENGAGE

    excess = add_node(g, 'ShaderNodeMath', dx * 4, 0, "Excess")
    excess.operation = 'SUBTRACT'
    g.links.new(dist.outputs['Value'], excess.inputs[0])
    g.links.new(engage.outputs['Value'], excess.inputs[1])

    exc_clamp = add_node(g, 'ShaderNodeMath', dx * 5, 0, "Exc+")
    exc_clamp.operation = 'MAXIMUM'
    g.links.new(excess.outputs['Value'], exc_clamp.inputs[0])
    exc_clamp.inputs[1].default_value = 0.0

    drift_clamp = add_node(g, 'ShaderNodeMath', dx * 6, 0, "DClp")
    drift_clamp.operation = 'MINIMUM'
    g.links.new(exc_clamp.outputs['Value'], drift_clamp.inputs[0])
    g.links.new(gin.outputs['Float Amount'], drift_clamp.inputs[1])

    _frame_section(g,
        "SLACK — Only drift after arm exceeds engage distance,"
        " then cap at Jim Rose's 5/8 inch maximum float",
        'strings', [engage, excess, exc_clamp, drift_clamp])

    # --- Final floated position ---
    drift_sc = add_node(g, 'ShaderNodeVectorMath', dx * 6, -120, "DSc")
    drift_sc.operation = 'SCALE'
    g.links.new(d_dir.outputs['Vector'], drift_sc.inputs[0])
    g.links.new(drift_clamp.outputs['Value'], drift_sc.inputs['Scale'])

    floated = add_node(g, 'ShaderNodeVectorMath', dx * 7, 0, "Float")
    floated.operation = 'ADD'
    g.links.new(gin.outputs['Base Attach'], floated.inputs[0])
    g.links.new(drift_sc.outputs['Vector'], floated.inputs[1])

    _frame_section(g,
        "FLOAT — Shift shoulder attachment toward the hand"
        " by the clamped drift amount",
        'body', [drift_sc, floated])

    gout = add_node(g, 'NodeGroupOutput', dx * 8, 0, "Out")
    g.links.new(floated.outputs['Vector'], gout.inputs['Vector'])

    return g


# ===================================================================
# SIMULATION ZONE — must use operator for proper pairing (Blender 5.2)
# ===================================================================

def _create_sim_zone(tree, context):
    """Create a properly paired simulation zone via Blender's operator.

    In Blender 5.2, creating GeometryNodeSimulationInput/Output directly
    via tree.nodes.new() produces UNPAIRED nodes. The operator
    bpy.ops.node.add_simulation_zone() creates correctly paired nodes.
    """
    node_area = None
    saved_type = None

    for area in context.screen.areas:
        if area.type == 'NODE_EDITOR':
            node_area = area
            break

    if node_area is None:
        for area in context.screen.areas:
            if area.type not in ('VIEW_3D',):
                saved_type = area.type
                area.type = 'NODE_EDITOR'
                node_area = area
                break

    if node_area is None:
        raise RuntimeError(
            "Could not find or create a Node Editor area. "
            "Open a Geometry Nodes editor and try again.")

    try:
        for region in node_area.regions:
            if region.type == 'WINDOW':
                with context.temp_override(
                        area=node_area,
                        region=region,
                        space_data=node_area.spaces.active):
                    node_area.spaces.active.node_tree = tree
                    bpy.ops.node.add_simulation_zone()
                break
    finally:
        if saved_type is not None:
            node_area.type = saved_type

    sim_in = sim_out = None
    for node in tree.nodes:
        if node.type == 'SIMULATION_INPUT':
            sim_in = node
        elif node.type == 'SIMULATION_OUTPUT':
            sim_out = node

    if not sim_in or not sim_out:
        raise RuntimeError("Simulation zone creation failed")

    return sim_in, sim_out


# ===================================================================
# VERLET PHYSICS — per-endpoint node builder
# ===================================================================

def _add_verlet_endpoint(tree, x, y, label,
                         pos_out, prev_out,
                         attach_out, length_out,
                         grav_vec_out, damping_out,
                         is_first_out, not_first_out,
                         rest_out,
                         hinge_axis=None, hinge_limit=0.15,
                         inward_limit=None,
                         ground_z_out=None,
                         midline_clamp=None,
                         bend_bias_y=0.0,
                         ground_friction_out=None):
    """Build Verlet integration + distance constraint for one limb endpoint.

    Physics: new_pos = pos + (pos - prev) * damping + gravity_vec
    Constraint: project onto sphere of `length` around `attachment`
    Hinge (optional): clamp the direction vector's Y component to prevent
        the limb from entering a forbidden half-space (hyperextension).
    Inward limit (optional): clamp direction X to prevent arm reaching
        across the body (Jim Rose joint stop).
    Ground friction (optional): when endpoint is near ground, blend XY
        toward previous position (kills horizontal slide on contact).
    Ground (optional): clamp Z >= ground_z to prevent passing through floor.
    Midline (optional): hard X position clamp as safety net.
    Init: on first frame, snap to rest position instead.

    hinge_axis: 'Y' = arms (clamp Y <= limit, can't reach behind body),
                '-Y' = legs (clamp Y >= -limit, can't kick forward).
                None = no hinge constraint.
    inward_limit: ('MINIMUM', val) or ('MAXIMUM', val) for direction X clamp.
    ground_z_out: socket providing ground plane height, or None.
    midline_clamp: ('MINIMUM', val) or ('MAXIMUM', val) for position X clamp.

    Returns (final_pos_socket, final_prev_socket) for SimOutput wiring.
    """
    dx = 200

    # --- Verlet integration ---
    vel = add_node(tree, 'ShaderNodeVectorMath', x, y, f"{label} Vel")
    vel.operation = 'SUBTRACT'
    tree.links.new(pos_out, vel.inputs[0])
    tree.links.new(prev_out, vel.inputs[1])

    vel_d = add_node(tree, 'ShaderNodeVectorMath', x + dx, y, f"{label} VD")
    vel_d.operation = 'SCALE'
    tree.links.new(vel.outputs['Vector'], vel_d.inputs[0])
    tree.links.new(damping_out, vel_d.inputs['Scale'])

    pv = add_node(tree, 'ShaderNodeVectorMath', x + dx * 2, y, f"{label} +V")
    pv.operation = 'ADD'
    tree.links.new(pos_out, pv.inputs[0])
    tree.links.new(vel_d.outputs['Vector'], pv.inputs[1])

    pvg = add_node(tree, 'ShaderNodeVectorMath', x + dx * 3, y, f"{label} +G")
    pvg.operation = 'ADD'
    tree.links.new(pv.outputs['Vector'], pvg.inputs[0])
    tree.links.new(grav_vec_out, pvg.inputs[1])

    # --- Bend bias (A-pose): tiny persistent push so limbs never hang
    # perfectly straight. Breaks IK degeneracy → visible elbow/knee bend.
    physics_pos = pvg.outputs['Vector']
    if bend_bias_y != 0.0:
        bias = add_node(tree, 'ShaderNodeCombineXYZ', x + dx * 3,
                        y - 80, f"{label} Bias")
        bias.inputs['Y'].default_value = bend_bias_y

        pvb = add_node(tree, 'ShaderNodeVectorMath', x + dx * 4, y - 40,
                       f"{label} +B")
        pvb.operation = 'ADD'
        tree.links.new(pvg.outputs['Vector'], pvb.inputs[0])
        tree.links.new(bias.outputs['Vector'], pvb.inputs[1])
        physics_pos = pvb.outputs['Vector']

    # --- Distance constraint ---
    r2 = y - 180

    off = add_node(tree, 'ShaderNodeVectorMath', x + dx * 2, r2, f"{label} Off")
    off.operation = 'SUBTRACT'
    tree.links.new(physics_pos, off.inputs[0])
    tree.links.new(attach_out, off.inputs[1])

    nrm = add_node(tree, 'ShaderNodeVectorMath', x + dx * 3, r2, f"{label} Nrm")
    nrm.operation = 'NORMALIZE'
    tree.links.new(off.outputs['Vector'], nrm.inputs[0])

    # --- Optional hinge constraint on direction vector ---
    # Clamp the Y component of the normalized direction, then renormalize.
    # This prevents the endpoint from crossing into a forbidden half-space.
    direction_out = nrm.outputs['Vector']

    if hinge_axis is not None:
        rh = r2 - 100

        h_sep = add_node(tree, 'ShaderNodeSeparateXYZ', x + dx * 4, rh,
                         f"{label} HSep")
        tree.links.new(nrm.outputs['Vector'], h_sep.inputs['Vector'])

        # Y-axis hinge: prevent hyperextension (existing)
        h_clamp = add_node(tree, 'ShaderNodeMath', x + dx * 5, rh,
                           f"{label} HClp")
        if hinge_axis == 'Y':
            h_clamp.operation = 'MINIMUM'
            h_clamp.inputs[1].default_value = hinge_limit
        else:  # '-Y'
            h_clamp.operation = 'MAXIMUM'
            h_clamp.inputs[1].default_value = -hinge_limit
        tree.links.new(h_sep.outputs['Y'], h_clamp.inputs[0])

        # X-axis inward limit: prevent arm reaching across body
        # (Jim Rose: flat-face joint stop at the shoulder)
        x_input = h_sep.outputs['X']
        if inward_limit is not None:
            h_clamp_x = add_node(tree, 'ShaderNodeMath', x + dx * 5,
                                 rh - 80, f"{label} HClX")
            h_clamp_x.operation = inward_limit[0]
            h_clamp_x.inputs[1].default_value = inward_limit[1]
            tree.links.new(h_sep.outputs['X'], h_clamp_x.inputs[0])
            x_input = h_clamp_x.outputs['Value']

        h_cmb = add_node(tree, 'ShaderNodeCombineXYZ', x + dx * 6, rh,
                         f"{label} HCmb")
        tree.links.new(x_input, h_cmb.inputs['X'])
        tree.links.new(h_clamp.outputs['Value'], h_cmb.inputs['Y'])
        tree.links.new(h_sep.outputs['Z'], h_cmb.inputs['Z'])

        h_nrm = add_node(tree, 'ShaderNodeVectorMath', x + dx * 7, rh,
                         f"{label} HNrm")
        h_nrm.operation = 'NORMALIZE'
        tree.links.new(h_cmb.outputs['Vector'], h_nrm.inputs[0])

        direction_out = h_nrm.outputs['Vector']

    # Scale direction by limb length + offset from attachment
    scl = add_node(tree, 'ShaderNodeVectorMath', x + dx * 4, r2, f"{label} *L")
    scl.operation = 'SCALE'
    tree.links.new(direction_out, scl.inputs[0])
    tree.links.new(length_out, scl.inputs['Scale'])

    con = add_node(tree, 'ShaderNodeVectorMath', x + dx * 5, r2, f"{label} Con")
    con.operation = 'ADD'
    tree.links.new(attach_out, con.inputs[0])
    tree.links.new(scl.outputs['Vector'], con.inputs[1])

    # --- Optional ground plane collision (Z-clamp) ---
    # Prevents endpoint from passing through the floor.
    # Clamp Z >= ground_z so feet plant on the ground → knees bend.
    con_out = con.outputs['Vector']

    if ground_z_out is not None:
        rg = r2 - 60

        g_sep = add_node(tree, 'ShaderNodeSeparateXYZ', x + dx * 6, rg,
                         f"{label} GSep")
        tree.links.new(con.outputs['Vector'], g_sep.inputs['Vector'])

        g_clamp = add_node(tree, 'ShaderNodeMath', x + dx * 7, rg,
                           f"{label} GClp")
        g_clamp.operation = 'MAXIMUM'
        tree.links.new(g_sep.outputs['Z'], g_clamp.inputs[0])
        tree.links.new(ground_z_out, g_clamp.inputs[1])

        g_cmb = add_node(tree, 'ShaderNodeCombineXYZ', x + dx * 8, rg,
                         f"{label} GCmb")
        tree.links.new(g_sep.outputs['X'], g_cmb.inputs['X'])
        tree.links.new(g_sep.outputs['Y'], g_cmb.inputs['Y'])
        tree.links.new(g_clamp.outputs['Value'], g_cmb.inputs['Z'])

        con_out = g_cmb.outputs['Vector']

    # --- Optional midline safety clamp (X position) ---
    # Hard stop: hand can't cross the body's center line.
    # Catches anything that slips past the direction-based inward limit.
    if midline_clamp is not None:
        rm = r2 - 120 if ground_z_out else r2 - 60

        m_sep = add_node(tree, 'ShaderNodeSeparateXYZ', x + dx * 6, rm,
                         f"{label} MSep")
        tree.links.new(con_out, m_sep.inputs['Vector'])

        m_clp = add_node(tree, 'ShaderNodeMath', x + dx * 7, rm,
                         f"{label} MClp")
        m_clp.operation = midline_clamp[0]
        m_clp.inputs[1].default_value = midline_clamp[1]
        tree.links.new(m_sep.outputs['X'], m_clp.inputs[0])

        m_cmb = add_node(tree, 'ShaderNodeCombineXYZ', x + dx * 8, rm,
                         f"{label} MCmb")
        tree.links.new(m_clp.outputs['Value'], m_cmb.inputs['X'])
        tree.links.new(m_sep.outputs['Y'], m_cmb.inputs['Y'])
        tree.links.new(m_sep.outputs['Z'], m_cmb.inputs['Z'])

        con_out = m_cmb.outputs['Vector']

    # --- Optional ground friction (damp XY slide when on floor) ---
    # When foot touches ground, blend XY toward previous position.
    # Kills horizontal velocity on contact → feet stop sliding.
    if ground_z_out is not None and ground_friction_out is not None:
        rf = r2 - 240

        # Height above ground → proximity [1=on ground, 0=above]
        f_sep = add_node(tree, 'ShaderNodeSeparateXYZ', x + dx * 6, rf,
                         f"{label} FSep")
        tree.links.new(con_out, f_sep.inputs['Vector'])

        f_height = add_node(tree, 'ShaderNodeMath', x + dx * 7, rf,
                            f"{label} FHgt")
        f_height.operation = 'SUBTRACT'
        tree.links.new(f_sep.outputs['Z'], f_height.inputs[0])
        tree.links.new(ground_z_out, f_height.inputs[1])

        f_sc10 = add_node(tree, 'ShaderNodeMath', x + dx * 8, rf,
                          f"{label} F*10")
        f_sc10.operation = 'MULTIPLY'
        tree.links.new(f_height.outputs['Value'], f_sc10.inputs[0])
        f_sc10.inputs[1].default_value = 10.0

        f_inv = add_node(tree, 'ShaderNodeMath', x + dx * 9, rf,
                         f"{label} F1-")
        f_inv.operation = 'SUBTRACT'
        f_inv.inputs[0].default_value = 1.0
        tree.links.new(f_sc10.outputs['Value'], f_inv.inputs[1])

        f_max0 = add_node(tree, 'ShaderNodeMath', x + dx * 10, rf,
                          f"{label} F>0")
        f_max0.operation = 'MAXIMUM'
        tree.links.new(f_inv.outputs['Value'], f_max0.inputs[0])
        f_max0.inputs[1].default_value = 0.0

        f_min1 = add_node(tree, 'ShaderNodeMath', x + dx * 10, rf - 80,
                          f"{label} F<1")
        f_min1.operation = 'MINIMUM'
        tree.links.new(f_max0.outputs['Value'], f_min1.inputs[0])
        f_min1.inputs[1].default_value = 1.0

        # blend = proximity * friction_amount
        f_blend = add_node(tree, 'ShaderNodeMath', x + dx * 11, rf,
                           f"{label} FBld")
        f_blend.operation = 'MULTIPLY'
        tree.links.new(f_min1.outputs['Value'], f_blend.inputs[0])
        tree.links.new(ground_friction_out, f_blend.inputs[1])

        # "Stuck" position: previous X, CONSTRAINED Y, physics Z.
        # Only pin X (sideways). Y stays free so the hinge forward-bias
        # can pull feet forward — fixes the backward-drag bug.
        p_sep = add_node(tree, 'ShaderNodeSeparateXYZ', x + dx * 6,
                         rf - 160, f"{label} PSep")
        tree.links.new(pos_out, p_sep.inputs['Vector'])

        stuck = add_node(tree, 'ShaderNodeCombineXYZ', x + dx * 8,
                         rf - 160, f"{label} Stuck")
        tree.links.new(p_sep.outputs['X'], stuck.inputs['X'])
        tree.links.new(f_sep.outputs['Y'], stuck.inputs['Y'])
        tree.links.new(f_sep.outputs['Z'], stuck.inputs['Z'])

        # Lerp: result = con_out + (stuck - con_out) * blend
        f_diff = add_node(tree, 'ShaderNodeVectorMath', x + dx * 10,
                          rf - 160, f"{label} FDif")
        f_diff.operation = 'SUBTRACT'
        tree.links.new(stuck.outputs['Vector'], f_diff.inputs[0])
        tree.links.new(con_out, f_diff.inputs[1])

        f_dsc = add_node(tree, 'ShaderNodeVectorMath', x + dx * 11,
                         rf - 100, f"{label} FSc")
        f_dsc.operation = 'SCALE'
        tree.links.new(f_diff.outputs['Vector'], f_dsc.inputs[0])
        tree.links.new(f_blend.outputs['Value'], f_dsc.inputs['Scale'])

        f_result = add_node(tree, 'ShaderNodeVectorMath', x + dx * 12,
                            rf - 100, f"{label} FFrc")
        f_result.operation = 'ADD'
        tree.links.new(con_out, f_result.inputs[0])
        tree.links.new(f_dsc.outputs['Vector'], f_result.inputs[1])

        con_out = f_result.outputs['Vector']

    # --- Initialization mix (first frame: rest position, else: physics) ---
    has_constraints = hinge_axis or ground_z_out or midline_clamp
    r3 = y - 480 if has_constraints else y - 380
    if ground_z_out is not None and ground_friction_out is not None:
        r3 -= 300  # extra room for friction nodes

    rest_sc = add_node(tree, 'ShaderNodeVectorMath', x + dx * 4, r3,
                       f"{label} rSc")
    rest_sc.operation = 'SCALE'
    tree.links.new(rest_out, rest_sc.inputs[0])
    tree.links.new(is_first_out, rest_sc.inputs['Scale'])

    con_sc = add_node(tree, 'ShaderNodeVectorMath', x + dx * 4, r3 - 160,
                      f"{label} cSc")
    con_sc.operation = 'SCALE'
    tree.links.new(con_out, con_sc.inputs[0])
    tree.links.new(not_first_out, con_sc.inputs['Scale'])

    fp = add_node(tree, 'ShaderNodeVectorMath', x + dx * 5, r3 - 80,
                  f"{label} Pos")
    fp.operation = 'ADD'
    tree.links.new(con_sc.outputs['Vector'], fp.inputs[0])
    tree.links.new(rest_sc.outputs['Vector'], fp.inputs[1])

    pos_sc = add_node(tree, 'ShaderNodeVectorMath', x + dx * 4, r3 - 360,
                      f"{label} pSc")
    pos_sc.operation = 'SCALE'
    tree.links.new(pos_out, pos_sc.inputs[0])
    tree.links.new(not_first_out, pos_sc.inputs['Scale'])

    fpr = add_node(tree, 'ShaderNodeVectorMath', x + dx * 5, r3 - 280,
                   f"{label} Prv")
    fpr.operation = 'ADD'
    tree.links.new(pos_sc.outputs['Vector'], fpr.inputs[0])
    tree.links.new(rest_sc.outputs['Vector'], fpr.inputs[1])

    return fp.outputs['Vector'], fpr.outputs['Vector']


# ===================================================================
# SHOULDER FLOAT — attachment drifts when arm pulls (Jim Rose: 5/8" slack)
# ===================================================================

def _apply_shoulder_float(tree, x, y, label,
                          base_attach_out, endpoint_pos_out,
                          float_amount_out, arm_length_out):
    """Compute a floated shoulder via the PP_ShoulderFloat node group.

    Jim Rose shoulder float: attachment drifts toward the hand when
    the arm is pulled past an engage threshold.
    Returns the group node (.outputs['Vector'] = floated position).
    """
    float_tree = _ensure_float_group()
    grp = add_node(tree, 'GeometryNodeGroup', x, y, label)
    grp.node_tree = float_tree
    tree.links.new(base_attach_out, grp.inputs['Base Attach'])
    tree.links.new(endpoint_pos_out, grp.inputs['Endpoint Pos'])
    tree.links.new(float_amount_out, grp.inputs['Float Amount'])
    tree.links.new(arm_length_out, grp.inputs['Arm Length'])
    return grp


# ===================================================================
# ARMATURE — head bone for receiving phone rotation
# ===================================================================

def create_armature(context):
    """Create a single-bone armature for head rotation.

    The head bone receives phone rotation via OSC. Its Euler angles
    drive the GN modifier inputs (headRotX, headRotY, headRotZ)
    via scripted expression drivers.
    """
    arm_data = bpy.data.armatures.new("PP_Armature")
    arm_obj = bpy.data.objects.new("PP_Armature", arm_data)
    context.collection.objects.link(arm_obj)

    # Enter edit mode to add the bone
    context.view_layer.objects.active = arm_obj
    bpy.ops.object.mode_set(mode='EDIT')

    bone = arm_data.edit_bones.new("head")
    bone.head = (0, 0, 0.0)
    bone.tail = (0, 0, 0.5)

    bpy.ops.object.mode_set(mode='OBJECT')

    # CRITICAL: Euler rotation mode (Blender defaults to Quaternion,
    # which would ignore rotation_euler from the phone)
    arm_obj.pose.bones['head'].rotation_mode = 'XYZ'

    # Hide armature display — student doesn't need to see it
    arm_obj.hide_viewport = True

    return arm_obj


# ===================================================================
# DATA FLOW — face tracking + head rotation reach the puppet via
# direct modifier writes in the OSC receiver timer (no drivers).
#
# Blender 5.2 changed GN modifier property paths from IDProperty to
# RNA, which breaks driver_add(). Instead, the OSC receiver's timer
# callback writes shape key values AND head rotation directly to the
# modifier's socket properties every 10ms. See osc_receiver.py
# _push_to_puppet() for the implementation.
# ===================================================================


# ===================================================================
# MAIN TREE BUILDER — blob head + physics body + head-driven movement
# ===================================================================

def build_marionette_tree(tree, body_mats, blob_mats, context):
    """Build the complete GN tree: blob head + chest/pelvis body + physics.

    V0.2.1: Two-part torso (chest + pelvis) connected by waist joint.
    Arms attach to chest, legs attach to pelvis. Spine tube runs through.

    Layout (left to right in the GN editor):
      Col A (-3600):  Group Input
      Col B (-3000):  Blob Head Group node + face tracking wiring
      Col C (-2400):  Transform blob head (rotate + position)
      Col D (-2000):  Body center + head rotation → movement deltas
      Col E (-1600):  Attachment points (static offset + rotation delta)
      Col E.5 (-1100): Torso positions + sway (chest, pelvis, waist)
      Col F (-1200):  Rest positions
      Col G (-600):   Simulation zone input
      Col H (-200…1000): Verlet physics per endpoint
      Col I (1400):   Simulation zone output
      Col J (1800):   Chest, pelvis, waist joint, hands, feet, joints
      Col K (2600):   Limb curves + spine tube + neck
      Col L (3400):   Join blob head + body → Group Output
    """
    tree.nodes.clear()
    tree.interface.clear()

    # ------------------------------------------------------------------
    # PRE-LOAD blob head tree so we can read its customization sockets
    # and create matching passthrough sockets on PPParty's interface.
    # ------------------------------------------------------------------
    blob_tree = load_blob_head_tree()
    blob_custom = enumerate_blob_custom_sockets(blob_tree, FACE_INPUTS)

    # ------------------------------------------------------------------
    # INTERFACE — all modifier-level inputs
    # ------------------------------------------------------------------

    # Face tracking + head rotation panels (all plumbing, hide_in_modifier).
    # Implementation lives in marionette/face_tracking.py.
    build_face_tracking_interface(tree)

    # Body movement sensitivity (tune these in the N-panel)
    mv_panel = tree.interface.new_panel("Body Movement")
    s = tree.interface.new_socket(
        "Lean Strength", in_out='INPUT', socket_type='NodeSocketFloat',
        parent=mv_panel)
    s.default_value = 1.0
    s.min_value = 0.0
    s.max_value = 5.0

    s = tree.interface.new_socket(
        "Extend Strength", in_out='INPUT', socket_type='NodeSocketFloat',
        parent=mv_panel)
    s.default_value = 0.5
    s.min_value = 0.0
    s.max_value = 2.0

    s = tree.interface.new_socket(
        "Lift Strength", in_out='INPUT', socket_type='NodeSocketFloat',
        parent=mv_panel)
    s.default_value = 0.3
    s.min_value = 0.0
    s.max_value = 2.0

    s = tree.interface.new_socket(
        "Step Strength", in_out='INPUT', socket_type='NodeSocketFloat',
        parent=mv_panel)
    s.default_value = 0.4
    s.min_value = 0.0
    s.max_value = 2.0

    s = tree.interface.new_socket(
        "Gesture Strength", in_out='INPUT', socket_type='NodeSocketFloat',
        parent=mv_panel)
    s.default_value = 0.3
    s.min_value = 0.0
    s.max_value = 2.0

    s = tree.interface.new_socket(
        "Momentum", in_out='INPUT', socket_type='NodeSocketFloat',
        parent=mv_panel)
    s.default_value = 0.7
    s.min_value = 0.0
    s.max_value = 0.95
    s.subtype = 'FACTOR'

    # Body Tracking — blend between face heuristics and real body landmarks
    bt_panel = tree.interface.new_panel("Body Tracking")
    s = tree.interface.new_socket(
        "Body Tracking", in_out='INPUT', socket_type='NodeSocketFloat',
        parent=bt_panel)
    s.default_value = 0.0
    s.min_value = 0.0
    s.max_value = 1.0
    s.subtype = 'FACTOR'

    # Shoulder/hip/elbow deltas + body center — plumbing pushed by the
    # receiver from landmark data. Never adjusted by hand.
    for bt_name in ('bt_shl_delta', 'bt_shr_delta',
                     'bt_hipl_delta', 'bt_hipr_delta',
                     'bt_elbow_l_hint', 'bt_elbow_r_hint',
                     'bt_body_center'):
        s = tree.interface.new_socket(
            bt_name, in_out='INPUT', socket_type='NodeSocketVector',
            parent=bt_panel)
        s.hide_in_modifier = True

    s = tree.interface.new_socket(
        "Performance Space", in_out='INPUT', socket_type='NodeSocketFloat',
        parent=bt_panel)
    s.default_value = 1.5
    s.min_value = 0.0
    s.max_value = 5.0

    # Per-limb visibility: receiver pushes 0-1 based on landmark confidence.
    # When a limb drops off camera, its factor → 0, falling back to face
    # heuristics (idle pose). Default 1.0 = fully visible. Plumbing.
    for vis_name in ('vis_arm_l', 'vis_arm_r', 'vis_leg_l', 'vis_leg_r'):
        s = tree.interface.new_socket(
            vis_name, in_out='INPUT', socket_type='NodeSocketFloat',
            parent=bt_panel)
        s.default_value = 1.0
        s.min_value = 0.0
        s.hide_in_modifier = True

    # Arm extension ratios — how bent the real arm is (0 = folded, 1 = straight).
    # Used to scale the tracked hand position to the puppet's arm length,
    # so the IK solver can compute proper elbow bend angles. Plumbing.
    for ext_name in ('bt_arm_l_ext', 'bt_arm_r_ext'):
        s = tree.interface.new_socket(
            ext_name, in_out='INPUT', socket_type='NodeSocketFloat',
            parent=bt_panel)
        s.default_value = 0.85
        s.min_value = 0.0
        s.max_value = 1.0
        s.subtype = 'FACTOR'
        s.hide_in_modifier = True

    # Physics (same as V0.1.1)
    ph_panel = tree.interface.new_panel("Physics")
    s = tree.interface.new_socket(
        "Gravity", in_out='INPUT', socket_type='NodeSocketFloat',
        parent=ph_panel)
    s.default_value = 9.8
    s.min_value = 0.0
    s.max_value = 30.0

    s = tree.interface.new_socket(
        "Damping", in_out='INPUT', socket_type='NodeSocketFloat',
        parent=ph_panel)
    s.default_value = 0.97
    s.min_value = 0.80
    s.max_value = 1.0

    s = tree.interface.new_socket(
        "Arm Length", in_out='INPUT', socket_type='NodeSocketFloat',
        parent=ph_panel)
    s.default_value = 0.7
    s.min_value = 0.2
    s.max_value = 2.0

    s = tree.interface.new_socket(
        "Leg Length", in_out='INPUT', socket_type='NodeSocketFloat',
        parent=ph_panel)
    s.default_value = 0.9
    s.min_value = 0.2
    s.max_value = 2.0

    s = tree.interface.new_socket(
        "Ground Height", in_out='INPUT', socket_type='NodeSocketFloat',
        parent=ph_panel)
    s.default_value = -3.0
    s.min_value = -10.0
    s.max_value = 0.5

    s = tree.interface.new_socket(
        "Ground Friction", in_out='INPUT', socket_type='NodeSocketFloat',
        parent=ph_panel)
    s.default_value = 0.7
    s.min_value = 0.0
    s.max_value = 1.0
    s.subtype = 'FACTOR'

    s = tree.interface.new_socket(
        "Shoulder Float", in_out='INPUT', socket_type='NodeSocketFloat',
        parent=ph_panel)
    s.default_value = SHOULDER_FLOAT_SLACK
    s.min_value = 0.0
    s.max_value = 0.2

    s = tree.interface.new_socket(
        "Upper Arm Ratio", in_out='INPUT', socket_type='NodeSocketFloat',
        parent=ph_panel)
    s.default_value = 0.5
    s.min_value = 0.3
    s.max_value = 0.7
    s.subtype = 'FACTOR'

    s = tree.interface.new_socket(
        "Upper Leg Ratio", in_out='INPUT', socket_type='NodeSocketFloat',
        parent=ph_panel)
    s.default_value = 0.5
    s.min_value = 0.3
    s.max_value = 0.7
    s.subtype = 'FACTOR'

    s = tree.interface.new_socket(
        "Head Gap", in_out='INPUT', socket_type='NodeSocketFloat',
        parent=ph_panel)
    s.default_value = 0.48
    s.min_value = 0.1
    s.max_value = 1.2

    # ------------------------------------------------------------------
    # CUSTOMIZATION — "Make It Yours" sliders for body shape + colors
    # ------------------------------------------------------------------
    cust_panel = tree.interface.new_panel("Customize")

    s = tree.interface.new_socket(
        "Body Width", in_out='INPUT', socket_type='NodeSocketFloat',
        parent=cust_panel)
    s.default_value = 0.0
    s.min_value = 0.0
    s.max_value = 2.0

    s = tree.interface.new_socket(
        "Hand Size", in_out='INPUT', socket_type='NodeSocketFloat',
        parent=cust_panel)
    s.default_value = 1.0
    s.min_value = 0.3
    s.max_value = 2.0

    s = tree.interface.new_socket(
        "Hand Width", in_out='INPUT', socket_type='NodeSocketFloat',
        parent=cust_panel)
    s.default_value = 0.0
    s.min_value = 0.0
    s.max_value = 2.0

    s = tree.interface.new_socket(
        "Hand Rotation", in_out='INPUT', socket_type='NodeSocketFloat',
        parent=cust_panel)
    s.default_value = 0.0
    s.min_value = -180.0
    s.max_value = 180.0

    s = tree.interface.new_socket(
        "Hand Tilt", in_out='INPUT', socket_type='NodeSocketFloat',
        parent=cust_panel)
    s.default_value = 0.0
    s.min_value = -180.0
    s.max_value = 180.0

    s = tree.interface.new_socket(
        "Foot Size", in_out='INPUT', socket_type='NodeSocketFloat',
        parent=cust_panel)
    s.default_value = 1.0
    s.min_value = 0.3
    s.max_value = 2.0

    s = tree.interface.new_socket(
        "Foot Width", in_out='INPUT', socket_type='NodeSocketFloat',
        parent=cust_panel)
    s.default_value = 0.0
    s.min_value = 0.0
    s.max_value = 2.0

    s = tree.interface.new_socket(
        "Foot Depth", in_out='INPUT', socket_type='NodeSocketFloat',
        parent=cust_panel)
    s.default_value = 0.0
    s.min_value = -0.3
    s.max_value = 0.3

    s = tree.interface.new_socket(
        "Foot Rotation", in_out='INPUT', socket_type='NodeSocketFloat',
        parent=cust_panel)
    s.default_value = 0.0
    s.min_value = -180.0
    s.max_value = 180.0

    s = tree.interface.new_socket(
        "Shoulder Width", in_out='INPUT', socket_type='NodeSocketFloat',
        parent=cust_panel)
    s.default_value = 0.0
    s.min_value = 0.0
    s.max_value = 2.0

    s = tree.interface.new_socket(
        "Shoulder Rotation", in_out='INPUT', socket_type='NodeSocketFloat',
        parent=cust_panel)
    s.default_value = 0.0
    s.min_value = -180.0
    s.max_value = 180.0

    # Body part material sockets — full Blender material assignment
    tree.interface.new_socket(
        "Body Part Material", in_out='INPUT',
        socket_type='NodeSocketMaterial', parent=cust_panel)
    tree.interface.new_socket(
        "Hand Material", in_out='INPUT',
        socket_type='NodeSocketMaterial', parent=cust_panel)
    tree.interface.new_socket(
        "Foot Material", in_out='INPUT',
        socket_type='NodeSocketMaterial', parent=cust_panel)
    tree.interface.new_socket(
        "Joint Material", in_out='INPUT',
        socket_type='NodeSocketMaterial', parent=cust_panel)
    tree.interface.new_socket(
        "Limb Material", in_out='INPUT',
        socket_type='NodeSocketMaterial', parent=cust_panel)

    # Cheek capsules — reactive puffs that respond to smiling. Cheeks
    # are facial features (they live on the head, react to mouth shape
    # keys), so their sockets belong with the Blob Head group, not the
    # body's Customize panel. We define them in a standalone "Cheeks"
    # panel and re-parent it under "Blob Head" after add_head_customization_sockets
    # runs (which is what actually creates the Blob Head parent panel).
    cheek_panel = tree.interface.new_panel("Cheeks")

    s = tree.interface.new_socket(
        "Cheek Size", in_out='INPUT', socket_type='NodeSocketFloat',
        parent=cheek_panel)
    s.default_value = 1.0
    s.min_value = 0.0
    s.max_value = 2.0
    s.subtype = 'FACTOR'

    tree.interface.new_socket(
        "Cheek Material", in_out='INPUT',
        socket_type='NodeSocketMaterial', parent=cheek_panel)

    # Cheek transform — matches the Eye transform pattern
    # (Spacing/Height/Depth/Width/Rotation). All defaults at 0 so the
    # addon's out-of-the-box cheeks look identical to before; non-zero
    # slider values shift/stretch/tilt around those baked-in defaults.
    s = tree.interface.new_socket(
        "Cheek Spacing", in_out='INPUT', socket_type='NodeSocketFloat',
        parent=cheek_panel)
    s.default_value = 0.0
    s.min_value = -0.15
    s.max_value = 0.3

    s = tree.interface.new_socket(
        "Cheek Height", in_out='INPUT', socket_type='NodeSocketFloat',
        parent=cheek_panel)
    s.default_value = 0.0
    s.min_value = -0.2
    s.max_value = 0.2

    s = tree.interface.new_socket(
        "Cheek Depth", in_out='INPUT', socket_type='NodeSocketFloat',
        parent=cheek_panel)
    s.default_value = 0.0
    s.min_value = -0.2
    s.max_value = 0.2

    s = tree.interface.new_socket(
        "Cheek Width", in_out='INPUT', socket_type='NodeSocketFloat',
        parent=cheek_panel)
    s.default_value = 0.0
    s.min_value = 0.0
    s.max_value = 2.0

    s = tree.interface.new_socket(
        "Cheek Rotation", in_out='INPUT', socket_type='NodeSocketFloat',
        parent=cheek_panel)
    s.default_value = 0.0
    s.min_value = -180.0
    s.max_value = 180.0

    # Studio Track: Object sockets for custom body parts
    # When a student assigns their modeled mesh, it replaces the capsule.
    # Chest and hips are separate — Jim Rose waist-cord principle
    # (see PUPPET_RIG_R&D/JIM_ROSE_MARIONETTE_RESEARCH.md). A real
    # marionette links them with a twist-limited cord so they can
    # move on independent timelines; PPParty keeps that separation
    # so walking, leaning, and counter-sway stay authentic.
    studio_panel = tree.interface.new_panel("Studio Track")
    # Custom Head placeholder socket — hidden for V1.0.0. The Blob Head is
    # currently the only head option. Un-hide when Round E1 ships custom
    # sculpted-head support (Face-It-style shape-key binding).
    s = tree.interface.new_socket(
        "Custom Head", in_out='INPUT',
        socket_type='NodeSocketObject', parent=studio_panel)
    s.hide_in_modifier = True
    tree.interface.new_socket(
        "Custom Chest", in_out='INPUT',
        socket_type='NodeSocketObject', parent=studio_panel)
    tree.interface.new_socket(
        "Custom Hips", in_out='INPUT',
        socket_type='NodeSocketObject', parent=studio_panel)
    # Custom Hand interface is kept so GN wiring doesn't break, but it's
    # hidden until hand tracking lands in Phase 2 (V1.0.0 hands are
    # procedural "Blob Hands"). Un-hide when hands.py is implemented.
    s = tree.interface.new_socket(
        "Custom Hand", in_out='INPUT',
        socket_type='NodeSocketObject', parent=studio_panel)
    s.hide_in_modifier = True
    tree.interface.new_socket(
        "Custom Foot", in_out='INPUT',
        socket_type='NodeSocketObject', parent=studio_panel)

    # ------------------------------------------------------------------
    # HEAD CUSTOMIZATION — passthrough from blob head template
    # Auto-creates sockets matching the blob's customization interface.
    # Returns the "Blob Head" parent panel so we can nest Cheeks under it.
    # ------------------------------------------------------------------
    head_parent = add_head_customization_sockets(tree, blob_custom)

    # Nest the Cheeks sub-panel under the Blob Head parent so all face
    # customization sits in one collapsible section in the modifier UI.
    #
    # alpha.20 fix: count Blob Head's existing children and pass that
    # count as `to_position`, which places Cheeks at the end (after
    # Lips). `to_position=-1` was observed to leave the panel stranded
    # at top level in Blender 5.2; an explicit positive index is the
    # reliable "append" idiom.
    if head_parent is not None:
        head_children_count = sum(
            1 for item in tree.interface.items_tree
            if getattr(item, 'parent', None) == head_parent)
        tree.interface.move_to_parent(
            cheek_panel, head_parent, head_children_count)

    # Geometry output
    tree.interface.new_socket(
        "Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry')

    # ------------------------------------------------------------------
    # GROUP INPUT / OUTPUT
    # ------------------------------------------------------------------
    group_in = add_node(tree, 'NodeGroupInput', -3600, 0, "Input")
    group_out = add_node(tree, 'NodeGroupOutput', 3600, -1000, "Output")

    _s = _snap_nodes(tree)  # snapshot before Section 1

    # ------------------------------------------------------------------
    # Body center: computed early so head + body share the same root
    # ------------------------------------------------------------------
    x_body = -2000

    body_ctr_static = add_node(tree, 'ShaderNodeCombineXYZ', x_body, 0,
                               "Body Ctr Static")
    body_ctr_static.inputs['X'].default_value = BODY_CENTER.x
    body_ctr_static.inputs['Y'].default_value = BODY_CENTER.y
    body_ctr_static.inputs['Z'].default_value = BODY_CENTER.z

    # Performance space: scale tracked body center by slider, then blend
    # with Body Tracking factor so it only applies when tracking is active
    perf_space = add_node(tree, 'ShaderNodeVectorMath', x_body + 200, -100,
                          "Perf Scale")
    perf_space.operation = 'SCALE'
    tree.links.new(group_in.outputs['bt_body_center'], perf_space.inputs[0])
    tree.links.new(group_in.outputs['Performance Space'],
                   perf_space.inputs['Scale'])

    perf_bt = add_node(tree, 'ShaderNodeVectorMath', x_body + 400, -100,
                       "Perf *BT")
    perf_bt.operation = 'SCALE'
    tree.links.new(perf_space.outputs['Vector'], perf_bt.inputs[0])
    tree.links.new(group_in.outputs['Body Tracking'],
                   perf_bt.inputs['Scale'])

    body_ctr = add_node(tree, 'ShaderNodeVectorMath', x_body + 600, 0,
                        "Body Ctr")
    body_ctr.operation = 'ADD'
    tree.links.new(body_ctr_static.outputs['Vector'], body_ctr.inputs[0])
    tree.links.new(perf_bt.outputs['Vector'], body_ctr.inputs[1])

    # ------------------------------------------------------------------
    # SECTION 1 — Blob Head Group node + face tracking + customization
    # ------------------------------------------------------------------
    # blob_tree was loaded earlier (before interface) to read its sockets.
    blob_geo_out = None
    blob_tf = None
    head_pos_fixed = None

    if blob_tree:
        blob_group = build_blob_group(
            tree, group_in, blob_tree, blob_custom, FACE_INPUTS)

        # Head materials are now passthrough sockets (wired above).
        # No hardcoded mat_map needed — user picks materials in N-panel.

        # Transform blob head: rotate by phone, scale, position at head
        head_rot_vec = add_node(tree, 'ShaderNodeCombineXYZ', -2600, 800,
                                "Head Rot Vec")
        tree.links.new(group_in.outputs['headRotX'],
                       head_rot_vec.inputs['X'])
        tree.links.new(group_in.outputs['headRotY'],
                       head_rot_vec.inputs['Y'])
        tree.links.new(group_in.outputs['headRotZ'],
                       head_rot_vec.inputs['Z'])

        # Head position: body_ctr + HEAD_OFFSET (moves with body tracking)
        # Z component driven by "Head Gap" slider instead of hardcoded 0.48
        head_off_static = add_node(tree, 'ShaderNodeCombineXYZ', -2800, 600,
                                   "Head Off")
        head_off_static.inputs['X'].default_value = HEAD_OFFSET.x
        head_off_static.inputs['Y'].default_value = HEAD_OFFSET.y
        tree.links.new(group_in.outputs['Head Gap'],
                       head_off_static.inputs['Z'])
        head_pos_fixed = add_node(tree, 'ShaderNodeVectorMath', -2600, 600,
                                  "Head Pos")
        head_pos_fixed.operation = 'ADD'
        tree.links.new(body_ctr.outputs['Vector'],
                       head_pos_fixed.inputs[0])
        tree.links.new(head_off_static.outputs['Vector'],
                       head_pos_fixed.inputs[1])

        # ---- Cheek capsules (in head-local space, before blob_tf) ----
        # Build cheeks relative to the blob head, then join them with the
        # blob geometry BEFORE the head transform. This way the cheeks
        # automatically move/rotate/scale with the head — no separate
        # position tracking needed.
        x_ck = -2800
        y_ck = -200
        # Positions and radius in head-local space (before 0.6× scaling)
        ck_r = CHEEK_RADIUS / BLOB_HEAD_SCALE
        ck_lx = CHEEK_LOCAL_X / BLOB_HEAD_SCALE
        ck_ly = CHEEK_LOCAL_Y / BLOB_HEAD_SCALE
        ck_lz = CHEEK_LOCAL_Z / BLOB_HEAD_SCALE

        cheek_parts = []
        for side_idx, (side, sign) in enumerate(
                [("L", -1.0), ("R", 1.0)]):
            y_row = y_ck - side_idx * 400

            # Sphere geometry (head-local scale)
            sphere = add_node(tree, 'GeometryNodeMeshUVSphere',
                              x_ck, y_row, f"Cheek {side}")
            sphere.inputs['Segments'].default_value = 12
            sphere.inputs['Rings'].default_value = 8
            sphere.inputs['Radius'].default_value = ck_r

            # Reactive scale: cheek_size * (1 + smile*puff - funnel*hollow)
            smile_name = ('mouthSmileLeft' if side == 'L'
                          else 'mouthSmileRight')

            puff = add_node(tree, 'ShaderNodeMath',
                            x_ck + 200, y_row - 60, f"Ck {side} Puff")
            puff.operation = 'MULTIPLY'
            tree.links.new(group_in.outputs[smile_name], puff.inputs[0])
            puff.inputs[1].default_value = CHEEK_PUFF_SCALE

            hollow = add_node(tree, 'ShaderNodeMath',
                              x_ck + 200, y_row - 120,
                              f"Ck {side} Hollow")
            hollow.operation = 'MULTIPLY'
            tree.links.new(group_in.outputs['mouthFunnel'],
                           hollow.inputs[0])
            hollow.inputs[1].default_value = -CHEEK_PUFF_SCALE * 0.5

            react = add_node(tree, 'ShaderNodeMath',
                             x_ck + 400, y_row - 90,
                             f"Ck {side} React")
            react.operation = 'ADD'
            tree.links.new(puff.outputs['Value'], react.inputs[0])
            tree.links.new(hollow.outputs['Value'], react.inputs[1])

            one_plus = add_node(tree, 'ShaderNodeMath',
                                x_ck + 600, y_row - 90,
                                f"Ck {side} 1+R")
            one_plus.operation = 'ADD'
            one_plus.inputs[0].default_value = 1.0
            tree.links.new(react.outputs['Value'], one_plus.inputs[1])

            scale_f = add_node(tree, 'ShaderNodeMath',
                               x_ck + 800, y_row - 90,
                               f"Ck {side} Scale")
            scale_f.operation = 'MULTIPLY'
            tree.links.new(group_in.outputs['Cheek Size'],
                           scale_f.inputs[0])
            tree.links.new(one_plus.outputs['Value'], scale_f.inputs[1])

            # --- Width: X stretch on top of the reactive scale ---
            width_plus = add_node(tree, 'ShaderNodeMath',
                                  x_ck + 800, y_row - 180,
                                  f"Ck {side} W+")
            width_plus.operation = 'ADD'
            width_plus.inputs[0].default_value = 1.0
            tree.links.new(group_in.outputs['Cheek Width'],
                           width_plus.inputs[1])

            scale_x = add_node(tree, 'ShaderNodeMath',
                               x_ck + 1000, y_row - 180,
                               f"Ck {side} SX")
            scale_x.operation = 'MULTIPLY'
            tree.links.new(scale_f.outputs['Value'], scale_x.inputs[0])
            tree.links.new(width_plus.outputs['Value'],
                           scale_x.inputs[1])

            scale_vec = add_node(tree, 'ShaderNodeCombineXYZ',
                                 x_ck + 1200, y_row - 90,
                                 f"Ck {side} ScaleVec")
            tree.links.new(scale_x.outputs['Value'],
                           scale_vec.inputs['X'])
            tree.links.new(scale_f.outputs['Value'],
                           scale_vec.inputs['Y'])
            tree.links.new(scale_f.outputs['Value'],
                           scale_vec.inputs['Z'])

            # --- Position: base offsets + Spacing/Height/Depth deltas ---
            sp_add = add_node(tree, 'ShaderNodeMath',
                              x_ck + 200, y_row + 140,
                              f"Ck {side} Sp+")
            sp_add.operation = 'ADD'
            sp_add.inputs[0].default_value = ck_lx
            tree.links.new(group_in.outputs['Cheek Spacing'],
                           sp_add.inputs[1])

            sp_x = add_node(tree, 'ShaderNodeMath',
                            x_ck + 400, y_row + 140,
                            f"Ck {side} SpX")
            sp_x.operation = 'MULTIPLY'
            tree.links.new(sp_add.outputs['Value'], sp_x.inputs[0])
            sp_x.inputs[1].default_value = sign

            dp_add = add_node(tree, 'ShaderNodeMath',
                              x_ck + 200, y_row + 80, f"Ck {side} Dp+")
            dp_add.operation = 'ADD'
            dp_add.inputs[0].default_value = ck_ly
            tree.links.new(group_in.outputs['Cheek Depth'],
                           dp_add.inputs[1])

            hg_add = add_node(tree, 'ShaderNodeMath',
                              x_ck + 200, y_row + 20, f"Ck {side} Hg+")
            hg_add.operation = 'ADD'
            hg_add.inputs[0].default_value = ck_lz
            tree.links.new(group_in.outputs['Cheek Height'],
                           hg_add.inputs[1])

            pos_vec = add_node(tree, 'ShaderNodeCombineXYZ',
                               x_ck + 600, y_row + 80,
                               f"Ck {side} Pos")
            tree.links.new(sp_x.outputs['Value'], pos_vec.inputs['X'])
            tree.links.new(dp_add.outputs['Value'], pos_vec.inputs['Y'])
            tree.links.new(hg_add.outputs['Value'], pos_vec.inputs['Z'])

            # --- Rotation: Cheek Rotation degrees → Y-axis radians ---
            # Y-axis tilts the cheek about the through-face line
            # (same visual as the "tilted eye" effect).
            rot_rad = add_node(tree, 'ShaderNodeMath',
                               x_ck + 600, y_row - 240,
                               f"Ck {side} Rot")
            rot_rad.operation = 'MULTIPLY'
            tree.links.new(group_in.outputs['Cheek Rotation'],
                           rot_rad.inputs[0])
            rot_rad.inputs[1].default_value = 0.017453292519943295

            rot_vec = add_node(tree, 'ShaderNodeCombineXYZ',
                               x_ck + 800, y_row - 240,
                               f"Ck {side} RotV")
            tree.links.new(rot_rad.outputs['Value'],
                           rot_vec.inputs['Y'])

            # Transform: wired position + scale + rotation. Head-level
            # blob_tf still inherits onto the whole assembly afterward.
            ck_tf = add_node(tree, 'GeometryNodeTransform',
                             x_ck + 1400, y_row, f"Ck {side} TF")
            tree.links.new(sphere.outputs['Mesh'],
                           ck_tf.inputs['Geometry'])
            tree.links.new(pos_vec.outputs['Vector'],
                           ck_tf.inputs['Translation'])
            tree.links.new(rot_vec.outputs['Vector'],
                           ck_tf.inputs['Rotation'])
            tree.links.new(scale_vec.outputs['Vector'],
                           ck_tf.inputs['Scale'])

            # Shade smooth + material
            ck_sm = add_node(tree, 'GeometryNodeSetShadeSmooth',
                             x_ck + 1400, y_row, f"Ck {side} Sm")
            tree.links.new(ck_tf.outputs['Geometry'],
                           ck_sm.inputs['Geometry'])

            ck_mt = add_node(tree, 'GeometryNodeSetMaterial',
                             x_ck + 1600, y_row, f"Ck {side} Mt")
            tree.links.new(ck_sm.outputs['Geometry'],
                           ck_mt.inputs['Geometry'])
            tree.links.new(group_in.outputs['Cheek Material'],
                           ck_mt.inputs['Material'])

            cheek_parts.append(ck_mt.outputs['Geometry'])

        # Join blob head + cheeks → single assembly for blob_tf
        head_assembly = add_node(tree, 'GeometryNodeJoinGeometry',
                                 -2500, 400, "Head + Cheeks")
        tree.links.new(blob_group.outputs['Geometry'],
                       head_assembly.inputs['Geometry'])
        for cp in cheek_parts:
            tree.links.new(cp, head_assembly.inputs['Geometry'])

        blob_tf = add_node(tree, 'GeometryNodeTransform', -2400, 600,
                           "Head TF")
        tree.links.new(head_assembly.outputs['Geometry'],
                       blob_tf.inputs['Geometry'])
        tree.links.new(head_pos_fixed.outputs['Vector'],
                       blob_tf.inputs['Translation'])
        tree.links.new(head_rot_vec.outputs['Vector'],
                       blob_tf.inputs['Rotation'])
        blob_tf.inputs['Scale'].default_value = (
            BLOB_HEAD_SCALE, BLOB_HEAD_SCALE, BLOB_HEAD_SCALE)

        blob_geo_out = blob_tf.outputs['Geometry']

    _frame_section(tree,
        "THE FACE — Blob head + ARKit face tracking"
        " + cheek capsules + customization sliders",
        'face', _new_nodes(tree, _s))
    _s = _snap_nodes(tree)

    # ------------------------------------------------------------------
    # SECTION 2 — Head rotation → movement
    # ------------------------------------------------------------------

    # Head rotation → movement: lean (Y) for walking, extend (X) for arms
    x_mv = -1800

    # lean_amount = headRotY * lean_strength
    lean = add_node(tree, 'ShaderNodeMath', x_mv, -200, "Lean Amt")
    lean.operation = 'MULTIPLY'
    tree.links.new(group_in.outputs['headRotY'], lean.inputs[0])
    tree.links.new(group_in.outputs['Lean Strength'], lean.inputs[1])

    # extend_amount = headRotX * extend_strength
    extend = add_node(tree, 'ShaderNodeMath', x_mv, -400, "Extend Amt")
    extend.operation = 'MULTIPLY'
    tree.links.new(group_in.outputs['headRotX'], extend.inputs[0])
    tree.links.new(group_in.outputs['Extend Strength'], extend.inputs[1])

    # Negated versions for opposite sides
    neg_lean = add_node(tree, 'ShaderNodeMath', x_mv + 200, -200,
                        "Neg Lean")
    neg_lean.operation = 'MULTIPLY'
    neg_lean.inputs[1].default_value = -1.0
    tree.links.new(lean.outputs[0], neg_lean.inputs[0])

    neg_extend = add_node(tree, 'ShaderNodeMath', x_mv + 200, -400,
                          "Neg Extend")
    neg_extend.operation = 'MULTIPLY'
    neg_extend.inputs[1].default_value = -1.0
    tree.links.new(extend.outputs[0], neg_extend.inputs[0])

    # Delta vectors per attachment point (contralateral walking gait):
    # Lean right (+Y) → right hand lifts, left leg lifts
    # Lean back (+X) → arms spread outward

    # Shoulder R: (+extend, 0, +lean)
    shr_delta = add_node(tree, 'ShaderNodeCombineXYZ', x_mv + 400, -100,
                         "ShR Delta")
    tree.links.new(extend.outputs[0], shr_delta.inputs['X'])
    tree.links.new(lean.outputs[0], shr_delta.inputs['Z'])

    # Shoulder L: (-extend, 0, -lean)
    shl_delta = add_node(tree, 'ShaderNodeCombineXYZ', x_mv + 400, -250,
                         "ShL Delta")
    tree.links.new(neg_extend.outputs[0], shl_delta.inputs['X'])
    tree.links.new(neg_lean.outputs[0], shl_delta.inputs['Z'])

    # --- Contralateral knee lift from mouth (V0.5.0) ---
    # mouthLeft → lifts RIGHT foot, mouthRight → lifts LEFT foot
    # This gives deliberate stepping control separate from head lean.
    step_l = add_node(tree, 'ShaderNodeMath', x_mv + 200, -600,
                      "Step L")
    step_l.operation = 'MULTIPLY'
    tree.links.new(group_in.outputs['mouthRight'], step_l.inputs[0])
    tree.links.new(group_in.outputs['Step Strength'], step_l.inputs[1])

    step_r = add_node(tree, 'ShaderNodeMath', x_mv + 200, -720,
                      "Step R")
    step_r.operation = 'MULTIPLY'
    tree.links.new(group_in.outputs['mouthLeft'], step_r.inputs[0])
    tree.links.new(group_in.outputs['Step Strength'], step_r.inputs[1])

    # Hip L Z = lean + step from mouthRight (contralateral)
    hipl_z = add_node(tree, 'ShaderNodeMath', x_mv + 400, -420,
                      "HipL Z")
    hipl_z.operation = 'ADD'
    tree.links.new(lean.outputs[0], hipl_z.inputs[0])
    tree.links.new(step_l.outputs['Value'], hipl_z.inputs[1])

    hipl_delta = add_node(tree, 'ShaderNodeCombineXYZ', x_mv + 600, -400,
                          "HipL Delta")
    tree.links.new(hipl_z.outputs['Value'], hipl_delta.inputs['Z'])

    # Hip R Z = neg_lean + step from mouthLeft (contralateral)
    hipr_z = add_node(tree, 'ShaderNodeMath', x_mv + 400, -570,
                      "HipR Z")
    hipr_z.operation = 'ADD'
    tree.links.new(neg_lean.outputs[0], hipr_z.inputs[0])
    tree.links.new(step_r.outputs['Value'], hipr_z.inputs[1])

    hipr_delta = add_node(tree, 'ShaderNodeCombineXYZ', x_mv + 600, -550,
                          "HipR Delta")
    tree.links.new(hipr_z.outputs['Value'], hipr_delta.inputs['Z'])

    # --- Arm gestures from face (V0.5.0) ---
    # Smile lifts hands (celebration), frown drops them (defeat).
    # Uses mouthSmileRight as smile proxy, avg of frown L+R for frown.
    smile_gest = add_node(tree, 'ShaderNodeMath', x_mv + 200, -840,
                          "Smile Gest")
    smile_gest.operation = 'MULTIPLY'
    tree.links.new(group_in.outputs['mouthSmileRight'], smile_gest.inputs[0])
    tree.links.new(group_in.outputs['Gesture Strength'], smile_gest.inputs[1])

    frown_add = add_node(tree, 'ShaderNodeMath', x_mv, -960,
                         "Frown Add")
    frown_add.operation = 'ADD'
    tree.links.new(group_in.outputs['mouthFrownLeft'], frown_add.inputs[0])
    tree.links.new(group_in.outputs['mouthFrownRight'], frown_add.inputs[1])

    frown_avg = add_node(tree, 'ShaderNodeMath', x_mv + 200, -960,
                         "Frown Avg")
    frown_avg.operation = 'MULTIPLY'
    tree.links.new(frown_add.outputs['Value'], frown_avg.inputs[0])
    frown_avg.inputs[1].default_value = 0.5

    frown_gest = add_node(tree, 'ShaderNodeMath', x_mv + 400, -960,
                          "Frown Gest")
    frown_gest.operation = 'MULTIPLY'
    tree.links.new(frown_avg.outputs['Value'], frown_gest.inputs[0])
    tree.links.new(group_in.outputs['Gesture Strength'], frown_gest.inputs[1])

    # Net gesture: smile lifts (+Z), frown drops (-Z)
    gesture_z = add_node(tree, 'ShaderNodeMath', x_mv + 600, -900,
                         "Gesture Z")
    gesture_z.operation = 'SUBTRACT'
    tree.links.new(smile_gest.outputs['Value'], gesture_z.inputs[0])
    tree.links.new(frown_gest.outputs['Value'], gesture_z.inputs[1])

    # Add gesture Z to shoulder deltas
    shr_z_total = add_node(tree, 'ShaderNodeMath', x_mv + 600, -100,
                           "ShR Z+Gest")
    shr_z_total.operation = 'ADD'
    tree.links.new(lean.outputs[0], shr_z_total.inputs[0])
    tree.links.new(gesture_z.outputs['Value'], shr_z_total.inputs[1])

    neg_lean_gest = add_node(tree, 'ShaderNodeMath', x_mv + 600, -250,
                             "ShL Z+Gest")
    neg_lean_gest.operation = 'ADD'
    tree.links.new(neg_lean.outputs[0], neg_lean_gest.inputs[0])
    tree.links.new(gesture_z.outputs['Value'], neg_lean_gest.inputs[1])

    # Re-wire shoulder deltas to include gesture
    # (overwrites previous Z links on the CombineXYZ nodes)
    tree.links.new(shr_z_total.outputs['Value'], shr_delta.inputs['Z'])
    tree.links.new(neg_lean_gest.outputs['Value'], shl_delta.inputs['Z'])

    # --- headRotZ → torso rotation ---
    # Slight Z-axis torso twist adds expressiveness when head tilts sideways
    torso_twist = add_node(tree, 'ShaderNodeMath', x_mv, -1100,
                           "Torso Twist")
    torso_twist.operation = 'MULTIPLY'
    tree.links.new(group_in.outputs['headRotZ'], torso_twist.inputs[0])
    torso_twist.inputs[1].default_value = 0.15  # subtle — 15% of head roll

    _frame_section(tree,
        "THE CONTROL BAR — Head rotation maps to body movement:"
        " lean=gait, extend=arms, mouth=step, smile/frown=gesture",
        'control', _new_nodes(tree, _s))
    _s = _snap_nodes(tree)

    # ------------------------------------------------------------------
    # SECTION 2.5 — Body Tracking blend (lerp heuristic ↔ body landmarks)
    # ------------------------------------------------------------------
    # When Body Tracking > 0, real body landmark deltas (from MediaPipe
    # receiver) blend with the face-heuristic deltas computed above.
    # At 0.0 = pure face heuristics (phone or face-only webcam).
    # At 1.0 = pure body tracking (webcam with body landmarks).
    x_bt = x_mv + 900
    bt_factor = group_in.outputs['Body Tracking']

    # Face-heuristic influence factor: (1 - Body Tracking).
    # When BT is active, face-to-body heuristics (lean→walk, mouth→step,
    # smile→gesture) are fully muted — real body data is the only input.
    # NOTE: Face→body is a cool concept we want to bring back as a
    # "Face Influence" slider. For now, hard-mute during BT for clean test.
    face_factor = add_node(tree, 'ShaderNodeMath', x_bt - 400, 0,
                           "Face Factor")
    face_factor.operation = 'SUBTRACT'
    face_factor.inputs[0].default_value = 1.0
    tree.links.new(bt_factor, face_factor.inputs[1])

    # Mute face-heuristic endpoint deltas by face_factor.
    # Without this, face deltas bleed into the lerp when limb visibility
    # is partial (BT × vis < 1), causing head tilt to drive legs/arms
    # even when body tracking is providing real limb positions.
    shl_delta_muted = add_node(tree, 'ShaderNodeVectorMath', x_bt - 400,
                                -250, "ShL\u00d7Face")
    shl_delta_muted.operation = 'SCALE'
    tree.links.new(shl_delta.outputs['Vector'],
                   shl_delta_muted.inputs[0])
    tree.links.new(face_factor.outputs['Value'],
                   shl_delta_muted.inputs['Scale'])

    shr_delta_muted = add_node(tree, 'ShaderNodeVectorMath', x_bt - 400,
                                -400, "ShR\u00d7Face")
    shr_delta_muted.operation = 'SCALE'
    tree.links.new(shr_delta.outputs['Vector'],
                   shr_delta_muted.inputs[0])
    tree.links.new(face_factor.outputs['Value'],
                   shr_delta_muted.inputs['Scale'])

    hipl_delta_muted = add_node(tree, 'ShaderNodeVectorMath', x_bt - 400,
                                 -550, "HipL\u00d7Face")
    hipl_delta_muted.operation = 'SCALE'
    tree.links.new(hipl_delta.outputs['Vector'],
                   hipl_delta_muted.inputs[0])
    tree.links.new(face_factor.outputs['Value'],
                   hipl_delta_muted.inputs['Scale'])

    hipr_delta_muted = add_node(tree, 'ShaderNodeVectorMath', x_bt - 400,
                                 -700, "HipR\u00d7Face")
    hipr_delta_muted.operation = 'SCALE'
    tree.links.new(hipr_delta.outputs['Vector'],
                   hipr_delta_muted.inputs[0])
    tree.links.new(face_factor.outputs['Value'],
                   hipr_delta_muted.inputs['Scale'])

    # Per-limb effective factors: Body Tracking × limb visibility.
    # When a limb drops off camera, vis → 0, factor → 0 → face heuristic.
    arm_l_factor = add_node(tree, 'ShaderNodeMath', x_bt - 200, -150,
                            "ArmL Vis")
    arm_l_factor.operation = 'MULTIPLY'
    tree.links.new(bt_factor, arm_l_factor.inputs[0])
    tree.links.new(group_in.outputs['vis_arm_l'], arm_l_factor.inputs[1])

    arm_r_factor = add_node(tree, 'ShaderNodeMath', x_bt - 200, -300,
                            "ArmR Vis")
    arm_r_factor.operation = 'MULTIPLY'
    tree.links.new(bt_factor, arm_r_factor.inputs[0])
    tree.links.new(group_in.outputs['vis_arm_r'], arm_r_factor.inputs[1])

    leg_l_factor = add_node(tree, 'ShaderNodeMath', x_bt - 200, -450,
                            "LegL Vis")
    leg_l_factor.operation = 'MULTIPLY'
    tree.links.new(bt_factor, leg_l_factor.inputs[0])
    tree.links.new(group_in.outputs['vis_leg_l'], leg_l_factor.inputs[1])

    leg_r_factor = add_node(tree, 'ShaderNodeMath', x_bt - 200, -600,
                            "LegR Vis")
    leg_r_factor.operation = 'MULTIPLY'
    tree.links.new(bt_factor, leg_r_factor.inputs[0])
    tree.links.new(group_in.outputs['vis_leg_r'], leg_r_factor.inputs[1])

    shl_delta_final = _vector_lerp(
        tree, x_bt, -250, "ShL",
        shl_delta_muted.outputs['Vector'],
        group_in.outputs['bt_shl_delta'],
        arm_l_factor.outputs['Value']).outputs['Vector']

    shr_delta_final = _vector_lerp(
        tree, x_bt, -400, "ShR",
        shr_delta_muted.outputs['Vector'],
        group_in.outputs['bt_shr_delta'],
        arm_r_factor.outputs['Value']).outputs['Vector']

    hipl_delta_final = _vector_lerp(
        tree, x_bt, -550, "HipL",
        hipl_delta_muted.outputs['Vector'],
        group_in.outputs['bt_hipl_delta'],
        leg_l_factor.outputs['Value']).outputs['Vector']

    hipr_delta_final = _vector_lerp(
        tree, x_bt, -700, "HipR",
        hipr_delta_muted.outputs['Vector'],
        group_in.outputs['bt_hipr_delta'],
        leg_r_factor.outputs['Value']).outputs['Vector']

    _frame_section(tree,
        "BODY TRACKING BLEND — Lerp between face heuristics and"
        " real body landmarks from MediaPipe webcam tracking",
        'control', _new_nodes(tree, _s))
    _s = _snap_nodes(tree)

    # ------------------------------------------------------------------
    # SECTION 3 — Torso positions + sway + walking bob + eyebrow lift
    # ------------------------------------------------------------------
    # Torso shifts with head rotation (sway), rises during stride (bob),
    # and lifts when eyebrows raise (pick-up gesture). Head follows too.
    x_sw = -1600

    # --- Walking bob: abs(lean) → vertical rise during stride ---
    # Jim Rose: "we raise our bodies above the ground rather more at
    # the beginning of a step than at the end"
    abs_lean = add_node(tree, 'ShaderNodeMath', x_sw, 700, "Abs Lean")
    abs_lean.operation = 'ABSOLUTE'
    tree.links.new(lean.outputs['Value'], abs_lean.inputs[0])

    bob_chest = add_node(tree, 'ShaderNodeMath', x_sw + 200, 700,
                         "Bob Chest")
    bob_chest.operation = 'MULTIPLY'
    tree.links.new(abs_lean.outputs['Value'], bob_chest.inputs[0])
    bob_chest.inputs[1].default_value = 0.6  # bumped from 0.4

    bob_pelvis = add_node(tree, 'ShaderNodeMath', x_sw + 200, 640,
                          "Bob Pelvis")
    bob_pelvis.operation = 'MULTIPLY'
    tree.links.new(abs_lean.outputs['Value'], bob_pelvis.inputs[0])
    bob_pelvis.inputs[1].default_value = 0.45  # bumped from 0.3

    # --- Eyebrow lift: raise brows → "pick up" the puppet ---
    brow_add = add_node(tree, 'ShaderNodeMath', x_sw, 950, "Brow Add")
    brow_add.operation = 'ADD'
    tree.links.new(group_in.outputs['eyeWideLeft'], brow_add.inputs[0])
    tree.links.new(group_in.outputs['eyeWideRight'], brow_add.inputs[1])

    brow_avg = add_node(tree, 'ShaderNodeMath', x_sw + 200, 950,
                        "Brow Avg")
    brow_avg.operation = 'MULTIPLY'
    tree.links.new(brow_add.outputs['Value'], brow_avg.inputs[0])
    brow_avg.inputs[1].default_value = 0.5

    brow_lift = add_node(tree, 'ShaderNodeMath', x_sw + 400, 950,
                         "Brow Lift")
    brow_lift.operation = 'MULTIPLY'
    tree.links.new(brow_avg.outputs['Value'], brow_lift.inputs[0])
    tree.links.new(group_in.outputs['Lift Strength'], brow_lift.inputs[1])

    # --- Jaw open → Z lift booster ---
    # Wide open mouth usually comes with raised eyebrows — stack the lift
    jaw_lift = add_node(tree, 'ShaderNodeMath', x_sw, 1060, "Jaw Lift")
    jaw_lift.operation = 'MULTIPLY'
    tree.links.new(group_in.outputs['jawOpen'], jaw_lift.inputs[0])
    tree.links.new(group_in.outputs['Lift Strength'], jaw_lift.inputs[1])

    jaw_lift_sc = add_node(tree, 'ShaderNodeMath', x_sw + 200, 1060,
                           "Jaw Lift*0.5")
    jaw_lift_sc.operation = 'MULTIPLY'
    tree.links.new(jaw_lift.outputs['Value'], jaw_lift_sc.inputs[0])
    jaw_lift_sc.inputs[1].default_value = 0.5  # half the brow effect

    # Combined Z lift: brow + jaw
    z_lift = add_node(tree, 'ShaderNodeMath', x_sw + 600, 1000, "Z Lift")
    z_lift.operation = 'ADD'
    tree.links.new(brow_lift.outputs['Value'], z_lift.inputs[0])
    tree.links.new(jaw_lift_sc.outputs['Value'], z_lift.inputs[1])

    # --- Eyebrow raise → arms spread outward (V0.9.0) ---
    # Raised brows push hands away from body on X axis
    brow_spread = add_node(tree, 'ShaderNodeMath', x_sw + 400, 890,
                           "Brow Spread")
    brow_spread.operation = 'MULTIPLY'
    tree.links.new(brow_avg.outputs['Value'], brow_spread.inputs[0])
    tree.links.new(group_in.outputs['Gesture Strength'],
                   brow_spread.inputs[1])

    # Right hand: extend + spread (outward = +X)
    shr_x_total = add_node(tree, 'ShaderNodeMath', x_sw + 600, 890,
                           "ShR X+Spr")
    shr_x_total.operation = 'ADD'
    tree.links.new(extend.outputs[0], shr_x_total.inputs[0])
    tree.links.new(brow_spread.outputs['Value'], shr_x_total.inputs[1])

    # Left hand: neg_extend - spread (outward = -X)
    shl_x_total = add_node(tree, 'ShaderNodeMath', x_sw + 600, 830,
                           "ShL X-Spr")
    shl_x_total.operation = 'SUBTRACT'
    tree.links.new(neg_extend.outputs[0], shl_x_total.inputs[0])
    tree.links.new(brow_spread.outputs['Value'], shl_x_total.inputs[1])

    # Re-wire shoulder delta X to include brow spread
    tree.links.new(shr_x_total.outputs['Value'], shr_delta.inputs['X'])
    tree.links.new(shl_x_total.outputs['Value'], shl_delta.inputs['X'])

    # --- Mouth lateral → torso lateral shift ---
    # mouthRight pushes torso +X, mouthLeft pushes -X
    mouth_lat = add_node(tree, 'ShaderNodeMath', x_sw, 550, "Mouth Lat")
    mouth_lat.operation = 'SUBTRACT'
    tree.links.new(group_in.outputs['mouthRight'], mouth_lat.inputs[0])
    tree.links.new(group_in.outputs['mouthLeft'], mouth_lat.inputs[1])

    mouth_lat_chest = add_node(tree, 'ShaderNodeMath', x_sw + 200, 550,
                               "MLat Chest")
    mouth_lat_chest.operation = 'MULTIPLY'
    tree.links.new(mouth_lat.outputs['Value'], mouth_lat_chest.inputs[0])
    mouth_lat_chest.inputs[1].default_value = 0.3

    mouth_lat_pelvis = add_node(tree, 'ShaderNodeMath', x_sw + 200, 490,
                                "MLat Pelvis")
    mouth_lat_pelvis.operation = 'MULTIPLY'
    tree.links.new(mouth_lat.outputs['Value'],
                   mouth_lat_pelvis.inputs[0])
    mouth_lat_pelvis.inputs[1].default_value = 0.2  # less than chest

    # --- Chest sway: lateral (lean + mouth) + vertical (dip + bob + lift) ---
    chest_sway_x = add_node(tree, 'ShaderNodeMath', x_sw, 400,
                            "Chest SwX")
    chest_sway_x.operation = 'MULTIPLY'
    tree.links.new(lean.outputs['Value'], chest_sway_x.inputs[0])
    chest_sway_x.inputs[1].default_value = 1.0

    chest_x_total = add_node(tree, 'ShaderNodeMath', x_sw + 400, 400,
                             "Chest X+Mouth")
    chest_x_total.operation = 'ADD'
    tree.links.new(chest_sway_x.outputs['Value'],
                   chest_x_total.inputs[0])
    tree.links.new(mouth_lat_chest.outputs['Value'],
                   chest_x_total.inputs[1])

    chest_dip_z = add_node(tree, 'ShaderNodeMath', x_sw, 340,
                           "Chest DipZ")
    chest_dip_z.operation = 'MULTIPLY'
    tree.links.new(extend.outputs['Value'], chest_dip_z.inputs[0])
    chest_dip_z.inputs[1].default_value = -0.2

    chest_z_bob = add_node(tree, 'ShaderNodeMath', x_sw + 200, 340,
                           "Chest +Bob")
    chest_z_bob.operation = 'ADD'
    tree.links.new(chest_dip_z.outputs['Value'], chest_z_bob.inputs[0])
    tree.links.new(bob_chest.outputs['Value'], chest_z_bob.inputs[1])

    chest_z_total = add_node(tree, 'ShaderNodeMath', x_sw + 400, 340,
                             "Chest +Lift")
    chest_z_total.operation = 'ADD'
    tree.links.new(chest_z_bob.outputs['Value'],
                   chest_z_total.inputs[0])
    tree.links.new(z_lift.outputs['Value'], chest_z_total.inputs[1])

    # Forward/back sway from head tilt (extend = headRotX) + twist
    chest_sway_y_base = add_node(tree, 'ShaderNodeMath', x_sw, 370,
                                 "Chest SwY")
    chest_sway_y_base.operation = 'MULTIPLY'
    tree.links.new(extend.outputs['Value'], chest_sway_y_base.inputs[0])
    chest_sway_y_base.inputs[1].default_value = 0.5

    # headRotZ twist adds Y sway (chest twists forward)
    chest_sway_y = add_node(tree, 'ShaderNodeMath', x_sw + 200, 370,
                            "Chest Y+Twist")
    chest_sway_y.operation = 'ADD'
    tree.links.new(chest_sway_y_base.outputs['Value'],
                   chest_sway_y.inputs[0])
    tree.links.new(torso_twist.outputs['Value'], chest_sway_y.inputs[1])

    chest_sway_vec = add_node(tree, 'ShaderNodeCombineXYZ', x_sw + 600,
                              400, "Chest Sway")
    tree.links.new(chest_x_total.outputs['Value'],
                   chest_sway_vec.inputs['X'])
    tree.links.new(chest_sway_y.outputs['Value'],
                   chest_sway_vec.inputs['Y'])
    tree.links.new(chest_z_total.outputs['Value'],
                   chest_sway_vec.inputs['Z'])

    # --- Pelvis sway: damped (heavier pendulum) ---
    pelvis_sway_x = add_node(tree, 'ShaderNodeMath', x_sw, 200,
                             "Pelvis SwX")
    pelvis_sway_x.operation = 'MULTIPLY'
    tree.links.new(lean.outputs['Value'], pelvis_sway_x.inputs[0])
    pelvis_sway_x.inputs[1].default_value = 0.7

    pelvis_x_total = add_node(tree, 'ShaderNodeMath', x_sw + 400, 200,
                              "Pelvis X+Mouth")
    pelvis_x_total.operation = 'ADD'
    tree.links.new(pelvis_sway_x.outputs['Value'],
                   pelvis_x_total.inputs[0])
    tree.links.new(mouth_lat_pelvis.outputs['Value'],
                   pelvis_x_total.inputs[1])

    pelvis_dip_z = add_node(tree, 'ShaderNodeMath', x_sw, 140,
                            "Pelvis DipZ")
    pelvis_dip_z.operation = 'MULTIPLY'
    tree.links.new(extend.outputs['Value'], pelvis_dip_z.inputs[0])
    pelvis_dip_z.inputs[1].default_value = -0.12

    pelvis_z_bob = add_node(tree, 'ShaderNodeMath', x_sw + 200, 140,
                            "Pelvis +Bob")
    pelvis_z_bob.operation = 'ADD'
    tree.links.new(pelvis_dip_z.outputs['Value'],
                   pelvis_z_bob.inputs[0])
    tree.links.new(bob_pelvis.outputs['Value'], pelvis_z_bob.inputs[1])

    # Pelvis gets 70% of combined lift (heavier, less responsive)
    pelvis_lift = add_node(tree, 'ShaderNodeMath', x_sw + 400, 260,
                           "Pelvis Lift*0.7")
    pelvis_lift.operation = 'MULTIPLY'
    tree.links.new(z_lift.outputs['Value'], pelvis_lift.inputs[0])
    pelvis_lift.inputs[1].default_value = 0.7

    pelvis_z_total = add_node(tree, 'ShaderNodeMath', x_sw + 400, 140,
                              "Pelvis +Lift")
    pelvis_z_total.operation = 'ADD'
    tree.links.new(pelvis_z_bob.outputs['Value'],
                   pelvis_z_total.inputs[0])
    tree.links.new(pelvis_lift.outputs['Value'],
                   pelvis_z_total.inputs[1])

    pelvis_sway_y_base = add_node(tree, 'ShaderNodeMath', x_sw, 170,
                                   "Pelvis SwY")
    pelvis_sway_y_base.operation = 'MULTIPLY'
    tree.links.new(extend.outputs['Value'], pelvis_sway_y_base.inputs[0])
    pelvis_sway_y_base.inputs[1].default_value = 0.35

    # Pelvis gets 60% of twist (heavier, less responsive)
    pelvis_twist = add_node(tree, 'ShaderNodeMath', x_sw, 130,
                            "Pelvis Twist")
    pelvis_twist.operation = 'MULTIPLY'
    tree.links.new(torso_twist.outputs['Value'], pelvis_twist.inputs[0])
    pelvis_twist.inputs[1].default_value = 0.6

    pelvis_sway_y = add_node(tree, 'ShaderNodeMath', x_sw + 200, 170,
                             "Pelvis Y+Twist")
    pelvis_sway_y.operation = 'ADD'
    tree.links.new(pelvis_sway_y_base.outputs['Value'],
                   pelvis_sway_y.inputs[0])
    tree.links.new(pelvis_twist.outputs['Value'], pelvis_sway_y.inputs[1])

    pelvis_sway_vec = add_node(tree, 'ShaderNodeCombineXYZ', x_sw + 600,
                               200, "Pelvis Sway")
    tree.links.new(pelvis_x_total.outputs['Value'],
                   pelvis_sway_vec.inputs['X'])
    tree.links.new(pelvis_sway_y.outputs['Value'],
                   pelvis_sway_vec.inputs['Y'])
    tree.links.new(pelvis_z_total.outputs['Value'],
                   pelvis_sway_vec.inputs['Z'])

    # --- Head lift vector (blob head + head position follow torso) ---
    head_lift = add_node(tree, 'ShaderNodeCombineXYZ', x_sw + 600, 700,
                         "Head Lift")
    tree.links.new(chest_x_total.outputs['Value'],
                   head_lift.inputs['X'])
    tree.links.new(chest_sway_y.outputs['Value'],
                   head_lift.inputs['Y'])
    tree.links.new(chest_z_total.outputs['Value'],
                   head_lift.inputs['Z'])

    # --- Mute face-heuristic sway when body tracking is active ---
    # face_factor (1 - BT) created in Section 2.5.
    # Same factor mutes both endpoint deltas AND torso sway.

    chest_sway_muted = add_node(tree, 'ShaderNodeVectorMath', x_sw + 700,
                                400, "Chest Sway×Face")
    chest_sway_muted.operation = 'SCALE'
    tree.links.new(chest_sway_vec.outputs['Vector'],
                   chest_sway_muted.inputs[0])
    tree.links.new(face_factor.outputs['Value'],
                   chest_sway_muted.inputs['Scale'])

    pelvis_sway_muted = add_node(tree, 'ShaderNodeVectorMath', x_sw + 700,
                                 200, "Pelvis Sway×Face")
    pelvis_sway_muted.operation = 'SCALE'
    tree.links.new(pelvis_sway_vec.outputs['Vector'],
                   pelvis_sway_muted.inputs[0])
    tree.links.new(face_factor.outputs['Value'],
                   pelvis_sway_muted.inputs['Scale'])

    head_lift_muted = add_node(tree, 'ShaderNodeVectorMath', x_sw + 700,
                               700, "Head Lift×Face")
    head_lift_muted.operation = 'SCALE'
    tree.links.new(head_lift.outputs['Vector'],
                   head_lift_muted.inputs[0])
    tree.links.new(face_factor.outputs['Value'],
                   head_lift_muted.inputs['Scale'])

    # --- Torso positions (chest, pelvis, waist) ---
    # Chest position = body_center + CHEST_OFFSET + sway (muted by BT)
    chest_off = add_node(tree, 'ShaderNodeCombineXYZ', x_sw + 800, 400,
                         "Chest Off")
    chest_off.inputs['X'].default_value = CHEST_OFFSET.x
    chest_off.inputs['Y'].default_value = CHEST_OFFSET.y
    chest_off.inputs['Z'].default_value = CHEST_OFFSET.z
    chest_base = add_node(tree, 'ShaderNodeVectorMath', x_sw + 1000, 400,
                          "Chest Base")
    chest_base.operation = 'ADD'
    tree.links.new(body_ctr.outputs['Vector'], chest_base.inputs[0])
    tree.links.new(chest_off.outputs['Vector'], chest_base.inputs[1])

    chest_pos = add_node(tree, 'ShaderNodeVectorMath', x_sw + 1200, 400,
                         "Chest Pos")
    chest_pos.operation = 'ADD'
    tree.links.new(chest_base.outputs['Vector'], chest_pos.inputs[0])
    tree.links.new(chest_sway_muted.outputs['Vector'],
                   chest_pos.inputs[1])

    # Pelvis position = body_center + PELVIS_OFFSET + sway (muted by BT)
    pelvis_off = add_node(tree, 'ShaderNodeCombineXYZ', x_sw + 800, 200,
                          "Pelvis Off")
    pelvis_off.inputs['X'].default_value = PELVIS_OFFSET.x
    pelvis_off.inputs['Y'].default_value = PELVIS_OFFSET.y
    pelvis_off.inputs['Z'].default_value = PELVIS_OFFSET.z
    pelvis_base = add_node(tree, 'ShaderNodeVectorMath', x_sw + 1000, 200,
                           "Pelvis Base")
    pelvis_base.operation = 'ADD'
    tree.links.new(body_ctr.outputs['Vector'], pelvis_base.inputs[0])
    tree.links.new(pelvis_off.outputs['Vector'], pelvis_base.inputs[1])

    pelvis_pos = add_node(tree, 'ShaderNodeVectorMath', x_sw + 1200, 200,
                          "Pelvis Pos")
    pelvis_pos.operation = 'ADD'
    tree.links.new(pelvis_base.outputs['Vector'], pelvis_pos.inputs[0])
    tree.links.new(pelvis_sway_muted.outputs['Vector'],
                   pelvis_pos.inputs[1])

    # Waist joint (dynamic midpoint)
    waist_pos = add_node(tree, 'ShaderNodeVectorMath', x_sw + 1200, 0,
                         "Waist Pos")
    waist_pos.operation = 'ADD'
    tree.links.new(chest_pos.outputs['Vector'], waist_pos.inputs[0])
    tree.links.new(pelvis_pos.outputs['Vector'], waist_pos.inputs[1])

    waist_mid = add_node(tree, 'ShaderNodeVectorMath', x_sw + 1400, 0,
                         "Waist Mid")
    waist_mid.operation = 'SCALE'
    tree.links.new(waist_pos.outputs['Vector'], waist_mid.inputs[0])
    waist_mid.inputs['Scale'].default_value = 0.5

    # --- Update blob head to follow body sway (muted by BT) ---
    if blob_tf is not None:
        dynamic_head = add_node(tree, 'ShaderNodeVectorMath', -2300, 600,
                                "Head Dyn")
        dynamic_head.operation = 'ADD'
        tree.links.new(head_pos_fixed.outputs['Vector'],
                       dynamic_head.inputs[0])
        tree.links.new(head_lift_muted.outputs['Vector'],
                       dynamic_head.inputs[1])
        # Overwrites static link (Blender replaces old link on same input)
        tree.links.new(dynamic_head.outputs['Vector'],
                       blob_tf.inputs['Translation'])

    _frame_section(tree,
        "THE STRINGS — Torso sway (lean + mouth), walking bob,"
        " eyebrow/jaw lift, head follows chest",
        'strings', _new_nodes(tree, _s))
    _s = _snap_nodes(tree)

    # ------------------------------------------------------------------
    # SECTION 3.5 — Attachment points (visual + physics split)
    # ------------------------------------------------------------------
    # Visual bases: local offset from chest/pelvis (stay on body).
    # Physics attachments: visual + contralateral delta (invisible
    # "string anchors" that drive the hands via Verlet constraint).
    # This separation means head tilt moves the HANDS, not the shoulders.
    x_att = -1300

    def _joint_from_torso(name, torso_node, local_offset, delta_out,
                          y_pos):
        """Create visual base + physics attachment from torso position.

        Visual = torso + local offset (stays on the body).
        Attach = visual + delta (drives physics).
        delta_out: an output socket (Vector) — can be from a node or lerp.
        """
        loc = add_node(tree, 'ShaderNodeCombineXYZ', x_att, y_pos,
                       f"{name} Loc")
        loc.inputs['X'].default_value = local_offset[0]
        loc.inputs['Y'].default_value = local_offset[1]
        loc.inputs['Z'].default_value = local_offset[2]

        visual = add_node(tree, 'ShaderNodeVectorMath', x_att + 200,
                          y_pos, f"{name} Vis")
        visual.operation = 'ADD'
        tree.links.new(torso_node.outputs['Vector'], visual.inputs[0])
        tree.links.new(loc.outputs['Vector'], visual.inputs[1])

        attach = add_node(tree, 'ShaderNodeVectorMath', x_att + 400,
                          y_pos, f"{name} Att")
        attach.operation = 'ADD'
        tree.links.new(visual.outputs['Vector'], attach.inputs[0])
        tree.links.new(delta_out, attach.inputs[1])

        return visual, attach

    # Local offsets: joint position relative to its parent torso part
    shl_local = (SHOULDER_L_OFFSET.x - CHEST_OFFSET.x,
                 SHOULDER_L_OFFSET.y - CHEST_OFFSET.y,
                 SHOULDER_L_OFFSET.z - CHEST_OFFSET.z)
    shr_local = (SHOULDER_R_OFFSET.x - CHEST_OFFSET.x,
                 SHOULDER_R_OFFSET.y - CHEST_OFFSET.y,
                 SHOULDER_R_OFFSET.z - CHEST_OFFSET.z)
    hipl_local = (HIP_L_OFFSET.x - PELVIS_OFFSET.x,
                  HIP_L_OFFSET.y - PELVIS_OFFSET.y,
                  HIP_L_OFFSET.z - PELVIS_OFFSET.z)
    hipr_local = (HIP_R_OFFSET.x - PELVIS_OFFSET.x,
                  HIP_R_OFFSET.y - PELVIS_OFFSET.y,
                  HIP_R_OFFSET.z - PELVIS_OFFSET.z)

    shl_visual, shl_attach = _joint_from_torso(
        "ShL", chest_pos, shl_local, shl_delta_final, -450)
    shr_visual, shr_attach = _joint_from_torso(
        "ShR", chest_pos, shr_local, shr_delta_final, -600)

    # --- Shoulder tilt from head rotation ---
    # When you tilt your head, shoulders naturally follow. headRotY
    # (roll/tilt) offsets shoulder Z positions in opposite directions.
    # Future: replace with actual tracked shoulder positions from MP.
    sh_tilt = add_node(tree, 'ShaderNodeMath', x_att + 600, -450,
                        "Sh Tilt")
    sh_tilt.operation = 'MULTIPLY'
    tree.links.new(group_in.outputs['headRotY'], sh_tilt.inputs[0])
    sh_tilt.inputs[1].default_value = -0.15

    # --- Shoulder yaw swing from head rotation (Y-axis depth) ---
    # Marionette spreader-bar principle: when the head yaws, the bar
    # rotates about its vertical axis — one string pulls forward while
    # the other slackens back. headRotZ drives opposite Y offsets on
    # L vs R shoulders. Lives at the attachment layer (same as sh_tilt)
    # so it applies regardless of Body Tracking mute state.
    yaw_swing = add_node(tree, 'ShaderNodeMath', x_att + 600, -380,
                         "Sh Yaw")
    yaw_swing.operation = 'MULTIPLY'
    tree.links.new(group_in.outputs['headRotZ'], yaw_swing.inputs[0])
    yaw_swing.inputs[1].default_value = 0.4

    neg_yaw = add_node(tree, 'ShaderNodeMath', x_att + 600, -330,
                       "Neg Yaw")
    neg_yaw.operation = 'MULTIPLY'
    neg_yaw.inputs[1].default_value = -1.0
    tree.links.new(yaw_swing.outputs[0], neg_yaw.inputs[0])

    # Left shoulder: Z += tilt, Y += yaw
    shl_tilt_vec = add_node(tree, 'ShaderNodeCombineXYZ',
                             x_att + 600, -500, "ShL TiltV")
    tree.links.new(sh_tilt.outputs['Value'], shl_tilt_vec.inputs['Z'])
    tree.links.new(yaw_swing.outputs[0], shl_tilt_vec.inputs['Y'])

    shl_vis_tilted = add_node(tree, 'ShaderNodeVectorMath',
                               x_att + 800, -450, "ShL VTilt")
    shl_vis_tilted.operation = 'ADD'
    tree.links.new(shl_visual.outputs['Vector'],
                   shl_vis_tilted.inputs[0])
    tree.links.new(shl_tilt_vec.outputs['Vector'],
                   shl_vis_tilted.inputs[1])

    shl_att_tilted = add_node(tree, 'ShaderNodeVectorMath',
                               x_att + 800, -500, "ShL ATilt")
    shl_att_tilted.operation = 'ADD'
    tree.links.new(shl_attach.outputs['Vector'],
                   shl_att_tilted.inputs[0])
    tree.links.new(shl_tilt_vec.outputs['Vector'],
                   shl_att_tilted.inputs[1])

    # Right shoulder: Z -= tilt (opposite direction)
    neg_tilt = add_node(tree, 'ShaderNodeMath', x_att + 600, -650,
                         "Neg Tilt")
    neg_tilt.operation = 'MULTIPLY'
    neg_tilt.inputs[1].default_value = -1.0
    tree.links.new(sh_tilt.outputs['Value'], neg_tilt.inputs[0])

    shr_tilt_vec = add_node(tree, 'ShaderNodeCombineXYZ',
                             x_att + 600, -700, "ShR TiltV")
    tree.links.new(neg_tilt.outputs['Value'], shr_tilt_vec.inputs['Z'])
    tree.links.new(neg_yaw.outputs[0], shr_tilt_vec.inputs['Y'])

    shr_vis_tilted = add_node(tree, 'ShaderNodeVectorMath',
                               x_att + 800, -600, "ShR VTilt")
    shr_vis_tilted.operation = 'ADD'
    tree.links.new(shr_visual.outputs['Vector'],
                   shr_vis_tilted.inputs[0])
    tree.links.new(shr_tilt_vec.outputs['Vector'],
                   shr_vis_tilted.inputs[1])

    shr_att_tilted = add_node(tree, 'ShaderNodeVectorMath',
                               x_att + 800, -700, "ShR ATilt")
    shr_att_tilted.operation = 'ADD'
    tree.links.new(shr_attach.outputs['Vector'],
                   shr_att_tilted.inputs[0])
    tree.links.new(shr_tilt_vec.outputs['Vector'],
                   shr_att_tilted.inputs[1])

    # Reassign — all downstream code uses tilted versions
    shl_visual = shl_vis_tilted
    shl_attach = shl_att_tilted
    shr_visual = shr_vis_tilted
    shr_attach = shr_att_tilted

    hipl_visual, hipl_attach = _joint_from_torso(
        "HipL", pelvis_pos, hipl_local, hipl_delta_final, -750)
    hipr_visual, hipr_attach = _joint_from_torso(
        "HipR", pelvis_pos, hipr_local, hipr_delta_final, -900)

    # Head position (includes body sway — moves with torso)
    # Z from "Head Gap" slider (same as blob head section above)
    head_off = add_node(tree, 'ShaderNodeCombineXYZ', x_att, -250,
                        "Head Off")
    head_off.inputs['X'].default_value = HEAD_OFFSET.x
    head_off.inputs['Y'].default_value = HEAD_OFFSET.y
    tree.links.new(group_in.outputs['Head Gap'],
                   head_off.inputs['Z'])
    head_base_pos = add_node(tree, 'ShaderNodeVectorMath', x_att + 200,
                             -250, "Head Base")
    head_base_pos.operation = 'ADD'
    tree.links.new(body_ctr.outputs['Vector'], head_base_pos.inputs[0])
    tree.links.new(head_off.outputs['Vector'], head_base_pos.inputs[1])
    head_pos = add_node(tree, 'ShaderNodeVectorMath', x_att + 400, -250,
                        "Head Pos")
    head_pos.operation = 'ADD'
    tree.links.new(head_base_pos.outputs['Vector'], head_pos.inputs[0])
    tree.links.new(head_lift_muted.outputs['Vector'], head_pos.inputs[1])

    _frame_section(tree,
        "ATTACHMENT POINTS — Where strings meet the body:"
        " visual joints (on torso) + physics anchors (with movement deltas)",
        'attach', _new_nodes(tree, _s))
    _s = _snap_nodes(tree)

    # ------------------------------------------------------------------
    # SECTION 4 — Rest positions (attachment + down vector)
    # ------------------------------------------------------------------
    x_rest = -1200

    neg_arm = add_node(tree, 'ShaderNodeMath', x_rest, -450, "Neg Arm")
    neg_arm.operation = 'MULTIPLY'
    neg_arm.inputs[1].default_value = -1.0
    tree.links.new(group_in.outputs['Arm Length'], neg_arm.inputs[0])

    drop_arm = add_node(tree, 'ShaderNodeCombineXYZ', x_rest + 200, -450,
                        "Drop Arm")
    drop_arm.inputs['Y'].default_value = 0.0
    tree.links.new(neg_arm.outputs['Value'], drop_arm.inputs['Z'])

    neg_leg = add_node(tree, 'ShaderNodeMath', x_rest, -750, "Neg Leg")
    neg_leg.operation = 'MULTIPLY'
    neg_leg.inputs[1].default_value = -1.0
    tree.links.new(group_in.outputs['Leg Length'], neg_leg.inputs[0])

    drop_leg = add_node(tree, 'ShaderNodeCombineXYZ', x_rest + 200, -750,
                        "Drop Leg")
    drop_leg.inputs['Y'].default_value = 0.0
    tree.links.new(neg_leg.outputs['Value'], drop_leg.inputs['Z'])

    def _make_rest(name, attach_node, drop_node, y_pos):
        r = add_node(tree, 'ShaderNodeVectorMath', x_rest + 400, y_pos,
                     f"Rest {name}")
        r.operation = 'ADD'
        tree.links.new(attach_node.outputs['Vector'], r.inputs[0])
        tree.links.new(drop_node.outputs['Vector'], r.inputs[1])
        return r

    rest_hl = _make_rest("HL", shl_visual, drop_arm, -400)
    rest_hr = _make_rest("HR", shr_visual, drop_arm, -550)
    rest_fl = _make_rest("FL", hipl_visual, drop_leg, -700)
    rest_fr = _make_rest("FR", hipr_visual, drop_leg, -850)

    _frame_section(tree,
        "REST POSE — Dead-hang positions: where limbs"
        " dangle when no input (attachment + gravity down)",
        'rest', _new_nodes(tree, _s))
    _s = _snap_nodes(tree)

    # ------------------------------------------------------------------
    # SECTION 5 — Simulation Zone
    # ------------------------------------------------------------------
    sim_in, sim_out = _create_sim_zone(tree, context)
    sim_in.location = (-600, 0)
    sim_out.location = (1400, 0)

    for name in POS_NAMES + PREV_NAMES:
        sim_out.state_items.new('VECTOR', name)
    # Floated shoulder positions — computed inside the zone, read outside
    # for visual parts (joint spheres, elbows, upper arm limbs)
    sim_out.state_items.new('VECTOR', 'floated_shl')
    sim_out.state_items.new('VECTOR', 'floated_shr')
    sim_out.state_items.new('FLOAT', 'initialized')

    tree.links.new(sim_in.outputs['Geometry'], sim_out.inputs['Geometry'])

    # NOTE: Torso momentum (V0.7.0) was removed. Smoothing the sway
    # inside the sim zone creates a circular dependency:
    #   sim_out → chest_pos → attachments → (inside zone) → sim_out
    # The zone can't evaluate because its output feeds its own input.
    # Momentum will be re-implemented at the Python/OSC level instead
    # (smoothing the raw headRot values before they reach the modifier).
    # The Momentum slider remains in the interface for future use.

    _frame_section(tree,
        "SIMULATION ZONE — Physics boundary: state persists"
        " across frames (positions, velocities, shoulder float)",
        'simzone', _new_nodes(tree, _s))
    _s = _snap_nodes(tree)

    # ------------------------------------------------------------------
    # SECTION 6 — Shared physics nodes (inside sim zone)
    # ------------------------------------------------------------------
    x_phys = -200

    dt_sq = add_node(tree, 'ShaderNodeMath', x_phys, 300, "dt^2")
    dt_sq.operation = 'MULTIPLY'
    tree.links.new(sim_in.outputs['Delta Time'], dt_sq.inputs[0])
    tree.links.new(sim_in.outputs['Delta Time'], dt_sq.inputs[1])

    neg_grav = add_node(tree, 'ShaderNodeMath', x_phys + 200, 300, "-Grav")
    neg_grav.operation = 'MULTIPLY'
    neg_grav.inputs[1].default_value = -1.0
    tree.links.new(group_in.outputs['Gravity'], neg_grav.inputs[0])

    grav_z = add_node(tree, 'ShaderNodeMath', x_phys + 400, 300, "Grav*dt2")
    grav_z.operation = 'MULTIPLY'
    tree.links.new(neg_grav.outputs['Value'], grav_z.inputs[0])
    tree.links.new(dt_sq.outputs['Value'], grav_z.inputs[1])

    grav_vec = add_node(tree, 'ShaderNodeCombineXYZ', x_phys + 600, 300,
                        "Grav Vec")
    tree.links.new(grav_z.outputs['Value'], grav_vec.inputs['Z'])

    init_cmp = add_node(tree, 'FunctionNodeCompare', x_phys, 150,
                        "Is First?")
    init_cmp.data_type = 'FLOAT'
    init_cmp.operation = 'LESS_THAN'
    tree.links.new(sim_in.outputs['initialized'], init_cmp.inputs[0])
    init_cmp.inputs[1].default_value = 0.5

    not_first = add_node(tree, 'ShaderNodeMath', x_phys + 200, 150,
                         "Not First")
    not_first.operation = 'SUBTRACT'
    not_first.inputs[0].default_value = 1.0
    tree.links.new(init_cmp.outputs['Result'], not_first.inputs[1])

    const_one = add_node(tree, 'ShaderNodeMath', x_phys + 600, 150,
                         "Init=1")
    const_one.operation = 'ADD'
    const_one.inputs[0].default_value = 1.0
    const_one.inputs[1].default_value = 0.0

    _frame_section(tree,
        "PHYSICS CORE — Shared by all limbs:"
        " gravity vector, timestep, first-frame initialization",
        'physics', _new_nodes(tree, _s))
    _s = _snap_nodes(tree)

    # ------------------------------------------------------------------
    # SECTION 6.5 — Shoulder float (uses previous-frame endpoint pos)
    # ------------------------------------------------------------------
    # Floated shoulders drift toward the hand when arm is pulled taut.
    # Uses sim_in (previous frame) positions — no circular dependency.
    x_float = -450

    floated_shl = _apply_shoulder_float(
        tree, x_float, -500, "ShL Flt",
        base_attach_out=shl_visual.outputs['Vector'],
        endpoint_pos_out=sim_in.outputs['pos_hand_l'],
        float_amount_out=group_in.outputs['Shoulder Float'],
        arm_length_out=group_in.outputs['Arm Length'])

    floated_shr = _apply_shoulder_float(
        tree, x_float, -700, "ShR Flt",
        base_attach_out=shr_visual.outputs['Vector'],
        endpoint_pos_out=sim_in.outputs['pos_hand_r'],
        float_amount_out=group_in.outputs['Shoulder Float'],
        arm_length_out=group_in.outputs['Arm Length'])

    # Pass floated positions through the sim zone boundary so visual
    # parts outside the zone can read them (links can't exit a zone)
    tree.links.new(floated_shl.outputs['Vector'],
                   sim_out.inputs['floated_shl'])
    tree.links.new(floated_shr.outputs['Vector'],
                   sim_out.inputs['floated_shr'])

    _frame_section(tree,
        "SHOULDER FLOAT — Jim Rose: real marionettes have 5/8\""
        " slack. Attachment drifts toward hand when arm pulls taut",
        'float', _new_nodes(tree, _s))
    _s = _snap_nodes(tree)

    # ------------------------------------------------------------------
    # SECTION 7 — Per-endpoint Verlet physics + hinge constraints
    # ------------------------------------------------------------------
    # Arms: hinge Y prevents hyperextension, inward_limit prevents
    #        reaching across body (joint stop), midline is safety net.
    # Legs: hinge -Y prevents forward kick, ground_z clamps to floor.
    ground_z = group_in.outputs['Ground Height']
    ground_fric = group_in.outputs['Ground Friction']
    endpoints = [
        ('HL', 'pos_hand_l', 'prev_hand_l', shl_attach,
         'Arm Length', rest_hl, 'Y', None,
         ('MINIMUM', INWARD_LIMIT), ('MINIMUM', -MIDLINE_MARGIN),
         ARM_BEND_BIAS, None),
        ('HR', 'pos_hand_r', 'prev_hand_r', shr_attach,
         'Arm Length', rest_hr, 'Y', None,
         ('MAXIMUM', -INWARD_LIMIT), ('MAXIMUM', MIDLINE_MARGIN),
         ARM_BEND_BIAS, None),
        ('FL', 'pos_foot_l', 'prev_foot_l', hipl_attach,
         'Leg Length', rest_fl, '-Y', ground_z,
         ('MAXIMUM', -FOOT_SPREAD_DIR), ('MINIMUM', -FOOT_MIDLINE),
         LEG_BEND_BIAS, ground_fric),
        ('FR', 'pos_foot_r', 'prev_foot_r', hipr_attach,
         'Leg Length', rest_fr, '-Y', ground_z,
         ('MINIMUM', FOOT_SPREAD_DIR), ('MAXIMUM', FOOT_MIDLINE),
         LEG_BEND_BIAS, ground_fric),
    ]

    for i, (label, pos_name, prev_name, attach, len_key, rest, hinge,
            gnd, inward, midline, bias_y,
            friction) in enumerate(endpoints):
        y_ep = -i * 800
        # Legs get forward bias hinge; arms use standard limit
        h_lim = LEG_HINGE_BIAS if hinge == '-Y' else HINGE_LIMIT
        pos_sock, prev_sock = _add_verlet_endpoint(
            tree, x_phys, y_ep, label,
            pos_out=sim_in.outputs[pos_name],
            prev_out=sim_in.outputs[prev_name],
            attach_out=attach.outputs['Vector'],
            length_out=group_in.outputs[len_key],
            grav_vec_out=grav_vec.outputs['Vector'],
            damping_out=group_in.outputs['Damping'],
            is_first_out=init_cmp.outputs['Result'],
            not_first_out=not_first.outputs['Value'],
            rest_out=rest.outputs['Vector'],
            hinge_axis=hinge,
            hinge_limit=h_lim,
            inward_limit=inward,
            ground_z_out=gnd,
            midline_clamp=midline,
            bend_bias_y=bias_y,
            ground_friction_out=friction,
        )
        tree.links.new(pos_sock, sim_out.inputs[pos_name])
        tree.links.new(prev_sock, sim_out.inputs[prev_name])

    tree.links.new(const_one.outputs['Value'],
                   sim_out.inputs['initialized'])

    _frame_section(tree,
        "VERLET PHYSICS — Per-limb: velocity + gravity + distance"
        " constraint + joint hinges + ground collision + friction",
        'verlet', _new_nodes(tree, _s))
    _s = _snap_nodes(tree)

    # ------------------------------------------------------------------
    # SECTIONS 8 + 9 — Visual body parts + skeleton (curves, IK, neck)
    # ------------------------------------------------------------------
    # All capsule composition, direct hand placement, limb tubes,
    # elbow/knee IK, neck, and spine live in marionette/body_parts.py.
    # That module owns its own framing for both "THE PUPPET'S BODY" and
    # "THE SKELETON" frames; the returned dict feeds Studio Track
    # overrides (Section 10) and Assembly (Section 11).
    body = build_body_parts(
        tree, group_in, sim_out, body_mats,
        chest_pos, pelvis_pos, waist_mid,
        hipl_visual, hipr_visual,
        shl_visual, shr_visual,
        arm_l_factor, arm_r_factor,
        snap_state=_s,
    )
    parts_geo = body['parts_geo']
    _idx_chest = body['_idx_chest']
    _idx_pelvis = body['_idx_pelvis']
    _idx_hand_l = body['_idx_hand_l']
    _idx_hand_r = body['_idx_hand_r']
    _idx_foot_l = body['_idx_foot_l']
    _idx_foot_r = body['_idx_foot_r']
    hand_l_pos = body['hand_l_pos']
    hand_r_pos = body['hand_r_pos']
    x_part = body['x_part']
    x_limb = body['x_limb']
    _s = body['snap_state']

    # ------------------------------------------------------------------
    # SECTION 10 — Studio Track: Custom body part overrides
    # When a student assigns a custom object, it replaces the capsule.
    # Uses Object Info to read geometry, Switch to select default/custom.
    # ------------------------------------------------------------------
    x_cust = 3000

    def _custom_object_switch(label, obj_socket_name, pos_socket,
                              capsule_idx, y_row, mirror_x=False,
                              rot_socket=None, scale_socket=None):
        """Replace a capsule with custom object geometry if assigned.

        Creates Object Info → face count check → Switch → Transform.
        If the object has faces (student assigned something), use it.
        Otherwise keep the default capsule.

        `rot_socket` and `scale_socket` are optional Vector sockets.
        When wired, the custom mesh picks up the same rotation/scale
        the default capsule receives (e.g. chest lean, hips counter-
        twist). Left unwired, the Transform stays at zero rotation +
        unit scale so today's behavior is unchanged.
        """
        obj_info = add_node(tree, 'GeometryNodeObjectInfo',
                            x_cust, y_row, f"Custom {label}")
        obj_info.transform_space = 'RELATIVE'
        tree.links.new(group_in.outputs[obj_socket_name],
                       obj_info.inputs['Object'])

        # Check face count — if > 0, student assigned a mesh
        domain_sz = add_node(tree, 'GeometryNodeAttributeDomainSize',
                             x_cust + 200, y_row,
                             f"Custom {label} Size")
        tree.links.new(obj_info.outputs['Geometry'],
                       domain_sz.inputs['Geometry'])

        has_custom = add_node(tree, 'FunctionNodeCompare',
                              x_cust + 400, y_row,
                              f"Custom {label} ?")
        has_custom.data_type = 'INT'
        has_custom.operation = 'GREATER_THAN'
        tree.links.new(domain_sz.outputs['Face Count'],
                       has_custom.inputs[2])
        has_custom.inputs[3].default_value = 0

        # Transform custom geo to body part position
        cust_tf = add_node(tree, 'GeometryNodeTransform',
                           x_cust + 400, y_row - 100,
                           f"Custom {label} TF")
        tree.links.new(obj_info.outputs['Geometry'],
                       cust_tf.inputs['Geometry'])
        tree.links.new(pos_socket, cust_tf.inputs['Translation'])
        if rot_socket is not None:
            tree.links.new(rot_socket, cust_tf.inputs['Rotation'])
        if mirror_x:
            cust_tf.inputs['Scale'].default_value = (-1.0, 1.0, 1.0)
        elif scale_socket is not None:
            tree.links.new(scale_socket, cust_tf.inputs['Scale'])

        # Shade smooth
        cust_sm = add_node(tree, 'GeometryNodeSetShadeSmooth',
                           x_cust + 600, y_row - 100,
                           f"Custom {label} Sm")
        tree.links.new(cust_tf.outputs['Geometry'],
                       cust_sm.inputs['Geometry'])

        # Switch: custom or default capsule
        switch = add_node(tree, 'GeometryNodeSwitch',
                          x_cust + 800, y_row,
                          f"Custom {label} Switch")
        switch.input_type = 'GEOMETRY'
        tree.links.new(has_custom.outputs['Result'],
                       switch.inputs['Switch'])
        # False = default capsule (index 0), True = custom (index 1)
        tree.links.new(parts_geo[capsule_idx],
                       switch.inputs[False])
        tree.links.new(cust_sm.outputs['Geometry'],
                       switch.inputs[True])

        # Replace the capsule entry with the switch output
        parts_geo[capsule_idx] = switch.outputs['Output']

    # --- Dampened head rotation for chest + hips custom slots ---
    # Jim Rose waist-cord in motion: head pulls chest, chest pulls
    # hips, each with progressively less twist. A fresh CombineXYZ
    # is built here (rather than reusing head_rot_vec from the blob
    # section) so this block stays scope-safe even when no blob head
    # is loaded. Bare Minkowski capsules are sphere-ish and rotation-
    # invariant, so only the custom-object Transform consumes these.
    head_rot_cust = add_node(tree, 'ShaderNodeCombineXYZ',
                             x_cust - 400, 300, "Studio Head Rot")
    tree.links.new(group_in.outputs['headRotX'],
                   head_rot_cust.inputs['X'])
    tree.links.new(group_in.outputs['headRotY'],
                   head_rot_cust.inputs['Y'])
    tree.links.new(group_in.outputs['headRotZ'],
                   head_rot_cust.inputs['Z'])

    chest_rot_damp = add_node(tree, 'ShaderNodeVectorMath',
                              x_cust - 200, 200, "Chest Rot x0.5")
    chest_rot_damp.operation = 'SCALE'
    tree.links.new(head_rot_cust.outputs['Vector'],
                   chest_rot_damp.inputs[0])
    chest_rot_damp.inputs['Scale'].default_value = 0.5

    pelvis_rot_damp = add_node(tree, 'ShaderNodeVectorMath',
                               x_cust - 200, -100, "Hips Rot x0.3")
    pelvis_rot_damp.operation = 'SCALE'
    tree.links.new(head_rot_cust.outputs['Vector'],
                   pelvis_rot_damp.inputs[0])
    pelvis_rot_damp.inputs['Scale'].default_value = 0.3

    # Custom Chest → replaces chest capsule (upper body above waist)
    _custom_object_switch("Chest", "Custom Chest",
                          chest_pos.outputs['Vector'],
                          _idx_chest, 0,
                          rot_socket=chest_rot_damp.outputs['Vector'])

    # Custom Hips → replaces pelvis capsule (lower body below waist).
    # Chest and hips are split per the Jim Rose waist-cord principle:
    # a real marionette treats upper and lower body as two masses
    # linked by a twist-limited cord, moving on independent timelines.
    _custom_object_switch("Hips", "Custom Hips",
                          pelvis_pos.outputs['Vector'],
                          _idx_pelvis, -300,
                          rot_socket=pelvis_rot_damp.outputs['Vector'])

    # Custom Hand → replaces both hand capsules (R is mirrored)
    _custom_object_switch("Hand L", "Custom Hand",
                          hand_l_pos,
                          _idx_hand_l, -600)
    _custom_object_switch("Hand R", "Custom Hand",
                          hand_r_pos,
                          _idx_hand_r, -900, mirror_x=True)

    # Custom Foot → replaces both foot capsules (R is mirrored)
    _custom_object_switch("Foot L", "Custom Foot",
                          sim_out.outputs['pos_foot_l'],
                          _idx_foot_l, -1200)
    _custom_object_switch("Foot R", "Custom Foot",
                          sim_out.outputs['pos_foot_r'],
                          _idx_foot_r, -1500, mirror_x=True)

    _frame_section(tree,
        "STUDIO TRACK — Custom body part overrides (Object Info"
        " nodes). Assign student meshes to replace default capsules.",
        'output', _new_nodes(tree, _s))
    _s = _snap_nodes(tree)

    # ------------------------------------------------------------------
    # SECTION 11 — Join blob head + body → output
    # ------------------------------------------------------------------
    join = add_node(tree, 'GeometryNodeJoinGeometry', 3400, -1000,
                    "Join All")

    # Add blob head first (drawn on top)
    if blob_geo_out:
        tree.links.new(blob_geo_out, join.inputs['Geometry'])

    # (Cheek capsules are joined with blob head before blob_tf —
    #  they're already inside blob_geo_out)

    # Add body parts
    for geo_socket in parts_geo:
        tree.links.new(geo_socket, join.inputs['Geometry'])

    tree.links.new(join.outputs['Geometry'], group_out.inputs['Geometry'])

    _frame_section(tree,
        "FINAL ASSEMBLY — Join blob head + all body"
        " parts into single output geometry",
        'output', _new_nodes(tree, _s))


# ===================================================================
# OPERATORS
# ===================================================================

class PPPARTY_OT_create_marionette(bpy.types.Operator):
    """Create a face-tracked marionette — blob head on a physics body"""

    bl_idname = "ppparty.create_marionette"
    bl_label = "Create Marionette"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        # --- Clean up previous puppet ---
        cleanup_names = [
            "PP_Control_L", "PP_Control_R",  # V0.1.x empties
            "PP_Hand_L", "PP_Hand_R", "PP_Foot_L", "PP_Foot_R",
            "PP_Marionette", "PP_Armature",
            # Studio Track placeholder objects
            "PP_Placeholder_Torso",  # legacy — swept up on rebuild
            "PP_Placeholder_Chest", "PP_Placeholder_Hips",
            "PP_Placeholder_Hand", "PP_Placeholder_Foot",
        ]
        for name in cleanup_names:
            obj = bpy.data.objects.get(name)
            if obj:
                bpy.data.objects.remove(obj, do_unlink=True)

        # Clean old materials
        for mat_name in ("PP_Body", "PP_Head", "PP_Hand", "PP_Foot",
                         "PP_Joint", "PP_Limb", "PP_Cheek",
                         "PP_HeadSkin", "PP_Mouth", "PP_EyeWhite",
                         "PP_Iris", "PP_Pupil", "PP_Ear", "PP_Brow",
                         "PP_Lip", "PP_Nose"):
            mat = bpy.data.materials.get(mat_name)
            if mat:
                bpy.data.materials.remove(mat)

        for ng_name in ("PPParty_Marionette", "GN_BlobPuppet",
                        "PP_DynCapsule", "PP_TwoBoneIK",
                        "PP_ShoulderFloat"):
            ng = bpy.data.node_groups.get(ng_name)
            if ng:
                bpy.data.node_groups.remove(ng)

        # --- Create materials ---
        body_mats = create_body_materials()
        blob_mats = create_blob_head_materials()

        # --- Create armature (receives phone head rotation) ---
        armature = create_armature(context)

        # --- Create puppet mesh + GN modifier ---
        # Modifier must exist BEFORE build_marionette_tree() runs because
        # _create_sim_zone() invokes bpy.ops.node.add_simulation_zone(),
        # whose poll() requires the tree to be visibly edited — which in
        # Blender 5.2 means tied to an active object's GN modifier.
        mesh = bpy.data.meshes.new("PP_Marionette")
        puppet = bpy.data.objects.new("PP_Marionette", mesh)
        context.collection.objects.link(puppet)
        context.view_layer.objects.active = puppet

        mod = puppet.modifiers.new("PPParty_Physics", 'NODES')
        tree = bpy.data.node_groups.new("PPParty_Marionette",
                                        'GeometryNodeTree')
        mod.node_group = tree

        # Build the full GN tree (blob head + physics body)
        build_marionette_tree(tree, body_mats, blob_mats, context)

        # --- Studio Track: create placeholder objects for Object Info ---
        # Simple UV spheres available in the Object dropdown. Chest/Hips/Foot
        # are also AUTO-ASSIGNED to their Custom* sockets so the Studio Track
        # pipeline is pre-wired on Create Marionette — David doesn't have to
        # load test meshes every session. Hand placeholder is created but NOT
        # auto-assigned (Custom Hand socket is hidden for V1.0.0 per hands.py
        # phase). Student swaps placeholders for real meshes via the Object
        # dropdown on the modifier.
        _placeholders = {
            'PP_Placeholder_Chest': (12, 8, 0.2),
            'PP_Placeholder_Hips':  (12, 8, 0.17),
            'PP_Placeholder_Hand':  (8, 6, 0.1),
            'PP_Placeholder_Foot':  (8, 6, 0.12),
        }
        _placeholder_socket_map = {
            'PP_Placeholder_Chest': 'Custom Chest',
            'PP_Placeholder_Hips':  'Custom Hips',
            'PP_Placeholder_Foot':  'Custom Foot',
            # PP_Placeholder_Hand intentionally omitted — Custom Hand
            # socket is hidden until hand tracking lands in Phase 2.
        }
        _placeholder_objs = {}
        import bmesh
        for obj_name, (segs, rings, radius) in _placeholders.items():
            ph_mesh = bpy.data.meshes.new(obj_name)
            ph_obj = bpy.data.objects.new(obj_name, ph_mesh)
            context.collection.objects.link(ph_obj)

            bm = bmesh.new()
            bmesh.ops.create_uvsphere(bm, u_segments=segs,
                                      v_segments=rings, radius=radius)
            bm.to_mesh(ph_mesh)
            bm.free()

            ph_obj.hide_viewport = True
            ph_obj.hide_render = True
            ph_obj.hide_select = True
            _placeholder_objs[obj_name] = ph_obj

        # Set interface default_value as a best-effort hint — Blender 5.2
        # does NOT reliably propagate this to an already-wired modifier
        # instance. Both `mod[identifier] = obj` (id-property TypeError)
        # and `mod.node_group = tree` (scrambles panel parents) failed in
        # alpha.18 / alpha.19. Student picks the PP_Placeholder_* object
        # from the Custom Chest / Hips / Foot dropdowns manually — the
        # placeholders exist in the scene collection so they appear at
        # the top of the Object picker.
        for item in tree.interface.items_tree:
            if (hasattr(item, 'item_type') and item.item_type == 'SOCKET'
                    and item.in_out == 'INPUT'
                    and item.socket_type == 'NodeSocketObject'):
                for ph_name, sock_name in _placeholder_socket_map.items():
                    if item.name == sock_name and ph_name in _placeholder_objs:
                        try:
                            item.default_value = _placeholder_objs[ph_name]
                        except Exception:
                            pass

        # --- Set default materials on modifier sockets ---
        # Materials are instance-level values (mod[id] = mat) — this API
        # works for Material sockets even though it fails for Object sockets.
        _mat_defaults = {
            # Head materials (passthrough from blob template)
            'Head Material': blob_mats.get('body'),
            'Mouth Material': blob_mats.get('mouth'),
            'Eye Material': blob_mats.get('eye_white'),
            'Iris Material': blob_mats.get('iris'),
            'Pupil Material': blob_mats.get('pupil'),
            'Ear Material': blob_mats.get('ear'),
            'Eyebrow Material': blob_mats.get('brow'),
            'Lip Material': blob_mats.get('lip'),
            'Nose Material': blob_mats.get('nose'),
            # Body part materials
            'Body Part Material': body_mats.get('body'),
            'Hand Material': body_mats.get('hand'),
            'Foot Material': body_mats.get('foot'),
            'Joint Material': body_mats.get('joint'),
            'Limb Material': body_mats.get('limb'),
            'Cheek Material': body_mats.get('cheek'),
        }
        for item in tree.interface.items_tree:
            if (hasattr(item, 'item_type') and item.item_type == 'SOCKET'
                    and item.in_out == 'INPUT'
                    and item.socket_type == 'NodeSocketMaterial'
                    and item.name in _mat_defaults):
                mat = _mat_defaults[item.name]
                if mat:
                    try:
                        mod[item.identifier] = mat
                    except Exception:
                        pass

        puppet.update_tag()

        # Ensure dummy mesh exists (OSC receiver writes shape keys here,
        # then pushes values directly to modifier — no drivers needed)
        from ..core.osc_receiver import ensure_dummy_mesh
        ensure_dummy_mesh()

        # Clear receiver's cached puppet ref so it re-discovers the new one
        from .. import receiver
        receiver._cached_puppet_mod = None
        receiver._face_socket_ids = None
        receiver._rot_socket_ids = None

        # --- Scene setup ---
        settings = context.scene.ppparty
        settings.pp_active_puppet = "PP_Marionette"

        context.view_layer.objects.active = puppet
        puppet.select_set(True)
        context.scene.render.engine = 'BLENDER_EEVEE'

        # Match scene fps to the MediaPipe sender (30) — a 24 ↔ 30 mismatch
        # shows up as sub-frame jitter. Push the timeline end far out so
        # playback doesn't loop back to frame 1 and re-initialize the
        # simulation zone mid-performance (sim reset reads as a noise spike).
        context.scene.render.fps = 30
        context.scene.frame_end = 24000

        ph_count = len(_placeholder_objs)
        ph_names = ", ".join(sorted(_placeholder_objs.keys()))
        self.report({'INFO'},
                    f"Puppet created ({ph_count} placeholders: {ph_names})")
        return {'FINISHED'}


class PPPARTY_OT_reset_physics(bpy.types.Operator):
    """Reset marionette by jumping to frame 1 (re-initializes sim zone)"""

    bl_idname = "ppparty.reset_physics"
    bl_label = "Reset Physics"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        context.scene.frame_set(context.scene.frame_start)
        self.report({'INFO'}, "Physics reset.")
        return {'FINISHED'}
