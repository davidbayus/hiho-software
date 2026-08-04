"""Bake Animation operator — write real keyframes onto the selected rig's bones.

Until baking, HIHO rigs animate through live constraints (skelly bones follow
the tracking empties; characters copy rotations from the skelly bones), so
there are no keyframes to clean up, retime, or export. Baking samples the
final visual pose on every frame of the scene range, writes keyframes the
bones own, strips the live constraints, and hides the tracking empties.
Re-running Load Take + Spawn Rig rebuilds the live version any time.
Design + David's locked choices: BAKE_ANIMATION_DESIGN_2026-07-02.md.
"""
import bpy
import numpy as np

from ..core.bind_to_rig import clear_hiho_constraints


def _iter_fcurves(action):
    """Blender 5.x slotted actions keep curves in layers/strips/channelbags."""
    curves = []
    layers = getattr(action, "layers", None)
    if layers:
        for layer in layers:
            for strip in layer.strips:
                for bag in strip.channelbags:
                    curves.extend(bag.fcurves)
    if not curves:
        curves = list(action.fcurves)
    return curves


def _quaternion_continuity_pass(action):
    """Keep every quaternion channel on one spelling of the pose.

    The bake derives each frame's rotation independently, so a bone turning
    past 180° flips between q and -q — the same pose, opposite numbers.
    Smoothing later averages across the flip and swings the bone. Negating
    whole keyframes is pose-neutral. Each frame must be compared against the
    previous frame AS ALREADY CORRECTED — comparing against the raw previous
    frame only fixes the first frame of a flipped run.
    Diagnosis + validation: Z_JITTER_DIAGNOSIS_2026-08-04.md.
    """
    grouped = {}
    for fc in _iter_fcurves(action):
        if fc.data_path.endswith("rotation_quaternion"):
            grouped.setdefault(fc.data_path, {})[fc.array_index] = fc

    bones_fixed = 0
    keys_fixed = 0
    for data_path, channels in grouped.items():
        if len(channels) != 4:
            continue

        counts = {len(channels[i].keyframe_points) for i in range(4)}
        if len(counts) != 1 or 0 in counts:
            continue

        def read(fc, attr):
            buf = np.empty(len(fc.keyframe_points) * 2)
            fc.keyframe_points.foreach_get(attr, buf)
            return buf

        q = np.stack([read(channels[i], "co")[1::2] for i in range(4)], axis=1)

        signs = np.ones(len(q))
        reference = q[0].copy()
        for i in range(1, len(q)):
            if np.dot(q[i], reference) < 0.0:
                signs[i] = -1.0
                reference = -q[i]
            else:
                reference = q[i]

        flipped = int(np.count_nonzero(signs < 0))
        if flipped == 0:
            continue

        for i in range(4):
            fc = channels[i]
            for attr in ("co", "handle_left", "handle_right"):
                buf = read(fc, attr)
                buf[1::2] *= signs          # values only, never the frame numbers
                fc.keyframe_points.foreach_set(attr, buf)
            fc.update()

        bones_fixed += 1
        keys_fixed += flipped

    return bones_fixed, keys_fixed


class HIHO_MOCAP_OT_bake_animation(bpy.types.Operator):
    """Write one keyframe per frame onto the selected rig's bones over the
    scene frame range, then remove the live tracking constraints and hide the
    tracking empties. Load Take + Spawn Rig rebuilds the live rig anytime."""
    bl_idname = "hiho_mocap.bake_animation"
    bl_label = "Bake Animation"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.object is not None and context.object.type == 'ARMATURE'

    def execute(self, context):
        arm = context.object
        scn = context.scene
        f0, f1 = scn.frame_start, scn.frame_end
        frame_before = scn.frame_current
        pose_bones = list(arm.pose.bones)
        total = f1 - f0 + 1

        wm = context.window_manager
        wm.progress_begin(0, 100)

        # Pass 1: sample the constraint-driven pose per frame. Keys are only
        # written in pass 2, after the constraints are gone, so the sampling
        # is never contaminated by the keys being inserted.
        samples = {}
        for i, f in enumerate(range(f0, f1 + 1)):
            scn.frame_set(f)
            samples[f] = {
                pb.name: arm.convert_space(pose_bone=pb, matrix=pb.matrix,
                                           from_space='POSE', to_space='LOCAL')
                for pb in pose_bones
            }
            wm.progress_update(int(50 * i / total))

        # Only OUR constraints come off. A character with its own rigging (a
        # downloaded rig, a student's IK, CloudRig) keeps it — removing every
        # constraint unconditionally destroyed that setup in one click.
        constraint_count = clear_hiho_constraints(arm)

        for i, f in enumerate(range(f0, f1 + 1)):
            scn.frame_set(f)
            for pb in pose_bones:
                pb.matrix_basis = samples[f][pb.name]
                pb.keyframe_insert("location", frame=f)
                if pb.rotation_mode == 'QUATERNION':
                    pb.keyframe_insert("rotation_quaternion", frame=f)
                else:
                    pb.keyframe_insert("rotation_euler", frame=f)
                pb.keyframe_insert("scale", frame=f)
            wm.progress_update(50 + int(50 * i / total))

        bones_respelled = keys_respelled = 0
        if arm.animation_data and arm.animation_data.action:
            action = arm.animation_data.action
            action.name = f"{arm.name}_baked"
            bones_respelled, keys_respelled = _quaternion_continuity_pass(action)

        hidden = self._hide_tracking_empties(arm)
        scn.frame_set(frame_before)
        wm.progress_end()

        spelling = (f"{keys_respelled} keys re-spelled on {bones_respelled} bones"
                    if keys_respelled else "verified continuous")
        self.report({'INFO'},
                    f"Baked {len(pose_bones)} bones x {total} frames; "
                    f"{constraint_count} HIHO constraints removed; {hidden} tracking "
                    f"empties hidden; quaternion spelling: {spelling}. "
                    f"The bones own the keyframes now.")
        return {'FINISHED'}

    @staticmethod
    def _hide_tracking_empties(arm):
        # Only the skelly hangs from the tracking root empty; a baked character
        # has no empties of its own, so this quietly does nothing there.
        root = arm.parent
        if root is None or root.type != 'EMPTY':
            return 0
        hidden = 0
        for obj in [root, *root.children_recursive]:
            if obj.type == 'EMPTY':
                try:
                    obj.hide_set(True)
                    hidden += 1
                except RuntimeError:
                    pass
        return hidden
