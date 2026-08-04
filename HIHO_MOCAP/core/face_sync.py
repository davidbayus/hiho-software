"""Line Up Face — sync a face take to the body take via the flash marker.

The performer blinks a flashlight once at the start of every take; the same
physical instant is visible in the camera video planes (body clock) and in
the phone's reference video (face clock). David scrubs to the flash in each,
clicks Mark Flash (Body) / Mark Flash (Face), and Line Up Face shifts the
face shape-key action and the face video plane so the two flashes land on
the same timeline frame. The playhead does all the math — no typed numbers
(FACE_CAPTURE_DESIGN_2026-07-20).

Shifts are applied ABSOLUTELY: the target offset is computed from the marks,
each carrier remembers how far it has already been shifted (custom prop on
the action, base frame on the plane), and only the difference is applied.
Re-marking and re-running therefore corrects by the delta instead of
compounding, and a freshly re-loaded (unshifted) action self-heals on the
next Line Up.
"""

import bpy

ACTION_OFFSET_PROP = "hiho_lineup_offset"


def target_offset(body_flash: float, face_flash: float,
                  offset_at_mark: float) -> float:
    """Total frames the face content must sit later than its raw import.

    face_flash was marked while the face content was already shifted by
    offset_at_mark, so the flash lives at (face_flash - offset_at_mark) in
    the raw take; putting it onto body_flash needs this absolute offset.
    """
    return body_flash - (face_flash - offset_at_mark)


def find_face_target(context):
    """The mesh face takes play on: the Test Face, else the active mesh
    with shape keys. Same resolution order as Load Face Take."""
    target = bpy.data.objects.get("HIHO Test Face")
    if target is None:
        active = context.active_object
        if (active is not None and active.type == 'MESH'
                and active.data.shape_keys is not None):
            target = active
    return target


def find_face_action(target):
    """The HIHO face-take action on target's shape keys, or None."""
    if target is None or target.data.shape_keys is None:
        return None
    anim = target.data.shape_keys.animation_data
    if anim is None or anim.action is None:
        return None
    if not anim.action.name.startswith("HIHO_FaceTake_"):
        return None
    return anim.action


def applied_offset(action) -> float:
    """How far this action has already been shifted by Line Up Face."""
    return float(action.get(ACTION_OFFSET_PROP, 0.0)) if action else 0.0


def shift_action(action, delta: float):
    """Move every keyframe in the action delta frames along the timeline.

    Returns (fcurves_shifted, last_key_frame). Slotted-action layout:
    fcurves live under layers > strips > channelbags (Blender 5.x).
    """
    shifted = 0
    last = 0.0
    for layer in action.layers:
        for strip in layer.strips:
            for bag in strip.channelbags:
                for fcurve in bag.fcurves:
                    count = len(fcurve.keyframe_points)
                    if not count:
                        continue
                    for attr in ("co", "handle_left", "handle_right"):
                        buf = [0.0] * (2 * count)
                        fcurve.keyframe_points.foreach_get(attr, buf)
                        buf[0::2] = [x + delta for x in buf[0::2]]
                        fcurve.keyframe_points.foreach_set(attr, buf)
                    fcurve.update()
                    shifted += 1
                    last = max(last, fcurve.keyframe_points[-1].co[0])
    return shifted, last
