# SPDX-License-Identifier: GPL-3.0-or-later
"""Physics — simulation zone, Verlet integration, joint constraints, shoulder float.

=============================================================================
Why this file exists
=============================================================================
Everything else in this addon describes a pose: where the chest sits, where
the hand should be, which shoulder to pull. This file is the one place where
TIME matters — where a puppet swings because it was swinging a moment ago,
where a foot sticks to the ground because it just hit it, where a hand drifts
away from the shoulder because the arm pulled taut. "State over time" is the
whole subject.

A traditional marionette is a physical object: strings, wood, gravity, slack.
Pull the right string and the right arm lifts — but ALSO the shoulder drifts
toward the hand because the string has a little slack in it, and the lower
arm swings a beat behind because it has mass. Those little lags and drifts
are the difference between a puppet that feels alive and a rig that just
snaps to positions.

We recreate them in Geometry Nodes with three building blocks:

    1. A SIMULATION ZONE — Blender's way of saying "anything between these
       two nodes carries state from one frame to the next." Inside the zone
       we keep the eight hand/foot positions (current + previous frame),
       two floated shoulder positions, a first-frame flag, and — added for
       hand secondary motion in Phase 2 — 32 finger-segment positions and
       16 palm-corner positions (per side, current + previous for each).

    2. VERLET INTEGRATION — a three-line physics trick that computes
       velocity from the difference between current and previous position,
       applies gravity, then projects the result onto a sphere of the right
       arm/leg length around its attachment point. No springs, no masses,
       no solver iterations — just (pos - prev) carried forward. This is
       the same math every cloth sim, every hair sim, every Roblox ragdoll
       is built on.

    3. JOINT CONSTRAINTS — clamps that say "this foot can't kick forward
       past this angle," "this hand can't cross the body's midline," "this
       hand can only fold inward so far." Each one is a two-node clamp
       applied to the direction vector between attachment and endpoint.
       Stacked, they're what keep a Verlet-driven puppet from looking like
       a pile of noodles.

The fourth piece is the SHOULDER FLOAT — Jim Rose's observation that real
marionette shoulders drift about 5/8" when the arm is pulled taut. It's
its own named sub-group (`PP_ShoulderFloat`) because it replaces about
twelve inline nodes per shoulder, and because it reads from the PREVIOUS
frame's hand position — looking backward in time is what prevents a
circular dependency inside the sim zone.

=============================================================================
The four sections this module builds, in order
=============================================================================

    SECTION 5 — THE SIMULATION ZONE
        Create the paired SimulationInput + SimulationOutput nodes. Add
        state items: four endpoint positions + four previous + two
        floated shoulders + one `initialized` flag (11 total, body-era)
        plus 48 hand-physics items declared for Phase 2 (finger chains +
        palm corners). The Phase 2 items are passthrough-wired in this
        section — they exist and carry their value forward untouched
        until steps 10/11 of the implementation plan overwrite the
        passthrough with real chain/jiggle wiring.
        Link Geometry in → out (we don't touch geometry inside the zone,
        just state). Nothing physical happens here; we're just declaring
        WHAT gets carried forward.

    SECTION 6 — PHYSICS CORE (shared by all four limbs)
        A gravity vector = `Gravity × dt²` pointing down. A first-frame
        detector (compares the `initialized` state item to 0.5). A
        constant 1.0 node that will be written back to `initialized`
        after frame 1, so "first frame?" is True exactly once.

    SECTION 6.5 — SHOULDER FLOAT
        Two instances of the PP_ShoulderFloat group, one per shoulder.
        Each reads the previous-frame hand position from `sim_in` and
        the static shoulder base. Output is the floated shoulder pos,
        which we store as a sim-zone state item so visual parts outside
        the zone can read it (links can't cross a zone boundary).

    SECTION 7 — PER-ENDPOINT VERLET + CONSTRAINTS
        Loop over the four endpoints (HL/HR/FL/FR). For each, build the
        Verlet integration + distance constraint + optional hinge +
        optional inward limit + optional ground clamp + optional midline
        clamp + optional ground friction. Feed the result back into the
        corresponding state item on sim_out.

=============================================================================
Why this all runs as one function
=============================================================================
Sections 5, 6, 6.5, and 7 share so many intermediate wires — the sim zone
input/output nodes, the gravity vector, the first-frame flag, the four
attach/rest sockets — that threading them through separate functions would
just mean passing ten references back and forth. Body_movement.py made the
same call for its three sections. Four labeled `_frame_section` calls
still give the GN editor reader four conceptual blocks.

=============================================================================
What this module exports
=============================================================================
    build_physics(tree, group_in, context, *,
                  shl_visual, shr_visual,
                  shl_attach, shr_attach, hipl_attach, hipr_attach,
                  rest_hl, rest_hr, rest_fl, rest_fr,
                  snap_state)
        Adds all four sections to `tree`. Returns a dict containing
        `sim_in`, `sim_out`, and an updated `snap_state` so the caller
        can keep threading frames through the rest of the tree.
"""


import bpy

from ._common import (
    add_node, _snap_nodes, _new_nodes, _frame_section, _vector_lerp)


# ===========================================================================
# CONSTANTS — tuning knobs for joint stops and shoulder float
# ===========================================================================
# These numbers all come out of Jim Rose's marionette research. They are
# the same numbers the code used when these helpers lived in
# create_marionette.py — moving them here does not change any math.

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

# State items for sim zone — one entry per endpoint for BOTH current and
# previous position. Verlet integration needs both to compute velocity.
POS_NAMES = ['pos_hand_l', 'pos_hand_r', 'pos_foot_l', 'pos_foot_r']
PREV_NAMES = ['prev_hand_l', 'prev_hand_r', 'prev_foot_l', 'prev_foot_r']


