# Facial Mocap — iPhone Interim Path (Decision, 2026-07-06)

**Addendum to `FACIAL_MOCAP_RESEARCH_2026-05-29.md`.** Read that first; this note
records a decision on top of it, prompted by the FreeMoCap V2 stream review
(`FREEMOCAP_V2_STREAM_NOTES_2026-07-06.md`).

## The decision (David's, 2026-07-06)

**iPhone + Live Link Face is the HIHO facial-capture standard for this school
year.** Rationale: every HIHO student has an iPhone or can borrow one; Live Link
Face is Epic's but free, so the zero-PAID-deps rule holds. Explicitly NOT the
ideal end state — **getting facial capture to 100% open source is a named
research thread for this year** (the May 29 helmet-cam/DeadFace pipeline is the
destination; see `RESEARCH_AGENDA_2026-07-06.md`).

Why this doesn't waste work: Live Link Face records the **same ARKit 52-blendshape
data** the open pipeline targets (CSV of shape values + reference video). The
downstream pipeline — CSV → shape keys → bake — is identical either way, so
swapping the capture device later costs nothing downstream. The real frontier is
unchanged from May 29: **getting the 52 shapes onto a chibi face** (rig
generation). Sync was never the hard part for us.

## Why Matthis's "multi-rate sync is hard" doesn't apply

V2 must solve the general problem: N camera groups, arbitrary frame rates,
synchronized live and automatically, for users he'll never meet. HIHO's version
is one extra device, post-hoc, one manual alignment per take by a human willing
to spend two minutes. That's a film-set problem, solved a century ago by the
clapper slate. Manual-once-per-take is cheap for us and forbidden for him.

## The sync recipe (visual marker — NOT audio)

**Gotcha that makes-or-breaks this: the rig cameras record SILENT video.** The
external recorder is OpenCV — frames only, no audio track (same fact that forced
the brightness-flash plan for the second-computer node). A clap therefore cannot
be found by audio on the rig side. It CAN be found by eye, which is why slates
have a clapper arm: one event, visible AND audible.

Per take, with the iPhone recording in Live Link Face and the rig recording
normally:

1. **Marker at the start:** one clap in view of the cameras — or better, a light
   flash (lamp / phone flashlight blink): one frame sharp in every camera
   including the iPhone, no hands needed, and already the doctrine for
   cross-machine sync.
2. **Find it on each side:** rig side = the flash frame in any camera video (or
   for a clap, the hands-meeting spike right in the mocap data). iPhone side =
   the same visual event in its reference video, or the audio spike.
3. **Offset the face track** to align the two frames (Blender NLA strip offset).
4. **Long takes (≥ ~60s): marker at the END too.** The iPhone's "60fps" and the
   C922s' "60fps" are two clocks that disagree slightly; over 2 minutes the end
   marker may land a frame or two off. Two markers measure the drift; a linear
   time-stretch of the face strip between them removes it. Faces are forgiving
   (an expression a frame late reads fine — unlike a foot contact), so for short
   takes one marker is enough. (Per-frame timestamps — adoptable-innovations
   Tier 1 — makes this correction automatic someday.)

## Practical notes / limits of the interim path

- **Live Link Face requires a TrueDepth iPhone** (Face ID models). Free app,
  Epic account. Records take CSV (52 blendshape weights + head rotation, with
  timecodes) + reference video, saved on the phone. Verify the exact CSV layout
  on the first real capture before writing any importer.
- **Framing:** a tripod iPhone loses the face when the performer turns or walks
  the volume — and full-body locomotion is canonical scope. For locomotion takes
  either mount the phone facing the performer's path, accept face dropouts, or
  capture face as a separate seated pass synced by marker. The helmet rig (open
  path) is what ultimately solves face-during-locomotion.
- **CSV → Blender importer** is the first build item when facial work starts:
  small mapping + keyframe writer per the May 29 research (RETARGET/BAKE =
  solved in principle). Community LLF-CSV importers exist — research before
  writing (research-doc-first pattern for interim deps).
- **Not a blocker for v1.x body work.** This rides alongside, same as May 29.

## Two-track summary

| Track | This year | Destination |
|---|---|---|
| Capture device | iPhone + Live Link Face (free, ubiquitous) | Helmet cam + MediaPipe/DeadFace (100% OSS) |
| Sync | Visual marker (flash/clap), manual per take | Same, then per-frame timestamps |
| Data | ARKit 52 CSV | Same 52 (DeadFace exports LLF-format CSV) |
| Frontier | Chibi rig generation (unchanged) | Same |
