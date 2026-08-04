"""PPParty V2 — UDP receiver and bone driver.

Listens for PPV2 body packets on a UDP port (default 11111), parses
the body+hands payload, and writes pose-bone matrices on the V2 rig
at ~60 Hz via a Blender timer. Pass 1 captures the full body — spine,
legs, arms, AND fingers — so the body packet carries 33 pose landmarks
and 0/1/2 hand blocks together (two-pass refactor 2026-04-29).

The work is split across two threads:

  Background thread (`_listen`)
      Owns the UDP socket. Pulls packets in a tight `recvfrom` loop,
      parses them, and parks the latest landmark frame in
      `self._latest` (lock-protected). Never touches Blender data.

  Main thread (`_tick`, registered with `bpy.app.timers`)
      Reads `self._latest`, applies it to the rig by computing each
      pose bone's matrix from MediaPipe landmark segments. All bpy
      access happens here.

The split keeps Blender's API access on the main thread (Blender's
data API is not thread-safe) while letting UDP recv block freely.
"""

import socket
import struct
import threading

import bpy
from mathutils import Matrix, Vector

from .recorder import get_recorder, get_face_recorder
from .rig import RIG_OBJECT_NAME


# ---------------------------------------------------------------------------
# Packet format — must match mediapipe_sender.py
# ---------------------------------------------------------------------------

MAGIC = b'PPV2'
VERSION = 0x01
PACKET_TYPE_BODY = 0x01      # Pass 1 unified body + 0..2 hand blocks
PACKET_TYPE_FACE = 0x03      # Pass 2 face packet (face_sender.py)
N_BODY_LANDMARKS = 33
N_HAND_LANDMARKS = 21
_FACE_MATRIX_FLOATS = 16   # 4×4 facial transform matrix, row-major

_HEADER_SIZE = 7
_FLOATS_PER_BODY_LM = 4   # x, y, z, visibility
_BODY_BLOCK_BYTES = N_BODY_LANDMARKS * _FLOATS_PER_BODY_LM * 4   # 528
_HAND_BLOCK_BYTES = 1 + N_HAND_LANDMARKS * 3 * 4                  # 253


def parse_body_packet(data):
    """Parse a PPV2 body packet (33 pose landmarks + 0..2 hand blocks).

    Layout (max 1041 bytes):
        7-byte header (magic, version, type=0x01, n_hands)
        528-byte body block — 33 landmarks × (x, y, z, visibility)
            in MP pose_world_landmarks coords.
        per hand (n_hands times): 1 byte handedness + 21 × 3 floats in
            hand_world_landmarks coords (hand-local meters).

    Returns (landmarks, hands) where:
        landmarks: list of 33 (x, y, z, visibility) tuples
        hands:     list of (handedness_str, lms) tuples (0–2 of them)

    Returns None if the packet is malformed.
    """
    if len(data) < _HEADER_SIZE or data[:4] != MAGIC:
        return None
    version, packet_type, n_hands = struct.unpack('BBB', data[4:7])
    if version != VERSION or packet_type != PACKET_TYPE_BODY:
        return None
    if n_hands > 2:
        return None
    expected = _HEADER_SIZE + _BODY_BLOCK_BYTES + n_hands * _HAND_BLOCK_BYTES
    if len(data) < expected:
        return None

    # Body block — always present.
    body_floats = struct.unpack_from(
        f'<{N_BODY_LANDMARKS * 4}f', data, _HEADER_SIZE,
    )
    landmarks = [
        (body_floats[i * 4], body_floats[i * 4 + 1],
         body_floats[i * 4 + 2], body_floats[i * 4 + 3])
        for i in range(N_BODY_LANDMARKS)
    ]

    # Hand blocks.
    hands = []
    offset = _HEADER_SIZE + _BODY_BLOCK_BYTES
    for _ in range(n_hands):
        h_byte = data[offset]
        handedness_str = 'Left' if h_byte == 0x00 else 'Right'
        offset += 1
        n_floats = N_HAND_LANDMARKS * 3
        floats = struct.unpack_from(f'<{n_floats}f', data, offset)
        offset += n_floats * 4
        lms = [
            (floats[i * 3], floats[i * 3 + 1], floats[i * 3 + 2])
            for i in range(N_HAND_LANDMARKS)
        ]
        hands.append((handedness_str, lms))
    return (landmarks, hands)


# ---------------------------------------------------------------------------
# MediaPipe -> Blender axis remap
# ---------------------------------------------------------------------------
#
# MediaPipe pose_world_landmarks coordinate system:
#     X — right (positive)
#     Y — DOWN (positive)
#     Z — toward camera (negative = closer)
#
# Blender world coordinate system (puppet faces -Y by default):
#     X — right (positive)
#     Y — into the scene (positive); -Y = toward viewer
#     Z — up (positive)
#
# Remap:
#     blender.x =  mp.x       (lateral, same axis)
#     blender.y =  mp.z       (depth: MP -Z toward cam ~ Blender -Y toward viewer)
#     blender.z = -mp.y       (vertical: MP +Y down ~ Blender +Z up — negate)
#
# Verified against V1's `osc_receiver.py:_mp_to_puppet` (alpha.55).

def mp_to_blender(mp_xyz):
    """Translate a MediaPipe world XYZ into Blender world XYZ."""
    x, y, z = mp_xyz
    return Vector((x, z, -y))


# ---------------------------------------------------------------------------
# Bone driver — pose_bone.matrix from landmark segments
# ---------------------------------------------------------------------------
#
# MediaPipe Pose landmark indices we use. Full list:
#   https://developers.google.com/mediapipe/solutions/vision/pose_landmarker

