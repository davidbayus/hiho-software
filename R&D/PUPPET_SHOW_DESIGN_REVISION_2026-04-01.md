# K-12 Blender Addon — Revised Design: The Puppet Show
**Date:** April 1, 2026
**Participants:** David Bayus + Claude
**Status:** Design revision — replaces pipeline-first architecture with performance-first architecture
**Context:** Builds on `Addon_Design_Brainstorm_2026-03-30.md` and R&D session analyzing Blender Conference 2025 talks + FOSCAP addon + OK Go demo file

---

## What Changed and Why

The original addon design (documented in `CLAUDE.md`) compressed David's 8-phase ART 102 character pipeline for younger students. That's a top-down simplification: take the adult workflow, automate the hard parts, hide the complexity. It works, but it puts the kid in the position of doing a junior version of what college students do.

This revision **flips the motivation**. The kid isn't learning "3D character creation." They're making a character *so they can perform with it*. The performance is the point. Character creation is just what you do to get there.

### The Insight

David's own art practice uses motion capture of his physical performances to animate his characters. A kid performing with a puppet they built — face tracked by a phone, character reacting on screen in real time — is doing the same thing at a simpler scale. The puppet show is the storytelling. The technology disappears.

### Why This Is Stronger

1. **Storytelling-first for real, not just in naming.** The original plan named workspaces after narrative stages ("Build Your World") but the pipeline was still fundamentally technical. The puppet show makes performance the actual structure of the experience.

2. **Hardware-optimized by design.** The original pipeline asked low-end machines to do voxel remeshing, quad remeshing, multires sculpting, and normal map baking — all computationally heavy. The puppet show asks for: a procedural geometry nodes character (lightweight), EEVEE real-time rendering, and UDP packets from a phone. Will Anderson's OK Go character runs in real time on a laptop.

3. **The phone is the mocap rig.** Every kid has access to a phone or tablet. Live Link Face is free. No external hardware purchases. No Kinect, no Rokoko suit, no webcam addon. This is critical for the Scrap-in-a-Box deployment model.

4. **Creates an ecosystem, not just a tool.** Older students (high school, CADRE) build puppet templates. Younger students perform with them. Each semester the library grows. A CADRE student's final project could be "build a puppet template used in three elementary classrooms." That's portfolio material AND community impact.

---

## Two-Track Architecture

### Track 1: The Stage (K–8, Middle School)

**Who:** Elementary and middle school students, no 3D experience assumed.

**The experience:** Pick a puppet → customize it with sliders → connect your phone → perform → record → share.

**Character creation:** Preset procedural characters built as geometry nodes templates. The kid picks a character type and adjusts parameters: body shape, limb count, colors, eye size, personality. No modeling, no sculpting, no UV unwrapping. The customization IS the creative expression at this level.

**The performance:** Phone face tracking drives the character in real time via OSC. The kid's facial expressions, head tilts, and mouth shapes become the character's movements. This can be:
- **Live** — projected in the classroom, kids take turns, audience participation. This is theater. This is public speaking disguised as art class.
- **Recorded** — the shy kid who doesn't want to perform live can still make their puppet show, record it, share it as a video.

**Target buttons (the entire UI):**
1. Pick Your Puppet (template browser with thumbnails)
2. Make It Yours (customization sliders — colors, shape, features)
3. Pick Your Stage (backdrop/environment selection)
4. Connect My Phone (one-button phone pairing, ideally via QR code)
5. Start the Show (begins live performance mode with EEVEE viewport)
6. Record My Show (captures the performance to video)
7. Share My Show (one-click export)

That's 7 buttons. Under the 8-12 max. A kid can understand the entire interface in under a minute.

**The "Kid Pix moment" (first 30 seconds):**
The addon opens with a puppet already on screen in a colorful stage environment. The kid taps "Connect My Phone," scans a QR code, and immediately their face is driving the puppet. They open their mouth — the puppet opens its mouth. They tilt their head — the puppet tilts. Laughter. Delight. Zero instruction needed. That's the hook.

