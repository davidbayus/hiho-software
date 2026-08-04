"""PPParty V2 — NLA mute orchestration for live capture passes.

A pass's previously-recorded NLA strip would fight the live receiver if
left playing during a re-take: both want to write the same bones every
frame. The receiver writes pose_bone properties directly while the NLA
evaluates strip keyframes; whichever wrote last wins, and over many
ticks per frame the result is a flicker.

The fix is simple and matches a recording-studio mental model: when a
pass is in live mode (mirror or recording), mute existing strips on
that pass. Restore them on Stop Mirror (no recording happened — the
take resumes). Discard the memory on Stop Recording (the new strip is
canonical; prior strips stay muted as drafts).

Strip identity is matched by the substring of the pass name in the
strip's action name (e.g. "BodyPass", "FacePass"). Multiple takes
(e.g. PP_V2_BodyPass.001) all match.
"""

import bpy

from ..core.rig import RIG_OBJECT_NAME

# pass_name_substring -> list of (track_idx, strip_idx) muted at last Start
_MUTED_BY_PASS: "dict[str, list[tuple[int, int]]]" = {}


def mute_pass_strips(rig, pass_name):
    """Mute existing NLA strips on `rig` whose action name contains `pass_name`.

    Records what was muted under the pass key so a later restore_pass_strips
    can flip them back. Already-muted strips are NOT recorded — the user's
    own mutes survive the round trip.
    """
    muted = []
    if rig is not None and rig.animation_data is not None:
        for ti, track in enumerate(rig.animation_data.nla_tracks):
            for si, strip in enumerate(track.strips):
                if (strip.action and pass_name in strip.action.name
                        and not strip.mute):
                    strip.mute = True
                    muted.append((ti, si))
    _MUTED_BY_PASS[pass_name] = muted
    return muted


def restore_pass_strips(rig, pass_name):
    """Unmute strips that mute_pass_strips muted under this pass key."""
    muted = _MUTED_BY_PASS.pop(pass_name, [])
    if rig is None or rig.animation_data is None:
        return
    for ti, si in muted:
        try:
            rig.animation_data.nla_tracks[ti].strips[si].mute = False
        except (IndexError, AttributeError):
            # Strip may have been removed since we muted it — drop silently.
            pass


def discard_pass_mutes(pass_name):
    """Drop the muted-strips memory without unmuting.

    Called from Stop Recording: the just-pushed new strip is canonical,
    and the previously-muted strips stay muted as drafts.
    """
    _MUTED_BY_PASS.pop(pass_name, None)


def body_pass_baked():
    """Return True if a PP_V2_BodyPass NLA strip exists on the rig.

    The gate for entering Pass 2 (face): the body pass must be baked
    so the spine/neck/arm bones come from the NLA strip rather than a
    live body mirror. Pass 1 owns body + arms + hands together post
    two-pass refactor — no separate hand-pass gate.
    """
    rig = bpy.data.objects.get(RIG_OBJECT_NAME)
    if rig is None or rig.animation_data is None:
        return False
    for track in rig.animation_data.nla_tracks:
        for strip in track.strips:
            if strip.action and "BodyPass" in strip.action.name:
                return True
    return False
