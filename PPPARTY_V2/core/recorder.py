"""PPParty V2 — body and face pass recorders.

Captures live mirror data into Blender Actions by inserting keyframes
on each pose update. Each tick of the receiver that lands a fresh pose
triggers a keyframe_insert at the recorder's current frame.

Two-pass architecture (2026-04-29 refactor):
    Pass 1 (BodyRecorder)  — spine, legs, arms, fingers. 41 bones.
    Pass 2 (FaceRecorder)  — head bone only.

Output flow per pass:
    Start Recording -> create Action ('PP_V2_BodyPass' / 'PP_V2_FacePass',
        with .001, .002, ... on collision), assign to rig.animation_data,
        fake-user it.
    Each tick -> keyframe_insert per driven bone at the recording frame.
    Stop Recording -> push the Action down to a new NLA track as a
        strip, clear the active action slot. Strips from each pass touch
        disjoint fcurves and stack cleanly in the NLA editor per
        V2_DESIGN.md §5.

Auto-pushing to NLA also clears the active action so live mirror
writes don't fight F-curve evaluation tick-by-tick. To play a take
back, stop the mirror and hit Spacebar — the NLA strip drives the rig.
"""

import statistics

import bpy

from .rig import RIG_OBJECT_NAME


# Names of the bones Pass 1 keyframes. Two-pass refactor 2026-04-29:
# Pass 1 owns the full body — spine, legs, arms, palms, AND fingers —
# because wrist orientation must match finger pose at the same instant
# (V2_DESIGN.md §5.1). Same MP image drives the arm chain AND the hand
# blocks; capturing them on the same fcurves keeps them coherent.
# Head is the only bone Pass 1 does NOT keyframe — Pass 2 (face) owns
# it. Disjoint pass ownership means body and face NLA strips stack
# cleanly without fighting fcurves.
# The body sender still DRIVES head live during body mirror (kid sees
# feedback) but does not capture it as keyframes.
# 7 spine/legs + 4 feet/toes + 2 shoulders + 4 arms + 8 palms + 30 phalanges = 55 bones per Pass 1.
_BODY_DRIVEN_BONES = (
    # Spine + legs.
    "pelvis", "chest", "neck",
    "upper_leg.R", "lower_leg.R",
    "upper_leg.L", "lower_leg.L",
    # Feet + toes (foot's own triangle drive — captures pointing/flexing).
    "foot.L", "toe.L",
    "foot.R", "toe.R",
    # Shoulders (collarbones — captures shrug).
    "shoulder.L", "shoulder.R",
    # Arms.
    "upper_arm.L", "lower_arm.L",
    "upper_arm.R", "lower_arm.R",
    # Palms (metacarpals) — 4 per hand.
    "palm.01.L", "palm.02.L", "palm.03.L", "palm.04.L",
    "palm.01.R", "palm.02.R", "palm.03.R", "palm.04.R",
    # Fingers — 15 phalanges per hand × 2.
    "thumb.01.L", "thumb.02.L", "thumb.03.L",
    "f_index.01.L", "f_index.02.L", "f_index.03.L",
    "f_middle.01.L", "f_middle.02.L", "f_middle.03.L",
    "f_ring.01.L", "f_ring.02.L", "f_ring.03.L",
    "f_pinky.01.L", "f_pinky.02.L", "f_pinky.03.L",
    "thumb.01.R", "thumb.02.R", "thumb.03.R",
    "f_index.01.R", "f_index.02.R", "f_index.03.R",
    "f_middle.01.R", "f_middle.02.R", "f_middle.03.R",
    "f_ring.01.R", "f_ring.02.R", "f_ring.03.R",
    "f_pinky.01.R", "f_pinky.02.R", "f_pinky.03.R",
)

# Data paths to keyframe per bone. We only key rotation for body
# bones (and head — but head is owned by Pass 2):
#   - location: chain anchoring resolves head positions from
#     parent.matrix every tick, so pose_bone.location stays at rest.
#     No reason to bake redundant location keyframes.
#   - scale: 1.0 for body bones (rotation-only). Constant.
#   - rotation_quaternion: this is the pose. The thing.
# Hand bones (palms + phalanges) get the extra `scale` channel keyed
# because the receiver dynamically scales them to MP segment lengths
# so the puppet's hand sizes to the kid's actual hand. Without
# keyframing scale, recorded clips snap back to rest length on NLA
# playback and the hand looks 2-3× too long again.
_KEYFRAMED_PATHS = ("rotation_quaternion",)
_HAND_KEYFRAMED_PATHS = ("rotation_quaternion", "scale")

