#!/usr/bin/env python3
"""V2 Phase 0 spike — landmarker-gated MediaPipe sender + FPS logger.

Fork of SOFTWARE/PPPARTY/mediapipe_sender.py (V1 alpha.56). The V1 archive
is read-only knowledge; this spike is the V2 sandbox version we run to
validate the V2_DESIGN.md FPS thesis: that running ONE landmarker at a
time clears the 12-15 FPS hand-on-face cliff that motivated V2.

What changed vs V1:
  - --mode {body,hands,face,all} gates which detect_async calls run.
    "all" reproduces V1 baseline. "body" / "hands" / "face" are the V2
    pass modes. Body-only is the primary thesis test.
  - --scenario LABEL is written to the FPS log so we can tag samples
    with what the performer is doing (idle, hand-on-face, etc.).
  - --log PATH appends one CSV row per second:
        timestamp_iso, scenario, mode, fps, face_active, body_active, hands_active
  - --duration SECONDS auto-quits after N seconds (so a session is repeatable).
  - At quit, prints summary: mean / p50 / p95 / min FPS for the run.
  - Models default to V1's PPPARTY/models/ if present (no re-download).

UDP sending and One Euro filtering are kept identical to V1 alpha.56 so
"--mode all" is a faithful baseline. We only strip the palm-basis math
and the blend-shape preview bars (cosmetic; do not affect FPS).

Usage examples:
    # Baseline run — V1 behavior, all three landmarkers
    python mediapipe_sender_spike.py --mode all --scenario baseline_idle --duration 30

    # V2 thesis — body-only with hand near face
    python mediapipe_sender_spike.py --mode body --scenario body_hand_on_face --duration 30
"""

import argparse
import csv
import math
import os
import socket
import statistics
import struct
import sys
import time
import urllib.request
from datetime import datetime

import cv2
import numpy as np
import mediapipe as mp


# ---------------------------------------------------------------------------
# Constants (mirrored from V1 alpha.56)
# ---------------------------------------------------------------------------

MAGIC = b'MPPT'
VERSION = 0x01
FLAG_HAS_FACE = 0x01
FLAG_HAS_BODY = 0x02
FLAG_HAS_HANDS = 0x04

BLACKLISTED = {
    "_neutral", "jawForward", "jawRight", "jawLeft",
    "mouthDimpleLeft", "mouthDimpleRight", "cheekPuff",
}

FACE_MODEL_URL = "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task"
POSE_MODEL_URL = "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task"
HAND_MODEL_URL = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task"

FACE_MODEL_FILE = "face_landmarker.task"
POSE_MODEL_FILE = "pose_landmarker_lite.task"
HAND_MODEL_FILE = "hand_landmarker.task"

HAND_WRIST = 0
HAND_THUMB_TIP = 4
HAND_INDEX_TIP = 8


# ---------------------------------------------------------------------------
# Model loading — prefer V1's downloaded models to skip re-fetching
# ---------------------------------------------------------------------------

def ensure_model(filename, url):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    v1_path = os.path.normpath(
        os.path.join(script_dir, '..', '..', 'PPPARTY', 'models', filename))
    if os.path.exists(v1_path):
        return v1_path
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
# One Euro Filter (verbatim from V1)
# ---------------------------------------------------------------------------

class OneEuroFilter:
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


def make_face_filters(min_cutoff=1.0, beta=0.007):
    return [OneEuroFilter(min_cutoff=min_cutoff, beta=beta) for _ in range(55)]


def make_body_filters(min_cutoff=0.8, beta=0.01):
    return [OneEuroFilter(min_cutoff=min_cutoff, beta=beta) for _ in range(102)]


def make_hand_filters(min_cutoff=0.8, beta=0.015):
    return [OneEuroFilter(min_cutoff=min_cutoff, beta=beta) for _ in range(12)]


# ---------------------------------------------------------------------------
# Head rotation (verbatim from V1)
# ---------------------------------------------------------------------------

def matrix_to_euler(mat):
    r00, r01, r02 = mat[0][0], mat[0][1], mat[0][2]
    r10, r11, r12 = mat[1][0], mat[1][1], mat[1][2]
    r20, r21, r22 = mat[2][0], mat[2][1], mat[2][2]
    sy = math.sqrt(r00 * r00 + r10 * r10)
    singular = sy < 1e-6
    if not singular:
        pitch = math.atan2(r21, r22)
        yaw = math.atan2(-r20, sy)
        roll = math.atan2(r10, r00)
    else:
        pitch = math.atan2(-r12, r11)
        yaw = math.atan2(-r20, sy)
        roll = 0.0
    return pitch, -roll, yaw


