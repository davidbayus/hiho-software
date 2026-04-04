# Green Room — K-12 Blender Puppet Show Addon — Claude Code Project

## What This Is
A Blender Python addon that transforms Blender into a **puppet show** for K-12 students. Kids pick a character, customize it with sliders, connect their phone, and perform — their face drives the puppet in real time. Built as a CADRE Lab collaboration at SJSU, led by David Bayus (Digital Media Art lecturer, 10+ years teaching 3D).

This is **local software** — not "Blender for kids" as a product, but Blender re-crafted for specific kids in specific classrooms with specific constraints.

## Project Lead
David Bayus is NOT a programmer. He's a visual artist and professor who teaches the 3D character pipeline this addon is based on. He'll describe what things should DO and how they should FEEL. You write the code. Ask clarifying questions when behavior is ambiguous — don't guess.

## Design Philosophy (Read This First)
- **Kid Pix is the north star.** A kid should be able to use this without an adult in the room. No dialog boxes. No modal interruptions. No dead ends.
- **One button per operation.** "Start the Show" not "Configure OSC → Set Port → Enable Face Tracking → Switch to EEVEE."
- **7 tools max for the Stage.** Radical tool reduction. Constraint enables creativity.
- **Performance frames the experience.** The kid isn't learning "3D." They're making a puppet show. The technology disappears.
- **Start with something, never nothing.** Addon opens with a puppet already on screen, ready to connect.
- **The "Kid Pix moment":** Kid opens addon → scans QR code → puppet moves with their face. Under 30 seconds. Zero instruction needed.

## Two-Track Architecture

### Track 1: The Stage (K–8, Elementary & Middle School)
**Who:** Young students, no 3D experience assumed.

**The experience:** Pick a puppet → customize it → connect your phone → perform → record → share.

**Character creation:** Preset procedural characters built as geometry nodes templates. The kid picks a type and adjusts parameters (body shape, colors, eye size). No modeling, no sculpting, no UV unwrapping. Customization IS the creative expression.

**The performance:** Phone face tracking (ARKit → Live Link Face → OSC) drives the character in real time. Kid's facial expressions become the puppet's movements. Can be live (projected in classroom) or recorded.

**Target buttons (the entire UI):**
1. Pick Your Puppet (template browser with thumbnails)
2. Make It Yours (customization sliders — colors, shape, features)
3. Pick Your Stage (backdrop/environment selection)
4. Connect My Phone (one-button phone pairing, ideally QR code)
5. Start the Show (begins live performance mode with EEVEE viewport)
6. Record My Show (captures the performance to video)
7. Share My Show (one-click export)

### Track 2: The Studio (High School / CADRE)
**Who:** Older students with some 3D basics, CADRE Lab students at SJSU.

**The experience:** Design a character from scratch → clean it up → paint it → rig it → perform with it. The full pipeline, but the payoff is still performance — you build a puppet template others can use.

**What this track includes:**
- Blockout with primitives (manual — the learning IS the doing)
- "Clean Up My Shape" (voxel remesh + quad remesh via QRemeshify, one button)
- Auto-UV on entering paint mode (custom heuristic seam placement)
- Texture painting (manual — direct expression)
- Geometry-nodes-based character setup with face tracking inputs
- "Publish Template" — package a character as a puppet template for younger students

**The ecosystem:** Older students build puppet templates. Younger students perform with them. Each semester the library grows. A CADRE student's final project: "build a puppet template used in three elementary classrooms."

## The Puppet Template Spec
A puppet template is a `.blend` file with a standard structure so the addon can load, customize, and perform with any template:

