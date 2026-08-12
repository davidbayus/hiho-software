"""Lock Feet operator — stop planted feet from sliding, before Bake.

Runs core/foot_locking.py (ported from the vendored ajc27 operator, see
FOOT_LOCKING_DESIGN_2026-08-11.md) on the take's hiho_* tracking empties.
Edits the empties' location keys in place — values only, frame numbers
untouched — so the live constraint rig follows immediately and Bake writes
the locked result onto the bones. Fine-tuning lives in the redo panel;
frame-count parameters derive from the take's real fps, never hardcoded.
"""

import os

import bpy
import numpy as np

from ..core.bind_to_rig import strip_dup_suffix
from ..core.foot_locking import FOOT_MARKERS, lock_feet
from . import STATE, norm_path


def _location_fcurves(obj):
    """The 3 location fcurves of an empty, wherever 5.x actions keep them."""
    ad = obj.animation_data
    if not ad or not ad.action:
        return None
    fcs = []
    layers = getattr(ad.action, "layers", None)
    if layers:
        for layer in layers:
            for strip in layer.strips:
                for bag in strip.channelbags:
                    fcs.extend(bag.fcurves)
    if not fcs:
        fcs = list(ad.action.fcurves)
    by_index = {fc.array_index: fc for fc in fcs if fc.data_path == "location"}
    if set(by_index) < {0, 1, 2}:
        return None
    return [by_index[0], by_index[1], by_index[2]]


def _read_curve(fc):
    buf = np.empty(2 * len(fc.keyframe_points))
    fc.keyframe_points.foreach_get("co", buf)
    return buf[0::2].copy(), buf[1::2].copy()


def _find_skelly_root(context):
    path = norm_path(context.scene.hiho_mocap.last_processed_path)
    if path:
        folder = os.path.basename(os.path.dirname(os.path.dirname(path)))
        root = bpy.data.objects.get(f"HIHO_MOCAP_Skelly_{folder}")
        if root is not None:
            return root
    roots = [o for o in bpy.data.objects
             if o.name.startswith("HIHO_MOCAP_Skelly_")]
    return roots[0] if len(roots) == 1 else None


def _rig_is_baked(root):
    """True when a rig for this take exists but carries no HIHO_ constraints."""
    rig_name = root.name.replace("HIHO_MOCAP_Skelly_", "HIHO_MOCAP_Rig_", 1)
    rig = bpy.data.objects.get(rig_name)
    if rig is None or rig.type != 'ARMATURE':
        return False
    return not any(c.name.startswith("HIHO_")
                   for pb in rig.pose.bones for c in pb.constraints)


