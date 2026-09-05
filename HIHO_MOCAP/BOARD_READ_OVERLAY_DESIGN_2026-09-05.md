# Live board-read badge in the camera windows — design, 2026-09-05 (BASEMENT, David's ask)

David, mid-calibration argument: "can we get a live tracker update in the windows, is that possible? so we
can confirm each cam can see the board?" The argument itself was the reason: he sees the board in every
tile, and the solver still only used part of what each camera saw. Seeing the board and reading the
board are different things, and only the second one calibrates. Today's numbers: from E and F the board
was ~158 px wide and mostly read at 6 of 8 corners; the solver keeps a frame only at 6 or more
(aniposelib boards.py:496, our 7 -> 6 patch); E's focal length solved 13 % off.

## What the badge shows (1.4.50, `external/record_take.py` + the two launch operators)
On every camera tile in the calibration recording window (countdown and recording) and in Show Cameras:

    board 8/8     green   the solver will keep this frame for this camera (6 or more corners)
    board 5/8     amber   partial read, thrown away by the solver
    board 0/8     red     nothing read
    read 37%      running share of sampled frames this camera has read at 6+ corners since recording began

So the dance becomes guided: hold until the far cameras go green, move on when they do.

## How
- Same detector and board as the solve: `cv2.aruco.CharucoBoard(size=[5,3], squareLength=1,
  markerLength=0.8, DICT_4X4_250)` (freemocap `charuco_5x3()`), legacy `detectMarkers` +
  `interpolateCornersCharuco` exactly as aniposelib does, so the count matches the solver's.
- Frames are downscaled to 640 px on the long side before detection; all cameras are sampled at
  most 4 times a second from the main loop (the capture/encode threads are untouched). Cost on the
  M4: about 4 ms per camera per sample, roughly a tenth of one core. The 1.4.48 load watcher
  reports if a recording ever starves.
- Opt-in flag `--board-overlay`; `record_calibration` and the Show Cameras preview pass it. Plain
  takes do not (no board, no cost).
- Failure mode: if the detector import fails, the badge reads "board ?" and recording continues.

## Test
Headless, against today's saved calibration frames: frame 180 of camera A must read 8/8 and of
camera E 6/8, matching the solver's own 2D detections for that frame. Then live on the 120 s
calibration: David watches E and F turn green when the board is tilted toward them.
