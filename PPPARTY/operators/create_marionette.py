# SPDX-License-Identifier: GPL-3.0-or-later
"""PPParty — Create Marionette V0.9.4: Material slots for all parts.

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

import os

import bpy
from mathutils import Vector


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
CHEST_OFFSET = Vector((0.0, 0.0, 0.07))
PELVIS_OFFSET = Vector((0.0, 0.0, -0.22))
CHEST_RADIUS = 0.2
PELVIS_RADIUS = 0.17
WAIST_JOINT_RADIUS = 0.05
WAIST_TUBE_RADIUS = 0.04

HAND_RADIUS = 0.1
FOOT_RADIUS = 0.12
JOINT_RADIUS = 0.06
LIMB_TUBE_RADIUS = 0.03
BLOB_HEAD_SCALE = 0.6  # Blob head scaled to sit on marionette body

# Joint constraints (Jim Rose marionette research)
SHOULDER_FLOAT_SLACK = 0.08    # max drift distance (digital 5/8" slack)
SHOULDER_FLOAT_ENGAGE = 0.5    # fraction of arm length before float engages
ELBOW_JOINT_RADIUS = 0.05
KNEE_JOINT_RADIUS = 0.06
FOOT_SPLAY_ANGLE = 0.262       # 15 degrees in radians
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

# Face tracking inputs — names matching both GN_BlobPuppet interface
# and the dummy mesh shape keys. If a name isn't on the blob head,
# the socket still exists (driver writes to it) but nothing reads it.
FACE_INPUTS = [
    'jawOpen', 'mouthSmileRight', 'mouthFunnel', 'mouthPucker',
    'mouthFrownLeft', 'mouthFrownRight', 'mouthLeft', 'mouthRight',
    'mouthClose', 'eyeBlinkLeft', 'eyeBlinkRight',
    'eyeWideLeft', 'eyeWideRight', 'eyeLookInLeft', 'eyeLookInRight',
]

# Path to blob head asset
ADDON_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS_DIR = os.path.join(ADDON_DIR, "assets")
BLOB_HEAD_BLEND = os.path.join(ASSETS_DIR, "blob_puppet.blend")

# Blob head inputs to SKIP when passing through customization
# (face tracking is wired separately)
_BLOB_SKIP = set(FACE_INPUTS)

# Rename blob "Body X" → "Head X" to avoid collision with marionette body
_BLOB_RENAME = {
    'Body Width': 'Head Width',
    'Body Height': 'Head Height',
    'Body Rotation': 'Head Tilt',
    'Body Material': 'Head Material',
}
_BLOB_UNRENAME = {v: k for k, v in _BLOB_RENAME.items()}


# ===================================================================
# HELPERS
# ===================================================================

def add_node(tree, node_type, x, y, label=None):
    """Add a node to the tree at position (x, y) with optional label."""
    node = tree.nodes.new(node_type)
    node.location = (x, y)
    if label:
        node.label = label
    return node


def make_material(name, color):
    """Create a simple solid-color Principled BSDF material."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = 0.8
    return mat


