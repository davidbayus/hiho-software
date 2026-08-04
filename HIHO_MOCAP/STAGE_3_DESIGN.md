# HIHO MOCAP — Stage 3 Design Doc (v1.0 Capture Flow)

**Date:** 2026-05-23
**Status:** Design — **SIGNED OFF 2026-05-23**. Implements the v1.0 feature checklist from [HIHO_MOCAP_v1_PLAN.md](HIHO_MOCAP_v1_PLAN.md).
**Builds on:** [CAMERA_MANAGER_DESIGN.md](CAMERA_MANAGER_DESIGN.md) (Stages 1 & 2 — passed at BASEMENT 2026-05-16 & 2026-05-17)
**Author:** David Bayus + Claude

---

## What This Is (Plain English)

The Stage 3 doc is the build plan for turning the two working Python modules (`camera_manager.py` and `blender_preview.py`) into a real Blender addon a student can install, click four buttons, and end up with mocap on a rig in their scene.

**Stage 1 gave us:** an engine that can open 4 cameras and write synchronized .mp4 files.
**Stage 2 gave us:** a way to see those camera frames live inside Blender.
**Stage 3 gives us:** the addon — the operators, the N-panel, the buttons, the wrapper around FreeMoCap's pipeline, and the operator that spawns the result rig.

When Stage 3 is done, the addon is v1.0 and the HIHO experimental animation club can install one zip file and use it.

---

## What's Already Done vs. What's Left

| Piece | Status |
|---|---|
| `core/camera_manager.py` — 4-cam open + record | ✅ Stage 1 — PASSED 2026-05-16 |
| `core/blender_preview.py` — frames into Blender Image datablocks | ✅ Stage 2 — PASSED 2026-05-17 |
| Addon scaffolding (`__init__.py` w/ `bl_info`, register/unregister) | ❌ |
| `operators/` — Blender operators wrapping the core modules | ❌ |
| `ui/panels.py` — N-panel with buttons + 4-cam grid | ❌ |
| Vendored FreeMoCap inside the addon | ❌ |
| `core/freemocap_runner.py` — wrapper around FreeMoCap's pipeline | ❌ |
| `core/output_rig.py` — spawn SkellyCam skelly rig with the animation | ❌ |
| One-zip Extensions install | ❌ |

Everything in the "❌" rows lands in Stage 3.

---

## The Student's Journey (the whole point)

After install, this is what a student does. Stage 3 succeeds if all five steps below work without the student dropping into Terminal.

```
1. Open Blender.
   In the N-panel, see a "HIHO MOCAP" tab.

2. Click [ Cameras Up ].
   4 little camera previews fade in inside the panel (2x2 grid).
   Student adjusts framing, makes sure everyone they want is in frame.

3. Click [ ● Record ].
   A 15-second countdown shows in the panel ("Recording in 14... 13...").
   Performer gets ready. Recording starts. A red dot + timer ticks up.
   At 60 seconds, recording stops automatically.
   (Or click [ ■ Stop ] to stop early.)

4. Click [ Process Mocap ].
   A real Blender progress bar appears at the bottom of the screen.
   ("Detecting people in camera 1...", "Triangulating...", etc.)
   Takes minutes — the student knows it's working because the bar moves.

5. Click [ Spawn Rig ].
   A SkellyCam skelly rig appears in the scene at the world origin,
   with the captured animation baked onto it.
   Press Play — the rig moves.
```

That's v1.0. Nothing else.

---

## The Big Picture (How It All Fits)