_HAND_BONE_NAMES = frozenset((
    "palm.01.L", "palm.02.L", "palm.03.L", "palm.04.L",
    "palm.01.R", "palm.02.R", "palm.03.R", "palm.04.R",
    "thumb.01.L", "thumb.02.L", "thumb.03.L",
    "f_index.01.L", "f_index.02.L", "f_index.03.L",
    "f_middle.01.L", "f_middle.02.L", "f_middle.03.L",
    "f_ring.01.L", "f_ring.02.L", "f_ring.03.L",
    "f_pinky.01.L", "f_pinky.02.L", "f_pinky.03.L",
    "thumb.01.R", "thumb.02.R", "thumb.03.R",
    "f_index.01.R", "f_index.02.R", "f_index.03.R",
    "f_middle.01.R", "f_middle.02.R", "f_middle.03.R",
    "f_ring.01.R", "f_ring.02.R", "f_ring.03.R",
    "f_pinky.01.R", "f_pinky.02.R", "f_pinky.03.R",
))


_ACTION_BASE_NAME = "PP_V2_BodyPass"


def _align_strip_to_recording(strip, frame_start, frame_end):
    """Force an NLA strip's NLA-timeline range to match the recording range.

    Workaround for a Blender 5.2 alpha bug: NLATracks.strips.new(name, start,
    action) places the strip with a frame_start that diverges from
    action_frame_start when the action's first keyframe is far from frame 1.
    Symptom: recorded keyframes 279–689 ended up as a strip from frame -9 to
    401, so playback grabbed head poses from the wrong moment of the recording
    and the rig collapsed.

    Order matters: Blender enforces frame_start < frame_end during assignment.
    We push the upper bound first to make room for the new lower bound.
    """
    # Ensure end is high enough to allow setting start to its target.
    if frame_start >= strip.frame_end:
        strip.frame_end = frame_end
        strip.frame_start = frame_start
    else:
        strip.frame_start = frame_start
        strip.frame_end = frame_end
    # Keep action playback range aligned with the keyframes actually written.
    strip.action_frame_start = frame_start
    strip.action_frame_end = frame_end


def _next_action_name(base=_ACTION_BASE_NAME):
    """Return a fresh action name. Versions like 'PP_V2_BodyPass.001' on collision."""
    if base not in bpy.data.actions:
        return base
    i = 1
    while True:
        candidate = f"{base}.{i:03d}"
        if candidate not in bpy.data.actions:
            return candidate
        i += 1


