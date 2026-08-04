#!/usr/bin/env python3
"""PPParty V2 Pass 2 sender — webcam to MediaPipe Pose + Hand to UDP.

Pass 2 captures arms AND hands together so the wrist is coherent:
the wrist orientation MediaPipe saw matches the wrist orientation the
puppet has at that instant. We run PoseLandmarker (for shoulders,
elbows, wrists — landmarks 11-16) AND HandLandmarker (for finger
articulation) in the same process on the same frame, and ship a
unified packet to the V2 hand receiver.

Two landmarkers in one sender bends V2 §3.1's "one landmarker per
pass" rule. The original concern was V1's FPS cliff, which Phase 0
showed lives Blender-side (GN tree + Verlet on the tracked rig).
V2's bones-only capture path sidesteps that cliff, and Phase 0
already validated that M3-class hardware fits three landmarkers in
the 33ms frame budget on the sender side.

This is Pass 2 of V2's layered capture workflow. Run it AFTER the
body pass is baked. While it runs, Blender plays back the body NLA
strip so the kid sees their already-recorded torso + legs while
they perform arms + hands on top.

Usage:
    python3 hand_sender.py
    python3 hand_sender.py --port 11112 --camera 0
    python3 hand_sender.py --no-preview

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
# Packet format — PPV2 arms + hands packet (PACKET_TYPE_ARMS_HANDS = 0x04)
# ---------------------------------------------------------------------------
# Header (7 bytes): magic, version, packet_type, n_hands
#
# Pose arms block (96 bytes, ALWAYS present): 6 pose landmarks × 4 floats
#     (x, y, z, visibility) in MediaPipe pose_world_landmarks coords.
#     Order: L_shoulder(11), R_shoulder(12), L_elbow(13), R_elbow(14),
#            L_wrist(15), R_wrist(16).
#
# Hand blocks (per hand, N_HANDS times — 0/1/2 hands):
#     [0]   handedness: 0x00 = Left, 0x01 = Right
#     [1+]  21 hand_world_landmarks × 3 floats (hand-local meters)
#
# Max packet size: 7 + 96 + 2 × 253 = 609 bytes.
# ---------------------------------------------------------------------------

MAGIC = b'PPV2'
VERSION = 0x01
PACKET_TYPE_ARMS_HANDS = 0x04   # Pass 2 unified arms + hands packet

N_HAND_LANDMARKS = 21
N_POSE_ARM_LANDMARKS = 6        # lms 11..16: shoulders, elbows, wrists
_HAND_BYTES_PER_HAND = 1 + N_HAND_LANDMARKS * 3 * 4  # handedness + xyz floats
_POSE_ARMS_BYTES = N_POSE_ARM_LANDMARKS * 4 * 4       # 6 lms × (x,y,z,vis)

# MP pose landmark indices we ship in the arms block.
POSE_ARM_INDICES = (11, 12, 13, 14, 15, 16)


# ---------------------------------------------------------------------------
# Models — auto-downloaded on first run
# ---------------------------------------------------------------------------

HAND_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
    "hand_landmarker/float16/latest/hand_landmarker.task"
)
HAND_MODEL_FILE = "hand_landmarker.task"

POSE_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
    "pose_landmarker_lite/float16/latest/pose_landmarker_lite.task"
)
POSE_MODEL_FILE = "pose_landmarker_lite.task"


def _ensure_model(filename, url):
    """Download `filename` from `url` on first run; return on-disk path."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    model_dir = os.path.join(script_dir, "models")
    os.makedirs(model_dir, exist_ok=True)
    path = os.path.join(model_dir, filename)
    if not os.path.exists(path):
        print(f"Downloading {filename}...")
        urllib.request.urlretrieve(url, path)
        print(f"  Saved to {path}")
    return path


# ---------------------------------------------------------------------------
# One Euro Filter — same implementation as body + face senders
# ---------------------------------------------------------------------------

class OneEuroFilter:
    """One Euro Filter for a single scalar channel."""

    def __init__(self, min_cutoff=1.2, beta=0.04, d_cutoff=1.0):
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


