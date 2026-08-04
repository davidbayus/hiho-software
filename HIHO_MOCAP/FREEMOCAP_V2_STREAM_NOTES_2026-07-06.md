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