# ---------------------------------------------------------------------------
# Phase 2 — hand secondary motion state items (see NATIVE_PHYSICS_DESIGN.md §5)
# ---------------------------------------------------------------------------
# The hand has two kinds of secondary motion: finger chains (Verlet segments
# that lag and swing) and palm corners (single-bone jiggle springs that flop).
# Both need pos + prev state so the sim zone can compute velocity frame to
# frame, same pattern as the body's hand/foot endpoints above.
#
# Chains: 4 per side × 2 segments × 2 sides × 2 vecs = 32 items.
#   - fingerA = thumb (anchor at palm SW corner)
#   - fingerB = tracked middle finger (driven by MediaPipe landmark 8)
#   - fingerC, fingerD = untracked side fingers (chain sim only)
# Palm corners: 4 per side × 2 sides × 2 vecs = 16 items.
#   - ne, nw, se, sw = compass labels relative to the palm plate (the +Y
#     direction points toward the fingertips; NE = finger-side far from
#     thumb when palm faces viewer).
#
# These items are declared by `build_physics` but not yet driven by chain or
# jiggle math — the sim zone passes them through (last frame's value becomes
# this frame's value unchanged) until steps 10 and 11 of the 14-step plan
# wire the real sub-groups in. This split lets us validate the zone still
# evaluates at the higher state count before taking on sub-group work.

HAND_CHAINS = ('fingerA', 'fingerB', 'fingerC', 'fingerD')
HAND_SIDES = ('l', 'r')
FINGER_SEGMENTS = 2  # V1: 2 segments per finger (base→mid→tip)
PALM_CORNERS = ('ne', 'nw', 'se', 'sw')

HAND_CHAIN_POS_NAMES = [
    f'pos_{chain}_{side}_seg{seg}'
    for chain in HAND_CHAINS
    for side in HAND_SIDES
    for seg in range(FINGER_SEGMENTS)
]
HAND_CHAIN_PREV_NAMES = [
    f'prev_{chain}_{side}_seg{seg}'
    for chain in HAND_CHAINS
    for side in HAND_SIDES
    for seg in range(FINGER_SEGMENTS)
]

PALM_CORNER_POS_NAMES = [
    f'pos_palm_{side}_{corner}'
    for side in HAND_SIDES
    for corner in PALM_CORNERS
]
PALM_CORNER_PREV_NAMES = [
    f'prev_palm_{side}_{corner}'
    for side in HAND_SIDES
    for corner in PALM_CORNERS
]

# Sanity: design doc specifies 32 chain + 16 palm = 48 new items.
# Assert at import time so a refactor mistake in these lists fails fast.
assert len(HAND_CHAIN_POS_NAMES) == 16 and len(HAND_CHAIN_PREV_NAMES) == 16
assert len(PALM_CORNER_POS_NAMES) == 8 and len(PALM_CORNER_PREV_NAMES) == 8


# ===========================================================================
# REUSABLE NODE GROUP — PP_ShoulderFloat
# ===========================================================================
# A GN Group is a sub-tree that can be dropped into the main tree as a
# single node. We build one here so that the ~12 nodes of shoulder-float
# math live in one collapsible place instead of being copy-pasted for L/R.

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


# ===========================================================================
# REUSABLE NODE GROUP — PP_ChainVerletSegment (Phase 2, hand secondary motion)
# ===========================================================================
# This sub-group computes ONE segment of a finger chain for ONE frame. It is
# the GN port of `chain_segment_step` from the Python prototype that David
# greenlit on 2026-04-23 ("these look great, exactly as expected ty!").
#
# Why a sub-group at all: the algorithm has ~22 nodes of vector + scalar math.
# Hands have 4 chains × 2 segments × 2 sides = 16 instances per frame. Pasting
# 22 nodes 16 times would dump ~350 nodes into the main tree and make the
# editor unreadable. The group collapses each instance to a single node.
#
# Caller responsibilities (NOT done inside the group):
#   - Compute Goal in world space (palm basis × local rest offset).
#   - Compute Root Falloff Factor per-segment as
#         rf * (1 - seg_index / (n_segments - 1))
#     (matches the prototype; seg 0 → fully pinned, tip → free).
#   - Compute End Factor Scale per-segment as
#         1 + (Stiff End Fac - 1) * (seg_index / (n_segments - 1))
#     (matches the prototype; seg 0 → 1.0, tip → Stiff End Fac).
#   - Handle the FIRST-FRAME snap to Goal OUTSIDE the group, same pattern as
#     the existing Verlet endpoints (init_cmp / not_first). This keeps the
#     sub-group pure — it doesn't need a `first_frame` input and it can be
#     unit-tested by hand against `chain_segment_step` for any single frame.
#   - Handle the Jakobsen segment-length distance constraint OUTSIDE the
#     group — that's a per-pair-of-segments concern. `Parent Pos` is exposed
#     on the interface for the future case where we want to fold the
#     constraint inside; today it is reserved-but-unused (see docstring).