NOSE = 0
L_SHOULDER, R_SHOULDER = 11, 12
L_ELBOW,    R_ELBOW    = 13, 14
L_WRIST,    R_WRIST    = 15, 16
L_HIP,      R_HIP      = 23, 24
L_KNEE,     R_KNEE     = 25, 26
L_ANKLE,    R_ANKLE    = 27, 28
L_HEEL,     R_HEEL     = 29, 30
L_FOOT_IDX, R_FOOT_IDX = 31, 32


# MP Hand landmark indices:
#   0: wrist
#   Thumb:  1=cmc, 2=mcp, 3=ip, 4=tip
#   Index:  5=mcp, 6=pip, 7=dip, 8=tip
#   Middle: 9=mcp, 10=pip, 11=dip, 12=tip
#   Ring:  13=mcp, 14=pip, 15=dip, 16=tip
#   Pinky: 17=mcp, 18=pip, 19=dip, 20=tip
#
# Maps (bone_suffix, head_lm_idx, tail_lm_idx). bone_suffix is the
# part after the side dot ("thumb.01" → "thumb.01.L" or ".R" depending
# on MP handedness).
#
# Palms first so they're written before any phalanx that depends on
# the palm's CURRENT pose (parent.matrix lookup in _drive_bone_segment).
# Each palm spans wrist (lm 0) → that finger's MCP knuckle. Phalanges
# then continue from the palm's tail. This matches Rigify's hand
# convention so fingers pivot at the MCP, not at the wrist.
_HAND_BONE_SEGMENTS = (
    # Palms (metacarpals) — wrist → MCP per finger.
    ("palm.01",     0,  5),   # wrist → index MCP
    ("palm.02",     0,  9),   # wrist → middle MCP
    ("palm.03",     0, 13),   # wrist → ring MCP
    ("palm.04",     0, 17),   # wrist → pinky MCP
    # Thumb (parented to palm.01 in the rig).
    ("thumb.01",    1,  2),   # cmc  → mcp
    ("thumb.02",    2,  3),   # mcp  → ip
    ("thumb.03",    3,  4),   # ip   → tip
    # Index (parented to palm.01).
    ("f_index.01",  5,  6),   # mcp  → pip
    ("f_index.02",  6,  7),
    ("f_index.03",  7,  8),
    # Middle (parented to palm.02).
    ("f_middle.01", 9,  10),
    ("f_middle.02", 10, 11),
    ("f_middle.03", 11, 12),
    # Ring (parented to palm.03).
    ("f_ring.01",   13, 14),
    ("f_ring.02",   14, 15),
    ("f_ring.03",   15, 16),
    # Pinky (parented to palm.04).
    ("f_pinky.01",  17, 18),
    ("f_pinky.02",  18, 19),
    ("f_pinky.03",  19, 20),
)


# Mirror convention: MediaPipe's "Left" landmarks (subject's anatomical
# left) drive the puppet's R-side bone, so the puppet mirrors the kid
# the way a real mirror would. Same convention V1 uses (alpha.55).


def _drive_bone_segment(pose_bone, head_world, tail_world,
                        scale_to_segment=False, side_ref=None):
    """Rotate the bone to align its Y-axis with (tail_world - head_world).

    Position comes from the bone's REST relationship to its parent,
    transformed by the parent's CURRENT pose. This handles three
    cases uniformly:

      - Root bone (pelvis, no parent): head stays at its rest
        head_local. The puppet is anchored at world origin and won't
        drift if MP's hip estimate wobbles.
      - Connected children (spine: chest, neck, head): rest_head
        equals parent's rest_tail, so the formula resolves to
        "parent's posed tail" — clean FK chain.
      - Non-connected children (legs branching from pelvis, arms
        branching from chest): rest_head is OFFSET from parent's
        rest_tail. The formula preserves that offset, so legs come
        out of the hips and arms out of the shoulders, even after
        parent rotates.

    Bone lengths default to REST so the puppet's body/arm proportions
    stay stable regardless of the performer's proportions or MP's
    noisier depth axis.

    Pass `scale_to_segment=True` to stretch the bone along its Y axis
    so the tail lands at `tail_world` instead of REST_LENGTH * direction
    from the head. Used for hand bones (thumb/finger chains) so the
    puppet's hand is sized to MP's hand instead of forcing rest-length
    bones into a chain that's 2-3× too long, which makes the thumb
    visibly stick out way past the rest of the hand. Chained children
    (connected) follow the scaled tail correctly via parent.matrix.

    Pass `side_ref` (a Vector) to fix near-vertical bones. The default
    `to_track_quat('Y', 'Z')` path is unstable when the bone direction
    is parallel to world +Z — Blender's fallback picks an arbitrary
    perpendicular axis, and frame-to-frame MP noise causes that axis
    to flip by 90° (visible as the upper body twisting back and forth).
    With side_ref provided, we project it perpendicular to the bone
    direction and use it as the bone's local +X axis explicitly, then
    derive bone-Z = X × Y. Pass `hip_lateral = (L_HIP - R_HIP)` for
    spine + legs + arms — it's stable AND tracks body twist (so the
    rig still rotates correctly when the kid turns sideways).

    `head_world` is used only to compute the target direction; the
    bone's actual head position is set by parenting.
    """
    direction = tail_world - head_world
    seg_length = direction.length
    if seg_length < 1e-6:
        return  # degenerate segment; skip this frame
    target_y = direction.normalized()

    if side_ref is not None:
        # Project side_ref onto the plane perpendicular to bone Y so it
        # becomes a valid bone-X direction.
        bone_x_proj = side_ref - target_y * side_ref.dot(target_y)
        if bone_x_proj.length > 1e-6:
            bone_x = bone_x_proj.normalized()
            bone_z = bone_x.cross(target_y).normalized()
            rot = Matrix((
                (bone_x.x, target_y.x, bone_z.x),
                (bone_x.y, target_y.y, bone_z.y),
                (bone_x.z, target_y.z, bone_z.z),
            ))
            quat = rot.to_quaternion()
        else:
            # side_ref is parallel to bone direction — degenerate.
            # Fall back to the default path; it'll still flicker but
            # there's nothing better we can do without a usable ref.
            quat = target_y.to_track_quat('Y', 'Z')
    else:
        quat = target_y.to_track_quat('Y', 'Z')

    if pose_bone.parent is not None:
        parent = pose_bone.parent
        # Express this bone's rest head in the parent's REST local frame...
        rest_head_in_parent_local = (
            parent.bone.matrix_local.inverted() @ pose_bone.bone.head_local
        )
        # ...then project it through the parent's CURRENT pose.
        head_armature = parent.matrix @ rest_head_in_parent_local
    else:
        # CONSTANT-STANCE (v2.0.2 explicit design choice):
        # The parent-less branch lands the pelvis at world origin
        # via rest_head_local. The puppet does NOT translate when
        # the kid walks. This is intentional puppet-show pedagogy —
        # see WORLD_SPACE_ANCHORING_RESEARCH.md for rationale and
        # candidate alternatives if revisited in V2.x. Performer
        # translation is captured via upper-body lean (chest /
        # shoulder / arm sway), not pelvis position. Classical
        # marionette stage convention; matches V0/V1 PPParty
        # restriction discipline ("simple inputs, expressive outputs").
        head_armature = pose_bone.bone.head_local.copy()

    # Two-step: set rotation via the matrix (with unit scale), THEN
    # set Y-scale on pose_bone.scale directly. Going through
    # LocRotScale's scale parameter goes through the matrix-basis
    # inverse decomposition and produces wrong basis scales — that
    # was the broken-spaghetti-fingers attempt earlier today.
    # Setting pose_bone.scale.y directly works (verified live: bone
    # length 0.072 → 0.036 with scale.y=0.5).
    pose_bone.matrix = Matrix.LocRotScale(
        head_armature, quat, Vector((1.0, 1.0, 1.0)),
    )
    if scale_to_segment and pose_bone.bone.length > 1e-6:
        pose_bone.scale.y = seg_length / pose_bone.bone.length


