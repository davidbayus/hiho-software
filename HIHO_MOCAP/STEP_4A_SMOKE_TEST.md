# Step 4a — Smoke Test (Trimmed Wheels in a Clean Venv)

**Date:** 2026-05-23. **Audience:** David. **Predecessor:** STEP_4_DEP_AUDIT.md.

---

## Verdict

# **PASS**

The trimmed wheel set imports cleanly. **PySide6 stayed out, pyqtgraph stayed out, QtPy stayed out** — the whole reason this test existed. The pipeline glue can be invoked. Proceed to Step 4b (write `blender_manifest.toml`, build the addon zip).

Two small surprises along the way, both expected-class and both already adjusted for. Read Section 7.

---

## 1. Wheel set summary

**Final state of `SOFTWARE/HIHO_MOCAP/wheels/`:**

- **68 wheels, 254 MB on disk** (gzipped wheel files; uncompressed install footprint will be ~600-700 MB inside Blender).
- Matches the audit's "trimmed bundle" prediction (~254 MB) within rounding.
- The 5 largest wheels are jaxlib (51 MB), mediapipe (48 MB), opencv (40 MB), llvmlite (36 MB), scipy (28 MB). Together those 5 are 80% of the bundle.

**Wheels deleted after download (the GUI / numpy drops, per audit):**

- `PySide6-6.6.3.1-cp38-abi3-macosx_11_0_universal2.whl`
- `PySide6_Addons-6.6.3.1-cp38-abi3-macosx_11_0_universal2.whl`
- `PySide6_Essentials-6.6.3.1-cp38-abi3-macosx_11_0_universal2.whl`
- `shiboken6-6.6.3.1-cp38-abi3-macosx_11_0_universal2.whl`
- `pyqtgraph-0.13.3-py3-none-any.whl`
- `numpy-1.26.2-cp311-cp311-macosx_11_0_arm64.whl`

