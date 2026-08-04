"""Money-spot scout: instead of guessing board placements one still-take at a
time, record ONE take slowly sliding the board around the floor (pausing a
beat at each candidate spot), then run this. It scans the whole take for
moments where the floor corners (0, 3, 4) all have simultaneous 2-camera
decode — i.e., spots where the floor solve would succeed — and saves a
snapshot image of the board at each passing moment, so you can see exactly
where on the floor it was and tape that spot.

Usage (inside freemocap-env):
    python spot_scout.py <recording_folder>

Snapshots land in <recording_folder>/SPOT_SCOUT/ as passing_XXs_camN.png.
No passing moments -> the board is too small for this rig: use a bigger board.
"""
import sys
from pathlib import Path

import cv2

FLOOR_CORNERS = (0, 3, 4)
STEP = 5          # sample every 5th frame
MIN_RUN = 12      # samples in a row required (~1 second of solid coverage)


def main() -> int:
    rec = Path(sys.argv[1]).expanduser()
    from freemocap.core_processes.capture_volume_calibration.charuco_stuff.charuco_board_definition import (
        charuco_5x3,
    )
    bd = charuco_5x3()
    aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_250)
    board = cv2.aruco.CharucoBoard(
        (bd.number_of_squares_width, bd.number_of_squares_height), 1.0, 0.8, aruco_dict)
    detector = cv2.aruco.CharucoDetector(board)

    vids = sorted(rec.glob("Camera_*.mp4")) or sorted(
        (rec / "synchronized_videos").glob("Camera_*.mp4"))
    if not vids:
        print(f"no Camera_*.mp4 in {rec}")
        return 2

    caps = [cv2.VideoCapture(str(v)) for v in vids]
    fps = caps[0].get(cv2.CAP_PROP_FPS) or 60.0
    per_frame = []   # list of (frame_idx, per-cam corner-id sets)
    idx = 0
    while True:
        frames = []
        alive = True
        for cap in caps:
            ok, f = cap.read()
            if not ok:
                alive = False
                break
            frames.append(f)
        if not alive:
            break
        if idx % STEP == 0:
            sets = []
            for f in frames:
                _, ids, _, _ = detector.detectBoard(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY))
                sets.append(set(ids.flatten().tolist()) if ids is not None else set())
            per_frame.append((idx, sets, frames))
        idx += 1

    def passing(sets) -> bool:
        return all(sum(1 for s in sets if c in s) >= 2 for c in FLOOR_CORNERS)

    flags = [passing(sets) for _, sets, _ in per_frame]
    runs = []
    start = None
    for i, ok in enumerate(flags):
        if ok and start is None:
            start = i
        if not ok and start is not None:
            runs.append((start, i))
            start = None
    if start is not None:
        runs.append((start, len(flags)))
    runs = [(a, b) for a, b in runs if b - a >= MIN_RUN]

    if not runs:
        print("NO passing spots found anywhere in this take.")
        print("The board never had a full second of 2-camera coverage of corners "
              f"{FLOOR_CORNERS}. Bigger board (or closer cameras) needed.")
        for cap in caps:
            cap.release()
        return 1

    out = rec / "SPOT_SCOUT"
    out.mkdir(exist_ok=True)
    print(f"{len(runs)} passing spot(s):")
    for a, b in runs:
        mid = (a + b) // 2
        frame_idx, sets, frames = per_frame[mid]
        secs = frame_idx / fps
        best_cam = max(range(len(sets)), key=lambda c: len(sets[c]))
        snap = out / f"passing_{int(secs):03d}s_cam{best_cam}.png"
        cv2.imwrite(str(snap), frames[best_cam])
        t0 = per_frame[a][0] / fps
        t1 = per_frame[b - 1][0] / fps
        print(f"  {t0:5.1f}s - {t1:5.1f}s  -> snapshot {snap.name} "
              f"(cam {best_cam} saw {len(sets[best_cam])}/8 corners)")
    print(f"\nSnapshots in {out} — the board's position in the photo IS the money "
          "spot. Tape it, orientation and all.")
    for cap in caps:
        cap.release()
    return 0


if __name__ == "__main__":
    sys.exit(main())
