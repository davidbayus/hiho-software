# HIHO Software

Free, open source motion capture and animation tools for classrooms, built in Blender.

![License: AGPL-3.0](https://img.shields.io/badge/license-AGPL--3.0-blue) ![Built in Blender](https://img.shields.io/badge/built%20in-Blender-orange) ![Engine: FreeMoCap](https://img.shields.io/badge/engine-FreeMoCap-8A2BE2) ![Status: pre-1.0](https://img.shields.io/badge/status-pre--1.0-yellow)

<!--
DAVID, OPTIONAL HERO VIDEO: committed video files show as click-to-play links,
not inline players. For a video that plays right here at the top, edit this
file on GitHub.com and drag MEDIA/06.mov (the six-camera grid reel) into this
spot; GitHub uploads it and inserts an inline player automatically.
-->

Six scavenged webcams, one Blender addon, no subscriptions, no mocap suit: a school computer lab becomes a capture studio. This repository holds the software side of HIHO ("Human In, Human Out"), a program for time-based human work: storytelling, performance, animation, games, film, and sound. HIHO is a working name while the program chooses its permanent one.

This is a working repository, pre-1.0, developed in the open. First classroom testing is planned for Fall 2026 at SJSU. Expect honest rough edges.

## The process in pictures

A real person walks on a treadmill inside a ring of thrift-store webcams. FreeMoCap turns the videos into a moving skeleton. The skeleton drives a character. The character keeps every hesitation and shrug of the person who performed it. That is the whole idea.

Numbered in the order the process happens. Click any moving picture to play its clip.

<img src="MEDIA/01.png" width="640">

**1. The studio.** A basement workspace: six scavenged webcams on mic stands and clamps, printed calibration boards, a thrift store treadmill.

[<img src="MEDIA/posters/poster_02.jpg" width="640">](MEDIA/02.mov)

**2. A walk through the studio.** Two minutes handheld through the same room: cameras clamped to shelves and ceiling beams, the powered hub that feeds them, printed calibration boards, the face helmet, and the paintings on the wall.

[<img src="MEDIA/posters/poster_03.jpg" width="640">](MEDIA/03.mov)

**3. The capture.** MediaPipe finds the body and face in each camera view. The solved skeleton drives the character.

[<img src="MEDIA/posters/poster_03_1.jpg" width="640">](MEDIA/03_1.mov)

**3.1. The same take on the character, rendered.** The character keeps the walk.

[<img src="MEDIA/posters/poster_04.jpg" width="300">](MEDIA/04.mov)

**4. A two character scene**, performed one take at a time on the treadmill.

[<img src="MEDIA/posters/poster_05.jpg" width="640">](MEDIA/05.mov)

**5. Staging test.** A third character walks the scene while the pair keeps pulling.

[<img src="MEDIA/posters/poster_06.jpg" width="640">](MEDIA/06.mov)

**6. The six camera ring.** Every view at once, driving one performance.

[<img src="MEDIA/posters/poster_07.jpg" width="640">](MEDIA/07.mov)

**7. Face experiments.** A phone strapped to a bike helmet records the face while the webcams take the body.

[<img src="MEDIA/posters/poster_08.jpg" width="640">](MEDIA/08.mov)

**8. The face transfer up close.**

More of the studio work these tools come from: [www.davidbayus.zone](https://www.davidbayus.zone)

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

- **Summer 2026.** The multi-camera system (HIHO MOCAP) becomes the canonical project: a six-webcam ring, printed-board calibration with honest quality scoring, FreeMoCap processing in an external environment, and a bake-first artist workflow in Blender.
- **Fall 2026.** Students.

## Engine and lineage

The 3D solving engine is [FreeMoCap](https://freemocap.org) (AGPL-3.0), which runs in its own Python environment. This addon drives it and never modifies it. MediaPipe does the per-camera body tracking. The Blender addon is the artist layer: recording, calibration scoring, take loading, rig spawning, baking, and export.

What we have learned while driving FreeMoCap in a classroom, written up for their community with every claim sourced and dated: [`HIHO_MOCAP/UPSTREAM_NOTES_FOR_FREEMOCAP_2026-08-05.md`](HIHO_MOCAP/UPSTREAM_NOTES_FOR_FREEMOCAP_2026-08-05.md)

## Who makes this

HIHO software is built by [David Bayus](https://www.davidbayus.zone), an artist and Senior Lecturer in Digital Media Art at San Jose State University's CADRE Laboratory. His films and editions are held in collections including MoMA, the Whitney, and LACMA. The animations above are from his studio practice, where these tools get their field testing before they reach students.

Questions, ideas, or a classroom that wants in: open an issue right here.

## License

AGPL-3.0. Free and open source, forever.