def _drive_foot_basis(pose_bone, side_axis, aim_axis, up_axis):
    """Set a pose bone to a full 3-axis orthonormal basis.

    Unlike `_drive_bone_segment` (which only controls the bone's Y axis,
    ignoring roll), this helper sets the entire bone orientation from
    three mutually-perpendicular axis vectors. Needed for feet because
    the foot can ROLL (pronate/supinate) independently of its forward
    direction — a pure aim-only drive would lose that information.

    Convention:
      • aim_axis  → bone's local +Y (Blender bone direction)
      • side_axis → bone's local +X
      • up_axis   → bone's local +Z

    The three axes MUST be unit-length and mutually perpendicular;
    caller is responsible for orthonormalization (typically via
    Gram-Schmidt over a cross-product chain).

    Position comes from the bone's REST relationship to its parent,
    transformed by the parent's CURRENT pose — same pattern as
    `_drive_bone_segment`. Bone length stays at REST (no segment-
    matching scale; foot proportions are visually fixed).
    """
    if pose_bone.parent is not None:
        parent = pose_bone.parent
        rest_head_in_parent_local = (
            parent.bone.matrix_local.inverted() @ pose_bone.bone.head_local
        )
        head_armature = parent.matrix @ rest_head_in_parent_local
    else:
        head_armature = pose_bone.bone.head_local.copy()

    # Build a 3x3 rotation from the basis axes as columns. mathutils.Matrix
    # takes rows, so transpose by constructing row-by-row from the
    # axis components.
    rot_3x3 = Matrix((
        (side_axis.x, aim_axis.x, up_axis.x),
        (side_axis.y, aim_axis.y, up_axis.y),
        (side_axis.z, aim_axis.z, up_axis.z),
    ))
    quat = rot_3x3.to_quaternion()

    pose_bone.matrix = Matrix.LocRotScale(
        head_armature, quat, Vector((1.0, 1.0, 1.0)),
    )