1. **Main geometry nodes tree** — procedural character exposing Group Inputs for:
   - Customization (body width, leg count, eye size, color palette — designer's choice)
   - Face tracking inputs (mouth_open, jaw, eye_blink_L/R, head_rotation — standardized)
2. **`ARKitShapeKeys.Dummy` mesh** — hidden mesh with 13 active ARKit shape key names for FOSCAP
3. **Scripted expressions** — connecting shape key values to geonode inputs
4. **Camera rig** — auto-framing camera that adapts to character shape
5. **Armature with head bone** — target for head rotation from phone
6. **Metadata** — template name, author, thumbnail, recommended age range

## Target Blender Version
- Blender 5.0+ (David's current version, confirmed working)
- Must run in EEVEE real-time (engine name is `BLENDER_EEVEE` in 5.0, NOT `BLENDER_EEVEE_NEXT`)

## Project Structure
```
green_room/
├── __init__.py                  # bl_info, register/unregister, shared state
├── core/
│   ├── osc_receiver.py          # FOSCAP fork — OSC/Live Link Face data receiver ✅ V0.1.0
│   ├── phone_connect.py         # IP detection, QR code generation ✅ V0.1.0
│   ├── template_loader.py       # Load, validate, and instantiate puppet templates
│   ├── template_spec.py         # Template validation — checks required components
│   └── performance_recorder.py  # Record face tracking + viewport to video
├── operators/
│   ├── connect_phone.py         # One-button phone connection ✅ V0.1.0
│   ├── pick_puppet.py           # Template browser with thumbnails
│   ├── customize_puppet.py      # Expose template parameters as kid-friendly sliders
│   ├── pick_stage.py            # Backdrop/environment selector
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
│   ├── panels.py                # N-panel UI — connection, instructions, live data ✅ V0.1.0
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

## What to Build First (Priority Order)
1. ~~**FOSCAP integration** — fork the OSC receiver, one-button phone connect~~ ✅ V0.1.0
2. ~~**Starter puppet template** — one working procedural character~~ ✅ V0.1.0 (blob template)
3. ~~**QR code phone pairing** — streamlined classroom setup~~ ✅ V0.1.0 (zero-dependency QR generator)
4. **Research Will Anderson's node setups** — study his videos for character design patterns, shape variety, and artistic style in geometry nodes
5. **Template loader** — load a puppet template, validate it, instantiate it
6. **Customization UI** — read geonode Group Inputs, expose as kid-friendly sliders
7. **Performance mode** — EEVEE viewport, camera rig, live face tracking
8. **Recording + export** — capture performance to video, one-click share
9. **Template browser** — thumbnails, stage/backdrop selection
10. **Studio track tools** — quad remesh (QRemeshify), auto-UV, template publishing
11. **Polish** — startup scene, tool reduction, workspace setup

## Existing Work

### PaWrappa the UV Unwrapper (V0.3.2 — Student Testing Ready)
Auto-UV tool lives in `UV_UNWRAPER/`. N-panel tab is "PaWrappa". Class prefix: `PAWRAPPA`. Operator prefix: `pawrappa.*`.

**Current state (April 3, 2026): Curvature-based face clustering VALIDATED. Ready for student testing.**

The V0.2.0 three-button approach (Character/Simple Shape/Thingamabob) has been replaced by one universal algorithm: Lloyd-style face clustering with a merge threshold slider. One button works on any shape.

**What exists now:**
- **Auto Seams** (primary tool) — one-click curvature-based face clustering + SLIM unwrap + pack. Merge threshold slider controls island count (F9 redo panel).
- **Edge Scorer** — debug tool, hidden under Advanced Tools
- **Legacy modes** — Character/Simple Shape/Thingamabob, hidden under Advanced Tools

**Algorithm:**
1. Score every edge by dihedral angle (curvature signal)
2. Pick seed faces via farthest-point sampling (deterministic, starts from face 0)
3. Grow clusters using heapq priority queue with normal deviation + edge crossing cost
4. Lloyd iteration (8 passes) — recompute seeds, reassign faces
5. Merge small clusters (< 3 faces)
6. Cluster boundaries → seams → SLIM unwrap → average island scale → pack

**Key parameters (F9 redo panel):**
- **Merge Threshold** (0.05–0.95, default 0.50) — left = more islands, right = fewer. Sweet spot for characters: 0.85–0.90
- **Normal Sensitivity** (0.1–3.0, default 1.0) — how strictly clusters follow surface direction
- **Prefer Concave Seams** (default ON) — 1.5x weight on concave edges (armpits, creases)
- **Hide Seams on Back +Y** (default ON) — 0.85x cost on back-facing edges
- **Refinement Passes** (1–30, default 8) — Lloyd iterations

**Validated test results (April 3, 2026) across 5 shape types:**

| Shape | Sweet Spot | Result | Notes |
|-------|-----------|--------|-------|
| Chibi character | 0.90 | PASS | 177 seams, clean body-part islands. One weird spot at 0.40 (expected — cluster count fights mesh's natural segmentation) |
| Mechanical (hard-surface) | 0.50–0.90 | PASS | Works great across full range. Strong curvature signals = clear boundaries |
| Simple organic | 0.90 | PASS | Each lobe = one island. Seams land in creases between bumps |
| Tube | — | KNOWN LIMITATION | Curvature only finds ring cuts, can't place lengthwise seam. Students need one manual cut. Same issue as SP. |
| Thingamabob (mixed) | 0.85 | PASS | Mixed morphology handled well. Each protrusion gets its own island |

**Scaling:** Linear cluster formula (`sqrt(faces) * (1 - threshold)`). Quadratic was tested and reverted — collapsed upper slider range. Linear gives better gradient across all shapes. Each shape has natural "sweet spots" on the slider.

**UI (student-ready):**
- One big "Auto Seams" button
- Plain English instructions: "Slide left = more pieces, slide right = fewer pieces"
- Status: UV map name, seam count, vert/face count
- Advanced Tools collapsed (Score Edges + Legacy Modes)

**Key files:**
- `UV_UNWRAPER/operators/face_cluster.py` — the core algorithm (Lloyd clustering + full unwrap pipeline)
- `UV_UNWRAPER/operators/edge_scorer.py` — curvature visualization debug tool
- `UV_UNWRAPER/operators/auto_uv.py` — legacy three-mode unwrapper
- `UV_UNWRAPER/ui/panels.py` — student-ready N-panel
- `UV_UNWRAPER/core/seam_generator.py` — legacy seam generation algorithms
- `CURVATURE_SEAM_RESEARCH.md` — research on SP's approach, math, references

**IMPORTANT — Testing gotcha:** OBJ export/reimport changes vertex/face ordering, which changes deterministic seed placement and produces different results. Always test with native .blend files, never exported OBJs.

This is **Studio Track** tooling. It's NOT needed for the Stage Track (K-8 puppet show) because puppet templates use procedural geometry with solid colors, not painted textures.

See `SESSION_NOTES.md` for detailed development history and known issues.

**Key lessons from development:**
- Make ONE change at a time. Test each change before making the next.
- Commit working states to git. Don't rewrite multiple files simultaneously.
- Boundary smoothing was attempted and reverted (no improvement at chaotic cluster counts).
- Quadratic slider scaling was attempted and reverted (collapsed upper range).
- Failed experiments are fine — revert cleanly and move on.

**Next steps for PaWrappa:**
- Student testing feedback (high school CADRE students)
- Tube/cylinder handling (topology-aware lengthwise cuts — V2 feature)
- Adaptive thresholding for smooth organic shapes with subtle curvature
- Consider exposing merge threshold directly in N-panel instead of F9-only

### QUADRE Quad Remesher (V0.1.0 — Beta, for Studio Track)
Quad remesher addon wrapping QuadWild (open-source). Lives in a separate repo/folder. N-panel tab is "QUADRE".

**Current state:** Shipped V0.1.0, students testing. ~80-85% of Exoside Quad Remesher quality. Known issue: unsigned dylibs need codesigning fix before Mac lab deployment. Some meshes produce pinching artifacts in concave regions (observed April 2, 2026 during PaWrappa testing).

**Pipeline role:** "Clean Up My Shape" button in the Studio Track. Student sculpts → QUADRE remeshes to clean quads → PaWrappa auto-UVs → student paints. QUADRE output quality directly affects PaWrappa's seam placement, so these two addons must be tested together.

**Note:** While QUADRE is in beta, use Exoside for test meshes when testing PaWrappa to isolate variables.

### Green Room Addon (V0.1.0 — Phone-to-Puppet Working)
Puppet show addon lives in `green_room/`. N-panel tab is "Green Room". Class prefix: `GREENROOM`. Operator prefix: `greenroom.*`. Property prefix: `gr_`.

**Current state (April 3, 2026): End-to-end face tracking pipeline WORKING.**

Phone → Live Link Face app → UDP → OSC receiver → dummy mesh shape keys → drivers → geometry nodes → puppet moves. Head rotation, eye blink, jaw open, smile, pucker all confirmed working.

**What exists now:**
- **OSC Receiver** (`core/osc_receiver.py`) — FOSCAP fork, class-based, threaded, 13 active ARKit blend shapes. Timer callback at 10ms pushes shape key values + head rotation to Blender objects.
- **Phone Connect** (`core/phone_connect.py`) — IP detection + QR code PNG generation, zero external dependencies
- **QR Generator** (`core/qr_gen.py`) — Complete QR code encoder from scratch (~280 lines). GF(256) arithmetic, Reed-Solomon error correction, versions 1-4, EC level L. Written because pip-installing qrcode in classrooms is a non-starter.
- **Connect Operator** (`operators/connect_phone.py`) — One button: creates dummy mesh, starts receiver, finds armature with "head" bone, generates QR, shows in panel
- **N-Panel** (`ui/panels.py`) — Three states: disconnected (port + connect button), waiting (QR code + instructions), receiving (live face data values)
- **Blob Puppet Template** (`assets/templates/blob/blob_puppet.blend`) — Procedural character built entirely in one geometry nodes tree (95 nodes, 133 links). Face tracking inputs as Group Inputs driven by dummy mesh shape keys via drivers. Customization sliders: Body Width/Height, Eye Size/Spacing, Ear Size, Mouth Size. Armature with "head" bone for phone rotation (Euler XYZ mode).
- **Template Generator** (`assets/create_blob_template.py`) — Python script that builds the blob template programmatically. Run inside Blender to regenerate.

**Key architecture decisions:**
- **Driver path format**: `modifiers["GeometryNodes"]["Socket_X"]` where Socket_X is the interface identifier from `tree.interface.items_tree`
- **Bone rotation mode**: Must be set to `'XYZ'` (Euler) — Blender defaults to Quaternion which ignores `rotation_euler` values from the phone
- **QR text format**: `"Green Room\nIP: {ip}\nPort: {port}"` — plain text prevents iOS from interpreting as URL
- **Dummy mesh pattern**: Hidden mesh `ARKitShapeKeys.Dummy` with shape keys matching ARKit blend shape names. OSC receiver writes values here, drivers read them.

**Known issues / next steps:**
- **Latency / skipping on fast head movement** — noticed during testing (April 3, 2026). Likely causes: viewport redraw throttled to 0.5s in `_apply_updates()`, UDP packet processing bottleneck, or Blender's depsgraph update speed. Needs research into e-waste-friendly solutions (no GPU compute, must stay open source). See "Latency Research" section below.
- Character design is basic — needs Will Anderson-style artistic variety (shape language, proportions, personality). Research his video tutorials for geometry node patterns.
- Template is functional but not beautiful — David wants to bring his own design sense into the node setup, which is important for high school (ART102) and CADRE students
- No template loader yet — currently must manually open .blend files
- No customization UI beyond the modifier panel — need kid-friendly sliders in N-panel
- Mouth hangs down like a tongue when jaw opens wide — scaling approach needs refinement (Will Anderson uses a 2x2 grid with profile curves, not scaled spheres)

**Latency Research (TODO — next session):**
Observed: head rotation skips/jumps during fast movement. Need to investigate and fix while staying e-waste friendly (8GB RAM, integrated GPU, no CUDA).

Possible causes to investigate:
1. **Viewport redraw throttle** — `_last_redraw_time` in osc_receiver.py only redraws every 0.5s. This is WAY too slow for smooth head tracking. The shape keys update at 10ms but the viewport doesn't show it. Try reducing to 0.033s (30fps) or removing throttle entirely.
2. **UDP packet drops** — socket buffer may overflow during fast movement. Could increase buffer size with `sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 65536)`.
3. **Thread lock contention** — the `_pending` list copies all updates every 10ms. Could switch to a lock-free ring buffer or only keep latest values (discard stale frames).
4. **Depsgraph updates** — Blender may batch dependency graph updates. Could try `bpy.context.view_layer.update()` or `depsgraph.update()` after applying values.
5. **Timer resolution** — `return 0.01` (10ms) is the requested timer interval but Blender's actual timer resolution may be lower. Test actual callback frequency.
6. **Live Link Face app send rate** — the app may send at 60fps but we may be processing slower. Log actual packet rate to verify.

Constraints (non-negotiable):
- Must run on integrated GPU (Intel HD / AMD Vega)
- No CUDA, no OpenCL compute
- 8GB RAM total
- Open source only
- No internet required

### Reference Material (in R&D/ folder)
- `PUPPET_SHOW_DESIGN_REVISION_2026-04-01.md` — Full design document for the puppet show architecture
- `REAL TIME_PUPPETRY IN BLENDER.md.txt` — Transcript of Will Anderson's Blender Conference 2025 talk
- `okgo_impulse_purchase-demo-v005.blend` — OK Go demo file (primary reference)
- `foscap-1.0.0.zip` — FOSCAP addon source (OSC receiver, GPL-3, ~400 lines)

### Reference Addons (in FOR_PROFITS_TESTCASES/)
- `AutoUV.zip` — Ministry of Flat wrapper (simple, Japanese)
- `G_Ready_Source.zip` — Ministry of Flat wrapper (full-featured, 30+ parameters)
- Both are wrappers around proprietary Windows-only .exe — can't use directly, but studied for approach

## Dependencies Policy
- **ZERO paid dependencies.** Non-negotiable.
- Blender's bundled Python + standard library = always OK
- numpy/scipy = OK (bundled with Blender)
- FOSCAP = OK (GPL-3, open source, we fork it)
- Live Link Face app = OK (free, runs on student's own phone)
- Any pip-installable pure Python library = OK but document it
- Anything requiring user to install external software = NOT OK for the final addon

## Hardware Target
The addon must run on "Scrap in a Box" hardware — repurposed e-waste machines for low-income K-12 schools:
- ~8GB RAM
- Integrated GPU (no discrete graphics card)
- Linux or Windows
- No internet required after install (phone connects via local WiFi)
- Phone/tablet for face tracking (student's own device)

## Code Style
- PEP 8
- Type hints where possible
- Every operator needs a docstring explaining what it does in plain English
- Blender class naming: `PAWRAPPA_OT_edge_score`, `PAWRAPPA_PT_uv_panel` (UV addon), `GREENROOM_OT_connect_phone` (puppet show addon)
- Prefix all custom properties with `gr_` (Green Room / puppet show) or `pw_` (PaWrappa) to avoid namespace collisions

## Communication Style
David talks like an artist, not an engineer. When explaining what you've built or asking questions:
- Use plain language, not jargon
- Show what changed, not how the code works internally
- "The puppet now follows your mouth" > "Implemented OSC UDP receiver with ARKit blend shape decoding"
- If something fails, explain what the user would SEE, not what the stack trace says

## Git
Git is initialized in this folder. Use `git log` to see history. Always commit working states before making changes.

**Commit history:**
```
3a3796c V0.1.0 — Green Room addon + blob puppet template (geometry nodes)
2fffee1 V0.3.3 — Cleaner UI + a student's testing guide
f8757bf V0.3.2 — Student-ready UI + restored exact V0.3.0 algorithm
0fccc6b V0.3.1 — Face clusterer validated across 5 shape types
47a9490 V0.3.0 — PaWrappa rename + curvature-based face clustering
dc50fb6 Pivot to puppet show architecture — two-track design
9221dfc Add session notes for continuity between sessions
1476272 V0.2.0 — Stable baseline with three working shape modes
```