class HIHO_MOCAP_OT_lock_feet(bpy.types.Operator):
    """Find every stretch where a heel or toe stays on the floor and hold it
    still there, easing in and out. Fixes foot sliding. Works on the tracking
    empties — run before Bake."""
    bl_idname = "hiho_mocap.lock_feet"
    bl_label = "Lock Feet"
    bl_options = {'REGISTER', 'UNDO'}

    target_feet: bpy.props.EnumProperty(
        name="Feet",
        items=[('BOTH', "Both", ""),
               ('LEFT', "Left only", ""),
               ('RIGHT', "Right only", "")],
        default='BOTH',
    )
    contact_height: bpy.props.FloatProperty(
        name="Contact height",
        description="Below this height a heel or toe counts as touching the floor",
        default=0.02, min=0.001, max=0.2, precision=3, subtype='DISTANCE',
    )
    floor_height: bpy.props.FloatProperty(
        name="Floor height",
        description="Planted markers are held exactly here "
                    "(calibration puts the floor at 0)",
        default=0.0, precision=3, subtype='DISTANCE',
    )
    knees_absorb: bpy.props.FloatProperty(
        name="Knees absorb",
        description="How much of the ankle's correction the knee and hip "
                    "take up (lower if the character rig runs its own leg IK)",
        default=1.0, min=0.0, max=1.0,
    )
    steady_body: bpy.props.BoolProperty(
        name="Steady the body",
        description="Carry the hip shift through the whole upper body",
        default=True,
    )

    def execute(self, context):
        if self.floor_height >= self.contact_height:
            self.report({'ERROR'},
                        "Floor height must be below Contact height — the foot "
                        "has to dip under the contact line to be held on the floor.")
            return {'CANCELLED'}

        root = _find_skelly_root(context)
        if root is None:
            self.report({'ERROR'},
                        "Load a take first — Lock Feet works on the tracking "
                        "empties, before Bake.")
            return {'CANCELLED'}

        gathered = {}
        for child in root.children_recursive:
            if child.type != 'EMPTY':
                continue
            name = strip_dup_suffix(child.name)
            if not name.startswith("hiho_"):
                continue
            fcs = _location_fcurves(child)
            if fcs is None:
                continue
            counts = {len(fc.keyframe_points) for fc in fcs}
            if len(counts) != 1 or 0 in counts:
                continue
            frames, values = zip(*(_read_curve(fc) for fc in fcs))
            gathered[name[len("hiho_"):]] = {
                "fcurves": fcs,
                "frames": frames,
                "array": np.stack(values, axis=0),
            }

        sides = {'BOTH': ("left", "right"),
                 'LEFT': ("left",),
                 'RIGHT': ("right",)}[self.target_feet]

        # Only markers matching the ankle's key count can play; a take is
        # only lockable on sides whose three foot markers all exist.
        usable_sides = []
        missing = []
        n_ref = None
        for side in sides:
            spec = FOOT_MARKERS[side]
            needed = spec["base"] + [spec["ankle"]]
            absent = [m for m in needed if m not in gathered]
            if absent:
                missing += absent
                continue
            usable_sides.append(side)
            if n_ref is None:
                n_ref = gathered[spec["ankle"]]["array"].shape[1]
        if not usable_sides:
            self.report({'ERROR'},
                        "This take is missing foot markers: "
                        f"{', '.join(sorted(set(missing)))}. Nothing to lock.")
            return {'CANCELLED'}

        markers = {name: g["array"] for name, g in gathered.items()
                   if g["array"].shape[1] == n_ref}

        # Frame-count parameters follow the take's real clock (the 30-vs-60
        # lesson of 1.4.34): minimum hold 1/3 s, ease in/out 1/6 s each.
        fps = context.scene.render.fps
        stats = lock_feet(
            markers,
            z_threshold=self.contact_height,
            ground_level=self.floor_height,
            frame_window_min_size=max(2, round(fps / 3)),
            initial_attenuation_count=max(1, round(fps / 6)),
            final_attenuation_count=max(1, round(fps / 6)),
            knee_hip_compensation_coefficient=self.knees_absorb,
            compensate_upper_body=self.steady_body,
            target_feet=tuple(usable_sides),
        )

        for name in stats["modified_markers"]:
            g = gathered[name]
            for axis in range(3):
                fc = g["fcurves"][axis]
                buf = np.empty(2 * len(g["frames"][axis]))
                buf[0::2] = g["frames"][axis]
                buf[1::2] = markers[name][axis]
                fc.keyframe_points.foreach_set("co", buf)
                fc.update()

        total_windows = sum(stats["windows"].values())
        if not total_windows and not stats["clamped_frames"]:
            self.report({'WARNING'},
                        f"No foot plants found below {self.contact_height:.3f} m "
                        "— is the floor at height 0 in this take? Try raising "
                        "Contact height.")
            return {'FINISHED'}

        per_side = ", ".join(f"{stats['windows'].get(s, 0)} {s}"
                             for s in usable_sides)
        msg = (f"Locked {total_windows} foot plants ({per_side}): "
               f"{stats['planted_frames']} frames held to the floor, "
               f"ankle re-solved on {stats['ankle_adjusted']}, "
               f"body steadied on {stats['body_frames']}.")
        if stats["skipped_feet"]:
            msg += f" Skipped (markers missing): {', '.join(stats['skipped_feet'])}."
        if _rig_is_baked(root):
            msg += (" This take is already baked — Spawn Rig again and lock "
                    "BEFORE Bake to see it on the rig.")
            self.report({'WARNING'}, msg)
        else:
            msg += " Play to check; Bake writes it onto the rig."
            self.report({'INFO'}, msg)
        STATE["status_text"] = msg
        return {'FINISHED'}