class BodyRecorder:
    """Captures body-mirror data into a Blender Action.

    Lifecycle:
        rec = get_recorder()
        rec.start_recording(scene)        # called by Start Recording op
        ...                               # receiver._tick calls rec.keyframe_now()
        rec.stop_recording(scene)         # called by Stop Recording op

    Only one recording is active at a time. `is_recording` reflects state.
    """

    def __init__(self):
        self._recording = False
        self._frame = 1
        self._frame_start = 1
        self._action = None
        self._action_name = _ACTION_BASE_NAME
        # Per-bone log of MP-derived segment lengths for end-of-take
        # median calibration on hand bones. Populated by the receiver
        # via log_hand_segment(); collapsed to a single scale keyframe
        # per bone in stop_recording. See _apply_median_hand_scale.
        self._hand_seg_lengths = {}

    @property
    def is_recording(self):
        return self._recording

    @property
    def current_frame(self):
        return self._frame

    @property
    def frame_count(self):
        return max(0, self._frame - self._frame_start)

    @property
    def action_name(self):
        return self._action_name

    def start_recording(self, scene):
        """Begin recording. Returns (ok, message)."""
        if self._recording:
            return False, "already recording"
        rig = bpy.data.objects.get(RIG_OBJECT_NAME)
        if rig is None:
            return False, f"rig '{RIG_OBJECT_NAME}' not found in scene"

        self._action_name = _next_action_name()
        action = bpy.data.actions.new(self._action_name)
        # Fake-user the action immediately so an interrupted recording
        # (Blender crash, addon reload, etc.) doesn't lose the in-flight
        # take. We're paranoid; this is cheap.
        action.use_fake_user = True
        if rig.animation_data is None:
            rig.animation_data_create()
        rig.animation_data.action = action
        self._action = action

        # Frame counter starts at the current scene frame (or scene_start,
        # whichever is later — protects against timeline-rewound state).
        self._frame_start = max(scene.frame_start, scene.frame_current)
        self._frame = self._frame_start
        scene.frame_current = self._frame

        # Fresh take = fresh segment-length log.
        self._hand_seg_lengths = {}

        self._recording = True
        return True, f"recording '{self._action_name}' from frame {self._frame_start}"

    def stop_recording(self, scene):
        """End recording. Push the Action down to NLA as a strip.

        The captured Action is moved onto a new NLA track on the rig
        (visible in the NLA editor) and the active action slot is
        cleared so live mirror writes don't fight F-curve evaluation.
        To play the take back, the kid stops the mirror and hits play
        — the NLA strip drives the rig cleanly.
        """
        if not self._recording:
            return False, "not recording"
        self._recording = False

        # Stretch the scene end frame to cover the recording.
        last_frame = max(self._frame - 1, self._frame_start)
        scene.frame_end = max(scene.frame_end, last_frame)

        rig = bpy.data.objects.get(RIG_OBJECT_NAME)
        action = self._action
        self._action = None

        # Median-length hand calibration. Collapse each hand bone's
        # per-frame scale fcurves into one constant value (median of
        # MP-derived segment lengths over the take) so finger sizes
        # stop pulsing on NLA playback. Must run while `action` is
        # still the rig's active action so keyframe_insert lands here.
        if action is not None and rig is not None:
            self._apply_median_hand_scale(rig, action)

        pushed_to_nla = False
        if (rig is not None and rig.animation_data is not None
                and action is not None):
            adt = rig.animation_data
            track = adt.nla_tracks.new()
            track.name = f"PP_V2 — {action.name}"
            new_strip = track.strips.new(action.name, self._frame_start, action)
            _align_strip_to_recording(new_strip, self._frame_start, last_frame)
            adt.action = None
            pushed_to_nla = True

        frames = last_frame - self._frame_start + 1
        if action is not None:
            destination = "NLA strip" if pushed_to_nla else "Action"
            return True, (
                f"saved {frames} frames as {destination} '{action.name}' "
                f"(frames {self._frame_start}–{last_frame})"
            )
        return True, "stopped"

    def log_hand_segment(self, bone_name, seg_length):
        """Record a hand bone's MP-derived segment length for this tick.

        Called from the receiver right after _drive_bone_segment writes
        the live scale. We accumulate per-bone lists during the take and
        collapse them into one median-derived scale at stop_recording.

        Per FREEMOCAP_RESEARCH.md §2.1: MP segment lengths jitter even
        when underlying landmark positions are One-Euro filtered, because
        the LENGTH is a derived signal. Median over the take is robust
        against MP guess-frames (hand-on-face, occlusion) where mean
        would average outliers in.
        """
        if not self._recording:
            return
        self._hand_seg_lengths.setdefault(bone_name, []).append(seg_length)

    def _apply_median_hand_scale(self, rig, action):
        """Collapse per-frame hand scale fcurves into one constant value.

        For each hand bone we logged segment lengths for: pick a
        constant scale via a per-bone-class estimator, remove the
        per-frame scale fcurves the recorder baked in keyframe_now,
        write the constant scale, and insert one scale keyframe at
        frame_start. A single-key fcurve evaluates to a constant on
        the NLA strip — finger size stays stable across the entire
        take.

        Why two estimators, not one (Day 8d split):

        - **Finger proximal + middle phalanges (f_*.01, f_*.02):** use
          90th-percentile length. These bones systematically
          foreshorten in MP's projected `hand_world_landmarks` —
          fingers rarely point straight at the camera, so the
          distribution skews short. The upper-tail estimator pulls
          calibrated length toward the "fully extended perpendicular
          to camera" anatomical length. Day 8b-with-median had
          .01s landing at 53–72% of rest; Day 8c-with-percentile
          moved them to 69–95%.

        - **Palms, thumbs, fingertips (.03):** use median. These
          bones have projected lengths near anatomical length even
          across mixed poses (palms because their landmarks are
          stable; tips because the segment is short and visibly
          tip-on). For these, the percentile sampled the noise tail
          instead of the truth — Day 8c-with-percentile blew tips
          out to 128–153% of rest, palms to 136–156%. Median is the
          right central tendency here.

        General principle: the right estimator depends on whether
        the projected-length distribution is biased (use upper-tail)
        or noise-centered (use median). Hand bones split cleanly into
        these two regimes by name pattern.

        Live mirror is unaffected: _drive_bone_segment still writes
        scale.y per tick, so the kid still sees their hand sized to
        their actual hand during recording. Only the bake is collapsed.

        Blender 5.2 (Slotted Actions) note: actions no longer expose a
        top-level `action.fcurves`. Real fcurve storage lives at
        `action.layers[i].strips[j].channelbags[k].fcurves`. We iterate
        every channelbag in every keyframe strip — data_path is unique
        per (bone, channel), so we won't touch anything we shouldn't.
        Verified live 2026-04-30 against an existing PP_V2_BodyPass
        action: 270-key scale fcurves with 0.53–1.00 range collapsed
        cleanly to a single 0.74 keyframe.
        """
        for bone_name, lengths in self._hand_seg_lengths.items():
            if not lengths:
                continue
            pb = rig.pose.bones.get(bone_name)
            if pb is None or pb.bone.length < 1e-6:
                continue
            # Per-class estimator split — see docstring.
            use_percentile = (
                bone_name.startswith("f_")
                and (".01." in bone_name or ".02." in bone_name)
            )
            if use_percentile:
                sorted_lengths = sorted(lengths)
                calibrated_len = sorted_lengths[
                    int(0.9 * (len(sorted_lengths) - 1))
                ]
            else:
                calibrated_len = statistics.median(lengths)
            target_scale_y = calibrated_len / pb.bone.length

            # Drop the per-frame scale fcurves (x, y, z) for this bone.
            data_path = f'pose.bones["{bone_name}"].scale'
            for layer in action.layers:
                for strip in layer.strips:
                    if strip.type != "KEYFRAME":
                        continue
                    for bag in strip.channelbags:
                        to_remove = [fc for fc in bag.fcurves
                                     if fc.data_path == data_path]
                        for fc in to_remove:
                            bag.fcurves.remove(fc)

            # Write the median scale and bake one keyframe at the
            # take's start frame. The keyframe insert recreates the
            # 3 fcurves with a single key each.
            pb.scale.x = 1.0
            pb.scale.y = target_scale_y
            pb.scale.z = 1.0
            pb.keyframe_insert(data_path="scale", frame=self._frame_start)

    def keyframe_now(self, rig):
        """Insert keyframes for all driven bones at the current recording frame.

        Called from receiver._tick after apply_landmarks_to_rig. The
        live driver has just written pose_bone.matrix; we capture that
        pose into the active action's F-curves at our recording frame,
        then advance scene.frame_current and the recording counter so
        the next tick lands on the next frame.
        """
        if not self._recording or rig is None:
            return
        for bone_name in _BODY_DRIVEN_BONES:
            pb = rig.pose.bones.get(bone_name)
            if pb is None:
                continue
            paths = (_HAND_KEYFRAMED_PATHS
                     if bone_name in _HAND_BONE_NAMES else _KEYFRAMED_PATHS)
            for path in paths:
                pb.keyframe_insert(data_path=path, frame=self._frame)
        bpy.context.scene.frame_current = self._frame
        self._frame += 1


