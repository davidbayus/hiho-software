# HIHO MOCAP — Headless FreeMoCap Build (Design)

**Date:** 2026-06-01
**Status:** Design, pre-code. For David's review at the rig before we write code.
**Goal (David's words):** "A new build of HIHO MOCAP that runs the recording through headless FreeMoCap, and the processing, and exports a skelly directly into the Blender scene." Result: the addon runs on current Blender (5.1+), not just 5.0.
**Builds on:** `HIHO_MOCAP_WRAPPER_ARCHITECTURE.md` §11 (Option B). This is the concrete, buildable version of that idea.

---

## 0. Plain-English summary

Today the addon does everything inside Blender, which forces Blender 5.0, because the motion-capture libraries need an old Python. This build moves the two heavy steps (running the cameras, solving the mocap) OUT to a separate program (your existing FreeMoCap environment) and keeps only the skelly-building inside Blender. The skelly-building is already pure Blender code, so it runs on any modern Blender.

Net result: Blender floats to current, the addon shrinks from ~287 MB to a few MB, and the version-sensitive stuff lives in the external program where it belongs.

---

## 1. Why this is a smaller build than it sounds

I read the current code. The pipeline already splits cleanly:

- **Heavy, version-sensitive (needs the old-Python libraries):** recording (`core/camera_manager.py`, OpenCV) and processing (`core/freemocap_runner.py`, FreeMoCap's `process_recording_folder`).
- **Light, already version-free:** the skelly build. `core/loader.py` only reads `output_data/*.npy` with numpy (which Blender ships) and builds the rig with pure `bpy`. No FreeMoCap import anywhere in it.

So the seam is already there. We cut along it: heavy steps go external, the skelly build stays and **does not need to change**.

---

## 2. Architecture

Three parts:

1. **External recorder** — 4 cameras to 4 mp4s on disk. Runs in your FreeMoCap environment. This is the logic in your proven `record_calibration.py` (and its in-Blender port `core/camera_manager.py`), relocated to run outside Blender.
2. **External processor** — mp4s + calibration to `output_data/*.npy`. Runs in your FreeMoCap environment. This is FreeMoCap's `process_recording_folder`, the same call `freemocap_runner.py` makes today, just run as a standalone script instead of a thread inside Blender.
3. **In-Blender skelly build** — `output_data/*.npy` to the 63-bone skelly in your scene. Unchanged. Runs on current Blender.

Blender orchestrates parts 1 and 2 by launching them as subprocesses, then reads their output for part 3.

```
 BLENDER (current version)                 EXTERNAL FreeMoCap env (frozen)
 ┌─────────────────────────┐               ┌──────────────────────────────┐
 │ Record button  ─────────┼─ subprocess ─►│ recorder  → Camera_0..3.mp4   │
 │ Process button ─────────┼─ subprocess ─►│ FreeMoCap → output_data/*.npy │
 │ skelly build  ◄─────────┼─ reads files ─┤ (writes to the take folder)   │
 │ (loader + build_rig)    │               └──────────────────────────────┘
 └─────────────────────────┘
```

---

## 3. The external environment

Your proven BASEMENT `freemocap-env` (conda; FreeMoCap 1.8.2; opencv-contrib 4.8.1.78; aniposelib; the anipose patch at `freemocap_anipose.py:2089`). It already drives the 4-cam rig. We point Blender at it. We do not rebuild it.

Note: per the install notes that env is Python 3.12, not 3.11. That is fine. The whole point of this build is that Blender no longer cares what Python the external program uses.

---

## 4. The seam (the one real design decision)

**Subprocess + file handoff + stdout progress.** Concretely:

- A new module, `core/external_runner.py`, launches `<env_python> <script> <args>` with `subprocess.Popen`, reads its stdout line by line, and exposes `progress_pct / current_stage / is_done / error / output_path`, the exact same surface `FreeMocapRunner` exposes today.
- Because the surface is identical, `operators/process.py` barely changes: it already polls a runner via `bpy.app.timers` and drives the progress bar. We swap the thread-runner for the subprocess-runner.
- Progress comes from the external process printing stage lines to stdout; we reuse the existing `STAGES` substring matching to turn those lines into a percentage.
- Done = process exits 0 and `output_data/` exists. Error = nonzero exit; we surface stderr in the panel.

**Rejected for now:** the HTTP / websocket server (the old "v3.0 home-rolled server"). Same concept, far more code. Subprocess is the plain version that works today. The server stays a later optimization.

---

## 5. Reused vs new

| Piece | Status |
|---|---|
| `core/loader.py`, `build_rig.py`, `bind_to_rig.py`, `enforce_rigid_bodies.py`, `output_rig.py`, `topology.py`, `virtual_landmarks.py` | REUSED unchanged (skelly build, already pure bpy + numpy) |
| `operators/spawn_rig.py` | REUSED, basically unchanged |
| `operators/process.py` | LIGHT EDIT (point at the subprocess runner instead of the thread runner) |
| `operators/record.py` | EDIT (kick the external recorder instead of the in-Blender camera manager) |
| `core/freemocap_runner.py` | RETIRED in-Blender; its `process_recording_folder` call moves into the external processor script |
| `core/camera_manager.py` | Its recording logic becomes the external recorder script |
| `core/external_runner.py` | NEW (the subprocess seam) |
| external scripts (`record.py`, `process.py` that run in the env) | NEW (thin; mostly lifted from existing code) |
| `blender_manifest.toml` wheels list | SHRINK to near-zero (drop freemocap, opencv, mediapipe, scipy, numba, jax, etc.) |

---

## 6. Build sequence (one change at a time, test after each)

1. **`external_runner.py` seam** — subprocess launch + stdout read + poll. Test with a trivial echo script.
2. **External processor + wire Process** — standalone script that runs `process_recording_folder` in the env. *Test: process an existing take folder, confirm the skelly builds.* No cameras needed; testable on any machine that has an existing take + calibration.
3. **External recorder + wire Record** — standalone recorder (from `record_calibration.py` / `camera_manager.py`). *Test: 4-cam record.* BASEMENT only.
4. **Shrink the addon** — drop the heavy wheels from the manifest, set the Blender version target to current, rebuild the zip (now a few MB). Anywhere.
5. **Confirm skelly build on current Blender** — see §8. Anywhere with an existing take.

Steps 1, 2, 5 do not need the cameras. Step 3 does.

---

## 7. Open knobs for David

- **Path to the external env's Python:** a field in the panel with a file picker (per your "operators that act on a file need a picker" rule), defaulting to the known conda env path. Survives Blender restarts.
- **Where the external scripts live:** recommend copying the recorder/processor scripts into the addon so they travel with it, rather than referencing the fragile `~/Desktop/record_calibration.py`.
- **Drop the heavy wheels now or after the external path is proven?** Recommend after (Step 4), so we only change one thing at a time.

---

## 8. The one fact to confirm at the rig

Does the skelly-build code run on Blender 5.2's API? Blender's animation API shifted in the 5.x line (slotted actions: `action.fcurves` moved). `build_rig.py` / the keyframing may need a small adaptation. This is the only in-Blender compatibility risk. The heavy-library and Python-version question is mooted by going headless. Quick check: build a skelly from an existing take's `output_data` in 5.2 and see if it errors.

---

## 9. What this does NOT change

- The mocap math / pipeline (still FreeMoCap, still 1:1).
- The 63-bone skelly topology.
- The calibration workflow (still an external TOML, still your lazy-Susan technique; there is still no in-addon "calibrate" button, that gap is unchanged).
- The known open issues (wrist flip, position jitter) ride along; out of scope here.

---

## 10. Logistics to settle first (do not assume)

- **Which machine are we building on today, and is `SOFTWARE/` synced to the BASEMENT laptop?** I am reading the source on the desktop. Rig work happens on the laptop. If `SOFTWARE/` is not shared between them, we need a way to get the new build onto the laptop. This shapes how we work today.
- **Where does a test take live** for Steps 2 and 5 (the no-camera tests)? The May 9 recordings are noted as laptop-only.
