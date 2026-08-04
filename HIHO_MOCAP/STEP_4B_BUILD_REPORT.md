# Step 4b — Buildable Zip Report

**Date:** 2026-05-23. **Audience:** David. **Predecessor:** STEP_4A_SMOKE_TEST.md. **Successor:** Step 4c (install in Blender, verify `import freemocap`).

---

## Verdict

# **PASS**

Buildable addon zip exists at `SOFTWARE/HIHO_MOCAP_v0.1.0-step4.zip`. Blender's own extension validator accepts both the in-tree manifest and the final zip. Ready to install.

---

## Phase 1 — Vendor FreeMoCap source

Copied `R&D/freemocap-main/freemocap/` into `SOFTWARE/HIHO_MOCAP/vendor/freemocap/` via `rsync` with exclusions for `gui/`, `__pycache__/`, `.pyc`, `.pyo`, `.idea/`.

- **Vendored size:** 4.1 MB (down from 5.0 MB upstream — the 900 KB delta is the Qt GUI tree).
- **Top-level kept:** `__init__.py`, `__main__.py`, `assets/`, `core_processes/`, `data_layer/`, `diagnostics/`, `system/`, `tests/`, `utilities/`.
- **Top-level dropped:** `gui/` (the entire Qt window tree, never touched by the processing pipeline functions we call).
- **`tests/` kept on purpose** — `recording_info_model.py` reaches into `tests/test_image_tracking_data_shape.py` for constants (poor upstream hygiene). Stripping that is a v1.1 cleanup task.

## Phase 2 — MediaPipe model files

Investigated the `mediapipe-0.10.14` wheel and confirmed: **skellytracker uses the legacy `mp.solutions.holistic` API** (not the new MediaPipe Tasks API), so `.tflite` files in the legacy bucket are what we need — `.task` files from `mediapipe-models/...` would be irrelevant.

Most `.tflite` files ARE already inside the wheel under `mediapipe/modules/`, including:
- `pose_landmark_full.tflite` (complexity=1, default in legacy holistic)
- `pose_detection.tflite`, `hand_landmark_full.tflite`, `hand_landmark_lite.tflite`, `face_landmark.tflite`, `face_landmark_with_attention.tflite`, `face_detection_*.tflite`, `palm_detection_*.tflite`, `holistic_landmark/hand_recrop.tflite`, etc.

**But two are NOT in the wheel and ARE required:**
- `pose_landmark_heavy.tflite` (26.4 MB) — needed because skellytracker defaults to `model_complexity=2`, which holistic.py downloads on demand from `https://storage.googleapis.com/mediapipe-assets/pose_landmark_heavy.tflite`.
- `pose_landmark_lite.tflite` (2.7 MB) — bundled defensively in case `model_complexity` ever becomes 0.

Both downloaded into `SOFTWARE/HIHO_MOCAP/mediapipe_models/` (29 MB total). Step 5's operator code will need a small "if the file's not in the mediapipe install dir, copy from our bundle" snippet before instantiating the holistic tracker. (The legacy API checks `os.path.exists(model_path)` before downloading — if we put the file at the right path, no internet needed.)

**Net: most of the offline-first promise is kept by the wheel itself. We only added 29 MB to fill the heavy/lite gap.**

## Phase 3 — `blender_manifest.toml`

Written at `SOFTWARE/HIHO_MOCAP/blender_manifest.toml`. Validated two ways:
1. `python -c "import tomllib; tomllib.load(...)"` parses without error and confirms all required keys present.
2. `Blender --command extension validate .` returns `Success parsing TOML`.

Headline values:
- `schema_version = "1.0.0"`
- `id = "hiho_mocap"`, `version = "0.1.0"`, `name = "HIHO MOCAP"`
- `tagline = "Multi-camera markerless mocap bundled inside Blender"` (52 chars, no terminal punctuation — Blender enforces both)
- `type = "add-on"`, `tags = ["Animation", "Rigging", "Tracking"]`
- `blender_version_min = "5.0.0"` (matches the Blender 5.0 pin)
- `license = ["SPDX:AGPL-3.0-or-later"]` (inherited from FreeMoCap)
- `platforms = ["macos-arm64"]` (single platform until Step 5 ships cross-platform wheels)
- `wheels = [...]` lists all 68 `.whl` files in `wheels/`, cross-checked against disk — zero missing, zero extras.
- `[permissions]` declares `files`, `network`, `camera` with explanations all under Blender's 64-char limit.
- `[build] paths_exclude_pattern` lists the heavy folders + docs so a future `Blender --command extension build` produces the same trimmed zip.

