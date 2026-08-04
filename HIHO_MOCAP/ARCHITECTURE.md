# PPParty (multi-cam) — Architecture

**Status:** First draft, 2026-05-06. Written after deep-read of FreeMoCap, Skellycam, ajc27 freemocap_blender_addon, and SnowMocap. Supersedes the high-level shape in [`../R&D/MULTICAM_MOCAP_DESIGN.md`](../R&D/MULTICAM_MOCAP_DESIGN.md) (which remains valid as the original ELI5 + hardware doc).

This doc captures *what we're building, what we're not building, and why* — so BASEMENT day on 5/9-10 has clear ground beneath it.

---

## 0. The one-paragraph version

PPParty (multi-cam) is a Blender-side coordinator for a 4-camera markerless mocap pipeline that already exists in open-source form. **Skellycam** captures synchronized video from N webcams. **FreeMoCap** processes those videos (MediaPipe per camera → Anipose triangulation → 3D landmarks → post-process). **ajc27_freemocap_blender_addon** loads the resulting `.npy` data into Blender as an armature with empties. **Our job** is the layer on top: a student-friendly UX (one-button capture, step-by-step calibration walkthrough, "apply to puppet character" retargeting), plus the pedagogical glue specific to HIHO Club / CADRE workflows. We write less code than V2; we wire more.

---

## 1. The stack — four packages, named roles

| Package | What it does | License | Path |
|---|---|---|---|
| **Skellycam** | Multi-cam capture + frame-perfect sync. FastAPI server on `localhost:53117`. Captures synchronized video files + timestamps. | AGPLv3+ | `R&D/skellycam/` |
| **FreeMoCap** | Pipeline orchestrator: invokes MediaPipe per cam → Anipose triangulation → post-process → `.npy` output. Includes `process_recording_headless()` for invocation without GUI. Depends on Skellycam (pip pulls it in). | AGPLv3 | `R&D/freemocap-main/` |
| **ajc27 freemocap_blender_addon** | Blender addon that loads FMC's `.npy` output, creates rig + empties, optionally exports videos / 3D models. Entry point: `ajc27_run_as_main_function(recording_path, blend_file_path, config)`. | AGPLv3 | `R&D/freemocap_blender_addon/ajc27_freemocap_blender_addon/` |
| **PPParty (this project)** | Student-facing Blender addon. Orchestrates the three above; adds calibration walkthrough, "apply to puppet character" retargeting, NLA management, classroom UX. | AGPLv3 (per `project_software_philosophy_free_open`) | `SOFTWARE/PPPARTY/` |

**Reference-only (not on the runtime path):**
- `R&D/snowmocap/` — RTMPose + UKF reference. Requires Nvidia CUDA → not deployable on macOS. Worth studying for math (UKF filter, Blender armature mapping); cannot run in our pipeline.
- `SOFTWARE/PPPARTY_V2/` — single-cam record-and-bake addon, parked at v2.0.4. Pattern donor only.

---

## 2. The runtime workflow (BASEMENT-ready as standalone tools day-1)

### Phase 0 — Standalone (Skellycam + FreeMoCap, no PPParty addon yet)

This is what David runs on BASEMENT day 1. **No new code from us required.** Goal: prove the pipeline works end-to-end on David's MacBook Pro, with 4 webcams.

```
1. Install:    pip install freemocap     (this also pulls in Skellycam)
2. Calibrate:  Launch FreeMoCap GUI → New Session → Calibrate (ChArUco board flow)
3. Record:     Launch FreeMoCap GUI → Record → perform → stop
               (FreeMoCap drives Skellycam under the hood for capture)
4. Process:    FreeMoCap auto-processes after stop (MediaPipe → triangulate → post-process)
               Output: a recording folder with synchronized videos + .npy 3D landmarks + .blend file
5. Verify:     Open the .blend file. Should see an armature + empties driven by mocap data.
```