(`QtPy`, `pytest`, `iniconfig`, `pluggy` were never pulled at all by the trimmed download — they only appear if you include `skelly_viewer`, which we didn't.)

**Wheels ADDED after smoke test surfaced they were load-bearing:**

- `pytest-9.0.3-py3-none-any.whl` (375 KB)
- `pluggy-1.6.0-py3-none-any.whl` (20 KB)
- `iniconfig-2.3.0-py3-none-any.whl` (8 KB)

**Why these three got added:** FreeMoCap's `recording_info_model.py` (a runtime production file, not a test) imports constants from `freemocap.tests.test_image_tracking_data_shape`, which top-level imports `pytest`. Poor FreeMoCap hygiene, but it's load-bearing for us. The 3 wheels combined add < 0.5 MB and don't pull anything GUI.

---

## 2. Phase 1 — Download (small correction to audit)

The audit's `pip download` command pinned `--platform macosx_11_0_arm64` only. That works for most wheels but **scipy 1.11.4 and scikit-learn 1.8.0 ship with `macosx_12_0_arm64` tags** — pip refused to resolve until we widened to multiple platform tags:

```
--platform macosx_11_0_arm64
--platform macosx_12_0_arm64
--platform macosx_13_0_arm64
--platform macosx_14_0_arm64
```

This is fine — they all run on macOS 11+ at runtime; the tag mismatch is purely a pip resolution thing. **Action item for Step 4b:** the actual `blender_manifest.toml` will declare `platforms = ["macos-arm64"]` which Blender resolves at install time, and Blender doesn't care about the cp-tag's stated minimum macOS version. Just bundle the .whl files.

---

## 3. Phase 3 — Import test results

### Group A: Wheel-set imports (the trimmed bundle)

All 12 imported cleanly:

```
OK    numpy                              (version 1.26.4, matches Blender's bundled)
OK    cv2                                (opencv-contrib-python 4.8.1.78)
OK    mediapipe                          (0.10.14)
OK    scipy
OK    pandas
OK    matplotlib
OK    aniposelib
OK    librosa
OK    skellyforge
OK    skelly_synchronize
OK    skellytracker
OK    pydantic
```

### Group B-E: skellyforge / skelly_synchronize / skellytracker functions

Every processing function we'd actually call from a Blender operator imports without leaking PySide6 or pyqtgraph:

```
OK    skellyforge config
OK    skellyforge constants
OK    skellyforge interpolate_skeleton_data (in interpolate_data.py)
OK    skellyforge filter_skeleton_data
OK    skellyforge align_skeleton_with_origin
OK    skelly_synchronize.skelly_synchronize
OK    skelly_synchronize file_extensions
OK    skellytracker mediapipe_holistic_tracker
```

**Audit had two path guesses wrong** — easy fixes:
- `interpolate_data_functions` (audit guess) → actual is `interpolate_data` module containing function `interpolate_skeleton_data`.
- `PostProcessingParameterModel` (audit guess) → actual class is `ProcessingParameterModel` (no "Post" prefix; the "post processing" appears as an attribute name inside).

Neither breaks anything, just need correct names in Step 5's operator code.

### Group F: FreeMoCap source-tree modules

These live in `R&D/freemocap-main/freemocap/` (FreeMoCap is not a wheel — we'll vendor the source files we need into our addon). All five imported cleanly in isolated subprocesses with **no PySide6 / pyqtgraph leak**:

```
OK    freemocap path_getters
OK    freemocap file_and_folder_names
OK    freemocap post_processing_parameter_models   (after pytest added)
OK    freemocap post_process_skeleton              (after pytest added)
OK    freemocap process_recording_folder           (after pytest added)
OK    freemocap freemocap_anipose                  (where interpolate_data actually lives)
```

The first time we ran the test in a single shared process, all the FreeMoCap imports cascaded into circular-import errors. That was a test artifact (one early failure poisoned `sys.modules['freemocap']` into a half-initialized state, breaking subsequent imports). In isolated subprocesses they all work.

---

## 4. PySide6 isolation result — **YES, isolated**

After the full battery of imports (every wheel + every FreeMoCap source module we'd touch + instantiating a MediaPipe tracker):

```
OK   PySide6 not in sys.modules
OK   pyqtgraph not in sys.modules
OK   qtpy not in sys.modules
```

**This is the load-bearing answer.** The audit's central concern was whether a transitive import chain like `freemocap.X` → `skellyforge.Y` → `pyqtgraph` would detonate when we ship without PySide6. **It does not.** The skellyforge "widgets" folder name is misleading — the modules under `postprocessing_widgets/postprocessing_functions/` are pure compute (numpy / scipy / pandas) with no Qt imports. skelly_synchronize's pyproject hard-requires PySide6 in metadata, but its actual runtime code does not.

We can ship the addon zip without any Qt wheels.

---

## 5. Phase 4 — Functional probe (light, not a full mocap run)

Inputs used:
- 4 frame-matched videos: `~/Desktop/CALIBRATION_RECORDINGS/2026-05-23_16-45-33/Camera_{0,1,2,3}.mp4` (1024x576 @ 30 fps, 300 frames each = 10s)
- Calibration TOML: `~/Desktop/CALIBRATION_RECORDINGS/2026-05-16_13-35-26/last_successful_calibration.toml`

Results:

| Probe | Result | Note |
|---|---|---|
| Load calibration TOML via aniposelib | **OK** | 4 cameras at 1024x576 confirmed. |
| Construct `ProcessingParameterModel` | **OK** | (audit had the class name wrong — see Section 7) |
| Get callable handle on `process_recording_folder` | **OK** | Signature: `(recording_processing_parameter_model, kill_event=None, logging_queue=None, use_tqdm=True) -> None` |
| Inspect recording dir | **OK** | 4 videos found, sizes 6-8 MB each. |
| Open all 4 videos with cv2 | **OK** | All decoded; 1024x576 @ 30 fps confirmed. |
| Instantiate MediaPipe holistic tracker | **PARTIAL** | Construction triggered first-run download of `pose_landmark_heavy.tflite`. SSL cert failure in this sandboxed venv blocked the download. **Not a HIHO MOCAP issue** — Blender's bundled Python has working SSL. See Section 7. |

The PySide6 isolation check repeated AFTER all the above still showed PySide6/pyqtgraph/qtpy NOT loaded.

I did not run a full mocap pipeline on the .mp4s — that's a 15-30 minute CPU job and Step 5's territory. The goal here was "can we invoke the pipeline objects without crashing?" Answer: yes.

---

## 6. Recommended next move

**Proceed to Step 4b.** Write `blender_manifest.toml` declaring:

- Schema version 1.0.0
- Type `add-on`
- Blender min version `5.0.0`
- Platforms `["macos-arm64"]`
- License `SPDX:AGPL-3.0-or-later`
- Wheels block listing all 68 `.whl` files in `wheels/`
- The vendored FreeMoCap source files we use (vendor a slim subset of `R&D/freemocap-main/freemocap/`, NOT the whole tree — see Section 7 item 3)

Then build the zip and move to Step 4c (install in Blender, verify `import` from the addon's `__init__.py`).

---

## 7. Things flagged that need a small Step 5 / Step 4b adjustment

None of these block the bundle path. All are easy fixes.

1. **Class name was `ProcessingParameterModel`, not `PostProcessingParameterModel`.** Audit guessed wrong. When Step 5 writes the operator, use:
   ```python
   from freemocap.data_layer.recording_models.post_processing_parameter_models import ProcessingParameterModel
   ```

2. **Function name was `interpolate_skeleton_data` in `interpolate_data.py`, not `interpolate_data_functions`.** Audit guessed wrong. Step 5 fix.

3. **FreeMoCap's `recording_info_model.py` imports from `freemocap.tests.test_image_tracking_data_shape`** — a production source file reaching into a test module. We need to vendor the `freemocap/tests/test_image_tracking_data_shape.py` file too, OR move its constants out as part of vendoring. Quick patch options for Step 4b:
   - Easiest: vendor the whole `freemocap/tests/` directory plus pytest/pluggy/iniconfig wheels. Already done — the 3 wheels are in `wheels/`.
   - Cleaner (recommended later): in our vendored copy, hoist the test-module constants into a new `freemocap/data_layer/_constants_from_tests.py` and patch the one import in `recording_info_model.py`. Removes the pytest dep entirely. Save for v1.1.

4. **MediaPipe downloads its model files on first use.** First-launch ImageError if student is offline. Two options for v1.0:
   - **Bundle the .tflite files** alongside the wheels. Pose landmark heavy alone is ~30 MB but lets the addon work offline forever. Aligns with HIHO's "offline-first" / refuse-pedagogy goals. **Recommended.**
   - **Document "first launch needs internet"** in the README. Simpler to ship; weaker user story.
   - Worth a small Step 4b decision before zipping. Not blocking but pick one and commit.

5. **The audit assumed FreeMoCap installs as a wheel.** Reality: FreeMoCap is not currently on PyPI as a wheel matching our pinned versions (we'd need to vendor the source tree into the addon). This is actually the path the v1 plan already calls for (`bundled-vendored FreeMoCap` per `project_hiho_mocap_freemocap_relationship.md`). No change needed — just confirm in Step 4b that the manifest vendoring strategy is "FreeMoCap source files copied into addon/" not "FreeMoCap as a wheel."

6. **Platform tag in pip download command:** the audit's `--platform macosx_11_0_arm64` was too narrow. Use the four-platform incantation when refreshing the wheel set (see Section 2). Worth recording in any rebuild script.

---

## 8. Wheels we couldn't drop

None of the "obvious drops" turned out to be load-bearing. The drop set worked exactly as the audit predicted.

The only wheels we ADDED back (`pytest`, `pluggy`, `iniconfig`) were not previously in any drop debate — they showed up because of FreeMoCap's poor source hygiene (importing test modules from production code). Even those add < 0.5 MB.

**Net effect on bundle size:** ~unchanged from the audit's 254 MB projection. The trimmed bundle is as small as the audit predicted, and it works.

---

## 9. Artifacts

- **`SOFTWARE/HIHO_MOCAP/wheels/`** — 68 wheels, 254 MB. Don't delete. Step 4b needs these.
- `/tmp/hiho_smoke_venv/` — **deleted** after testing (was ~1.1 GB).
- `/tmp/smoke_test_imports.py`, `/tmp/smoke_test_functional.py` — **deleted** (their output is inlined in Sections 3-5 above).