**Maintainer email is a placeholder** (`hiho-experimental-animation-club@example.invalid`) with a `# TODO` comment. David should swap it before any extensions.blender.org submission.

## Phase 4 — `__init__.py` adjustments

Two non-destructive additions:
1. **`sys.path` insert at the top** (above `bl_info`) — adds `vendor/` to Python's import path so `import freemocap` resolves to the vendored copy.
2. **Register-time probe** (inside `register()`, after the class registration and property assignment) — wrapped in `try/except`, prints `HIHO MOCAP: bundled FreeMoCap ... loaded.` on success or `WARNING — bundled FreeMoCap failed to import: ...` on failure. Never crashes the addon on import error — Step 4c needs to see the message in console.

Existing operator/UI imports untouched. `unregister()` untouched.

## Phase 5 — Zip build

Built from `SOFTWARE/`, not from inside `HIHO_MOCAP/` (per `feedback_zip_build_from_software_dir.md`).

- **Final file:** `SOFTWARE/HIHO_MOCAP_v0.1.0-step4.zip`
- **Size:** **281 MB** (consistent with the audit's ~270 MB projection + 29 MB mediapipe weights + small vendor source)
- **Wheel count inside zip:** 68 (matches manifest exactly)
- **Manifest path inside zip:** `HIHO_MOCAP/blender_manifest.toml` — correct, this is where Blender looks.
- **Exclusions applied:** `.DS_Store`, `__pycache__/`, `MOCAP_TAKES/`, `MOCAP_CALIBRATION_FILES/`, `HIHO_MOCAP_LIBRARY/`, and the ten `.md` docs (`STEP_4_*.md`, `STEP_4A_*.md`, `STEP_4B_*.md`, `BUGS_AND_BACKLOG.md`, `V2_HOMEROLLED_RESEARCH.md`, `HIHO_MOCAP_v1_PLAN.md`, `STAGE_3_DESIGN.md`, `ARCHITECTURE.md`, `CAMERA_MANAGER_DESIGN.md`, `README.md`).

## Phase 6 — Pre-install sanity check

Extracted the built zip to a temp dir and verified:

```
OK manifest present
OK __init__.py present
OK wheels dir present
OK vendored freemocap present
OK mediapipe_models present
OK pose_landmark_heavy.tflite present
OK operators present
OK ui present
OK core present
OK properties.py present
Wheel count in zip:       68
```

Sanity confirmed: zip contains only what Blender needs to run the addon. No recordings, no docs, no junk.

**Plus** ran `Blender --command extension validate HIHO_MOCAP_v0.1.0-step4.zip` against the final zip and got `Success parsing TOML`.

## Deliverables

1. `SOFTWARE/HIHO_MOCAP/vendor/freemocap/` — vendored source, gui/ excluded (4.1 MB).
2. `SOFTWARE/HIHO_MOCAP/mediapipe_models/` — `pose_landmark_heavy.tflite` + `pose_landmark_lite.tflite` (29 MB total). Most other MediaPipe weights already in the wheel.
3. `SOFTWARE/HIHO_MOCAP/blender_manifest.toml` — valid manifest, all 68 wheels listed, validated by Blender.
4. `SOFTWARE/HIHO_MOCAP/__init__.py` — updated with `sys.path` insert + register-time probe.
5. `SOFTWARE/HIHO_MOCAP_v0.1.0-step4.zip` — 281 MB buildable addon zip.
6. This report (`STEP_4B_BUILD_REPORT.md`).

## What Step 4c needs to do

Install via Blender's Extensions panel (Edit > Preferences > Extensions > Install from Disk > pick the zip). Enable the "HIHO MOCAP" entry. Watch Blender's system console for either:
- `HIHO MOCAP: bundled FreeMoCap (no __version__) loaded.` → success path, move to Step 5.
- `HIHO MOCAP: WARNING — bundled FreeMoCap failed to import: ...` → Step 4c writes a quick failure analysis and we iterate.

## Hard rules respected

- Operators / UI / core / properties untouched (Step 5's job).
- No FreeMoCap source modifications (only copies).
- Addon NOT installed in Blender (that's Step 4c).
- `wheels/` untouched.
- Zip built from `SOFTWARE/`, not from inside `HIHO_MOCAP/`.