def _try_drive_foot(pb, bl, vis, side_suffix,
                    ankle_idx, heel_idx, foot_idx_idx, side_sign):
    """Drive foot.{side_suffix} + toe.{side_suffix} from MP foot landmarks.

    On visibility failure, resets both bones to rest (basis = identity)
    rather than holding pose. See `apply_landmarks_to_rig` block comment
    for the math recipe and mirror/sign-flip convention.

    `side_sign` is the per-side handedness flip for the LATERAL axis:
    +1 for one foot, -1 for the other. The MP foot triangle has the
    same winding for both feet (cross product gives the same +X-ish
    direction), but anatomical "lateral out" is +X for the puppet-R
    foot and -X for the puppet-L foot — so one side gets flipped.
    """
    foot_pb = pb.get(f"foot.{side_suffix}")
    toe_pb  = pb.get(f"toe.{side_suffix}")
    if foot_pb is None or toe_pb is None:
        return

    # Visibility gate — all three foot landmarks must be confident.
    if (vis[ankle_idx]    < _VIS_THRESHOLD or
            vis[heel_idx]     < _VIS_THRESHOLD or
            vis[foot_idx_idx] < _VIS_THRESHOLD):
        foot_pb.matrix_basis = _IDENTITY_4X4
        toe_pb.matrix_basis  = _IDENTITY_4X4
        return

    ankle      = bl[ankle_idx]
    heel       = bl[heel_idx]
    foot_index = bl[foot_idx_idx]

    aim_vec  = foot_index - ankle
    back_vec = heel - ankle
    if aim_vec.length < 1e-6 or back_vec.length < 1e-6:
        return  # degenerate triangle

    aim  = aim_vec.normalized()
    back = back_vec.normalized()

    # `aim × back` is the NORMAL to the foot's sagittal plane (= lateral
    # direction). It is NOT the dorsal direction — both aim and back have
    # only Y/Z components, so their cross product points purely along X.
    side_vec = aim.cross(back)
    if side_vec.length < 1e-6:
        return  # collinear (foot points straight along leg)

    # IMPORTANT: derive `up` from the UNFLIPPED side, then apply the
    # per-side flip to side AFTERWARDS. If we flipped side first, then
    # `aim × side` would also flip — but the dorsal direction is
    # invariant to which foot it is (always points up for a flat foot).
    # Computing up from side_natural keeps it consistent for both feet.
    side_natural = side_vec.normalized()
    up   = aim.cross(side_natural).normalized()
    side = side_natural * side_sign

    # Foot and toe share the same orientation — toe is parented to foot
    # so it inherits position correctly via parent.matrix. Both bones
    # written explicitly so recording captures keyframes for both.
    _drive_foot_basis(foot_pb, side, aim, up)
    _drive_foot_basis(toe_pb,  side, aim, up)


# MP visibility threshold for legs. Below this a leg's drive is skipped
# and the leg holds its previous pose. Kids sit at desks; MP guesses
# garbage when legs are occluded, and 0.5 is a common MP confidence
# threshold. Arms are NOT gated — see the comment on the arm drive
# below.
_VIS_THRESHOLD = 0.5

# Cached identity matrix for resetting undriven hand bones to rest.
_IDENTITY_4X4 = Matrix.Identity(4)


# Running-minimum spine length, used as the "rest" baseline for the
# shoulder shrug anchor. mid_shoulder rises with the actual shoulders
# during a symmetric shrug, so anchoring the shoulder bone direction
# at mid_shoulder makes the shrug invisible — both endpoints of the
# direction vector rise together. Anchoring at a fixed distance up the
# spine from mid_hip instead lets us SEE the shrug: the spine vector
# (mid_shoulder - mid_hip) lengthens when both shoulders rise, so a
# fixed-length anchor stays at rest height while the actual shoulders
# rise above it. The vector from anchor → L_SHOULDER tilts up.
#
# Tracked as the running min so the baseline self-corrects: if the kid
# starts mid-shrug, the next time they relax their shoulders the spine
# vector shrinks and the baseline updates downward.
_rest_spine_length = None


def _reset_shoulder_calibration():
    """Clear the cached rest spine length so the next session re-calibrates."""
    global _rest_spine_length
    _rest_spine_length = None