# ---------------------------------------------------------------------------
# UDP packet packing — simplified, no palm basis (FPS thesis only)
# ---------------------------------------------------------------------------

def pack_frame(blend_shapes, head_rotation, body_landmarks,
               body_center=None, hands=None):
    flags = 0x00
    body = b''

    if blend_shapes is not None:
        flags |= FLAG_HAS_FACE
        rot = head_rotation if head_rotation else (0.0, 0.0, 0.0)
        body += struct.pack('<55f', *blend_shapes, *rot)

    if body_landmarks is not None:
        flags |= FLAG_HAS_BODY
        flat = []
        for lm in body_landmarks:
            flat.extend([lm[0], lm[1], lm[2], lm[3]])
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
# Main loop — gated landmarkers + FPS logger
# ---------------------------------------------------------------------------

def run(args):
    mode = args.mode
    use_face = mode in ("face", "all")
    use_pose = mode in ("body", "all")
    use_hand = mode in ("hands", "all")

    print(f"[spike] mode={mode}  scenario={args.scenario}  duration={args.duration}s")
    print(f"[spike] active landmarkers: "
          f"face={use_face}  body={use_pose}  hands={use_hand}")

    face_model = args.model_face or ensure_model(FACE_MODEL_FILE, FACE_MODEL_URL) if use_face else None
    pose_model = args.model_pose or ensure_model(POSE_MODEL_FILE, POSE_MODEL_URL) if use_pose else None
    hand_model = args.model_hand or ensure_model(HAND_MODEL_FILE, HAND_MODEL_URL) if use_hand else None

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    target = (args.host, args.port)

    face_result_container = [None]
    pose_result_container = [None]
    hand_result_container = [None]

    def on_face_result(result, output_image, timestamp_ms):
        face_result_container[0] = result

    def on_pose_result(result, output_image, timestamp_ms):
        pose_result_container[0] = result

    def on_hand_result(result, output_image, timestamp_ms):
        hand_result_container[0] = result

    BaseOptions = mp.tasks.BaseOptions
    VisionRunningMode = mp.tasks.vision.RunningMode

    face_lm = None
    pose_lm = None
    hand_lm = None

    if use_face:
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
        face_lm = FaceLandmarker.create_from_options(face_options)

    if use_pose:
        PoseLandmarker = mp.tasks.vision.PoseLandmarker
        PoseLandmarkerOptions = mp.tasks.vision.PoseLandmarkerOptions
        pose_options = PoseLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=pose_model),
            running_mode=VisionRunningMode.LIVE_STREAM,
            num_poses=1,
            result_callback=on_pose_result,
        )
        pose_lm = PoseLandmarker.create_from_options(pose_options)

    if use_hand:
        HandLandmarker = mp.tasks.vision.HandLandmarker
        HandLandmarkerOptions = mp.tasks.vision.HandLandmarkerOptions
        hand_options = HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=hand_model),
            running_mode=VisionRunningMode.LIVE_STREAM,
            num_hands=2,
            result_callback=on_hand_result,
        )
        hand_lm = HandLandmarker.create_from_options(hand_options)

    cap = cv2.VideoCapture(args.camera)
    if not cap.isOpened():
        print(f"ERROR: Cannot open camera {args.camera}")
        sys.exit(1)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
    actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"[spike] camera: {actual_w}x{actual_h}  -> UDP {target[0]}:{target[1]}")

    # CSV log setup
    log_path = args.log
    log_dir = os.path.dirname(os.path.abspath(log_path))
    os.makedirs(log_dir, exist_ok=True)
    log_is_new = not os.path.exists(log_path)
    log_file = open(log_path, "a", newline="")
    log_writer = csv.writer(log_file)
    if log_is_new:
        log_writer.writerow([
            "timestamp_iso", "scenario", "mode", "fps",
            "face_active", "body_active", "hands_active",
        ])

    face_filters = make_face_filters(min_cutoff=args.smooth_min_cutoff,
                                     beta=args.smooth_beta)
    body_mc = (args.smooth_body_min_cutoff if args.smooth_body_min_cutoff
               is not None else args.smooth_min_cutoff * 0.8)
    body_beta = (args.smooth_body_beta if args.smooth_body_beta
                 is not None else args.smooth_beta * 2.0)
    body_filters = make_body_filters(min_cutoff=body_mc, beta=body_beta)
    hand_mc = (args.smooth_hand_min_cutoff if args.smooth_hand_min_cutoff
               is not None else args.smooth_min_cutoff * 0.8)
    hand_beta = (args.smooth_hand_beta if args.smooth_hand_beta
                 is not None else args.smooth_beta * 1.5)
    hand_filters = make_hand_filters(min_cutoff=hand_mc, beta=hand_beta)

    fps_samples = []  # list of float FPS, one per second
    frame_count = 0
    fps_time = time.time()
    fps_display = 0.0
    start_wall = time.time()

    try:
        while True:
            if args.duration > 0 and (time.time() - start_wall) >= args.duration:
                break

            ret, frame = cap.read()
            if not ret:
                print("Camera read failed, retrying...")
                time.sleep(0.1)
                continue

            frame = cv2.flip(frame, 1)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            ts_ms = int(time.monotonic() * 1000)

            # GATED detect_async — this is the V2 thesis under test
            if face_lm is not None:
                face_lm.detect_async(mp_image, ts_ms)
            if pose_lm is not None:
                pose_lm.detect_async(mp_image, ts_ms)
            if hand_lm is not None:
                hand_lm.detect_async(mp_image, ts_ms)

            blend_shapes = None
            head_rotation = None
            body_landmarks = None

            face_res = face_result_container[0] if use_face else None
            if face_res and face_res.face_blendshapes:
                bs = face_res.face_blendshapes[0]
                blend_shapes = [0.0] * 52
                for i, category in enumerate(bs):
                    if i < 52:
                        name = category.category_name
                        val = category.score
                        if name in BLACKLISTED:
                            val = 0.0
                        blend_shapes[i] = val
                if face_res.facial_transformation_matrixes:
                    mat = face_res.facial_transformation_matrixes[0]
                    head_rotation = matrix_to_euler(mat)

            pose_res = pose_result_container[0] if use_pose else None
            body_center = None
            if pose_res and pose_res.pose_world_landmarks:
                wl = pose_res.pose_world_landmarks[0]
                body_landmarks = []
                for lm in wl:
                    body_landmarks.append((lm.x, lm.y, lm.z, lm.visibility))
                if pose_res.pose_landmarks:
                    il = pose_res.pose_landmarks[0]
                    lh = il[23]
                    rh = il[24]
                    body_center = (
                        (lh.x + rh.x) / 2.0 - 0.5,
                        -((lh.y + rh.y) / 2.0 - 0.5),
                        0.0,
                    )

            t_now = time.monotonic()
            if blend_shapes is not None:
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
                    fi = j * 3
                    fx = body_filters[fi](lm[0], t_now)
                    fy = body_filters[fi + 1](lm[1], t_now)
                    fz = body_filters[fi + 2](lm[2], t_now)
                    filtered_body.append((fx, fy, fz, lm[3]))
                body_landmarks = filtered_body
                if body_center is not None:
                    body_center = (
                        body_filters[99](body_center[0], t_now),
                        body_filters[100](body_center[1], t_now),
                        body_filters[101](body_center[2], t_now),
                    )

            hands = None
            hand_res = hand_result_container[0] if use_hand else None
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
                    thumb_xyz = (wrist_xyz[0] + thumb_off.x,
                                 wrist_xyz[1] + thumb_off.y,
                                 wrist_xyz[2] + thumb_off.z)
                    index_xyz = (wrist_xyz[0] + index_off.x,
                                 wrist_xyz[1] + index_off.y,
                                 wrist_xyz[2] + index_off.z)
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

            if (blend_shapes is not None or body_landmarks is not None
                    or hands is not None):
                packet = pack_frame(blend_shapes, head_rotation,
                                    body_landmarks, body_center, hands)
                sock.sendto(packet, target)

            frame_count += 1
            now = time.time()
            if now - fps_time >= 1.0:
                fps_display = frame_count / (now - fps_time)
                fps_samples.append(fps_display)
                log_writer.writerow([
                    datetime.now().isoformat(timespec="seconds"),
                    args.scenario,
                    mode,
                    f"{fps_display:.2f}",
                    int(blend_shapes is not None),
                    int(body_landmarks is not None),
                    int(hands is not None),
                ])
                log_file.flush()
                frame_count = 0
                fps_time = now

            if not args.no_preview:
                # Body skeleton (orange dots, cyan lines) — only if pose is on
                if pose_res and pose_res.pose_landmarks:
                    plm = pose_res.pose_landmarks[0]
                    h, w = frame.shape[:2]

                    def _px(idx):
                        return (int(plm[idx].x * w), int(plm[idx].y * h))

                    _SKELETON = [
                        (11, 12), (11, 23), (12, 24), (23, 24),
                        (11, 13), (13, 15),
                        (12, 14), (14, 16),
                        (23, 25), (25, 27),
                        (24, 26), (26, 28),
                        (11, 0), (12, 0),
                    ]
                    for a, b in _SKELETON:
                        if a < len(plm) and b < len(plm):
                            cv2.line(frame, _px(a), _px(b), (255, 200, 0), 2)
                    for i, lm in enumerate(plm):
                        x = int(lm.x * w)
                        y = int(lm.y * h)
                        cv2.circle(frame, (x, y), 4, (0, 128, 255), -1)

                # Face dots — only if face is on
                if face_res and face_res.face_landmarks:
                    for lm in face_res.face_landmarks[0]:
                        x = int(lm.x * frame.shape[1])
                        y = int(lm.y * frame.shape[0])
                        cv2.circle(frame, (x, y), 1, (0, 255, 0), -1)

                # Hand skeleton (magenta) — only if hand is on
                if hand_res and hand_res.hand_landmarks:
                    h, w = frame.shape[:2]
                    for hlm in hand_res.hand_landmarks:
                        for lm in hlm:
                            x = int(lm.x * w)
                            y = int(lm.y * h)
                            cv2.circle(frame, (x, y), 2, (200, 80, 220), -1)

                # FPS + status overlay (bottom left)
                h = frame.shape[0]
                tag = f"[{mode}] {args.scenario}"
                face_ok = "FACE" if blend_shapes is not None else "----"
                body_ok = "BODY" if body_landmarks is not None else "----"
                hand_ok = "HAND" if hands is not None else "----"
                cv2.putText(frame,
                            f"FPS:{fps_display:.1f}  {face_ok}|{body_ok}|{hand_ok}",
                            (10, h - 35),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                cv2.putText(frame, tag, (10, h - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 2)

                cv2.imshow("PPParty V2 Spike", frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
            else:
                if frame_count == 0:
                    print(f"\rFPS:{fps_display:.1f}  mode={mode}  scenario={args.scenario}",
                          end='', flush=True)
    finally:
        # Cleanup
        cap.release()
        if not args.no_preview:
            cv2.destroyAllWindows()
        sock.close()
        for lm in (face_lm, pose_lm, hand_lm):
            if lm is not None:
                lm.close()
        log_file.close()

        # Summary stats — drop the first sample (cold start)
        warm = fps_samples[1:] if len(fps_samples) > 1 else fps_samples
        print()
        print("=" * 60)
        print(f"[spike] DONE  mode={mode}  scenario={args.scenario}")
        print(f"        samples (warm, 1Hz): {len(warm)}")
        if warm:
            warm_sorted = sorted(warm)
            n = len(warm_sorted)
            p50 = warm_sorted[n // 2]
            p95_idx = max(0, min(n - 1, int(round(0.95 * (n - 1)))))
            p95 = warm_sorted[p95_idx]
            print(f"        mean : {statistics.fmean(warm):.2f} FPS")
            print(f"        p50  : {p50:.2f} FPS")
            print(f"        p95  : {p95:.2f} FPS")
            print(f"        min  : {min(warm):.2f} FPS")
            print(f"        max  : {max(warm):.2f} FPS")
        print(f"        log  : {os.path.abspath(log_path)}")
        print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="V2 Phase 0 spike — landmarker-gated FPS test"
    )
    parser.add_argument("--mode", choices=["body", "hands", "face", "all"],
                        default="body",
                        help="Which landmarker(s) to run (default: body)")
    parser.add_argument("--scenario", type=str, default="unlabeled",
                        help="Scenario tag written to the FPS log")
    parser.add_argument("--duration", type=float, default=30.0,
                        help="Auto-quit after N seconds (0 = run forever)")
    parser.add_argument("--log", type=str,
                        default=os.path.join(
                            os.path.dirname(os.path.abspath(__file__)),
                            "results", "spike_fps.csv"),
                        help="CSV path to append FPS samples (one row/sec)")
    parser.add_argument("--port", type=int, default=11111)
    parser.add_argument("--host", type=str, default="127.0.0.1")
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--no-preview", action="store_true")
    parser.add_argument("--model-face", type=str, default=None)
    parser.add_argument("--model-pose", type=str, default=None)
    parser.add_argument("--model-hand", type=str, default=None)
    parser.add_argument("--smooth-min-cutoff", type=float, default=1.5)
    parser.add_argument("--smooth-beta", type=float, default=0.02)
    parser.add_argument("--smooth-body-min-cutoff", type=float, default=None)
    parser.add_argument("--smooth-body-beta", type=float, default=None)
    parser.add_argument("--smooth-hand-min-cutoff", type=float, default=None)
    parser.add_argument("--smooth-hand-beta", type=float, default=None)
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
