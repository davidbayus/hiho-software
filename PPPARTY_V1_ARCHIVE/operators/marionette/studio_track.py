# SPDX-License-Identifier: GPL-3.0-or-later
"""Studio Track — swap default capsules for student-modeled geometry.

=============================================================================
Why this file exists
=============================================================================
Every other module in this refactor builds a default marionette: the chest
is a capsule, the hips are a capsule, the hands and feet are capsules. That
works — a "blob marionette" is a legitimate puppet, and the K-8 Stage Track
never needs more. But PPParty has a SECOND audience: high-school and CADRE
students who spend a semester learning to model, sculpt, and retopologize.
For them, the addon has to answer one more question:

    "I modeled a chest. Can I see my mesh driving the puppet?"

This module is the "yes." It wires four Object sockets onto the modifier —
Custom Chest, Custom Hips, Custom Hand, Custom Foot — and, when a student
assigns a mesh to one, swaps the default capsule out for the student's
geometry. The rest of the rig is unchanged: the same position signal drives
the custom mesh, the same sim-zone physics wobble it, the same joins merge
it into the final geometry. The STUDENT'S WORK is in the capsule slot.

This is the "runs at 30fps on the rig" moment from the Studio Track
curriculum: a sculpted chest that survives texture, normal bake, and
real-time evaluation becomes a passing project.

=============================================================================
The Switch pattern — "plug in student geometry"
=============================================================================
Every body part has one Switch node behind it. The Switch picks between
two inputs based on a Boolean — here, "does this Object have any faces?"

    false (default)  →  the procedural Minkowski capsule we already built
    true  (custom)   →  the student's mesh, transformed to the body part's
                        current world position

The Boolean comes from an Attribute Domain Size node on the Object Info
geometry: face count > 0 means the student assigned a real mesh. If the
Object socket is empty, face count is 0 and the Switch falls back to the
capsule. No modal UI, no error case, no broken state — an empty slot and
a full slot are both valid.

This is the same trick used for fallbacks throughout computing: pick a
"canary" value (here, 0 faces) that an unassigned input naturally produces,
test for it, branch on the result. The student does not see the Switch.
They assign an object, and their mesh appears.

=============================================================================
The Jim Rose waist-cord principle, inside the custom-mesh path
=============================================================================
The default chest and hips capsules are sphere-ish and rotation-invariant —
rotating them does nothing visible. Custom meshes are NOT sphere-ish. A
student chest with a face, a collar, and an asymmetric shirt will twist if
we rotate it. So the custom Transform for Chest and Hips takes a rotation
input: the head's own rotation, scaled down.

    chest_rot = head_rot × 0.5   (chest lags the head at half the angle)
    hips_rot  = head_rot × 0.3   (hips lag the chest at a further reduced angle)

That 0.5 / 0.3 taper is Jim Rose's marionette-in-motion observation: the
head pulls the chest, the chest pulls the hips, each with progressively
less twist. A real marionette's torso works this way because the waist
cord is twist-limited; a PPParty torso works this way because we stacked
two SCALE nodes off the same head-rotation vector.

Bare capsules get no rotation wired in. Custom meshes get the dampened
rotation wired in. Same code path, different visual payoff.

=============================================================================
What this module exports
=============================================================================
    build_studio_track(tree, group_in, *,
                       parts_geo,
                       chest_pos, pelvis_pos,
                       sim_out,
                       idx_chest, idx_pelvis,
                       idx_foot_l, idx_foot_r,
                       snap_state)
        Mutates `parts_geo` in-place: each of the four entries named by
        the idx_* arguments gets replaced with a Switch output that
        selects between the original capsule and the student's custom
        mesh. Returns a dict with the (same) `parts_geo` list and an
        updated `snap_state` so the caller can keep framing downstream
        sections.

        alpha.48: Custom Hand override was retired when the cartoon
        capsule hands were removed in favor of hands.py's articulated
        palm + finger-chain system. The "Custom Hand" socket stays on
        the modifier interface (kept hidden in assembly.py) so existing
        .blend files don't lose the slot, but nothing is wired to it;
        per-hand-part overrides (Custom Palm, Custom Thumb, Custom
        Finger A/B/C) are a future pedagogy phase, not an alpha.48 job.
"""


from ._common import add_node, _snap_nodes, _new_nodes, _frame_section


def build_studio_track(
    tree, group_in, *,
    parts_geo,
    chest_pos, pelvis_pos,
    sim_out,
    idx_chest, idx_pelvis,
    idx_foot_l, idx_foot_r,
    snap_state,
):
    """Wire the Custom Chest / Hips / Foot overrides into parts_geo.

    For each of the four capsule slots (chest, hips, L+R foot), build
    an Object Info → face-count check → Switch chain that replaces the
    default capsule with the student's mesh when one is assigned. Chest
    and Hips additionally pick up a dampened head-rotation vector so
    non-spherical meshes twist with the torso.

    `parts_geo` is mutated in place — the same list the caller passed in
    has four of its entries rebound to Switch outputs. The function
    returns the same list for symmetry with other build_* modules.

    alpha.48: Hand override was retired with the cartoon capsule hand.
    """
    # ------------------------------------------------------------------
    # SECTION 10 — Studio Track: Custom body part overrides
    # When a student assigns a custom object, it replaces the capsule.
    # Uses Object Info to read geometry, Switch to select default/custom.
    # ------------------------------------------------------------------
    x_cust = 3000
    _s = snap_state

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
                          idx_chest, 0,
                          rot_socket=chest_rot_damp.outputs['Vector'])

    # Custom Hips → replaces pelvis capsule (lower body below waist).
    # Chest and hips are split per the Jim Rose waist-cord principle:
    # a real marionette treats upper and lower body as two masses
    # linked by a twist-limited cord, moving on independent timelines.
    _custom_object_switch("Hips", "Custom Hips",
                          pelvis_pos.outputs['Vector'],
                          idx_pelvis, -300,
                          rot_socket=pelvis_rot_damp.outputs['Vector'])

    # Custom Hand is retired (alpha.48) — the old cartoon capsule hand
    # that this switched into was removed in favor of hands.py's
    # articulated palm + finger-chain system. The "Custom Hand" socket
    # stays declared on the interface (hidden) so existing .blend files
    # keep their slot, but no Switch is wired here.

    # Custom Foot → replaces both foot capsules (R is mirrored)
    _custom_object_switch("Foot L", "Custom Foot",
                          sim_out.outputs['pos_foot_l'],
                          idx_foot_l, -1200)
    _custom_object_switch("Foot R", "Custom Foot",
                          sim_out.outputs['pos_foot_r'],
                          idx_foot_r, -1500, mirror_x=True)

    _frame_section(tree,
        "STUDIO TRACK — Custom body part overrides (Object Info"
        " nodes). Assign student meshes to replace default capsules.",
        'output', _new_nodes(tree, _s))
    _s = _snap_nodes(tree)

    return {
        'parts_geo': parts_geo,
        'snap_state': _s,
    }
