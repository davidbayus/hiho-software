#!/usr/bin/env python3
"""PPParty V2 Pass 1 sender — webcam to MediaPipe Pose + Hand to UDP.

Standalone Python script. Runs in system Python (NOT inside Blender).
Captures the webcam, runs PoseLandmarker AND HandLandmarker together
in the same process (both in MediaPipe LIVE_STREAM async mode), and
ships a unified body+hands packet to the V2 receiver inside Blender.

Pass 1 is the full-body pass: spine, legs, arms, AND fingers in one
take. Capturing pose + hands together gives same-frame wrist coherence
— the wrist orientation MediaPipe saw matches the wrist orientation
the puppet has at that instant, so the finger projection is consistent
by construction. (Two-pass refactor, 2026-04-29 — see V2_DESIGN.md §5.)

Day 5 testing on M3 confirmed steady 30 FPS with Pose + Hand both
active in LIVE_STREAM async mode. Synchronous VIDEO mode halves FPS
(sequential blocking inference); never use it for multi-landmarker.

Usage:
    python3 mediapipe_sender.py
    python3 mediapipe_sender.py --port 11111 --camera 0
    python3 mediapipe_sender.py --no-preview        # headless

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
# UDP packet format — PACKET_TYPE_BODY (0x01)
# ---------------------------------------------------------------------------
# Header (7 bytes):
#   MAGIC       (4 bytes)  b'PPV2'              PPParty V2 magic
#   VERSION     (1 byte)   0x01                 protocol version
#   PACKET_TYPE (1 byte)   PACKET_TYPE_BODY     0x01
#   N_HANDS     (1 byte)   0, 1, or 2           how many hand blocks follow
#
# Body block (528 bytes, ALWAYS present):
#   33 records of 4 floats (x, y, z, visibility) in MediaPipe
#   pose_world_landmarks coordinates: meters, body-relative,
#   axes aligned to camera world (Y-up).
#
# Hand blocks (per hand, N_HANDS times — 0/1/2):
#   [0]   handedness: 0x00 = Left, 0x01 = Right
#   [1+]  21 hand_world_landmarks × 3 floats (hand-local meters)
#   = 1 + 21 × 3 × 4 = 253 bytes per hand
#
# Total packet size: 7 + 528 + n_hands × 253 = 535 / 788 / 1041 bytes.
# Comfortable for UDP — well under any platform's MTU concerns on
# loopback.
# ---------------------------------------------------------------------------

MAGIC = b'PPV2'
VERSION = 0x01
PACKET_TYPE_BODY = 0x01
PACKET_TYPE_FACE = 0x03   # Pass 2 face packet (face_sender.py)

N_BODY_LANDMARKS = 33
N_HAND_LANDMARKS = 21

# MP pose landmark indices used for the lighter "arms" smoothing tier.
# Calmer arms keep the wrist orientation stable, which keeps the finger
# projection stable on the receiver side.
_POSE_ARM_INDICES = (11, 12, 13, 14, 15, 16)


# ---------------------------------------------------------------------------
# Models — auto-downloaded on first run, cached next to this script
# ---------------------------------------------------------------------------

POSE_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
    "pose_landmarker_lite/float16/latest/pose_landmarker_lite.task"
)
POSE_MODEL_FILE = "pose_landmarker_lite.task"

HAND_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
    "hand_landmarker/float16/latest/hand_landmarker.task"
)
HAND_MODEL_FILE = "hand_landmarker.task"


def _ensure_model(filename, url):
    """Download `filename` from `url` on first run; return on-disk path.

    Models live in a ./models/ folder next to this script so the
    addon zip and the sender script stay self-contained.
    """
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
# One Euro Filter — adaptive low-pass for jitter reduction
#
# Casiez, Roussel, Vogel (CHI 2012). MIT-compatible algorithm.
# Smooths when the signal is still, stays responsive on fast motion.
# Each landmark axis gets its own filter instance (state per channel).
# ---------------------------------------------------------------------------

class OneEuroFilter:
    """One Euro Filter for a single scalar channel.

    Parameters:
        min_cutoff: minimum cutoff frequency (Hz). Lower = more
                    smoothing when the signal is still.
        beta:       speed coefficient. Higher = less lag when the
                    signal is moving fast.
        d_cutoff:   cutoff for the derivative filter. Usually 1.0.
    """

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

        # Filtered derivative.
        a_d = self._smoothing_factor(te, self.d_cutoff)
        dx = (x - self._x_prev) / te
        dx_hat = a_d * dx + (1.0 - a_d) * self._dx_prev

        # Adaptive cutoff: bigger derivative -> less smoothing.
        cutoff = self.min_cutoff + self.beta * abs(dx_hat)
        a = self._smoothing_factor(te, cutoff)
        x_hat = a * x + (1.0 - a) * self._x_prev

        self._x_prev = x_hat
        self._dx_prev = dx_hat
        self._t_prev = t
        return x_hat


def make_body_filters(min_cutoff, beta):
    """One filter per (landmark, axis). 33 landmarks × 3 axes = 99 filters.

    These cover the full pose body — spine, legs, and the non-arm
    landmarks. Arm landmarks (11..16) get a lighter filter pair
    below for steadier wrists.
    """
    return [
        OneEuroFilter(min_cutoff=min_cutoff, beta=beta)
        for _ in range(N_BODY_LANDMARKS * 3)
    ]


def make_arm_filters(min_cutoff=1.0, beta=0.02):
    """Lighter One Euro filters for pose arm landmarks 11..16.

    Calmer arms keep the wrist orientation steady, which keeps the
    receiver's finger projection (anchored to wrist orientation) stable.
    Per-axis filter — replaces the per-axis filters in `body_filters`
    for the 6 arm landmark indices.
    """
    return {
        idx: [OneEuroFilter(min_cutoff, beta) for _ in range(3)]
        for idx in _POSE_ARM_INDICES
    }


# Tip landmarks per MediaPipe Hand topology.
# 4 = thumb tip, 8 = index tip, 12 = middle tip, 16 = ring tip, 20 = pinky tip.
# These are the noisy ones — smallest pixel footprint + lowest model confidence.
HAND_TIP_INDICES = frozenset({4, 8, 12, 16, 20})


def make_hand_filters(min_cutoff=1.2, beta=0.04,
                      tip_min_cutoff=None, tip_beta=None):
    """One Euro filters for 2 hands × 21 landmarks × 3 axes.

    Tip landmarks (4/8/12/16/20) get heavier smoothing when
    tip_min_cutoff/tip_beta are provided — Lever B from
    HAND_ROTATION_NOISE_RESEARCH.md. Tradeoff is real: heavier
    smoothing adds lag during fast motion. Tune via CLI flags.

    With tip_min_cutoff=None and tip_beta=None, all 21 landmarks
    use the same parameters (v2.0.2 behavior).
    """
    tmc = min_cutoff if tip_min_cutoff is None else tip_min_cutoff
    tb  = beta       if tip_beta       is None else tip_beta

    def landmark_filters(j):
        if j in HAND_TIP_INDICES:
            return [OneEuroFilter(tmc, tb) for _ in range(3)]
        return [OneEuroFilter(min_cutoff, beta) for _ in range(3)]

    return [
        [landmark_filters(j) for j in range(N_HAND_LANDMARKS)]
        for _ in range(2)
    ]


# ---------------------------------------------------------------------------
# Packet packing
# ---------------------------------------------------------------------------

def pack_body_packet(landmarks, hands):
    """Pack 33 body landmarks + 0/1/2 hand blocks into a PPV2 body packet.

    Args:
        landmarks: list of 33 tuples (x, y, z, visibility) in meters.
        hands: list of (handedness_str, hand_lms) tuples (0–2 of them):
            handedness_str: 'Left' or 'Right' (MediaPipe label)
            hand_lms: list of 21 (x, y, z) tuples in hand_world coords

    Returns:
        bytes ready to send over UDP.
    """
    n_hands = min(len(hands), 2)
    header = MAGIC + struct.pack('BBB', VERSION, PACKET_TYPE_BODY, n_hands)

    # Body block — always 33 landmarks × 4 floats.
    body_floats = []
    for lm in landmarks:
        body_floats.extend(lm)
    body_block = struct.pack(
        f'<{N_BODY_LANDMARKS * 4}f', *body_floats,
    )

    # Hand blocks.
    hand_blocks = b''
    for handedness_str, lms in hands[:2]:
        h_byte = 0x00 if handedness_str == 'Left' else 0x01
        floats = []
        for x, y, z in lms:
            floats.extend([x, y, z])
        hand_blocks += struct.pack('B', h_byte)
        hand_blocks += struct.pack(f'<{N_HAND_LANDMARKS * 3}f', *floats)

    return header + body_block + hand_blocks


# ---------------------------------------------------------------------------
# Preview overlay — body skeleton + finger chains + FPS readout
# ---------------------------------------------------------------------------

# MediaPipe Pose skeleton — pairs of landmark indices to connect.
# Reference: https://developers.google.com/mediapipe/solutions/vision/pose_landmarker
_POSE_SKELETON = [
    (11, 12),                       # shoulders
    (11, 23), (12, 24), (23, 24),   # torso sides + hip line
    (11, 13), (13, 15),             # left arm  (shoulder -> elbow -> wrist)
    (12, 14), (14, 16),             # right arm
    (23, 25), (25, 27),             # left leg  (hip -> knee -> ankle)
    (24, 26), (26, 28),             # right leg
    (11, 0), (12, 0),               # shoulders -> nose (head proxy)
]

# Finger chains: each starts from wrist (0) and runs to the tip.
_FINGER_CHAINS = (
    (0, 1, 2, 3, 4),
    (0, 5, 6, 7, 8),
    (0, 9, 10, 11, 12),
    (0, 13, 14, 15, 16),
    (0, 17, 18, 19, 20),
)


def _draw_pose_overlay(frame, pose_screen_lms):
    """Draw the body skeleton on `frame`. `pose_screen_lms` may be None."""
    if not pose_screen_lms:
        return
    h, w = frame.shape[:2]
    pts = [(int(lm.x * w), int(lm.y * h)) for lm in pose_screen_lms]
    for a, b in _POSE_SKELETON:
        if a < len(pts) and b < len(pts):
            cv2.line(frame, pts[a], pts[b], (255, 200, 0), 2)
    for pt in pts:
        cv2.circle(frame, pt, 4, (0, 128, 255), -1)


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
# Main loop: webcam -> Pose + Hand -> UDP
# ---------------------------------------------------------------------------

def run(args):
    """Main capture/send loop. Returns when the user quits or the camera dies."""
    pose_model_path = args.model_pose or _ensure_model(POSE_MODEL_FILE, POSE_MODEL_URL)
    hand_model_path = _ensure_model(HAND_MODEL_FILE, HAND_MODEL_URL)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    target = (args.host, args.port)

    # MediaPipe LIVE_STREAM mode delivers landmarker results asynchronously
    # via callbacks. Synchronous VIDEO mode would block the frame loop for
    # both inferences sequentially and halve the FPS. Running both
    # landmarkers async lets MediaPipe overlap inference with capture so
    # the loop runs at camera rate. Day 5 testing on M3 confirmed steady
    # 30 FPS with Pose + Hand both active. We park the latest result in
    # a single-element list so the closure can mutate it without nonlocal.
    pose_result_box = [None]
    hand_result_box = [None]

    def on_pose(result, _output_image, _timestamp_ms):
        pose_result_box[0] = result

    def on_hand(result, _output_image, _timestamp_ms):
        hand_result_box[0] = result

    BaseOptions = mp.tasks.BaseOptions
    VisionRunningMode = mp.tasks.vision.RunningMode
    PoseLandmarker = mp.tasks.vision.PoseLandmarker
    PoseLandmarkerOptions = mp.tasks.vision.PoseLandmarkerOptions
    HandLandmarker = mp.tasks.vision.HandLandmarker
    HandLandmarkerOptions = mp.tasks.vision.HandLandmarkerOptions

    pose_options = PoseLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=pose_model_path),
        running_mode=VisionRunningMode.LIVE_STREAM,
        num_poses=1,
        result_callback=on_pose,
    )
    hand_options = HandLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=hand_model_path),
        running_mode=VisionRunningMode.LIVE_STREAM,
        num_hands=2,
        result_callback=on_hand,
    )

    cap = cv2.VideoCapture(args.camera)
    if not cap.isOpened():
        print(f"ERROR: cannot open camera {args.camera}", file=sys.stderr)
        sys.exit(1)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)

    actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"Camera opened: {actual_w}x{actual_h}")
    print(f"Sending body+hands packets to {target[0]}:{target[1]}")
    print(
        "Press 'q' in the preview window to quit"
        if not args.no_preview else "Press Ctrl+C to quit"
    )

    body_filters = make_body_filters(
        min_cutoff=args.smooth_min_cutoff,
        beta=args.smooth_beta,
    )
    arm_filters = make_arm_filters()
    hand_filters = make_hand_filters(
        min_cutoff=args.smooth_min_cutoff,
        beta=args.smooth_beta,
        tip_min_cutoff=args.smooth_tip_min_cutoff,
        tip_beta=args.smooth_tip_beta,
    )

    fps_display = 0.0
    fps_counter = 0
    fps_window_start = time.time()

    pose_lm = PoseLandmarker.create_from_options(pose_options)
    hand_lm = HandLandmarker.create_from_options(hand_options)
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("Camera read failed, retrying...")
                time.sleep(0.05)
                continue

            # Mirror mode — flip horizontally so the kid sees a mirror of
            # themselves. Same convention the face sender uses. All passes
            # must share one frame convention or they fight on composition.
            frame = cv2.flip(frame, 1)

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

            # Dispatch BOTH landmarkers asynchronously. Each call returns
            # immediately; results land in their boxes via callbacks.
            ts_ms = int(time.monotonic() * 1000)
            pose_lm.detect_async(mp_image, ts_ms)
            hand_lm.detect_async(mp_image, ts_ms)

            # Read whatever's most recent (may be from this frame or one
            # frame back — that's the cost of async, but it's cheap
            # compared to halving the FPS).
            pose_result = pose_result_box[0]
            hand_result = hand_result_box[0]

            t_now = time.monotonic()
            landmarks = None
            hands = []

            # --- Body block (always present when pose detected) ---
            if pose_result and pose_result.pose_world_landmarks:
                wl = pose_result.pose_world_landmarks[0]
                filtered = []
                for j, lm in enumerate(wl):
                    # Arm landmarks (11..16) get the lighter filter pair;
                    # the rest of the body uses the standard body filters.
                    if j in arm_filters:
                        af = arm_filters[j]
                        fx = af[0](lm.x, t_now)
                        fy = af[1](lm.y, t_now)
                        fz = af[2](lm.z, t_now)
                    else:
                        fi = j * 3
                        fx = body_filters[fi](lm.x, t_now)
                        fy = body_filters[fi + 1](lm.y, t_now)
                        fz = body_filters[fi + 2](lm.z, t_now)
                    filtered.append((fx, fy, fz, lm.visibility))
                landmarks = filtered

            # --- Hand blocks ---
            if hand_result and hand_result.handedness:
                for i, (handedness_cats, world_lms) in enumerate(
                    zip(hand_result.handedness, hand_result.hand_world_landmarks)
                ):
                    handedness_str = handedness_cats[0].category_name  # 'Left'/'Right'
                    hand_idx = min(i, 1)
                    lms = []
                    for j, lm in enumerate(world_lms):
                        x = hand_filters[hand_idx][j][0](lm.x, t_now)
                        y = hand_filters[hand_idx][j][1](lm.y, t_now)
                        z = hand_filters[hand_idx][j][2](lm.z, t_now)
                        lms.append((x, y, z))
                    hands.append((handedness_str, lms))

            # Only ship a packet if we have a body. (No body = no useful
            # data to drive the rig; receiver holds prior pose.)
            if landmarks is not None:
                packet = pack_body_packet(landmarks, hands)
                sock.sendto(packet, target)

            # FPS counter: rolling 1-second window.
            fps_counter += 1
            now = time.time()
            if now - fps_window_start >= 1.0:
                fps_display = fps_counter / (now - fps_window_start)
                fps_counter = 0
                fps_window_start = now
                if args.no_preview:
                    body_status = "BODY" if landmarks else "----"
                    n_hands = len(hands)
                    print(
                        f"\rFPS: {fps_display:.1f}  {body_status}  hands={n_hands}",
                        end='', flush=True,
                    )

            if not args.no_preview:
                if pose_result and pose_result.pose_landmarks:
                    _draw_pose_overlay(frame, pose_result.pose_landmarks[0])
                if hand_result and hand_result.handedness:
                    for handedness_cats, screen_lms in zip(
                        hand_result.handedness, hand_result.hand_landmarks
                    ):
                        _draw_hand_overlay(
                            frame, screen_lms, handedness_cats[0].category_name,
                        )

                n_hands = len(hands)
                n_pose = 1 if landmarks else 0
                status = (
                    f"FPS: {fps_display:.1f}  "
                    f"Body: {n_pose}  Hands: {n_hands}  |  port: {args.port}"
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
                cv2.imshow("PPParty V2 — Pass 1 (Body + Hands)", frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
    finally:
        pose_lm.close()
        hand_lm.close()
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
        description="PPParty V2 Pass 1 sender (webcam to Pose + Hand to UDP)",
    )
    parser.add_argument("--port", type=int, default=11111,
                        help="UDP target port (default: 11111)")
    parser.add_argument("--host", type=str, default="127.0.0.1",
                        help="UDP target host (default: 127.0.0.1)")
    parser.add_argument("--camera", type=int, default=0,
                        help="Camera device index (default: 0)")
    parser.add_argument("--width", type=int, default=640,
                        help="Capture width (default: 640)")
    parser.add_argument("--height", type=int, default=480,
                        help="Capture height (default: 480)")
    parser.add_argument("--no-preview", action="store_true",
                        help="Headless mode (no preview window)")
    parser.add_argument("--model-pose", type=str, default=None,
                        help="Override pose_landmarker_lite.task path")
    parser.add_argument("--smooth-min-cutoff", type=float, default=1.2,
                        help="One Euro min cutoff Hz "
                             "(lower = smoother when still; default: 1.2)")
    parser.add_argument("--smooth-beta", type=float, default=0.04,
                        help="One Euro beta "
                             "(higher = less lag when moving fast; "
                             "default: 0.04)")
    # Lever B knobs — disabled by default in v2.0.4 after v2.0.3 trial felt
    # rubbery on deliberate gestures. Defaults match the global cutoff/beta,
    # so tip landmarks behave identically to non-tip landmarks (= v2.0.2
    # behavior). Filter-class plumbing in make_hand_filters() retained as
    # an inert escape valve for the future step-by-step-bake reframe (see
    # HAND_TIP_SMOOTHING_DESIGN.md status block + project_software_identity_reframe_2026-05-06.md).
    parser.add_argument("--smooth-tip-min-cutoff", type=float, default=1.2,
                        help="One Euro min cutoff Hz for fingertip landmarks "
                             "(4/8/12/16/20). v2.0.4 default: 1.2 (Lever B "
                             "disabled = matches global). Pass 0.5 to "
                             "re-enable v2.0.3 Lever B aggressiveness, or "
                             "0.7-0.9 for a lighter Lever B retune.")
    parser.add_argument("--smooth-tip-beta", type=float, default=0.04,
                        help="One Euro beta for fingertip landmarks. v2.0.4 "
                             "default: 0.04 (Lever B disabled = matches "
                             "global). Pass 0.005 to re-enable v2.0.3 Lever "
                             "B aggressiveness, or 0.01-0.02 for a lighter "
                             "Lever B retune.")
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
