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
from .marionette.body_movement import build_body_movement
from .marionette.physics import build_physics, SHOULDER_FLOAT_SLACK


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

# Joint constraints, sim zone state items, and the Verlet/shoulder-float
# helpers all live with their consumer in marionette/physics.py. Re-exported
# via `from .marionette.physics import build_physics` at the top of this file.

# FACE_INPUTS (the 18 ARKit blend shape names) now lives with the face
# tracking interface builder in marionette/face_tracking.py. Re-exported
# at the top of this file for callers that still reference it.



# ===================================================================
# REUSABLE NODE GROUPS — collapse repeated math into single nodes
# ===================================================================
# PP_DynCapsule (the Minkowski capsule group) lives in
# marionette/capsules.py. PP_TwoBoneIK (elbow/knee solver) lives in
# marionette/body_parts.py (sibling of the body composition it serves).
# PP_ShoulderFloat (Jim Rose shoulder drift) lives in marionette/physics.py
# alongside the sim zone + Verlet + constraint helpers it belongs with.
# See REFACTOR_PLAN.md for the curriculum order.


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
