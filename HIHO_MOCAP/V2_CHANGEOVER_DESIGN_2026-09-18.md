# V2 CHANGEOVER DESIGN: RTMPose becomes the default tracker (HIHO MOCAP 1.5)

*2026-09-18, laptop. STATUS: BLESSED by David 2026-09-18 about 3:05 PM ("Yes, build it now" for 1.5.0; Q2
answered: the menu remembers PER FILE). Q1, Q3, Q4 stand at the recommended defaults unless he objects.*
*BUILD ON HOLD the same afternoon, David's call ("lets hold off on the build, im heading home soon. lets debrief
and plan"). The blessing stands; no code was written. 1.5.0 starts at the next laptop dev session.*

***1.5.0 BUILT AND TERMINAL-TESTED 2026-09-19 (laptop), hold lifted by David ("lets build it so its ready to deploy").**
Both tests in section 6 pass: the 09-18 student take in 2 min 55 s (MediaPipe: 13 min), numbers level with or calmer
than the MediaPipe ceiling result; the 09-11 120 s take in 9 min 26 s, past the 300 s mark, loader files identical to
the eval kit's (0.0000 mm). David's eye on the two rigs side by side, same day, his words: "visual check confirmed.
RTMpose mocap looks great out of the box". **1.5.0's acceptance test is COMPLETE.** Details in STATUS.md. What the build
settled, for 1.5.1 and later:*
- *2.0 does NOT clear `output_data/` (section 5's open question). The move-aside guard is therefore essential, and it
  lives in the new script. It also moves the old PROCESS_QUALITY.txt into the aside folder.*
- *The tracker stamp lives at `output_data/HIHO_TRACKER.json` (inside the folder, so it travels with the results it
  describes). 1.5.1's badge reads it from there. The new script already writes it; the old script's stamp is 1.5.1.*
- *2.0 reports a failed camera worker only as a progress message (the pipeline stops being alive, exit 0). The script
  accepts a result only if 2.0 wrote it during this run. 1.5.2's progress reader could surface the FAILED phase too.*
- *No ffmpeg needed: both tests ran with a bare PATH. 1.5.3's installer does not have to ship one.*
- *2.0 warns "No timestamps CSV found ... cannot determine framerate" and then keeps the fps we pass. Harmless.*
- *The script passes 2.0's per-camera progress lines through one per line (`Camera_3:  42%|...`), ready for 1.5.2.*
- *A rerun with the same tracker makes 2.0 draw its new overlay on top of its previous annotated video (cosmetic).*
- *Pace measured through the new script: 175 s for a 30 s take, 566 s for a 120 s take.*

*Build notes gathered before the hold (for whoever starts 1.5.0):*
- *2.0 names its overlays `annotated_videos/Camera_N_annotated.mp4`; 1.8.2 names them `Camera_N_mediapipe.mp4`. Both
  sets can sit in one folder, so check what `core/video_planes.py` picks up when both exist (1.5.1).*
- *The panel picks the badge icon by looking for GOOD / CHECK / BAD inside the quality line (`ui/panels.py`). The
  RTMPose wording "not measured ... yet" contains none of them and falls to the ERROR icon. Give it a neutral icon
  in 1.5.2, and keep those three words out of the RTMPose line.*
- *`build_zip.py` ships everything under `external/`, so the new script needs no build-list change. Version lives in
  `blender_manifest.toml` line 4 and `__init__.py` line 14.*
- *The other-tracker move-aside guard belongs IN the new script (the script is what overwrites), so it lands in
  1.5.0 rather than 1.5.1: safer from the very first run. The mirror guard in the old `process_take.py` stays 1.5.1.*
- *1.4.52 is still uncommitted. Commit it first so 1.5.0 is its own commit (David's call).*
*This is the "official changeover to V2" named on 2026-09-11. Rules in force: design before code, one change
per build, test after each.*

## 0. The short version (plain English)

Today the **Process Mocap** button always runs the old pipeline: FreeMoCap 1.8.2 with the MediaPipe tracker. It
looks at one camera at a time, so a take waits in line six times.

After this change, the button runs the new pipeline by default: FreeMoCap 2.0 with the **RTMPose** tracker, which
looks at all six cameras at the same time. A small **Tracker** menu sits right above the button. It starts on
RTMPose in every new file. The second choice is the old MediaPipe pipeline, kept exactly as it is, as the
known-good fallback. The menu is a list, so more trackers can be added later.

Nothing else in the addon changes. Recording, calibration, Load Take, the rig, Bake, Lock Feet: all untouched.

## 1. Why now

David's ask, 2026-09-18, after the first classroom-style demo with a student: "it ran on the old mediapipe not
the RTMpose. so it took a long time and it processed one cam at a time. can we set it up so that RTM is the
default. and we can also have a toggle maybe for previous machine vision models."

What the demo take shows (`HIHO_CAPTURES/2026-09-18_13-42-27`, 30 s, six cameras, 1800/1800 frames on every
camera):

| | Old path (what ran today) | New path (expected) |
|---|---|---|
| Tracker | MediaPipe, FreeMoCap 1.8.2 | RTMPose, FreeMoCap 2.0 alpha.23 |
| Cameras | one at a time, one annotated video landed about every 2 minutes | all six at once |
| Wait for a 30 s take | about 13 minutes (13:43 to 13:56 on the clock) | about 3 minutes |

**This take is the benchmark.** David's verdict on it the same afternoon, his words: "the recording out was current
ceiling quality standard overall". So the old path, on this footage, is the quality ceiling to date. The RTMPose
path has to stand next to it on the SAME footage before the default flips: that side-by-side is the acceptance
test for build 1.5.0 (section 6), always on a copy, the original take is never touched. It is also the reason the
old path stays in the menu rather than being removed.

The "about 3 minutes" comes from the five full runs already on disk (`RTMPOSE_EVAL/LOCAL.nosync/recordings`):
60 s walk 288 s, 45 s seated take 295 s, 60 s BASEMENT walk 326 s, 120 s take 553 s. That is 4.6 to 5.4 seconds
of work per second of recording, plus roughly 40 s of start-up.

The decision itself is already made (2026-09-05 "we move forward with RTMPose 100%"; 2026-09-11 "our next step
... will be the official changeover to V2"). Evidence: left/right swaps 6 to 0 on the 08-01 walk, calmer limbs on
the 09-05 walk, David's eyeball verdict "easily worth the cleanup".

## 2. What the student sees

In the Process section, one new row above the button:

```
Process
  Tracker:  [ RTMPose (fast)            v ]
            [ MediaPipe (classic, slow)   ]
  [ > Process Mocap ]  [x]
```

- The menu is always visible, so which tracker is about to run is never a surprise.
- It starts on **RTMPose (fast)** in every new .blend (see question Q2).
- While it runs, the status line says what is true for that path: "Detecting: all 6 cameras at once (42%)"
  instead of "camera 3 of 6".
- When it finishes, the badge names the tracker: "Processing complete. RTMPose."

Messages when something is missing, in plain words, and **never a silent fallback**. A silent fallback to
MediaPipe is a student waiting 13 minutes without knowing why, which is today's demo.

- 2.0 is not installed on this computer: Process refuses and says "The fast tracker (RTMPose) is not installed
  on this computer. Pick MediaPipe (classic) in the Tracker menu, or run HIHO Setup."
- First run with no internet and no model on disk: "RTMPose needs a one-time download. Connect to the internet
  once, or run HIHO Setup."

## 3. How it works under the hood

Today:

```
Process Mocap -> ExternalProcessRunner -> external/process_take.py      (runs in the 1.8.2 env)
```

New, when Tracker = RTMPose:

```
Process Mocap -> ExternalProcessRunner -> external/process_take_fmc2.py (runs in the 2.0 env)
```

`ExternalProcessRunner` already takes any env python and any script, so the seam exists. The new script is a port
of the three eval-kit pieces that have been proven on five takes, folded into one file that speaks the same
protocol the panel already listens for (`HIHO_INFO::`, `HIHO_DONE::`, `HIHO_ERROR::`, plus the `HIHO_DONE.txt` /
`HIHO_ERROR.txt` / `PROCESS_QUALITY.txt` files):

1. **Warm the model** in one process (`warm_model_cache.py`). 2.0's six workers race to download the model on a
   first run and one reads a half-written file.
2. **Run 2.0's posthoc pipeline headless** (`run_fmc2_posthoc.py`), fps read from `HIHO_RECORDING_INFO.json`,
   Butterworth 7 Hz order 4, the same filter as the old path.
3. **Shim** (`shim_fmc2_to_hiho.py`): write the four files `core/loader.py` needs. The loader is NOT touched in
   this wave. Making the loader read RTMPose files natively is a later, separate change.

The eval kit in `HIHO_ALL/RTMPOSE_EVAL/` stays as it is. It remains the side-by-side and research tool.

### Lessons from the eval that the port must carry

| Lesson | Where it came from |
|---|---|
| Refresh `registry.heartbeat_timestamp` by hand every 1 s. Do NOT call `start_heartbeat()`: it also starts a monitor that can kill our own process. Without the refresh every worker dies at 300 s. | 09-11, first 120 s take died at 56 % |
| Warm the model cache in ONE process before the six workers start. | 09-04, first-run download race |
| Undo the hand/face block scramble, and detect it first, so the fix turns itself off when upstream fixes it. | 09-04, upstream report #5 |
| Attach each hand to the body wrist every frame. 2.0's own wrist fix fails for RTMPose. | 09-04 |
| Leave with `os._exit` after the files are written. 2.0's thread workers linger after "complete". | 09-04 |
| Take the fps from the recorder's sidecar, never assume 30. | 08-04, the half-filtered takes |

## 4. Honest badges

**Quality.** Checked today on all seven 2.0 runs on disk: 2.0 alpha.23 writes a `reprojection_error` column, and
it is empty (100 % NaN) in every run. The shim's error file is a placeholder (0 where a point was tracked). So on
the RTMPose path `PROCESS_QUALITY.txt` must never print GOOD from that placeholder. First wave: the line reads
"Quality: not measured on the RTMPose path yet" followed by the one number that IS real, the share of frames
where the body was tracked. A real quality number is its own later change (it needs the 2D detections; find out
whether 2.0 can save them).

**Progress.** 2.0 logs one live line per camera (`Camera_3:  42%|...`). The bar reads the average across the
cameras for the detection stretch (5 to 90 %), with a time-left estimate from the measured pace, seeded at 5 s of
work per second of take. The old path keeps its camera-by-camera clock.

**Tracker stamp.** Every processed take gets `HIHO_TRACKER.json` (tracker, backend version, date). The panel badge
and the finish message name the tracker, so a result can always be traced to the pipeline that made it.

## 5. Reprocessing a take that already has results

Both pipelines hand the loader the same four file names, so a second run on the same take would overwrite the
first. Today's demo take is the live example: its MediaPipe result exists, and an RTMPose run in place would
replace it without a word.

Rule: before a run writes over results made by a DIFFERENT tracker, it moves the old `output_data/` aside to
`output_data_<tracker>_<date-time>/`. A move, never a delete. Same tracker again: overwrite as today.
(To verify during the build, on a copy: whether 2.0 clears `output_data/` by itself at start.)

## 6. Build order: one change per zip, each tested before the next

| Build | The one change | Test before moving on |
|---|---|---|
| **1.5.0** | New file only: `external/process_take_fmc2.py`. The panel is unchanged, so the working path carries zero risk. | From Terminal, on a COPY of the 09-18 demo take (the quality-ceiling benchmark) and of the 09-11 120 s take: status files appear, four loader files appear, Load Take spawns a rig. Then the side-by-side: the RTMPose rig next to the 09-18 MediaPipe rig, numbers from `compare_v1_v2.py`, and David's eye on it. |
| **1.5.1** | Tracker menu (default RTMPose) + "FreeMoCap 2.0 env" preference + Process routes by tracker + refuse-with-message when 2.0 is missing + move-aside of another tracker's results + tracker stamp. | Headless Blender operator test, then David's live look on a fresh recording. |
| **1.5.2** | Honest progress and quality wording for the six-at-once path. | Watch a real run; the bar must never sit still or read done early. |
| **1.5.3** | `HIHO_Setup_Mac.command` installs the 2.0 env with uv into a fixed home and warms the model; the preference default points there. | Proven on one Art 241 Mac mini. This is the student cut-over gate set on 09-05. |

Later, each with its own design: the hands decision; a real quality number on 2.0; calibration solve on 2.0;
Windows; retiring 1.8.2 after one semester as fallback.

## 7. What does NOT change in this wave

- Recording (`record_take.py`) and calibration (`calibrate.py`) keep running in the 1.8.2 env. Both envs stay
  installed this semester. Only Process changes.
- `core/loader.py`, the rig, Bake, Lock Feet, Save Out, the face chain.
- The 2.0 env stays pinned at alpha.23 (2.0 is a daily alpha; a pin bump is its own tested change).
- The frozen `freemocap-env` is not touched.

## 8. Questions for David

**Q1. Menu wording.** Proposed: "RTMPose (fast)" and "MediaPipe (classic, slow)".

**Q2. Where the menu remembers its setting.** Recommended: per .blend file, so every new file starts on RTMPose
and a forgotten switch can never follow the next student. The alternative is per computer (set once, sticks).

**Q3. A third choice later?** 2.0 can also run MediaPipe with all six cameras at once (the 45 s seated take ran in
194 s). Recommended: not in the first wave. One default plus one known-good fallback; the menu is a list, so it
can grow.

**Q4. Fingers on the RTMPose path.** RTMPose fingers are about 2.5 times wobblier than MediaPipe's. Recommended
for the first wave: keep exactly what the 09-05 and 09-11 side-by-sides showed (RTMPose fingers, attached to the
wrists). The hands decision stays its own design.