# ---------------------------------------------------------------------------
# Body recorder singleton
# ---------------------------------------------------------------------------

_recorder = None


def get_recorder():
    """Return the module-level BodyRecorder, creating it on first call."""
    global _recorder
    if _recorder is None:
        _recorder = BodyRecorder()
    return _recorder


# ---------------------------------------------------------------------------
# HandRecorder retired in two-pass refactor (2026-04-29)
# ---------------------------------------------------------------------------
# Arms + fingers folded into _BODY_DRIVEN_BONES above; Pass 1 captures
# them in the same Action as the spine + legs. The standalone
# HandRecorder + PP_V2_HandPass NLA track are gone — see V2_DESIGN.md
# §5 and HANDOFF.md for the rationale.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# FaceRecorder — Pass 2: head bone only.
# ---------------------------------------------------------------------------

# Only the head bone for now. Summer calibration can add jaw and blend shapes.
_FACE_DRIVEN_BONES = ("head",)

_FACE_ACTION_BASE_NAME = "PP_V2_FacePass"


class FaceRecorder:
    """Captures face-pass data (head rotation) into a Blender Action.

    Same lifecycle as BodyRecorder. On Stop, pushes the Action to its
    own NLA track ('PP_V2 — PP_V2_FacePass'). Body and face strips
    stack independently in the NLA editor — disjoint bones (face owns
    head, body owns everything else), so they never fight on fcurves.
    """

    def __init__(self):
        self._recording = False
        self._frame = 1
        self._frame_start = 1
        self._action = None
        self._action_name = _FACE_ACTION_BASE_NAME

    @property
    def is_recording(self):
        return self._recording

    @property
    def current_frame(self):
        return self._frame

    @property
    def frame_count(self):
        return max(0, self._frame - self._frame_start)

    @property
    def action_name(self):
        return self._action_name

    def _next_action_name(self):
        base = _FACE_ACTION_BASE_NAME
        if base not in bpy.data.actions:
            return base
        i = 1
        while True:
            candidate = f"{base}.{i:03d}"
            if candidate not in bpy.data.actions:
                return candidate
            i += 1

    def start_recording(self, scene):
        """Begin recording face pass. Returns (ok, message)."""
        if self._recording:
            return False, "already recording"
        rig = bpy.data.objects.get(RIG_OBJECT_NAME)
        if rig is None:
            return False, f"rig '{RIG_OBJECT_NAME}' not found"

        self._action_name = self._next_action_name()
        action = bpy.data.actions.new(self._action_name)
        action.use_fake_user = True
        if rig.animation_data is None:
            rig.animation_data_create()
        rig.animation_data.action = action
        self._action = action

        self._frame_start = max(scene.frame_start, scene.frame_current)
        self._frame = self._frame_start
        scene.frame_current = self._frame

        self._recording = True
        return True, f"recording '{self._action_name}' from frame {self._frame_start}"

    def stop_recording(self, scene):
        """End recording. Push Action to NLA as its own strip."""
        if not self._recording:
            return False, "not recording"
        self._recording = False

        last_frame = max(self._frame - 1, self._frame_start)
        scene.frame_end = max(scene.frame_end, last_frame)

        rig = bpy.data.objects.get(RIG_OBJECT_NAME)
        action = self._action
        self._action = None

        pushed_to_nla = False
        if (rig is not None and rig.animation_data is not None
                and action is not None):
            adt = rig.animation_data
            track = adt.nla_tracks.new()
            track.name = f"PP_V2 — {action.name}"
            new_strip = track.strips.new(action.name, self._frame_start, action)
            _align_strip_to_recording(new_strip, self._frame_start, last_frame)
            adt.action = None
            pushed_to_nla = True

        frames = last_frame - self._frame_start + 1
        if action is not None:
            destination = "NLA strip" if pushed_to_nla else "Action"
            return True, (
                f"saved {frames} frames as {destination} '{action.name}' "
                f"(frames {self._frame_start}–{last_frame})"
            )
        return True, "stopped"

    def keyframe_now(self, rig):
        """Insert keyframes for head bone at the current recording frame."""
        if not self._recording or rig is None:
            return
        for bone_name in _FACE_DRIVEN_BONES:
            pb = rig.pose.bones.get(bone_name)
            if pb is None:
                continue
            pb.keyframe_insert(data_path="rotation_quaternion", frame=self._frame)
        bpy.context.scene.frame_current = self._frame
        self._frame += 1


# ---------------------------------------------------------------------------
# Face recorder singleton
# ---------------------------------------------------------------------------

_face_recorder = None


def get_face_recorder():
    """Return the module-level FaceRecorder, creating it on first call."""
    global _face_recorder
    if _face_recorder is None:
        _face_recorder = FaceRecorder()
    return _face_recorder
