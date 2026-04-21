# SPDX-License-Identifier: GPL-3.0-or-later
"""Body movement — face → body mapping, BT blend, torso sway + bob + lift.

=============================================================================
Why this file exists
=============================================================================
A marionette has two layers of input. The face is one — webcam blend shapes
drive the eyes, mouth, cheeks. But the puppet's BODY also has to move, and
that's what this module is about.

In traditional marionette work, the puppeteer works a control bar above the
puppet. Tilting the bar left makes the whole body lean left. Dipping the
bar forward extends an arm. A waist cord connects chest to pelvis so they
sway on different timelines. A good puppeteer can suggest walking with
nothing but bar tilts — no individual string pulls required.

PPParty recreates that control-bar feel using face tracking. The performer's
head rotation and mouth shape become the control bar. The body leans, steps,
lifts, gestures — all driven by face signals, no arms-up required. That's
what the code here builds in the Geometry Nodes tree.

When the webcam ALSO sees the performer's body (MediaPipe's body landmarks),
we fade from "face drives body" (heuristic puppet) to "body drives body"
(real motion capture). The blend is per-limb: if the performer's left arm
drops off camera, that arm falls back to the face heuristic while the
tracked arm keeps tracking. That fade is Section 2.5 here.

Finally, once we know where each limb wants to go, the chest and pelvis
still need to sway, bob, and lift in sympathy. A walking puppet rises
slightly on each step (Jim Rose's "we raise our bodies above the ground
rather more at the beginning of a step than at the end"). Raised eyebrows
'pick up' the whole puppet. Those body-wide motions are Section 3.

=============================================================================
The three sections this module builds, in order
=============================================================================

    SECTION 2 — The Control Bar
        The marionette control bar. Each face-tracking signal becomes a
        small delta vector that will eventually be added onto the body:
          headRotY (lean)   → lateral sway + contralateral arm/leg swing
          headRotX (extend) → forward tilt + arm spread
          headRotZ (roll)   → slight torso twist
          mouthLeft/Right   → contralateral knee lift (deliberate stepping)
          mouthSmileRight   → arm lift (celebration gesture)
          mouthFrownL/R avg → arm drop (defeat gesture)
        Outputs four delta vectors (shl_delta, shr_delta, hipl_delta,
        hipr_delta), plus the raw `lean`/`extend`/`torso_twist` scalars
        Section 3 will reuse.

    SECTION 2.5 — The Body Tracking Blend
        When the "Body Tracking" slider is > 0, real body landmarks from
        MediaPipe arrive on the `bt_shl_delta`/`bt_shr_delta`/etc. inputs.
        We lerp each face-heuristic delta against its tracked counterpart
        by a per-limb factor (`Body Tracking × limb visibility`). If a
        limb leaves the camera frame, its visibility drops, the lerp
        falls back to the heuristic. If BT = 0, we get pure face puppet.
        If BT = 1 with full visibility, we get pure motion capture.
        Outputs four final deltas: shl_delta_final, shr_delta_final,
        hipl_delta_final, hipr_delta_final.

    SECTION 3 — The Strings
        Chest and pelvis positions. Lean sways them laterally. Extend
        sways them forward/back. Walking bob (abs(lean)) lifts them.
        Eyebrow raise + jaw-open add a Z lift. Mouth lateral adds an
        X shift (chest more than pelvis — waist cord). Then we mute all
        of this sway by `face_factor = 1 - Body Tracking` so that when
        BT is active, the body only moves from tracked landmarks, not
        from face heuristics bleeding in. Outputs chest_pos, pelvis_pos,
        waist_mid, and head_lift_muted (Section 3.5 uses it to make the
        head follow the body, but only when face-driven).

=============================================================================
Why this runs as a single function and not three
=============================================================================
The three sections share a LOT of intermediate values. `lean` from
Section 2 feeds Section 3's bob. `face_factor` from 2.5 mutes Section 3's
sway. `torso_twist` from 2 feeds Section 3's Y sway on both chest and
pelvis. Extending the boundaries between the three in Python would mean
threading 8–10 node references across functions just to wire them back
together. One function keeps the cross-wiring readable.

The `_frame_section` calls at the end of each section still give the GN
editor three separately-labeled frames (control / control / strings), so
the curriculum reader still sees three conceptual blocks.

=============================================================================
What this module exports
=============================================================================
    build_body_movement(tree, group_in, body_ctr, *,
                        blob_tf, head_pos_fixed,
                        CHEST_OFFSET, PELVIS_OFFSET,
                        snap_state)
        Adds all three sections to `tree`. Returns a dict of output
        sockets + updated snap_state. See the function docstring for the
        full signature and output contract.
"""