def make_hand_filters(min_cutoff=1.2, beta=0.04):
    """Filters for 2 hands × 21 landmarks × 3 axes."""
    return [
        [[OneEuroFilter(min_cutoff, beta) for _ in range(3)]
         for _ in range(N_HAND_LANDMARKS)]
        for _ in range(2)
    ]


def make_pose_arm_filters(min_cutoff=1.0, beta=0.02):
    """Filters for 6 pose arm landmarks × 4 channels (x, y, z, visibility).

    Pose-side smoothing is gentler (lower beta) than hands because the
    upper-arm chain doesn't need fast finger-style response — calmer
    arms keep the wrist orientation steady, which keeps the hand
    projection stable.
    """
    return [[OneEuroFilter(min_cutoff, beta) for _ in range(4)]
            for _ in range(N_POSE_ARM_LANDMARKS)]


# ---------------------------------------------------------------------------
# Packet builder
# ---------------------------------------------------------------------------

def build_arms_hands_packet(arm_lms, hands):
    """Pack arm pose landmarks + hand data into a PPV2 arms+hands packet.

    `arm_lms` is a list of 6 (x, y, z, visibility) tuples for pose
    landmarks 11..16 in MP pose_world coords. Always present.

    `hands` is a list of (handedness_str, hand_lms) where:
        handedness_str: 'Left' or 'Right' (MediaPipe label)
        hand_lms: list of 21 (x, y, z) tuples in hand_world coords

    Returns bytes.
    """
    n_hands = min(len(hands), 2)
    header = struct.pack('4sBBB', MAGIC, VERSION, PACKET_TYPE_ARMS_HANDS, n_hands)

    # Pose arms block — always 6 landmarks × 4 floats.
    arm_floats = []
    for x, y, z, vis in arm_lms:
        arm_floats.extend([x, y, z, vis])
    arm_block = struct.pack(f'<{N_POSE_ARM_LANDMARKS * 4}f', *arm_floats)

    # Hand blocks.
    hand_blocks = b''
    for handedness_str, lms in hands[:2]:
        h_byte = 0x00 if handedness_str == 'Left' else 0x01
        floats = []
        for x, y, z in lms:
            floats.extend([x, y, z])
        hand_blocks += struct.pack('B', h_byte)
        hand_blocks += struct.pack(f'<{len(floats)}f', *floats)

    return header + arm_block + hand_blocks


# ---------------------------------------------------------------------------
# Preview overlay
# ---------------------------------------------------------------------------

# Pose arm chain: shoulder→elbow→wrist per side. Indices into
# `pose_landmarks` (the screen-space 33-landmark list).
_ARM_CHAIN_L = [11, 13, 15]   # L_shoulder → L_elbow → L_wrist
_ARM_CHAIN_R = [12, 14, 16]   # R_shoulder → R_elbow → R_wrist

# Finger chains: each starts from wrist (0) and runs to the tip.
_FINGER_CHAINS = (
    (0, 1, 2, 3, 4),
    (0, 5, 6, 7, 8),
    (0, 9, 10, 11, 12),
    (0, 13, 14, 15, 16),
    (0, 17, 18, 19, 20),
)


def _draw_arm_overlay(frame, pose_screen_lms):
    """Draw the arm chain (shoulder→elbow→wrist, both sides) on `frame`."""
    if not pose_screen_lms:
        return
    h, w = frame.shape[:2]
    pts = [(int(lm.x * w), int(lm.y * h)) for lm in pose_screen_lms]
    for chain, color in ((_ARM_CHAIN_L, (0, 200, 255)),
                         (_ARM_CHAIN_R, (255, 150, 0))):
        for a, b in zip(chain, chain[1:]):
            cv2.line(frame, pts[a], pts[b], color, 2)
        for i in chain:
            cv2.circle(frame, pts[i], 5, color, -1)


