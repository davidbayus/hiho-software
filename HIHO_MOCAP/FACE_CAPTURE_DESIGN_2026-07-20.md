# HIHO MOCAP — Face Capture v1 Design (iPhone interim path) — 2026-07-20

**What this is.** The build design for the first working slice of facial capture,
sitting on two locked documents: `FACIAL_MOCAP_IPHONE_INTERIM_2026-07-06.md`
(the decision: iPhone + Live Link Face is this school year's standard) and
`FACIAL_MOCAP_RESEARCH_2026-05-29.md` (the research: capture/retarget/bake all
have clean answers; chibi rig generation is the year-long frontier and is NOT
in this design). Goal: **Wednesday 2026-07-22 at the BASEMENT, record body +
face in one take, and see the face animate in Blender, synced to the body.**

## Decisions locked 2026-07-20 (David)

1. **Home test capture first.** David records ~10 seconds at home with Live
   Link Face and AirDrops the CSV + reference video to the laptop. The CSV
   parser is built and tested against that real file before Wednesday. (This
   satisfies the interim doc's rule: verify the real CSV before writing any
   importer.)
2. **Test face = Spawn Test Face.** The addon generates its own cartoon debug
   head. No downloaded assets, no license vetting, works offline, stays useful
   forever as the diagnostic puppet. Chibi/Cortisol characters wait for the
   rig-generation research thread.

Defaults chosen by Claude, flagged for David's veto:

3. **Head rotation is ignored in v1.** The body rig already owns the head via
   body mocap; importing the phone's head angles would fight it. The channels
   are parsed and kept, just not applied (a toggle can come later).
4. **Panel home:** a new **Face** section in the main HIHO MOCAP panel, after
   Output. (Capture → Calibrate → Process → Output → Face.)
5. **Folder convention:** AirDropped face takes live in
   `~/Desktop/HIHO_FACE_TAKES/<take-name>/` (CSV + MOV together), matching the
   existing `HIHO_*` Desktop working-folder pattern.

## Scope

**IN:** capture protocol (no code), `Spawn Test Face`, `Load Face Take`
(CSV → shape-key animation), `Line Up Face` (flash-marker sync with zero
typed numbers), face reference video plane.

**OUT (explicit):** chibi rig generation (year thread); live streaming into
Blender (foscap-style OSC — someday, for a classroom "mirror" mode); the
helmet/DeadFace 100%-open path (the importer built here is SHARED with it —
DeadFace writes the same CSV format, so nothing here is throwaway); two-marker
drift stretch for long takes (v1.1 if a real take shows drift); eye-bone
rotations (the eyeLook* shape keys already carry gaze for shape-key faces);
MetaHuman Animator mode (see gotcha below).

## The data (verified by web research 2026-07-20; re-verify on David's real file)

- **A Live Link Face take = one CSV + one reference .mov** (video with audio
  and timecode), saved on the phone. Retrieval: Take Browser → share →
  AirDrop, or Files app → Live Link Face → takes.
- **App mode gotcha (new since the July 6 doc):** the app now has two capture
  modes. HIHO uses **"Live Link (ARKit)"** mode. The other mode, "MetaHuman
  Animator," records depth footage for Epic's own offline solver and does not
  produce the CSV we want. Set once, verify per session.
- **CSV layout:** header row, then one row per captured frame:
  `Timecode, BlendshapeCount (61), 52 ARKit blendshape columns (0–1 floats),
  HeadYaw, HeadPitch, HeadRoll, LeftEyeYaw, LeftEyePitch, LeftEyeRoll,
  RightEyeYaw, RightEyePitch, RightEyeRoll`.
  Cross-checked against Blender Studio's foscap addon (vendored at
  `R&D/foscap/`, GPL-3.0, Blender Foundation), which decodes the same 61-float
  stream live: indices 0–51 = shapes, 52–54 = head, 55–60 = eyes.
- **Known wrinkle:** some app versions shipped wrong header column NAMES in
  ARKit mode (later fixed). The parser therefore matches channels by name
  first and falls back to documented column position with a loud warning —
  never a silent guess (the 2026-06-09 audit theme: no silent failure).
- **Timing:** nominally 60 fps, but the parser derives real time from the
  Timecode column and never assumes a rate. Dropped frames appear as timecode
  gaps; timecode-driven keying absorbs them automatically.

## Build plan — three builds, one change each, one zip each

### 1.4.30 — Spawn Test Face (no CSV dependency; can build immediately)

