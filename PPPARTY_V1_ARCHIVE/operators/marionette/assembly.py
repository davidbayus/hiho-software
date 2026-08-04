# SPDX-License-Identifier: GPL-3.0-or-later
"""Assembly — the orchestrator that calls every other marionette module.

=============================================================================
Why this file exists
=============================================================================
The other modules in this folder are each a single chapter of the marionette
curriculum: a capsule primitive, a material palette, a blob head, a face
tracking interface, body-movement heuristics, physics, body composition,
studio-track overrides. Each module owns one idea and builds one frame in
the GN tree. That structure is what makes the addon teachable.

This file is the hand that turns the pages. `build_marionette_tree()` is the
top-level function the Create Puppet operator runs, and it calls the modules
in the order a student reads them:

    1.  THE FACE         → blob_head + face_tracking + cheek capsules
    2–3. THE CONTROL BAR → body_movement (lean, extend, step, lift, swing)
    3.5  ATTACHMENT      → where strings meet the body + shoulder tilt/yaw
    4.   REST POSE       → dangle positions (attachment + gravity)
    5–7. PHYSICS         → sim zone, Verlet, shoulder float, constraints
    8–9. BODY + SKELETON → capsules, limbs, IK, neck, spine
    10.  STUDIO TRACK    → custom-mesh overrides
    11.  FINAL JOIN      → blob head + body → group output

=============================================================================
What still lives inline (and why)
=============================================================================
Most of the work is already delegated to a module and shows up here as a
one-line `build_X(...)` call. A few stretches — the interface construction
at the top (GN panels + sockets the modifier reads), Section 1 cheek-capsule
building, Section 3.5 attachment-point helpers, Section 4 rest positions,
and the Section 11 final join — remain inline in this file.

That's deliberate. Those stretches are either (a) very tightly coupled to
the operator's `execute()` (the interface determines what sockets the
operator writes materials into), or (b) small enough that extracting them
would add import overhead without improving curriculum clarity. A later
pedagogical pass may tease out `cheeks.py` and `attachments.py`, but the
structural refactor stops here: every heavy section is its own module.

=============================================================================
What this module exports
=============================================================================
    build_marionette_tree(tree, body_mats, blob_mats, context)
        Wipe `tree` and rebuild the entire PPParty marionette inside it.
        Called once per Create Puppet — the operator owns the GN modifier
        and material creation; this function owns the tree contents.
"""


import bpy
from mathutils import Vector

from ._common import (
    add_node,
    _snap_nodes,
    _new_nodes,
    _frame_section,
)
from .blob_head import (
    load_blob_head_tree,
    enumerate_blob_custom_sockets,
    add_head_customization_sockets,
    build_blob_group,
)
from .body_parts import build_body_parts
from .face_tracking import FACE_INPUTS, build_face_tracking_interface
from .body_movement import build_body_movement
from .hands import build_hands
from .physics import build_physics, SHOULDER_FLOAT_SLACK
from .studio_track import build_studio_track