def _draw_hand_overlay(frame, screen_lms, label):
    """Draw the hand finger skeleton on `frame`."""
    h, w = frame.shape[:2]
    pts = [(int(lm.x * w), int(lm.y * h)) for lm in screen_lms]
    color = (0, 200, 255) if label == 'Left' else (255, 150, 0)
    for chain in _FINGER_CHAINS:
        for a, b in zip(chain, chain[1:]):
            cv2.line(frame, pts[a], pts[b], color, 2)
    for pt in pts:
        cv2.circle(frame, pt, 3, color, -1)
    cv2.putText(
        frame, label, pts[0],
        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1,
    )


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def run(port, camera_index, no_preview, min_cutoff, beta):
    hand_model_path = _ensure_model(HAND_MODEL_FILE, HAND_MODEL_URL)
    pose_model_path = _ensure_model(POSE_MODEL_FILE, POSE_MODEL_URL)

    from mediapipe.tasks import python as mp_tasks
    from mediapipe.tasks.python import vision as mp_vision

    # LIVE_STREAM mode for both landmarkers — async dispatch with results
    # delivered via callback. Synchronous VIDEO mode would block the
    # frame loop for both inferences sequentially and halve the FPS;
    # LIVE_STREAM lets MediaPipe overlap inference with capture so the
    # loop runs at camera rate. Same pattern the body sender uses.
    pose_result_box = [None]
    hand_result_box = [None]

    def on_pose(result, _output_image, _timestamp_ms):
        pose_result_box[0] = result

    def on_hand(result, _output_image, _timestamp_ms):
        hand_result_box[0] = result

    hand_options = mp_vision.HandLandmarkerOptions(
        base_options=mp_tasks.BaseOptions(model_asset_path=hand_model_path),
        running_mode=mp_vision.RunningMode.LIVE_STREAM,
        num_hands=2,
        result_callback=on_hand,
    )
    pose_options = mp_vision.PoseLandmarkerOptions(
        base_options=mp_tasks.BaseOptions(model_asset_path=pose_model_path),
        running_mode=mp_vision.RunningMode.LIVE_STREAM,
        num_poses=1,
        result_callback=on_pose,
    )
    hand_landmarker = mp_vision.HandLandmarker.create_from_options(hand_options)
    pose_landmarker = mp_vision.PoseLandmarker.create_from_options(pose_options)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    cap = cv2.VideoCapture(camera_index)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    hand_filters = make_hand_filters(min_cutoff, beta)
    arm_filters = make_pose_arm_filters()

    print(f"Pass 2 sender running → UDP 127.0.0.1:{port}  (Ctrl-C to quit)")

    # Rolling 1-second FPS counter — shown in preview so we can read the
    # actual frame rate while the two-landmarker budget is being tested.
    fps_display = 0.0
    fps_counter = 0
    fps_window_start = time.time()

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("Webcam read failed — exiting.", file=sys.stderr)
                break

            # Mirror mode — flip horizontally so the kid sees a mirror of
            # themselves, matching body + face senders. All three passes
            # must share one frame convention or they fight on composition.
            frame = cv2.flip(frame, 1)

            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(
                image_format=mp.ImageFormat.SRGB, data=frame_rgb
            )

            # Dispatch BOTH landmarkers asynchronously. Each call returns
            # immediately; results land in their boxes via callbacks.
            ts_ms = int(time.monotonic() * 1000)
            pose_landmarker.detect_async(mp_image, ts_ms)
            hand_landmarker.detect_async(mp_image, ts_ms)

            # Read whatever's most recent (may be from this frame or a
            # frame or two ago — that's the cost of async, but it's
            # cheap compared to halving the FPS).
            pose_result = pose_result_box[0]
            hand_result = hand_result_box[0]

            t = time.monotonic()

            # --- Pose arms block (6 landmarks 11..16) ---
            arm_lms = []
            if pose_result and pose_result.pose_world_landmarks:
                world_lms = pose_result.pose_world_landmarks[0]
                for slot, mp_idx in enumerate(POSE_ARM_INDICES):
                    lm = world_lms[mp_idx]
                    x = arm_filters[slot][0](lm.x, t)
                    y = arm_filters[slot][1](lm.y, t)
                    z = arm_filters[slot][2](lm.z, t)
                    vis = arm_filters[slot][3](lm.visibility, t)
                    arm_lms.append((x, y, z, vis))
            else:
                # No pose result yet (first few frames) or no pose detected.
                # Send zeroed arms with vis=0 so the receiver holds prior pose.
                arm_lms = [(0.0, 0.0, 0.0, 0.0)] * N_POSE_ARM_LANDMARKS

            # --- Hand blocks ---
            hands = []
            if hand_result and hand_result.handedness:
                for i, (handedness_cats, world_lms) in enumerate(
                    zip(hand_result.handedness, hand_result.hand_world_landmarks)
                ):
                    handedness_str = handedness_cats[0].category_name  # 'Left'/'Right'
                    hand_idx = min(i, 1)
                    lms = []
                    for j, lm in enumerate(world_lms):
                        x = hand_filters[hand_idx][j][0](lm.x, t)
                        y = hand_filters[hand_idx][j][1](lm.y, t)
                        z = hand_filters[hand_idx][j][2](lm.z, t)
                        lms.append((x, y, z))
                    hands.append((handedness_str, lms))

            packet = build_arms_hands_packet(arm_lms, hands)
            sock.sendto(packet, ('127.0.0.1', port))

            # Update rolling-window FPS.
            fps_counter += 1
            now = time.time()
            if now - fps_window_start >= 1.0:
                fps_display = fps_counter / (now - fps_window_start)
                fps_counter = 0
                fps_window_start = now
                if no_preview:
                    print(f"FPS: {fps_display:.1f}  arms={int(bool(arm_lms))}  hands={len(hands)}")

            if not no_preview:
                # Arm chain overlay (uses screen-space pose landmarks).
                if pose_result and pose_result.pose_landmarks:
                    _draw_arm_overlay(frame, pose_result.pose_landmarks[0])
                # Hand finger skeleton overlay (uses screen-space hand landmarks).
                if hand_result and hand_result.handedness:
                    for handedness_cats, screen_lms in zip(
                        hand_result.handedness, hand_result.hand_landmarks
                    ):
                        _draw_hand_overlay(
                            frame, screen_lms, handedness_cats[0].category_name,
                        )

                n_hands = len(hands)
                n_pose = 1 if pose_result and pose_result.pose_world_landmarks else 0
                status = (
                    f"FPS: {fps_display:.1f}  "
                    f"Arms: {n_pose}  Hands: {n_hands}  |  port: {port}"
                )
                # Color FPS green if >=27 (close to 30 target), yellow 20-27,
                # red <20 — quick visual gauge of how the two-landmarker
                # budget is holding up.
                if fps_display >= 27:
                    fps_color = (0, 230, 0)
                elif fps_display >= 20:
                    fps_color = (0, 220, 220)
                else:
                    fps_color = (0, 0, 230)
                cv2.putText(
                    frame, status, (10, 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, fps_color, 1,
                )
                cv2.imshow("PPParty V2 — Pass 2 (Arms + Hands)", frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break

    except KeyboardInterrupt:
        pass
    finally:
        cap.release()
        cv2.destroyAllWindows()
        sock.close()
        hand_landmarker.close()
        pose_landmarker.close()
        print("Pass 2 sender stopped.")


def main():
    parser = argparse.ArgumentParser(description="PPParty V2 Pass 2 sender (arms + hands)")
    parser.add_argument("--port", type=int, default=11112,
                        help="UDP port the V2 hand receiver listens on")
    parser.add_argument("--camera", type=int, default=0,
                        help="Webcam index (0 = default)")
    parser.add_argument("--no-preview", action="store_true",
                        help="Disable the preview window (headless mode)")
    parser.add_argument("--smooth-min-cutoff", type=float, default=1.2,
                        help="One Euro filter min cutoff (lower = smoother)")
    parser.add_argument("--smooth-beta", type=float, default=0.04,
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
