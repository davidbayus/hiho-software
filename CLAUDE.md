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
- **Green Room:** Blender 5.0+ (confirmed working)
- **PPParty:** Blender 5.2 Alpha (David installed April 9, 2026 — from builder.blender.org — to access experimental XPBD solver features)
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

### Green Room Addon (V0.7.0 — Nose + Latency Optimization)
Puppet show addon lives in `green_room/`. N-panel tab is "Green Room". Class prefix: `GREENROOM`. Operator prefix: `greenroom.*`. Property prefix: `gr_`.

**Current state (April 8, 2026): Nose added, QR code removed (pending fix), OSC receiver optimized for travel router deployment, node tree trimmed (30 nodes removed — UV Unwrap overhead eliminated for solid-color materials).**

Phone → Live Link Face app → UDP → OSC receiver → dummy mesh shape keys → drivers → geometry nodes → puppet moves. Head rotation, eye blink, jaw open, smile/frown, pucker, eye look direction all working. Blob puppet has reactive eyebrows and nose.

**What exists now:**
- **OSC Receiver** (`core/osc_receiver.py`) — FOSCAP fork, class-based, threaded, 13 active ARKit blend shapes. Timer callback at 10ms pushes shape key values + head rotation to Blender objects. V0.7.0: 64KB UDP receive buffer (busy WiFi), cached shape key + bone refs, O(1) dict swap.
- **Phone Connect** (`core/phone_connect.py`) — IP detection, zero external dependencies. QR generation code still present but not called (QR display removed from UI pending fix).
- **QR Generator** (`core/qr_gen.py`) — Complete QR code encoder from scratch (~280 lines). GF(256) arithmetic, Reed-Solomon error correction, versions 1-4, EC level L. Written because pip-installing qrcode in classrooms is a non-starter. Currently unused — will be re-enabled when QR issues are resolved.
- **Connect Operator** (`operators/connect_phone.py`) — One button: creates dummy mesh, starts receiver, finds armature with "head" bone, reports IP/port
- **Template Loader** (`core/template_loader.py`) — Loads .blend puppet templates, validates structure, wires drivers from dummy mesh to geonode inputs
- **Template Spec** (`core/template_spec.py`) — Validates templates: checks for geonode modifier, armature with "head" bone, face tracking inputs, customization inputs. Groups sockets by panel.
- **Puppet Picker** (`operators/pick_puppet.py`) — Browse and load available puppet templates
- **Customize Puppet** (`operators/customize_puppet.py`) — N-panel "Make It Yours" section draws customization sliders grouped by body part (Body, Eyes, Mouth, Nose, Ears, Eyebrows). Also exposes Subdivision Surface "Smoothness" slider.
- **Calibrate Brows** (`operators/calibrate_brows.py`) — Developer tool: one-shot UDP capture to identify unknown ARKit blend shape indices. Results write to Blender Text Editor ("FaceSnapshot") — no Terminal needed.
- **N-Panel** (`ui/panels.py`) — Puppet panel (picker + customization sliders) + Connect panel (three states: disconnected, waiting, receiving). QR code display removed in V0.7.0.
- **Blob Puppet Template** (`assets/create_blob_template.py` → `assets/templates/blob/blob_puppet.blend`) — Procedural character with:
  - **Body parts**: Body, eyes, irises, pupils, ears, eyebrows (ALL dynamic capsules), nose (dynamic capsule), mouth, lips (curve-based)
  - **Face tracking** (13 ARKit inputs): jawOpen, mouth smile/frown/funnel/left/right, eye blink/wide/look per side
  - **Customization panels** (7 groups, 37 sliders):
    - Body: Width (0–2, capsule extension), Height, Rotation (-180°–180°), Color
    - Eyes: Size, Spacing, Height, Depth, Color, Width (0–2, football eye), Rotation (-180°–180°, tilted eye)
    - Mouth: Size, Height, Depth, Color
    - Nose: Size, Height, Depth, Color, Width (0–2, long nose), Rotation (-180°–180°)
    - Ears: Size, Height, Spread, Depth, Color, Width (0–2, long ear), Rotation (-180°–180°)
    - Eyebrows: Size, Height, Depth, Spread, Color, Width (0–2, wide brow), Rotation (-180°–180°)
    - Lips: Thickness, Color
  - **Dynamic capsules on ALL parts** (Minkowski sum in geonodes): Width slider extends the straight midsection while caps stay round. Width=0 → sphere (default, same as before), Width>0 → pill shape. Rotation tilts the capsule around Y axis. Eyes/irises/pupils share Eye Width + Eye Rotation so they stay aligned. Extension factors are proportional to each part's radius to maintain matching aspect ratios.
  - **Shade Smooth** applied to all joined geometry before output
  - **Subdivision Surface** modifier (level 2) with kid-friendly Smoothness slider
  - **Lip tube**: Curve Circle path (24pts) deformed by mouth field → Curve to Mesh with profile circle → 3D tube around mouth opening
  - **Eyebrow face tracking**: eyeWide lifts (0.15), eyeBlink drops (-0.12), per-side independent. Reactive rotation: frown+squint → angry inward V, smile+wide eyes → happy outward arch.
  - **Nose face tracking**: Reactive to jawOpen (drops) and mouthSmileRight (lifts). No dedicated ARKit nose inputs — reuses existing signals for lighter data pipeline.
  - **Mouth deformation**: Per-vertex field (squished circle, jawOpen drops bottom, smile/frown bends corners, funnel narrows, mouthLeft/Right shifts laterally at 0.35 strength)
  - **Material system**: Solid-color Principled BSDF materials, assigned via Set Material geonode. No UV Unwrap overhead — UVs deferred to future build for texture painting support.
  - Armature with "head" bone (Euler XYZ) for phone rotation
  - **Node tree spacing**: Rows spaced 400+ apart for readability in the Geometry Nodes editor