def apply_landmarks_to_rig(rig_object, landmarks, hands):
    """Drive the V2 rig's pose bones from a body+hands packet.

    Bones are rotated to track the performer's segment directions;
    bone lengths stay at rest and the chain stays anchored at world
    origin (via the pelvis bone's rest head) so the puppet stays put.

    Order matters:
      1. Spine (top-down) — parents must be written before children.
      2. Shoulders — arm parents; must be written before arms.
      3. Arm chain (so each forearm.matrix is current).
      4. Legs (visibility-gated).
      5. Finger projection through each forearm's CURRENT matrix.

    Same-frame coherence between wrist orientation and finger pose is
    the entire point of capturing pose + hands together — no stale NLA
    wrist mediating between them (per V2_DESIGN.md §5.1).

    Mirror convention: MP-Left → puppet .R bones, MP-Right → .L.
    """
    if rig_object is None or not landmarks:
        return

    # Remap each landmark XYZ to Blender world. Keep visibility as a
    # parallel array — we use it to gate the leg + arm drives.
    bl = [mp_to_blender(lm[:3]) for lm in landmarks]
    vis = [lm[3] for lm in landmarks]

    # Derived spine waypoints. MediaPipe Pose only gives us hips,
    # shoulders, and the nose for the torso/head axis — split each
    # gap evenly so the four spine bones cover the body proportionally.
    mid_hip      = (bl[L_HIP]      + bl[R_HIP])      * 0.5
    mid_shoulder = (bl[L_SHOULDER] + bl[R_SHOULDER]) * 0.5
    mid_chest    = (mid_hip        + mid_shoulder)   * 0.5
    mid_face     = (mid_shoulder   + bl[NOSE])       * 0.5

    # Stable lateral reference for spine + leg + arm bones. These bones
    # are near-vertical when the body is upright, and the default
    # to_track_quat('Y', 'Z') path is unstable in that regime — Blender's
    # fallback picks an arbitrary axis perpendicular to bone-Y when bone-Y
    # is parallel to world +Z, and tiny MP noise flips the choice between
    # frames (visible as 90° twist flickering). Using L_HIP→R_HIP as the
    # bone-X reference anchors the rotation to the body's hip axis: it
    # stays stable when upright AND tracks twist correctly when the kid
    # turns sideways.
    hip_vec = bl[L_HIP] - bl[R_HIP]
    if hip_vec.length > 0.01:
        hip_lateral = hip_vec.normalized()
    else:
        hip_lateral = Vector((1.0, 0.0, 0.0))  # degenerate fallback

    pb = rig_object.pose.bones

    # --- Spine (top-down) ---
    # Pelvis target ignores forward lean: take the X (lateral) and Z (height)
    # from mid_chest but keep the Y (depth) at mid_hip's. So the pelvis bone
    # rotates side-to-side with lateral lean but never tilts forward/back.
    # Without this, both pelvis AND chest tilt forward when the kid leans
    # toward the screen — and since legs are children of pelvis, they
    # inherit the tilt and the whole rig hunches over. Anatomically a real
    # spine bends in the lumbar/thoracic region (= our chest bone) while
    # the pelvis stays roughly vertical, planted to the chair/floor.
    pelvis_target = Vector((mid_chest.x, mid_hip.y, mid_chest.z))
    _drive_bone_segment(pb["pelvis"], mid_hip,      pelvis_target, side_ref=hip_lateral)
    _drive_bone_segment(pb["chest"],  mid_chest,    mid_shoulder,  side_ref=hip_lateral)
    _drive_bone_segment(pb["neck"],   mid_shoulder, mid_face,      side_ref=hip_lateral)
    _drive_bone_segment(pb["head"],   mid_face,     bl[NOSE],      side_ref=hip_lateral)

    # --- Shoulders (mirror) ---
    # Collarbone bridges spine top to the actual lateral shoulder joint.
    # Tilts up on a shrug, points lateral when relaxed. Must run before
    # arms — upper_arm.L/R now parent to shoulder.L/R, so their head
    # positions resolve through the just-written shoulder matrix.
    #
    # Direction reference (head_world): a STABLE point at "rest mid_shoulder
    # height" along the spine, NOT mid_shoulder itself. mid_shoulder rises
    # with both shoulders during a symmetric shrug, so using it as the
    # reference cancels the shrug out of the direction vector. The stable
    # anchor (mid_hip + spine_unit * rest_spine_length) holds steady at
    # the rest shoulder height even when the actual shoulders rise; the
    # vector from anchor → L_SHOULDER then gains a visible upward tilt.
    global _rest_spine_length
    spine_vec = mid_shoulder - mid_hip
    spine_length = spine_vec.length
    if spine_length > 0.1:
        if _rest_spine_length is None or spine_length < _rest_spine_length:
            _rest_spine_length = spine_length
        spine_dir = spine_vec / spine_length
        shoulder_anchor = mid_hip + spine_dir * _rest_spine_length
    else:
        # Degenerate spine (very small or zero): fall back to mid_shoulder.
        shoulder_anchor = mid_shoulder

    _drive_bone_segment(pb["shoulder.R"], shoulder_anchor, bl[L_SHOULDER])
    _drive_bone_segment(pb["shoulder.L"], shoulder_anchor, bl[R_SHOULDER])

    # --- Arms (mirror: MP-Left -> puppet-R, MP-Right -> puppet-L) ---
    # No visibility gate. day5e Pass 1 body mirror drove arms
    # unconditionally and that's what David's used to. MP visibility on
    # arm landmarks routinely sits in the 0.35-0.45 range even when the
    # arm is in clear view, so a 0.5 gate freezes the arms in stale
    # poses for chunks of every session. The One Euro filter on the
    # sender side handles the noise that the gate would otherwise
    # protect against.
    # Arms get hip_lateral as side_ref too — they're near-vertical when
    # hanging at sides (= the rest pose for sitting kids), and would flicker
    # with the default to_track_quat fallback.
    _drive_bone_segment(pb["upper_arm.R"], bl[L_SHOULDER], bl[L_ELBOW], side_ref=hip_lateral)
    _drive_bone_segment(pb["lower_arm.R"], bl[L_ELBOW],    bl[L_WRIST], side_ref=hip_lateral)
    _drive_bone_segment(pb["upper_arm.L"], bl[R_SHOULDER], bl[R_ELBOW], side_ref=hip_lateral)
    _drive_bone_segment(pb["lower_arm.L"], bl[R_ELBOW],    bl[R_WRIST], side_ref=hip_lateral)

    # --- Legs (visibility-gated) ---
    # Kids sit at desks: MediaPipe infers leg landmarks even when it can't
    # see them, and the guesses are garbage (knees above hips, sprawled
    # rig). Only drive a leg when ALL three of its landmarks (hip, knee,
    # ankle) report visibility above the threshold. Below threshold →
    # leg holds whatever pose it was last in (rest pose at start).
    # Legs also use hip_lateral as side_ref — they hang downward in stance,
    # which is parallel to world -Z and causes to_track_quat instability.
    #
    # Legs use INVERTED mirror convention compared to arms/hands. Empirical
    # observation 2026-04-30: MediaPipe's PoseLandmarker swaps L/R labels
    # for lower-body landmarks (lm 23-32) when the camera frame is
    # horizontally pre-flipped (sender does cv2.flip for the kid's mirror
    # preview). Upper-body landmarks (lm 11-16) keep correct anatomy
    # because the face anchors L/R determination; legs lack that anchor
    # and MP falls back to image-position heuristics. So MP-L for legs
    # actually tracks the performer's anatomical-RIGHT leg, and vice
    # versa. The pose body convention (MP-L → puppet .R) becomes a
    # double-flip that produces the wrong visible side. Drive puppet .L
    # from MP-L (and .R from MP-R) for legs to undo the inversion.
    # If MP fixes this in a future model release, swap back.
    if (vis[L_HIP] > _VIS_THRESHOLD and vis[L_KNEE] > _VIS_THRESHOLD
            and vis[L_ANKLE] > _VIS_THRESHOLD):
        _drive_bone_segment(pb["upper_leg.L"], bl[L_HIP],  bl[L_KNEE],  side_ref=hip_lateral)
        _drive_bone_segment(pb["lower_leg.L"], bl[L_KNEE], bl[L_ANKLE], side_ref=hip_lateral)

    if (vis[R_HIP] > _VIS_THRESHOLD and vis[R_KNEE] > _VIS_THRESHOLD
            and vis[R_ANKLE] > _VIS_THRESHOLD):
        _drive_bone_segment(pb["upper_leg.R"], bl[R_HIP],  bl[R_KNEE],  side_ref=hip_lateral)
        _drive_bone_segment(pb["lower_leg.R"], bl[R_KNEE], bl[R_ANKLE], side_ref=hip_lateral)

    # --- Feet (visibility-gated, foot's own triangle) ---
    # Use the foot's three landmarks (ankle, heel, foot_index) — NOT the
    # leg-foot triangle BlendArMocap uses — because in V2's classroom use
    # case the foot is more often visible than the leg (kids sit at desks
    # with feet under but legs occluded). See BLENDARMOCAP_FOOT_MATH.md.
    #
    # Build an orthonormal basis from the foot triangle:
    #   aim  = ankle → foot_index (forward through the foot)
    #   back = ankle → heel (reverse, anchors the up direction)
    #   up   = aim × back (out of the dorsal surface; sign-flipped per side)
    #   side = up × aim (final lateral axis)
    #
    # Mirror convention: MP-Left foot landmarks → puppet R-side bones.
    # Per-side sign flip on `up` because the foot triangle's winding is
    # opposite on the two sides — without it, the foot would visually
    # supinate on one side and pronate on the other.
    #
    # If any foot landmark is below visibility threshold, RESET foot+toe
    # to rest (basis = identity) instead of holding pose. Holding stale
    # foot poses looks tangled when MP loses the foot mid-session — same
    # failure mode as the day6c hand-stale-freeze bug.
    _try_drive_foot(pb, bl, vis, "R", L_ANKLE, L_HEEL, L_FOOT_IDX, side_sign=+1.0)
    _try_drive_foot(pb, bl, vis, "L", R_ANKLE, R_HEEL, R_FOOT_IDX, side_sign=-1.0)

    # --- Fingers ---
    # MP `hand_world_landmarks` are in world-aligned axes (just translated
    # so the hand's geometric center sits near the origin). Live diagnostic
    # 2026-04-29 confirmed: thumb of David's right hand sits at MP +X, left
    # hand thumb at MP -X — opposite signs match anatomical mirroring in a
    # shared world frame. Day5c's projection multiplied by forearm.matrix
    # under the assumption MP coords were hand-local; with world-aligned
    # data, that extra rotation warps fingers into the forearm's tilted
    # frame (the "tangled hand" bug). Fix: subtract the MP wrist landmark
    # to translate the hand to origin, axis-remap with mp_to_blender, and
    # add wrist_world to anchor at the puppet's current wrist. No
    # forearm-orientation multiplication.
    driven_sides = set()
    if hands:
        for handedness_str, lms_raw in hands:
            # Mirror: MP 'Left' → puppet side 'R', MP 'Right' → 'L'.
            puppet_side = 'R' if handedness_str == 'Left' else 'L'
            driven_sides.add(puppet_side)
            forearm_name = f"lower_arm.{puppet_side}"
            forearm = pb.get(forearm_name)
            if forearm is None:
                continue
            wrist_world = forearm.tail

            wx, wy, wz = lms_raw[0]
            projected = [
                wrist_world + mp_to_blender(
                    (lm[0] - wx, lm[1] - wy, lm[2] - wz)
                )
                for lm in lms_raw
            ]

            # Lever A (v2.0.1): stable side_ref for hand bones, derived
            # from this hand's own across-palm vector (pinky_MCP -
            # index_MCP). Eliminates the `to_track_quat('Y','Z')` roll
            # flicker on near-vertical hand bones. The vector self-
            # mirrors per hand — pinky/index swap sides between L and R
            # so the same code produces the anatomically-correct bone-X
            # direction for both hands, no sign flip required (same
            # natural-anatomy emergence that body bones get from
            # `(L_HIP - R_HIP)` for free).
            #
            # Why across-palm instead of palm-normal: palm_normal flips
            # between hands without a sign correction; across-palm IS
            # the bone-X direction we want for finger phalanges (across
            # the knuckles, perpendicular to the finger). Per
            # `HAND_SIDE_REF_RESEARCH.md` §3-4 / `HAND_SIDE_REF_DESIGN.md`.
            #
            # Degenerate case (index/pinky reported colinear with wrist
            # — extreme occlusion / MP failure): _drive_bone_segment's
            # built-in fallback at the side_ref-parallel-to-bone check
            # catches it and falls through to `to_track_quat('Y','Z')`.
            # No extra guard needed here.
            palm_side_ref = projected[17] - projected[5]

            for bone_suffix, head_idx, tail_idx in _HAND_BONE_SEGMENTS:
                bone_name = f"{bone_suffix}.{puppet_side}"
                if bone_name not in pb:
                    continue
                # Hand bones scale to MP segment length so thumb +
                # fingers are sized to the kid's actual hand instead
                # of the rig's rest pose proportions.
                _drive_bone_segment(
                    pb[bone_name], projected[head_idx], projected[tail_idx],
                    scale_to_segment=True,
                    side_ref=palm_side_ref,
                )
                # Log the MP segment length so the recorder can collapse
                # per-frame scale jitter to one median value at stop.
                # No-op when not recording.
                seg_length = (projected[tail_idx] - projected[head_idx]).length
                get_recorder().log_hand_segment(bone_name, seg_length)

    # Reset hand bones on sides that didn't get a hand this frame.
    # Without this, when MP loses a hand the puppet's bones for that
    # side stay frozen in the LAST detected pose — and if MP only saw
    # the hand briefly at a weird angle, the puppet is stuck looking
    # tangled on that side for the rest of the session.
    for side in ('L', 'R'):
        if side not in driven_sides:
            for bone_suffix, _, _ in _HAND_BONE_SEGMENTS:
                hb = pb.get(f"{bone_suffix}.{side}")
                if hb is None:
                    continue
                hb.matrix_basis = _IDENTITY_4X4
                hb.scale = Vector((1.0, 1.0, 1.0))

    # Tag for redraw so the viewport picks up the new pose.
    rig_object.update_tag()


