# HIHO Software

Free, open source motion capture and animation tools for classrooms, built in Blender.

Six scavenged webcams, one Blender addon, no subscriptions, no mocap suit: a school computer lab becomes a capture studio. This repository holds the software side of HIHO ("Human In, Human Out"), a program for time-based human work: storytelling, performance, animation, games, film, and sound. HIHO is a working name while the program chooses its permanent one.

This is a working repository, pre-1.0, developed in the open. First classroom testing is planned for Fall 2026 at SJSU. Expect honest rough edges.

## What is here

| Project | What it does | Status |
|---|---|---|
| `HIHO_MOCAP/` | Multi-camera markerless motion capture addon for Blender. Record with a ring of webcams, process through FreeMoCap, get a baked animation on a rig. | Active, canonical (v1.4.42) |
| `UV_UNWRAPER/` | PaWrappa, one-click UV unwrapping for student sculpts. | Student-testing ready (v0.3.5) |
| `CADRE_REMESHER/` | Quadre, a quad remesher. A free alternative to paid remeshing tools. | Working (v0.3.0) |
| `green_room/` | Procedural character design toolkit. | Early, recently reactivated |
| `PPPARTY_V2/` | The single-camera era of the mocap work. | Parked (v2.0.4) |
| `PPPARTY_V1_ARCHIVE/` | The phone-era live puppet experiment that started it all. | Archived, read only |

## Human In, Human Out

The name is the policy. From the club newsletter:

> - Claude Opus helped write the code, but a human decided what to build and tested it
> - The capture system uses AI (Google's Mediapipe) to find your body, the input is from a real person moving
> - It never invents motion from a prompt
> - A human performs, designs the character, and tells the story
> - The AI is a tool in the middle, never the author

The same rule governs how this software is made. Every feature starts as a plain-language design document. Code is written in collaboration with AI (Claude), one tested change at a time, and a human decides what gets built, what ships, and what gets thrown away.

## How this was built

This repository documents itself in prose, not just commits. Every feature began as a dated design document, every bug hunt has a diagnosis writeup, and every research question has a research doc with its sources. More than a hundred of them live next to the code, and they are the real development history. Start with:

- `HIHO_MOCAP/STATUS.md` for the live state of the canonical project
- `HIHO_MOCAP/HIHO_MOCAP_WRAPPER_ARCHITECTURE.md` for the architecture and its reasoning
- the dated `*_DESIGN_*` and `*_RESEARCH_*` docs for every decision in between

The working rules: no code before design. One change at a time, one versioned build each, tested on a real capture before the next change begins. If a change makes things worse, it gets reverted, and the reversion is recorded too.

## The story so far

- **Spring 2026.** A phone-based live puppet experiment (PPParty V1) proves the appetite and hits the ceiling of one camera.
- **Late spring 2026.** A single-camera recording tool (V2) gets hands working and shows why true 3D needs more views.
- **Summer 2026.** The multi-camera system (HIHO MOCAP) becomes the canonical project: a six-webcam ring, printed-board calibration with honest quality scoring, FreeMoCap processing in an external environment, and a bake-first artist workflow in Blender.
- **Fall 2026.** Students.

## Engine and lineage

The 3D solving engine is [FreeMoCap](https://freemocap.org) (AGPL-3.0), which runs in its own Python environment. This addon drives it and never modifies it. MediaPipe does the per-camera body tracking. The Blender addon is the artist layer: recording, calibration scoring, take loading, rig spawning, baking, and export.

## License

AGPL-3.0. Free and open source, forever.