```
┌──────────────────────────────────────────────────────────────────┐
│                       BLENDER (main thread)                       │
│                                                                   │
│  ┌─────────────────────────────────────┐                         │
│  │       N-Panel: "HIHO MOCAP"         │                         │
│  │                                      │                         │
│  │  ┌─────┐ ┌─────┐                    │   ← 4-camera live grid │
│  │  │Cam1 │ │Cam2 │   (live thumbnails) │     (Stage 2 images,   │
│  │  ├─────┤ ├─────┤                    │      displayed via     │
│  │  │Cam3 │ │Cam4 │                    │      template_ID /     │
│  │  └─────┘ └─────┘                    │      template_preview) │
│  │                                      │                         │
│  │  [ Cameras Up ]  [ Cameras Down ]   │   ← Stage 3 operators  │
│  │  [ ● Record ]    Countdown: 15s     │                         │
│  │                  Length:    60s     │                         │
│  │  [ Process Mocap ]                  │                         │
│  │  [ Spawn Rig ]                      │                         │
│  │                                      │                         │
│  └──────────────┬───────────────────────┘                         │
│                 │                                                  │
│   ┌─────────────┴─────────────┐                                   │
│   ▼                           ▼                                   │
│  Operators                Properties (PropertyGroup)              │
│   │                           │                                   │
│   │                           └── countdown_seconds (IntProp)     │
│   │                               record_length_seconds (IntProp) │
│   │                               last_take_path (StringProp)     │
│   ▼                                                                │
│  ┌──────────────────────────────────────────────────┐             │
│  │  core/camera_manager.py  (Stage 1 — done)         │             │
│  │  core/blender_preview.py (Stage 2 — done)         │             │
│  │  core/freemocap_runner.py (NEW)                   │             │
│  │  core/output_rig.py       (NEW)                   │             │
│  └──────────────────┬───────────────────────────────┘             │
│                     │                                              │
└─────────────────────┼──────────────────────────────────────────────┘
                      │
              ┌───────┴────────┐
              ▼                ▼
       Disk: MOCAP_TAKES/   Vendored FreeMoCap
       (the .mp4 files      (inside addon zip,
        and processed       pipeline runs in a
        output)             worker thread to keep
                            Blender responsive)
```

---

## The Big Decisions (resolve in this doc so we don't keep relitigating)

**All five confirmed by David on 2026-05-23.**

### Decision 1: Class prefix is `HIHO_MOCAP_OT_*`

Old V2 code used `PPPARTY_OT_*`. Per the rename, all new operators use `HIHO_MOCAP_OT_*`. Panels use `HIHO_MOCAP_PT_*`. Property groups use `HIHO_MOCAP_PG_*`. No back-compat alias — there's no live install to break.

### Decision 2: Vendored FreeMoCap via Blender Extensions wheel bundling

Per `project_ppparty_extensions_migration.md`, the canonical install model for v1.0 is the Blender Extensions system with bundled wheels. That means:

- The addon's `blender_manifest.toml` lists FreeMoCap + its transitive deps as wheels.
- The wheels live in a `wheels/` folder inside the addon zip.
- Blender installs them into an addon-local site-packages on first enable.
- Students never run `pip` themselves.

**Risk:** FreeMoCap has heavy transitive deps (MediaPipe, OpenCV, PySide6, plotly, ipykernel, aniposelib...). Total wheel size will be hundreds of MB. We don't know yet if Extensions wheel bundling handles a payload this big cleanly. **This is the biggest unknown in Stage 3** and gets its own build step (Step 4) to de-risk early.

**Fallback if wheel bundling can't carry FreeMoCap:** ship the addon with a "Run install script" operator that pip-installs into Blender's Python on first run. Uglier UX but proven (it's what Stage 2's cv2 install was). Decide at Step 4 once we've actually tried Extensions.

### Decision 3: 4-camera live grid lives in the N-panel itself

Two options:
- **A)** A separate Image Editor area the student has to set up (what Stage 2 does today).
- **B)** Inline thumbnails right in the N-panel, in a 2x2 grid.

**Choose B.** It's the v1 plan's ESSENTIAL viz priority — the whole point is the student sees their cameras *without* having to know what an Image Editor is. We use the existing `bpy.data.images["PPParty_Cam_N"]` from Stage 2 and display each via `layout.template_preview(...)` or `layout.template_ID_preview(...)` with a small size.