If steps 1-5 work cleanly on macOS with 4 cameras, we have a ground truth and can start building the PPParty layer on top. **If any step fails, we debug standalone before adding our complexity.**

### Phase 1 — PPParty addon as orchestrator (our work)

Once standalone is proven, we wrap the same pipeline behind a Blender addon UI:

```
[Student opens Blender, PPParty panel]
   |
   ├─ Click "Setup Cameras" (if not already)
   |    → addon launches Skellycam server as subprocess
   |    → step-by-step calibration walkthrough (ChArUco board)
   |    → calibration TOML saved to known location
   |
   ├─ Click "Record"
   |    → addon hits Skellycam HTTP /record/start
   |    → student performs
   |    → Click "Stop"
   |    → addon hits /record/stop, gets back recording folder path
   |
   ├─ Click "Process"
   |    → addon invokes freemocap.process_recording_headless(recording_path, calibration_toml)
   |    → progress bar in Blender
   |    → output: .npy + (already-existing) ajc27 addon import into the active scene
   |
   └─ Click "Apply to Character"
        → student picks a puppet template (PPParty character library)
        → retarget mocap skeleton → puppet rig
        → keyframes baked, NLA-pushed to a track (V2 pattern)
        → ready to render / edit / continue
```

The addon never reimplements Skellycam (we use its HTTP API), never reimplements MediaPipe/triangulation (we call FMC's headless processor), never reimplements .npy→armature loading (we invoke ajc27's MainController). We add the orchestration glue + the student UX layer + the puppet character system.

---

## 3. Calibration — the one-time setup that gates everything

Calibration is the most error-prone step and also the only one that has no alternative pathway. Without a calibration TOML, FreeMoCap refuses to triangulate multi-cam recordings (`process_recording_headless` raises `ValueError` if multi-cam without TOML).

**FreeMoCap's calibration is invokable headless** via `AniposeCameraCalibrator(charuco_board_object, charuco_square_size, calibration_videos_folder_path, progress_callback)`. So our addon can drive it from within Blender — but for BASEMENT day 1, we skip our wrapper and just use FreeMoCap's GUI. Get the TOML, store it, reuse for every recording until cameras get bumped.

**Calibration UX in PPParty (Phase 2 work):** a step-by-step walkthrough panel that:
1. Shows the student a printed/bought ChArUco board image to verify
2. Tells them "wave the board slowly in front of every camera, make sure each camera sees it from multiple angles"
3. Records via Skellycam for 30-60 seconds
4. Invokes the AniposeCameraCalibrator class on the recorded videos
5. Saves the resulting TOML to a known location
6. Reports back "ready" or "failed — try again"

This is the largest piece of net-new design work in the project.

---

## 4. What we cherry-pick from V2 (small, named list)

V2 is parked, but four patterns earned their keep and transfer:

1. **Rigify-matched hand bone hierarchy** (`SOFTWARE/PPPARTY_V2/core/rig.py`). 4 palm metacarpals + 15 phalanges per side, anatomically-proportioned. Per memory `feedback_use_rigify_as_bone_reference`. Drop-in replaceable for whatever rig ajc27 produces, since we want puppet rigs, not generic skeleton rigs.
2. **Blender 5.2 Slotted Actions fcurve enumeration** (`core/recorder.py`). `action.layers[*].strips[*].channelbags[*].fcurves`. We will need this anywhere we touch keyframes. Per memory `feedback_blender_52_slotted_actions`.
3. **NLA-push-on-Stop pattern** (`BodyRecorder.stop_recording`). Auto-push captured Action to a new NLA track. Per memory `project_v2_nla_push_recording`.
4. **Operator + N-panel scaffolding shape** (`SOFTWARE/PPPARTY_V2/operators/`, `ui/panels.py`). Class naming, registration boilerplate, panel hierarchy. Don't redesign from scratch.

**Note on porting:** these are *patterns*, not files. We rewrite each fresh in `SOFTWARE/PPPARTY/` because the surrounding context is different. Don't `cp` from V2.