# ---------------------------------------------------------------------------
# BodyReceiver — UDP listener + Blender timer
# ---------------------------------------------------------------------------

class BodyReceiver:
    """Listens for PPV2 body packets and drives the V2 rig.

    Lifecycle:
        recv = get_receiver()
        recv.start()        # opens socket, starts listener thread + Blender timer
        ...                 # packets stream in, the rig animates
        recv.stop()         # tears down cleanly

    There is at most one receiver instance active at a time (see
    `get_receiver`); `start()` is a no-op when already running. The
    receiver looks up the V2 rig by name on each tick, so the rig
    can be (re)built while a session is running without restarting.
    """

    def __init__(self, port=11111, host='127.0.0.1'):
        self._port = port
        self._host = host
        self._sock = None
        self._thread = None
        self._stop_event = threading.Event()
        self._latest = None
        self._lock = threading.Lock()
        self._running = False
        # 60 Hz cap. The sender targets 30 FPS; running the timer at 60
        # Hz keeps Blender's apply step responsive without burning CPU.
        self._tick_interval = 1.0 / 60.0

    @property
    def running(self):
        return self._running

    @property
    def port(self):
        return self._port

    def start(self):
        """Open the UDP socket, start the listener thread, register the timer."""
        if self._running:
            return
        # Fresh session = fresh shoulder shrug calibration. The running-min
        # spine length adapts in seconds, so this keeps a kid's previous
        # session's posture from poisoning the next kid's baseline.
        _reset_shoulder_calibration()
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind((self._host, self._port))
        sock.settimeout(0.1)
        self._sock = sock
        self._stop_event.clear()
        self._latest = None
        self._thread = threading.Thread(
            target=self._listen, name="PPV2BodyReceiver", daemon=True,
        )
        self._thread.start()
        bpy.app.timers.register(
            self._tick,
            first_interval=self._tick_interval,
            persistent=True,
        )
        self._running = True

    def stop(self):
        """Tear down: stop the thread, close the socket, unregister the timer."""
        if not self._running:
            return
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None
        if self._sock is not None:
            try:
                self._sock.close()
            finally:
                self._sock = None
        try:
            bpy.app.timers.unregister(self._tick)
        except ValueError:
            pass  # already unregistered
        self._running = False
        with self._lock:
            self._latest = None

    def _listen(self):
        """Background thread: pull packets, park the latest in self._latest."""
        while not self._stop_event.is_set():
            try:
                data, _addr = self._sock.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                break  # socket closed by stop()
            parsed = parse_body_packet(data)
            if parsed is not None:
                with self._lock:
                    self._latest = parsed

    def _tick(self):
        """Main thread: apply the latest received frame to the rig.

        Returning None unregisters the timer; returning a float
        re-arms it for that many seconds.
        """
        if not self._running:
            return None
        with self._lock:
            parsed = self._latest
            self._latest = None  # consume so we don't re-apply old frames
        if parsed is not None:
            landmarks, hands = parsed
            rig = bpy.data.objects.get(RIG_OBJECT_NAME)
            if rig is not None:
                apply_landmarks_to_rig(rig, landmarks, hands)
                # If a recording is in progress, capture this pose.
                get_recorder().keyframe_now(rig)
        return self._tick_interval