**Key architecture decisions:**
- **Dynamic Minkowski capsule (CRITICAL — hard-won lesson)**: You CANNOT get F9-style capsule behavior by scaling a fixed mesh. Uniform scaling stretches both the caps and midsection. The Blender Round Cube addon's `size` parameter works because it changes the GEOMETRY — vertices in the flat region stay flat, cap vertices stay on a sphere surface. To replicate this in geonodes, build the Minkowski sum math inline: subdivided cube → clamp each vertex to inner box (sized by Width slider) → offset from box → normalize × radius �� add to clamped position. The inner box half-extent IS the midsection length. When it's 0, all vertices map to a sphere. When it's >0, vertices inside the box stay flat = straight midsection.
- **`add_dynamic_capsule()` helper** — replaces the old `add_round_cube()`. Takes `width_output` (slider node output), `ext_factor` (per-part extension tuning), and `axis` ('X', 'Y', or 'Z' for extension direction). Body still uses inline Minkowski (pre-existing, untouched). All other parts use the helper.
- **Capsule axis selection**: Eyes/irises/pupils/eyebrows extend along X (football/horizontal pill). Ears extend along Z (vertical pill). Body extends along Z (inline, rotated 90° by body transform). The axis parameter sets which CombineXYZ input gets the dynamic extension — other axes stay at 2×radius.
- **Proportional extension factors**: Iris (ext_factor=0.16) and pupil (0.12) ext_factors are tuned so that at the same Eye Width slider value, all three (eye, iris, pupil) produce the same aspect ratio. Calculation: match eye's total/diameter ratio across all sub-parts.
- **Round Cube addon threshold gotcha**: The Extra Objects addon's `primitive_round_cube_add` operator has an internal threshold: `size` must exceed `2 * (radius - sagitta)` to produce ANY straight section. With radius=0.5 and arc_div=8, that threshold is ~1.0. Passing size=0.8 produces a sphere, not a capsule. This is why the Object Info approach failed — the reference mesh was just a sphere.
- **Driver path format**: `modifiers["GeometryNodes"]["Socket_X"]` where Socket_X is the identifier from `tree.interface.items_tree`
- **Bone rotation mode**: Must be set to `'XYZ'` (Euler) — Blender defaults to Quaternion which ignores `rotation_euler` values from the phone
- **Dummy mesh pattern**: Hidden mesh `ARKitShapeKeys.Dummy` with shape keys matching ARKit blend shape names. OSC receiver writes values here, drivers read them.
- **Geonode panels**: Blender 5.0 does NOT support nested panels (`new_panel(parent=...)` throws TypeError). Use separate top-level panels instead.
- **Solid-color materials**: `make_material()` creates Principled BSDF with a solid Base Color. Each body part gets a Set Material geonode (no UV overhead). UVs will be re-added in a future build when texture painting support lands.
- **Mouth deformation**: Flat circle mesh with per-vertex Set Position field. Y squished to 0.12 at rest (thin line). jawOpen pushes bottom verts down. Smile range is bidirectional: `(smile * 0.8 - 0.15) * abs(x)` gives slight frown at rest, full grin at smile=1.
- **Eyebrow position**: Independent from eyes — Eyebrow Spread/Depth/Height are separate sliders. Height still offsets FROM eyes_height_z so brows track vertically with eyes.
- **Socket cross-wiring prevention**: `setup_drivers()` maps by socket NAME not index. Adding new interface sockets won't shift existing driver targets. Always include ALL face tracking socket names in the face_inputs list.

