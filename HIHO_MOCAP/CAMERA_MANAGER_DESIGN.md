# PPParty Camera Manager — Design Doc

**Date:** 2026-05-15
**Status:** Design — replaces SkellyCam in our pipeline
**Author:** David Bayus + Claude

---

## What This Is (Plain English)

A module inside the PPParty addon that handles everything webcam-related: detecting cameras, showing live previews inside Blender, and recording synchronized video to disk. Think of it as our own mini-SkellyCam, but simpler, cross-platform, and living inside Blender instead of being a separate server.

**Why we need it:** SkellyCam had a RAM bug that silently ate recordings (FreeMoCap Issue #650). We already built a working replacement recorder (`MOCAP_CALIBRATION_FILES/record_calibration.py`) that writes direct-to-disk. This design promotes that recorder into a proper Blender-integrated module and adds the live preview feature we've been wanting.

---

## What It Replaces

| Old piece | What was wrong | New piece |
|-----------|---------------|-----------|
| SkellyCam (FastAPI server + WebSocket) | RAM bug (#650), over-engineered for our needs, separate process to manage | `core/camera_manager.py` — runs inside Blender's Python |
| `record_calibration.py` (standalone script) | Works great but requires Terminal, no preview, no Blender integration | Same proven logic, absorbed into the Camera Manager |
| FreeMoCap GUI's "record" tab | Crashes on macOS (Bug #10, #13), can't find Blender (#12) | PPParty N-panel buttons |

---

## How It Works (The Big Picture)

```
┌─────────────────────────────────────────────────┐
│                BLENDER (main thread)             │
│                                                  │
│  ┌──────────────┐    ┌─────────────────────────┐ │
│  │  N-Panel UI  │    │  Timer Callback (10 Hz) │ │
│  │              │    │                         │ │
│  │  [Cam 0] img │◄───│  Grabs latest frames    │ │
│  │  [Cam 1] img │    │  from shared buffers,   │ │
│  │  [Cam 2] img │    │  writes to bpy.Image    │ │
│  │  [Cam 3] img │    │  datablocks, triggers   │ │
│  │              │    │  panel redraw           │ │
│  │  [● Record]  │    └────────────▲────────────┘ │
│  │  [■ Stop]    │                 │              │
│  └──────────────┘                 │              │
└───────────────────────────────────┼──────────────┘
                                    │ reads latest frame
                    ┌───────────────┴───────────────┐
                    │     Shared Frame Buffers       │
                    │  (one numpy array per camera,  │
                    │   protected by threading.Lock) │
                    └───────────────┬───────────────┘
                                    │ writes every frame
          ┌─────────┬──────────┬────┴────┐
          ▼         ▼          ▼         ▼
     [Thread 0] [Thread 1] [Thread 2] [Thread 3]
     cv2.read() cv2.read()  cv2.read() cv2.read()
         │          │           │          │
         ▼          ▼           ▼          ▼
     (if recording: also write to VideoWriter)
```

**Four background threads** — one per camera, each running `cv2.VideoCapture.read()` in a loop. Every frame goes into a shared buffer (a single numpy array per camera, swapped atomically). If recording is active, the frame also gets written to a `cv2.VideoWriter`.

**One Blender timer** — fires ~10 times per second. Reads the latest frame from each shared buffer, downscales it for preview, converts to Blender's pixel format (RGBA float), and writes it into a `bpy.data.images` datablock. The N-panel displays those images.

**The camera threads never touch Blender.** They're pure OpenCV. Blender interaction only happens on the main thread via the timer callback. This keeps things stable — Blender's Python API isn't thread-safe, so you never want background threads calling `bpy.*` anything.

---

## Two Modes

### Preview Mode (cameras open, no recording)

What the student sees: 4 small camera views in the N-panel. They can check framing, verify all cameras are working, make sure the performer is visible in all views.

What's happening: each camera thread is grabbing frames and updating the shared buffer. The timer callback is pulling frames and pushing to Blender Images. No disk writes.

### Record Mode (cameras open, writing to disk)

What the student sees: same 4 camera views, but with a red "● Recording" indicator and a frame counter ticking up.

What's happening: same as preview, but each camera thread is ALSO writing frames to a `cv2.VideoWriter`. Frame-count-bounded (not time-bounded) — same proven approach from `record_calibration.py` that guarantees identical frame counts across all cameras (FreeMoCap requires this).

Transition from Preview → Record is instant because the cameras are already open and warmed up. No countdown delay needed (the current recorder has a 5-second countdown because it needs time to open cameras — we've already done that in Preview).

---

## Cross-Platform

The only platform-specific part is how OpenCV talks to the camera hardware:

| Platform | OpenCV backend | How we handle it |
|----------|---------------|-----------------|
| macOS | `CAP_AVFOUNDATION` | Auto-detected by OpenCV when you pass `cv2.CAP_ANY` |
| Windows | `CAP_DSHOW` (DirectShow) or `CAP_MSMF` | Auto-detected by OpenCV |
| Linux | `CAP_V4L2` | Auto-detected by OpenCV |

**The fix is simple:** instead of hardcoding `cv2.CAP_AVFOUNDATION` like the current recorder does, we use `cv2.CAP_ANY` (which is just `0`) and let OpenCV pick the right backend. If that causes issues on a specific platform, we add a fallback list.

```python
# Current recorder (macOS-only):
cap = cv2.VideoCapture(cam_id, cv2.CAP_AVFOUNDATION)

# Camera Manager (cross-platform):
cap = cv2.VideoCapture(cam_id)  # CAP_ANY is the default
```

That's it. OpenCV handles the rest.

---

## Module Design

### File: `core/camera_manager.py`

The core module. No Blender dependency — just OpenCV + threading + numpy. This means it can also be used standalone (for testing outside Blender, or as a CLI recorder).

```python
class CameraManager:
    """Manages N webcams: preview frames + synchronized recording."""

    def __init__(self, camera_ids: list[int], resolution=(960, 540), fps=30):
        ...

    # === Lifecycle ===
    def start(self) -> dict[int, bool]:
        """Open all cameras, start capture threads, begin preview.
        Returns {cam_id: True/False} for which cameras opened successfully."""

    def stop(self):
        """Stop all threads, release all cameras. Safe to call multiple times."""

    # === Recording ===
    def start_recording(self, output_dir: str, duration_sec: int = 60) -> str:
        """Begin writing to disk. Returns the output directory path.
        Frame-count-bounded: all cameras record exactly duration_sec * fps frames."""

    def stop_recording(self) -> dict[int, int]:
        """Stop recording early (before duration limit).
        Returns {cam_id: frame_count} for each camera."""

    # === Preview ===
    def get_latest_frames(self) -> dict[int, numpy.ndarray | None]:
        """Get the most recent frame from each camera (or None if no frame yet).
        Returns full-resolution frames. Caller handles downscaling for preview."""

    # === Status ===
    @property
    def is_recording(self) -> bool: ...

    @property
    def camera_count(self) -> int: ...

    @property
    def frame_counts(self) -> dict[int, int]: ...

    @property
    def recording_elapsed_sec(self) -> float: ...
```

**Key internals:**

- One `_CameraThread` per camera (daemon thread). Each thread:
  - Opens `cv2.VideoCapture(cam_id)` with MJPG fourcc + configured resolution
  - Warms up (5 frame discards, same as current recorder)
  - Loops: `cap.read()` → write to shared buffer → if recording, also `writer.write(frame)`
  - Recording start/stop controlled by `threading.Event` flags (no thread restart needed)

- Shared buffer per camera: a `threading.Lock`-protected single frame (numpy array). The capture thread overwrites it every frame. The preview reader grabs whatever's there. No queue, no accumulation, no RAM growth. Latest frame only.

- Frame-count sync: when recording starts, each thread targets `duration_sec * fps` frames. A shared `threading.Event` signals all threads to start writing simultaneously (same pattern as `record_calibration.py`'s `start_event`).

### File: `core/blender_preview.py`

The Blender-side glue. Depends on `bpy`. Talks to `CameraManager` on one side and Blender's image system on the other.

```python
class BlenderCameraPreview:
    """Bridges CameraManager frames into Blender Image datablocks."""

    def __init__(self, camera_manager: CameraManager, preview_width=320, preview_height=240):
        ...

    def start(self):
        """Create Blender Image datablocks, register timer callback."""

    def stop(self):
        """Unregister timer, remove Image datablocks."""

    def _timer_tick(self) -> float:
        """Called by bpy.app.timers. Grabs latest frames, updates Images.
        Returns 0.1 (= call me again in 100ms = ~10 Hz preview refresh)."""
```

**How frames get into Blender:**

1. Timer fires (~10 Hz)
2. Calls `camera_manager.get_latest_frames()` — gets a dict of numpy arrays
3. For each camera: downscale frame to preview size with `cv2.resize()`
4. Convert BGR (OpenCV) → RGBA (Blender): `cv2.cvtColor()` + add alpha channel
5. Flatten to float32 array (Blender wants pixels as `[r, g, b, a, r, g, b, a, ...]` floats 0.0–1.0)
6. Write to `bpy.data.images["PPParty_Cam_N"].pixels[:]`
7. Tag image for update

**Preview resolution:** 320×240 is plenty for a thumbnail. At 10 Hz refresh with 4 cameras, that's ~4 × 320 × 240 × 4 bytes × 10/sec ≈ 12 MB/sec of pixel data. Negligible.

### File: `operators/camera_ops.py`

Blender operators — thin wrappers that call into the core modules.

```
PPPARTY_OT_detect_cameras    — Scan for available webcams, report to UI
PPPARTY_OT_start_preview     — Open cameras + start live preview
PPPARTY_OT_stop_preview      — Stop preview + release cameras
PPPARTY_OT_start_recording   — Begin recording (preview stays on)
PPPARTY_OT_stop_recording    — Stop recording (preview stays on)
```

### File: `ui/camera_panel.py`

The N-panel section showing camera previews + controls.

```
┌─────────────────────────────────┐
│  PPParty > Cameras              │
│                                 │
│  ┌──────────┐  ┌──────────┐    │
│  │  Cam 0   │  │  Cam 1   │    │
│  │  (image) │  │  (image) │    │
│  └──────────┘  └──────────┘    │
│  ┌──────────┐  ┌──────────┐    │
│  │  Cam 2   │  │  Cam 3   │    │
│  │  (image) │  │  (image) │    │
│  └──────────┘  └──────────┘    │
│                                 │
│  Status: 4/4 cameras connected │
│                                 │
│  [ Start Preview ]              │
│  [ ● Record ]  Duration: 60s   │
│                                 │
│  Frames: 0 / 1800              │
│  Elapsed: 0.0s                  │
└─────────────────────────────────┘
```

Images displayed using `layout.template_icon(icon_value=img.preview.icon_id, scale=10)` or by splitting a row into two columns each with `layout.template_preview(source=img)`.

---

## How This Fits Into the Full Pipeline

```
Step 1: PREVIEW (Camera Manager)
  Student opens Blender → PPParty panel → "Start Preview"
  → 4 live camera views appear in the panel
  → Student checks framing, adjusts cameras if needed

Step 2: CALIBRATE (separate operator, future work)
  Student clicks "Calibrate" → Camera Manager records a calibration take
  → Anipose processes the ChArUco board footage → calibration TOML saved
  → Accuracy badge shown (green/yellow/red)

Step 3: RECORD (Camera Manager)
  Student clicks "Record" → preview stays live, recording starts
  → Red indicator + frame counter in panel
  → Student performs → clicks "Stop" (or recording auto-stops at duration limit)
  → 4 synchronized .mp4 files saved to MOCAP_TAKES/

Step 4: PROCESS (FreeMoCap headless, future work)
  Student clicks "Process" → FreeMoCap runs MediaPipe + triangulation
  → Progress bar → .npy output

Step 5: IMPORT (ajc27 bridge, future work)
  Student clicks "Import" → ajc27 addon loads .npy → armature in scene

Step 6: TIDY + BAKE (future operators)
  Student clicks "Tidy" → raw data hidden in collection
  Student clicks "Bake" → constraints → keyframes on armature
```

**The Camera Manager is Steps 1–3.** It's the foundation everything else builds on.

---

## Build Order (Step by Step)

### Step 1: `core/camera_manager.py` — the engine (no Blender dependency)

Port the proven logic from `record_calibration.py` into a reusable class. Add:
- Auto-detect backend (remove hardcoded `CAP_AVFOUNDATION`)
- Shared frame buffers for preview
- Start/stop recording without restarting camera threads
- Camera detection (enumerate available cameras)

**Test:** run standalone from Terminal — open 4 cams, preview frames to a window (`cv2.imshow`), record 10 seconds, verify identical frame counts.

### Step 2: `core/blender_preview.py` — the bridge

Timer-based frame pusher. Creates Blender Image datablocks, updates them at ~10 Hz.

**Test:** install as minimal addon — just preview, no recording UI yet. Open Blender, run from console: `from ppparty.core.camera_manager import CameraManager; ...` etc. Verify 4 images appear in Blender's Image Editor.

### Step 3: `operators/camera_ops.py` + `ui/camera_panel.py` — the buttons

Wire up the N-panel with Start Preview / Stop Preview / Record / Stop Record.

**Test:** full addon install. Student workflow: open Blender → PPParty tab → Start Preview → see cameras → Record → perform → Stop → verify files.

### Step 4: Camera detection operator

"Detect Cameras" button that scans for available webcams and lets the student pick which 4 to use (handles the case where the MacBook's built-in camera shows up as index 0 and shifts the externals).

### Step 5: Integration with calibration + recording workflows

Wire the Camera Manager's recording output into the calibration and processing operators (when those get built).

---

## What We Keep From `record_calibration.py`

Everything that works:
- One thread per camera (proven stable)
- `cv2.VideoWriter` with `mp4v` fourcc for output
- Frame-count-bounded recording (not time-bounded) — guarantees sync
- MJPG fourcc on capture (better bandwidth than raw)
- 5-frame warmup discard (auto-exposure settle)
- `threading.Event` for synchronized recording start

What we change:
- Remove hardcoded `CAP_AVFOUNDATION` → auto-detect
- Remove hardcoded camera indices → detect + user-select
- Add shared frame buffer for preview
- Add start/stop recording without restarting threads
- Wrap in a class instead of a standalone script

---

## Risks

1. **Camera permissions on macOS.** Each process that opens a camera needs Camera permission in System Settings. Blender may need to be granted access separately from Terminal. One-time setup, but could confuse a student on first run.
   → **Mitigation:** Setup guide + "Camera access denied" error handling with a helpful message.

2. **USB bandwidth with 4 cameras.** Already solved at BASEMENT (2 on hub + 2 on adapters). The Camera Manager doesn't change this — same physical constraint.
   → **Mitigation:** Setup guide (Bug #2 from BUGS_AND_BACKLOG).

3. **OpenCV not installed in Blender's Python.** Blender ships its own Python. OpenCV needs to be installed into it (`pip install opencv-contrib-python` in Blender's Python).
   → **Mitigation:** One-time setup step. Could add an auto-installer operator later.

4. **Preview frame rate affecting recording.** If the main thread's timer callback takes too long processing preview frames, it could theoretically affect Blender's responsiveness.
   → **Mitigation:** Preview is small (320×240) and runs at 10 Hz. If it's still too heavy, drop to 5 Hz or skip frames.

---

## Sources / Prior Art

- `MOCAP_CALIBRATION_FILES/record_calibration.py` — our proven recorder (May 9, 2026)
- `BUGS_AND_BACKLOG.md` — the 22 bugs from BASEMENT testing (May 9 + May 12, 2026)
- `ARCHITECTURE.md` — the full pipeline design (May 6, 2026)
- SkellyCam source (`R&D/skellycam/`) — reference for what NOT to over-engineer
- V2 receiver pattern (`PPPARTY_V2/core/receiver.py`) — timer-based Blender integration pattern
