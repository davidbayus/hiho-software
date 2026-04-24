#!/usr/bin/env python3
"""MediaPipe face + body + hand tracking → UDP sender for PPParty.

Standalone script — runs in system Python, NOT inside Blender.
Captures webcam, runs MediaPipe FaceLandmarker + PoseLandmarker + HandLandmarker,
packs blend shapes + body landmarks + hand endpoints into UDP packets, sends
to Blender.

alpha.46 (5b.i): Hand endpoints wired into the UDP packet. Three tracked
endpoints per hand — WRIST (0), THUMB_TIP (4), INDEX_FINGER_TIP (8) —
sent in body-anchored world coordinates (meters, same frame as
pose_world_landmarks). Wrist comes from pose_world[15/16]; tips computed
as wrist + hand_world_landmarks offset. Receiver-blind: alpha.45 receivers
skip the new FLAG_HAS_HANDS bit and tolerate trailing bytes, so this commit
is safe to deploy ahead of receiver-side hand parsing.

Usage:
    python mediapipe_sender.py
    python mediapipe_sender.py --port 11111 --camera 0
    python mediapipe_sender.py --no-preview  # headless mode

Dependencies (pip install):
    mediapipe >= 0.10.30
    opencv-python
    numpy
"""

import argparse
import math
import os
import socket
import struct
import sys
import time
import urllib.request

import cv2
import numpy as np
import mediapipe as mp

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# UDP packet magic header
MAGIC = b'MPPT'
VERSION = 0x01
FLAG_HAS_FACE = 0x01
FLAG_HAS_BODY = 0x02
FLAG_HAS_HANDS = 0x04  # alpha.46 (5b.i) — per-hand 3-endpoint packet

# MediaPipe blend shapes come out in alphabetical order (52 total).
# Index 0 is "_neutral" which we skip — we send indices 1-51 (51 values)
# plus _neutral as index 0 for a full 52-float array.
# The receiver maps by NAME, not index, so order must match MediaPipe's output.
BLEND_SHAPE_NAMES = [
    "_neutral",          # 0  — not used by puppet, but sent for completeness
    "browDownLeft",      # 1
    "browDownRight",     # 2
    "browInnerUp",       # 3
    "browOuterUpLeft",   # 4
    "browOuterUpRight",  # 5
    "cheekPuff",         # 6  — blacklisted (unreliable)
    "cheekSquintLeft",   # 7
    "cheekSquintRight",  # 8
    "eyeBlinkLeft",      # 9
    "eyeBlinkRight",     # 10
    "eyeLookDownLeft",   # 11
    "eyeLookDownRight",  # 12
    "eyeLookInLeft",     # 13
    "eyeLookInRight",    # 14
    "eyeLookOutLeft",    # 15
    "eyeLookOutRight",   # 16
    "eyeLookUpLeft",     # 17
    "eyeLookUpRight",    # 18
    "eyeSquintLeft",     # 19
    "eyeSquintRight",    # 20
    "eyeWideLeft",       # 21
    "eyeWideRight",      # 22
    "jawForward",        # 23 — blacklisted (unreliable)
    "jawLeft",           # 24 — blacklisted (unreliable)
    "jawOpen",           # 25
    "jawRight",          # 26 — blacklisted (unreliable)
    "mouthClose",        # 27
    "mouthDimpleLeft",   # 28 — blacklisted (unreliable)
    "mouthDimpleRight",  # 29 — blacklisted (unreliable)
    "mouthFrownLeft",    # 30
    "mouthFrownRight",   # 31
    "mouthFunnel",       # 32
    "mouthLeft",         # 33
    "mouthLowerDownLeft",  # 34
    "mouthLowerDownRight", # 35
    "mouthPressLeft",    # 36
    "mouthPressRight",   # 37
    "mouthPucker",       # 38
    "mouthRight",        # 39
    "mouthRollLower",    # 40
    "mouthRollUpper",    # 41
    "mouthShrugLower",   # 42
    "mouthShrugUpper",   # 43
    "mouthSmileLeft",    # 44
    "mouthSmileRight",   # 45
    "mouthStretchLeft",  # 46
    "mouthStretchRight", # 47
    "mouthUpperUpLeft",  # 48
    "mouthUpperUpRight", # 49
    "noseSneerLeft",     # 50
    "noseSneerRight",    # 51
]