**Next steps:**
- **Lightweight UV Unwrap** — Re-add UVs so kids can texture-paint their puppets. Must avoid per-frame recalculation (explore static UV bake or paint-mode-only generation).
- **QR code fix** — Re-enable QR display in Connect panel once the rendering issue is resolved
- Asymmetric controls (per-eye size, per-ear size) — David requested this
- Character design variety — needs Will Anderson-style artistic range

**Known issues:**
- **Mouth shape**: Mouth is large and fully open-looking at rest when mouth size is cranked up. May need squish factor to scale with mouth size.
- **Nose sneer indices**: ARKit noseSneerLeft/Right were not wired (indices couldn't be calibrated). Nose uses reactive movement from jawOpen/smile instead — works well, lighter pipeline.

**Calibration results (April 4, 2026):**
- **mouthLeft [21] CONFIRMED** — 0.914 when pushing mouth left
- **mouthRight [22] CONFIRMED** — 0.953 when pushing mouth right
- **mouthFrownLeft [25] CONFIRMED** — 0.165 (was flagged as dead, actually works)
- **mouthFrownRight [26] CONFIRMED** — 0.179 (was flagged as dead, actually works)
- Mouth lateral shift strength bumped from 0.15 → 0.35 (visible movement now)
- Latency fix (viewport redraw 0.5s → 0.033s) was already applied in V0.2.0

### Reference Material (in R&D/ folder)
- `PUPPET_SHOW_DESIGN_REVISION_2026-04-01.md` — Full design document for the puppet show architecture
- `REAL TIME_PUPPETRY IN BLENDER.md.txt` — Transcript of Will Anderson's Blender Conference 2025 talk
- `okgo_impulse_purchase-demo-v005.blend` — OK Go demo file (primary reference)
- `foscap-1.0.0.zip` — FOSCAP addon source (OSC receiver, GPL-3, ~400 lines)

### Reference Addons (in FOR_PROFITS_TESTCASES/)
- `AutoUV.zip` — Ministry of Flat wrapper (simple, Japanese)
- `G_Ready_Source.zip` — Ministry of Flat wrapper (full-featured, 30+ parameters)
- Both are wrappers around proprietary Windows-only .exe — can't use directly, but studied for approach

### PPPARTY — The People's Puppet Party (V0.4.1 — Joint Constraints + 3-Axis Torso)
Full-body digital marionette addon. Lives in `PPPARTY/`. N-panel tab is "PPPARTY". Class prefix: `PPPARTY`. Operator prefix: `ppparty.*`. Property prefix: `pp_`.

**Current state (April 10, 2026): Face-tracked blob head on physics marionette body with anatomically correct joint bending, foot spread/midline limits, ground friction, forward hinge bias on legs, 3-axis torso sway, walking bob, eyebrow/jaw lift, mouth lateral sway. Confirmed working on Blender 5.2 Alpha.**

**Core concept:** A digital marionette where face tracking provides the control input (like a marionette control bar), and Verlet physics makes the puppet body dangle and react. Face tracking drives facial expressions AND body movement. Inspired by traditional puppet rigging — Bunraku threshold toggles, marionette under-actuation, Henson's "maximum expression from minimum controls."

**What exists now:**
- **Create Marionette operator** (`operators/create_marionette.py`) — one button builds blob head + marionette body + sim zone physics + materials. Creates PP_Marionette mesh, PP_Armature (hidden, single "head" bone), ARKitShapeKeys.Dummy mesh.
- **Blob head** — loaded from `assets/blob_puppet.blend` as GN Group node (GN_BlobPuppet). Same head as Green Room. Scaled 0.6, positioned at (0, 0, 0.48).
- **Face tracking** — 15 ARKit shape keys (jawOpen, blink, smile, frown, pucker, eye look, etc.) + 3 head rotation axes. All wired as GN Group Inputs on the modifier.
- **Multi-channel body movement** — 6 face tracking channels drive body:
  - headRotY (lean) → lateral torso sway + contralateral gait
  - headRotX (extend) → forward/backward torso sway + Z dip + arm spread
  - abs(headRotY) → walking bob (vertical rise during stride)
  - mouthLeft/Right → lateral torso shift (0.3 chest, 0.2 pelvis)
  - eyeWideL/R avg → Z lift ("pick up" puppet, Lift Strength slider)
  - jawOpen → Z lift booster (stacks with brow lift)
- **Analytical two-bone IK** for elbows/knees — `_compute_mid_joint()` uses law of cosines + double cross product to compute joint position from attachment→endpoint vector. `bend_axis` parameter controls bend direction.
- **GN simulation zone physics** — Verlet integration + distance constraints. 9 state items: 4 endpoints, 4 previous, 1 initialized flag.
- **Joint constraints per endpoint:**
  - Arms: Y-axis hinge (prevents hyperextension), inward limit (prevents crossing body), midline clamp (hard stop at center)
  - Legs: -Y hinge with forward bias (`LEG_HINGE_BIAS = -0.06` → feet forced slightly forward), spread limit (`FOOT_SPREAD_DIR = 0.5`), midline clamp (`FOOT_MIDLINE = 0.08`)
  - Ground friction on feet (proximity-based XY velocity damping near floor)
  - Ground collision (Z clamp at floor height)
- **OSC receiver** (`core/osc_receiver.py`) — ported from Green Room, standalone. Threaded UDP, 13 active ARKit blend shapes. Pushes values directly to GN modifier (bypasses broken 5.2 drivers). Probe system: RNA → IDProperty → interface default_value fallback.
- **Phone connect** (`operators/connect_phone.py`, `core/phone_connect.py`) — one button: creates dummy mesh, starts receiver, finds PP_ armature, reports IP/port.
- **N-panel** (`ui/panels.py`) — Create Marionette, Body Movement sliders (Lean Strength, Extend Strength, Lift Strength), Physics sliders (Gravity, Damping, Arm/Leg Length, Ground Friction), Proportions, Connect Phone (3 states), Debug (collapsed), How to Use (collapsed).
- **Debug operator** (`operators/debug_modifier.py`) — dumps ALL modifier properties to "PPParty_Debug" text block.
- **Reset Physics operator** — jumps to frame 1 (re-initializes sim zone)

**Body parts:**
- **Chest** — oblate UV Sphere (radius 0.2, scaled 1.1 × 0.8 × 1.05)
- **Pelvis** — oblate UV Sphere (radius 0.17, scaled 1.0 × 0.85 × 0.9)
- **Waist joint** — connects chest to pelvis
- **Head** — blob puppet (GN Group node from blob_puppet.blend)
- **Hands** — UV Spheres (radius 0.1) at physics endpoint positions
- **Feet** — UV Spheres (radius 0.12) with 15° splay angle
- **Elbows/Knees** — joint spheres at analytical IK midpoints
- **Limbs** — split into upper/lower segments with joint sphere between
- **Neck** — tube connecting chest top to head bottom, follows chest sway
- **6 materials**: PP_Body, PP_Head, PP_Hand, PP_Foot, PP_Joint, PP_Limb

**3-axis torso sway (V0.4.0+):**
- **X (lateral):** lean × 1.0 (chest), × 0.7 (pelvis) + mouth lateral shift
- **Y (forward/back):** extend × 0.5 (chest), × 0.35 (pelvis) — tilt head forward, body follows
- **Z (vertical):** walking bob + dip + eyebrow/jaw lift
- Head follows chest sway on all 3 axes so no gap opens during movement

**Architecture decisions (V0.2.0+):**
- **Blob head as GN Group node**: `_load_blob_head_tree()` loads GN_BlobPuppet from blob_puppet.blend via `bpy.data.libraries.load()`. Independent copy (not linked).
- **Direct modifier push (no drivers)**: Blender 5.2 broke driver paths. OSC receiver writes values directly via `mod[sid] = value` + `puppet.update_tag()`.
- **CRITICAL: `update_tag()` required**: After writing any GN modifier values in Blender 5.2, must call `obj.update_tag()` or the modifier won't re-evaluate.
- **Analytical mid-joint IK**: `_compute_mid_joint()` — law of cosines for projection distance, then perpendicular offset via double cross product: `side = ab_dir × bend_axis`, `bend = ab_dir × side` (note: inputs swapped from standard `side × ab_dir` to get correct anatomical bend direction). Knees bend forward with `bend_axis=(0,1,0)`, elbows backward with `(0,-1,0)`.
- **Forward hinge bias on legs**: `LEG_HINGE_BIAS = -0.06` → hinge computes `max(dir_Y, 0.06)` forcing foot direction slightly forward. Prevents backward foot drag that plagued earlier versions.
- **Per-endpoint constraint system**: `_add_verlet_endpoint()` takes optional `hinge_axis`, `hinge_limit`, `inward_limit`, `midline_clamp`, `ground_z_out`, `ground_friction_out` parameters. All constraint types composable per-endpoint.

**Blender 5.2 Alpha physics research (April 9, 2026):**
- **Simulation zones** (stable since 3.6): Unchanged in 5.2. DIY Verlet physics proven.
- **Bone Info node** (new in 5.1): Reads armature bone transforms in GN. Useful for future versions.
- **XPBD solver** (PR #154435): Cosserat Rod support. **Still NOT merged.** Target: 5.3 (Nov 2026).
- **RNA property refactor (BREAKING CHANGE in 5.2)**: GN modifier properties use real RNA paths. **Will break Green Room's driver paths when Green Room moves to 5.2 stable.**

**Tracking input (TBD — two paths under research):**
- **Webcam pivot:** MediaPipe on local USB webcam → face mesh + hand tracking. No phone, no network.
- **Phone baseline:** Phone for face (existing pipeline) + separate hand tracking source.

**Key design principle:** Same "ancient methodology → modern tool" pattern as Green Room. Don't add more tracking inputs — design the puppet rig so that existing inputs trigger richer responses at different thresholds.

**Relationship to Green Room:** Completely separate project. Green Room stays stable at V0.7.0. PPParty is the experimental sandbox for full-body puppetry. ~80% code overlap in `osc_receiver.py` and `phone_connect.py` — future refactor could extract shared OSC module, but low priority since projects are intentionally independent.

**Known issues (V0.4.1):**
- **Grey materials**: Body parts render grey in Solid mode. Need Material Preview / EEVEE for colors.
- **Foot backward drag**: Forward hinge bias helps but feet can still drift backward during extreme lean. May need stronger bias or per-frame forward nudge.
- **`build_marionette_tree()` is 1071 lines**: Should be refactored into sub-functions (blob head, torso, limbs, output).

**Version history (this session, April 10, 2026):**
- V0.3.6 — Foot spread limits (inward_limit + midline_clamp on feet)
- V0.3.7 — Lean sensitivity boost (chest 0.7→1.0, pelvis 0.5→0.7), wider foot midline (0.02→0.08)
- V0.3.8 — Cross product swap to fix inverted knee/elbow bend direction
- V0.3.9 — Reverted bend_axis to original values (two negations were canceling; kept only cross product swap)
- V0.4.0 — 3-axis torso sway (added Y forward/back from headRotX), head follows on all axes
- V0.4.1 — Forward hinge bias on legs (`LEG_HINGE_BIAS = -0.06`), prevents backward foot drag

**Next steps:**
- **V0.5.0** — Contralateral knee lift from mouth (mouthLeft raises right knee, mouthRight raises left knee). New expression channel for deliberate stepping.
- **V0.6.0** — Arm gestures from face (smile lifts hands, frown drops them), head tilt → torso rotation
- **V0.7.0** — Torso momentum/lag (one-frame blend for heavy puppet feel), threshold-triggered stepping poses (Bunraku concept)
- **V0.8.0** — Minkowski capsule body parts, customization sliders
- **V1.0.0** — Recording + bake pipeline (keyframes, Alembic, video export)
- **Summer** — Webcam/hand tracking (MediaPipe), custom iOS face capture app

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

### Networking: Travel Router (Standard Deployment)
School and campus WiFi networks block device-to-device communication (client isolation). Instead of fighting IT at every site, Green Room deploys with its own travel router — a pocket-sized box that creates a private network between the phone and computer.

**Standard kit:** GL.iNet Slate AX (GL-AXT1800) — WiFi 6, 5GHz, USB-C powered, ~$120. Chosen for headroom to support multiple students performing simultaneously in the future.

**Setup:** Plug in router → connect computer and phone to its WiFi → done. No internet needed, no IT involvement, works in any room or outdoors with a battery pack.

**Gotchas:**
- macOS will warn "no internet" — dismiss it. In Wi-Fi settings, turn OFF "Limit IP Address Tracking" on the router's network.
- iPhone will also warn "no internet" — tap "Use Without Internet" or it silently switches back to cellular and the connection drops.
- Router's default WiFi name and password are printed on the bottom of the device.

## Code Style
- PEP 8
- Type hints where possible
- Every operator needs a docstring explaining what it does in plain English
- Blender class naming: `PAWRAPPA_OT_edge_score`, `PAWRAPPA_PT_uv_panel` (UV addon), `GREENROOM_OT_connect_phone` (puppet show addon), `PPPARTY_OT_*` (marionette addon)
- Prefix all custom properties with `gr_` (Green Room / puppet show), `pw_` (PaWrappa), or `pp_` (PPParty) to avoid namespace collisions

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
PENDING PPParty V0.4.1 — Forward hinge bias on legs, prevents backward foot drag
PENDING PPParty V0.4.0 — 3-axis torso sway, correct joint bending, foot constraints
PENDING PPParty V0.3.5 — Walking bob, mouth sway, jaw lift, ground friction
PENDING PPParty V0.3.3 — Visual/physics split, chest+pelvis, analytical two-bone IK
PENDING PPParty V0.2.0 — Face-tracked marionette (blob head + body movement from phone)
PENDING PPParty V0.1.1 — Simulation zone physics (replaces Python Verlet handler)
PENDING PPParty V0.1.0 — Dangling puppet (Verlet physics, GN visual tree, N-panel)
PENDING V0.7.0 — Nose, QR removal, latency optimization (UDP buffer, caching, UV strip)
b28aebe V0.6.0 — Reactive eyebrow rotation, mouth lateral shift, calibration UI fix
6c7d23d V0.5.1 — Fix sideways blink, mirror eyebrow rotation
2af933c V0.5.0 — Dynamic capsules on ALL body parts (eyes, ears, brows, irises, pupils)
7aa1056 V0.4.1 — Dynamic Minkowski capsule body, rotation slider, width min=0
9d3be18 V0.4.0 — Round cube primitives, shade smooth, subdivision surface
627aec6 V0.3.2 — Lip tube geometry (beveled curve around mouth opening)
9978eff V0.3.1 — Organized customize panels, independent eyebrow position controls
6a2dbe7 V0.3.0 — Eyebrows, mouth frown/shift, color controls, position sliders
96cd580 V0.2.0 — Template loader, puppet picker, customization sliders, latency fix
2de54b3 Add latency research notes — head tracking skips on fast movement
35170ce Update CLAUDE.md — Green Room V0.1.0 documented, priorities reordered
3a3796c V0.1.0 — Green Room addon + blob puppet template (geometry nodes)
2fffee1 V0.3.3 — Cleaner UI + a student's testing guide (PaWrappa)
f8757bf V0.3.2 — Student-ready UI + restored exact V0.3.0 algorithm (PaWrappa)
0fccc6b V0.3.1 — Face clusterer validated across 5 shape types (PaWrappa)
47a9490 V0.3.0 — PaWrappa rename + curvature-based face clustering
dc50fb6 Pivot to puppet show architecture — two-track design
9221dfc Add session notes for continuity between sessions
1476272 V0.2.0 — Stable baseline with three working shape modes
```
