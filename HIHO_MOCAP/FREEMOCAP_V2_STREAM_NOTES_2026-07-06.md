# FreeMoCap V2 Stream — Notes & HIHO Position (2026-07-06)

**Source:** transcript of Jon Matthis's V2 work-in-progress livestream
(`~/Desktop/FREEMOCAP V2 UPDATE.txt`, ~1h50m). Reviewed with David 2026-07-06;
he independently reached the same conclusions. This is the settled read.

## What V2 is right now

Pre-alpha ("alpha 0.0" at best, no releases yet). Server (Python/FastAPI) +
Electron/React front end talking over HTTP/WebSocket. Two pipeline kinds:
**real-time** (live cameras → RTMPose whole-body on GPU/CUDA → triangulate →
One Euro filter) and **post-hoc** (video groups → MediaPipe → same functional
pipeline as V1 — Matthis expects "identical or nearly identical results" to
1.8's processing). Blender output punches through the same ajc27-lineage
pipeline (soon renamed "Skelly Blender"). His own words: workflows "relatively
insane," state/persistence "not good," progress bars unreliable. The stream
itself was plagued by camera-enumeration shuffles and in-use-camera failures.

## HIHO position (all confirmed with David)

**KEEP — nothing changes for Fall 2026:**
- Option B doctrine holds: backend frozen at vendored 1.8.2 for the semester.
  Matthis: "if you wait a little while it will be better." Re-evaluate per
  semester (next look: before Spring 2027 freeze).
- Post-hoc-first validated from the source: real-time is "arguably kind of a
  toy relative to the post hoc pipeline, which actually produces the best
  quality data." Capture-and-bake stays the deliverable.
- CPU-only stays promised upstream ("no matter what... always must maintain a
  CPU-only option") — the old-machines mission survives V2's GPU turn.
- **Our camera picker (1.4.24) is AHEAD of upstream** — V2 has not solved
  enumeration instability; he fought it on stream for ten minutes.

**RESEARCH / WATCH:**
1. **openpnp-capture** (C lib he's adopting via a Rust skelly-cam rewrite on
   the `skellycam` development branches): detects in-use cameras AND enumerates
   a camera's true supported resolutions/fps — would answer C922 format
   questions from the descriptor and harden the picker. Not urgent (our OpenCV
   recorder is field-proven); candidate research doc when camera work next opens.
2. **Dr. Aaron Cherry's dissertation** — tracker-vs-tracker accuracy against a
   Qualisys gold standard; MediaPipe reportedly least accurate. Going public +
   being chopped into peer-reviewed papers. **Ed.D. citation gold** and the
   evidence base for any future tracker swap. Grab on release.
3. **Camera groups + soft sync** (mocap cams + face cams at different rates):
   V2's architecture will provide this — do NOT build our own multi-rate sync.
   Interim facecap sync is manual visual markers
   (`FACIAL_MOCAP_IPHONE_INTERIM_2026-07-06.md`).
4. **Server/client network split** (cameras on one machine, UI on another) —
   V2 may eventually make our Plan B second-computer node a supported feature.
   Also note: V2's server resembles what `project_hiho_mocap_v2_homerolled_ideal`
   imagined building with CS students — contributing upstream may beat home-rolling.

**SKIP (for now):** V2 itself for students (unstable, Windows/CUDA-centric,
no releases); the real-time pipeline (resource monster, wrong deliverable);
his home-rolled MediaPipe holistic (accuracy unvalidated — Google killed
official holistic, which is WHY V1 pins old MediaPipe; we stay on vendored
1.8.2); front-end tech choices (Electron vs Tauri — irrelevant to a Blender
panel).

**OPPORTUNITIES (timing is now — he's in listening/redesign mode):**
- **File the groundplane bug report upstream** (queued since 2026-07-03). V2
  does groundplane at calibration and he admits detection is "not as robust as
  it could be." We have the planar-ambiguity diagnosis, the flipped-world
  incident data, and a shipped detector (1.4.21 camera-heights check).
  Maximum-impact moment is while he's rearchitecting calibration.
- **FreeMoCap University arts lane:** a semester of classroom findings (picker,
  per-session calibration doctrine, quality score bands, treadmill protocol,
  110mm board lesson) is field data the project doesn't have. David's invited
  lane.
- Side note: his open-tooling/AI-cost politics rhyme with David's open-source
  AI pipeline position — kindred-spirit ground for the relationship.

---

# UPDATE 2026-08-11 — the alphas are real: v2.0.0-alpha.18 → alpha.21 reviewed (laptop)

Five weeks after the stream, V2 went from "no releases" to four shipped alphas.
Read from the GitHub release notes + the Discord announcement, 08-11:

- **alpha.18 (07-28):** first general-user alpha of the ground-up rewrite (camera
  capture, tracking, desktop UI all redesigned).
- **alpha.19 + .20 (08-05):** skeleton refitting (aaroncherian) and proper
  filtering/triangulation options finally exposed in the UI. **SkellyCam overhaul:
  synchronized recording with equal frame counts across all cameras and per-frame
  `perf_counter_ns` timestamps** — the Tier 1 item from `HIHO_ADOPTABLE_INNOVATIONS`
  is now REAL upstream, and their equal-frame-count guarantee matches our early-stop
  equalize-upward rule. SkellyTracker rewrite runs MediaPipe AND RTMPose with GPU
  acceleration (CUDA on Windows/Linux, **CoreML on Apple Silicon**). New
  React/Electron UI; standalone installers including a macOS .dmg.
- **alpha.21 (08-11):** framerate is now derived from the recorded videos and fed to
  the Butterworth filter (**PR #861 — this CLOSED #849, the bug we measured**;
  imported pre-recorded video still needs manual fps). Synchronized-video import
  added. Single-camera-needs-calibration bug fixed. UI now explicit that only
  MediaPipe recordings export to Blender (RTMPose export planned).

**HIHO verdict: NOTHING TO IMPLEMENT.** The two behavior fixes alpha.21 ships are
things HIHO already ships on the 1.x line: the fps→filter clock (our 1.4.34 sidecar
fix, measured ~90% noise reduction) and outlier rejection default ON (ours since
July; theirs via #838). Upstream independently landed on both answers, which is
validation, not work.

**2.0-only bugs that confirm the semester freeze:** #820 (calibration/data scaling
"slightly off," ~10%, filed by aaroncherian, explicitly against 2.0 — our 1.8.2
volume/scale numbers are NOT implicated) and #863 (2.0 records ALL connected cameras
regardless of selection — our own recorder with preview-as-picker is immune, and
this is the second time upstream recorder trouble has justified it, after #650).
2.0 remains not classroom-ready; frozen-backend doctrine unchanged.

**Watch-list changes for the pre-Spring-2027 re-evaluation:**
1. Per-frame timestamps + equal frame counts shipped (alpha.20) — when 2.x
   stabilizes, this is the headline adoption reason.
2. RTMPose with CoreML on Apple Silicon — potential accuracy jump, biggest where our
   noise gradient is worst (hands). Blender export for RTMPose recordings does not
   exist yet; watch that specifically.
3. Standalone installers (.dmg) — matters for a future students-at-home story.
4. aaroncherian says (on our #862, 08-11) calibration work is coming "in the near
   future" with the ambiguity issue in mind — watch #862/#820 for the ground-plane
   fix taking shape.
