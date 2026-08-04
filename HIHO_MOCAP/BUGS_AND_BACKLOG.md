# PPParty Addon — Bugs & Backlog

**Last updated:** 2026-05-12
**Source:** Real BASEMENT mocap sessions on May 9 and May 12, 2026.

This is the consolidated friction list from actually running the multi-cam pipeline end-to-end. Nothing here is theoretical — every item was hit in practice. The addon work checks itself against this list; each operator we ship gets to cross items off.

## Headline

**Every bug from May 12 was at the FreeMoCap GUI / orchestration layer.** The underlying pieces — Blender, Anipose, MediaPipe, the custom recorder, the calibration math — all worked fine when invoked directly. The 13-second CLI export vs 15-minute GUI hang is the proof. This list IS the case for the PPParty addon: the addon doesn't have to reinvent the engine, it has to replace the brittle layer above it.

---

## The 8 bugs from May 9 install (already worked around)

These are the obstacle course the May 9 install ran through. Working around them is now in our muscle memory; the addon's job is to make sure no student ever sees them.

1. **SABRENT hub physical power button** — must be pressed; cameras don't enumerate otherwise.
   *Stays external (physical).* → Setup guide.
2. **macOS UVC bandwidth ceiling** — 4× C922 on one hub fails. Working split: 2 cams on hub + 2 cams on Anker USB-C-to-A adapters into separate Mac USB-C ports.
   *Stays external (physical).* → Setup guide.
3. **opencv-python / opencv-contrib-python pip conflict** — FreeMoCap's auto-fix doesn't actually run pip. Manual: `pip uninstall opencv-python opencv-contrib-python; pip install opencv-contrib-python==4.8.1.78`.
   *Stays external (one-time env setup).* → Setup guide.
4. **FreeMoCap Issue #650** — built-in multi-cam recorder accumulates frames in RAM, save thread fails silently.
   *Already worked around.* → Custom `record_calibration.py` writes direct-to-disk. Absorb into addon as internal module.
5. **Frame-count parity required** — FreeMoCap rejects videos that differ by even 1 frame across cameras.
   *Already handled.* → Recorder is frame-count-bounded by design.
6. **Calibration radio buttons hidden** — until the synchronized-videos status check passes.
   *Eliminated by integration.* → Addon doesn't have hidden-because-not-ready UI states.
7. **Anipose hardcoded `len(o) >= 7`** at `freemocap_anipose.py:2089` — broken for 5×3 board (only 8 corners). Patched to `>= 6` on this laptop.
   *Active patch on this laptop.* → File upstream PR. Save patch snippet to `MOCAP_CALIBRATION_FILES/` so env is re-buildable.
