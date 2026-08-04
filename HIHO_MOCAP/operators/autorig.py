"""Auto-Rig operator — one click from placed markers to a skinned character.

Fit half: core/marker_fit.py grows the ajc27-named body skeleton from the 13
markers. Skin half: core/voxel_skinning.py glues the mesh to it (voxel solver
by default, Blender Automatic Weights as toggle or automatic fallback).
"""

import bpy
from mathutils import Vector

from ..core import marker_fit, voxel_skinning
from . import STATE
from .markers import MARKER_TEMPLATE, character_meshes, find_marker


class HIHO_MOCAP_OT_auto_rig(bpy.types.Operator):
    """Build a skeleton fitted to the markers and skin the character to it"""
    bl_idname = "hiho_mocap.auto_rig"
    bl_label = "Auto-Rig"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        settings = context.scene.hiho_mocap

        marker_objects = {marker_id: find_marker(marker_id)
                          for marker_id in MARKER_TEMPLATE}
        markers = {mid: Vector(ob.location) if ob else None
                   for mid, ob in marker_objects.items()}
        missing = marker_fit.missing_markers(markers)
        if missing:
            self.report({'ERROR'},
                        f"Missing marker(s): {', '.join(missing)}. Run Add Markers first.")
            return {'CANCELLED'}

        meshes = character_meshes(context)
        if not meshes:
            self.report({'ERROR'},
                        "No character found. Import Character first (or select your character's meshes).")
            return {'CANCELLED'}

        centered = marker_fit.center_marker_depth(
            marker_objects, meshes, settings.marker_mirror_axis)
        if centered:
            markers = {mid: Vector(ob.location) if ob else None
                       for mid, ob in marker_objects.items()}
        already_rigged = [ob.name for ob in meshes
                          if any(mod.type == 'ARMATURE' and mod.object is not None
                                 and not mod.object.name.startswith("HIHO_AutoRig")
                                 for mod in ob.modifiers)]
        if already_rigged:
            self.report({'ERROR'},
                        f"{already_rigged[0]} is already rigged to a non-HIHO armature. "
                        "Remove that rig first (one rig at a time).")
            return {'CANCELLED'}

        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        rig_name = f"HIHO_AutoRig_{settings.character_collection or 'Character'}"
        self._purge_prior_rig(rig_name, meshes)

        rig = marker_fit.build_marker_armature(
            markers, meshes, rig_name, settings.marker_mirror_axis)

        fell_back = False
        if settings.skinning_mode == 'VOXEL':
            ok, detail = voxel_skinning.skin_voxel(meshes, rig)
            if not ok:
                fell_back = True
                fail_reason = detail
                ok, detail = voxel_skinning.skin_automatic(meshes, rig)
        else:
            ok, detail = voxel_skinning.skin_automatic(meshes, rig)

        if not ok:
            self.report({'ERROR'}, f"Auto-Rig failed at skinning: {detail}")
            return {'CANCELLED'}

        settings.character_target = rig
        msg = f"Auto-Rig done: {detail}."
        if centered:
            msg = f"Centered {centered} marker(s) in the body. " + msg
        if fell_back:
            msg = (f"Auto-Rig done with fallback — voxel solver said: {fail_reason}. "
                   f"{detail} instead.")
        msg += " Next: Load a take, then Send to Character."
        STATE["status_text"] = msg
        self.report({'WARNING'} if fell_back else {'INFO'}, msg)
        return {'FINISHED'}

    @staticmethod
    def _purge_prior_rig(rig_name, meshes):
        """Re-running Auto-Rig replaces the previous attempt (same pattern as
        Spawn Rig): drop the old armature, its modifiers, and its vertex
        groups so weights never stack."""
        prior = bpy.data.objects.get(rig_name)
        if prior is None:
            return
        deform_names = {b.name for b in prior.data.bones}
        for ob in meshes:
            for mod in list(ob.modifiers):
                if mod.type == 'ARMATURE' and mod.object is prior:
                    ob.modifiers.remove(mod)
            for vg in list(ob.vertex_groups):
                if vg.name in deform_names:
                    ob.vertex_groups.remove(vg)
            if ob.parent is prior:
                world = ob.matrix_world.copy()
                ob.parent = None
                ob.matrix_world = world
        data = prior.data
        bpy.data.objects.remove(prior)
        if data.users == 0:
            bpy.data.armatures.remove(data)