# ---------------------------------------------------------------------------
# Body receiver singleton
# ---------------------------------------------------------------------------

_receiver = None


def get_receiver():
    """Return the module-level BodyReceiver, creating it on first call."""
    global _receiver
    if _receiver is None:
        _receiver = BodyReceiver()
    return _receiver


# ---------------------------------------------------------------------------
# Face packet parser
# ---------------------------------------------------------------------------

def parse_face_packet(data):
    """Parse a PPV2 face packet.

    Returns a flat list of 16 floats (row-major 4×4 facial transform
    matrix) if a face was detected, an empty list if n_faces==0, or
    None if the packet is malformed / wrong type.
    """
    if len(data) < _HEADER_SIZE or data[:4] != MAGIC:
        return None
    version, packet_type, n_faces = struct.unpack('BBB', data[4:7])
    if version != VERSION or packet_type != PACKET_TYPE_FACE:
        return None
    if n_faces == 0:
        return []
    expected = _HEADER_SIZE + _FACE_MATRIX_FLOATS * 4
    if len(data) < expected:
        return None
    floats = struct.unpack_from(f'<{_FACE_MATRIX_FLOATS}f', data, _HEADER_SIZE)
    return list(floats)


# ---------------------------------------------------------------------------
# Face bone driver
# ---------------------------------------------------------------------------
#
# FaceLandmarker's facial_transformation_matrixes uses a right-handed
# coordinate system aligned to the camera:
#     X — right
#     Y — up
#     Z — toward viewer (out of screen)
#
# Blender world:
#     X — right
#     Y — forward (into scene)
#     Z — up
#
# Remap matrix P (FaceLandmarker cam → Blender world):
#     BL_X =  MP_X
#     BL_Y = -MP_Z   (MP Z out of screen → Blender -Y away from scene)
#     BL_Z =  MP_Y   (MP Y up = Blender Z up)
#
# For a rotation matrix R_mp, the remapped matrix is:
#     R_bl = P @ R_mp @ P^T
#
# With P = [[1,0,0],[0,0,-1],[0,1,0]] and P^T = [[1,0,0],[0,0,1],[0,-1,0]]:
#
#     R_bl = [[ r00, -r02,  r01],
#             [-r20,  r22, -r21],
#             [ r10, -r12,  r11]]
#
# Axis mapping may need sign-flip tuning once tested in the classroom.
# Mark the tuning spots with TODO comments so they're easy to find.

