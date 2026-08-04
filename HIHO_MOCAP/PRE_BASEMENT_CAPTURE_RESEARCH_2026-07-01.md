# Pre-BASEMENT Capture Research — 2026-07-01 (evening)

**Purpose:** Audit of HIHO MOCAP's capture pipeline + comparison against FreeMoCap upstream and the wider open-source field, ahead of the July 2 BASEMENT capture tests.
**Status:** Research only. No code changed. Per the no-code-before-design rule, anything adopted from here gets its own design note first.
**Sources:** Local code audit (1.4.11 tree), FreeMoCap/skellycam/skellytracker GitHub as of 2026-07-01, Pose2Sim, Caliscope/multiwebcam, recent sync papers (RocSync, VisualSync).

---

## 1. TL;DR

1. **You are already on the best code available.** The live processing env runs FreeMoCap v1.8.2, which is the newest upstream release (April 2026, nothing since). The custom recorder bypass is still justified: issue #650 is still open upstream with no fix.
2. **One free upgrade is sitting unused:** v1.8.2 shipped a new "reprojection outlier rejection" triangulation mode, built specifically for 4+ camera rigs where one bad camera view poisons the skeleton ("ghost skeleton" fix). It is OFF by default and HIHO's `process_take.py` uses defaults, so we've never used it. It's a post-processing switch: takes recorded tomorrow can be processed both ways afterward with zero capture-day risk. **This is the best "better code" opportunity and it costs nothing tomorrow.**
3. **Two settings findings worth testing tomorrow (it's a test day, so test them):**
   - HIHO records at 960×540. FreeMoCap's own docs say 720p minimum. The field (Pose2Sim's accuracy studies) says frame rate matters more than resolution: **720p at 60fps beats 1080p at 30fps** for tracking quality. Worth an A/B against the current 540p30, USB bandwidth permitting.
   - The C922s' autofocus and auto-exposure should be **locked off before calibrating**. Autofocus hunting mid-session silently invalidates the calibration (the lens physically changes). This is likely a real, previously invisible quality leak.
4. **The biggest capture risks tomorrow are the known silent failures** (dim light halving the frame rate, USB port shuffle mis-rotating cameras, corrupt rotations file). All have zero-code mitigations in the checklist below.

---

## 2. Where the code stands (local audit)

