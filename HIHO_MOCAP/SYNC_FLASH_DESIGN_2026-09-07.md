# Sync flash box — design, 2026-09-07 (laptop; research day, no code yet)

Companion research: `DR_BAYUS/HIHO_GLOBAL_SHUTTER_CAMERA_RESEARCH_2026-09-07.md` (cameras, trigger pins, prices).
Rule of the house: no code before design. This doc is the design. Builds are listed at the end, one at a time.

## What it is, in one paragraph
A small battery-powered box that makes one bright, sharp flash of light (and one beep) at the start of every take,
visible to every camera in the ring and to any extra device: the iPhone face camera, a second laptop, a student's
phone. Every video then contains the same event on one frame, and lining videos up becomes "find the flash frame in
each," which is how film sets have done it for a century (the clapper slate) and how FreeMoCap's own tool
`skelly_synchronize` does it (its brightness method). The box replaces the hand-held flashlight blink that is already
HIHO doctrine (FACIAL_MOCAP_IPHONE_INTERIM 2026-07-06; SIX_CAMERA_SCALING_RESEARCH §6; FACE_CAPTURE_DESIGN 1.4.32,
Mark Flash / Line Up Face) with something repeatable, hands-free, and eventually automatic.

## Why now (the problem, as measured)
- **08-21:** seven board takes proved the six cameras are NOT time-synchronised. The recorder counts frames and treats
  equal counts as equal time (AUDIT_2026-06-09 M9; RECORDER_HARD_STOP_DESIGN 09-05). No per-frame timestamps yet;
  `external/record_take.py` marks the sidecar as their future landing spot (Tier 1.1).
- **08-01, 08-22, 09-05:** three takes where one camera silently ran slow (5, 25, 28 fps). 1.4.48 now stops at the
  clock and names the laggard. A camera that starts a few frames late and then runs at speed is still invisible.
- **Face capture (1.4.32)** and the **second-computer node** (the path to eight cameras) both already depend on a
  flash. The Art 241 kit (Mac minis, with the laptop present at every test) makes "two machines recording the same
  performer" the normal case this fall, not the exception.
- **Solo performer doctrine:** every cue must reach the performer's ear. David dances the calibration alone and
  cannot see the laptop; the 1.4.51 spoken camera count exists for the same reason.

## Behaviour spec (Phase 1, the button box)
| state | light | sound | what happens |
|---|---|---|---|
| IDLE | dim, slow breathing | none | Box in frame; the cameras' auto-exposure settles with it there. |
| ARMED (button press) | yellow, orange, red, one step per second | one short beep per step | Three seconds. Matches the recorder's spoken start countdown in feel; length configurable. |
| FLASH | full white for 100 ms | one sharp beep on the same instant | 100 ms = 6 frames at 60 fps, 3 at 30, 12 at 120. Long enough that every camera, rolling or global, catches at least two fully lit frames. The FIRST fully lit frame is the marker. The beep is the audio marker for any device that records sound (iPhone, phones). |
| GO | green, 1 s | none | Performer starts. Back to IDLE. |
| END (optional, long takes of 60 s or more) | same flash, no countdown | same beep | Second press at the end. Two markers let Line Up Face measure drift; the iPhone's "60 fps" is not exactly 60 (interim doc). |

Rules:
- **The flash must be big and diffuse, not a pinpoint.** A 24 mm LED at 2 m is about 10 pixels wide and moves a
  frame's mean brightness by nothing; skelly_synchronize looks at mean brightness. Aim for a diffuser at least 10 cm
  across at 50 percent white or more (a frosted printed tube over an LED strip), placed at the volume centre on the
  floor or a mic stand, where every camera in the 270-degree ring already looks. Pointing the strip at a white wall
  or the ceiling lights a big patch and works too, but not every camera sees the same wall.
- **Never plugged into the laptop.** The three Thunderbolt ports are camera hubs, and camera hubs carry cameras only
  (hard rule since 08-01). Battery only. The laptop talks to it over WiFi (Phase 2), never USB.
- The 100 ms flash is too short for webcam auto-exposure to react (it adapts over roughly half a second), so the
  frames after the flash are not darkened. Keep the IDLE light dim for the same reason.