8. **"Auto Open in Blender" checkbox** — does NOT trigger the .blend save. (See May 12 #10 — this escalated.)
   *Eliminated by integration.* → Addon doesn't subprocess Blender; it IS Blender.

---

## New bugs from May 12

9. **FreeMoCap doesn't save reprojection error to disk.** The calibration math computes the accuracy metric internally but no log line, no TOML field, no JSON output. The number disappears with the terminal. We had to write a post-hoc PnP-based scorer to recover it.
   *Severity: Medium.* → Addon displays accuracy badge right after calibration (excellent / good / workable / recalibrate). Prototype already at `MOCAP_CALIBRATION_FILES/check_calibration_accuracy.py`.

10. **Bug #8 escalated on macOS 26.4.1: "hang" → "SIGABRT crash."** What used to silently hang now actively crashes Python with EXC_CRASH. Thread name in crash report: `ProcessMotionCaptureDataThreadWorker`. All mocap data was already on disk; only the final Blender export step crashed.
    *Severity: **High** (data is recoverable, but pipeline appears to fail).* → Eliminated by integration.

11. **`Record_Calibration.command` is named for calibration but does body capture too.** Same script, different intent. Misleading for students.
    *Severity: Low.* → Rename to `record_take` with explicit Calibration / Body Capture toggle in the addon.

12. **FreeMoCap's "Choose Blender Executable" picker doesn't propagate the selection.** Selected `/Applications/Blender.app/Contents/MacOS/Blender` correctly via the file picker. Clicked Open. FreeMoCap's stored path stayed at the literal placeholder string `"BLENDER EXECUTABLE NOT FOUND"`. Subsequent exports failed.
    *Severity: **High** (the documented recovery path doesn't actually work).* → Eliminated by integration. Addon runs inside Blender; no path-picking needed.

13. **FreeMoCap's QProcess invocation of Blender hangs at 0% CPU for 15+ minutes.** The exact same `Blender --background --python run_simple.py -- [args]` command runs to completion in 13 seconds when invoked from a terminal. Bug is somewhere in how FreeMoCap's worker thread wires stdio / environment to the subprocess.
    *Severity: **Critical** (this is the load-bearing bug — without a workaround, you cannot get a .blend out of FreeMoCap on macOS 26).* → Eliminated by integration. Addon doesn't subprocess Blender at all.

14. **"Synchronize videos" checkbox in Import Videos dialog defaults to wrong value.** Checking it (the responsible-looking option) breaks the frame-locked custom-recorder workflow. Leaving unchecked is correct but non-obvious.
    *Severity: Medium.* → Eliminated by integration. Addon defaults are correct; checkbox doesn't exist.

15. **Tab navigation: Process Data → Export Data.** The natural workflow expectation is "I clicked Process, give me my .blend" but the user has to switch tabs to find the export button.
    *Severity: Low (compounds with #14 and #8 into general UI loss).* → Eliminated by integration. Addon is one N-panel.

16. **Exported .blend lives buried at `~/freemocap_data/recording_sessions/[session]/[session].blend`.** Non-obvious location, deeply nested, hard to find for non-experts.
    *Severity: Low.* → Addon writes (or auto-copies) to `MOCAP_TAKES/` automatically.

17. **The exported .blend includes ~80 tracker empties + bone-mesh cones + 4 video planes.** "FreeMoCap raw" structure. Students open it and see chaos instead of a clean rig.
    *Severity: Medium (this is the bottleneck for the library concept per May 10 handoff).* → "Tidy" operator hides these into a "FreeMoCap Raw Data" collection. Preserves, doesn't delete.

18. **Mocap rig is constraint-driven by tracker empties.** Each MediaPipe landmark has its own Action; 82 Actions live on the empties, not on the armature. Students can't push to NLA or layer takes until baked.
    *Severity: Medium.* → "Bake & Flatten" operator bakes constraint-driven rig pose into a single Action on the armature. Paper-prototyped manually on 2026-05-12; pattern validated.

19. **Video file paths in the exported .blend are relative to the FreeMoCap session folder.** Move the .blend (e.g., copy to `MOCAP_TAKES/`) → videos break → magenta-wall placeholders.
    *Severity: Medium.* → Addon writes absolute paths by default. Separate "Pack for sharing" operator for when student wants to take their work to another machine.

20. **Two similarly-named video folders confuse the "Find Missing Files" workflow.** `synchronized_videos/` holds raw `Camera_X.mp4`; `annotated_videos/` holds `Camera_X_mediapipe.mp4`. The .blend references the annotated ones. Naive "Find Missing Files" pointed at synchronized_videos doesn't help.
    *Severity: Low.* → Eliminated by integration. Addon manages references.

21. **macOS file picker doesn't dive into .app bundles by default.** Students need to know `⌘+Shift+G` to navigate to a path inside an .app, or that double-clicking an .app in a picker sometimes enters the bundle.
    *Severity: Low.* → Eliminated alongside #12.

22. **Third-party `Step_Motion.py` addon has buggy `unregister()`.** Throws `ValueError: list.remove(x): x not in list` on Blender shutdown. Harmless — fires after .blend is saved — but adds noise to the log and might confuse a student.
    *Severity: Cosmetic.* → Not our bug. Document in setup guide: either uninstall this addon, or note that the shutdown noise is benign.

---

## Eliminated by integration (the case for the addon, in one section)

These bugs simply don't exist when PPParty IS the front-end and runs inside Blender:

- Bug #6 (radio button visibility)
- Bug #8 (Auto-Open foot-gun)
- Bug #10 (SIGABRT crash on auto-open)
- Bug #12 (Blender executable picker doesn't propagate)
- Bug #13 (subprocess hangs at 0% CPU)
- Bug #14 (Synchronize checkbox default)
- Bug #15 (tab navigation)
- Bug #20 (which video folder to point at)
- Bug #21 (.app bundle file picker)

**Nine bugs deleted by architecture choice.** This is what "the addon IS the front-end" buys us.

---

## Needs an explicit operator

These need code in the addon:

- **Tidy operator** — handles Bug #17. Moves tracker empties, bone-mesh cones, video planes into a "FreeMoCap Raw Data" collection. Preserves everything.
- **Bake & Flatten operator** — handles Bug #18. Bakes constraint-driven rig pose into a single Action on the armature.
- **Retarget operator** (parametric rig system) — separate design doc; not on today's bug list but cross-references the May 10 handoff.
- **Save to Library operator** — handles Bug #16. Auto-copies the baked .blend to `MOCAP_TAKES/` (and eventually to `HIHO_MOCAP/`) with sensible default naming.
- **Pack for Sharing operator** — handles Bug #19. Packs video textures into the .blend for portability.
- **Calibration Accuracy badge** — handles Bug #9. Wraps `check_calibration_accuracy.py`. Shows green/yellow/red verdict + the pixel number right after calibration.
- **Capture operator** — replaces `Record_Calibration.command`. Toggles Calibration / Body Capture mode. Renames the script per Bug #11.

---

## Needs setup-guide documentation

These stay external concerns — physical/environmental — but a "first-time user" doc should cover them so no one re-runs the obstacle course:

- Bug #1 (hub power button)
- Bug #2 (USB topology — 2 on hub + 2 on adapters)
- Bug #3 (opencv pip conflict — one-time fix)
- Bug #7 (anipose patch — apply once after conda env creation; save snippet to `MOCAP_CALIBRATION_FILES/anipose_patch_line2089.txt`)
- Bug #22 (Step_Motion addon noise — uninstall or ignore)

Recording technique (lazy-Susan, face-up board, central overlap zone) also lives here.

---

## Pedagogy wins to preserve

Things the addon design should bake in, not strip out:

- **"Open your take and see your puppet skeleton move"** — annotated videos in the .blend show the MediaPipe skeleton overlay drawn on the original footage. Students see their captured performance with the rig overlaid. Keep this as a feature, not noise.
- **The accuracy badge after calibration** — a green / yellow / red verdict turns a hidden technical metric into a teachable concept. "0.33 px is excellent" is a number a student can be proud of.
- **Batch capture, batch process rhythm** — capture multiple takes in a row, process them while away from the rig. Teach this loop explicitly so students don't stall the human on the AI.
- **Movement-description naming** (David's design call) — clip names should describe what's in them (`walk_cycle.blend`, `wave_hello.blend`), not session-day numbers. Lets clips travel across projects and be searchable.
- **Local library is contribution, not consumption** — students aren't downloading clips, they're adding to the shared library. Citizenship moment.

---

## Post-v1.0 deferred cleanup

24. **"Open Camera Views" layout is asymmetric (1-left + 3-stacked-right) instead of clean 2x2.** Stage 3 Step 2 shipped 2026-05-23 with this known cosmetic flaw. Root cause: `bpy.ops.screen.area_split(factor=0.5)` on a brand-new window doesn't actually produce 50/50 splits, so the "split the biggest VIEW_3D" heuristic keeps picking right-side cells. All 4 cameras display live; only the visual symmetry is off. **v1.1 fix candidates:** (a) bundle a pre-built `.blend` with the 2x2 layout, append it instead of programmatic splits; (b) iterate splits with measured corrections; (c) switch to 4 separate windows per camera. Decide after observing v1.0 club usage.

23. **Rationalize the take/processing/output folder structure.** David flagged 2026-05-23 (during Stage 3 design sign-off): the current spread is genuinely hard to track —
    - `~/Desktop/CALIBRATION_RECORDINGS/<timestamp>/` (raw .mp4s from Camera Manager)
    - `MOCAP_TAKES/` (some takes)
    - `~/freemocap_data/recording_sessions/` (FreeMoCap's session output)
    - `~/Desktop/HIHO_MOCAP/` (baked rigs)
    - `HIHO_MOCAP_LIBRARY/` (curated library)

    Each of these landed for a different reason and they don't compose. v1.0 ships with the existing layout — the test gates in `STAGE_3_DESIGN.md` lean on the working CALIBRATION_RECORDINGS path. v1.1 work: consolidate to a single configurable HIHO MOCAP project folder with subfolders per take, where everything for one capture (raw videos, calibration TOML used, processed .npy, baked .blend) lives in one place.

    *Severity: Medium.* Not a bug, but compounding friction. Pre-v1.1 design pass needed.

---

## Source-of-truth pointers

- **Live recorder + launchers + accuracy scorer:** `SOFTWARE/PPPARTY/MOCAP_CALIBRATION_FILES/`
- **MOCAP_TAKES (raw exports, light, iCloud-synced):** `SOFTWARE/PPPARTY/MOCAP_TAKES/`
- **HIHO_MOCAP (baked, ready-to-use rigs):** `~/Desktop/HIHO_MOCAP/`
- **Raw FreeMoCap session folders (heavy, laptop-only):** `~/freemocap_data/recording_sessions/`
- **PPParty architecture doc:** `SOFTWARE/PPPARTY/ARCHITECTURE.md`
- **Memory: BASEMENT install state:** `project_basement_multicam_install`
- **Memory: PPParty V3 canonical state:** `project_ppparty_current_state`
- **Memory: deliverable framing:** `project_ppparty_deliverable_is_baked_animation`

---

## 2026-07-22 — Live-use paper cuts (the "artist intuition" list)

Found during the verification day at BASEMENT. All display/UX — none touched data
integrity. David's closing directive names the theme for the next design cycle:
**"it works — now streamline the design for artist intuition."** Design doc first
(ARTIST_INTUITION), then one build per fix. The common disease: **the panel makes
the artist read truncated file paths to know what's loaded.**

1. **Path fields hide identity.** The Calib field shows `…a_calibration.toml` —
   which day's? The lost-in-pickers episode came from this. Fields should show
   take names/dates ("Jul 22, 2:34 pm"), never squeezed paths.
2. **Pickers open wherever they last wandered.** Each should open in its home:
   Take → HIHO_CAPTURES, Calib → HIHO_CALIBRATIONS, Face take → HIHO_FACE_TAKES.
   Related: TWO calibration cabinets exist (Desktop `HIHO_CALIBRATIONS/` and
   FreeMoCap's own `~/freemocap_data/calibrations/`) — surface only ours.
3. **Load Face Take rejects a picked folder.** Students will pick the take
   folder every time; the operator should find the `_cal.csv` inside it.
4. **Map the Volume uses the panel Calib, not the take's own calibration.**
   Wrong-ruler episode: same take read ~0.50 m under a mismatched TOML, ~0.75 m
   under its own (each calibration defines its own origin → ring center shifts).
   Fix: auto-use the calibration the take was processed with. ALSO: the verdict
   can't distinguish "turbulence boundary" from "data ran out" — a center-hugging
   take (jitter 1.0× everywhere sampled) still headlines "~0.50 m" and reads as a
   shrunken volume. Say "clean as far as tested (~0.5 m); no data beyond."
5. **Idle status line lies.** After the camera picker closes, the Capture status
   still reads "Recording cameras 0,1,2,3,4,5." — should clear or say "Ready."
   (It fooled the AI assistant mid-session; it will fool students.)
6. **Add Camera Videos renders some planes upside down / mirrored.** Display
   only — solves are provably fine — the plane builder isn't applying per-camera
   rotation. Fix orientation so reference planes read naturally.

Also field-confirmed from the 07-18 out-of-scope list: a **mean≫median companion
note** ("a few points exploded — check blink window / volume edge") would have
explained the helmet take's tail (mean 36 / p95 173 / median 15.7) at a glance.

**Clapper thread (new, design-doc candidate):** fluorescent OFF-edge works as the
sync mark (restrike stutter = 5-dip fingerprint, matchable across all lenses; scan
script proved it on both sides — graduate `blink_scan.py` into `diagnostics/`).
Proper classroom clapper = remote-control lamp in the volume (keyfob in performer's
pocket) or thrift-store speedlight on a trigger; the automatic end-state is
per-frame timestamps (adoptable-innovations Tier 1). Protocol v2 meanwhile: blink
while standing still — blink frames are sacrificial, and the known, timestamped
blink window is the first customer for rung-2 constraint gap-fill.

## 2026-08-01 — Ring re-rig day (laptop at BASEMENT)

1. **Recorder never stops when one camera lags.** Camera 4 delivered ~5 fps
   (583 frames vs everyone else's 3600); the calibration recording blew past
   the 60 s length setting and ran until David pressed Q, then the solve
   failed on the mismatched stream. Three identical failures before diagnosis.
   Wanted: stop at the target duration no matter what, and say WHY loudly —
   "Camera 4 delivered 583 of 3600 expected frames" — instead of a generic
   "calibration failed." Same silent-failure disease as the 06-09 audit theme.
   Diagnosis recipe that worked, for reuse: per-camera file sizes in the
   attempt folder (laggard is ~¼ size, mtime later than the rest) →
   `mdls -name kMDItemDurationSeconds` per video → frame count via cv2 →
   pull a mid-frame to identify the camera and check brightness.

   **Code trace (verified, multi-agent pass 2026-08-01 evening):** the stop
   condition counts FRAMES, never the clock. `start_recording` sets
   target = duration × requested fps (`core/camera_manager.py:278`); each
   camera thread closes only at its own frame target
   (`camera_manager.py:135-141`); `is_recording` stays True while ANY camera
   is still writing (`camera_manager.py:337-349`); both wait loops in
   `external/record_take.py` (332-338 windowed, 340-341 headless) never
   compare elapsed time to `--duration`. A 5 fps camera therefore needs
   ~12 min to finish; a dead camera (`camera_manager.py:112-114` retries
   silently forever) runs the take FOREVER. The mismatch error fires at
   `record_take.py:347-352` on early stop; the mp4s stay orphaned, no
   sidecar JSON, take never registers in Blender. Also: end-of-take frame
   counts are emitted as INFO but `external_runner.py` has no INFO branch —
   Blender silently drops the one honest line. AND: the recording window
   only obeys ESC, not Q (`record_take.py:335`) — explains the "had to just
   quit out" experience.
   **Build A (recommended first, one file):** both wait loops exit at
   duration + ~2 s grace → existing stop machinery → plain-words error
   ("Camera 4 delivered 583 of 3600 expected frames, ~5 fps; stopped at
   60 s") + RECORDING_REPORT.txt in the take folder. Error channel to the
   panel already exists (`external_capture.py:69`).
   **Build B (second):** Camera Health preflight button — 3 s per-camera
   fps meter with a loud laggard badge; delivery rate is the one signal
   auto-exposure can't fake. Would have caught today's failure in 3 seconds.
   **Build C (cheap one-liner, bundle with A):** honor Q as well as ESC in
   the recording window.
   Full memo + file:line verification in the 2026-08-01 workflow output
   (see SESSION_HANDOFF_2026-08-01.md).
2. **`charuco_square_mm` defaults to 110, doctrine is 200.** TWO near-misses
   today alone: fresh scene in the morning (solve launched at 110 before the
   live connector caught it), and again after a Blender restart in the
   afternoon. Wanted: default = 200, and/or the square field gets the same
   loud-badge treatment as stale calibrations. One-line properties.py change
   plus zip; waiting on David's go.
3. **ROOT-CAUSED same day (David):** keyboard + mouse were plugged into one
   of the camera hubs during the re-rig. The hubs are already at the 2-camera
   bandwidth ceiling (May 9 bug #2); constantly-polling HID devices on the
   same hub tipped one camera into ~5 fps delivery with a normal-looking
   image. Survived reboot and port switch because the keyboard/mouse never
   moved. The USB tree scan had them in plain sight on the same chain as two
   C922s ("USB Optical Mouse" / "Dell USB Entry Keyboard", Device Speed 0).
   **Rule for the setup guide: camera hubs carry cameras ONLY — max 2 per
   hub, no keyboards, mice, drives, or chargers, ever.** A Camera Health
   preflight (backlog idea, this section) would have caught it in 3 seconds
   instead of three failed 60 s recordings + a reboot.
   Related still-useful lesson: a camera can run ~5 fps while its image
   looks NORMAL (auto-exposure hides trouble); per-camera fps is the honest
   signal, image quality is not. Connects to the uvcc exposure-lock thread
   (FOUR_CAM_OPTIMIZATION 2a).

## 2026-08-04 — Audit day + the Z-snap mystery (laptop, no code touched)

Three-track session while David built slides: full pre-semester audit, forensics on the
smoothing jitter, and per-region smoothing research. Docs: **AUDIT_2026-08-04.md** (the
findings + ranked fix list), **Z_JITTER_DIAGNOSIS_2026-08-04.md**,
**SMOOTHING_METHODOLOGY_2026-08-04.md**, **SMOOTHING_RESEARCH_PRIOR_ART_2026-08-04.md**.

1. **The 1-frame Z-snap-under-smoothing is OUR bake's bug.** `bake_animation.py:59`
   re-derives each frame's rotation from a matrix, which always returns the positive
   quaternion spelling, with no frame-to-frame memory — so every rotation past 180°
   flips the stored sign. Invisible raw (q and -q are the same pose), catastrophic under
   any filter (averaging +q with -q → near zero → the root swings the whole rig).
   The 08-01 perimeter walk had 7 pelvis flips + 12 finger bones; measured 78.7° error
   at flip frames vs 0.98° elsewhere. Euler Filter can't help (Euler channels only).
   Repair script validated pose-neutral and David live-verified the fixed take
   ("best yet", heavy spinning). Interim protocol: **run
   `HIHO_quaternion_continuity_repair.py` after every Bake, before any smoothing.**
   Permanent fix = continuity pass inside the bake (build 1 next session).
2. **Every take is pre-filtered at the wrong frame rate.** FreeMoCap's position
   pre-filter defaults to 30 fps and nothing ever overwrites it; our takes are 60 fps,
   so the intended 7 Hz pre-clean effectively cuts ~14 Hz — takes arrive half-filtered,
   and the surviving 8–14 Hz band is exactly where hand jitter lives. Live chain:
   `external/process_take.py:158` (defaults) → env freemocap 1.8.2
   `post_processing_parameter_models.py:32` → `post_process_skeleton.py:50`.
   Fix = one line in our `process_take.py` (build 2 next session). All smoothing
   numbers measured 08-04 re-derive after it lands.
3. **Audit net result:** golden path is clean (06-09 fixes all confirmed; 5.2 API
   compliant; no data-loss paths on disk) — remaining items + ranked easy wins live in
   AUDIT_2026-08-04.md. Next-session build order approved by David 08-04 (see STATUS.md).
