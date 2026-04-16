#!/usr/bin/env python3
"""MediaPipe face + body tracking → UDP sender for PPParty.

Standalone script — runs in system Python, NOT inside Blender.
Captures webcam, runs MediaPipe FaceLandmarker + PoseLandmarker,
packs blend shapes + body landmarks into UDP packets, sends to Blender.

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

FACE_MODEL_FILE = "face_landmarker.task"
POSE_MODEL_FILE = "pose_landmarker_lite.task"


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
    """Create filters for 33 body landmarks × 3 axes (skip visibility)."""
    return [OneEuroFilter(min_cutoff=min_cutoff, beta=beta) for _ in range(99)]


# ---------------------------------------------------------------------------
# Head rotation from face transformation matrix
# ---------------------------------------------------------------------------

def matrix_to_euler(mat):
    """Extract pitch, yaw, roll from a 4x4 transformation matrix.

    Returns (pitch, yaw, roll) in radians matching the axis convention
    used by PPParty's OSC receiver (FOSCAP style):
      pitch = rotation around X (nod)
      yaw   = rotation around Y (shake head)
      roll  = rotation around Z (tilt head)

    MediaPipe's face transformation matrix is row-major.
    We negate axes to match FOSCAP's convention where the phone
    sent inverted values.
    """
    # Extract rotation from 4x4 matrix (top-left 3x3)
    r00, r01, r02 = mat[0][0], mat[0][1], mat[0][2]
    r10, r11, r12 = mat[1][0], mat[1][1], mat[1][2]
    r20, r21, r22 = mat[2][0], mat[2][1], mat[2][2]

    # Euler angles (XYZ order) from rotation matrix
    sy = math.sqrt(r00 * r00 + r10 * r10)
    singular = sy < 1e-6

    if not singular:
        pitch = math.atan2(r21, r22)   # X
        yaw = math.atan2(-r20, sy)     # Y
        roll = math.atan2(r10, r00)    # Z
    else:
        pitch = math.atan2(-r12, r11)
        yaw = math.atan2(-r20, sy)
        roll = 0.0

    # Negate to match FOSCAP/Live Link Face convention
    return -yaw, -pitch, -roll


# ---------------------------------------------------------------------------
# UDP packet packing
# ---------------------------------------------------------------------------

def pack_frame(blend_shapes, head_rotation, body_landmarks):
    """Pack a single frame into the MPPT binary UDP packet.

    Args:
        blend_shapes: list of 52 floats (ARKit blend shape weights)
        head_rotation: tuple of 3 floats (pitch, yaw, roll) or None
        body_landmarks: list of 33 (x, y, z, visibility) tuples, or None

    Returns:
        bytes ready to send via UDP
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
        body += struct.pack('<132f', *flat)

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

    # UDP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    target = (args.host, args.port)

    # --- Shared result containers (written by callbacks) ---
    face_result_container = [None]  # [FaceLandmarkerResult]
    pose_result_container = [None]  # [PoseLandmarkerResult]
    face_timestamp = [0]
    pose_timestamp = [0]

    def on_face_result(result, output_image, timestamp_ms):
        face_result_container[0] = result
        face_timestamp[0] = timestamp_ms

    def on_pose_result(result, output_image, timestamp_ms):
        pose_result_container[0] = result
        pose_timestamp[0] = timestamp_ms

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
    face_filters = make_face_filters(
        min_cutoff=args.smooth_min_cutoff,
        beta=args.smooth_beta,
    )
    body_filters = make_body_filters(
        min_cutoff=args.smooth_min_cutoff * 0.8,  # body slightly smoother
        beta=args.smooth_beta * 1.5,               # but snappier on fast moves
    )

    with FaceLandmarker.create_from_options(face_options) as face_lm, \
         PoseLandmarker.create_from_options(pose_options) as pose_lm:

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

            # Run both detectors (async — results come via callbacks)
            face_lm.detect_async(mp_image, ts_ms)
            pose_lm.detect_async(mp_image, ts_ms)

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
            if pose_res and pose_res.pose_world_landmarks:
                wl = pose_res.pose_world_landmarks[0]  # first person
                body_landmarks = []
                for lm in wl:
                    body_landmarks.append((lm.x, lm.y, lm.z, lm.visibility))

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

            # Send UDP packet if we have any data
            if blend_shapes is not None or body_landmarks is not None:
                packet = pack_frame(blend_shapes, head_rotation, body_landmarks)
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
                face_ok = "FACE" if blend_shapes is not None else "---"
                body_ok = "BODY" if body_landmarks is not None else "---"
                cv2.putText(frame, f"FPS: {fps_display:.1f}  {face_ok} | {body_ok}",
                            (10, h - 15),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

                cv2.imshow("PPParty Tracker", frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
            else:
                # Headless mode — print FPS periodically
                if frame_count == 0:
                    face_ok = "FACE" if blend_shapes is not None else "---"
                    body_ok = "BODY" if body_landmarks is not None else "---"
                    print(f"\rFPS: {fps_display:.1f}  {face_ok} | {body_ok}",
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
    parser.add_argument("--smooth-min-cutoff", type=float, default=1.0,
                        help="One Euro Filter min cutoff Hz — lower = smoother "
                             "when still (default: 1.0)")
    parser.add_argument("--smooth-beta", type=float, default=0.007,
                        help="One Euro Filter speed coefficient — higher = less "
                             "lag when moving fast (default: 0.007)")
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
