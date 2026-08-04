# HIHO MOCAP — Wrapper Architecture

**Status:** Design doc, 2026-05-27, evolved 2026-05-28. Pre-code. The next code session should not start without this being read and either accepted or amended. **Section 11 (2026-05-28) is the current direction:** it evolves the FreeMoCap layer from "bundled inside Blender" to "separate backend" (Option B, which dissolves the Blender 5.0 pin), locks the shared-skeleton plus 45-degree A-pose standard, defines the golden-path loop, and records the BUILD verdict for the HIHO Mixamo auto-rig.

**Author context:** Written in response to an ajc27 baseline audit that revealed every parity check between our v1.1 port and ajc27's official addon passes. We have been re-implementing what already exists. This doc proposes we stop, bundle the upstream addon, and become the artist-facing layer on top of it.

---

## 0. The one-paragraph version

HIHO MOCAP today is a from-scratch port of [ajc27's freemocap_blender_addon](https://github.com/freemocap/freemocap_blender_addon). After auditing both side by side we found that ajc27 already gives us the load pipeline, the rig, the constraints, the bake-on-FBX-export, foot locking, retargeting basics, and multi-camera scene reconstruction. What it does NOT give us is an artist-facing user experience, a take library, stylized retargeting for chibi proportions, in-scene baking to a clean keyframed rig, sensible defaults for the known wrist-flip problem, or any classroom workflow. The proposal is to stop porting and become the thin artist-facing layer wrapped around the bundled ajc27 baseline. This kills the entire "did we port X correctly" debugging surface and concentrates our work on what only we can do: the pedagogy, the student UI, the local library, and the HIHO-specific character pipeline.

---

## 1. Why this reframe

### 1.1 What the audit found

Every parity check passes between v1.1 and the ajc27 reference:

- Constraint stacks on `hand.R / hand.L` are identical (`DAMPED_TRACK` → hand_middle, then `LOCKED_TRACK` → thumb_cmc).
- Bone rolls and rest-pose construction are identical.
- `fix_hand_data` is applied in both (hand wrist exactly equals body wrist at every sampled frame).
- `enforce_rigid_bodies` is applied in both (constant bone lengths frame-to-frame).
- Butterworth filtering at 7 Hz applies to the full 553-marker array, including hand landmarks, in both pipelines.

We have a clean 1:1 port. We also have all the same problems ajc27 has, because we ported them faithfully. The wrist flip we just spent a session diagnosing exists in ajc27 too. We are not behind the upstream; we are running in parallel to it.

### 1.2 The cost of running in parallel

Two cost lines:

1. **Every ajc27 bugfix is also a port we have to redo.** ajc27 ships at roughly v1.1.7 in spring 2026. As the upstream moves, we have to follow.
2. **Every artist-facing improvement we want to make competes for time with the parallel-port maintenance.** We are spending sessions confirming that our `enforce_rigid_bodies.py` matches their `enforce_rigid_bodies.py`, rather than building the take library that does not exist anywhere yet.

### 1.3 What the reframe buys

- The parallel-port maintenance line goes to zero. We call ajc27's operators by name.
- Our code surface shrinks from "the whole pipeline" to "the wrapper." A few hundred lines, not a few thousand.
- Every gap we identify becomes either a contribution upstream (to ajc27) or a HIHO-specific layer on top. We get to choose which.
- The Ed.D. dissertation framing becomes cleaner: HIHO MOCAP is the **applied pedagogy layer**, not a re-implementation of a research tool. That maps directly to the breakaway-frame dissertation memory.

---

## 2. The three-layer stack

```
┌────────────────────────────────────────────────────────────┐
│  LAYER 3:  HIHO MOCAP wrapper                              │
│            Studio Panel (5 buttons)                         │
│            Bake Take                                        │
│            Take Library                                     │
│            Parametric rig + stylized retarget               │
│            Confidence heatmap                               │
│            Sensible wrist defaults                          │
│            Curriculum metadata hooks                        │
│            AGPL-3.0                                         │
└────────────────────────────────────────────────────────────┘
                            ▲
                            │ extends + opinions
                            │
┌────────────────────────────────────────────────────────────┐
│  LAYER 2:  ajc27 freemocap_blender_addon (BUNDLED)         │
│            Load pipeline (empties + rig + constraints)      │
│            Visualization overlays                           │
│            FBX / GLB export with bake_anim                  │
│            Foot locking                                     │
│            Basic retargeting                                │
│            Multi-cam scene reconstruction                   │
│            AGPL-3.0                                         │
└────────────────────────────────────────────────────────────┘
                            ▲
                            │ depends on
                            │
┌────────────────────────────────────────────────────────────┐
│  LAYER 1:  FreeMoCap proper (BUNDLED-VENDORED)             │
│            Triangulation, calibration, butterworth filter   │
│            AGPL-3.0                                         │
└────────────────────────────────────────────────────────────┘
```

**Bundled vs vendored:** the layer 1 distinction is the existing one (bundled-vendored, never "fork"). Layer 2 is new. We bundle ajc27's addon directory inside HIHO MOCAP's distribution, so students install one zip and get all three layers wired up correctly. The license is AGPL-3.0 the whole way down, so this is legal and clean.

---

## 3. Audience and scope

### 3.1 Who this is for

- **Primary:** HIHO 4D ART CLUB students at SJSU and the CADRE student/alumni body, launching late June 2026. High-school-age and college-age, CS-curious but not CS-trained, here to make short films and animations.
- **Secondary:** the Summer 2026 SCRAP test class, which will be K-12 with a teaching artist.
- **Tertiary:** the broader FreeMoCap-University arts-leg conversation with Mathis post-July 2026.

### 3.2 Who this is NOT for

- **Not** biomechanics researchers. The ROM gauges, base-of-support, COM-vertical-projection, joint-angle text, and time-series plots stay available behind a Science Mode toggle, but they are NOT the default surface.
- **Not** professional VFX studios. We optimize for "kid making a 30-second short," not "studio making a feature."
- **Not** a real-time VJ tool. Captured-and-baked is the deliverable shape. Live performance is out of scope. (This is the existing PPParty-V3 deliverable principle carried forward.)

### 3.3 Local first

HIHO is Bay-Area-specific by design. The library lives on local file systems and the BASEMENT server. We are not building a global Mixamo competitor. We are building a peer-shared local library for the HIHO program. Other programs can fork the code if they want their own.

---

## 4. The Studio Panel (artist UI)

This is the surface a HIHO student sees. Five sections, top to bottom, in the order they get used.

### 4.1 Layout sketch

```
+----------------------------------+
|  HIHO MOCAP - STUDIO             |
+----------------------------------+
|                                  |
|  1. CHOOSE TAKE                  |
|     [pick from library...]       |
|     or [browse folder...]        |
|                                  |
|  2. PREVIEW                      |
|     [play]                       |
|                                  |
|  3. CHARACTER                    |
|     Character: [None v]          |
|     [Send to Character]          |
|                                  |
|  4. POLISH                       |
|     [Smooth hands]               |
|     [Fix wrist flips]            |
|     [Trim frames]                |
|                                  |
|  5. EXPORT                       |
|     ( ) FBX  ( ) GLB  ( ) .blend |
|     [Save out]                   |
|                                  |
|  --------------------------      |
|  v  Show Science Mode            |
+----------------------------------+
```

### 4.2 What each section does, in plain language

| Section | What the student sees | What actually happens |
|---|---|---|
| 1. Choose Take | A list of recordings with thumbnails, or a folder picker. | Sets the recording folder path. Loads the `annotated_videos` first frame as a preview thumbnail. Reads `recording_parameters.json` to confirm the take is processed. |
| 2. Preview | A "Play" button. Plays the timeline with the raw empties visible, no rig built yet. | Calls a lightweight loader: empties only, no armature, no constraints. Fast scrubbing, low scene cost. Lets the student decide if the take is worth committing to. |
| 3. Character | A dropdown of available characters in the scene. "Send to Character" button. | Calls `bpy.ops.freemocap.load_data()` to build the full rig, then runs our **Bake Take** step (see section 5.1), then applies the baked animation to the chosen character mesh via our **stylized retarget** (see section 5.2). |
| 4. Polish | Three buttons for the common post-bake fixes. | Each calls a specific utility: One Euro smoothing on hand landmarks, our LIMIT_ROTATION pass to clamp wrist flips, and frame-range trim. |
| 5. Export | Format radio buttons plus a Save Out button. | Calls Blender's standard FBX / GLB export with `bake_anim=True` for the FBX path, or saves the .blend with the baked rig. The output file name auto-derives from the take + character name. |

### 4.3 Terminology translation

The doc body uses laymen's terms first, technical terms second. The actual UI uses ONLY laymen's terms. A glossary at the bottom of the doc (section 9) cross-references them.

| Laymen term (UI uses this) | Technical term (code uses this) |
|---|---|
| Take | Recording session folder |
| Choose a take | Set `recording_folder` path |
| Preview | Spawn empties, no armature build |
| Character | A target armature in the scene |
| Send to Character | Build rig + bake constraints + retarget to target armature |
| Bake | Sample constraint output per frame, write keyframes, remove constraints |
| Polish | Post-bake animation cleanup |
| Smooth hands | One Euro filter on finger empties |
| Fix wrist flips | Apply LIMIT_ROTATION on `hand.R / hand.L` |
| Trim frames | Set scene frame range to a sub-window |
| Save out | Export FBX / GLB or save .blend |
| Science Mode | Show ajc27's biomechanics panels (ROM, BOS, COM, joint angles) |

### 4.4 What gets HIDDEN by default

The following ajc27 features are useful but live behind Science Mode:

- ROM gauges
- Base of support polygons
- Center-of-mass vertical projection
- Joint angle text overlays
- Time-series plots
- Motion paths
- Multi-camera reconstruction visualization
- Calibration TOML inspection

A teacher running a biomechanics lesson can flip Science Mode on for the day. The kid making a film never sees these.

---

## 5. The seven layers we add

For each: what it is, why it matters for HIHO, what it depends on, and where it lives.

### 5.1 Bake Take

**What:** a button that walks every pose bone, samples its constraint-resolved rotation per frame, writes clean keyframes, and removes the constraints. The result is a self-contained armature animation that does not depend on the empties anymore. Optionally also deletes the empties (or hides them, default).

**Why:** the ajc27 rig is constraint-driven. The moment a student tries to hand-tweak a frame, add a secondary animation, blend with another take, or drive a character mesh that is not ajc27's `skelly_mesh`, the constraint stack falls apart. FBX export bakes on the way out, but that means the student can only edit AFTER export, in another tool. We want them to edit in Blender.

**Depends on:** `bpy.ops.nla.bake()` with `bake_types={'POSE'}, visual_keying=True, clear_constraints=True`. Standard Blender. Our wrapper just calls it with the right options and timing.

**Lives in:** `hiho_mocap/operators/bake_take.py`. Small file, 100 lines ish.

### 5.2 Stylized retarget

**What:** a retargeter that knows about chibi / grown-chibi / normal / stylized proportions and adjusts joint angles to match the target rig's anatomy. Source is the baked HIHO rig. Target is a character rig with known proportions. The math accounts for: shorter limb lengths (chibi), bigger head pivot offset (chibi), wider shoulders (grown-chibi), and so on.

**Why:** the entire HIHO visual vocabulary leans on the ART 102 grown-chibi template. The kids are going to retarget their mocap onto chibi characters. ajc27's retarget is fuzzy-name-match plus `COPY_ROTATION`. It assumes proportions match. It breaks on chibi.

**Depends on:** a parametric rig definition with proportion sliders. This is sibling work to the **parametric rig system** described in the existing `project_ppparty_parametric_rig_system` memory. The rig and the retargeter co-design.

**Lives in:** `hiho_mocap/retarget/` directory with the rig definitions and the retargeter logic. This is the biggest piece of new code in v2.0. It probably also wants a Green Room dependency, since Green Room is the procedural character system.

**Open question:** does Green Room ship the parametric rig, and HIHO MOCAP just consumes it? Probably yes. Resolve before v2.0 starts.

### 5.3 Take library and metadata

**What:** a JSON-indexed library of takes with thumbnails, performer attribution, tags, license, calibration source, and quality scoring. Library root is local. Default location: `~/HIHO_MOCAP_LIBRARY/`. Two takes in the library can be browsed in a grid view, loaded side by side in the same scene with offset root empties, and compared.

**Why:** the HIHO program vision includes a peer-built local mocap library, "Mixamo-better." This is the entry point. Without a library system, every student starts from a folder picker, which is the admin work David hates.

**Depends on:** nothing exotic. A `library.json` schema, a thumbnail extraction step (read first frame of `annotated_videos/Camera_0_mediapipe.mp4`), a small Blender UI panel for the grid view.

**Lives in:** `hiho_mocap/library/` directory. Separate from the operators.

**Curriculum hook:** each take's metadata includes a `license` field. Defaults to "HIHO internal." Students can mark a take as CC0 or CC-BY for the broader library. This is the entire training-data-policy memory in one field.

### 5.4 Confidence heatmap

**What:** a viewport overlay that colors each landmark empty by its FreeMoCap reprojection error. Green = trusted, yellow = noisy, red = unreliable. Reads from `output_data/raw_data/mediapipe_3dData_numFrames_numTrackedPoints_reprojectionError.npy`.

**Why:** BASEMENT calibration is good but imperfect. The wrist flip we keep seeing is almost certainly driven by occasional high reprojection error on `right_hand_thumb_cmc`. Right now the artist has no idea which landmarks are unreliable until they hit play and see the snap. The heatmap lets them spot trouble frames before committing.

**Depends on:** reading the reprojection-error npy, writing a custom viewport shader or coloring the empties' display color per frame. Blender's GPU module supports this.

**Lives in:** `hiho_mocap/overlays/confidence_heatmap.py`. Modest size.

### 5.5 Sensible wrist defaults (LIMIT_ROTATION)

**What:** during the bake step, apply `LIMIT_ROTATION` constraints to `hand.R` and `hand.L` that clamp the wrist to anatomically plausible angles (roughly +/- 70 degrees pitch, +/- 30 degrees roll, +/- 90 degrees yaw, all in bone local space). Configurable per-take, with an "off" toggle for the rare case where the artist wants a contortion.

**Why:** the wrist flip we diagnosed is a known `LOCKED_TRACK` pathology, triggered when the thumb crosses the bone's local Z plane. ajc27 ships without rotation limits. We turn them on by default. The flip stops looking like a hardware glitch and starts looking like a rig.

**Depends on:** Blender's `LIMIT_ROTATION` constraint. No new tech.

**Lives in:** part of the **Bake Take** step (5.1). Not a separate operator.

### 5.6 Curriculum metadata hooks

**What:** a per-take metadata block that captures: class section, semester, assignment name, performer consent status, and license. Defaults to the current student's profile. Written to the take folder as `hiho_metadata.json`.

**Why:** the library's value compounds when takes are well-tagged. The metadata also doubles as the consent record (per the training-data-policy memory: opt-in, never leaves HIHO servers).

**Depends on:** student profile (a simple per-machine config file at `~/.hiho_mocap_profile.json`).

**Lives in:** `hiho_mocap/library/metadata.py`. Minimal.

### 5.7 2026-era forward compatibility maintenance

**What:** a commitment, not a feature. HIHO MOCAP gets tested against Blender 5.0 (the FreeMoCap pin) AND Blender 5.x current. We patch ajc27 incompatibilities in our vendored copy when needed and upstream the patches.

**Why:** ajc27 declares Python 3.10-3.12 but runs fine on Blender 5.2's 3.13 with a single harmless syntax warning. We have already shown we can carry these patches. We just commit to it.

**Lives in:** `hiho_mocap/vendor_patches/` directory holding small diff files. Each patch is dated and explained.

---

## 6. Migration from v1.1 to wrapper

### 6.1 Files we DELETE (move to ARCHIVE)

Everything we ported from ajc27. ajc27 owns these now.

- `core/loader.py` (most of it; we keep a thin shim that calls ajc27's load_data)
- `core/enforce_rigid_bodies.py`
- `core/topology.py`
- `core/build_rig.py`
- `core/bind_to_rig.py`
- `core/output_rig.py`
- `core/virtual_landmarks.py`

Per the never-delete rule, these move to `SOFTWARE/HIHO_MOCAP/_LEGACY_v1.1_port/` rather than getting `rm -rf`'d. David reviews and decides if any go to `_REVIEW_FOR_DELETION/`.

### 6.2 Files we KEEP

- `operators/spawn_rig.py` becomes a thin wrapper that calls ajc27's `bpy.ops.freemocap.load_data()` and adds our HIHO-specific post-processing.
- `core/freemocap_runner.py` — the BASEMENT custom-recorder bypass logic. ajc27 does not own this.
- `core/camera_manager.py` — multi-cam helpers we built that ajc27 does not have.
- `HAND_BONES_DESIGN.md` — research doc, stays as reference.
- All MEMORY pointers.

### 6.3 Files we ADD

New `hiho_mocap/` directory tree:

```
hiho_mocap/
  __init__.py
  panel/
    studio_panel.py        # the 5-section UI
    science_mode.py        # toggle that re-exposes ajc27 panels
  operators/
    bake_take.py
    polish_smooth_hands.py
    polish_fix_wrist_flips.py
    polish_trim_frames.py
    save_out.py
  library/
    library_root.py
    library_index.py
    take_card.py
    metadata.py
  retarget/                # v2.0
    parametric_rig.py
    stylized_retarget.py
  overlays/                # v2.0
    confidence_heatmap.py
  vendor/
    ajc27_freemocap_blender_addon/   # bundled copy
  vendor_patches/
    README.md
    <patches as needed>
```

### 6.4 The bundle decision

**Recommendation: bundle ajc27 inside HIHO MOCAP's zip.**

Tradeoffs:

- *Pro bundling:* one install for the student. We control the ajc27 version we depend on. We can pre-apply our compatibility patches. Easier classroom deployment.
- *Pro separate:* lighter touch on upstream. No risk of ours-vs-upstream version drift in a student's setup. Easier to upstream contributions.

For HIHO MOCAP's audience (student artists who hate admin work), bundling wins. The vendored copy lives at `hiho_mocap/vendor/ajc27_freemocap_blender_addon/`. We register both addons from our `__init__.py`. ajc27 stays modifiable but we treat it as read-only by convention.

Re-confirm at v1.2 ship.

---

## 7. Versioning

### 7.1 v1.2 (next ship, summer 2026)

The architectural pivot itself. Must-haves:

- Vendor ajc27 inside our distribution. Register both addons from our `__init__.py`.
- The Studio Panel (5 sections). Hidden Science Mode toggle.
- Bake Take operator with the LIMIT_ROTATION defaults baked in.
- Polish operators: smooth hands (One Euro), fix wrist flips (already in bake), trim frames.
- Updated v1 plan doc to reflect the wrapper architecture.
- Test installation on a fresh Blender 5.0 user account end to end.

NOT in v1.2:

- The take library. (Comes in v2.0.)
- Stylized retargeting. (v2.0.)
- Confidence heatmap. (v2.0.)
- Parametric rig. (v2.0, may be Green Room.)

### 7.2 v2.0 (Fall 2026 / Spring 2027)

The library + curriculum integration features. Lock the v1.2 surface for the summer test class, then build v2.0 against feedback from that class.

- Take library with metadata, thumbnails, grid browser.
- Curriculum metadata hooks.
- Stylized retargeting + parametric rig (jointly with Green Room).
- Confidence heatmap overlay.

### 7.3 v3.0 and beyond

Out of scope for this doc. The HIHO MOCAP v2 home-rolled server (memory: `project_hiho_mocap_v2_homerolled_ideal`) is a separate trajectory that depends on the CS-student labor pipeline.

---

## 8. Decisions (locked 2026-05-28)

The three v1.2 blockers are locked. The four v2.0 questions are explicitly deferred to the v2.0 design pass. v1.2 code can begin.

1. **UI button labels — LOCKED, proposed slate.** Five labels: "Choose Take / Preview / Send to Character / Polish / Save Out." Studio Panel code uses these verbatim. Section labels match (CHOOSE TAKE / PREVIEW / CHARACTER / POLISH / EXPORT).
2. **Bake Take behavior on the empties — LOCKED, hide in collection.** After bake, empties are moved into a new collection named `HIHO_MOCAP_Raw`. The collection is hidden by default; user can toggle visibility from the outliner. Never deleted, per the never-delete rule.
3. **Bundled ajc27 vs separate — LOCKED, bundle.** ajc27 vendored at `hiho_mocap/vendor/ajc27_freemocap_blender_addon/`. Both addons register from our `__init__.py`. Compatibility patches live under `hiho_mocap/vendor_patches/`, each dated and explained.
4. **Where the parametric rig lives — DEFERRED to v2.0 design.** Out of v1.2 scope. Revisit with Green Room context during the v2.0 design pass. Current working assumption (Green Room owns the rig, HIHO MOCAP imports it) is unconfirmed.
5. **Library root path default — DEFERRED to v2.0 design.** Library is v2.0. Revisit then.
6. **Confidence heatmap thresholds — DEFERRED to v2.0 design.** Overlay is v2.0. Revisit then with real BASEMENT reprojection-error data in hand.
7. **Wrist rotation limits, specific angles — SHIP WITH STAND-INS.** v1.2 ships +/- 70 pitch, +/- 30 roll, +/- 90 yaw in `hand.R / hand.L` local space. Numbers live in `hiho_mocap/operators/bake_take.py` as named constants for easy adjustment after the first artist test.

---

## 9. Glossary

For the doc body, used both ways. For the UI, only the left column ever appears.

| Laymen | Technical | What it means in one sentence |
|---|---|---|
| Take | Recording session | A single multi-cam mocap shoot, stored as a folder of npys, videos, and metadata. |
| Choose Take | Set recording_folder | Tell HIHO MOCAP which take to load. |
| Preview | Spawn empties only | Load just the tracker dots without building a skeleton, for fast scrubbing. |
| Character | Target armature | The character rig you want the motion to drive. |
| Send to Character | Build, bake, retarget | Build the skeleton, lock in the animation as keyframes, transfer it to the character. |
| Bake | Bake constraints to keyframes | Sample the constraint output per frame, write clean keyframes, drop the constraints. |
| Constraint | Blender constraint | A live Blender rule that makes one object follow another. Brittle for export. |
| Keyframe | Keyframe | A saved value at a specific frame. Survives export, survives editing, durable. |
| Polish | Post-bake cleanup | Smoothing, wrist fixes, frame trimming, after the bake. |
| Smooth hands | One Euro filter | A specific smoothing math that removes hand jitter without lagging fast motions. |
| One Euro filter | One Euro filter | A noise filter that adapts to motion speed. (Named after the price of the prototype, not the currency.) |
| Fix wrist flips | LIMIT_ROTATION | A Blender constraint that caps how far a bone can rotate. Stops the hand from snapping 180 degrees. |
| Trim frames | Scene frame range | Cut the timeline to start and end at the frames you actually want. |
| Save out / Export | FBX / GLB / .blend export | Write a file in a format another program can read. |
| FBX | FBX | An animation file format most game engines and 3D programs accept. |
| GLB | glTF binary | A newer, lighter animation file format. Good for web and game engines. |
| .blend | Blender file | Native Blender file. Edit it later in Blender. |
| Library | Take library | A local folder of takes you can browse, tag, and share with other HIHO students. |
| Tag | Metadata field | A label on a take, like "running" or "wave," to find it later. |
| License | License field | What others can do with this take. Default HIHO internal, can opt in to CC0 or CC-BY. |
| Confidence heatmap | Reprojection error overlay | Colors on the tracker dots showing which ones the cameras trusted. Red = don't trust. |
| Stylized retarget | Proportion-aware retarget | A way to put a normal-bodied person's mocap on a chibi character without breaking the elbows. |
| Chibi / grown-chibi | Stylized proportions | The HIHO character family: big heads, short or long limbs depending on style. |
| Parametric rig | Slider-driven rig | A skeleton with sliders that let you change proportions on the fly. |
| Science Mode | ajc27 biomechanics panels | The original ROM, BOS, COM, joint-angle UI, hidden by default. |
| ROM | Range of Motion | How far a joint can rotate. Biomechanics term. |
| BOS | Base of Support | The polygon under your feet showing how stable your stance is. Biomechanics term. |
| COM | Center of Mass | The point where your body's mass balances. Biomechanics term. |

---

## 10. What to do with this doc

1. Read it slowly.
2. Mark anything that should be different.
3. Lock the open questions in section 8.
4. Then, and only then, start the v1.2 code.

Per the no-code-before-design rule. The next session reads this doc, accepts or amends, and then either writes the Studio Panel skeleton or pauses for another design pass.

**Status (2026-05-28):** Section 8 locked. The next code task is the Studio Panel skeleton in `hiho_mocap/panel/studio_panel.py`, registered alongside the bundled ajc27 addon from `hiho_mocap/__init__.py`.

---

## 11. Option B and the HIHO Mixamo (design session 2026-05-28)

**This section is the current direction.** It evolves section 2 (the three-layer stack) and section 6 (bundling). The wrapper philosophy is unchanged (recompose existing AGPL tools into HIHO's pedagogy), but it is pushed one level deeper. All decisions below were locked with David on 2026-05-28.

### 11.1 HIHO MOCAP is a workflow, not a tool

The product is the UX, the workflow, and the pedagogy. The mocap math (FreeMoCap) and the rig building (ajc27) are solved and maintained by others. HIHO's value is "a student makes a mocap short in one class period without a terminal." We recompose existing AGPL tools toward that, and own only the artist layer.

### 11.2 Option B: Blender is the only surface, FreeMoCap is a backend

The three-layer stack from section 2 evolves. FreeMoCap proper, AND the camera recording, move OUT of Blender into a separate backend process that keeps its own frozen Python. Blender hosts only the thin HIHO UI plus the bundled ajc27 rig-building, which is pure `bpy`.

Consequences:
- **The Blender 5.0 pin dissolves.** The only thing that ever forced Blender 5.0 was FreeMoCap's processing libraries needing old Python. With those in the backend, nothing left inside Blender needs 5.0. We already proved ajc27 runs on Blender 5.2. Once Option B is built, HIHO MOCAP rides whatever Blender is current. (Until then, the current monolith still needs 5.0. See [[hiho-mocap-blender-50-pin]].)
- **Two version numbers, not one.** Blender out front floats to current. The FreeMoCap backend freezes on a known-good set per semester. All version-sensitive code lives in the backend, so that is the thing we pin; Blender is free to move.
- **Recording lives in the backend** (decision; David deferred to recommendation). Cameras run on OpenCV, which is version-sensitive, so it belongs with the rest of the sensitive stuff. Previews stream to Blender so the student never leaves Blender; whether that is a live in-Blender view or a backend window during recording is an implementation sub-detail. The v1.0 in-Blender Camera Manager is kept as the fallback and first cut until the backend recorder is proven.
- **Why now, not v3.0:** the upstream (FreeMoCap v2) is itself becoming a separate installable backend plus server, so Option B swims with the current. The full home-rolled custom server (the old "v2.0 / v3.0 home-rolled" idea) is the fancy version of this; the plain version is available now with no CS-student labor. The May 2026 smoke test already proved FreeMoCap's processing runs headless with its GUI absent.

### 11.3 The one shared skeleton standard (LOCKED)

The skelly (the ajc27 / FreeMoCap skeleton) is the single shared skeleton. The standard is its bone topology PLUS a **45-degree A-pose rest** (ajc27's `freemocap_apose`, adopted 2026-05-28 as the starting point, tunable but to be frozen before the library fills). Every take baked into the library and every character rigged speaks exactly this. Result: zero retargeting between any clip and any character.

A-pose mechanism (confirmed in the ajc27 source 2026-05-28):
- ajc27 already ships `freemocap_apose` (arms dropped 45 degrees from the T-pose) as a first-class build option alongside `freemocap_tpose`. The rig builder takes a pose parameter (`add_rig_bone_method`, default `FREEMOCAP_TPOSE`).
- Crucially, the tracking constraints store their track and lock axes **per pose** (`data_models/bones/bone_constraints.py`), so building in A-pose automatically uses the A-pose constraint behavior. The wrist-flip risk is already handled upstream for A-pose. This was the only real danger and it is solved.
- Switching is threading `FREEMOCAP_APOSE` through ajc27's build call (a small change; ajc27 does not expose this choice in its own UI, default is T-pose). "An A-pose of our design" = copy `freemocap_apose`, change the droop angle, test; the existing A-pose constraint axes carry over for a normal A-pose range.
- **Time-sensitivity:** the rest pose is part of the standard. Baked library clips are tied to the rest pose they were made against. Change it later and every existing clip needs re-baking. So the A-pose is locked NOW, before the library grows.

### 11.4 The golden-path loop

```
CAPTURE (HIHO MOCAP)                         STUDIO (HIHO MOCAP)
  cameras up                                   place markers on an A-pose character
  record                                       auto-rig the character to the skelly
  cameras down                                 character plays the whole library,
  process (in the backend)                       including every future take
    -> skelly in the scene
    -> clip saved to the local library
            |                                            ^
            +--------- the library is the hinge ---------+
```

Each capture publishes a clip to the local library. The Studio reads the whole library. So "future takes" is not a feature, it is what happens for free once the loop exists. Capture grows the shelf; every rigged character gets the new clips automatically. The library is delivered through Blender's native Asset Browser (drag-and-drop animations, free, built in).

### 11.5 The HIHO Mixamo (auto-rig), research-grounded

Full research artifact: [AUTORIG_RESEARCH_2026-05-28.md](AUTORIG_RESEARCH_2026-05-28.md). Bottom line: **BUILD, do not adopt**, but it is a tractable build.

- **The architecture is proven.** What David designed (one fixed skeleton, fit to each character, shared clip library, zero retargeting) is exactly the Pinocchio method (Baran & Popović, SIGGRAPH 2007), explicitly built as "an animation system for novices and children." Mixamo descends from this lineage. "Mixamo-level" is a known ~2007 algorithm, not bleeding edge.
- **Our marker placement removes the hardest step.** Pinocchio's most failure-prone part is auto-guessing joint locations. Having the student place the markers hands the algorithm that answer, de-risking the rig half.
- **The two halves:** (1) fit the skelly to the markers (tractable geometry; reuse Rigify for bone-construction plumbing only; Rigify does not skin). (2) skin the mesh (the hard part). Blender's built-in bone-heat is the free floor and is the same Pinocchio family; it may already suffice on clean student meshes.
- **Robust skinning on messy meshes is the frontier.** The robust methods (Geodesic Voxel Binding; the 2024 Robust Biharmonic Geometric Fields) have no usable open code and would need clean-room reimplementation. Defer; lean on bone-heat plus a keep-your-mesh-clean guideline for the first version.
- **Ruled out:** RigNet / brignet (own skeleton, brignet declared dead, heavy deps), GameRig (GPL-2-only, license-incompatible with AGPL-3.0), Rigify alone (no skinning).
- **Cheap first experiment (do before building):** test how good Blender bone-heat alone is on a clean chibi mesh. If good enough, the HIHO Mixamo shrinks to "fit skelly to markers, then call bone-heat," a club-buildable scope.

### 11.6 Setup and upkeep

- **Setup (club / SJSU student):** three one-time steps. Current Blender; the FreeMoCap backend via an in-addon "Install FreeMoCap" button that fetches and places it; the thin HIHO addon zip. Plus a "Check Setup" button that verifies Blender, cameras, and the backend and says in plain words what is missing.
- **Upkeep:** a written known-good set for the backend (already found: Python 3.11, numpy 1.26.4, mediapipe 0.10.14); one thin adapter seam so all calls into FreeMoCap / ajc27 funnel through a single module; a five-minute smoke test re-run on every update; freeze the backend per semester; the club owns the re-baselining as curriculum.

### 11.7 What this means for the version plan

- **v1.2 (in flight):** wrapper + Studio Panel + Bake Take. Still valid as the near-term.
- **Option B + the A-pose standard:** fold into the v2.0 design. Dissolves the 5.0 pin.
- **The HIHO Mixamo (auto-rig):** the heart of v2.0. Build Pinocchio-style. A natural club research project.
- Exact version renumbering is TBD. The home-rolled custom server moves from "the only escape" to "a later optimization of Option B."

### 11.8 Open questions for the next sessions

1. How good is Blender bone-heat alone on clean chibi meshes? (Test first; may make the robust-solver work optional.)
2. Is there an AGPL-compatible voxel-geodesic skinning implementation to vendor, or must it be clean-room reimplemented? **David's lead (2026-05-28): Voxel Heat Diffuse Skinning (meshonline) handles multi-piece characters and may be exactly this. Chase it first next session; verify license, fixed-skeleton support, maintenance. See AUTORIG_RESEARCH_2026-05-28.md.**
3. Did the 2024 Robust Biharmonic (Geometric Fields) team release code, and under what license?
4. Newer learned skinners (UniRig, RigAnything, ASMR, ARMO): fixed-skeleton mode + AGPL license? Not yet evaluated.
5. Recording preview UX: live in-Blender stream vs a backend window during the record step.

---

**Status (2026-05-28, evening):** Option B, the shared-skeleton + 45-degree A-pose standard, the golden-path loop, the setup and upkeep plan, and the BUILD verdict for the HIHO Mixamo are all captured here. Auto-rig research preserved in AUTORIG_RESEARCH_2026-05-28.md. These are design decisions, not yet code. Next code is still the v1.2 Studio Panel and Bake Take (section 8). Option B and the HIHO Mixamo are v2.0 design, to be sequenced after v1.2.