### Track 2: The Studio (High School / CADRE)

**Who:** High school students with some 3D basics, CADRE Lab students at SJSU.

**The experience:** Design a character from scratch → clean it up → paint it → rig it → perform with it. The full ART 102-adjacent pipeline, but the *payoff* is still performance. You build a more refined character and then you puppeteer it.

**What stays from the original plan:**
- Blockout with primitives (manual — the learning IS the doing)
- "Clean Up My Shape" (voxel remesh + quad remesh, one button)
- Auto-UV on entering paint mode
- Texture painting (manual — direct expression)
- Simplified rigging or geometry-nodes-based character setup

**What's new:**
- The endpoint is a **puppet template**, not just a finished character
- Students learn to expose parameters in geometry nodes (what should be customizable?)
- Students learn to set up face tracking inputs (which blend shapes drive what?)
- The design challenge becomes: "make a character system someone else can use" — that's a fundamentally different level of thinking than "make a character"

**Template creation as pedagogy:**
Designing for someone else requires empathy, systems thinking, and an understanding of constraints — exactly the skills David teaches. A CADRE student who builds a puppet template that elementary kids love has demonstrated mastery of character design, procedural thinking, AND user-centered design.

---

## Technical Architecture

### The Puppet Template Spec

A puppet template is a `.blend` file that follows a standard structure so the addon can load, customize, and perform with any template interchangeably.

**Required components:**

