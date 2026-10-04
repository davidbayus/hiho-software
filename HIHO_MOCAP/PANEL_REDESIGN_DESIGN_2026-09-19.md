# PANEL REDESIGN DESIGN: six numbered steps a first-timer can follow (HIHO MOCAP 1.5.2 to 1.5.5)

*2026-09-19, laptop. STATUS: BLESSED WITH CHANGES by David the same afternoon ("yes lets do it", then his five
answers, recorded in section 9). **ALL FOUR BUILDS SHIPPED THE SAME AFTERNOON: 1.5.2 (A), 1.5.3 (B), 1.5.4 (C),
1.5.5 (D), each tested headless, installed live and committed; details in STATUS.md. Both open placements were
confirmed by David ("computer paths understood. And yes that makes everything cleaner . status line . yes go ahead").
Still owed: his ears on the audio and his eyes on the panel in a real session (BASEMENT, 2026-09-20).** Born from the debrief of
the first demo with a student watching (2026-09-18; David performed, the student observed) and talked
through section by section the same day. Rules in force: design
before code, one change per zip, test after each, screenshot of the real panel for David's eye after each.*

*Version note: this wave takes the next free numbers, 1.5.2 to 1.5.5. The two builds still owed by
`V2_CHANGEOVER_DESIGN_2026-09-18.md` (the honest six-at-once percentage, and the HIHO Setup installer) take whatever
numbers are free when they are built. Build NAMES in that doc still describe the right work; only the numbers move.*

## 0. The short version (plain English)

Today the panel is in the wrong order for a beginner: the Record button sits above Record Calibration although every
session starts with calibration, the two record buttons look and read almost the same, one Length box serves two
different recordings, and unfinished tools share the panel with the six things a student actually does.

After this wave the panel reads top to bottom as the session runs: **1. Cameras, 2. Calibrate, 3. Record, 4. Process,
5. Rig, 6. Bake + Export**, with Face folded shut at the bottom. Every button and box explains itself in plain words
when you hover over it. The unfinished tools stay alive for David's studio work behind one checkbox in Preferences.
And the recorder stops talking over itself.

Nothing about recording, calibration, processing, the rig, or the bake changes. This wave moves, renames and explains.

## 1. Why now (David's words, 2026-09-19)

- "Having a "Record" and A "Record Calibartion" button is confusing for a noob. Also we Calibrate first but the Record
  Calibration button is below the record button. Also the length should be set to 120 by default. since calibration
  recordings need that much time."
- "Remove the studio section, thats not ready for primetime yet. and lets move "bake/export" to right after the rig is
  spawned, then the last thing on the list is face sync, because as of now im still getting that workflow down myself.
  and should be closed up by default"
- On the studio tools: "its not gone. we just need the time to to the design and testing. its just not ready for a
  public build yet. we can keep reseraching and testing in my own work."
- "leave everything open. just make sure the steps are apparent, so make sure the hover text describes the steps as
  simply."
- On the audio: "basicallt the problem is that all the audio tools talk over each other." and "record coundown has a
  weird big where it repeats get ready. then when the countdown is going, the camera count is also going, so its noisy
  and a bit chaotic"

The rule this wave enforces is David's own from 2026-08-07: capture and calibration are step one of every session, and
the panel's naming and order follow the order of the work.

What the code showed (read 2026-09-19):
- The real session runs Show Cameras, calibration dance, Solve, Check, record, Process, Spawn Rig. The panel runs those
  in the order 1, 5, 2, 3, 4, 6, 7.
- Both record buttons wear the same icon and nearly the same word.
- ONE Length box feeds BOTH recordings. Every calibration take from the last three sessions (09-05, 09-11, 09-18) was
  set to 120 seconds; the demo take on 09-18 was 30. So on demo day the number had to be typed twice, and the
  default of 60 is right for neither job.
- Bake Animation and Save Out work on whatever rig is selected, and Spawn Rig already selects the new rig. So Bake is
  live the moment a rig spawns, with nothing needed from the Studio panel.
- The status line is drawn under the Record button, even when the message is about processing further down.

## 2. The new panel