def _ensure_chain_segment_group():
    """Create or retrieve the PP_ChainVerletSegment node group.

    Faithful port of the Python prototype's `chain_segment_step`. One
    instance computes one segment, one frame:

        vel        = (Pos - Prev) * Chain Velocity
        vel_d      = vel * (1 - Chain Dampening)
        grav_vec   = (0, 0, -Chain Gravity * dt^2)

        to_goal    = Goal - Pos
        goal_pull  = to_goal * Chain Stiffness * End Factor Scale

        vel_len    = length(vel)
        vel_t      = clamp((vel_len - Stiff Vel Min) /
                           (Stiff Vel Max - Stiff Vel Min), 0, 1)
        vel_stiff  = Stiff Vel Fac * vel_t
        vel_pull   = to_goal * vel_stiff

        physics    = Pos + vel_d + grav_vec + goal_pull + vel_pull
        New Pos    = mix(physics, Goal, Root Falloff Factor)
        New Prev   = Pos

    `Parent Pos` is declared on the interface for future use (Jakobsen
    distance constraint, if we ever decide to bake it in here instead of
    leaving it to the caller). Today it is unwired — adding the socket
    now means step 10 wiring won't have to refactor the interface.

    `Stiff End Fac` and `Root Falloff` (the raw preset scalars) are
    intentionally NOT on the interface — they are used only to compute
    `End Factor Scale` and `Root Falloff Factor` per-segment, which the
    caller does once before instantiation.
    """
    existing = bpy.data.node_groups.get("PP_ChainVerletSegment")
    if existing:
        return existing

    g = bpy.data.node_groups.new(
        "PP_ChainVerletSegment", 'GeometryNodeTree')
    g.interface.clear()

    # --- Inputs (vec3 first, then float) ---
    g.interface.new_socket(
        "Pos", in_out='INPUT', socket_type='NodeSocketVector')
    g.interface.new_socket(
        "Prev", in_out='INPUT', socket_type='NodeSocketVector')
    g.interface.new_socket(
        "Parent Pos", in_out='INPUT', socket_type='NodeSocketVector')
    g.interface.new_socket(
        "Goal", in_out='INPUT', socket_type='NodeSocketVector')

    s = g.interface.new_socket(
        "Root Falloff Factor", in_out='INPUT',
        socket_type='NodeSocketFloat')
    s.default_value = 0.0
    s.min_value = 0.0
    s.max_value = 1.0
    s = g.interface.new_socket(
        "End Factor Scale", in_out='INPUT', socket_type='NodeSocketFloat')
    s.default_value = 1.0
    s = g.interface.new_socket(
        "Delta Time", in_out='INPUT', socket_type='NodeSocketFloat')
    s.default_value = 1.0 / 30.0

    # 7 used chain-sim params (Stiff End Fac and Root Falloff omitted —
    # caller pre-bakes them into End Factor Scale and Root Falloff Factor).
    s = g.interface.new_socket(
        "Chain Velocity", in_out='INPUT', socket_type='NodeSocketFloat')
    s.default_value = 1.0
    s = g.interface.new_socket(
        "Chain Dampening", in_out='INPUT', socket_type='NodeSocketFloat')
    s.default_value = 0.25
    s = g.interface.new_socket(
        "Chain Gravity", in_out='INPUT', socket_type='NodeSocketFloat')
    s.default_value = 0.02
    s = g.interface.new_socket(
        "Chain Stiffness", in_out='INPUT', socket_type='NodeSocketFloat')
    s.default_value = 0.35
    s = g.interface.new_socket(
        "Stiff Vel Fac", in_out='INPUT', socket_type='NodeSocketFloat')
    s.default_value = 0.1
    s = g.interface.new_socket(
        "Stiff Vel Min", in_out='INPUT', socket_type='NodeSocketFloat')
    s.default_value = 0.05
    s = g.interface.new_socket(
        "Stiff Vel Max", in_out='INPUT', socket_type='NodeSocketFloat')
    s.default_value = 0.5

    # --- Tip-pull inputs (alpha.52 / dropout delta, NATIVE_PHYSICS_DESIGN_
    # DELTA_DROPOUT.md §Delta 3). Tracked Tip is the world-space position
    # MediaPipe reports for the tracked fingertip (already lerped by the
    # receiver during REACQUIRING). Tip Pull Live is the per-frame Live
    # float — 1.0=tracked → full pull, 0.0=released → no pull, in-between
    # during the asymmetric ramp. Tip Pull Strength is set per-instance
    # by hands.py from physics_presets.TIP_PULL_STRENGTH (0.6 default),
    # NOT user-tunable as a slider — same status as MIDLINE_MARGIN.
    #
    # Sub-group defaults are intentionally "off-by-default": Tip Pull Live
    # defaults to 0.0 so an instantiated sub-group with nothing wired
    # produces zero tip-pull contribution (chain runs as plain Verlet +
    # goal pull). Tracked Tip defaults to (0,0,0) which only matters when
    # Live > 0; untracked chains leave Live at 0 and don't care about
    # Tracked Tip. Tracked chains in hands.py (step 3d) wire Live to
    # `Hand <side> Live` from the modifier interface (which defaults to
    # 1.0, so a freshly-built rig pre-tracking still pulls correctly
    # toward the tracked socket — which is also (0,0,0) pre-tracking,
    # so the rest-pose fallback in hands.py takes over).
    g.interface.new_socket(
        "Tracked Tip", in_out='INPUT', socket_type='NodeSocketVector')
    s = g.interface.new_socket(
        "Tip Pull Live", in_out='INPUT', socket_type='NodeSocketFloat')
    s.default_value = 0.0
    s.min_value = 0.0
    s.max_value = 1.0
    s = g.interface.new_socket(
        "Tip Pull Strength", in_out='INPUT', socket_type='NodeSocketFloat')
    s.default_value = 0.6
    s.min_value = 0.0
    s.max_value = 5.0

    # --- Outputs ---
    g.interface.new_socket(
        "New Pos", in_out='OUTPUT', socket_type='NodeSocketVector')
    g.interface.new_socket(
        "New Prev", in_out='OUTPUT', socket_type='NodeSocketVector')

    dx = 200
    gin = add_node(g, 'NodeGroupInput', 0, 0, "In")

    # --- VELOCITY + DAMPING ---
    # vel_raw = Pos - Prev
    vel_raw = add_node(g, 'ShaderNodeVectorMath', dx, 0, "VelRaw")
    vel_raw.operation = 'SUBTRACT'
    g.links.new(gin.outputs['Pos'], vel_raw.inputs[0])
    g.links.new(gin.outputs['Prev'], vel_raw.inputs[1])

    # vel = vel_raw * Chain Velocity
    vel = add_node(g, 'ShaderNodeVectorMath', dx * 2, 0, "Vel")
    vel.operation = 'SCALE'
    g.links.new(vel_raw.outputs['Vector'], vel.inputs[0])
    g.links.new(gin.outputs['Chain Velocity'], vel.inputs['Scale'])

    # one_minus_cd = 1 - Chain Dampening
    one_minus_cd = add_node(g, 'ShaderNodeMath', dx, -120, "1-CD")
    one_minus_cd.operation = 'SUBTRACT'
    one_minus_cd.inputs[0].default_value = 1.0
    g.links.new(gin.outputs['Chain Dampening'], one_minus_cd.inputs[1])

    # vel_d = vel * (1 - cd)
    vel_d = add_node(g, 'ShaderNodeVectorMath', dx * 3, 0, "VelD")
    vel_d.operation = 'SCALE'
    g.links.new(vel.outputs['Vector'], vel_d.inputs[0])
    g.links.new(one_minus_cd.outputs['Value'], vel_d.inputs['Scale'])

    _frame_section(g,
        "VELOCITY — Verlet implicit velocity from (Pos - Prev),"
        " scaled by Chain Velocity then attenuated by Dampening",
        'verlet', [vel_raw, vel, one_minus_cd, vel_d])

    # --- GRAVITY (= (0, 0, -1) * Chain Gravity * dt^2) ---
    dt_sq = add_node(g, 'ShaderNodeMath', dx, -260, "dt^2")
    dt_sq.operation = 'MULTIPLY'
    g.links.new(gin.outputs['Delta Time'], dt_sq.inputs[0])
    g.links.new(gin.outputs['Delta Time'], dt_sq.inputs[1])

    grav_mag = add_node(g, 'ShaderNodeMath', dx * 2, -260, "GravMag")
    grav_mag.operation = 'MULTIPLY'
    g.links.new(gin.outputs['Chain Gravity'], grav_mag.inputs[0])
    g.links.new(dt_sq.outputs['Value'], grav_mag.inputs[1])

    grav_z = add_node(g, 'ShaderNodeMath', dx * 3, -260, "-GravZ")
    grav_z.operation = 'MULTIPLY'
    g.links.new(grav_mag.outputs['Value'], grav_z.inputs[0])
    grav_z.inputs[1].default_value = -1.0

    grav_vec = add_node(g, 'ShaderNodeCombineXYZ', dx * 4, -260, "GravVec")
    g.links.new(grav_z.outputs['Value'], grav_vec.inputs['Z'])

    _frame_section(g,
        "GRAVITY — Down-Z vector scaled by Chain Gravity * dt^2,"
        " same Verlet convention as the body endpoints",
        'physics', [dt_sq, grav_mag, grav_z, grav_vec])

    # --- GOAL PULL (rest-pose memory, attenuated toward chain tip) ---
    to_goal = add_node(g, 'ShaderNodeVectorMath', dx, -420, "ToGoal")
    to_goal.operation = 'SUBTRACT'
    g.links.new(gin.outputs['Goal'], to_goal.inputs[0])
    g.links.new(gin.outputs['Pos'], to_goal.inputs[1])

    stiff_x_efs = add_node(g, 'ShaderNodeMath', dx * 2, -420, "Stf*EFS")
    stiff_x_efs.operation = 'MULTIPLY'
    g.links.new(gin.outputs['Chain Stiffness'], stiff_x_efs.inputs[0])
    g.links.new(gin.outputs['End Factor Scale'], stiff_x_efs.inputs[1])

    goal_pull = add_node(g, 'ShaderNodeVectorMath', dx * 3, -420, "GoalPull")
    goal_pull.operation = 'SCALE'
    g.links.new(to_goal.outputs['Vector'], goal_pull.inputs[0])
    g.links.new(stiff_x_efs.outputs['Value'], goal_pull.inputs['Scale'])

    _frame_section(g,
        "GOAL PULL — Spring back toward rest pose."
        " End Factor Scale lets the tip droop more freely than the base.",
        'rest', [to_goal, stiff_x_efs, goal_pull])

    # --- VELOCITY-SCALED STIFFNESS (Cody's marquee feature) ---
    # vel_t = clamp((|vel| - Stiff Vel Min) / (Stiff Vel Max - Stiff Vel Min),
    #               0, 1)  — Map Range with clamp=True does this in one node.
    vel_len = add_node(g, 'ShaderNodeVectorMath', dx, -580, "VelLen")
    vel_len.operation = 'LENGTH'
    g.links.new(vel.outputs['Vector'], vel_len.inputs[0])

    vel_t = add_node(g, 'ShaderNodeMapRange', dx * 2, -580, "VelT")
    vel_t.data_type = 'FLOAT'
    vel_t.interpolation_type = 'LINEAR'
    vel_t.clamp = True
    g.links.new(vel_len.outputs['Value'], vel_t.inputs['Value'])
    g.links.new(gin.outputs['Stiff Vel Min'], vel_t.inputs['From Min'])
    g.links.new(gin.outputs['Stiff Vel Max'], vel_t.inputs['From Max'])
    vel_t.inputs['To Min'].default_value = 0.0
    vel_t.inputs['To Max'].default_value = 1.0

    vel_stiff = add_node(g, 'ShaderNodeMath', dx * 3, -580, "VStf")
    vel_stiff.operation = 'MULTIPLY'
    g.links.new(gin.outputs['Stiff Vel Fac'], vel_stiff.inputs[0])
    g.links.new(vel_t.outputs['Result'], vel_stiff.inputs[1])

    vsp = add_node(g, 'ShaderNodeVectorMath', dx * 4, -580, "VStfPull")
    vsp.operation = 'SCALE'
    g.links.new(to_goal.outputs['Vector'], vsp.inputs[0])
    g.links.new(vel_stiff.outputs['Value'], vsp.inputs['Scale'])

    _frame_section(g,
        "VELOCITY STIFFNESS — Extra spring kick when the segment is"
        " moving fast (Goo-physics 'marquee feature'). Ramps from 0 at"
        " Stiff Vel Min to Stiff Vel Fac at Stiff Vel Max.",
        'control', [vel_len, vel_t, vel_stiff, vsp])

    # --- TIP PULL (alpha.52 — pull toward MediaPipe-tracked fingertip,
    # gated by the per-hand Live float). Three nodes, parallel to the
    # other contribution chains (gravity, goal pull, vel stiffness).
    # to_tip = Tracked Tip - Pos    — vector toward tracked tip
    # tps_live = Tip Pull Strength * Tip Pull Live    — gated magnitude
    # tip_pull = to_tip * tps_live  — final contribution vector
    # When Live = 0 (RELEASED), tps_live = 0 → contribution is identically
    # zero → chain runs as a free Verlet rope under gravity + goal pull.
    # When Live = 1 (TRACKED), tps_live = Tip Pull Strength → chain is
    # pulled toward the tracked tip with full strength.
    to_tip = add_node(g, 'ShaderNodeVectorMath', dx * 1, -740, "ToTip")
    to_tip.operation = 'SUBTRACT'
    g.links.new(gin.outputs['Tracked Tip'], to_tip.inputs[0])
    g.links.new(gin.outputs['Pos'], to_tip.inputs[1])

    tps_live = add_node(g, 'ShaderNodeMath', dx * 2, -740, "TPS*Live")
    tps_live.operation = 'MULTIPLY'
    g.links.new(gin.outputs['Tip Pull Strength'], tps_live.inputs[0])
    g.links.new(gin.outputs['Tip Pull Live'], tps_live.inputs[1])

    tip_pull = add_node(g, 'ShaderNodeVectorMath', dx * 3, -740, "TipPull")
    tip_pull.operation = 'SCALE'
    g.links.new(to_tip.outputs['Vector'], tip_pull.inputs[0])
    g.links.new(tps_live.outputs['Value'], tip_pull.inputs['Scale'])

    _frame_section(g,
        "TIP PULL — Pull toward the MediaPipe-tracked fingertip, gated"
        " by the per-hand Live float. Live=0 → contribution is zero,"
        " chain dangles freely. Live=1 → full pull, chain reaches for"
        " the tracked tip. Receiver lerps Tracked Tip during recovery.",
        'control', [to_tip, tps_live, tip_pull])

    # --- INTEGRATE (Pos + vel_d + grav + goal_pull + vel_stiff_pull
    #                + tip_pull) ---
    add1 = add_node(g, 'ShaderNodeVectorMath', dx * 5, 0, "+VelD")
    add1.operation = 'ADD'
    g.links.new(gin.outputs['Pos'], add1.inputs[0])
    g.links.new(vel_d.outputs['Vector'], add1.inputs[1])

    add2 = add_node(g, 'ShaderNodeVectorMath', dx * 6, 0, "+Grav")
    add2.operation = 'ADD'
    g.links.new(add1.outputs['Vector'], add2.inputs[0])
    g.links.new(grav_vec.outputs['Vector'], add2.inputs[1])

    add3 = add_node(g, 'ShaderNodeVectorMath', dx * 7, 0, "+GoalP")
    add3.operation = 'ADD'
    g.links.new(add2.outputs['Vector'], add3.inputs[0])
    g.links.new(goal_pull.outputs['Vector'], add3.inputs[1])

    physics_pos = add_node(g, 'ShaderNodeVectorMath', dx * 8, 0, "+VStf")
    physics_pos.operation = 'ADD'
    g.links.new(add3.outputs['Vector'], physics_pos.inputs[0])
    g.links.new(vsp.outputs['Vector'], physics_pos.inputs[1])

    add_tip = add_node(g, 'ShaderNodeVectorMath', dx * 9, 0, "Physics")
    add_tip.operation = 'ADD'
    g.links.new(physics_pos.outputs['Vector'], add_tip.inputs[0])
    g.links.new(tip_pull.outputs['Vector'], add_tip.inputs[1])

    _frame_section(g,
        "INTEGRATE — Sum all six contributions: damped velocity carries"
        " momentum, gravity drops, goal pull springs home, velocity"
        " stiffness adds the kick, tip pull reaches for tracked tip.",
        'physics', [add1, add2, add3, physics_pos, add_tip])

    # --- ROOT FALLOFF MIX (segments near the chain root stay pinned) ---
    # mix(add_tip, Goal, Root Falloff Factor) implemented as a 3-node
    # vector lerp via the shared `_vector_lerp` helper:
    #     result = add_tip + (Goal - add_tip) * Factor
    #     Factor = 0 → add_tip (no pin); Factor = 1 → Goal (full pin).
    # ShaderNodeMix would also work but its sockets are positional + named
    # ambiguously across data types — the helper keeps wiring obvious and
    # matches the rest of the codebase (see body_movement.py BT blend).
    snap_mix = _snap_nodes(g)
    new_pos = _vector_lerp(
        g, dx * 10, 0, "RootMix",
        a_out=add_tip.outputs['Vector'],
        b_out=gin.outputs['Goal'],
        factor_out=gin.outputs['Root Falloff Factor'])

    _frame_section(g,
        "ROOT FALLOFF — Blend toward Goal by per-segment pin strength."
        " Caller pre-computes Root Falloff Factor"
        " (seg 0 = full pin, tip = free).",
        'float', _new_nodes(g, snap_mix))

    # --- OUTPUTS ---
    gout = add_node(g, 'NodeGroupOutput', dx * 12, 0, "Out")
    g.links.new(new_pos.outputs['Vector'], gout.inputs['New Pos'])
    g.links.new(gin.outputs['Pos'], gout.inputs['New Prev'])

    return g


