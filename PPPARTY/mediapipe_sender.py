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
                # Draw face landmarks
                if face_res and face_res.face_landmarks:
                    for lm in face_res.face_landmarks[0]:
                        x = int(lm.x * frame.shape[1])
                        y = int(lm.y * frame.shape[0])
                        cv2.circle(frame, (x, y), 1, (0, 255, 0), -1)

                # Draw pose landmarks
                if pose_res and pose_res.pose_landmarks:
                    for lm in pose_res.pose_landmarks[0]:
                        x = int(lm.x * frame.shape[1])
                        y = int(lm.y * frame.shape[0])
                        cv2.circle(frame, (x, y), 4, (0, 128, 255), -1)

                # FPS text
                cv2.putText(frame, f"FPS: {fps_display:.1f}", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

                # Status text
                face_ok = "FACE" if blend_shapes is not None else "---"
                body_ok = "BODY" if body_landmarks is not None else "---"
                cv2.putText(frame, f"{face_ok} | {body_ok}", (10, 60),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)

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
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
