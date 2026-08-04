"""Simultaneous-coverage check: in how many opening frames could the floor
corners (0, 3, 4) actually triangulate (2+ cams decoding in the SAME frame)?
Usage: python corner_check2.py <recording_folder> [n_frames]"""
import sys
from pathlib import Path
import cv2
import numpy as np

rec = Path(sys.argv[1]).expanduser()
n_frames = int(sys.argv[2]) if len(sys.argv) > 2 else 300

from freemocap.core_processes.capture_volume_calibration.charuco_stuff.charuco_board_definition import charuco_5x3
bd = charuco_5x3()
aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_250)
board = cv2.aruco.CharucoBoard(
    (bd.number_of_squares_width, bd.number_of_squares_height), 1.0, 0.8, aruco_dict)
detector = cv2.aruco.CharucoDetector(board)

vids = sorted(rec.glob("Camera_*.mp4")) or sorted((rec / "synchronized_videos").glob("Camera_*.mp4"))
n_corners = 8
STEP = 5
# decoded[cam][frame_idx] = set of corner ids
per_cam = []
for vid in vids:
    cap = cv2.VideoCapture(str(vid))
    rows = []
    for f in range(n_frames):
        ok, frame = cap.read()
        if not ok:
            break
        if f % STEP:
            continue
        corners, ids, _, _ = detector.detectBoard(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))
        rows.append(set(ids.flatten().tolist()) if ids is not None else set())
    cap.release()
    per_cam.append(rows)

n_samples = min(len(r) for r in per_cam)
FLOOR_CORNERS = (0, 3, 4)  # origin, y-direction, x-direction
good_frames = []
for s in range(n_samples):
    cams_per_corner = [sum(1 for cam in per_cam if c in cam[s]) for c in range(n_corners)]
    if all(cams_per_corner[c] >= 2 for c in FLOOR_CORNERS):
        good_frames.append(s * STEP)

print(f"checked {n_samples} sampled frames across first {n_frames}")
print(f"frames where floor corners 0, 3 AND 4 all triangulate simultaneously: {len(good_frames)}")
if good_frames:
    print("frame numbers:", good_frames[:20], "..." if len(good_frames) > 20 else "")
    print("VERDICT: floor solve has usable frames" + 
          (" (but only barely — aim for dozens, not a handful)" if len(good_frames) < 10 else ""))
else:
    # diagnose which corner is the blocker
    for c in FLOOR_CORNERS:
        n_ok = sum(1 for s in range(n_samples)
                   if sum(1 for cam in per_cam if c in cam[s]) >= 2)
        print(f"  corner {c}: simultaneous 2-cam decode in {n_ok}/{n_samples} sampled frames")
    print("VERDICT: NO usable still frame -> floor solve cannot succeed on this take")