# ===================================================================
# CONSTANTS — body proportions + cheek anatomy
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
                     'bt_body_center',
                     'bt_wrist_l', 'bt_thumb_l', 'bt_index_l',
                     'bt_wrist_r', 'bt_thumb_r', 'bt_index_r'):
        s = tree.interface.new_socket(
            bt_name, in_out='INPUT', socket_type='NodeSocketVector',
            parent=bt_panel)
        s.hide_in_modifier = True

    # Hand liveness floats (alpha.52 / dropout delta) — receiver computes
    # these from a per-hand presence timer. 1.0 = tracked, 0.0 = released,
    # in-between = the asymmetric ramp during dropout/reacquisition.
    # hands.py reads them in step 3d to gate the tip-pull term on each
    # tracked-finger PP_ChainVerletSegment instance. Default 1.0 so a
    # freshly-built rig before tracking ever starts behaves identically
    # to alpha.50 (full tip pull, falls through to rest-pose fallback).
    # See NATIVE_PHYSICS_DESIGN_DELTA_DROPOUT.md §Delta 2.
    for live_name in ('Hand L Live', 'Hand R Live'):
        s = tree.interface.new_socket(
            live_name, in_out='INPUT', socket_type='NodeSocketFloat',
            parent=bt_panel)
        s.default_value = 1.0
        s.min_value = 0.0
        s.max_value = 1.0
        s.hide_in_modifier = True

    # Palm basis vectors (alpha.56) — orthonormal in-palm orientation
    # per hand. palm_x = across the palm (radial → ulnar after the
    # selfie L/R swap), palm_y = wrist → fingers in palm plane. The
    # third basis vector palm_z is reconstructed GN-side via
    # cross(palm_x, palm_y) — saves 2 sockets per hand.
    #
    # alpha.57: hands.py consumes these to replace _yaw_mirror_for_side
    # at anchor / palm corners / finger rest_dirs / palm plate. Defaults
    # encode the V1-like rest pose (palms face forward, fingers dangle
    # down): palm_x = world +X (across), palm_y = world -Z (fingers
    # toward floor). Right-handed for both sides — no chirality flip on
    # first tracking event. The cosmetic ±45° yaw of V1 is dropped from
    # the default — once MP detects the hand, the live basis takes over
    # and the palm rotates to match the performer.
    for vname, default in (
        ('palm_x_l', (1.0, 0.0, 0.0)),
        ('palm_y_l', (0.0, 0.0, -1.0)),
        ('palm_x_r', (1.0, 0.0, 0.0)),
        ('palm_y_r', (0.0, 0.0, -1.0)),
    ):
        s = tree.interface.new_socket(
            vname, in_out='INPUT', socket_type='NodeSocketVector',
            parent=bt_panel)
        s.default_value = default
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

    # Chain sim params — 7 of HAIRSIDE preset's 9. Defaults match
    # physics_presets.CHAIN_PRESETS["HAIRSIDE"] (the role-mapped preset
    # for fingers). Two preset-only knobs sit out: Root Falloff and
    # Stiff End Fac are baked into per-segment Root Falloff Factor and
    # End Factor Scale at Create-Marionette time (hands.py reads the
    # preset directly), so a runtime slider would be inert. The 7 here
    # ARE runtime-tunable — every chain segment instance reads them via
    # group_in.outputs[name]. Tooltips draw from GOO_PHYSICS_RESEARCH.md
    # parameter decoder (see ui/panels.py if/when sliders surface).
    for sock_name, default, smin, smax in (
            ("Chain Velocity",  1.0,  0.0, 2.0),
            ("Chain Dampening", 0.1,  0.0, 1.0),
            ("Chain Gravity",   0.02, 0.0, 0.2),
            ("Chain Stiffness", 0.41, 0.0, 1.0),
            ("Stiff Vel Fac",   0.2,  0.0, 1.0),
            ("Stiff Vel Min",   0.1,  0.0, 1.0),
            ("Stiff Vel Max",   1.0,  0.0, 5.0)):
        s = tree.interface.new_socket(
            sock_name, in_out='INPUT', socket_type='NodeSocketFloat',
            parent=ph_panel)
        s.default_value = default
        s.min_value = smin
        s.max_value = smax

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
    # SECTIONS 2 + 2.5 + 3 — Control bar, BT blend, torso sway
    # ------------------------------------------------------------------
    # Face → body cascade: head rotation + mouth shapes become control-bar
    # deltas (§2), MediaPipe body landmarks lerp against those deltas by
    # per-limb visibility (§2.5), and chest/pelvis swing/bob/lift in
    # sympathy (§3). All three sections live in marionette/body_movement.py.
    body_mv = build_body_movement(
        tree, group_in, body_ctr,
        blob_tf=blob_tf, head_pos_fixed=head_pos_fixed,
        CHEST_OFFSET=CHEST_OFFSET, PELVIS_OFFSET=PELVIS_OFFSET,
        snap_state=_s,
    )
    chest_pos = body_mv['chest_pos']
    pelvis_pos = body_mv['pelvis_pos']
    waist_mid = body_mv['waist_mid']
    head_lift_muted = body_mv['head_lift_muted']
    shl_delta_final = body_mv['shl_delta_final']
    shr_delta_final = body_mv['shr_delta_final']
    hipl_delta_final = body_mv['hipl_delta_final']
    hipr_delta_final = body_mv['hipr_delta_final']
    arm_l_factor = body_mv['arm_l_factor']
    arm_r_factor = body_mv['arm_r_factor']
    _s = body_mv['snap_state']

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
    # SECTIONS 5 + 6 + 6.5 + 7 — Sim zone + physics core + float + Verlet
    # ------------------------------------------------------------------
    # Sim-zone scaffolding, shared physics nodes (gravity + timestep +
    # first-frame init), shoulder float, and per-endpoint Verlet with
    # hinge / inward / midline / ground / friction constraints live in
    # marionette/physics.py. That module owns all four labeled frames
    # (simzone / physics / float / verlet) and returns the sim_in/sim_out
    # handles that downstream body_parts + Studio Track consume.
    physics_result = build_physics(
        tree, group_in, context,
        shl_visual=shl_visual, shr_visual=shr_visual,
        shl_attach=shl_attach, shr_attach=shr_attach,
        hipl_attach=hipl_attach, hipr_attach=hipr_attach,
        rest_hl=rest_hl, rest_hr=rest_hr,
        rest_fl=rest_fl, rest_fr=rest_fr,
        snap_state=_s,
    )
    sim_in = physics_result['sim_in']
    sim_out = physics_result['sim_out']
    _s = physics_result['snap_state']

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
    _idx_foot_l = body['_idx_foot_l']
    _idx_foot_r = body['_idx_foot_r']
    hand_l_pos = body['hand_l_pos']
    hand_r_pos = body['hand_r_pos']
    x_part = body['x_part']
    x_limb = body['x_limb']
    _s = body['snap_state']

    # ------------------------------------------------------------------
    # SECTION 9.5 — Hand geometry (Phase 2, step 7/14)
    # ------------------------------------------------------------------
    # Palm plate + 4 corner beads + 4 finger chains per side. Built
    # at rest pose for untracked bones; thumb tip (fingerA) and
    # pointer tip (fingerB) follow tracked MediaPipe positions via
    # bt_thumb_* and bt_index_* sockets. Remaining physics (palm
    # corner jiggle, untracked finger flop) lands in step 11.
    # Lives in marionette/hands.py (owns its own 'body' frame).
    #
    # alpha.49: palm anchors on hand_l/r_pos — the post-lerp arm
    # endpoint from body_parts. When Body Tracking is 0 (webcam
    # off, slider muted) that socket equals the Verlet-blended arm
    # endpoint, so the palm dangles at the arm tip. When Body
    # Tracking ramps up, the same socket becomes shoulder +
    # tracked_dir × arm_length, so the palm follows the performer.
    # Either way it's never (0,0,0), which kills the pre-tracking
    # teleport-to-origin we saw in alpha.47/48.
    #
    # alpha.54: hands.py now also runs INSIDE the sim zone (chain
    # physics writes finger seg state to sim_out). Pass through:
    #   sim_in            — for previous-frame state reads + Delta Time
    #   shl/shr_visual    — to recompute the hand_<S>_pos blend in-zone
    #   arm_l/r_factor    — same lerp factor body_parts uses post-zone
    #   init/not_first    — first-frame init (snap to rest on frame 1)
    # Live-gated tip pull replaces the old _with_fallback rest-snap;
    # when MP drops a hand the receiver ramps Hand <S> Live → 0 and
    # the chain dangles freely instead of jumping to a constant.
    hand_result = build_hands(
        tree, group_in, sim_in, sim_out, body_mats,
        shl_visual, shr_visual,
        arm_l_factor, arm_r_factor,
        palm_l_pos=hand_l_pos,
        palm_r_pos=hand_r_pos,
        rest_hl=rest_hl,
        rest_hr=rest_hr,
        init_cmp_out=physics_result['init_cmp_out'],
        not_first_out=physics_result['not_first_out'],
        snap_state=_s)
    parts_geo.extend(hand_result['parts_geo'])
    _s = hand_result['snap_state']

    # ------------------------------------------------------------------
    # SECTION 10 — Studio Track: Custom body part overrides
    # ------------------------------------------------------------------
    # Object Info → face-count check → Switch chain that swaps each of
    # the six capsule slots (chest / hips / L+R hand / L+R foot) for
    # student-modeled geometry when assigned. `parts_geo` is mutated in
    # place — the six indexed entries get rebound to Switch outputs.
    # Lives in marionette/studio_track.py (owns its own 'output' frame).
    studio_result = build_studio_track(
        tree, group_in,
        parts_geo=parts_geo,
        chest_pos=chest_pos, pelvis_pos=pelvis_pos,
        sim_out=sim_out,
        idx_chest=_idx_chest, idx_pelvis=_idx_pelvis,
        idx_foot_l=_idx_foot_l, idx_foot_r=_idx_foot_r,
        snap_state=_s,
    )
    parts_geo = studio_result['parts_geo']
    _s = studio_result['snap_state']

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