def add_dynamic_capsule(tree, x, y, label, radius=0.5, subdivs=6,
                        width_output=None, ext_factor=0.3, axis='Z'):
    """Add a dynamic Minkowski capsule driven by a Width slider.

    Ported from Green Room blob puppet. Subdivided cube → clamp to inner
    box → offset → normalize × radius → add to clamped position.
    Width=0 → sphere. Width>0 → pill shape along the specified axis.

    Returns the Set Position node (geometry output = capsule mesh).
    """
    diam = 2.0 * radius

    if width_output is None:
        cube = add_node(tree, 'GeometryNodeMeshCube', x, y, f"{label} Cube")
        cube.inputs['Size'].default_value = (diam, diam, diam)
        cube.inputs['Vertices X'].default_value = subdivs
        cube.inputs['Vertices Y'].default_value = subdivs
        cube.inputs['Vertices Z'].default_value = subdivs

        pos_in = add_node(tree, 'GeometryNodeInputPosition', x + 150,
                          y - 50, f"{label} Pos")
        norm = add_node(tree, 'ShaderNodeVectorMath', x + 300, y - 50,
                        f"{label} Norm")
        norm.operation = 'NORMALIZE'
        tree.links.new(pos_in.outputs['Position'], norm.inputs[0])

        scaled = add_node(tree, 'ShaderNodeVectorMath', x + 450, y - 50,
                          f"{label} Rnd")
        scaled.operation = 'SCALE'
        scaled.inputs['Scale'].default_value = radius
        tree.links.new(norm.outputs['Vector'], scaled.inputs[0])

        set_pos = add_node(tree, 'GeometryNodeSetPosition', x + 600, y,
                           f"{label} RndPos")
        tree.links.new(cube.outputs['Mesh'], set_pos.inputs['Geometry'])
        tree.links.new(scaled.outputs['Vector'],
                       set_pos.inputs['Position'])
        return set_pos

    # --- Dynamic capsule: Width slider drives extension along axis ---
    ext = add_node(tree, 'ShaderNodeMath', x - 300, y - 80,
                   f"{label} W→Ext")
    ext.operation = 'MULTIPLY'
    ext.inputs[1].default_value = ext_factor
    tree.links.new(width_output, ext.inputs[0])

    ext_x2 = add_node(tree, 'ShaderNodeMath', x - 300, y - 160,
                       f"{label} Ext×2")
    ext_x2.operation = 'MULTIPLY'
    ext_x2.inputs[1].default_value = 2.0
    tree.links.new(ext.outputs[0], ext_x2.inputs[0])

    axis_size = add_node(tree, 'ShaderNodeMath', x - 150, y - 160,
                         f"{label} AxSz")
    axis_size.operation = 'ADD'
    axis_size.inputs[1].default_value = diam
    tree.links.new(ext_x2.outputs[0], axis_size.inputs[0])

    cube_size = add_node(tree, 'ShaderNodeCombineXYZ', x - 50, y - 80,
                         f"{label} CubeSz")
    cube_size.inputs['X'].default_value = diam
    cube_size.inputs['Y'].default_value = diam
    cube_size.inputs['Z'].default_value = diam
    tree.links.new(axis_size.outputs[0], cube_size.inputs[axis])

    cube = add_node(tree, 'GeometryNodeMeshCube', x, y, f"{label} Cube")
    cube.inputs['Vertices X'].default_value = subdivs
    cube.inputs['Vertices Y'].default_value = subdivs
    cube.inputs['Vertices Z'].default_value = subdivs
    tree.links.new(cube_size.outputs['Vector'], cube.inputs['Size'])

    pos_in = add_node(tree, 'GeometryNodeInputPosition', x + 100, y - 60,
                      f"{label} Pos")

    clamp_hi_v = add_node(tree, 'ShaderNodeCombineXYZ', x + 100, y - 130,
                          f"{label} +Ext")
    clamp_hi_v.inputs['X'].default_value = 0.0
    clamp_hi_v.inputs['Y'].default_value = 0.0
    clamp_hi_v.inputs['Z'].default_value = 0.0
    tree.links.new(ext.outputs[0], clamp_hi_v.inputs[axis])

    ext_neg = add_node(tree, 'ShaderNodeMath', x + 100, y - 200,
                       f"{label} NegExt")
    ext_neg.operation = 'MULTIPLY'
    ext_neg.inputs[1].default_value = -1.0
    tree.links.new(ext.outputs[0], ext_neg.inputs[0])

    clamp_lo_v = add_node(tree, 'ShaderNodeCombineXYZ', x + 250, y - 200,
                          f"{label} -Ext")
    clamp_lo_v.inputs['X'].default_value = 0.0
    clamp_lo_v.inputs['Y'].default_value = 0.0
    clamp_lo_v.inputs['Z'].default_value = 0.0
    tree.links.new(ext_neg.outputs[0], clamp_lo_v.inputs[axis])

    clamp_hi = add_node(tree, 'ShaderNodeVectorMath', x + 400, y - 60,
                        f"{label} ClHi")
    clamp_hi.operation = 'MINIMUM'
    tree.links.new(pos_in.outputs['Position'], clamp_hi.inputs[0])
    tree.links.new(clamp_hi_v.outputs['Vector'], clamp_hi.inputs[1])

    clamp_lo = add_node(tree, 'ShaderNodeVectorMath', x + 550, y - 60,
                        f"{label} ClLo")
    clamp_lo.operation = 'MAXIMUM'
    tree.links.new(clamp_hi.outputs['Vector'], clamp_lo.inputs[0])
    tree.links.new(clamp_lo_v.outputs['Vector'], clamp_lo.inputs[1])

    offset = add_node(tree, 'ShaderNodeVectorMath', x + 700, y - 60,
                      f"{label} Offs")
    offset.operation = 'SUBTRACT'
    tree.links.new(pos_in.outputs['Position'], offset.inputs[0])
    tree.links.new(clamp_lo.outputs['Vector'], offset.inputs[1])

    norm = add_node(tree, 'ShaderNodeVectorMath', x + 850, y - 60,
                    f"{label} Norm")
    norm.operation = 'NORMALIZE'
    tree.links.new(offset.outputs['Vector'], norm.inputs[0])

    cap = add_node(tree, 'ShaderNodeVectorMath', x + 1000, y - 60,
                   f"{label} ×R")
    cap.operation = 'SCALE'
    cap.inputs['Scale'].default_value = radius
    tree.links.new(norm.outputs['Vector'], cap.inputs[0])

    final = add_node(tree, 'ShaderNodeVectorMath', x + 1150, y - 60,
                     f"{label} Final")
    final.operation = 'ADD'
    tree.links.new(clamp_lo.outputs['Vector'], final.inputs[0])
    tree.links.new(cap.outputs['Vector'], final.inputs[1])

    set_pos = add_node(tree, 'GeometryNodeSetPosition', x + 1300, y,
                       f"{label} Cap")
    tree.links.new(cube.outputs['Mesh'], set_pos.inputs['Geometry'])
    tree.links.new(final.outputs['Vector'], set_pos.inputs['Position'])

    return set_pos


def create_body_materials():
    """Create materials for the marionette body parts."""
    return {
        'body': make_material("PP_Body", (0.85, 0.55, 0.35, 1.0)),
        'hand': make_material("PP_Hand", (0.95, 0.75, 0.55, 1.0)),
        'foot': make_material("PP_Foot", (0.6, 0.4, 0.25, 1.0)),
        'joint': make_material("PP_Joint", (0.5, 0.5, 0.5, 1.0)),
        'limb': make_material("PP_Limb", (0.25, 0.25, 0.25, 1.0)),
    }


def create_blob_head_materials():
    """Create materials for the blob head (matches Green Room defaults)."""
    return {
        'body': make_material("PP_HeadSkin", (1.0, 0.78, 0.65, 1.0)),
        'mouth': make_material("PP_Mouth", (0.25, 0.12, 0.08, 1.0)),
        'eye_white': make_material("PP_EyeWhite", (1.0, 1.0, 1.0, 1.0)),
        'iris': make_material("PP_Iris", (0.2, 0.65, 0.7, 1.0)),
        'pupil': make_material("PP_Pupil", (0.05, 0.05, 0.05, 1.0)),
        'ear': make_material("PP_Ear", (1.0, 0.7, 0.55, 1.0)),
        'brow': make_material("PP_Brow", (0.18, 0.09, 0.05, 1.0)),
        'lip': make_material("PP_Lip", (0.85, 0.45, 0.45, 1.0)),
        'nose': make_material("PP_Nose", (1.0, 0.72, 0.58, 1.0)),
    }


# ===================================================================
# BLOB HEAD — load from .blend as a reusable node group
# ===================================================================