(Stage 2's image names still say `PPParty_Cam_N`. Renaming to `HIHO_MOCAP_Cam_N` is part of Step 1 below.)

### Decision 4: FreeMoCap processing runs in a worker thread + uses Blender's native progress

FreeMoCap's processing takes minutes (MediaPipe per camera + triangulation). If we run it in the main thread, Blender freezes. We run it in a `threading.Thread` and poll its status from a `bpy.app.timers` callback (same pattern Stage 2 already uses for camera frames).

For the visible progress bar, we use `context.window_manager.progress_begin(0, 100)` / `progress_update(n)` / `progress_end()` — Blender's native progress reporting that shows in the bottom status bar. FreeMoCap exposes per-stage callbacks we can hook into for the percentage.

### Decision 5: Output location stays as it is

Recordings land in `~/Desktop/CALIBRATION_RECORDINGS/<timestamp>/` (matches what Stage 1 already does and what FreeMoCap already reads). Don't move it for v1.0 — it works. v1.1 can introduce a configurable take folder if needed.

**David flagged 2026-05-23:** the multi-folder structure (`CALIBRATION_RECORDINGS/`, `MOCAP_TAKES/`, `~/freemocap_data/recording_sessions/`, `HIHO_MOCAP_LIBRARY/`) is genuinely hard to track. Queued for post-v1 cleanup in [BUGS_AND_BACKLOG.md](BUGS_AND_BACKLOG.md). v1.0 lives with the current layout to ship.

---

## Module Layout (what new files we add)

Adds in **bold**, existing files unchanged:

```
SOFTWARE/HIHO_MOCAP/
├── __init__.py                       ← NEW (bl_info + register/unregister)
├── blender_manifest.toml             ← NEW (Extensions system manifest)
├── wheels/                           ← NEW (bundled FreeMoCap + deps)
│   └── ...
├── core/
│   ├── __init__.py                   (unchanged)
│   ├── camera_manager.py             (Stage 1)
│   ├── blender_preview.py            (Stage 2)
│   ├── freemocap_runner.py           ← NEW (wraps FreeMoCap pipeline)
│   └── output_rig.py                 ← NEW (spawns SkellyCam skelly)
├── operators/                        ← NEW folder
│   ├── __init__.py
│   ├── cameras.py                    (start/stop cameras)
│   ├── record.py                     (countdown + record + stop)
│   ├── process.py                    (process mocap with progress bar)
│   └── output.py                     (spawn output rig)
├── ui/                               ← NEW folder
│   ├── __init__.py
│   └── panels.py                     (HIHO_MOCAP_PT_main with 4-cam grid)
├── properties.py                     ← NEW (PropertyGroup w/ countdown, length, etc.)
├── ARCHITECTURE.md                   (existing — needs an update pass at end of Stage 3)
├── BUGS_AND_BACKLOG.md               (existing)
├── CAMERA_MANAGER_DESIGN.md          (existing — Stages 1-2 spec)
├── HIHO_MOCAP_v1_PLAN.md             (existing — the requirements)
├── STAGE_3_DESIGN.md                 (this doc)
├── README.md                         (existing)
├── HIHO_MOCAP_LIBRARY/               (existing)
├── MOCAP_CALIBRATION_FILES/          (existing — Stage 1 CLI driver lives here)
└── MOCAP_TAKES/                      (existing)
```

**Two non-negotiables in this layout:**

- **Operators are thin.** Each operator file holds one operator class. The operator's `execute()` is ~10–30 lines: validate state, call into `core/`, set status. No business logic in operators.
- **`core/` modules never import `bpy` if they don't have to.** `camera_manager.py` already follows this (no `bpy`). `freemocap_runner.py` follows the same rule — pure Python wrapper around FreeMoCap. Only `blender_preview.py` and `output_rig.py` import `bpy` because their job is to talk to Blender.

---

## Each Operator's Design

### `HIHO_MOCAP_OT_start_cameras`

**Purpose:** Open 4 cameras and start the live preview in the N-panel grid.

```python
class HIHO_MOCAP_OT_start_cameras(bpy.types.Operator):
    bl_idname = "hiho_mocap.start_cameras"
    bl_label = "Cameras Up"

    def execute(self, context):
        # 1. Instantiate CameraManager (Stage 1) with detected/configured indices
        # 2. Call .start() — get {cam_id: True/False} dict back
        # 3. If any failed: self.report({'ERROR'}, "Camera N failed to open"); return {'CANCELLED'}
        # 4. Instantiate BlenderCameraPreview (Stage 2) wrapping the manager
        # 5. Call preview.start() — this also creates the Image datablocks
        # 6. Stash both objects on a module-level singleton so other operators can reach them
        # 7. Tag panel for redraw so the grid populates
        return {'FINISHED'}
```

**State storage:** A module-level dict in `operators/__init__.py` — `STATE = {"manager": None, "preview": None, "recorder_thread": None, ...}`. Module-level is fine here because there's only ever one mocap session active at a time. Don't overdesign with a Scene PropertyGroup for runtime objects (they're not serializable anyway).

### `HIHO_MOCAP_OT_stop_cameras`

Mirror of above. Calls `preview.stop()`, `manager.stop()`, clears state. Image datablocks stick around showing last frame (matches what Stage 2 already does on `preview.stop()`).

### `HIHO_MOCAP_OT_record`

**Purpose:** Countdown, then record for the configured duration.

```python
class HIHO_MOCAP_OT_record(bpy.types.Operator):
    bl_idname = "hiho_mocap.record"
    bl_label = "Record"

    _timer = None
    _phase = "countdown"  # or "recording" or "done"
    _countdown_start_time = 0.0

    def invoke(self, context, event):
        # Validate cameras are up. If not: error + cancel.
        # Register a modal timer (0.1s) and a wm timer.
        # Set _phase = "countdown".
        self._countdown_start_time = time.monotonic()
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.1, window=context.window)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type == 'TIMER':
            if self._phase == "countdown":
                elapsed = time.monotonic() - self._countdown_start_time
                remaining = context.scene.hiho_mocap.countdown_seconds - elapsed
                if remaining <= 0:
                    # Countdown done. Start recording.
                    STATE["manager"].start_recording(
                        out_dir=expanduser("~/Desktop/CALIBRATION_RECORDINGS/..."),
                        duration_sec=context.scene.hiho_mocap.record_length_seconds,
                    )
                    self._phase = "recording"
                    self._record_start_time = time.monotonic()
                # else: update the panel's countdown display (force redraw)
            elif self._phase == "recording":
                # Check if recording finished (frame count hit target)
                if not STATE["manager"].is_recording:
                    self._phase = "done"
                    return self._cleanup(context, {'FINISHED'})
        elif event.type == 'ESC':
            STATE["manager"].stop_recording()
            return self._cleanup(context, {'CANCELLED'})
        return {'PASS_THROUGH'}  # don't block other Blender input
```

**Why modal operator** (not a `bpy.app.timers` callback): we want ESC to stop the recording. Modal operators can intercept keyboard input; timer callbacks can't. The cost is the operator stays "running" for ~75 seconds (15s countdown + 60s record), which is fine.

**Why `PASS_THROUGH`** in modal: so the student can still rotate the viewport / click around while recording. We only consume the timer + ESC events.

### `HIHO_MOCAP_OT_stop_record`

Optional companion to ESC — a clickable Stop button. Just sets a flag the modal operator notices. Could fold into Record as a state toggle if simpler.

### `HIHO_MOCAP_OT_process_mocap`

**Purpose:** Run FreeMoCap's pipeline on the last recorded take, without blocking Blender.

```python
class HIHO_MOCAP_OT_process_mocap(bpy.types.Operator):
    bl_idname = "hiho_mocap.process_mocap"
    bl_label = "Process Mocap"

    def execute(self, context):
        take_path = context.scene.hiho_mocap.last_take_path
        if not take_path:
            self.report({'ERROR'}, "No take to process. Record something first.")
            return {'CANCELLED'}

        # Spin up a worker thread that runs FreeMoCap headless
        STATE["processor"] = freemocap_runner.FreeMocapRunner(take_path)
        STATE["processor"].start()  # non-blocking — starts the worker

        # Begin Blender's native progress
        context.window_manager.progress_begin(0, 100)

        # Register a poll timer that:
        #   - Reads processor.progress_pct
        #   - Calls wm.progress_update(pct)
        #   - When processor.is_done: progress_end() + set output_path on scene props
        bpy.app.timers.register(self._poll_progress, first_interval=0.5)

        self.report({'INFO'}, "Processing started — check progress in the status bar.")
        return {'FINISHED'}
```

**`core/freemocap_runner.py` sketch:**

```python
class FreeMocapRunner:
    def __init__(self, take_path: str):
        self.take_path = take_path
        self.progress_pct = 0
        self.current_stage = "pending"
        self.is_done = False
        self.error = None
        self.output_path = None
        self._thread = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        try:
            # Import the vendored FreeMoCap
            from freemocap.process_recording_headless import process_recording_headless

            def progress_cb(stage: str, pct: float):
                self.current_stage = stage
                self.progress_pct = int(pct * 100)

            self.output_path = process_recording_headless(
                self.take_path,
                progress_callback=progress_cb,
                # ... whatever other params FMC needs
            )
            self.is_done = True
        except Exception as e:
            self.error = str(e)
            self.is_done = True
```

**Threading caveat:** FreeMoCap's pipeline probably does a lot of multiprocessing under the hood (MediaPipe per camera, Anipose triangulation). Running it as a thread inside Blender's process should still work because the heavy work happens in subprocesses or in C extensions that release the GIL. **Verify this in Step 5** — if FreeMoCap fights with Blender's main loop, the fallback is `subprocess.Popen` to run a worker Python process instead of a thread.

### `HIHO_MOCAP_OT_spawn_output_rig`

**Purpose:** Load the SkellyCam skelly rig with the processed animation onto it.

The SkellyCam project includes a default skeleton (the "skelly rig") that's the standard FreeMoCap output target. We use that as v1.0's output. (Replacing with a custom HIHO demo character is v1.1 work per the v1 plan.)

```python
class HIHO_MOCAP_OT_spawn_output_rig(bpy.types.Operator):
    bl_idname = "hiho_mocap.spawn_output_rig"
    bl_label = "Spawn Rig"

    def execute(self, context):
        output_path = STATE.get("processor", None) and STATE["processor"].output_path
        if not output_path:
            self.report({'ERROR'}, "No processed output. Run Process Mocap first.")
            return {'CANCELLED'}

        # Delegate to core/output_rig.py
        rig_obj = output_rig.spawn_skelly_with_animation(output_path)

        # Frame the viewport on it
        bpy.ops.object.select_all(action='DESELECT')
        rig_obj.select_set(True)
        bpy.ops.view3d.view_selected(use_all_regions=False)

        return {'FINISHED'}
```

**`core/output_rig.py`** wraps the rig-loading logic. For v1.0 the simplest path is to **call FreeMoCap's existing Blender-output code** if it has one (ajc27's freemocap_blender_addon does this; check whether it's bundled with FreeMoCap or separate). If we have to reimplement, the steps are:

1. Load the .npy 3D landmarks from the processed output folder.
2. Create an Armature object with bones matching SkellyCam's skelly hierarchy (skull, spine, arms, legs).
3. For each frame in the landmarks: convert landmark positions → bone transforms, set keyframes.
4. Return the armature object.

**The reimplement path is heavy.** Plan for v1.0 to use whatever FreeMoCap/ajc27 provides off-the-shelf; reimplement only if it's broken on Blender 5.0.

---

## N-Panel Layout (the only UI the student sees)

```
┌─────────────────────────────────────────┐
│  HIHO MOCAP                              │
│  ─────────────────────────────────────── │
│                                          │
│   Cameras                                │
│   ┌────────────┐ ┌────────────┐        │
│   │   Cam 1    │ │   Cam 2    │        │
│   │   live     │ │   live     │        │
│   └────────────┘ └────────────┘        │
│   ┌────────────┐ ┌────────────┐        │
│   │   Cam 3    │ │   Cam 4    │        │
│   │   live     │ │   live     │        │
│   └────────────┘ └────────────┘        │
│                                          │
│   [ Cameras Up ]   [ Cameras Down ]     │
│   ─────────────────────────────────────  │
│                                          │
│   Record                                 │
│   Countdown:  [ 15s   ]                  │
│   Length:     [ 60s   ]                  │
│                                          │
│   [ ● Record ]   [ ■ Stop ]              │
│                                          │
│   Status: 14s until recording...         │
│   ─────────────────────────────────────  │
│                                          │
│   Process                                │
│   Last take: 2026-05-23_14-22-18         │
│   [ Process Mocap ]                      │
│                                          │
│   ─────────────────────────────────────  │
│                                          │
│   Output                                 │
│   [ Spawn Rig ]                          │
│                                          │
└─────────────────────────────────────────┘
```

Sections divided by `layout.separator()` so the eye can find them. Camera previews use `layout.template_ID_preview(...)` or a custom `Operator` that draws via `bgl/gpu` — TBD in Step 2 based on what works smoothly at panel-redraw time.

---

## Build Order (Step by Step)

Each step ends with a real test. **Don't start the next step until the current one passes.** If something fails, fix it before moving on — that's the rule that got Stages 1 and 2 home clean.

### Step 1 — Addon scaffolding + camera operators (TEST at BASEMENT)

**What gets built:**
- `__init__.py` with `bl_info` and `register()` / `unregister()`
- `properties.py` with a `HIHO_MOCAP_PG_settings` PropertyGroup (countdown, length, last_take_path)
- `operators/cameras.py` with `HIHO_MOCAP_OT_start_cameras` + `HIHO_MOCAP_OT_stop_cameras`
- `ui/panels.py` with `HIHO_MOCAP_PT_main` showing just the two buttons (no grid yet)
- Rename `bpy.data.images["PPParty_Cam_N"]` → `"HIHO_MOCAP_Cam_N"` in `blender_preview.py`

**Test:**
- Install the addon as a regular .py addon (not Extensions yet — that's Step 4)
- N-panel shows "HIHO MOCAP" tab with two buttons
- "Cameras Up" — Stage 2 preview works (image datablocks appear, refresh)
- "Cameras Down" — preview stops cleanly, no errors

**Passes if:** the addon installs, the buttons work, no console errors. Stage 1+2 functionality is preserved through the operator wrapper.

### Step 2 — "Open Camera Views" window (PIVOTED 2026-05-23)

**Pivot rationale:** the original plan (inline 2x2 thumbnail grid in the N-panel via `template_icon` + writes to `Image.preview.icon_pixels_float`) hit Blender's C-level icon cache. Even with `is_icon_custom = True`, the rendered icon shown by `template_icon` didn't update from per-frame icon-pixel writes. `template_icon` is built for static thumbnails, not video. Real live video in a panel requires a GPU draw handler (~100 lines, fiddly positioning). Cost/benefit didn't justify it for v1.0.

**What we built instead:** a single **"Open Camera Views"** button in the N-panel that spawns a new top-level window containing a 2x2 grid of Image Editors, one per camera. Uses Stage 2's already-proven Image Editor live-refresh path (`img.pixels.foreach_set` + `img.update()` is enough; Image Editor draws directly from image pixel data, not from the cached preview icon).

**What gets built:**
- `HIHO_MOCAP_OT_open_camera_views` operator in `operators/cameras.py`
- N-panel button (label "Open Camera Views", icon `WINDOW`), visible only when cameras are live
- Reverted preview-icon code from `core/blender_preview.py` — back to Stage 2 form

**Test:**
- "Cameras Up" → status box shows "Live: N cameras", "Open Camera Views" button appears
- Click "Open Camera Views" → new window opens with 4 Image Editors in 2x2, each showing one camera live
- Move in front of cameras → see motion in each Image Editor at 10 Hz
- Original Blender window stays untouched

**Passes if:** new window opens, 4 image editors visible, all show live camera feeds, main workspace undisturbed.

**v1.1+ possibility:** if students complain about "having to open a separate window," reconsider GPU draw handler for inline panel previews. For v1.0, defer.

### Step 3 — Record operator with countdown + duration (TEST at BASEMENT)

**What gets built:**
- `operators/record.py` — modal operator with countdown phase + recording phase
- N-panel additions: Countdown property field, Length property field, Record button, Stop button, status text
- Properties bound to the `HIHO_MOCAP_PG_settings` PropertyGroup

**Test:**
- Set countdown=5s, length=10s (short for fast iteration)
- "Cameras Up" → grid live
- "Record" → 5-second countdown visible in panel
- Recording for 10s, red dot visible
- Files land in `~/Desktop/CALIBRATION_RECORDINGS/<timestamp>/` (4 .mp4s with identical frame counts)

**Passes if:** countdown counts down visibly, recording runs the full configured length, files are on disk with parity, ESC cancels cleanly.

### Step 4 — Vendor FreeMoCap into the addon (TEST: zip installs end-to-end)

**This is the biggest unknown step. Do this BEFORE writing the Process operator, because if vendoring fails, the whole approach changes.**

**What gets built:**
- `blender_manifest.toml` with the Extensions system metadata
- `wheels/` folder populated with FreeMoCap + transitive deps (downloaded via `pip download --dest wheels/ freemocap`)
- Manifest wheel manifest entries
- Test build of the .zip

**Test:**
- Build the .zip
- Note its file size (probably hundreds of MB — log this as a baseline)
- Install via Blender's Extensions install
- Open Blender's Python console: `import freemocap; print(freemocap.__version__)` — should work
- Restart Blender, reverify — wheels persisted

**Passes if:** addon zip installs, FreeMoCap is importable inside Blender's Python.

**Fails if:** wheel install errors, missing deps, OS-specific wheel mismatches, or Blender refuses a zip over its size limit. **Fallback** if this fails: defer to a "Run install script" operator that pip-installs into Blender's Python on first enable. Document the fallback in `BUGS_AND_BACKLOG.md` and proceed.

### Step 5 — Process operator with progress bar (TEST at BASEMENT)

**What gets built:**
- `core/freemocap_runner.py` — `FreeMocapRunner` class with `start()`, `progress_pct`, `is_done`
- `operators/process.py` — the `HIHO_MOCAP_OT_process_mocap` operator
- Timer-driven progress polling that calls `wm.progress_update()`
- N-panel additions: "Last take" display, Process button

**Test:**
- Record a 10s take (from Step 3 flow)
- Click "Process Mocap"
- Blender's bottom status bar shows progress moving up over minutes
- Blender stays responsive throughout (rotate viewport, etc.)
- On completion: output folder populated with `.npy` landmarks + processed videos

**Passes if:** processing completes without freezing Blender, output folder matches what Terminal FreeMoCap produces.

**Risk to validate:** FreeMoCap's internal multiprocessing inside a Blender-hosted thread. If it deadlocks or crashes, swap to `subprocess.Popen` running a worker Python process (per Decision 4 note).

### Step 6 — Spawn output rig (TEST at BASEMENT)

**What gets built:**
- `core/output_rig.py` — wraps whatever FreeMoCap / ajc27 provides for Blender output, OR a clean reimplementation if their code isn't compatible with Blender 5.0 / Python 3.11
- `operators/output.py` — the `HIHO_MOCAP_OT_spawn_output_rig` operator
- N-panel "Spawn Rig" button

**Test:**
- Full end-to-end from a fresh scene: Cameras Up → Record (short take) → Process → Spawn Rig
- Armature appears in scene
- Press Spacebar to play — armature animates per the recorded motion

**Passes if:** the whole student journey runs without dropping to Terminal, and the rig actually moves.

**This is v1.0 done.** Tag the build, write a one-page install README for the club, schedule the first club session.

### Step 7 (STRETCH) — 3D skeleton viewer in viewport

If everything above ships clean and time remains, build the stretch goal from the v1 plan: a live armature populating in the viewport as processing data lands.

**Ship without it** if Step 6 is on the edge of the club's launch date. v1 plan explicitly says this is a stretch.

---

## Risks (and what to do about them)

1. **FreeMoCap wheel bundling is bigger / messier than expected.** Heaviest unknown in Stage 3. Mitigated by doing it as Step 4 (early), with a documented pip-install fallback.

2. **N-panel performance with 4 inline live thumbnails.** Mitigated by tunable refresh rate (Stage 2 already exposes `PREVIEW_HZ`); worst case we drop to 5 Hz or move grid to a dedicated sub-area.

3. **FreeMoCap's processing fights with Blender threading.** Mitigated by `subprocess.Popen` fallback if the in-process thread approach deadlocks.

4. **Output rig spawn relies on FreeMoCap / ajc27 working on Blender 5.0 / Python 3.11.** ajc27 was last verified on Blender 4.x. Could need patches. Mitigated by reimplementing the .npy → armature step ourselves if needed (heavy but tractable).

5. **One-zip Extensions install on macOS vs. Windows behaves differently.** v1.0 only needs to work on macOS (BASEMENT, club members likely Mac). Windows support is v1.1+.

6. **Camera permissions on a fresh machine.** Already a known issue (see CAMERA_MANAGER_DESIGN.md Risks #1). Document in the install README; can't fix in code.

---

## What This Doc Doesn't Cover (parked for later)

These are intentionally NOT in Stage 3, per v1 plan "Parked for v1.1+":

- NLA-editor cleanup pipeline
- Log output panel (FreeMoCap-style log strip inside Blender)
- Custom HIHO demo character to replace the SkellyCam default rig
- Dedicated "HIHO MOCAP" workspace tab at the top of Blender
- Calibration walkthrough in-Blender (still done in Terminal FreeMoCap GUI for v1.0)
- Camera detection / selection UI (cameras hardcoded to `[1, 2, 3, 4]` or whatever Stage 1 testing settled on)

Don't sneak any of these in mid-Stage-3 — they bloat the scope and delay the club. Note any that turn out to be load-bearing in `BUGS_AND_BACKLOG.md` for v1.1 planning.

---

## Sources / Cross-References

- [HIHO_MOCAP_v1_PLAN.md](HIHO_MOCAP_v1_PLAN.md) — the requirements doc that Stage 3 implements
- [CAMERA_MANAGER_DESIGN.md](CAMERA_MANAGER_DESIGN.md) — Stages 1 & 2 design (the engine + Blender bridge)
- [ARCHITECTURE.md](ARCHITECTURE.md) — pre-Camera-Manager architecture, needs an update pass at end of Stage 3 (still references SkellyCam HTTP server which the Camera Manager replaced)
- [BUGS_AND_BACKLOG.md](BUGS_AND_BACKLOG.md) — the 22 BASEMENT bugs Stage 3's pipeline replaces
- `MEMORY/project_hiho_mocap_current_state.md` — live state anchor
- `MEMORY/project_hiho_mocap_freemocap_relationship.md` — bundled-vendored model, AGPL obligations
- `MEMORY/project_ppparty_extensions_migration.md` — Extensions wheel bundling rationale
- `MEMORY/project_hiho_animation_club.md` — first non-David user, launches late June 2026

---

## Resolved Questions (David 2026-05-23)

- **Suite question — RESOLVED.** Green Room and Quadre are **separate** HIHO addons. Not a shared HIHO suite. Each ships independently. Branding for v1.0 of HIHO MOCAP doesn't have to coordinate with the others.
- **Course connection — RESOLVED.** **No** Stage 3 work ties to an ART 102 / 105 / 180 / 195 deliverable. David explicitly wants this project to grow organically with no set deadlines. The HIHO experimental animation club's late-June launch is a soft target, not a deadline.