# Blend shapes to force to zero (unreliable from webcam)
BLACKLISTED = {
    "_neutral", "jawForward", "jawRight", "jawLeft",
    "mouthDimpleLeft", "mouthDimpleRight", "cheekPuff",
}

# MediaPipe model file URLs (downloaded on first run)
FACE_MODEL_URL = "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task"
POSE_MODEL_URL = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task"
HAND_MODEL_URL = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task"

FACE_MODEL_FILE = "face_landmarker.task"
POSE_MODEL_FILE = "pose_landmarker_lite.task"
HAND_MODEL_FILE = "hand_landmarker.task"

# MediaPipe hand landmark indices (subset used by PPParty Option C).
# The full 21-landmark layout is documented in MediaPipe's hand docs;
# these are the 3 endpoints the Blender side will consume in alpha.46.
HAND_WRIST = 0
HAND_THUMB_TIP = 4
HAND_INDEX_TIP = 8
HAND_TRACKED_INDICES = (HAND_WRIST, HAND_THUMB_TIP, HAND_INDEX_TIP)


# ---------------------------------------------------------------------------
# Model download
# ---------------------------------------------------------------------------

def ensure_model(filename, url):
    """Download model file if not present. Returns path."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    model_dir = os.path.join(script_dir, "models")
    os.makedirs(model_dir, exist_ok=True)
    path = os.path.join(model_dir, filename)
    if os.path.exists(path):
        return path
    print(f"Downloading {filename}...")
    urllib.request.urlretrieve(url, path)
    print(f"  Saved to {path}")
    return path


# ---------------------------------------------------------------------------
# One Euro Filter — adaptive low-pass for jitter reduction
# BSD/MIT-compatible algorithm (Casiez et al., 2012)
# Smooths when still, stays responsive when moving fast.
# ---------------------------------------------------------------------------

class OneEuroFilter:
    """One Euro Filter for a single scalar value.

    Parameters:
        min_cutoff: minimum cutoff frequency (Hz). Lower = more smoothing
                    when still. Default 1.0 is good for face blend shapes.
        beta:       speed coefficient. Higher = less lag when moving fast.
                    Default 0.007 is conservative; 0.01-0.05 for snappier.
        d_cutoff:   cutoff for derivative filter. Usually leave at 1.0.
    """

    def __init__(self, min_cutoff=1.0, beta=0.007, d_cutoff=1.0):
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
        self._x_prev = None
        self._dx_prev = 0.0
        self._t_prev = None

    @staticmethod
    def _smoothing_factor(te, cutoff):
        r = 2.0 * math.pi * cutoff * te
        return r / (r + 1.0)

    def __call__(self, x, t=None):
        if t is None:
            t = time.monotonic()

        if self._t_prev is None:
            self._x_prev = x
            self._t_prev = t
            return x

        te = t - self._t_prev
        if te <= 0:
            return self._x_prev

        # Filtered derivative
        a_d = self._smoothing_factor(te, self.d_cutoff)
        dx = (x - self._x_prev) / te
        dx_hat = a_d * dx + (1.0 - a_d) * self._dx_prev

        # Adaptive cutoff
        cutoff = self.min_cutoff + self.beta * abs(dx_hat)
        a = self._smoothing_factor(te, cutoff)
        x_hat = a * x + (1.0 - a) * self._x_prev

        self._x_prev = x_hat
        self._dx_prev = dx_hat
        self._t_prev = t
        return x_hat


def make_face_filters(min_cutoff=1.0, beta=0.007):
    """Create 52 One Euro Filters for face blend shapes + 3 for head rotation."""
    return [OneEuroFilter(min_cutoff=min_cutoff, beta=beta) for _ in range(55)]


def make_body_filters(min_cutoff=0.8, beta=0.01):
    """Create filters for 33 body landmarks × 3 axes + 3 body center axes."""
    return [OneEuroFilter(min_cutoff=min_cutoff, beta=beta) for _ in range(102)]


def make_hand_filters(min_cutoff=0.8, beta=0.015):
    """Create filters for 2 hands × 2 tips × 3 axes = 12 filters.

    Only the thumb/index tips are filtered here — the wrist anchor reuses
    body_filters via pose_world_landmarks[15/16], so no double-filtering.
    Tips are the noisiest hand landmarks; slightly hotter beta than body
    since hand motion is typically faster than torso sway.

    Filter layout:
        [0..2]   L thumb tip xyz
        [3..5]   L index tip xyz
        [6..8]   R thumb tip xyz
        [9..11]  R index tip xyz
    """
    return [OneEuroFilter(min_cutoff=min_cutoff, beta=beta) for _ in range(12)]


# ---------------------------------------------------------------------------
# Head rotation from face transformation matrix
# ---------------------------------------------------------------------------

def matrix_to_euler(mat):
    """Extract head rotation from a 4x4 transformation matrix.

    Returns (headRotX, headRotY, headRotZ) mapped to Blender's
    coordinate system (Z-up):
      headRotX = pitch (nod up/down)     — rotation around X
      headRotY = roll  (tilt side)       — rotation around Y
      headRotZ = yaw   (turn left/right) — rotation around Z

    MediaPipe uses Y-up, so its Y-rotation (yaw) maps to Blender's
    Z-rotation, and its Z-rotation (roll) maps to Blender's Y-rotation.
    """
    # Extract rotation from 4x4 matrix (top-left 3x3)
    r00, r01, r02 = mat[0][0], mat[0][1], mat[0][2]
    r10, r11, r12 = mat[1][0], mat[1][1], mat[1][2]
    r20, r21, r22 = mat[2][0], mat[2][1], mat[2][2]

    # Euler angles (XYZ order) from rotation matrix
    sy = math.sqrt(r00 * r00 + r10 * r10)
    singular = sy < 1e-6

    if not singular:
        pitch = math.atan2(r21, r22)   # X — nod
        yaw = math.atan2(-r20, sy)     # Y — turn (MediaPipe Y-up)
        roll = math.atan2(r10, r00)    # Z — tilt (MediaPipe Z-forward)
    else:
        pitch = math.atan2(-r12, r11)
        yaw = math.atan2(-r20, sy)
        roll = 0.0

    # Map MediaPipe (Y-up) → Blender (Z-up):
    #   pitch → headRotX (nod),  roll → headRotY (tilt),  yaw → headRotZ (turn)
    # Yaw sign: NOT negated. MediaPipe's FaceLandmarker matrix is already
    # in the camera's view frame (not mirrored), so passing yaw through
    # directly makes the puppet turn the same way the performer does.
    return pitch, -roll, yaw


# ---------------------------------------------------------------------------
# UDP packet packing
# ---------------------------------------------------------------------------

def pack_frame(blend_shapes, head_rotation, body_landmarks,
               body_center=None, hands=None):
    """Pack a single frame into the MPPT binary UDP packet.

    Args:
        blend_shapes: list of 52 floats (ARKit blend shape weights)
        head_rotation: tuple of 3 floats (pitch, yaw, roll) or None
        body_landmarks: list of 33 (x, y, z, visibility) tuples, or None
        body_center: tuple of 3 floats (x, y, z) — image-space hip
            midpoint centered at (0,0), or None
        hands: tuple (left_hand, right_hand). Each element is either
            None (hand not tracked) or a tuple of 3 vec3s
            (wrist_xyz, thumb_xyz, index_xyz) in body-anchored world
            coordinates (meters, same frame as pose_world_landmarks).

    Returns:
        bytes ready to send via UDP

    alpha.46 (5b.i) hand section layout — appended after body section,
    guarded by FLAG_HAS_HANDS. Sent only when at least one hand is tracked:
        1 byte  — presence (bit 0: L present, bit 1: R present)
        If L:   9 floats (L_wrist, L_thumb_tip, L_index_tip × xyz)
        If R:   9 floats (R_wrist, R_thumb_tip, R_index_tip × xyz)
    VERSION byte is NOT bumped — alpha.45 receivers ignore the new flag
    bit and tolerate trailing bytes, so old receivers remain compatible.
    """
    flags = 0x00
    body = b''

    if blend_shapes is not None:
        flags |= FLAG_HAS_FACE
        # 52 blend shape floats + 3 head rotation floats
        rot = head_rotation if head_rotation else (0.0, 0.0, 0.0)
        body += struct.pack('<55f', *blend_shapes, *rot)

    if body_landmarks is not None:
        flags |= FLAG_HAS_BODY
        flat = []
        for lm in body_landmarks:
            flat.extend([lm[0], lm[1], lm[2], lm[3]])
        # Append body center (3 floats) after the 132 landmark floats
        bc = body_center if body_center else (0.0, 0.0, 0.0)
        flat.extend(bc)
        body += struct.pack('<135f', *flat)

    if hands is not None:
        left_hand, right_hand = hands
        if left_hand is not None or right_hand is not None:
            flags |= FLAG_HAS_HANDS
            presence = 0
            if left_hand is not None:
                presence |= 0x01
            if right_hand is not None:
                presence |= 0x02
            body += struct.pack('B', presence)
            for hand in (left_hand, right_hand):
                if hand is None:
                    continue
                wrist, thumb, index_tip = hand
                body += struct.pack(
                    '<9f',
                    wrist[0], wrist[1], wrist[2],
                    thumb[0], thumb[1], thumb[2],
                    index_tip[0], index_tip[1], index_tip[2],
                )

    header = MAGIC + struct.pack('BB', VERSION, flags)
    return header + body


# ---------------------------------------------------------------------------
# Main tracking loop
# ---------------------------------------------------------------------------

def run(args):
    """Main loop: webcam → MediaPipe → UDP."""

    # Ensure models are available
    face_model = args.model_face or ensure_model(FACE_MODEL_FILE, FACE_MODEL_URL)
    pose_model = args.model_pose or ensure_model(POSE_MODEL_FILE, POSE_MODEL_URL)
    hand_model = args.model_hand or ensure_model(HAND_MODEL_FILE, HAND_MODEL_URL)

    # UDP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    target = (args.host, args.port)

    # --- Shared result containers (written by callbacks) ---
    face_result_container = [None]  # [FaceLandmarkerResult]
    pose_result_container = [None]  # [PoseLandmarkerResult]
    hand_result_container = [None]  # [HandLandmarkerResult]
    face_timestamp = [0]
    pose_timestamp = [0]
    hand_timestamp = [0]

    def on_face_result(result, output_image, timestamp_ms):
        face_result_container[0] = result
        face_timestamp[0] = timestamp_ms

    def on_pose_result(result, output_image, timestamp_ms):
        pose_result_container[0] = result
        pose_timestamp[0] = timestamp_ms

    def on_hand_result(result, output_image, timestamp_ms):
        hand_result_container[0] = result
        hand_timestamp[0] = timestamp_ms

    # --- MediaPipe setup ---
    BaseOptions = mp.tasks.BaseOptions
    VisionRunningMode = mp.tasks.vision.RunningMode

    # Face landmarker (blend shapes + head pose)
    FaceLandmarker = mp.tasks.vision.FaceLandmarker
    FaceLandmarkerOptions = mp.tasks.vision.FaceLandmarkerOptions
    face_options = FaceLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=face_model),
        running_mode=VisionRunningMode.LIVE_STREAM,
        output_face_blendshapes=True,
        output_facial_transformation_matrixes=True,
        num_faces=1,
        result_callback=on_face_result,
    )

    # Pose landmarker (body landmarks)
    PoseLandmarker = mp.tasks.vision.PoseLandmarker
    PoseLandmarkerOptions = mp.tasks.vision.PoseLandmarkerOptions
    pose_options = PoseLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=pose_model),
        running_mode=VisionRunningMode.LIVE_STREAM,
        num_poses=1,
        result_callback=on_pose_result,
    )

    # Hand landmarker (21 landmarks per hand, both hands) — alpha.45.
    # Preview-only at this stage: landmarks feed the overlay but not the UDP
    # packet. Wire-level integration lands in alpha.46 alongside the Blender
    # receiver sockets.
    HandLandmarker = mp.tasks.vision.HandLandmarker
    HandLandmarkerOptions = mp.tasks.vision.HandLandmarkerOptions
    hand_options = HandLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=hand_model),
        running_mode=VisionRunningMode.LIVE_STREAM,
        num_hands=2,
        result_callback=on_hand_result,
    )

    # Open webcam
    cap = cv2.VideoCapture(args.camera)
    if not cap.isOpened():
        print(f"ERROR: Cannot open camera {args.camera}")
        sys.exit(1)

    # Lower resolution for performance on e-waste hardware
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)

    actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"Camera opened: {actual_w}x{actual_h}")
    print(f"Sending to {target[0]}:{target[1]}")
    print("Press 'q' to quit" if not args.no_preview else "Press Ctrl+C to quit")

    frame_count = 0
    fps_time = time.time()
    fps_display = 0.0

    # One Euro Filters for smoothing (adaptive: smooth when still, fast when moving)
    # alpha.5: defaults raised (1.0→1.5 cutoff, 0.007→0.02 beta) for less
    # baseline smoothing and faster response to quick gestures.
    face_filters = make_face_filters(
        min_cutoff=args.smooth_min_cutoff,
        beta=args.smooth_beta,
    )
    body_mc = (args.smooth_body_min_cutoff if args.smooth_body_min_cutoff
               is not None else args.smooth_min_cutoff * 0.8)
    body_beta = (args.smooth_body_beta if args.smooth_body_beta
                 is not None else args.smooth_beta * 2.0)
    body_filters = make_body_filters(
        min_cutoff=body_mc,
        beta=body_beta,
    )
    hand_mc = (args.smooth_hand_min_cutoff if args.smooth_hand_min_cutoff
               is not None else args.smooth_min_cutoff * 0.8)
    hand_beta = (args.smooth_hand_beta if args.smooth_hand_beta
                 is not None else args.smooth_beta * 1.5)
    hand_filters = make_hand_filters(
        min_cutoff=hand_mc,
        beta=hand_beta,
    )

    with FaceLandmarker.create_from_options(face_options) as face_lm, \
         PoseLandmarker.create_from_options(pose_options) as pose_lm, \
         HandLandmarker.create_from_options(hand_options) as hand_lm:

        while True:
            ret, frame = cap.read()
            if not ret:
                print("Camera read failed, retrying...")
                time.sleep(0.1)
                continue

            # Flip horizontally so it mirrors the performer (selfie mode)
            frame = cv2.flip(frame, 1)

            # Convert to MediaPipe Image
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

            # Timestamp in milliseconds (monotonic)
            ts_ms = int(time.monotonic() * 1000)

            # Run all three detectors (async — results come via callbacks)
            face_lm.detect_async(mp_image, ts_ms)
            pose_lm.detect_async(mp_image, ts_ms)
            hand_lm.detect_async(mp_image, ts_ms)

            # --- Pack latest results ---
            blend_shapes = None
            head_rotation = None
            body_landmarks = None

            # Face blend shapes
            face_res = face_result_container[0]
            if face_res and face_res.face_blendshapes:
                bs = face_res.face_blendshapes[0]  # first face
                # Build 52-float array in MediaPipe's alphabetical order
                blend_shapes = [0.0] * 52
                for i, category in enumerate(bs):
                    if i < 52:
                        name = category.category_name
                        val = category.score
                        # Zero out blacklisted shapes
                        if name in BLACKLISTED:
                            val = 0.0
                        blend_shapes[i] = val

                # Head rotation from transformation matrix
                if face_res.facial_transformation_matrixes:
                    mat = face_res.facial_transformation_matrixes[0]
                    # mat is a 4x4 numpy array
                    head_rotation = matrix_to_euler(mat)

            # Body landmarks (use world landmarks for 3D positions in meters)
            pose_res = pose_result_container[0]
            body_center = None
            if pose_res and pose_res.pose_world_landmarks:
                wl = pose_res.pose_world_landmarks[0]  # first person
                body_landmarks = []
                for lm in wl:
                    body_landmarks.append((lm.x, lm.y, lm.z, lm.visibility))

                # Body center from image-space landmarks (where body is
                # in the camera frame). Hip midpoint, centered so (0,0)
                # = middle of frame.
                if pose_res.pose_landmarks:
                    il = pose_res.pose_landmarks[0]  # image-space
                    lh = il[23]  # left hip
                    rh = il[24]  # right hip
                    body_center = (
                        (lh.x + rh.x) / 2.0 - 0.5,   # x: centered
                        -((lh.y + rh.y) / 2.0 - 0.5), # y: flip (image down → up)
                        0.0,                            # z: depth (future)
                    )

            # --- One Euro Filter pass (smooth before sending) ---
            t_now = time.monotonic()

            if blend_shapes is not None:
                # Filter 52 blend shapes + 3 head rotation values
                for i in range(52):
                    blend_shapes[i] = face_filters[i](blend_shapes[i], t_now)
                if head_rotation is not None:
                    head_rotation = tuple(
                        face_filters[52 + i](head_rotation[i], t_now)
                        for i in range(3)
                    )

            if body_landmarks is not None:
                filtered_body = []
                for j, lm in enumerate(body_landmarks):
                    fi = j * 3  # 3 filters per landmark (x, y, z)
                    fx = body_filters[fi](lm[0], t_now)
                    fy = body_filters[fi + 1](lm[1], t_now)
                    fz = body_filters[fi + 2](lm[2], t_now)
                    filtered_body.append((fx, fy, fz, lm[3]))  # keep raw visibility
                body_landmarks = filtered_body

                # Filter body center (indices 99-101 in body_filters)
                if body_center is not None:
                    body_center = (
                        body_filters[99](body_center[0], t_now),
                        body_filters[100](body_center[1], t_now),
                        body_filters[101](body_center[2], t_now),
                    )

            # --- Hand endpoints (body-anchored world space, alpha.46) ---
            # Wrist anchor from pose_world[15/16] (filtered). Tips computed
            # as wrist + hand_world_landmarks offset — hand_world is
            # hand-local meters with wrist at origin and axes aligned to
            # world space, so the vector add lands the tip in body-relative
            # meters, same frame as pose_world. No hand data sent when
            # either the hand is missing OR the body landmarks aren't
            # available (no anchor → no body-space position).
            hands = None
            hand_res = hand_result_container[0]
            if (hand_res and hand_res.hand_world_landmarks
                    and body_landmarks is not None):
                left_hand = None
                right_hand = None
                for hand_idx, hwl in enumerate(hand_res.hand_world_landmarks):
                    if not (hand_res.handedness
                            and hand_idx < len(hand_res.handedness)
                            and hand_res.handedness[hand_idx]):
                        continue
                    label = hand_res.handedness[hand_idx][0].category_name
                    # MediaPipe labels assume mirrored input; we cv2.flip
                    # the frame, so "Left" == performer's left hand ==
                    # pose LEFT_WRIST (15), "Right" == RIGHT_WRIST (16).
                    if label == "Left":
                        pose_wrist_idx = 15
                    elif label == "Right":
                        pose_wrist_idx = 16
                    else:
                        continue

                    wrist_lm = body_landmarks[pose_wrist_idx]
                    wrist_xyz = (wrist_lm[0], wrist_lm[1], wrist_lm[2])

                    thumb_off = hwl[HAND_THUMB_TIP]
                    index_off = hwl[HAND_INDEX_TIP]
                    thumb_xyz = (
                        wrist_xyz[0] + thumb_off.x,
                        wrist_xyz[1] + thumb_off.y,
                        wrist_xyz[2] + thumb_off.z,
                    )
                    index_xyz = (
                        wrist_xyz[0] + index_off.x,
                        wrist_xyz[1] + index_off.y,
                        wrist_xyz[2] + index_off.z,
                    )

                    # Filter tips (wrist is already filtered via body_filters).
                    # Layout: L thumb = [0..2], L index = [3..5],
                    #         R thumb = [6..8], R index = [9..11].
                    base = 0 if label == "Left" else 6
                    thumb_filt = (
                        hand_filters[base + 0](thumb_xyz[0], t_now),
                        hand_filters[base + 1](thumb_xyz[1], t_now),
                        hand_filters[base + 2](thumb_xyz[2], t_now),
                    )
                    index_filt = (
                        hand_filters[base + 3](index_xyz[0], t_now),
                        hand_filters[base + 4](index_xyz[1], t_now),
                        hand_filters[base + 5](index_xyz[2], t_now),
                    )

                    hand_entry = (wrist_xyz, thumb_filt, index_filt)
                    if label == "Left":
                        left_hand = hand_entry
                    else:
                        right_hand = hand_entry

                if left_hand is not None or right_hand is not None:
                    hands = (left_hand, right_hand)

            # Send UDP packet if we have any data
            if (blend_shapes is not None or body_landmarks is not None
                    or hands is not None):
                packet = pack_frame(blend_shapes, head_rotation,
                                    body_landmarks, body_center, hands)
                sock.sendto(packet, target)

            # FPS counter
            frame_count += 1
            now = time.time()
            if now - fps_time >= 1.0:
                fps_display = frame_count / (now - fps_time)
                frame_count = 0
                fps_time = now

            # Preview window (optional)
            if not args.no_preview:
                # Draw face mesh (green dots)
                if face_res and face_res.face_landmarks:
                    for lm in face_res.face_landmarks[0]:
                        x = int(lm.x * frame.shape[1])
                        y = int(lm.y * frame.shape[0])
                        cv2.circle(frame, (x, y), 1, (0, 255, 0), -1)

                # Draw body skeleton (orange dots + cyan lines)
                if pose_res and pose_res.pose_landmarks:
                    plm = pose_res.pose_landmarks[0]
                    h, w = frame.shape[:2]

                    def _px(idx):
                        return (int(plm[idx].x * w), int(plm[idx].y * h))

                    # Skeleton connections (MediaPipe Pose indices)
                    _SKELETON = [
                        # Torso
                        (11, 12), (11, 23), (12, 24), (23, 24),
                        # Left arm
                        (11, 13), (13, 15),
                        # Right arm
                        (12, 14), (14, 16),
                        # Left leg
                        (23, 25), (25, 27),
                        # Right leg
                        (24, 26), (26, 28),
                        # Shoulders to ears (neck proxy)
                        (11, 0), (12, 0),
                    ]
                    for a, b in _SKELETON:
                        if a < len(plm) and b < len(plm):
                            cv2.line(frame, _px(a), _px(b),
                                     (255, 200, 0), 2)

                    # Draw joint dots on top
                    for i, lm in enumerate(plm):
                        x = int(lm.x * w)
                        y = int(lm.y * h)
                        cv2.circle(frame, (x, y), 4, (0, 128, 255), -1)

                # Draw hand landmarks (magenta skeleton + highlighted endpoints)
                hand_res = hand_result_container[0]
                if hand_res and hand_res.hand_landmarks:
                    h, w = frame.shape[:2]
                    # MediaPipe hand skeleton — 5 finger chains rooted at wrist
                    # plus a palm arch connecting the MCPs.
                    _HAND_CHAINS = [
                        (0, 1, 2, 3, 4),        # thumb
                        (0, 5, 6, 7, 8),        # index
                        (9, 10, 11, 12),        # middle (no root-to-9 line)
                        (13, 14, 15, 16),       # ring
                        (0, 17, 18, 19, 20),    # pinky
                    ]
                    _PALM_ARCH = [(5, 9), (9, 13), (13, 17)]

                    for hand_idx, hlm in enumerate(hand_res.hand_landmarks):
                        # Label (L/R) from handedness output
                        label = "?"
                        if (hand_res.handedness
                                and hand_idx < len(hand_res.handedness)
                                and hand_res.handedness[hand_idx]):
                            label = hand_res.handedness[hand_idx][0].category_name[0]

                        def _hpx(idx, _hlm=hlm, _w=w, _h=h):
                            return (int(_hlm[idx].x * _w), int(_hlm[idx].y * _h))

                        # Finger chain lines (magenta)
                        for chain in _HAND_CHAINS:
                            for i in range(len(chain) - 1):
                                a, b = chain[i], chain[i + 1]
                                if a < len(hlm) and b < len(hlm):
                                    cv2.line(frame, _hpx(a), _hpx(b),
                                             (200, 80, 220), 2)
                        for a, b in _PALM_ARCH:
                            if a < len(hlm) and b < len(hlm):
                                cv2.line(frame, _hpx(a), _hpx(b),
                                         (200, 80, 220), 2)

                        # All 21 dots (small, magenta)
                        for lm in hlm:
                            x = int(lm.x * w)
                            y = int(lm.y * h)
                            cv2.circle(frame, (x, y), 2, (200, 80, 220), -1)

                        # Highlight the 3 tracked endpoints (yellow, larger).
                        # These are the only landmarks the Blender rig will
                        # consume in alpha.46 — visually distinguishing them
                        # helps us confirm tracking stability during testing.
                        for idx in HAND_TRACKED_INDICES:
                            if idx < len(hlm):
                                px, py = _hpx(idx)
                                cv2.circle(frame, (px, py), 6, (0, 255, 255), -1)
                                cv2.circle(frame, (px, py), 6, (0, 0, 0), 1)

                        # Handedness label near wrist
                        if len(hlm) > 0:
                            wx, wy = _hpx(HAND_WRIST)
                            cv2.putText(frame, label, (wx + 10, wy - 10),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                                        (0, 255, 255), 2)

                # Blend shape bars (right side of frame)
                if blend_shapes is not None:
                    h, w = frame.shape[:2]
                    bar_x = w - 160
                    bar_w = 120
                    bar_h = 12
                    _SHOW_SHAPES = [
                        (25, "jawOpen"),
                        (45, "smileR"),
                        (30, "frownL"),
                        (9, "blinkL"),
                        (10, "blinkR"),
                        (21, "wideL"),
                        (32, "funnel"),
                        (33, "mouthL"),
                        (39, "mouthR"),
                    ]
                    for row, (idx, label) in enumerate(_SHOW_SHAPES):
                        val = blend_shapes[idx] if idx < len(blend_shapes) else 0
                        by = 20 + row * (bar_h + 6)
                        # Background bar
                        cv2.rectangle(frame, (bar_x, by),
                                      (bar_x + bar_w, by + bar_h),
                                      (40, 40, 40), -1)
                        # Fill bar
                        fill = int(val * bar_w)
                        cv2.rectangle(frame, (bar_x, by),
                                      (bar_x + fill, by + bar_h),
                                      (0, 220, 120), -1)
                        # Label
                        cv2.putText(frame, f"{label} {val:.2f}",
                                    (bar_x - 2, by + bar_h - 2),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.35,
                                    (200, 200, 200), 1)

                # FPS + status (bottom left)
                h = frame.shape[0]
                face_ok = "FACE" if blend_shapes is not None else "----"
                body_ok = "BODY" if body_landmarks is not None else "----"
                hand_res_for_status = hand_result_container[0]
                hand_count = (len(hand_res_for_status.hand_landmarks)
                              if hand_res_for_status
                              and hand_res_for_status.hand_landmarks else 0)
                hand_ok = f"HANDS:{hand_count}" if hand_count else "HANDS:0"
                cv2.putText(frame, f"FPS: {fps_display:.1f}  {face_ok} | {body_ok} | {hand_ok}",
                            (10, h - 15),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

                cv2.imshow("PPParty Tracker", frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
            else:
                # Headless mode — print FPS periodically
                if frame_count == 0:
                    face_ok = "FACE" if blend_shapes is not None else "----"
                    body_ok = "BODY" if body_landmarks is not None else "----"
                    hand_res_for_status = hand_result_container[0]
                    hand_count = (len(hand_res_for_status.hand_landmarks)
                                  if hand_res_for_status
                                  and hand_res_for_status.hand_landmarks else 0)
                    print(f"\rFPS: {fps_display:.1f}  {face_ok} | {body_ok} | HANDS:{hand_count}",
                          end='', flush=True)

    # Cleanup
    cap.release()
    if not args.no_preview:
        cv2.destroyAllWindows()
    sock.close()
    print("\nDone.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="PPParty MediaPipe Tracker — webcam to UDP sender"
    )
    parser.add_argument("--port", type=int, default=11111,
                        help="UDP port to send to (default: 11111)")
    parser.add_argument("--host", type=str, default="127.0.0.1",
                        help="Target IP (default: 127.0.0.1)")
    parser.add_argument("--camera", type=int, default=0,
                        help="Camera device index (default: 0)")
    parser.add_argument("--width", type=int, default=640,
                        help="Capture width (default: 640)")
    parser.add_argument("--height", type=int, default=480,
                        help="Capture height (default: 480)")
    parser.add_argument("--no-preview", action="store_true",
                        help="Run without preview window (headless)")
    parser.add_argument("--model-face", type=str, default=None,
                        help="Path to face_landmarker.task model file")
    parser.add_argument("--model-pose", type=str, default=None,
                        help="Path to pose_landmarker_lite.task model file")
    parser.add_argument("--model-hand", type=str, default=None,
                        help="Path to hand_landmarker.task model file")
    parser.add_argument("--smooth-min-cutoff", type=float, default=1.5,
                        help="Face One Euro min cutoff Hz — lower = smoother "
                             "when still (default: 1.5)")
    parser.add_argument("--smooth-beta", type=float, default=0.02,
                        help="Face One Euro speed coefficient — higher = less "
                             "lag when moving fast (default: 0.02)")
    parser.add_argument("--smooth-body-min-cutoff", type=float, default=None,
                        help="Body-specific min cutoff Hz (default: face × 0.8)")
    parser.add_argument("--smooth-body-beta", type=float, default=None,
                        help="Body-specific speed coefficient (default: face × 2)")
    parser.add_argument("--smooth-hand-min-cutoff", type=float, default=None,
                        help="Hand-tip min cutoff Hz (default: face × 0.8)")
    parser.add_argument("--smooth-hand-beta", type=float, default=None,
                        help="Hand-tip speed coefficient (default: face × 1.5)")
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