def _load_blob_head_tree():
    """Load the GN_BlobPuppet node group from blob_puppet.blend.

    Returns the node group, or None if loading fails.
    The blob head is loaded as an independent copy (not linked),
    so PPParty is fully self-contained.
    """
    # Already loaded from a previous run?
    existing = bpy.data.node_groups.get("GN_BlobPuppet")
    if existing:
        return existing

    if not os.path.exists(BLOB_HEAD_BLEND):
        print(f"PPParty: blob head not found at {BLOB_HEAD_BLEND}")
        return None

    with bpy.data.libraries.load(BLOB_HEAD_BLEND) as (data_from, data_to):
        if "GN_BlobPuppet" in data_from.node_groups:
            data_to.node_groups = ["GN_BlobPuppet"]

    return bpy.data.node_groups.get("GN_BlobPuppet")


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
    """Compute a floated shoulder attachment that drifts toward the hand.

    Uses the PREVIOUS frame's endpoint position (from sim_in) — no
    circular dependency. The attachment drifts up to `float_amount`
    toward the hand when the arm is stretched past an engage threshold.

    Returns the floated attachment position socket.
    """
    dx = 200

    # drift_vec = endpoint - base_attachment
    drift = add_node(tree, 'ShaderNodeVectorMath', x, y, f"{label} Drft")
    drift.operation = 'SUBTRACT'
    tree.links.new(endpoint_pos_out, drift.inputs[0])
    tree.links.new(base_attach_out, drift.inputs[1])

    # drift_dist = length(drift_vec)
    dist = add_node(tree, 'ShaderNodeVectorMath', x + dx, y, f"{label} Dist")
    dist.operation = 'LENGTH'
    tree.links.new(drift.outputs['Vector'], dist.inputs[0])

    # drift_dir = normalize(drift_vec)
    d_dir = add_node(tree, 'ShaderNodeVectorMath', x + dx, y - 120,
                     f"{label} Dir")
    d_dir.operation = 'NORMALIZE'
    tree.links.new(drift.outputs['Vector'], d_dir.inputs[0])

    # engage_dist = arm_length * SHOULDER_FLOAT_ENGAGE
    engage = add_node(tree, 'ShaderNodeMath', x + dx * 2, y, f"{label} Eng")
    engage.operation = 'MULTIPLY'
    tree.links.new(arm_length_out, engage.inputs[0])
    engage.inputs[1].default_value = SHOULDER_FLOAT_ENGAGE

    # excess = max(drift_dist - engage_dist, 0)
    excess = add_node(tree, 'ShaderNodeMath', x + dx * 3, y, f"{label} Exc")
    excess.operation = 'SUBTRACT'
    tree.links.new(dist.outputs['Value'], excess.inputs[0])
    tree.links.new(engage.outputs['Value'], excess.inputs[1])

    exc_clamp = add_node(tree, 'ShaderNodeMath', x + dx * 4, y,
                         f"{label} Exc+")
    exc_clamp.operation = 'MAXIMUM'
    tree.links.new(excess.outputs['Value'], exc_clamp.inputs[0])
    exc_clamp.inputs[1].default_value = 0.0

    # clamped_drift = min(excess, float_amount)
    drift_clamp = add_node(tree, 'ShaderNodeMath', x + dx * 5, y,
                           f"{label} DClp")
    drift_clamp.operation = 'MINIMUM'
    tree.links.new(exc_clamp.outputs['Value'], drift_clamp.inputs[0])
    tree.links.new(float_amount_out, drift_clamp.inputs[1])

    # floated = base_attachment + drift_dir * clamped_drift
    drift_sc = add_node(tree, 'ShaderNodeVectorMath', x + dx * 5, y - 120,
                        f"{label} DSc")
    drift_sc.operation = 'SCALE'
    tree.links.new(d_dir.outputs['Vector'], drift_sc.inputs[0])
    tree.links.new(drift_clamp.outputs['Value'], drift_sc.inputs['Scale'])

    floated = add_node(tree, 'ShaderNodeVectorMath', x + dx * 6, y - 60,
                       f"{label} Float")
    floated.operation = 'ADD'
    tree.links.new(base_attach_out, floated.inputs[0])
    tree.links.new(drift_sc.outputs['Vector'], floated.inputs[1])

    return floated


# ===================================================================
# ANALYTICAL MID-JOINTS — two-bone IK solve for elbows/knees
# ===================================================================