# ===========================================================================
# REUSABLE NODE GROUP — PP_JiggleSpring (Phase 2, palm-corner flop)
# ===========================================================================
# Single-bone spring-mass jiggle. Much simpler than the chain segment —
# no chain index, no velocity-scaled stiffness, no gravity. A spring wants
# to return to (Parent Pos + Rest Offset); damping bleeds off oscillation;
# friction attenuates velocity over time. GN port of `jiggle_step` from
# /tmp/jiggle_sim_prototype.py, validated against DEFAULTJIGGLE /
# JIGGLELOOSE / JIGGLESTIFF / PPPALMV1 in the Python prototype on
# 2026-04-23 ("settle time 1.67s on step input, no overshoot").
#
# One instance per palm corner. V1: 4 corners per side × 2 sides = 8
# instances total, all parameterized from the shared
# JIGGLE_PRESET_FOR_PALM (PPPALMV1) preset at build time.
#
# Caller responsibilities (NOT done inside the group):
#   - Compute `Parent Pos` as the palm plate center in world space.
#   - Compute `Rest Offset` as the NE/NW/SE/SW local offset, rotated by
#     the palm basis so the corner sits at the right spot on the palm
#     regardless of hand orientation.
#   - Handle the FIRST-FRAME snap to (Parent Pos + Rest Offset) OUTSIDE
#     the group, same pattern as the Verlet endpoints and chain segments
#     (init_cmp / not_first). Keeps the sub-group pure — no `first_frame`
#     input to wire, and the group unit-tests cleanly against
#     `jiggle_step` for any mid-sim frame.