```
HIHO MOCAP
 [ status line, pinned at the very top, only when there is something to say ]

 1. Cameras
    [ Show Cameras ]
    Cameras: 0,1,2,3,4,5

 2. Calibrate
    Countdown 15     Length 120
    [ Record Calibration ]              grid icon, never the record dot
    [ Solve ]  [ Check ]
    Board take: ...
    Square size (mm): 200
    Quality badge / Floor badge / "not solved yet" warning

 3. Record
    Countdown 15     Length 60
    [ (dot) Record Mocap ]  [x]         the ONLY record dot in the panel

 4. Process
    Take: ...
    Calib: ...
    Tracker: RTMPose (fast)
    [ > Process Mocap ]  [x]
    badge

 5. Rig
    Processed: ...
    [ Spawn Rig ]
    [ Add Camera Videos ]

 6. Bake + Export
    [ Bake Animation ]
    FBX | GLB | .blend
    [ Save Out ]

 > Face Sync                            folded shut; one click opens it, contents unchanged
```

Steps 1 to 6 are always open (David: "leave everything open"). Only Face folds.

### Where every current control goes

| Today | After | Build |
|---|---|---|
| "Capture" heading | "1. Cameras" and "3. Record" | A |
| Show Cameras, Cameras box | step 1 | A |
| Two-line hint under Show Cameras | removed; the camera window prints the same help on its own bottom strip, and the hover text carries it | C |
| Countdown | shown in step 2 AND step 3. It is one number (time to walk to your spot); changing it in one place changes both, and the hover text says so | A |
| Length (one box, default 60) | TWO boxes: step 2 "Length" default **120**, step 3 "Length" default **60** | A |
| Record | "**Record Mocap**", red record dot, step 3 | A |
| Record Calibration | keeps its name, gets a grid icon, moves up to step 2 | A |
| Solve, Check Calibration, Board take, Square size, the three badges | step 2, unchanged | A |
| Status line under Record | pinned at the top of the panel | A |
| Take, Calib, Tracker, Process Mocap, badge | step 4, unchanged | A |
| "Calib blank = use last_successful_calibration.toml" hint | removed; the Calib hover text says it in plain words | C |
| "Output" heading | "5. Rig" | A |
| Processed, Spawn Rig, Add Camera Videos | step 5 | A |
| Save to, FreeMoCap path, RTMPose path (set once per computer) | OUT of the panel. They already live in Edit > Preferences > Add-ons > HIHO MOCAP; error messages will point there (recommended, question Q2) | A |
| Map the Volume, Spawn Empties (debug) | move into the Studio tools (diagnostics, not a student step) | B |
| Studio panel: Choose Take, Preview (Play, Lock Feet), Character tools | hidden unless "Show Studio tools (experimental)" is ticked in Preferences | B |
| Studio panel: Export (Bake Animation, format, Save Out) | becomes step 6 of the main panel; leaves the Studio panel so nothing appears twice | B |
| Face section | last, folded shut by default, contents unchanged | B |

## 3. Decisions