def _compute_mid_joint(tree, x, y, label,
                       start_socket, end_socket,
                       upper_ratio_out, total_length_out,
                       bend_axis):
    """Compute elbow/knee position analytically from shoulder→hand vector.

    Uses the law of cosines to find the intersection of two spheres
    (upper limb length from start, lower limb length from end).
    The bend_axis tuple picks which side the joint bends toward:
    (0, -1, 0) for elbows (bend backward), (0, 1, 0) for knees (forward).

    Returns the mid-joint position socket.
    """
    dx = 200

    # upper_len = total_length * upper_ratio
    upper = add_node(tree, 'ShaderNodeMath', x, y, f"{label} ULen")
    upper.operation = 'MULTIPLY'
    tree.links.new(total_length_out, upper.inputs[0])
    tree.links.new(upper_ratio_out, upper.inputs[1])

    # lower_len = total_length - upper_len
    lower = add_node(tree, 'ShaderNodeMath', x, y - 100, f"{label} LLen")
    lower.operation = 'SUBTRACT'
    tree.links.new(total_length_out, lower.inputs[0])
    tree.links.new(upper.outputs['Value'], lower.inputs[1])

    # AB = end - start
    ab = add_node(tree, 'ShaderNodeVectorMath', x + dx, y, f"{label} AB")
    ab.operation = 'SUBTRACT'
    tree.links.new(end_socket, ab.inputs[0])
    tree.links.new(start_socket, ab.inputs[1])

    # d = length(AB)
    d_len = add_node(tree, 'ShaderNodeVectorMath', x + dx * 2, y,
                     f"{label} |AB|")
    d_len.operation = 'LENGTH'
    tree.links.new(ab.outputs['Vector'], d_len.inputs[0])

    # ab_dir = normalize(AB)
    ab_dir = add_node(tree, 'ShaderNodeVectorMath', x + dx * 2, y - 100,
                      f"{label} ABd")
    ab_dir.operation = 'NORMALIZE'
    tree.links.new(ab.outputs['Vector'], ab_dir.inputs[0])

    # cos_a = (upper^2 + d^2 - lower^2) / (2 * upper * d)
    u2 = add_node(tree, 'ShaderNodeMath', x + dx * 3, y + 80, f"{label} u2")
    u2.operation = 'MULTIPLY'
    tree.links.new(upper.outputs['Value'], u2.inputs[0])
    tree.links.new(upper.outputs['Value'], u2.inputs[1])

    d2 = add_node(tree, 'ShaderNodeMath', x + dx * 3, y, f"{label} d2")
    d2.operation = 'MULTIPLY'
    tree.links.new(d_len.outputs['Value'], d2.inputs[0])
    tree.links.new(d_len.outputs['Value'], d2.inputs[1])

    l2 = add_node(tree, 'ShaderNodeMath', x + dx * 3, y - 80, f"{label} l2")
    l2.operation = 'MULTIPLY'
    tree.links.new(lower.outputs['Value'], l2.inputs[0])
    tree.links.new(lower.outputs['Value'], l2.inputs[1])

    u2_d2 = add_node(tree, 'ShaderNodeMath', x + dx * 4, y + 40,
                     f"{label} u2+d2")
    u2_d2.operation = 'ADD'
    tree.links.new(u2.outputs['Value'], u2_d2.inputs[0])
    tree.links.new(d2.outputs['Value'], u2_d2.inputs[1])

    numer = add_node(tree, 'ShaderNodeMath', x + dx * 4, y - 40,
                     f"{label} Num")
    numer.operation = 'SUBTRACT'
    tree.links.new(u2_d2.outputs['Value'], numer.inputs[0])
    tree.links.new(l2.outputs['Value'], numer.inputs[1])

    two_u = add_node(tree, 'ShaderNodeMath', x + dx * 4, y - 120,
                     f"{label} 2u")
    two_u.operation = 'MULTIPLY'
    two_u.inputs[0].default_value = 2.0
    tree.links.new(upper.outputs['Value'], two_u.inputs[1])

    two_ud = add_node(tree, 'ShaderNodeMath', x + dx * 5, y - 120,
                      f"{label} 2ud")
    two_ud.operation = 'MULTIPLY'
    tree.links.new(two_u.outputs['Value'], two_ud.inputs[0])
    tree.links.new(d_len.outputs['Value'], two_ud.inputs[1])

    # Prevent division by zero: max(denominator, 0.001)
    denom_safe = add_node(tree, 'ShaderNodeMath', x + dx * 5, y - 200,
                          f"{label} Den")
    denom_safe.operation = 'MAXIMUM'
    tree.links.new(two_ud.outputs['Value'], denom_safe.inputs[0])
    denom_safe.inputs[1].default_value = 0.001

    cos_a = add_node(tree, 'ShaderNodeMath', x + dx * 5, y - 40,
                     f"{label} CosA")
    cos_a.operation = 'DIVIDE'
    tree.links.new(numer.outputs['Value'], cos_a.inputs[0])
    tree.links.new(denom_safe.outputs['Value'], cos_a.inputs[1])

    # Clamp cos_a to [-1, 1]
    ca_min = add_node(tree, 'ShaderNodeMath', x + dx * 6, y - 40,
                      f"{label} Ca<1")
    ca_min.operation = 'MINIMUM'
    tree.links.new(cos_a.outputs['Value'], ca_min.inputs[0])
    ca_min.inputs[1].default_value = 1.0

    ca_clamp = add_node(tree, 'ShaderNodeMath', x + dx * 6, y - 120,
                        f"{label} Ca>-1")
    ca_clamp.operation = 'MAXIMUM'
    tree.links.new(ca_min.outputs['Value'], ca_clamp.inputs[0])
    ca_clamp.inputs[1].default_value = -1.0

    # proj = upper * cos_a (distance along AB)
    proj = add_node(tree, 'ShaderNodeMath', x + dx * 7, y, f"{label} Proj")
    proj.operation = 'MULTIPLY'
    tree.links.new(upper.outputs['Value'], proj.inputs[0])
    tree.links.new(ca_clamp.outputs['Value'], proj.inputs[1])

    # h = sqrt(max(upper^2 - proj^2, 0)) (height off AB line)
    p2 = add_node(tree, 'ShaderNodeMath', x + dx * 7, y - 80, f"{label} p2")
    p2.operation = 'MULTIPLY'
    tree.links.new(proj.outputs['Value'], p2.inputs[0])
    tree.links.new(proj.outputs['Value'], p2.inputs[1])

    h2 = add_node(tree, 'ShaderNodeMath', x + dx * 7, y - 160, f"{label} h2")
    h2.operation = 'SUBTRACT'
    tree.links.new(u2.outputs['Value'], h2.inputs[0])
    tree.links.new(p2.outputs['Value'], h2.inputs[1])

    h2_safe = add_node(tree, 'ShaderNodeMath', x + dx * 8, y - 160,
                       f"{label} h2+")
    h2_safe.operation = 'MAXIMUM'
    tree.links.new(h2.outputs['Value'], h2_safe.inputs[0])
    h2_safe.inputs[1].default_value = 0.0

    h = add_node(tree, 'ShaderNodeMath', x + dx * 8, y - 80, f"{label} h")
    h.operation = 'SQRT'
    tree.links.new(h2_safe.outputs['Value'], h.inputs[0])

    # along = start + ab_dir * proj
    along_sc = add_node(tree, 'ShaderNodeVectorMath', x + dx * 8, y,
                        f"{label} Alng")
    along_sc.operation = 'SCALE'
    tree.links.new(ab_dir.outputs['Vector'], along_sc.inputs[0])
    tree.links.new(proj.outputs['Value'], along_sc.inputs['Scale'])

    along = add_node(tree, 'ShaderNodeVectorMath', x + dx * 9, y,
                     f"{label} AlP")
    along.operation = 'ADD'
    tree.links.new(start_socket, along.inputs[0])
    tree.links.new(along_sc.outputs['Vector'], along.inputs[1])

    # Bend direction: cross(ab_dir, bend_axis) → side, cross(side, ab_dir) → bend
    # Small epsilon in bend_axis prevents degenerate cross when limb is vertical
    bend_ax = add_node(tree, 'ShaderNodeCombineXYZ', x + dx * 7, y - 260,
                       f"{label} BAx")
    bend_ax.inputs['X'].default_value = bend_axis[0] + 0.001
    bend_ax.inputs['Y'].default_value = bend_axis[1]
    bend_ax.inputs['Z'].default_value = bend_axis[2]

    side = add_node(tree, 'ShaderNodeVectorMath', x + dx * 8, y - 260,
                    f"{label} Side")
    side.operation = 'CROSS_PRODUCT'
    tree.links.new(ab_dir.outputs['Vector'], side.inputs[0])
    tree.links.new(bend_ax.outputs['Vector'], side.inputs[1])

    bend = add_node(tree, 'ShaderNodeVectorMath', x + dx * 9, y - 260,
                    f"{label} Bend")
    bend.operation = 'CROSS_PRODUCT'
    tree.links.new(ab_dir.outputs['Vector'], bend.inputs[0])
    tree.links.new(side.outputs['Vector'], bend.inputs[1])

    bend_n = add_node(tree, 'ShaderNodeVectorMath', x + dx * 9, y - 160,
                      f"{label} BNrm")
    bend_n.operation = 'NORMALIZE'
    tree.links.new(bend.outputs['Vector'], bend_n.inputs[0])

    # perp = bend_normalized * h
    perp = add_node(tree, 'ShaderNodeVectorMath', x + dx * 10, y - 120,
                    f"{label} Perp")
    perp.operation = 'SCALE'
    tree.links.new(bend_n.outputs['Vector'], perp.inputs[0])
    tree.links.new(h.outputs['Value'], perp.inputs['Scale'])

    # mid_joint = along + perp
    mid = add_node(tree, 'ShaderNodeVectorMath', x + dx * 10, y,
                   f"{label} Mid")
    mid.operation = 'ADD'
    tree.links.new(along.outputs['Vector'], mid.inputs[0])
    tree.links.new(perp.outputs['Vector'], mid.inputs[1])

    return mid


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
    blob_tree = _load_blob_head_tree()
    blob_custom = []   # list of (pp_name, blob_name, socket_type, default, min, max, subtype, panel)
    if blob_tree:
        for item in blob_tree.interface.items_tree:
            if not (hasattr(item, 'item_type') and item.item_type == 'SOCKET'
                    and item.in_out == 'INPUT'):
                continue
            if item.name in _BLOB_SKIP:
                continue
            if item.socket_type not in ('NodeSocketFloat',
                                         'NodeSocketMaterial'):
                continue
            pp_name = _BLOB_RENAME.get(item.name, item.name)
            panel = item.parent.name if item.parent else 'Other'
            if panel == 'Body':
                panel = 'Head Shape'
            blob_custom.append((
                pp_name, item.name, item.socket_type,
                getattr(item, 'default_value', None),
                getattr(item, 'min_value', 0.0),
                getattr(item, 'max_value', 1.0),
                getattr(item, 'subtype', 'NONE'),
                panel,
            ))

    # ------------------------------------------------------------------
    # INTERFACE — all modifier-level inputs
    # ------------------------------------------------------------------

    # Face tracking (driven by dummy mesh shape keys)
    ft_panel = tree.interface.new_panel("Face Tracking")
    for name in FACE_INPUTS:
        s = tree.interface.new_socket(
            name, in_out='INPUT', socket_type='NodeSocketFloat',
            parent=ft_panel)
        s.default_value = 0.0
        s.min_value = 0.0
        s.max_value = 1.0
        s.subtype = 'FACTOR'

    # Head rotation (driven by armature head bone)
    rot_panel = tree.interface.new_panel("Head Rotation")
    for rname in ('headRotX', 'headRotY', 'headRotZ'):
        s = tree.interface.new_socket(
            rname, in_out='INPUT', socket_type='NodeSocketFloat',
            parent=rot_panel)
        s.default_value = 0.0
        s.min_value = -3.14159
        s.max_value = 3.14159

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
    s.default_value = -1.0
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

    # ------------------------------------------------------------------
    # HEAD CUSTOMIZATION — passthrough from blob head template
    # Auto-creates sockets matching the blob's customization interface.
    # ------------------------------------------------------------------
    head_panels = {}
    for pp_name, blob_name, sock_type, default, mn, mx, subtype, panel in blob_custom:
        if panel not in head_panels:
            head_panels[panel] = tree.interface.new_panel(panel)
        s = tree.interface.new_socket(
            pp_name, in_out='INPUT', socket_type=sock_type,
            parent=head_panels[panel])
        if sock_type == 'NodeSocketFloat':
            s.default_value = default
            s.min_value = mn
            s.max_value = mx
            if subtype and subtype != 'NONE':
                s.subtype = subtype

    # Geometry output
    tree.interface.new_socket(
        "Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry')

    # ------------------------------------------------------------------
    # GROUP INPUT / OUTPUT
    # ------------------------------------------------------------------
    group_in = add_node(tree, 'NodeGroupInput', -3600, 0, "Input")
    group_out = add_node(tree, 'NodeGroupOutput', 3600, -1000, "Output")

    # ------------------------------------------------------------------
    # SECTION 1 — Blob Head Group node + face tracking + customization
    # ------------------------------------------------------------------
    # blob_tree was loaded earlier (before interface) to read its sockets.
    blob_geo_out = None
    blob_tf = None
    head_pos_fixed = None

    if blob_tree:
        blob_group = add_node(tree, 'GeometryNodeGroup', -3000, 600,
                              "Blob Head")
        blob_group.node_tree = blob_tree

        # Wire face tracking inputs: main tree → blob head Group node
        blob_input_names = set()
        for inp in blob_group.inputs:
            blob_input_names.add(inp.name)

        for name in FACE_INPUTS:
            if name in blob_input_names:
                try:
                    tree.links.new(group_in.outputs[name],
                                   blob_group.inputs[name])
                except KeyError:
                    pass

        # Wire head customization passthrough: PPParty slider/material → blob
        for pp_name, blob_name, sock_type, *_ in blob_custom:
            if blob_name in blob_input_names:
                try:
                    tree.links.new(group_in.outputs[pp_name],
                                   blob_group.inputs[blob_name])
                except KeyError:
                    pass

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

        head_pos_fixed = add_node(tree, 'ShaderNodeCombineXYZ', -2600, 600,
                                  "Head Pos")
        head_pos_fixed.inputs['X'].default_value = (BODY_CENTER.x
                                                     + HEAD_OFFSET.x)
        head_pos_fixed.inputs['Y'].default_value = (BODY_CENTER.y
                                                     + HEAD_OFFSET.y)
        head_pos_fixed.inputs['Z'].default_value = (BODY_CENTER.z
                                                     + HEAD_OFFSET.z)

        blob_tf = add_node(tree, 'GeometryNodeTransform', -2400, 600,
                           "Head TF")
        tree.links.new(blob_group.outputs['Geometry'],
                       blob_tf.inputs['Geometry'])
        tree.links.new(head_pos_fixed.outputs['Vector'],
                       blob_tf.inputs['Translation'])
        tree.links.new(head_rot_vec.outputs['Vector'],
                       blob_tf.inputs['Rotation'])
        blob_tf.inputs['Scale'].default_value = (
            BLOB_HEAD_SCALE, BLOB_HEAD_SCALE, BLOB_HEAD_SCALE)

        blob_geo_out = blob_tf.outputs['Geometry']

    # ------------------------------------------------------------------
    # SECTION 2 — Body center (fixed) + head rotation → movement
    # ------------------------------------------------------------------
    x_body = -2000

    body_ctr = add_node(tree, 'ShaderNodeCombineXYZ', x_body, 0, "Body Ctr")
    body_ctr.inputs['X'].default_value = BODY_CENTER.x
    body_ctr.inputs['Y'].default_value = BODY_CENTER.y
    body_ctr.inputs['Z'].default_value = BODY_CENTER.z

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

    # --- Torso positions (chest, pelvis, waist) ---
    # Chest position = body_center + CHEST_OFFSET + sway
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
    tree.links.new(chest_sway_vec.outputs['Vector'], chest_pos.inputs[1])

    # Pelvis position = body_center + PELVIS_OFFSET + sway
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
    tree.links.new(pelvis_sway_vec.outputs['Vector'],
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

    # --- Update blob head to follow body sway ---
    if blob_tf is not None:
        dynamic_head = add_node(tree, 'ShaderNodeVectorMath', -2300, 600,
                                "Head Dyn")
        dynamic_head.operation = 'ADD'
        tree.links.new(head_pos_fixed.outputs['Vector'],
                       dynamic_head.inputs[0])
        tree.links.new(head_lift.outputs['Vector'],
                       dynamic_head.inputs[1])
        # Overwrites static link (Blender replaces old link on same input)
        tree.links.new(dynamic_head.outputs['Vector'],
                       blob_tf.inputs['Translation'])

    # ------------------------------------------------------------------
    # SECTION 3.5 — Attachment points (visual + physics split)
    # ------------------------------------------------------------------
    # Visual bases: local offset from chest/pelvis (stay on body).
    # Physics attachments: visual + contralateral delta (invisible
    # "string anchors" that drive the hands via Verlet constraint).
    # This separation means head tilt moves the HANDS, not the shoulders.
    x_att = -1300

    def _joint_from_torso(name, torso_node, local_offset, delta_node,
                          y_pos):
        """Create visual base + physics attachment from torso position.

        Visual = torso + local offset (stays on the body).
        Attach = visual + contralateral delta (drives physics).
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
        tree.links.new(delta_node.outputs['Vector'], attach.inputs[1])

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
        "ShL", chest_pos, shl_local, shl_delta, -450)
    shr_visual, shr_attach = _joint_from_torso(
        "ShR", chest_pos, shr_local, shr_delta, -600)
    hipl_visual, hipl_attach = _joint_from_torso(
        "HipL", pelvis_pos, hipl_local, hipl_delta, -750)
    hipr_visual, hipr_attach = _joint_from_torso(
        "HipR", pelvis_pos, hipr_local, hipr_delta, -900)

    # Head position (includes body sway — moves with torso)
    head_off = add_node(tree, 'ShaderNodeCombineXYZ', x_att, -250,
                        "Head Off")
    head_off.inputs['X'].default_value = HEAD_OFFSET.x
    head_off.inputs['Y'].default_value = HEAD_OFFSET.y
    head_off.inputs['Z'].default_value = HEAD_OFFSET.z
    head_base_pos = add_node(tree, 'ShaderNodeVectorMath', x_att + 200,
                             -250, "Head Base")
    head_base_pos.operation = 'ADD'
    tree.links.new(body_ctr.outputs['Vector'], head_base_pos.inputs[0])
    tree.links.new(head_off.outputs['Vector'], head_base_pos.inputs[1])
    head_pos = add_node(tree, 'ShaderNodeVectorMath', x_att + 400, -250,
                        "Head Pos")
    head_pos.operation = 'ADD'
    tree.links.new(head_base_pos.outputs['Vector'], head_pos.inputs[0])
    tree.links.new(head_lift.outputs['Vector'], head_pos.inputs[1])

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

    def _add_capsule_part(y, label, radius, pos_socket, mat,
                          scale=(1, 1, 1), rotation=(0, 0, 0),
                          width_output=None, ext_factor=0.3, axis='Z',
                          subdivs=6, uniform_scale_out=None,
                          rotation_output=None, rot_axis='Y',
                          tilt_output=None, tilt_axis='X',
                          depth_output=None, depth_axis='Y',
                          mat_socket=None):
        """Create one body part: capsule + transform + material + smooth.

        uniform_scale_out: optional socket driving uniform XYZ scale
        rotation_output: optional socket driving rotation (degrees) on rot_axis
        tilt_output: optional SECOND rotation axis (degrees) on tilt_axis
        depth_output: optional position offset along depth_axis
        mat_socket: optional group_in socket for material assignment
                    (overrides hardcoded mat when provided)
        """
        import math

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
            # Build rotation vector: static base, override driven axes
            rot_vec = add_node(tree, 'ShaderNodeCombineXYZ',
                               x_part + 200, y - 160, f"{label} RotV")
            rot_vec.inputs['X'].default_value = rotation[0]
            rot_vec.inputs['Y'].default_value = rotation[1]
            rot_vec.inputs['Z'].default_value = rotation[2]

            if rotation_output is not None:
                rot_rad = add_node(tree, 'ShaderNodeMath',
                                   x_part + 50, y - 160, f"{label} D→R")
                rot_rad.operation = 'MULTIPLY'
                rot_rad.inputs[1].default_value = math.pi / 180.0
                tree.links.new(rotation_output, rot_rad.inputs[0])
                tree.links.new(rot_rad.outputs[0],
                               rot_vec.inputs[rot_axis])

            if tilt_output is not None:
                tilt_rad = add_node(tree, 'ShaderNodeMath',
                                    x_part + 50, y - 220, f"{label} T→R")
                tilt_rad.operation = 'MULTIPLY'
                tilt_rad.inputs[1].default_value = math.pi / 180.0
                tree.links.new(tilt_output, tilt_rad.inputs[0])
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

    def _add_sphere_part(y, label, radius, pos_socket, mat,
                         segments=12, rings=8, mat_socket=None):
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

    # --- Capsule body parts ---
    # Chest: dynamic capsule, extends along X (wider torso)
    _add_capsule_part(0, "Chest", CHEST_RADIUS,
                      chest_pos.outputs['Vector'], body_mats['body'],
                      scale=(1.1, 0.8, 1.05),
                      width_output=group_in.outputs['Body Width'],
                      ext_factor=0.15, axis='X',
                      mat_socket=group_in.outputs['Body Part Material'])

    # Pelvis: dynamic capsule, same width driver (slightly less extension)
    _add_capsule_part(-280, "Pelvis", PELVIS_RADIUS,
                      pelvis_pos.outputs['Vector'], body_mats['body'],
                      scale=(1.0, 0.85, 0.9),
                      width_output=group_in.outputs['Body Width'],
                      ext_factor=0.12, axis='X',
                      mat_socket=group_in.outputs['Body Part Material'])

    # Waist joint (small sphere)
    _add_sphere_part(-460, "Waist Jnt", WAIST_JOINT_RADIUS,
                     waist_mid.outputs['Vector'], body_mats['joint'],
                     mat_socket=group_in.outputs['Joint Material'])

    # Hands: capsules with Width + Rotation + Tilt
    _add_capsule_part(-620, "Hand L", HAND_RADIUS,
                      sim_out.outputs['pos_hand_l'], body_mats['hand'],
                      width_output=group_in.outputs['Hand Width'],
                      ext_factor=0.3, axis='Z',
                      uniform_scale_out=group_in.outputs['Hand Size'],
                      rotation_output=group_in.outputs['Hand Rotation'],
                      tilt_output=group_in.outputs['Hand Tilt'],
                      tilt_axis='X',
                      mat_socket=group_in.outputs['Hand Material'])
    _add_capsule_part(-780, "Hand R", HAND_RADIUS,
                      sim_out.outputs['pos_hand_r'], body_mats['hand'],
                      width_output=group_in.outputs['Hand Width'],
                      ext_factor=0.3, axis='Z',
                      uniform_scale_out=group_in.outputs['Hand Size'],
                      rotation_output=group_in.outputs['Hand Rotation'],
                      tilt_output=group_in.outputs['Hand Tilt'],
                      tilt_axis='X',
                      mat_socket=group_in.outputs['Hand Material'])

    # Feet: capsules with Width + Rotation + Depth (forward offset)
    _add_capsule_part(-940, "Foot L", FOOT_RADIUS,
                      sim_out.outputs['pos_foot_l'], body_mats['foot'],
                      rotation=(0, 0, FOOT_SPLAY_ANGLE),
                      width_output=group_in.outputs['Foot Width'],
                      ext_factor=0.3, axis='Y',
                      uniform_scale_out=group_in.outputs['Foot Size'],
                      rotation_output=group_in.outputs['Foot Rotation'],
                      rot_axis='X',
                      depth_output=group_in.outputs['Foot Depth'],
                      depth_axis='Y',
                      mat_socket=group_in.outputs['Foot Material'])
    _add_capsule_part(-1100, "Foot R", FOOT_RADIUS,
                      sim_out.outputs['pos_foot_r'], body_mats['foot'],
                      rotation=(0, 0, -FOOT_SPLAY_ANGLE),
                      width_output=group_in.outputs['Foot Width'],
                      ext_factor=0.3, axis='Y',
                      uniform_scale_out=group_in.outputs['Foot Size'],
                      rotation_output=group_in.outputs['Foot Rotation'],
                      rot_axis='X',
                      depth_output=group_in.outputs['Foot Depth'],
                      depth_axis='Y',
                      mat_socket=group_in.outputs['Foot Material'])

    # Shoulder joints: capsules with Width + Rotation
    _add_capsule_part(-1260, "Jnt ShL", JOINT_RADIUS,
                      sim_out.outputs['floated_shl'], body_mats['joint'],
                      width_output=group_in.outputs['Shoulder Width'],
                      ext_factor=0.3, axis='Z',
                      rotation_output=group_in.outputs['Shoulder Rotation'],
                      mat_socket=group_in.outputs['Joint Material'])
    _add_capsule_part(-1360, "Jnt ShR", JOINT_RADIUS,
                      sim_out.outputs['floated_shr'], body_mats['joint'],
                      width_output=group_in.outputs['Shoulder Width'],
                      ext_factor=0.3, axis='Z',
                      rotation_output=group_in.outputs['Shoulder Rotation'],
                      mat_socket=group_in.outputs['Joint Material'])

    # Hip joints (small spheres — stay spherical)
    _add_sphere_part(-1460, "Jnt HipL", JOINT_RADIUS,
                     hipl_visual.outputs['Vector'], body_mats['joint'],
                     mat_socket=group_in.outputs['Joint Material'])
    _add_sphere_part(-1560, "Jnt HipR", JOINT_RADIUS,
                     hipr_visual.outputs['Vector'], body_mats['joint'],
                     mat_socket=group_in.outputs['Joint Material'])

    # ------------------------------------------------------------------
    # SECTION 9 — Limb curves + neck
    # ------------------------------------------------------------------
    x_limb = 2600

    profile = add_node(tree, 'GeometryNodeCurvePrimitiveCircle',
                       x_limb - 200, -1400, "Tube Profile")
    profile.mode = 'RADIUS'
    profile.inputs['Radius'].default_value = LIMB_TUBE_RADIUS
    profile.inputs['Resolution'].default_value = 8

    def _add_limb(y, label, start_socket, end_socket, mat,
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

    # --- Analytical mid-joints (two-bone IK for elbows/knees) ---
    x_mid = x_limb - 2400  # mid-joint computation nodes to the left

    elbow_l = _compute_mid_joint(
        tree, x_mid, -200, "Elbow L",
        start_socket=sim_out.outputs['floated_shl'],
        end_socket=sim_out.outputs['pos_hand_l'],
        upper_ratio_out=group_in.outputs['Upper Arm Ratio'],
        total_length_out=group_in.outputs['Arm Length'],
        bend_axis=(0, -1, 0))  # elbows bend backward

    elbow_r = _compute_mid_joint(
        tree, x_mid, -550, "Elbow R",
        start_socket=sim_out.outputs['floated_shr'],
        end_socket=sim_out.outputs['pos_hand_r'],
        upper_ratio_out=group_in.outputs['Upper Arm Ratio'],
        total_length_out=group_in.outputs['Arm Length'],
        bend_axis=(0, -1, 0))

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
    _add_limb(-100, "UArm L",
              sim_out.outputs['floated_shl'],
              elbow_l.outputs['Vector'], body_mats['limb'],
              mat_socket=group_in.outputs['Limb Material'])
    _add_limb(-170, "FArm L",
              elbow_l.outputs['Vector'],
              sim_out.outputs['pos_hand_l'], body_mats['limb'],
              mat_socket=group_in.outputs['Limb Material'])
    _add_limb(-240, "UArm R",
              sim_out.outputs['floated_shr'],
              elbow_r.outputs['Vector'], body_mats['limb'],
              mat_socket=group_in.outputs['Limb Material'])
    _add_limb(-310, "FArm R",
              elbow_r.outputs['Vector'],
              sim_out.outputs['pos_hand_r'], body_mats['limb'],
              mat_socket=group_in.outputs['Limb Material'])

    # Legs (hips → knee → foot)
    _add_limb(-410, "Thigh L",
              hipl_visual.outputs['Vector'],
              knee_l.outputs['Vector'], body_mats['limb'],
              mat_socket=group_in.outputs['Limb Material'])
    _add_limb(-480, "Shin L",
              knee_l.outputs['Vector'],
              sim_out.outputs['pos_foot_l'], body_mats['limb'],
              mat_socket=group_in.outputs['Limb Material'])
    _add_limb(-550, "Thigh R",
              hipr_visual.outputs['Vector'],
              knee_r.outputs['Vector'], body_mats['limb'],
              mat_socket=group_in.outputs['Limb Material'])
    _add_limb(-620, "Shin R",
              knee_r.outputs['Vector'],
              sim_out.outputs['pos_foot_r'], body_mats['limb'],
              mat_socket=group_in.outputs['Limb Material'])

    # Elbow/knee joint spheres
    _add_sphere_part(-1420, "Elbow L", ELBOW_JOINT_RADIUS,
                     elbow_l.outputs['Vector'], body_mats['joint'],
                     mat_socket=group_in.outputs['Joint Material'])
    _add_sphere_part(-1520, "Elbow R", ELBOW_JOINT_RADIUS,
                     elbow_r.outputs['Vector'], body_mats['joint'],
                     mat_socket=group_in.outputs['Joint Material'])
    _add_sphere_part(-1620, "Knee L", KNEE_JOINT_RADIUS,
                     knee_l.outputs['Vector'], body_mats['joint'],
                     mat_socket=group_in.outputs['Joint Material'])
    _add_sphere_part(-1720, "Knee R", KNEE_JOINT_RADIUS,
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

    _add_limb(-800, "Neck",
              neck_top.outputs['Vector'],
              neck_bot.outputs['Vector'], body_mats['body'],
              mat_socket=group_in.outputs['Body Part Material'])

    # Spine / waist connector (chest → pelvis, thicker than limbs)
    waist_profile = add_node(tree, 'GeometryNodeCurvePrimitiveCircle',
                             x_limb - 200, -1550, "Waist Profile")
    waist_profile.mode = 'RADIUS'
    waist_profile.inputs['Radius'].default_value = WAIST_TUBE_RADIUS
    waist_profile.inputs['Resolution'].default_value = 8

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

    # ------------------------------------------------------------------
    # SECTION 10 — Join blob head + body → output
    # ------------------------------------------------------------------
    join = add_node(tree, 'GeometryNodeJoinGeometry', 3400, -1000,
                    "Join All")

    # Add blob head first (drawn on top)
    if blob_geo_out:
        tree.links.new(blob_geo_out, join.inputs['Geometry'])

    # Add body parts
    for geo_socket in parts_geo:
        tree.links.new(geo_socket, join.inputs['Geometry'])

    tree.links.new(join.outputs['Geometry'], group_out.inputs['Geometry'])


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
        ]
        for name in cleanup_names:
            obj = bpy.data.objects.get(name)
            if obj:
                bpy.data.objects.remove(obj, do_unlink=True)

        # Clean old materials
        for mat_name in ("PP_Body", "PP_Head", "PP_Hand", "PP_Foot",
                         "PP_Joint", "PP_Limb",
                         "PP_HeadSkin", "PP_Mouth", "PP_EyeWhite",
                         "PP_Iris", "PP_Pupil", "PP_Ear", "PP_Brow",
                         "PP_Lip", "PP_Nose"):
            mat = bpy.data.materials.get(mat_name)
            if mat:
                bpy.data.materials.remove(mat)

        for ng_name in ("PPParty_Marionette", "GN_BlobPuppet"):
            ng = bpy.data.node_groups.get(ng_name)
            if ng:
                bpy.data.node_groups.remove(ng)

        # --- Create materials ---
        body_mats = create_body_materials()
        blob_mats = create_blob_head_materials()

        # --- Create armature (receives phone head rotation) ---
        armature = create_armature(context)

        # --- Create puppet mesh + GN modifier ---
        mesh = bpy.data.meshes.new("PP_Marionette")
        puppet = bpy.data.objects.new("PP_Marionette", mesh)
        context.collection.objects.link(puppet)

        mod = puppet.modifiers.new("PPParty_Physics", 'NODES')
        tree = bpy.data.node_groups.new("PPParty_Marionette",
                                        'GeometryNodeTree')
        mod.node_group = tree

        # Build the full GN tree (blob head + physics body)
        context.view_layer.objects.active = puppet
        build_marionette_tree(tree, body_mats, blob_mats, context)

        # Set default materials on modifier sockets (head + body)
        # The tree has Material sockets — set them to our freshly created mats.
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

        self.report({'INFO'},
                    "Marionette created! Connect your phone to control it.")
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
