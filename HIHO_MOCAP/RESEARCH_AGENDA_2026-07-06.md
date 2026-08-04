# HIHO Research Agenda — 2026–27 School Year (opened 2026-07-06)

Named research threads for the year, set by David 2026-07-06 (during the
FreeMoCap V2 stream review, last Fable session). These are QUEUED — the
research-doc-first pattern applies to each: research → design → code, and none
of them blocks v1.x body work or the Jul 7 sprint items. Initial leads below
are exactly that — leads to verify, not conclusions.

## 1. Facial capture to 100% open source

**Goal:** retire the iPhone/Live Link Face interim path (this year's classroom
standard — see `FACIAL_MOCAP_IPHONE_INTERIM_2026-07-06.md`) in favor of the
helmet-cam + MediaPipe/DeadFace pipeline from `FACIAL_MOCAP_RESEARCH_2026-05-29.md`.
The proprietary layer is deliberately temporary; making it open IS the research.
**Frontier:** chibi rig generation (52 ARKit shapes onto stylized faces) — first
thread is Blender-native shape-key transfer, per the May 29 doc. Fits the Ed.D.
frame directly: a documented DBR arc from pragmatic-proprietary to open.

## 2. Hand stabilization: DIY telemetry gloves and/or a "hand camera"

**Problem:** fingers are the noisiest part of every take — hands are small,
fast, self-occluding targets for 720p cameras at room distance (this is why the
hand-length fix already uses high-percentile + L/R mirror instead of trusting
per-frame data).

**Thread A — DIY gloves (Rokoko-like, doesn't need pro quality):** sensor
gloves report finger pose electronically, immune to camera distance/occlusion.
Leads to verify: the open-VR-community glove projects (LucidGloves/"open gloves"
lineage — flex-resistor DIY builds in the tens-of-dollars range; SlimeVR as the
open IMU-tracker ecosystem precedent). Key framing: gloves and cameras are
COMPLEMENTARY — gloves give smooth relative finger curl but drift; cameras give
absolute position but noise. A fusion (camera wrist + glove fingers) is the
same asymmetric-trust thinking as the TRACKED/RELEASED physics doctrine.
Electronics/soldering also = curriculum material (club build project).
**David learns this hands-on himself, first** (his call, 2026-07-06) — same
pattern as the local-LLM learning track: he builds a pair with his own hands
(ELI5 pacing, Claude handles all measurements/values),
THEN it becomes a club build he can teach. The research doc should therefore
pick the glove design for buildability-by-a-beginner, not just specs.

**Thread B — "hand camera" (blue sky, David's):** a dedicated close-up camera
looking at the hands — wrist-, chest-, or desk-mounted — running MediaPipe
Hands, merged with the body solve. Precedent is the helmet face-cam: HIHO
already accepts per-body-part cameras. A close camera sees fingers at a
resolution the room cameras never will. Open questions: mount point that
survives performance movement; merging a hands-only track into the baked rig;
whether V2's camera-groups architecture (different fps per group, soft sync)
eventually carries this for free — same watch-item as facecap sync.

**Research doc should compare A, B, and A+B against: cost per student, build
complexity, cleanup time saved, and openness.**

**Thread A opened 2026-07-06 (same day):** web research settled the platform —
**LucidGloves Prototype 4.1, tracking-only** (MIT, the established DIY glove
project; official docs confirm it builds without the haptics servos; Prototype
5 is BETA with no stable hardware files, skip for now). Build manual +
costed shopping list for David's learn-first build:
**`GLOVE_BUILD_MANUAL_2026-07-06.pdf`** (this folder). First glove + all tools
≈ $135–195; second glove ≈ $25–35. Remaining research (deferred until the
glove physically works): the serial→CSV logger, the camera+glove fusion
design, and the Thread B hand-camera comparison.

## 3. Suction-cup / no-drill camera mounting (mobile-lab prerequisite)

**Problem:** wall-mounted cameras work best (BASEMENT-proven), but the mobile
lab cannot drill into host-site walls. Need a mount system that installs and
strikes in minutes, damage-free.

Leads to verify: film/automotive "pump cup" suction mounts (Delkin Fat Gecko
class — rated far above a C922's ~160g); GoPro-style suction bases; plus the
non-suction no-drill family that may beat suction in real classrooms:
**floor-to-ceiling tension poles (autopole class), clamp mounts onto existing
fixtures (pipes, shelving, door frames), and plain light stands.**

Known physics to design around (verify specifics):
- Suction needs SMOOTH, NON-POROUS surfaces — glass, gloss paint, metal, tile.
  Matte-painted drywall, cinderblock, and brick (i.e., most classrooms) hold
  poorly or not at all. A suction-only kit could fail exactly where the mobile
  lab goes; the research must treat suction as one option in a mixed kit, not
  the answer.
- Suction loses vacuum over hours. Between-sessions drift is already absorbed
  by the per-session calibration doctrine; a MID-TAKE slip is the real risk —
  safety tethers + a re-pump ritual belong in any suction protocol.
- Every mount option must hold the ~2'5"–5'8" height bands from the validated
  varied-heights layout (2026-07-05) and allow portrait rotation.

**Deliverable:** a costed mobile mounting kit spec (per-camera mount + tether +
setup ritual) that a teaching artist can install in an unfamiliar room in
under 30 minutes.

## Standing watch items (from `FREEMOCAP_V2_STREAM_NOTES_2026-07-06.md`)

openpnp-capture for the recorder; Dr. Cherry's dissertation on release; V2
camera groups (carries facecap + hand-cam sync someday); V2 per-semester
re-evaluation before each backend freeze.