from ._common import (
    add_node,
    _snap_nodes,
    _new_nodes,
    _frame_section,
    _vector_lerp,
)


# ===========================================================================
# build_body_movement — the full face→body cascade
# ===========================================================================

def build_body_movement(tree, group_in, body_ctr, *,
                        blob_tf, head_pos_fixed,
                        CHEST_OFFSET, PELVIS_OFFSET,
                        snap_state):
    """Build the control bar + BT blend + torso sway cascade.

    Call this AFTER the blob head / face-tracking section has wired
    head_pos_fixed / blob_tf (so we can re-route the blob head's
    translation to follow torso sway when face-driven), and BEFORE the
    attachment-point section (which needs chest_pos, pelvis_pos, and the
    four final deltas).

    Parameters
    ----------
    tree : GN node tree
        The marionette tree. Nodes get added directly to it.
    group_in : Group Input node
        Source for every face tracking, head rotation, Body Tracking,
        visibility, and slider socket read here.
    body_ctr : Vector Math node
        Output socket `.outputs['Vector']` is the body center
        position (body_ctr_static + performer_offset * Body Tracking).
        Chest and pelvis positions are built as offsets from this.
    blob_tf : GeometryNodeTransform or None
        The blob head's Transform node. If present, its Translation
        input gets re-routed to `head_pos_fixed + head_lift_muted` so
        the blob head follows the torso sway when face-driven.
    head_pos_fixed : Vector Math node or None
        The blob head's static head position (body_ctr + HEAD_OFFSET).
        Only used if `blob_tf` is also present.
    CHEST_OFFSET, PELVIS_OFFSET : Vector
        Static offsets from body_ctr to chest and pelvis centers.
        Sway vectors get added on top of these.
    snap_state : set
        Result of the previous `_snap_nodes(tree)` call. We need it so
        the first _frame_section in this module wraps only the nodes
        added since the caller's last snap — not nodes from earlier
        sections. Every _frame_section call inside this function
        updates `_s` locally, and we return the final value so the
        caller can thread it forward.

    Returns
    -------
    dict with keys:
        chest_pos       — Vector Math node (output = chest world pos)
        pelvis_pos      — Vector Math node (output = pelvis world pos)
        waist_mid       — Vector Math node (midpoint between chest/pelvis)
        head_lift_muted — Vector Math node (torso lift × face_factor)
        shl_delta_final — output socket (Vector) — left shoulder blended
        shr_delta_final — output socket (Vector) — right shoulder blended
        hipl_delta_final — output socket (Vector) — left hip blended
        hipr_delta_final — output socket (Vector) — right hip blended
        arm_l_factor    — Math node (BT × vis_arm_l, for downstream use)
        arm_r_factor    — Math node (BT × vis_arm_r, for downstream use)
        snap_state      — updated snap (set) after THE STRINGS frame
    """
    _s = snap_state

    # ======================================================================
    # SECTION 2 — THE CONTROL BAR
    # ======================================================================
    # Head rotation → body movement deltas:
    #   lean (Y)   → lateral sway, contralateral gait
    #   extend (X) → forward tilt, arm spread
    #   mouth L/R  → contralateral knee lift
    #   smile/frown → arm gestures (up = celebration, down = defeat)
    #   headRotZ   → slight torso twist (Z roll → Y forward lean)
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

    # ======================================================================
    # SECTION 2.5 — BODY TRACKING BLEND
    # ======================================================================
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

    # ======================================================================
    # SECTION 3 — THE STRINGS (torso sway + walking bob + lift)
    # ======================================================================
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

    return {
        'chest_pos': chest_pos,
        'pelvis_pos': pelvis_pos,
        'waist_mid': waist_mid,
        'head_lift_muted': head_lift_muted,
        'shl_delta_final': shl_delta_final,
        'shr_delta_final': shr_delta_final,
        'hipl_delta_final': hipl_delta_final,
        'hipr_delta_final': hipr_delta_final,
        'arm_l_factor': arm_l_factor,
        'arm_r_factor': arm_r_factor,
        'snap_state': _s,
    }