Locked by David on 2026-09-19:
- Button words: **Record Calibration** and **Record Mocap**.
- The mocap Length stays at 60. The calibration Length is its own box at 120.
- No "you have not calibrated today" warning for now.
- Studio leaves the student view; Bake + Export sit right after Spawn Rig; Face is last and folded shut.
- Steps stay open; hover text must make each step plain.
- Lock Feet: David deferred to Claude's read of its quality. **Claude's call: it stays OUT of the student build and IN
  the Studio tools.** It has been eyeballed once ("a good start", 08-12) and number-tested on one walk, on MediaPipe
  data only. It decides "the foot is down" at 2 cm from the floor, and the two trackers place heels and toes about
  2 cm apart, so it has never been checked against the tracker students now get by default. It holds the foot's height
  only; feet still slide about 14 cm per step. And upstream FreeMoCap has since replaced the method we ported with one
  that also stops the sliding (their addon, changes #71 and #75). Path back into the student panel: try it on RTMPose
  takes in the studio, then weigh porting the newer upstream method.

Recommended by Claude, waiting for David's OK (section 8):
- The studio tools live behind ONE checkbox in the add-on Preferences, off by default, ticked on David's laptop. One
  build, no second zip to keep in step.
- The three set-once computer paths leave the panel.
- The status line is pinned at the top.
- The spoken countdown thins out (section 5).

## 4. Hover text: every student-facing button and box

Rules: say which step it is, say what it does in words a 13-year-old knows, two sentences at most, numbers given
outright. Blender cannot show hover text on a section heading, so the headings must explain themselves ("2. Calibrate").

| Control | New hover text |
|---|---|
| Show Cameras | Step 1. Opens a window that shows every camera. Right-click a camera to use it or skip it, left-click to turn its picture, press Q when you are done. |
| Cameras | The cameras that will record. It fills in by itself when you close the Show Cameras window. |
| Countdown | Seconds before a recording starts, so you can walk to your spot. Both Record buttons use this number. |
| Length (step 2) | How long the calibration recording runs, in seconds. The calibration dance needs 120. |
| Record Calibration | Step 2. Do this at the start of every session. Records you doing the calibration dance with the board. |
| Solve | Works out where every camera is, from the calibration recording. Takes a few minutes. |
| Check | Scores the calibration. Green is good. Red means record the calibration again. |
| Board take | The calibration recording to solve. It fills in by itself after Record Calibration. Change it only to solve an older one again. |
| Square size (mm) | Width of one black square on the board, in millimeters. The house board is 200. Leave it alone unless you use a different board. |
| Length (step 3) | How long the performance recording runs, in seconds. |
| Record Mocap | Step 3. Records the performance. A countdown plays out loud first. |
| x next to Record Mocap | Closes the camera window. |
| Take | The recording to process. It fills in by itself after Record Mocap. Change it only to process an older take. |
| Calib | The calibration to use. Leave it blank to use the one you just solved. |
| Tracker | (unchanged) Which tracker Process Mocap runs. Every new file starts on RTMPose. |
| Process Mocap | Step 4. Turns the recording into 3D motion. About 3 minutes for a 30 second take. |
| x next to Process Mocap | Stops processing. |
| Processed | The processed take the rig is built from. It fills in by itself after Process Mocap. Change it only to load an older take. |
| Spawn Rig | Step 5. Builds the skeleton and plays your motion on it. Press Space to watch. |
| Add Camera Videos | Optional. Puts the camera videos in the scene so you can check the motion against them. |
| Bake Animation | Step 6. Turns the motion into real keyframes on the rig, so you can edit it or export it. Click the rig first. |
| FBX, GLB, .blend | The file type Save Out writes. FBX for game engines, GLB for the web, .blend for Blender. |
| Save Out | Saves the baked rig as a file you can take to another program. Bake first. |

Same build, same spirit (words only):
- The RTMPose badge is too long for the panel today and gets cut off ("Quality: not meas...00.0% of frames.", seen live
  09-19). It becomes two short rows: "Quality: not measured yet." and "Body tracked in 100% of frames." The finish
  message shrinks to "Processing complete (RTMPose)." and leaves the quality to the badge.
- Error messages that mention a computer path say where it lives: "Edit > Preferences > Add-ons > HIHO MOCAP".
- Face and Studio tools keep their current hover text.

## 5. Audio: one voice at a time, and the countdown is in charge

What happens today (`external/record_take.py`): every phrase is fired as its own `say` process and nothing waits for
anything. "get ready" and the first countdown number are fired in the same instant, so they collide, and macOS can
restart the phrase that got interrupted: that is the repeating "get ready". During the countdown the camera count
("4 cameras", "all 6") speaks whenever it changes, on top of the numbers: that is the chaos.

The new rules:
1. **One voice.** A single speaker object owns the Mac's voice. Two phrases can never sound at once.
2. **Two kinds of phrase.** CLOCK phrases ("get ready", the numbers, "recording", "done") are tied to a moment. COUNT
   phrases (the camera count) are not.
3. **The clock always wins.** If anything is still speaking when a CLOCK phrase is due, it is cut off and the CLOCK
   phrase speaks on time.
4. **A count never interrupts.** If the voice is busy, only the NEWEST count is remembered, and it is spoken when the
   voice is free, and only if it is still true and still news.
5. **During any countdown the camera count is silent.** Start countdown and end countdown both. (The end countdown
   already worked this way; the start countdown did not.) While the performer carries the board to the middle the
   count jumps around and means nothing. The first count is spoken right after "recording".
6. **"get ready" gets its own moment**, and the early numbers thin out: "get ready", then "10", then
   "5, 4, 3, 2, 1", then "recording". The window still shows every number. Fewer words, more air, and every word
   lands on its second. (A countdown shorter than 10 skips the "10".)
7. **Show Cameras counts only the cameras you have switched on.** Today it counts every camera the Mac can find,
   including ones you excluded and the laptop's own camera, so "all 6" can be impossible to reach.

## 6. What does NOT change

- Every operator's behavior: recording, calibration solve and check, processing, the Tracker menu, Spawn Rig, Bake,
  Save Out, the face chain. The Studio tools' code is untouched; only where they are drawn changes.
- File formats, folder names, the take log, the calibration dance.
- Old .blend files open fine: every existing setting keeps its name; the new calibration Length simply starts at 120.

## 7. Build order: one change per zip, each tested before the next

| Build | The one change | Test before moving on |
|---|---|---|
| **A = 1.5.2** | The panel in session order with numbered headings; Record Mocap + grid-icon Record Calibration; two Length boxes (120 / 60); status line on top; computer paths out of the panel (if Q2 = yes). Files: `ui/panels.py`, `properties.py`, `operators/calibration.py`, `operators/external_capture.py` (label only). | Headless: install in a sandboxed Blender, defaults 120 and 60, Record Calibration launches with 120 and Record Mocap with 60 (launch intercepted, no cameras needed), every control the panel draws exists (mock layout walk). Then live install + a screenshot for David. |
| **B = 1.5.3** | "Show Studio tools (experimental)" checkbox in Preferences, default off; Studio panel + Map the Volume + Spawn Empties only when it is ticked; Bake + Export as step 6 of the main panel and out of the Studio panel; Face folded shut. | Headless: with the box off the Studio panel refuses to draw and the diagnostics are absent; with it on they appear; Bake and Save Out still run from the main panel on a spawned rig. Live screenshot both ways. |
| **C = 1.5.4** | Words only: the hover text table, the two hints removed, the shorter RTMPose badge and finish message, path errors that say where to look. | Headless: every hover text in the table is what Blender reports; the badge rows fit 36 characters; the 1.5.1 round-trip test still passes 30 of 30 (the badge icon still keys on "not measured"). Live screenshot. |
| **D = 1.5.5** | The one-voice speaker in `external/record_take.py` (rules 1 to 7). | Headless with a fake voice and the fake-camera rig: no two phrases ever overlap; "get ready" is spoken exactly once; every CLOCK phrase starts within 0.15 s of its moment; no COUNT phrase inside a countdown; Show Cameras counts only included cameras. Then David's ears at BASEMENT. |

Tomorrow's BASEMENT session is the live test for the whole wave plus 1.5.1. Fallbacks stay in place: the Tracker menu
still offers MediaPipe, and `hiho_mocap-1.5.1.zip` stays at the top level as the known-good previous build.

## 8. Questions for David

**Q1. Studio tools behind one Preferences checkbox** ("Show Studio tools (experimental)", off by default, ticked on
your laptop)? It brings back the Studio panel, Lock Feet, Map the Volume and Spawn Empties for your studio recordings;
students never see them. Recommended: yes.

**Q2. Computer paths out of the panel** (Save to, FreeMoCap path, RTMPose path; they stay in Preferences)?
Recommended: yes. The alternative is keeping "Save to" in step 1.

**Q3. Status line pinned at the top?** Recommended: yes.

**Q4. The thinner spoken countdown** ("get ready", "10", "5, 4, 3, 2, 1", "recording"), with the camera count silent
until "recording"? Recommended: yes. The alternative keeps every number spoken, still one voice at a time.

**Q5. Show Cameras counts only the switched-on cameras?** Recommended: yes.

## 9. David's answers, 2026-09-19 about 1:00 PM, and what they change

His words: "1. yes but keep the voice active. its usefull during calibration! 2. just have a checkbox in the addon at
the bottom that opens the studio tabs up. Have lock feet as a sepeate checkable option. keep it outside of studio tools.
it should be considered a part of cleanup. 3. can you explain a bit more? slightly confused by the question 4. yes agreed
5. yes. does that all make sense?"

- **Audio: yes, and the voice stays active.** Nothing in section 5 mutes the camera count during a calibration recording
  or in Show Cameras. It is silent ONLY while a countdown is being spoken (the seconds before recording, and the last
  five). The first count is spoken right after "recording". Rules 1 to 7 stand.
- **Studio tools: a checkbox IN THE PANEL, at the bottom, not in Preferences.** "Studio tools", off by default. Ticked,
  the Studio panel opens up below. This REPLACES the Preferences checkbox of Q1 and the table row in section 2.
- **Lock Feet: its own checkbox, outside the Studio tools, part of CLEANUP.** "Lock Feet (cleanup)", off by default.
  Ticked, an unnumbered "Cleanup" block with the Lock Feet / Unlock Feet button appears between "5. Rig" and
  "6. Bake + Export" (it has to run before Bake). It stays a BUTTON, so the Unlock toggle keeps working for before and
  after comparisons. This REPLACES "stays in the Studio tools" in section 3: David wants it reachable on its own, as the
  first tenant of a future Cleanup area. Claude's quality caution stands, which is why it is opt-in and off by default.
- Both checkboxes are remembered PER COMPUTER (add-on preferences, drawn in the panel), so David ticks them once on the
  laptop and they survive new files; student machines start unticked.
- Map the Volume and Spawn Empties still travel with the Studio tools (diagnostics).
- Thinner spoken countdown: yes. Show Cameras counts only switched-on cameras: read as yes.
- Still being confirmed when Build A started: computer paths out of the panel (Q2), status line on top (Q3). David was
  unsure which question he had found confusing, so both were explained again in plain words.

Bottom of the panel after Build B:

```
 6. Bake + Export
 > Face Sync                  (folded)
 ------------------------------------
 [ ] Lock Feet (cleanup)
 [ ] Studio tools
```

## 10. NEXT WAVE, from the first live session (BASEMENT, 2026-09-19 afternoon). DESIGN ONLY, not built.

Field notes, David's words: "Countdown just says 10 and then that's it... When solving the progress bar doesn't update
it just stays at 0.00 till complete. Also when we process the mobcap the cursor progress icon stays at 0.00 and the info
update graphic on the top is unclear in progress" and, on the step 4 badge ("Quality: not measured yet."): "this part
becomes unclear, thers should be a quality check button underneath so students know where to go". Asked whether the
button should show numbers only or also a rating: "number and a quality value yes plz".

**Build E = 1.5.6, audio hot fix (BUILT 09-19, waiting for his ears):** never cut off or poll the `say` process; the
estimate of "is the voice busy" comes from the phrase's length. Lesson: a simulated voice proves the rules, never the
Mac's speech system; anything touching `say` needs one audible run before it ships.

**Build F, Check Quality (step 4), mirrors Check in step 2:**
- A **Check Quality** button under the Process badge. It reads the processed take's own motion inside Blender (numpy
  only, a second or two, no cameras, no FreeMoCap env) with the take log's definitions (`HIHO_ALL/TAKE_LOG/take_metrics.py`).