## Parts (Build A: zero solder)
| part | about | why |
|---|---|---|
| ESP32 dev board (classic ESP32 DevKit or ESP32-S3) | $8 | brain; WiFi for Phase 2; USB-C for programming |
| WS2812B "NeoPixel" strip, 5 V, 1 m, 60 LEDs, with a JST pigtail | $15 | the flash; one data wire, no MOSFET, no relay; doubles as the countdown colours |
| piezo buzzer module (3-pin) | $2 | the beeps |
| momentary push-button module | $2 | arm |
| Dupont jumper wires, female-female and female-male | $5 | no soldering anywhere |
| USB power bank, 5 V, 2 A or more (owned) | $0 | power; 60 LEDs at 50 percent white for 100 ms is fine on a 2 A bank |
| printed diffuser tube, white or frosted PETG, 1/4-20 nut in the base | filament | Kobra Max; fits a mic stand or sits on the floor |
| **Total** | **about $32** | |

Tidier brain: an M5Stack ATOM Lite or ATOM Matrix (about $10 to $20, cased, with a button and a Grove port). The
Matrix's own 5x5 LEDs are too small to be the flash but fine for bench tests.

Firmware: MicroPython or Arduino, roughly 60 lines: button, countdown, flash, go; a WiFi command triggers the same
sequence. A 4D ART CLUB session can build it.

## Software side (addon, laptop, one build at a time, after David approves this doc)
**Build S1: "Find Flash" (single-machine diagnostic).** After a take, scan the first N seconds (default 10) of each
`Camera_X.mp4`. Two statistics per frame: mean brightness (skelly_synchronize's method) and the brightest-region
brightness (a high percentile of a blurred frame; this is what catches a small flash). The first frame whose jump
exceeds the threshold is the flash frame. Report per camera, in the panel and in `RECORDING_REPORT.txt`:

    Flash: Camera_0 f=182  Camera_1 f=182  Camera_2 f=183  Camera_3 f=182  Camera_4 f=185 (3 late)  Camera_5 f=182

Verdict: all within one frame = green. Otherwise name the camera, in plain words, the way 1.4.48 names a laggard.
Store the indexes in `HIHO_RECORDING_INFO.json`. No trimming on the single-machine rig (frame-count start stays the
rule); this is a check, like the board-read badge. It closes today's blind spot: a camera that started late but ran
at speed.

**Build S2: multi-device alignment.** Line Up Face already does this for the iPhone by hand (Mark Flash, Mark Flash,
Line Up). Generalise: any extra video (node laptop, Mac mini, student phone) → find flash → trim to the flash frame
minus a fixed lead → equalise lengths → drop into `synchronized_videos/`. Or shell out to `skelly_synchronize`
(official, handles frame-rate normalisation) and keep our detector for the report. Decision for David: our detector
for both, or their tool for the alignment. Recommendation: their tool for alignment (one-to-one with FreeMoCap), ours
for the report.

**Build S3: WiFi trigger.** `record_take.py` sends one UDP packet to the box when recording starts (after the spoken
countdown). The box runs countdown, flash, go. The recorder writes the send time into the sidecar. No button, no
hands; the performer hears the box, not the laptop.

**Build S4 (later, needs trigger-capable cameras; see the research doc §4).** The same box outputs a 60 Hz pulse
train on six wires and the cameras expose in lockstep. The flash stays as the cross-device marker and the sanity
check. This is the only build that tightens sync; everything above makes misalignment visible or fixable after the
fact.

## Accuracy, honestly
Plus or minus one frame: 16.7 ms at 60 fps, 33 ms at 30. The same tolerance the rig already lives with. The flash
cannot tighten single-machine sync (the cameras still free-run); it makes misalignment visible and makes cross-device
alignment possible. Only Build S4 changes the physics.

## Test plan
1. **Bench:** box at the volume centre, one 30 s take. Find Flash reports the same index (within one) on all six.
2. **Break it on purpose:** keyboard and mouse on a camera hub (the 08-01 failure) and confirm the report names the
   starved camera; unplug and replug one camera during the countdown and confirm the late start is named.
3. **iPhone:** one face take with the box instead of the flashlight; Mark Flash on both sides lands on the beep and
   flash; Line Up Face plays in sync; the second flash at 60 s shows the measured drift.
4. **Two machines** (when the node or a mini is ready): same take from both, align, process as one FreeMoCap session.

## Not doing
- No audio sync on the rig side (the OpenCV recorder writes silent video). The beep is for the phones.
- No infrared flash (the C922 and Brio have IR-cut filters). Visible white for everyone.
- No changes to `core/camera_manager.py`; the report lives in `external/record_take.py` like 1.4.48.
- No USB connection to the laptop, ever.

## Open questions for David
1. Box placement: floor centre, or a mic stand at head height?
2. Countdown length: match the recorder's spoken five, or a shorter three?
3. Who builds it: a bench evening (David + Claude), or a 4D ART CLUB session?
4. Build order: S1 (the check) first, or the hardware first so the check has something to find?