### Confirmed healthy
- All 6 serious + 7 medium findings from the 2026-06-09 audit are fixed and shipped in the canonical 1.4.11 build (sentinels, ESC equalize-up, group-kill, loud frame-count mismatches, NaN guards, watched capture launches).
- Recording design is sound: one thread per camera, frame-count-bounded recording, direct-to-disk (no RAM accumulation, the #650 killer), ESC early-stop equalizes counts up with a 3-second laggard window and fails loudly on mismatch.
- The live env matches upstream pins exactly: freemocap 1.8.2, skellycam 2025.09.1097, skellytracker 2025.10.1024, aniposelib 0.4.3, mediapipe 0.10.14. (The `vendor/freemocap` 1.7.4 tree on disk is the RETIRED pre-Option-B code, not what runs.)

### Open weaknesses in the capture path (all previously logged, none new)
| ID | Weakness | Symptom | Tomorrow's mitigation |
|----|----------|---------|----------------------|
| M8 | Recorded fps is *requested*, never *measured*. C922s halve frame rate in dim light. | Skeleton plays at 2× speed, no error. | Light the room hard. Eyeball first take's playback speed. |
| M6 | Camera rotations keyed by USB index; enumeration order unstable across reboots. | Sideways cameras, garbage tracking, invalid calibration. | Run Show Cameras first, every session, and visually confirm each camera's identity and rotation. |
| M10 | `~/.hiho_mocap/camera_rotations.json` corruption is silently swallowed. | All cameras record unrotated. | Confirm rotations look right in Show Cameras before recording (same ritual as M6). |
| M7 | A camera dying mid-take retries forever; no wall-clock failsafe. | Recording appears hung. | Known escape: ESC triggers the 3s-timeout equalize path and reports loudly. |
| M9 | No per-frame timestamps anywhere; equal frame count is treated as sync. | Unevenly dropped frames = mushy fast motion that nothing detects. | Procedural: clap + flashlight sweep at take start (see §5). Code fix is Tier 1.1, post-test. |

### Where recording settings actually live
- `core/camera_manager.py:23-24`: `DEFAULT_RESOLUTION = (960, 540)`, `DEFAULT_FPS = 30`. Camera input MJPG, file output mp4v.
- `external/process_take.py:126`: `ProcessingParameterModel(recording_info_model=recording_info)` — all processing defaults, so outlier rejection off, minimum cameras for triangulation 3 (correct for a 4-cam rig).

---

## 3. Upstream comparison (FreeMoCap GitHub, July 2026)

- **freemocap:** latest release v1.8.2 (2026-04-22). Headline feature: **reprojection outlier rejection** (PR #758, by ajc27), optional per-point rejection of bad camera views during triangulation. Off by default; upstream RFC #782 is collecting feedback on making it default. Also new: `minimum_cameras_for_triangulation` (default 3). **Verified present in David's env.** Nothing in 1.8.x touches recording, sync, timestamps, or macOS.
- **Issue #650** (multi-cam recorder memory crash): still open, untouched since Nov 2024. The HIHO custom recorder remains the right call.
- **skellycam:** v1 (what freemocap uses) frozen since Sept 2025. The v2 rewrite is very active (v2.0.0-alpha.6, June 2026: server architecture, Mac fixes, performance refactor). Notable: skellycam v1 already does `grab()`/`retrieve()` + per-frame `timestamp_ns` + post-hoc timestamp alignment + framerate diagnostic plots — a proven in-family reference implementation for HIHO's own Tier 1.1 timestamp work.
- **skellytracker:** release still MediaPipe 0.10.14. But the development branch now has RTMPose (Mac/CoreML merged 2026-06-17, only ~5-7 fps so not usable yet), ViTPose, and active YOLO persistent-person-ID work — upstream is converging on the same multi-person answer as our Supervision/ByteTrack research. Watch, don't duplicate.
- **aniposelib:** 0.8.0 (May 2026) adds JAX-accelerated optimization, but freemocap pins 0.4.3 and our env matches. Not a drop-in; ignore for now.
- **mediapipe:** 0.10.35 exists but has no new pose/hand models and nothing Apple-Silicon-relevant. skellytracker pins 0.10.14 anyway. Don't touch.

**Net: nothing upstream to adopt tonight except flipping on a feature we already have installed.**

## 4. Field comparison (beyond FreeMoCap)

- **Pose2Sim** (the biomechanics-grade open-source peer): their accuracy studies show dropping 1080p→720p costs almost nothing while dropping fps hurts, and heavy compression barely matters (MJPG artifacts are a non-issue). They also sync unsynchronized cameras in post by cross-correlating keypoint velocities — the sync signal is the mocap data itself. Since HIHO already produces per-camera MediaPipe output, this is a small standalone script someday, and it pairs with directing performers to "start with a jump."
- **Caliscope / multiwebcam** (built by a FreeMoCap community alumnus): the closest analog to our custom recorder. Records a `timestamps.csv` per camera per take, aligns in post, achieves 10-50ms precision. Validates Tier 1.1 exactly, and their hardware philosophy ("dumb webcams are more reliable; camera auto-features cause firmware stalls") independently supports locking the C922 autos off.
- **RocSync (Nov 2025 paper):** a *periodic* blinking LED filmed by all cameras beats a single flash, because it measures drift across the take, not just offset at the start. Cheap upgrade to the Tier 2.2 LED idea when we get there.
- **OpenCV on macOS reality check:** the AVFoundation backend cannot set exposure/focus/white-balance (`cap.set()` silently fails), and `CAP_PROP_FOURCC` MJPG forcing also fails on Mac. Camera control must happen outside OpenCV, via UVC tools. Two good ones: `uvc-util` (compiles from source with one gcc command) or `uvcc` (npm install). Both can lock all four C922s. Order matters: set auto-exposure-mode to manual (value 1) *before* setting exposure-time. Settings can reset on unplug/sleep, so re-run the lock script each session.

---

## 5. Test-day checklist (tomorrow, zero code)

**Rig setup**
1. USB topology: 2 cameras + 2 cameras across two separate Thunderbolt ports (never 3+ behind one port). If a camera won't deliver frames, move ports before debugging anything else.
2. SABRENT hub power button on. macOS camera permission confirmed.
3. Tape cameras down. Any bump after calibration = recalibrate.

**Camera state (the new part)**
4. Show Cameras first: confirm all 4 enumerate, confirm identity and rotation per camera (the ring rig's 90/270 pattern).
5. If possible, lock the autos before calibrating: autofocus off + focus set for capture distance, auto-exposure manual with a short exposure (uvc-util `exposure-time-abs` around 40 to 80, which is 4 to 8 milliseconds), white balance locked to the same value on all four. If no UVC tool is ready, at minimum kill continuous autofocus via Logitech's app.
6. Light the room hard, diffuse, from the front. No windows or bright light behind the performer. Bright light is what makes short exposure and a true full frame rate possible on C922s.

**Calibration ritual**
7. Flat, rigid 5×3 ChArUco. Move it SLOWLY (pause-and-hold beats waving). "Paint" each camera's full view. Every camera must share simultaneous board views with at least one other camera. Cover the actual performance volume, and lay the board flat on the floor at the start for the ground plane.
8. Judge it by number: reprojection error under 1 pixel is usable, 0.5 or under is good, over 2 means redo. (This matches the panel's existing badge thresholds.)
9. Then a 5-second standing-still test take. Check bone-length jitter and floor contact before real takes.

**Every take**
10. Start with the floor-first 5 seconds of standing still (feet visible), plus one loud clap and a flashlight sweep visible to all cameras. The clap/flash costs nothing and can rescue any take where sync looks suspect later.
11. Performer: tight high-contrast clothes, elbows and knees visible, fills the frame, every body part visible to 2-3 cameras.
12. After each take, glance at the printed frame counts (they should match) and play back one video to confirm normal speed (M8 check).

**Experiments to run (it's a test day)**
13. **A/B resolution/fps:** record the same short performance at the current 960×540 @ 30 and at 1280×720 @ 60 (if 4-cam USB bandwidth allows 720p60; if not, try 720p30). Process both, compare skeletons. Field evidence says fps beats pixels.
14. **A/B outlier rejection:** process one good take twice, once as normal and once with `use_triangulate_outlier_rejection=True` (and `minimum_cameras_for_triangulation=3`). Compare ghost-skeleton artifacts and fast-motion mushiness. Post-hoc, re-runnable, zero risk to the recordings.

---

## 6. Software backlog fed by this research (post-test, each needs a design note first)

Ranked by value-for-effort, aligned with `HIHO_ADOPTABLE_INNOVATIONS.md`:

1. **Per-frame timestamps to CSV** (Tier 1.1, audit M9). Now with two proven in-family reference implementations: skellycam v1's `timestamp_ns` logging and multiwebcam's `timestamps.csv`. Timestamp at `grab()` time using the grab/retrieve split (Tier 1.7). Include a frame-drop accountant (gaps in timestamp deltas flagged at capture time).
2. **Expose outlier rejection in `process_take.py`** as a flag (default matching upstream), assuming tomorrow's A/B shows benefit.
3. **Measured-fps truth check** (audit M8): after recording, compare wall-clock elapsed vs frame count per camera; warn loudly under ~25fps effective.
4. **UVC lock script** shipped alongside `HIHO_Record.command` so the camera-settings ritual is one double-click.
5. **Resolution/fps default change** if the A/B supports it.
6. Later: Pose2Sim-style keypoint-velocity sync script; Hampel outlier pass before One Euro smoothing; periodic-LED (RocSync-style) drift measurement for long takes.

**Upstream watch list:** skellycam v2 alphas (the eventual #650 fix), skellytracker development branch (RTMPose CoreML, YOLO person IDs — overlaps the two-person plan), aniposelib 0.8.0, RFC #782 (outlier rejection default).