def _ensure_jiggle_spring_group():
    """Create or retrieve the PP_JiggleSpring node group.

    Faithful port of the Python prototype's `jiggle_step`. One instance
    computes one palm corner, one frame:

        target       = Parent Pos + Rest Offset
        vel          = (Pos - Prev) * Jiggle Speed

        force_spring = (target - Pos) * Jiggle Stiffness
        force_damp   = vel * (-Jiggle Damping * dt)
        force        = force_spring + force_damp

        accel        = force / max(Jiggle Mass, 1e-9)
        vel_next     = (vel + accel * dt) * (1 - Jiggle Friction * dt)
        new_pos_raw  = Pos + vel_next

        New Pos      = lerp(target, new_pos_raw, Jiggle Sim Influence)
        New Prev     = Pos

    Sim Influence acts as a "how much does physics matter?" dial:
    1.0 → fully simulated (pure jiggle), 0.0 → snap to target (no
    jiggle, corner rides rigidly on the palm). Implemented with
    `_vector_lerp` (`target + (new_pos - target) * infl`) for the same
    reason as chain segment's Root Falloff blend: `ShaderNodeMix` has
    duplicate-named sockets across data types, and the helper is the
    codebase's convention.

    Mass guard: `max(Mass, 1e-9)` prevents a divide-by-zero if a caller
    or preset sets Mass to 0. The preset dict only holds positive masses
    (0.15–0.2); this guard is belt-and-suspenders against user override.
    """
    existing = bpy.data.node_groups.get("PP_JiggleSpring")
    if existing:
        return existing

    g = bpy.data.node_groups.new(
        "PP_JiggleSpring", 'GeometryNodeTree')
    g.interface.clear()

    # --- Inputs (vec3 first, then float) ---
    g.interface.new_socket(
        "Pos", in_out='INPUT', socket_type='NodeSocketVector')
    g.interface.new_socket(
        "Prev", in_out='INPUT', socket_type='NodeSocketVector')
    g.interface.new_socket(
        "Parent Pos", in_out='INPUT', socket_type='NodeSocketVector')
    g.interface.new_socket(
        "Rest Offset", in_out='INPUT', socket_type='NodeSocketVector')

    s = g.interface.new_socket(
        "Delta Time", in_out='INPUT', socket_type='NodeSocketFloat')
    s.default_value = 1.0 / 30.0

    # 6 jiggle params — defaults match DEFAULTJIGGLE from
    # physics_presets.py (same convention as chain segment using
    # DEFAULTGEONODES-style defaults). Caller overwrites with PPPALMV1
    # values at Create-Puppet time. Order mirrors the algorithm's
    # evaluation order so a reader scanning the interface sees the
    # same narrative arc as a reader scanning the node graph:
    # Speed (velocity), Stiffness (spring), Damping (damp), Mass
    # (accel), Friction (vel_next), Sim Influence (blend).
    s = g.interface.new_socket(
        "Jiggle Speed", in_out='INPUT', socket_type='NodeSocketFloat')
    s.default_value = 0.8
    s = g.interface.new_socket(
        "Jiggle Stiffness", in_out='INPUT', socket_type='NodeSocketFloat')
    s.default_value = 0.1
    s = g.interface.new_socket(
        "Jiggle Damping", in_out='INPUT', socket_type='NodeSocketFloat')
    s.default_value = 8.0
    s = g.interface.new_socket(
        "Jiggle Mass", in_out='INPUT', socket_type='NodeSocketFloat')
    s.default_value = 0.15
    s = g.interface.new_socket(
        "Jiggle Friction", in_out='INPUT', socket_type='NodeSocketFloat')
    s.default_value = 5.0
    s = g.interface.new_socket(
        "Jiggle Sim Influence", in_out='INPUT', socket_type='NodeSocketFloat')
    s.default_value = 1.0

    # --- Outputs ---
    g.interface.new_socket(
        "New Pos", in_out='OUTPUT', socket_type='NodeSocketVector')
    g.interface.new_socket(
        "New Prev", in_out='OUTPUT', socket_type='NodeSocketVector')

    dx = 200
    gin = add_node(g, 'NodeGroupInput', 0, 0, "In")

    # --- VELOCITY (Verlet implicit velocity, scaled by Jiggle Speed) ---
    # Same pattern as chain segment's VELOCITY section: (Pos - Prev)
    # gives per-frame displacement, Jiggle Speed lets the animator
    # attenuate or amplify momentum.
    vel_raw = add_node(g, 'ShaderNodeVectorMath', dx, 0, "VelRaw")
    vel_raw.operation = 'SUBTRACT'
    g.links.new(gin.outputs['Pos'], vel_raw.inputs[0])
    g.links.new(gin.outputs['Prev'], vel_raw.inputs[1])

    vel = add_node(g, 'ShaderNodeVectorMath', dx * 2, 0, "Vel")
    vel.operation = 'SCALE'
    g.links.new(vel_raw.outputs['Vector'], vel.inputs[0])
    g.links.new(gin.outputs['Jiggle Speed'], vel.inputs['Scale'])

    _frame_section(g,
        "VELOCITY — Verlet implicit velocity from (Pos - Prev),"
        " scaled by Jiggle Speed",
        'verlet', [vel_raw, vel])

    # --- SPRING FORCE (Hooke's law pull toward rest target) ---
    # target = Parent Pos + Rest Offset. The corner rides on the palm
    # plate at a fixed local offset; the spring wants to bring the
    # simulated position back to that anchor.
    target = add_node(g, 'ShaderNodeVectorMath', dx, -140, "Target")
    target.operation = 'ADD'
    g.links.new(gin.outputs['Parent Pos'], target.inputs[0])
    g.links.new(gin.outputs['Rest Offset'], target.inputs[1])

    to_target = add_node(g, 'ShaderNodeVectorMath', dx * 2, -140, "ToTgt")
    to_target.operation = 'SUBTRACT'
    g.links.new(target.outputs['Vector'], to_target.inputs[0])
    g.links.new(gin.outputs['Pos'], to_target.inputs[1])

    force_spring = add_node(
        g, 'ShaderNodeVectorMath', dx * 3, -140, "FSpring")
    force_spring.operation = 'SCALE'
    g.links.new(to_target.outputs['Vector'], force_spring.inputs[0])
    g.links.new(
        gin.outputs['Jiggle Stiffness'], force_spring.inputs['Scale'])

    _frame_section(g,
        "SPRING FORCE — Hooke's law. Pulls the corner back toward"
        " (Parent Pos + Rest Offset) proportional to displacement.",
        'rest', [target, to_target, force_spring])

    # --- DAMPING FORCE (opposes velocity, scaled by Damping * dt) ---
    # This is what actually settles the oscillation. Without damping
    # the spring would ring forever.
    damping_x_dt = add_node(g, 'ShaderNodeMath', dx, -280, "Damp*dt")
    damping_x_dt.operation = 'MULTIPLY'
    g.links.new(gin.outputs['Jiggle Damping'], damping_x_dt.inputs[0])
    g.links.new(gin.outputs['Delta Time'], damping_x_dt.inputs[1])

    neg_damping_x_dt = add_node(
        g, 'ShaderNodeMath', dx * 2, -280, "-Damp*dt")
    neg_damping_x_dt.operation = 'MULTIPLY'
    g.links.new(damping_x_dt.outputs['Value'], neg_damping_x_dt.inputs[0])
    neg_damping_x_dt.inputs[1].default_value = -1.0

    force_damp = add_node(
        g, 'ShaderNodeVectorMath', dx * 3, -280, "FDamp")
    force_damp.operation = 'SCALE'
    g.links.new(vel.outputs['Vector'], force_damp.inputs[0])
    g.links.new(
        neg_damping_x_dt.outputs['Value'], force_damp.inputs['Scale'])

    _frame_section(g,
        "DAMPING FORCE — Bleeds kinetic energy off proportional to"
        " velocity and dt. This is what actually settles the oscillation.",
        'physics', [damping_x_dt, neg_damping_x_dt, force_damp])

    # --- NET FORCE + ACCEL (force / mass, with divide-by-zero floor) ---
    # Newton's F = m·a solved for a. MassSafe floors at 1e-9 so a
    # misconfigured preset (Mass = 0) doesn't produce NaN acceleration
    # and blow up the sim zone.
    force = add_node(g, 'ShaderNodeVectorMath', dx * 4, -200, "Force")
    force.operation = 'ADD'
    g.links.new(force_spring.outputs['Vector'], force.inputs[0])
    g.links.new(force_damp.outputs['Vector'], force.inputs[1])

    mass_safe = add_node(g, 'ShaderNodeMath', dx * 4, -380, "MassSafe")
    mass_safe.operation = 'MAXIMUM'
    g.links.new(gin.outputs['Jiggle Mass'], mass_safe.inputs[0])
    mass_safe.inputs[1].default_value = 1e-9

    inv_mass = add_node(g, 'ShaderNodeMath', dx * 5, -380, "1/Mass")
    inv_mass.operation = 'DIVIDE'
    inv_mass.inputs[0].default_value = 1.0
    g.links.new(mass_safe.outputs['Value'], inv_mass.inputs[1])

    accel = add_node(g, 'ShaderNodeVectorMath', dx * 5, -200, "Accel")
    accel.operation = 'SCALE'
    g.links.new(force.outputs['Vector'], accel.inputs[0])
    g.links.new(inv_mass.outputs['Value'], accel.inputs['Scale'])

    _frame_section(g,
        "NET FORCE + ACCEL — Newton's F = m·a, solved for a."
        " MassSafe floors at 1e-9 as a divide-by-zero guard.",
        'physics', [force, mass_safe, inv_mass, accel])

    # --- VELOCITY UPDATE ((vel + accel*dt) * (1 - friction*dt)) ---
    # Explicit-Euler-style integration step for velocity, then a
    # multiplicative friction term that attenuates overall motion
    # regardless of direction. Friction is NOT "air resistance" here;
    # it's a kinematic drag knob that helps the corner stop drifting
    # when the palm is still.
    accel_x_dt = add_node(g, 'ShaderNodeVectorMath', dx * 6, -200, "A*dt")
    accel_x_dt.operation = 'SCALE'
    g.links.new(accel.outputs['Vector'], accel_x_dt.inputs[0])
    g.links.new(gin.outputs['Delta Time'], accel_x_dt.inputs['Scale'])

    vel_plus_accel = add_node(
        g, 'ShaderNodeVectorMath', dx * 7, 0, "V+A")
    vel_plus_accel.operation = 'ADD'
    g.links.new(vel.outputs['Vector'], vel_plus_accel.inputs[0])
    g.links.new(accel_x_dt.outputs['Vector'], vel_plus_accel.inputs[1])

    friction_x_dt = add_node(
        g, 'ShaderNodeMath', dx * 6, -520, "Fric*dt")
    friction_x_dt.operation = 'MULTIPLY'
    g.links.new(gin.outputs['Jiggle Friction'], friction_x_dt.inputs[0])
    g.links.new(gin.outputs['Delta Time'], friction_x_dt.inputs[1])

    one_minus_fric_dt = add_node(
        g, 'ShaderNodeMath', dx * 7, -520, "1-F*dt")
    one_minus_fric_dt.operation = 'SUBTRACT'
    one_minus_fric_dt.inputs[0].default_value = 1.0
    g.links.new(
        friction_x_dt.outputs['Value'], one_minus_fric_dt.inputs[1])

    vel_next = add_node(
        g, 'ShaderNodeVectorMath', dx * 8, 0, "VNext")
    vel_next.operation = 'SCALE'
    g.links.new(vel_plus_accel.outputs['Vector'], vel_next.inputs[0])
    g.links.new(
        one_minus_fric_dt.outputs['Value'], vel_next.inputs['Scale'])

    _frame_section(g,
        "VELOCITY UPDATE — Integrate acceleration into velocity,"
        " then attenuate by (1 - Friction * dt) for kinematic drag",
        'verlet', [accel_x_dt, vel_plus_accel,
                   friction_x_dt, one_minus_fric_dt, vel_next])

    # --- NEW POS (Pos + vel_next) — the Verlet position update ---
    new_pos_raw = add_node(
        g, 'ShaderNodeVectorMath', dx * 9, 0, "NewRaw")
    new_pos_raw.operation = 'ADD'
    g.links.new(gin.outputs['Pos'], new_pos_raw.inputs[0])
    g.links.new(vel_next.outputs['Vector'], new_pos_raw.inputs[1])

    _frame_section(g,
        "NEW POS — Integrate velocity into position (Verlet step)."
        " This is the pre-blend physics answer.",
        'physics', [new_pos_raw])

    # --- SIM INFLUENCE BLEND (lerp target → new_pos by Sim Influence) ---
    # Sim Influence = 1.0 → fully physics (new_pos_raw), 0.0 → snap to
    # target (corner rides rigidly on the palm, no jiggle at all).
    # `_vector_lerp(a=target, b=new_pos_raw, factor=sim_influence)`:
    #   result = target + (new_pos_raw - target) * sim_influence
    # Matches the prototype's
    #   new_pos = new_pos * si + target * (1 - si)
    # (algebraically identical). Three vector-math nodes; see chain
    # segment's Root Falloff mix for rationale over ShaderNodeMix.
    snap_mix = _snap_nodes(g)
    new_pos = _vector_lerp(
        g, dx * 10, 0, "InflMix",
        a_out=target.outputs['Vector'],
        b_out=new_pos_raw.outputs['Vector'],
        factor_out=gin.outputs['Jiggle Sim Influence'])

    _frame_section(g,
        "SIM INFLUENCE — Blend between rest target and physics position."
        " 1.0 = full jiggle, 0.0 = snap to rest (physics disabled).",
        'float', _new_nodes(g, snap_mix))

    # --- OUTPUTS ---
    gout = add_node(g, 'NodeGroupOutput', dx * 13, 0, "Out")
    g.links.new(new_pos.outputs['Vector'], gout.inputs['New Pos'])
    g.links.new(gin.outputs['Pos'], gout.inputs['New Prev'])

    return g