def apply_face_to_rig(rig_object, matrix_flat):
    """Drive the head bone from the 4×4 facial transform matrix.

    Writes ``rotation_quaternion`` (the bone's matrix_basis) directly,
    expressing the face rotation in the head bone's REST-LOCAL frame
    via the similarity transform ``M_rest⁻¹ · R_world · M_rest``. This
    is parent-pose-independent: when the body NLA strip moves the
    spine/neck every frame, the head's basis stays stable and the
    parent chain composes the final pose naturally.

    The earlier ``pose_bone.matrix = …`` (armature-space write) version
    back-computed basis against the parent's CURRENT pose, so each
    receiver tick had to re-fight the just-evaluated NLA. Between
    ticks (60 Hz) and frame updates (24 fps) the basis was stale
    against the new parent — visible as a head shake during face
    mirror with body NLA playing back.

    `matrix_flat` is a list of 16 floats (row-major 4×4) or an empty
    list (no face detected — skip this tick).
    """
    if not matrix_flat or rig_object is None:
        return

    # Extract the 3×3 rotation from the top-left of the 4×4 (row-major).
    r00, r01, r02 = matrix_flat[0], matrix_flat[1], matrix_flat[2]
    r10, r11, r12 = matrix_flat[4], matrix_flat[5], matrix_flat[6]
    r20, r21, r22 = matrix_flat[8], matrix_flat[9], matrix_flat[10]

    # Apply coordinate remap. Sender flips the camera frame horizontally
    # (mirror mode) so this matrix is already in the same convention
    # the body pass uses — no extra mirror correction needed here.
    rot_bl = Matrix((
        ( r00, -r02,  r01),
        (-r20,  r22, -r21),
        ( r10, -r12,  r11),
    ))

    head_pb = rig_object.pose.bones.get("head")
    if head_pb is None:
        return

    # Express face rotation in the head bone's rest-local frame.
    rest_3x3 = head_pb.bone.matrix_local.to_3x3()
    basis_3x3 = rest_3x3.inverted() @ rot_bl @ rest_3x3

    if head_pb.rotation_mode != 'QUATERNION':
        head_pb.rotation_mode = 'QUATERNION'
    head_pb.rotation_quaternion = basis_3x3.to_quaternion()
    rig_object.update_tag()


# ---------------------------------------------------------------------------
# FaceReceiver — same architecture as BodyReceiver, port 11113
# ---------------------------------------------------------------------------

class FaceReceiver:
    """Listens for PPV2 face packets and drives the head bone.

    Pass 2 (face): head rotation only, from the FaceLandmarker facial
    transform matrix. Same two-thread architecture as BodyReceiver.
    Port 11113.

    During Pass 2 recording, the body NLA strip plays back so the kid
    sees their full prior performance while they record face. The face
    receiver only writes the head bone rotation — the rest of the rig
    (spine, legs, arms, fingers) continues playing from the body NLA.
    """

    def __init__(self, port=11113, host='127.0.0.1'):
        self._port = port
        self._host = host
        self._sock = None
        self._thread = None
        self._stop_event = threading.Event()
        self._latest = None
        self._lock = threading.Lock()
        self._running = False
        self._tick_interval = 1.0 / 60.0

    @property
    def running(self):
        return self._running

    @property
    def port(self):
        return self._port

    def start(self):
        """Open socket, start listener thread, register timer."""
        if self._running:
            return
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind((self._host, self._port))
        sock.settimeout(0.1)
        self._sock = sock
        self._stop_event.clear()
        self._latest = None
        self._thread = threading.Thread(
            target=self._listen, name="PPV2FaceReceiver", daemon=True,
        )
        self._thread.start()
        bpy.app.timers.register(
            self._tick,
            first_interval=self._tick_interval,
            persistent=True,
        )
        self._running = True

    def stop(self):
        """Tear down: stop thread, close socket, unregister timer."""
        if not self._running:
            return
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None
        if self._sock is not None:
            try:
                self._sock.close()
            finally:
                self._sock = None
        try:
            bpy.app.timers.unregister(self._tick)
        except ValueError:
            pass
        self._running = False
        with self._lock:
            self._latest = None

    def _listen(self):
        """Background thread: receive face packets."""
        while not self._stop_event.is_set():
            try:
                data, _addr = self._sock.recvfrom(256)
            except socket.timeout:
                continue
            except OSError:
                break
            matrix_flat = parse_face_packet(data)
            if matrix_flat is not None:
                with self._lock:
                    self._latest = matrix_flat

    def _tick(self):
        """Main thread: apply latest face frame to head bone."""
        if not self._running:
            return None
        with self._lock:
            matrix_flat = self._latest
            self._latest = None
        if matrix_flat is not None:
            rig = bpy.data.objects.get(RIG_OBJECT_NAME)
            if rig is not None:
                apply_face_to_rig(rig, matrix_flat)
                get_face_recorder().keyframe_now(rig)
        return self._tick_interval


# ---------------------------------------------------------------------------
# Face receiver singleton
# ---------------------------------------------------------------------------

_face_receiver = None


def get_face_receiver():
    """Return the module-level FaceReceiver, creating it on first call."""
    global _face_receiver
    if _face_receiver is None:
        _face_receiver = FaceReceiver()
    return _face_receiver
