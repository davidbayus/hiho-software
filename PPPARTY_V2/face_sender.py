#!/usr/bin/env python3
"""PPParty V2 face sender — webcam to FaceLandmarker to UDP (Pass 2).

Head rotation only, via FaceLandmarker's facial transform matrix.
No blend shapes, no jaw — those are summer calibration work. The goal
here is to prove the two-pass pipeline: body + hands (Pass 1) and face
(Pass 2) land as separate NLA strips and compose cleanly. (Pre-refactor
this was Pass 3 of a three-pass split; arms+hands folded into Pass 1
on 2026-04-29 — see V2_DESIGN.md §5.)

Usage:
    python3 face_sender.py
    python3 face_sender.py --port 11113 --camera 0
    python3 face_sender.py --no-preview

Dependencies:
    pip install mediapipe opencv-python numpy
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
import mediapipe as mp


# ---------------------------------------------------------------------------
# Packet format — PPV2 face packet (PACKET_TYPE_FACE = 0x03)
# ---------------------------------------------------------------------------
# Header (7 bytes): magic PPV2 + version + packet_type + n_faces
# Per face (64 bytes): 16 floats — the 4×4 facial transform matrix, row-major
#
# Max packet size: 7 + 64 = 71 bytes. Tiny.
# ---------------------------------------------------------------------------

MAGIC = b'PPV2'
VERSION = 0x01
PACKET_TYPE_FACE = 0x03

_FACE_MATRIX_FLOATS = 16   # 4×4 transform matrix


# ---------------------------------------------------------------------------
# Face model — auto-downloaded on first run
# ---------------------------------------------------------------------------

FACE_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/latest/face_landmarker.task"
)
FACE_MODEL_FILE = "face_landmarker.task"


def ensure_face_model():
    """Download the FaceLandmarker model on first run; return its path."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    model_dir = os.path.join(script_dir, "models")
    os.makedirs(model_dir, exist_ok=True)
    path = os.path.join(model_dir, FACE_MODEL_FILE)
    if not os.path.exists(path):
        print(f"Downloading {FACE_MODEL_FILE}...")
        urllib.request.urlretrieve(FACE_MODEL_URL, path)
        print(f"  Saved to {path}")
    return path


# ---------------------------------------------------------------------------
# One Euro Filter — same implementation as the body sender
# ---------------------------------------------------------------------------

class OneEuroFilter:
    """One Euro Filter for a single scalar channel."""

    def __init__(self, min_cutoff=1.0, beta=0.02, d_cutoff=1.0):
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
        a_d = self._smoothing_factor(te, self.d_cutoff)
        dx = (x - self._x_prev) / te
        dx_hat = a_d * dx + (1.0 - a_d) * self._dx_prev
        cutoff = self.min_cutoff + self.beta * abs(dx_hat)
        a = self._smoothing_factor(te, cutoff)
        x_hat = a * x + (1.0 - a) * self._x_prev
        self._x_prev = x_hat
        self._dx_prev = dx_hat
        self._t_prev = t
        return x_hat


def make_matrix_filters(min_cutoff=1.0, beta=0.02):
    """One Euro filter for each of the 16 entries in the 4×4 matrix."""
    return [OneEuroFilter(min_cutoff, beta) for _ in range(_FACE_MATRIX_FLOATS)]


# ---------------------------------------------------------------------------
# Packet builder
# ---------------------------------------------------------------------------