---

## 5. What we deliberately don't port from V2

These existed in V2 because of single-cam MediaPipe constraints. Multi-cam triangulation makes them obsolete:

- **Hand calibration estimators** (per-class median + 90th percentile in `core/recorder.py`). Was a workaround for MP's `hand_world_landmarks` being projected/foreshortened lengths. Multi-cam triangulation gives true 3D positions; the foreshortening problem disappears.
- **Lever A side_ref math** (across-palm vector for hand bones). Was a workaround for `to_track_quat('Y','Z')` degenerate fallback on near-vertical bones. True 3D positions probably don't hit the same failure modes — but we should re-measure before assuming.
- **`mediapipe_sender.py` entirely**. Skellycam replaces it. MediaPipe still runs — but inside FreeMoCap's pipeline, per camera, on saved video files, not as our own subprocess.
- **One Euro filter implementation**. FreeMoCap's post-process (`skellyforge`) handles smoothing. Different math, established pipeline.
- **Constant-stance / floor constraint**. Pedagogy decisions for live puppet show; not load-bearing for film-production multi-cam.
- **Lever B inert escape valve** (we kept it parked in V2). Doesn't transfer; FMC's smoothing pipeline replaces all of this.

---

## 6. Codebase layout in `SOFTWARE/PPPARTY/`

Proposal — verify with David before cementing:

```
SOFTWARE/PPPARTY/
├── README.md                       # ← already exists; project landing page
├── ARCHITECTURE.md                 # ← this doc
├── HANDOFF.md                      # ← created on first build (per V2 pattern)
├── BENCHMARKS.md                   # ← created on first benchmark ship
├── __init__.py                     # bl_info for the addon
├── core/
│   ├── __init__.py
│   ├── skellycam_client.py         # HTTP client wrapping Skellycam REST + WebSocket
│   ├── freemocap_runner.py         # Wrapper around freemocap.process_recording_headless
│   ├── ajc_addon_bridge.py         # Wrapper invoking ajc27's MainController
│   ├── calibration.py              # AniposeCameraCalibrator wrapper + UX state machine
│   ├── retarget.py                 # Mocap skeleton → PPParty puppet rig retargeting
│   └── nla_push.py                 # NLA-push pattern from V2 (rewritten clean)
├── operators/
│   ├── __init__.py
│   ├── setup_cameras.py            # First-run camera detection + calibration walkthrough
│   ├── record.py                   # Start/Stop recording (talks to Skellycam)
│   ├── process.py                  # Invoke FreeMoCap headless on the recording
│   ├── apply_to_character.py       # Retarget + NLA-push to puppet rig
│   └── pick_character.py           # Browse puppet template library
├── ui/
│   ├── __init__.py
│   └── panels.py                   # N-panel "PPParty" with phased UX
├── puppets/
│   ├── __init__.py
│   ├── puppet_spec.py              # Puppet template validator (port from V1 idea)
│   └── templates/                  # Bundled .blend puppet templates
└── tests/
    └── ...
```

**The folder layout matters less than the module boundaries.** The non-negotiables:

- **Skellycam talks happen in ONE module** (`core/skellycam_client.py`). If their HTTP API changes, we change one place.
- **FreeMoCap calls happen in ONE module** (`core/freemocap_runner.py`). Same reason.
- **ajc27 invocations happen in ONE module** (`core/ajc_addon_bridge.py`). Same reason.
- **Operators are thin** — just call into core modules. No business logic in operators.

---

## 7. Phased build plan (refined from `MULTICAM_MOCAP_DESIGN.md`)

Original plan put Blender bridge at "Fall 2026" and one-button-from-Blender at "Spring 2027." Today's reframe pulls those forward — short film + Range Eval need it operational this summer. Revised:

