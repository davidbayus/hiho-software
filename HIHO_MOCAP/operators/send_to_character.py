"""Send to Character operator — the loaded take's motion drives the
auto-rigged (or any ajc27-named) character armature.

Applies the stock ajc27 constraint stack (core/bind_to_rig.py, verbatim —
David's 2026-07-01 call: no recipe changes before BASEMENT) to the picked
character rig, targeting the loaded take's empties. Auto-rigged characters
have the 23 body bones, so the 40 finger entries skip cleanly.
"""

import os

import bpy

from ..core.bind_to_rig import clear_hiho_constraints
from ..core.rotation_retarget import apply_rotation_retarget
from . import STATE, norm_path

_FINGER_PARTS = ("thumb", "palm", "f_index", "f_middle", "f_ring", "f_pinky")


def _stripped(name: str) -> str:
    parts = name.rsplit(".", 1)
    return parts[0] if len(parts) == 2 and parts[1].isdigit() else name


def _scale_take_to_character(skelly_root, rig, scene):
    """Uniformly scale the loaded take so its skeleton matches the character's
    size. Without this a big character binds to person-sized targets and the
    bone chains fold back on themselves — the 'crumple' David hit (2026-07-01,
    5.4x mismatch on his chibi). Ratio = character rest hip height : recorded
    hip height (median of 3 sampled frames). Idempotent: the original scale is
    remembered on the skelly root, so re-sending recomputes from base instead
    of compounding. Returns the factor, or None if scaling wasn't possible."""
    hips = next((c for c in skelly_root.children_recursive
                 if _stripped(c.name) == "hiho_hips_center"), None)
    pelvis = rig.data.bones.get("pelvis")
    if hips is None or pelvis is None:
        return None
    char_hip_z = (rig.matrix_world @ pelvis.head_local).z
    if char_hip_z <= 0:
        return None

    from mathutils import Vector
    prev_frame = scene.frame_current
    zs = []
    for f in (scene.frame_start + 5,
              (scene.frame_start + scene.frame_end) // 2,
              scene.frame_end - 5):
        scene.frame_set(max(f, scene.frame_start))
        bpy.context.view_layer.update()
        zs.append(hips.matrix_world.translation.z)
    scene.frame_set(prev_frame)
    zs.sort()
    mocap_hip_z = zs[1]

    if "hiho_base_scale" not in skelly_root:
        skelly_root["hiho_base_scale"] = list(skelly_root.scale)
    base = Vector(skelly_root["hiho_base_scale"])
    current_factor = skelly_root.scale.z / base.z if base.z else 1.0
    mocap_hip_at_base = mocap_hip_z / max(current_factor, 1e-6)
    if mocap_hip_at_base <= 1e-4:
        return None
    factor = max(min(char_hip_z / mocap_hip_at_base, 100.0), 0.05)
    skelly_root.scale = base * factor
    bpy.context.view_layer.update()
    return factor


class HIHO_MOCAP_OT_send_to_character(bpy.types.Operator):
    """Make the picked character armature perform the loaded take"""
    bl_idname = "hiho_mocap.send_to_character"
    bl_label = "Send to Character"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        settings = context.scene.hiho_mocap
        return bool(settings.last_processed_path) and settings.character_target is not None

    def execute(self, context):
        settings = context.scene.hiho_mocap
        rig = settings.character_target
        if rig is None or rig.type != 'ARMATURE':
            self.report({'ERROR'}, "Pick your character's rig in the Character field.")
            return {'CANCELLED'}

        processed_path = norm_path(settings.last_processed_path)
        if not processed_path:
            self.report({'ERROR'}, "No take loaded. Use Load Take first.")
            return {'CANCELLED'}
        recording_folder = os.path.dirname(os.path.dirname(processed_path))
        folder_name = os.path.basename(os.path.normpath(recording_folder))
        skelly_root = bpy.data.objects.get(f"HIHO_MOCAP_Skelly_{folder_name}")
        skelly_rig = bpy.data.objects.get(f"HIHO_MOCAP_Rig_{folder_name}")
        if skelly_root is None or skelly_rig is None:
            self.report({'ERROR'}, "This take isn't in the scene yet. Use Load Take first.")
            return {'CANCELLED'}

        factor = _scale_take_to_character(skelly_root, rig, context.scene)

        cleared = clear_hiho_constraints(rig)
        try:
            bound, skipped = apply_rotation_retarget(rig, skelly_rig)
        except Exception as exc:
            self.report({'ERROR'}, f"Bind failed: {type(exc).__name__}: {exc}")
            return {'CANCELLED'}

        finger_skips = [b for b in skipped if any(p in b for p in _FINGER_PARTS)]
        other_skips = [b for b in skipped if b not in finger_skips]

        msg = f"{rig.name} is performing the take — press Spacebar. Bound {len(bound)} bone(s)"
        if factor is not None and abs(factor - 1.0) > 0.02:
            msg += f", scaled the take to your character (x{factor:.1f})"
        if cleared:
            msg += f", refreshed {cleared} old link(s)"
        if finger_skips:
            msg += f". ({len(finger_skips)} finger bones skipped — auto-rigs don't have fingers yet.)"
        if other_skips:
            preview = ", ".join(other_skips[:4])
            more = f" +{len(other_skips) - 4}" if len(other_skips) > 4 else ""
            msg += f" Missing body bones skipped: {preview}{more}."
        STATE["status_text"] = msg
        self.report({'WARNING'} if other_skips else {'INFO'}, msg)
        return {'FINISHED'}