def build_face_packet(matrices):
    """Pack face transform data into a PPV2 face packet.

    `matrices` is a list of flat 16-float lists (one per detected face,
    max 1). Each list is a row-major 4×4 facial transform matrix.
    Returns bytes.
    """
    n = min(len(matrices), 1)
    header = struct.pack('4sBBB', MAGIC, VERSION, PACKET_TYPE_FACE, n)
    payload = b''
    for flat in matrices[:1]:
        payload += struct.pack(f'<{_FACE_MATRIX_FLOATS}f', *flat)
    return header + payload


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def run(port, camera_index, no_preview, min_cutoff, beta):
    model_path = ensure_face_model()

    from mediapipe.tasks import python as mp_tasks
    from mediapipe.tasks.python import vision as mp_vision

    base_options = mp_tasks.BaseOptions(model_asset_path=model_path)
    options = mp_vision.FaceLandmarkerOptions(
        base_options=base_options,
        running_mode=mp_vision.RunningMode.VIDEO,
        num_faces=1,
        output_facial_transformation_matrixes=True,
    )
    landmarker = mp_vision.FaceLandmarker.create_from_options(options)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    cap = cv2.VideoCapture(camera_index)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    # 16 One Euro filters — one per matrix entry.
    filters = make_matrix_filters(min_cutoff, beta)

    print(f"Face sender running → UDP 127.0.0.1:{port}  (Ctrl-C to quit)")

    timestamp_ms = 0
    frame_interval_ms = 33   # ~30 FPS target

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("Webcam read failed — exiting.", file=sys.stderr)
                break

            # Mirror mode — flip horizontally so the kid sees a mirror of
            # themselves, matching the body sender. Both passes must share
            # one frame convention or they fight on composition.
            frame = cv2.flip(frame, 1)

            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(
                image_format=mp.ImageFormat.SRGB, data=frame_rgb
            )
            result = landmarker.detect_for_video(mp_image, timestamp_ms)
            timestamp_ms += frame_interval_ms

            matrices = []
            t = time.monotonic()
            if result.facial_transformation_matrixes:
                raw = result.facial_transformation_matrixes[0]
                # Flatten the 4×4 matrix to 16 floats (row-major).
                flat_raw = [float(v) for v in raw.flatten()]
                # Smooth each matrix entry independently.
                flat = [filters[i](flat_raw[i], t)
                        for i in range(_FACE_MATRIX_FLOATS)]
                matrices.append(flat)

            packet = build_face_packet(matrices)
            sock.sendto(packet, ('127.0.0.1', port))

            if not no_preview:
                n_faces = len(matrices)
                # Draw a rough face oval using screen landmarks.
                if result.face_landmarks:
                    lms = result.face_landmarks[0]
                    h, w = frame.shape[:2]
                    # Standard 37-point face oval landmark indices.
                    oval_indices = [
                        10, 338, 297, 332, 284, 251, 389, 356, 454, 323,
                        361, 288, 397, 365, 379, 378, 400, 377, 152, 148,
                        176, 149, 150, 136, 172, 58, 132, 93, 234, 127,
                        162, 21, 54, 103, 67, 109, 10,
                    ]
                    pts = [
                        (int(lms[i].x * w), int(lms[i].y * h))
                        for i in oval_indices
                    ]
                    for a, b in zip(pts, pts[1:]):
                        cv2.line(frame, a, b, (0, 255, 180), 1)

                status = f"Faces: {n_faces}  |  port: {port}"
                cv2.putText(
                    frame, status, (10, 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1,
                )
                cv2.imshow("PPParty V2 — Face Pass", frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break

    except KeyboardInterrupt:
        pass
    finally:
        cap.release()
        cv2.destroyAllWindows()
        sock.close()
        landmarker.close()
        print("Face sender stopped.")


def main():
    parser = argparse.ArgumentParser(description="PPParty V2 face sender")
    parser.add_argument("--port", type=int, default=11113,
                        help="UDP port the V2 face receiver listens on")
    parser.add_argument("--camera", type=int, default=0,
                        help="Webcam index (0 = default)")
    parser.add_argument("--no-preview", action="store_true",
                        help="Disable the preview window (headless mode)")
    parser.add_argument("--smooth-min-cutoff", type=float, default=1.0,
                        help="One Euro filter min cutoff (lower = smoother)")
    parser.add_argument("--smooth-beta", type=float, default=0.02,
                        help="One Euro filter beta (higher = faster response)")
    args = parser.parse_args()

    run(
        port=args.port,
        camera_index=args.camera,
        no_preview=args.no_preview,
        min_cutoff=args.smooth_min_cutoff,
        beta=args.smooth_beta,
    )


if __name__ == "__main__":
    main()