### Phase 0 — BASEMENT standalone (5/9-10 weekend + week after)
- Install FreeMoCap + Skellycam on David's MacBook Pro (`pip install freemocap` covers both)
- Stand up 4-cam rig at BASEMENT
- Calibrate via FreeMoCap GUI
- Record + process a test capture standalone
- Verify .blend file output via ajc27 addon
- **Success criteria:** end-to-end capture → 3D armature in Blender, no PPParty code yet
- Dissertation note: document everything for the install guide

### Phase 1 — PPParty orchestrator MVP (mid-May → mid-June)
- Bootstrap `SOFTWARE/PPPARTY/` per layout above
- `core/skellycam_client.py` — HTTP wrapper, basic record start/stop
- `core/freemocap_runner.py` — wrap `process_recording_headless`
- `core/ajc_addon_bridge.py` — invoke `ajc27_run_as_main_function`
- N-panel with three buttons: Record / Process / Open Result
- **Success criteria:** student opens Blender → clicks 3 buttons → has a baked armature in their scene

### Phase 2 — Calibration UX in-Blender (mid-June → early July)
- `core/calibration.py` — wrap `AniposeCameraCalibrator`
- Calibration walkthrough operator in the panel
- TOML saved to known location, auto-loaded for subsequent recordings
- **Success criteria:** student calibrates from inside Blender, no external GUI needed

### Phase 3 — Apply to Character (early July → mid-July)
- `core/retarget.py` — mocap skeleton → puppet rig retargeting
- `puppets/` — at least one canonical puppet template (port a V1 blob? or new?)
- "Pick Your Puppet" + "Apply to Character" operators
- NLA-push pattern in place
- **Success criteria:** student records, processes, picks a puppet, applies — sees their performance on a character

### Phase 4 — Short film production use (mid-July → August)
- David + HIHO Club use the addon to produce his next short film
- Iteration on cleanup tools, retargeting quality, UX rough edges
- Document the experience for Range Eval + dissertation
- **Success criteria:** there exists a finished short film made with PPParty, and HIHO Club students participated

### Phase 5 — Art241 install (Fall 2026 onward, post-summer)
- Replicate BASEMENT setup at SJSU CADRE Lab Art241 (gated on the lab manager)
- ART 105 / ART 195 students use it as part of class
- Real-world classroom-validation begins

---

## 8. macOS specifics

**Python version:** 3.12 (intersection of FMC `>=3.10,<3.13` and Skellycam `>=3.11`).

**No Nvidia GPU required.** FreeMoCap works on Mac with CPU-based MediaPipe. Don't get distracted by SnowMocap's CUDA requirement — that's a different project we can't deploy.