# ===========================================================================
# SIMULATION ZONE — must use operator for proper pairing (Blender 5.2)
# ===========================================================================

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


# ===========================================================================
# VERLET PHYSICS — per-endpoint node builder
# ===========================================================================

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


# ===========================================================================
# SHOULDER FLOAT — attachment drifts when arm pulls (Jim Rose: 5/8" slack)
# ===========================================================================

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


# ===========================================================================
# build_physics — the full sim zone + Verlet cascade
# ===========================================================================

def build_physics(tree, group_in, context, *,
                  shl_visual, shr_visual,
                  shl_attach, shr_attach, hipl_attach, hipr_attach,
                  rest_hl, rest_hr, rest_fl, rest_fr,
                  snap_state):
    """Build sim zone + physics core + shoulder float + per-endpoint Verlet.

    Call this AFTER the attachment-point section has tilted + delta-added
    the four physics attach nodes, and BEFORE the visual body-parts section
    (which reads `pos_hand_l/r`, `pos_foot_l/r`, `floated_shl/shr` off the
    returned `sim_out` to position joints, limbs, hands, and feet).

    Parameters
    ----------
    tree : GN node tree
        The marionette tree. Nodes get added directly to it.
    group_in : Group Input node
        Source for Gravity, Damping, Ground Height, Ground Friction,
        Arm Length, Leg Length, Shoulder Float sockets.
    context : bpy.types.Context
        Needed by `_create_sim_zone` — the Blender 5.2 simulation-zone
        operator requires a NODE_EDITOR area override to pair its input
        and output nodes correctly.
    shl_visual, shr_visual : Vector Math nodes
        The static shoulder base positions (joint centers, after the
        head-rotation tilt, before the Verlet delta is added). Feed the
        PP_ShoulderFloat group's Base Attach.
    shl_attach, shr_attach, hipl_attach, hipr_attach : Vector Math nodes
        The four physics attachment points (visual + contralateral
        delta). Their `.outputs['Vector']` sockets drive the Verlet
        distance constraint.
    rest_hl, rest_hr, rest_fl, rest_fr : Vector Math nodes
        Rest positions (attachment + gravity-down drop). Used on frame 1
        to initialize the sim zone before any physics run.
    snap_state : set
        Result of the previous `_snap_nodes(tree)` call. Needed so the
        first `_frame_section` in this module wraps only the nodes added
        since the caller's last snap. Every `_frame_section` call inside
        this function updates `_s` locally; the final value is returned
        so the caller can keep threading frames through the rest of the
        tree.

    Returns
    -------
    dict with keys:
        sim_in      — SimulationInput node (exposed for completeness;
                      callers rarely need it after this function)
        sim_out     — SimulationOutput node. Downstream modules read
                      `.outputs['pos_hand_l/r']`, `.outputs['pos_foot_l/r']`,
                      and `.outputs['floated_shl/shr']` off this.
        snap_state  — updated snap (set) after the VERLET PHYSICS frame
    """
    _s = snap_state

    # Phase 2 sub-group bootstrap. Both `_ensure_chain_segment_group`
    # and `_ensure_jiggle_spring_group` are idempotent — calling them
    # here makes PP_ChainVerletSegment and PP_JiggleSpring available in
    # the .blend's node-group library so standalone step-5/6 validation
    # works (drop a manual GeometryNodeGroup, assign the group, compare
    # output to the Python prototypes in /tmp/). Neither group is
    # instantiated in this tree — chain wiring lands in step 10/14,
    # jiggle wiring in step 11/14.
    _ensure_chain_segment_group()
    _ensure_jiggle_spring_group()

    # ======================================================================
    # SECTION 5 — Simulation Zone
    # ======================================================================
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

    # --- Phase 2 hand physics state items ---
    # 32 finger-chain + 16 palm-corner vectors. Declared here, passthrough-
    # wired below, sim-wired in steps 10/11. See module-level HAND_CHAIN_*
    # and PALM_CORNER_* constants for the naming scheme.
    _hand_state_names = (
        HAND_CHAIN_POS_NAMES + HAND_CHAIN_PREV_NAMES +
        PALM_CORNER_POS_NAMES + PALM_CORNER_PREV_NAMES)
    for name in _hand_state_names:
        sim_out.state_items.new('VECTOR', name)

    tree.links.new(sim_in.outputs['Geometry'], sim_out.inputs['Geometry'])

    # Passthrough each Phase 2 hand item so the zone evaluates. Each item's
    # previous-frame value is copied straight to the next frame; once
    # hands.py lands in step 7 and the Verlet/jiggle sub-groups in 10/11,
    # these passthrough links get replaced by the real sim output. Keeping
    # the passthrough explicit (rather than leaving sim_out.inputs unwired)
    # makes intent obvious and avoids any evaluation surprises from
    # unconnected zone inputs.
    for name in _hand_state_names:
        tree.links.new(sim_in.outputs[name], sim_out.inputs[name])

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

    # ======================================================================
    # SECTION 6 — Shared physics nodes (inside sim zone)
    # ======================================================================
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

    # ======================================================================
    # SECTION 6.5 — Shoulder float (uses previous-frame endpoint pos)
    # ======================================================================
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

    # ======================================================================
    # SECTION 7 — Per-endpoint Verlet physics + hinge constraints
    # ======================================================================
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

    return {
        'sim_in': sim_in,
        'sim_out': sim_out,
        'snap_state': _s,
        # First-frame init plumbing — exposed so other in-zone modules
        # (hands.py chain physics, alpha.54+) can reuse the same compare
        # node instead of re-deriving it from sim_in.outputs['initialized'].
        # Same socket pair _add_verlet_endpoint already consumes locally:
        #   init_cmp_out  = 1 on frame 1, 0 thereafter (snap to rest)
        #   not_first_out = 0 on frame 1, 1 thereafter (run physics)
        'init_cmp_out': init_cmp.outputs['Result'],
        'not_first_out': not_first.outputs['Value'],
    }