A button in the new Face section generates **"HIHO Test Face"**: a simple
procedural cartoon head (sphere-derived, ~2k verts, readable features) with
**all 52 ARKit shape keys created**. About 14 of them get real modeled
deformation — `jawOpen`, `eyeBlinkLeft/Right`, `eyeWideLeft/Right`,
`browInnerUp`, `browDownLeft/Right`, `mouthSmileLeft/Right`,
`mouthFrownLeft/Right`, `mouthFunnel`, `mouthPucker`, `mouthClose` — the rest
exist as zero-deformation keys so every CSV channel lands, animates its
slider, and can be inspected in the Graph Editor even though it doesn't move
the mesh. Honest diagnostic: nothing imported is ever dropped.

Idempotent like Spawn Rig: re-running replaces the previous Test Face and its
action. Pure `bpy`, no assets, no dependencies.

### 1.4.31 — Load Face Take (gated on David's home CSV arriving)

Face section gets a file picker (**Face take** — points at the CSV; stored on
the Scene so it survives Blender restart, same as every other picker) and a
**Load Face Take** button:

1. Parse the CSV (name-match channels, positional fallback with warning).
2. Target = the Test Face if present, else the active mesh; channels apply to
   any mesh whose shape keys use the ARKit names.
3. Convert each row's timecode to seconds from the first row, then to scene
   frames at the scene's frame rate (subframe-accurate keys — no resampling
   math, Blender interpolates on playback).
4. Write one shape-key action named after the take folder.
5. Report an honest INFO summary: frames written, duration, channels matched /
   missing on the target. Missing-everything is an error, not a shrug.

Head/eye rotation columns: parsed, stored as custom properties on the action
for the future, not applied (Decision 3).

### 1.4.32 — Line Up Face (sync, zero arithmetic)

Reuses the existing video-planes machinery to add the iPhone reference video
as one more plane beside the camera planes. Then three buttons:

- **Mark Flash (Body)** — scrub the timeline until the flash appears in the
  camera video planes, click; the current playhead frame is stored.
- **Mark Flash (Face)** — scrub until the flash appears in the face reference
  plane, click; playhead frame stored.
- **Line Up Face** — shifts the face action AND the face video plane by the
  difference. Re-runnable: the applied offset is stored, so re-marking and
  re-running corrects by the delta instead of compounding.

David never types or subtracts a number; the playhead does all the math.
Long takes (≥ ~60 s) get a second flash at the end per the interim doc; if a
real take ever shows visible drift, the two-marker time-stretch becomes v1.1.

## Wednesday protocol (BASEMENT, 2026-07-22)

1. **First, Friday's pending 1.4.29 live checks** (from
   `SESSION_HANDOFF_2026-07-18.md`): install 1.4.29 → stale-badge check →
   progress clock → median verdict wording → Map the Volume on `13-28-17` +
   a fresh take. Face builds stack on top of a verified 1.4.29.
2. **Calibrate per session doctrine** (every session, 200 mm board).
3. **Face rig:** iPhone on tripod at face height just outside the clean
   volume, Live Link (ARKit) mode, screen facing performer. First takes are
   standing/seated facing the phone — locomotion face-dropouts are a known
   interim limit; the helmet path is the eventual answer.
4. **Per take:** start rig Record → start Live Link Face record → one
   flashlight blink visible to all six cameras AND the phone → perform
   20–30 s → second blink → stop both.
5. AirDrop the take's CSV + MOV into `HIHO_FACE_TAKES/`; process the body
   take as usual.
6. **Same evening:** Process → Spawn Rig → Add Camera Videos → Load Face
   Take → Mark both flashes → Line Up Face → watch body and face play
   together.

## Testing

- Parser unit tests on the real home-capture CSV plus synthetic fixtures:
  renamed-header variant, timecode gap, 30 fps file, truncated row.
- Headless Blender registration smoke test (operators + properties register).
- David's GUI pass through the actual panel buttons is the real test
  (test-the-user's-path rule) — first at home on the test capture, then
  Wednesday end-to-end.

## Future folds (recorded, not built)

- The year frontier: transferring the 52 shapes onto auto-rigged student
  characters (Blender-native shape-key transfer test is the first thread).
- DeadFace Video Mode CSVs flow through this same Load Face Take — swapping
  the capture device later costs nothing downstream (the whole point of the
  interim decision).
- foscap-style live OSC streaming as a classroom mirror mode.
- Per-frame timestamps (adoptable-innovations Tier 1) eventually make Line Up
  automatic.
