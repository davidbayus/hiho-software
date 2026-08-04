"""Which charuco corners does each camera decode in the opening window?
Usage: python corner_check.py <recording_folder> [n_frames]"""
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
n_corners = (bd.number_of_squares_width - 1) * (bd.number_of_squares_height - 1)
per_cam = {}
for vid in vids:
    cap = cv2.VideoCapture(str(vid))
    counts = np.zeros(n_corners, dtype=int)
    frames_checked = 0
    for f in range(n_frames):
        ok, frame = cap.read()
        if not ok:
            break
        if f % 5:
            continue
        frames_checked += 1
        corners, ids, _, _ = detector.detectBoard(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))
        if ids is not None:
            for cid in ids.flatten():
                counts[cid] += 1
    cap.release()
    per_cam[vid.stem] = (counts, frames_checked)

print(f"corner decode rate over first {n_frames} frames (sampled every 5th):")
print("            " + "  ".join(f"c{i}" for i in range(n_corners)))
for name, (counts, checked) in per_cam.items():
    pct = (counts / max(checked, 1) * 100).astype(int)
    print(f"{name}:  " + "  ".join(f"{p:2d}" for p in pct) + "   (% of frames)")

stack = np.array([c for c, _ in per_cam.values()])
cams_per_corner = (stack > 0).sum(axis=0)
print("\ncameras decoding each corner at least once:", list(cams_per_corner))
bad = [i for i, n in enumerate(cams_per_corner) if n < 2]
if bad:
    print(f"VERDICT: corners {bad} lack 2-camera coverage -> floor solve WILL fail")
else:
    print("VERDICT: all corners have 2+ camera coverage -> floor solve should succeed")
