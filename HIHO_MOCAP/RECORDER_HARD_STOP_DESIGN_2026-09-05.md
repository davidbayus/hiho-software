# Recorder hard stop + end countdown — design, 2026-09-05 (laptop, BASEMENT)

## The failure, as measured today
Calibration take `HIHO_CALIBRATIONS/2026-09-05_14-02-15`, six cameras, length set to 60 s:

| camera | frames written | finished at |
|---|---|---|
| Camera_1..5 | 3600 (= 60 s at 60 fps) | 14:03:36 |
| Camera_0 | 3070 | 14:04:27, 51 s after the others |

Camera_0 delivered about 28 frames per second instead of 60. The recorder counts frames, not
seconds (`core/camera_manager.py`, `is_recording` stays true while any camera is still writing;
both wait loops in `external/record_take.py` never look at the clock), so the take ran on until
David stopped it. Same disease as 2026-08-01 (camera at ~5 fps, keyboard on a hub) and 2026-08-22
(two cameras at ~25 fps, RAM swap). Today the hubs were clean (2+2+2, nothing else on them, verified
from the USB tree) and no heavy apps were open, so the likely cause is the camera itself: a dim view
makes a C922 halve its frame rate, or a cable. The speed probe names it.

David's ask today, his words: "the length kept going past the set 60sec" and "add in the countdown
at the end of the recording from 5 sec out, so the student knows when the recording is about to end."

## Build 1.4.48 — stop at the clock, say why (backlog 2026-08-01 Build A + C)
One file: `external/record_take.py`. The camera manager is untouched.

1. Both wait loops (windowed and headless) exit when `recording_elapsed_sec >= duration + 2 s`
   grace, not only when every camera has hit its frame target. Two seconds covers the normal
   one-frame stagger and the equalize step; a healthy take never sees the deadline.
2. On a deadline exit, call the existing `stop_recording()` (equalize on, 3 s timeout): healthy
   cameras are already closed at their target; a laggard is cut where it is, so the mismatch is
   exposed, not hidden.
3. Honest report, always: `RECORDING_REPORT.txt` in the take folder with per-camera frames
   delivered / expected, effective fps, elapsed seconds, and the verdict. The same words go to the
   panel: on a mismatch the error reads
   `Camera 0 delivered 3070 of 3600 frames (~28 fps): check its light, cable, or hub. Stopped at 62 s.`
   instead of a generic "mismatched frame counts".
4. Q closes the recording window like ESC (the 08-01 "had to quit out" complaint).

Not changed: frame-count parity as the success condition (FreeMoCap rejects mismatched takes);
the countdown before recording; anything inside Blender. A take that fails this way stays on disk
without `HIHO_RECORDING_INFO.json`, as today.

Test before install: a headless run of `record_take.main()` against a fake camera manager whose
"Camera 0" writes at half speed; expected: exit within duration + grace, report file written,
error text names Camera 0 with the right numbers. Then live: the next calibration recording.

## Build 1.4.49 — end-of-take countdown (David, today)
Same file, same loop. When the remaining recording time drops to 5 s: the window overlay reads
`ENDING IN 5` ... `ENDING IN 1` and the Mac says each number aloud (same `say` helper as the start
countdown, so a performer away from the screen hears it), then "done" as now. Headless runs speak
the numbers too. Nothing else changes.

Test: fake-manager run shows the five overlay strings and five `say` calls at 5,4,3,2,1 s
remaining. Then live on the first take of the day.

## Order today
1. 1.4.48 built, tested headless, installed, verified on the re-recorded calibration.
2. 1.4.49 built, tested headless, installed, verified on the first take.
One change per zip so either can be reverted alone. Commit after David's live OK.