- The badge then shows a **quality value plus the numbers**, the same shape as the calibration badge:
  `Quality: Clean` / `Body tracked 100%` / `Bones steady 5%` / `Shake 2.4` / `Left/right mix-ups: none`.
- Quality words are the COMPUTED value and deliberately not the human ones: **Clean / Look closer / Rough**.
  PROVISIONAL bands, from the ten take-log rows (one room, mostly one performer), to be re-derived as the log grows:
  Clean = tracked 99 % or more, no mix-ups, bone wobble 7 % or less, mean shake 3.5 or less; Rough = tracked under 90 %,
  or mix-ups in more than 2 % of frames, or bone wobble over 12 %; everything else = Look closer. The badge says
  "provisional" in its hover text. Never the words GOOD / CHECK / BAD (those belong to the pixel badge).
- **Rate this take** beside it: three buttons, **ceiling / usable / redo** (the take log's human words). One click saves
  the rating WITH the numbers into the take folder (`HIHO_TAKE_RATING.json`: numbers, computed value, human rating, who,
  when, tracker stamp). The take log can then fill itself, and every rated take is one more point for tuning the bands:
  numbers next to an artist's eye, the data the FreeMoCap diagnostics work has no source for.
- After a run the "not measured yet" line gains a pointer: "Click Check Quality".
- Test: the ten logged takes must reproduce their take-log numbers exactly; the 09-18 demo take (his "ceiling") must
  come out Clean; the 09-05 walk (shakiest on record) must not.

**Build G, honest progress for Process (RTMPose):** read the per-camera `Camera_N: NN%` lines the script already passes
through; bar = the average across cameras mapped to 5 to 90 %, then triangulate / filter / convert; status reads
"Tracking: all 6 cameras, 42% (about 2 min left)". This is the build the V2 changeover design still owed.

**Build H, honest progress for Solve:** the runner's stage words are FreeMoCap PROCESSING stages, which the calibration
script never matches, so Solve sits at 0 % until done (older than this wave; the status line on top made it visible).
Minimum = a ticking clock ("Solving: 1:23 so far, usually about 3 minutes"); better = real stage lines from
`external/calibrate.py`.

Order: E (his ears) > G > F > H, one change per zip, each tested, screenshots after each.