**USB topology** (from `MULTICAM_SHOPPING_LIST.md`, already validated by David's hardware order):
- 2× cameras → USB-C hub → MacBook Thunderbolt port 1
- 1× camera → USB-A→USB-C adapter → port 2
- 1× camera → USB-A→USB-C adapter → port 3
- Power via MagSafe so all three TB ports stay free for cameras
- Skellycam README warns about USB hub bandwidth issues — if a camera fails to detect, swap port assignments

**Skellycam macOS install:** `python -m skellycam` on `localhost:53117`. The README's `uv venv` + `uv sync` instructions cover macOS. If we run it as a subprocess from our addon, we manage the lifecycle (start on first use, kill on Blender quit).

**FreeMoCap macOS install:** `pip install freemocap` works. The GUI uses PySide6 (Qt). Runs fine on Apple Silicon. README's `python3 -m venv` flow is what we'd use.

**Camera permissions:** macOS will prompt for camera access on first capture. Per memory `project_basement_multicam_install`, each capture process (Python, Blender) needs Camera permission granted in System Settings → Privacy & Security → Camera. One-time setup; persists.

---

## 9. Open questions / things to verify on BASEMENT day

These can't be settled by code-reading; they need real hardware:

1. **Does `pip install freemocap` actually finish cleanly on David's MacBook Pro?** It pulls Skellycam, skellytracker, skelly_viewer, skellyforge, PySide6, opencv-contrib, aniposelib, plotly, ipykernel — heavy install. Might fail on a dependency. **Verify on first install.**
2. **Does Skellycam detect all 4 webcams?** USB controller topology, macOS AVFoundation, hub bandwidth — all unknowns until tested.
3. **Does FreeMoCap's calibration succeed on a homemade ChArUco board?** Per shopping list, DIY board on foam core should work, but board-quality affects calibration accuracy.
4. **Does FreeMoCap's processing complete in reasonable time on M3 / M5 Mac without CUDA?** MediaPipe per-camera is the bottleneck. 4 cameras × ~30 seconds of footage = 4 × 30 sec of MP inference, sequentially per camera. Might be 5-10 minutes processing per take.
5. **Does ajc27 addon work with current Blender 5.2 alpha?** The addon was probably built for Blender 4.x. Could need patches for Blender 5.2 Slotted Actions API (the same lesson V2 hit at day8).
6. **Camera recommendation lock:** shopping list said C922 ×4. David's actual order (per `project_basement_multicam_install`) was 4× **C922x**. Same camera family, should be fine.

If any of these fails, the architecture above is correct; we'd just have a longer Phase 0 to fix the broken piece before Phase 1 starts.

---

## 10. Risks (and what to do about them)

- **Risk: ajc27 addon's output rig doesn't match what we want.** If it produces a generic skeleton that doesn't accept retargeting, we either fork the addon and customize their rig builder, or we bypass it and load the .npy directly into our own armature.
  → **Mitigation:** Phase 0 verifies what they produce. Decide in Phase 1 whether to wrap or replace.

- **Risk: Skellycam recording filenames + folder structure don't fit cleanly into FMC's expected layout.** They're sister projects, so it should work, but the integration may have rough edges.
  → **Mitigation:** Phase 0 validates this end-to-end.

- **Risk: macOS heat / thermal throttling on 4-cam captures.** A MacBook Pro running 4 simultaneous webcams plus MediaPipe processing may throttle on long takes.
  → **Mitigation:** Test long takes in Phase 0. If throttling is real, the dedicated mocap desktop becomes a real budget item per `MULTICAM_MOCAP_DESIGN.md` "if needed."

- **Risk: Blender 5.2 alpha breaking changes.** ajc27 addon may not be 5.2-compatible. Same risk we hit on V2 with Slotted Actions.
  → **Mitigation:** Phase 0 verifies. If broken, options are: pin to Blender 4.x for ajc27 work, or patch the addon ourselves and submit upstream.

- **Risk: We're optimizing for "easy student install" but the install is heavy.** `pip install freemocap` + Blender + ajc27 addon + PPParty addon = real setup. Not Kid-Pix-easy.
  → **Mitigation:** Long-term, an installer script. Short-term, a written walkthrough doc. HS students at CADRE can manage CLI installs; K-12 deployment is later anyway.

---

## 11. Cross-references

- High-level architecture (David, ELI5): [`../R&D/MULTICAM_MOCAP_DESIGN.md`](../R&D/MULTICAM_MOCAP_DESIGN.md)
- Hardware shopping + day-1 setup: [`../R&D/MULTICAM_SHOPPING_LIST.md`](../R&D/MULTICAM_SHOPPING_LIST.md)
- Pre-this-project research (single-cam era): `../PPPARTY_V2/FREEMOCAP_RESEARCH.md`, `../PPPARTY_V2/HAND_ROTATION_NOISE_RESEARCH.md`, etc.
- Codebase paths: `../R&D/freemocap-main/`, `../R&D/skellycam/`, `../R&D/freemocap_blender_addon/ajc27_freemocap_blender_addon/`
- V2 pattern donor: `../PPPARTY_V2/` (parked at v2.0.4)
- V1 archive (do not confuse): `../PPPARTY_V1_ARCHIVE/`
- Memory: `project_ppparty_multicam_summer_priority_2026-05-06`, `project_software_identity_reframe_2026-05-06`, `feedback_ppparty_sandbox_only`
