# SPDX-License-Identifier: GPL-3.0-or-later
"""PPParty — Create Marionette operator.

This file is now intentionally thin. The entire GN-tree build lives in
`marionette/assembly.py` (orchestrator) and the eight sibling modules
(capsules, materials, blob_head, body_parts, face_tracking, body_movement,
physics, studio_track). All that remains here is the Blender-side glue:

    - create_armature(context) — builds the single-bone PP_Armature that
      receives head rotation from the tracker.
    - PPPARTY_OT_create_marionette — the Create Puppet operator. Creates
      materials, armature, puppet mesh + GN modifier; calls
      build_marionette_tree() to populate the tree; drops Studio Track
      placeholder objects into the scene and assigns them to the Custom
      Chest / Hips / Foot sockets; sets scene fps=30 and frame_end=24000
      to match the MediaPipe sender and avoid sim-zone reset mid-perf.
    - PPPARTY_OT_reset_physics — jumps to frame 1 to re-init the sim zone.

See PPPARTY/REFACTOR_PLAN.md for the curriculum order + per-module notes,
and marionette/assembly.py for the section-by-section breakdown of the
GN tree itself.
"""

import bpy

from .marionette.materials import (
    create_body_materials,
    create_blob_head_materials,
)
from .marionette.assembly import build_marionette_tree


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