1. **Main geometry nodes tree** — the procedural character, exposing Group Input parameters for:
   - Customization (body width, leg count, eye size, color palette, etc. — designer's choice)
   - Face tracking inputs (mouth_open, jaw, eye_blink_L, eye_blink_R, head_rotation — standardized)

2. **`ARKitShapeKeys.Dummy` mesh** — a hidden mesh with the 13 active ARKit shape key names that FOSCAP targets:
   - eyeLookIn_L/R, eyeLookOut_L/R
   - mouthFunnel, mouthPucker, mouthSmileRight, mouthClose
   - jawOpen
   - eyeBlink_L/R, eyeWideL/R

3. **Scripted expressions** — connecting shape key values to geometry node Group Input properties (simple math: add, subtract, multiply, amplify)

4. **Camera rig** — auto-framing camera that adapts to the character's shape and movement

5. **Armature with head bone** — target for head rotation data from phone

6. **Metadata** — template name, author, thumbnail, recommended age range, description

### The Addon (All-in-One)

One addon that handles everything. No separate FOSCAP install. No manual file management.

```
addon/
├── __init__.py                  # bl_info, register/unregister, mode switching
├── core/
│   ├── osc_receiver.py          # FOSCAP fork — OSC/Live Link Face data receiver
│   ├── phone_connect.py         # Auto-discovery / QR code phone pairing
│   ├── template_loader.py       # Load, validate, and instantiate puppet templates
│   ├── template_spec.py         # Template validation — checks required components
│   └── performance_recorder.py  # Record face tracking + viewport to video
├── operators/
│   ├── pick_puppet.py           # Template browser with thumbnails
│   ├── customize_puppet.py      # Expose template parameters as kid-friendly sliders
│   ├── pick_stage.py            # Backdrop/environment selector
│   ├── connect_phone.py         # One-button phone connection
│   ├── start_show.py            # Enter performance mode (EEVEE viewport)
│   ├── record_show.py           # Start/stop recording
│   ├── share_show.py            # One-click export (video/GIF/image)
│   │
│   │  # --- Studio Track (High School / CADRE) ---
│   ├── cleanup_shape.py         # "Clean Up My Shape" — voxel + quad remesh
│   ├── auto_uv.py               # Automatic UV unwrapping
│   ├── auto_bake.py             # Automated normal map bake
│   └── publish_template.py      # Package a character as a puppet template
├── ui/
│   ├── panels.py                # Custom UI panels — Stage mode vs Studio mode
│   ├── workspaces.py            # Workspace definitions per track
│   └── startup_scene.py         # Pre-loaded puppet + stage on addon activation
├── assets/
│   ├── templates/               # Bundled puppet templates (starter library)
│   │   ├── basic_biped/
│   │   ├── basic_quad/
│   │   └── blob/
│   ├── stages/                  # Backdrop environments
│   └── startup.blend            # Default scene
└── tests/
    ├── test_osc_receiver.py
    ├── test_template_loader.py
    └── test_template_spec.py
```

### What We're Building vs. What Already Exists

| Component | Status | Source |
|-----------|--------|--------|
| OSC face tracking receiver | **Done** — fork FOSCAP | FOSCAP 1.0.0 (GPL-3, Blender Studio) |
| Procedural character in geonodes | **Proven** — study OK Go demo | Will Anderson / Blender Studio (CC BY-SA) |
| EEVEE real-time performance | **Built into Blender** | Blender 4.2+ |
| Live Link Face app | **Free, existing** | Epic Games (iOS/Android) |
| Template browser UI | **Build this** | Our addon code |
| One-button phone pairing | **Build this** | Our addon code (wraps FOSCAP) |
| QR code for connection | **Build this** | Python qrcode lib + FOSCAP |
| Customization slider UI | **Build this** | Our addon code (reads geonode inputs) |
| Performance recorder | **Build this** | Viewport capture + keyframe recording |
| Puppet template spec | **Define this** | Our standard |
| Stage/backdrop system | **Build this** | Simple HDRI or scene switching |
| Quad remesher (Studio track) | **Hard problem** — still needed for high school track | QRemeshify / QuadWild-BiMDF |
| Auto-UV (Studio track) | **Hard problem** — still needed for high school track | Custom heuristic seam placement |
| Template publishing tool | **Build this** | Our addon code |

### Key Simplification

The two hardest engineering problems from the original plan — the free quad remesher and automatic UV unwrapping — are **no longer blockers for the primary experience**. They move to the Studio track (high school / CADRE), which is a later build priority. The Stage track (K–8) can ship without them because puppet templates are pre-built by older students using whatever tools are available (including manual retopo if needed).

This means we can have a working, shippable K–8 experience much sooner.

---

## Research Sources (This Session)

### Video Transcripts (in R&D folder)

1. **"ClayPencil: Animating In 3D Using 2D, Animating Without Rig"** — Daniel Martínez Lara, Blender Conference 2025
   - 16 years of development aimed at minimizing rigs for 3D animation
   - ClayPencil: Grease Pencil 2D drawing + Geometry Nodes → 3D animated objects
   - Material-based workflow: different stroke materials get different geometry node treatments
   - *Decision: Interesting R&D direction but different geonodes architecture. Back-burnered in favor of Will Anderson's pipeline for v1.*

2. **"Real Time Puppetry in Blender"** — Will Anderson, Blender Conference 2025
   - OK Go "Impulse Purchase" music video — entirely procedural character in one geometry nodes tree
   - Face tracking via ARKit / Live Link Face → OSC → shape keys → geometry node inputs
   - Runs in real time in EEVEE
   - Character built from simple parametric shapes (cube → bevel → sphere → capsule)
   - Camera rig that auto-adapts to dynamic character changes
   - Open source, downloadable from Blender Studio
   - *Decision: This is our primary reference pipeline. Similar ethos to David's, proven on low-end hardware, open source.*

### Production Files (in R&D folder)

3. **okgo_impulse_purchase-demo-v005.blend** — The actual demo file
   - Blender 4.5 format (zstd compressed)
   - Key objects: body, Camera, cameraPos, ARKitShapeKeys.Dummy, mouth, arm.L/R, forearm.L/R, PhysicsLimb.L/R
   - Key node trees: gn-proceduralCharacter.Final, gn-body, gn-head-mouth, gn-characterRoll, gn-track linear point, camera Position, color-switcher
   - 1695 GeometryNode references, 208 Group Inputs — substantial procedural setup
   - Includes recorded iPhone face capture data (MySlate_7_iPhone action)

4. **foscap-1.0.0.zip** — The OSC receiver addon
   - Single file, ~400 lines of Python, GPL-3
   - Receives Live Link Face data over UDP/OSC
   - Decodes 61 ARKit blend shapes, uses only 13 active ones
   - Updates shape keys on ARKitShapeKeys.Dummy mesh
   - Head rotation drives armature bone
   - Simple recording system (keyframes everything during performance)
   - UI: three buttons (Play Animation, Start OSC, Start Recording) + settings panel

5. **Blender + OSC Live Puppeteering Demo** (PDF) — Blender Studio blog post
   - Step-by-step setup guide for FOSCAP + demo file
   - Requirements: Blender 4.5 LTS, FOSCAP addon, Live Link Face app, same WiFi network
   - Confirms the pipeline is simple enough for a blog tutorial

---

## What This Means for CLAUDE.md

The existing `CLAUDE.md` in the project root should be updated to reflect the puppet show architecture. Key changes:

1. **Design philosophy stays the same** — Kid Pix principles, local software, storytelling-first. The puppet show is a *better* expression of these principles, not a departure from them.

2. **Pipeline table gets replaced** with the two-track architecture (Stage vs Studio).

3. **Priority order changes:**
   - Build priority 1: Addon shell + FOSCAP integration (fork OSC receiver, one-button connect)
   - Build priority 2: Template loader + starter puppet template
   - Build priority 3: Customization UI (read geonode inputs, expose as sliders)
   - Build priority 4: Performance mode (EEVEE viewport, camera rig)
   - Build priority 5: Recording + export
   - Build priority 6: Template browser + stage/backdrop system
   - Build priority 7: Studio track tools (quad remesh, auto-UV, template publishing)
   - Build priority 8: QR code phone pairing, polish, startup scene

4. **Critical technical challenges shift.** The two hardest problems (quad remesher, auto-UV) are no longer blockers for v1. The new challenges are:
   - Defining and validating the puppet template spec
   - Auto-discovering phones on the network (or QR code fallback)
   - Smooth viewport recording during live performance
   - Building a template browser UI that feels like picking a toy, not browsing files

5. **Project structure changes** to reflect the new file layout (see Technical Architecture above).

---

## Open Questions (Carry Forward)

1. **What's the template creation workflow for CADRE students?** Do they start from a blank geonodes setup, or do we provide a "template starter kit" with the required components pre-wired?

2. **How does the phone pairing work in a classroom with 30 phones on the same WiFi?** Each instance needs a unique port. Auto-assign? Manual selection? Teacher dashboard?

3. **Can we do body tracking, not just face?** MediaPipe or similar could add hand/body pose. Probably v2, but worth noting.

4. **What does "Share My Show" output?** Video file? GIF? Direct upload to a class gallery? YouTube?

5. **What's the progression from Stage to Studio?** Is there a moment where a kid "graduates" from performing with pre-made puppets to building their own? What triggers that?

6. **Does the puppet show need multiple characters?** Can two kids perform together — two phones, two puppets, one scene? That's a puppet show in the traditional sense.

7. **What about sound/music?** A puppet show needs audio. Does the kid record narration? Pick from a music library? Both?

8. **The metaphor question (from March 30 brainstorm) is now answered:** It's a puppet show. The overall metaphor is theater/performance. "The Stage" and "The Studio" as the two modes.

---

*This document captures the design pivot of April 1, 2026. It should be read alongside `Addon_Design_Brainstorm_2026-03-30.md` (pedagogical theory, Kid Pix principles, local software thesis) and the R&D transcripts in this folder. The next step is to update CLAUDE.md in the project root and begin building in Claude Code.*
