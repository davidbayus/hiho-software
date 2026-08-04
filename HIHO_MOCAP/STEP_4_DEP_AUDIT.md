# Step 4 — Dependency Audit (Bundle vs. Fallback)

**Goal:** Decide whether HIHO MOCAP v1.0 can ship FreeMoCap's pipeline as bundled wheels inside a single Blender Extension `.zip`, or whether we have to fall back to a "Run install script" operator at first enable.

**Audience:** David. **Date:** 2026-05-23. **Scope:** macOS arm64 / Python 3.11.13 / Blender 5.0 / numpy 1.26.4 (Blender's bundled). **Method:** read-only — pip `--dry-run --report` + wheel header inspection. Nothing installed.

---

## Headline (read this if nothing else)

**Recommendation: bundle is viable, with caveats.**

- **All 87 wheels in the full resolution exist for cp311 macOS arm64.** Zero source-only deps, zero missing wheels. Pip resolved cleanly in one pass.
- **No package requires numpy 2.** Every numpy constraint in the tree is satisfied by Blender's bundled 1.26.4. No landmines.
- **Full bundle as FreeMoCap declares it = ~810 MB.** Most of that is GUI (PySide6 alone is ~380 MB).
- **Bundle trimmed to capture + processing only = ~270 MB** (drop PySide6/Qt + the entire `skellycam` + `skelly_viewer` GUI deps + torch/ultralytics from `skellytracker[all]`).
- **The "drop" set is unusually clean.** GUI deps are isolated to `gui/qt/` and the four FreeMoCap functions we'd call from a Blender operator (`interpolate_data`, `default_settings`, `synchronize_videos_from_audio`, `process_folder_of_videos`) do NOT import PySide6 at all.

**Biggest landmines:**
1. `skelly_*` packages hard-pin `numpy==1.26.2` exactly. Blender 5.0 ships 1.26.4. Pip would refuse this; Blender Extensions doesn't run pip's resolver at install (it just extracts whatever wheels we list), so runtime is fine. But this means we cannot use vanilla `pip install` inside Blender as a fallback either.
2. `aniposelib` declares unbounded `numpy` and `opencv-contrib-python`. If we ever let pip resolve it alone, it grabs numpy 2.4 + opencv 4.13 — co-pin it with the others or it goes off the rails.
3. We have to MANUALLY MAINTAIN the wheels list — Blender does not auto-resolve transitive deps. If we drop PySide6 and skelly_synchronize ever changes its imports, an `ImportError` lands on a student. There's no install-time safety net.

---

## Section 1 — Method, briefly

1. Read FreeMoCap's pyproject.toml (the 15 direct deps) and the uv.lock that ships with it (167 resolved packages including dev tools).
2. Ran `pip install --dry-run --report` against Blender 5.0's bundled Python 3.11.13 for the FULL set of direct deps, then again for the TRIMMED set (no GUI, no `[all]` extras on skellytracker).
3. Cross-referenced every wheel against the PyPI JSON API to confirm wheel availability for `cp311-*macosx*arm64*` and to collect exact byte sizes.
4. Greped FreeMoCap's source tree to confirm which deps are GUI-only and which are core to the capture/processing pipeline we actually need.
5. Pulled and unzipped the four `skelly_*` wheels to inspect actual module-level imports inside the functions FreeMoCap calls.

All scratch artifacts live in `/tmp/wheel_dryrun/` (the pip reports, the unzipped wheel inspections, the sizes JSON).

---

## Section 2 — Drop set (confirmed droppable, with evidence)

These are in FreeMoCap because Mathis ships a standalone Qt GUI. Inside a Blender addon, Blender's panels do the UI.

| Drop | Why droppable | Evidence (path inside `R&D/freemocap-main/`) |
|---|---|---|
| `PySide6` (+ `_Addons`, `_Essentials`, `shiboken6`) | Only imported by the Qt GUI layer. | `grep -rl 'PySide6' freemocap/` returns 30+ files, ALL under `freemocap/gui/qt/`. No non-GUI imports. |
| `QtPy` | Pulled by pandas as an optional. Pandas only uses it for its DataFrame HTML repr in Jupyter. We don't need DataFrame.\_repr\_html\_ inside Blender. | Indirect via pandas; not imported by FreeMoCap code. |
| `pyqtgraph` | Imported only by skellyforge's `postprocessing_widgets/`. FreeMoCap imports skellyforge's NON-widget modules (`config`, `constants`, `postprocessing_functions`). | `skellyforge/freemocap_utils/postprocessing_widgets/*.py` use pyqtgraph; the four `postprocessing_functions/*.py` files we actually need do not. |
| `ipykernel` | NOT imported anywhere in `freemocap/`. Only relevant as runtime for the Jupyter notebook widget in their Qt GUI. | `grep -rl 'ipykernel' freemocap/` returns no hits. |
| `libsass` | Only used by `freemocap/gui/qt/style_sheet/compile_scss_to_css.py` to compile Qt stylesheet CSS at startup. | Single file, GUI-only. |
| `plotly` | Used by `freemocap/diagnostics/calibration/generate_calibration_report.py` (a one-off diagnostic report generator, not capture pipeline) and inside two `freemocap_template.ipynb` Jupyter notebooks. | Two non-pipeline source files. |
| `skellycam` | Imported only by `freemocap/gui/qt/widgets/...` for the live camera preview widget. We capture inside Blender or via our own thin recorder. | `grep -rn 'skellycam' freemocap/` returns 20 hits, all under `gui/qt/`. |
| `skelly_viewer` | Imported only by `freemocap/gui/qt/main_window/freemocap_main_window.py` for the 3D playback viewer. We view inside Blender's viewport. | One non-commented import, in the GUI main window. |
| `skellytracker[all]` extras: `torch`, `torchvision`, `ultralytics`, `ultralytics-thop`, `opencv-python` (4.11), `sympy` | The `[all]` extra enables YOLO + torch trackers. FreeMoCap's default pipeline is MediaPipe, and `skellytracker/__init__.py` uses `try/except ModuleNotFoundError` for the optional trackers. | `process_folder_of_videos.py` graceful-imports yolo/openpose/mmpose. Install `skellytracker[mediapipe]` only. |

**Combined savings from drop set: ~540 MB** (PySide6 trio: 380 MB, torch+ultralytics+opencv-python 4.11: 110 MB, the rest: ~50 MB).

**Cannot drop, despite GUI association:**
- `skellyforge` — used by `core_processes/post_process_skeleton_data/` for filtering & interpolation. KEEP.
- `skelly_synchronize` — used by GUI workers, but the underlying `synchronize_videos_from_audio` function is core to multi-cam workflow. KEEP. (skelly_synchronize's pyproject hard-requires PySide6, but the function we need lives in `skelly_synchronize/skelly_synchronize.py` which has NO PySide6 imports — verified by inspecting the wheel.)
- `skellytracker` — core MediaPipe wrapper. KEEP (without the `[all]` extra).

---

## Section 3 — Required set (must bundle)

Sorted by approximate wheel size. All cp311 macOS arm64 wheels exist and were resolved cleanly by pip.

### Heavy (>10 MB)

| Dep | Version | Wheel | Size | Notes |
|---|---|---|---|---|
| mediapipe | 0.10.14 | `mediapipe-0.10.14-cp311-cp311-macosx_11_0_universal2.whl` | 47.9 MB | Core tracker. Pulls jax. |
| jaxlib | 0.6.1 | `jaxlib-0.6.1-cp311-cp311-macosx_11_0_arm64.whl` | 51.3 MB | Required by mediapipe on macOS. |
| opencv-contrib-python | 4.8.1.78 | `opencv_contrib_python-4.8.1.78-cp37-abi3-macosx_11_0_arm64.whl` | 39.5 MB | The numpy-1 opencv we want. |
| llvmlite | 0.47.0 | `llvmlite-0.47.0-cp311-cp311-macosx_11_0_arm64.whl` | 35.5 MB | numba's LLVM backend. |
| scipy | 1.11.4 | `scipy-1.11.4-cp311-cp311-macosx_12_0_arm64.whl` | 28.3 MB | aniposelib + librosa + skelly_synchronize. |
| numpy | 1.26.2 | `numpy-1.26.2-cp311-cp311-macosx_11_0_arm64.whl` | 13.3 MB | Blender already ships 1.26.4 — see Section 5. We probably DON'T bundle this. |
| pandas | 2.1.4 | `pandas-2.1.4-cp311-cp311-macosx_11_0_arm64.whl` | 10.3 MB | Anipose + skelly_synchronize. |

### Medium (1-10 MB)

scikit-learn 1.8.0 (7.7 MB), matplotlib 3.8.2 (7.1 MB), pillow 12.2 (4.5 MB), ajc27_freemocap_blender_addon 2025.11.1038 (2.8 MB — Mathis's existing Blender addon, we may not even need this depending on architecture), fonttools 4.63 (2.8 MB), numba 0.65.1 (2.6 MB), jax 0.6.1 (2.3 MB), pydantic_core 2.46.4 (1.9 MB), Pygments 2.20.0 (1.2 MB), setuptools 75.8 (1.2 MB), soundfile 0.13.1 (1.0 MB).

### Small (<1 MB)

About 45 small pure-Python or tiny binary wheels. Combined: ~5 MB. Includes pydantic 2.13.4, mpmath, protobuf, joblib, contourpy, librosa, six, decorator, etc.

### Total bundle estimates

| Bundle profile | Wheels included | Total size |
|---|---|---|
| Everything in FreeMoCap's pyproject (no trimming) | 87 packages | **~810 MB** |
| Drop skellycam, skelly_viewer, `[all]` extra | 64 packages | **~647 MB** |
| Also omit PySide6/Qt/pyqtgraph from the manifest's wheel list | 58 packages | **~267 MB** |
| Also drop bundled numpy (let Blender's 1.26.4 satisfy it) | 57 packages | **~254 MB** |

The Extensions zip on disk will be a bit larger than these numbers since wheels compress further; the install footprint inside Blender is roughly the uncompressed wheel contents.

---

## Section 4 — Per-dep table (full unified resolution)

This is the resolution pip produced for the trimmed-but-still-PySide6-pulling case: `skellyforge + skelly_synchronize + skellytracker[mediapipe] + ajc27_freemocap_blender_addon + opencv-contrib-python==4.8.* + toml + aniposelib + pydantic==2.* + packaging===23.2`. 64 packages.

The "Bundle?" column reflects my best read of the trimmed bundle. "no - GUI" = omit from the `wheels = [...]` list in `blender_manifest.toml` because nothing we import at runtime needs it.

| Dep | Version | Wheel | numpy | Bundle? | Notes |
|---|---|---|---|---|---|
| absl-py | 2.4.0 | py3-none-any | agnostic | yes | mediapipe runtime |
| ajc27_freemocap_blender_addon | 2025.11.1038 | py3-none-any | n/a | maybe | Mathis's existing standalone addon. We may absorb its functionality directly into HIHO MOCAP and drop. |
| aniposelib | 0.4.3 | py3-none-any | unbounded → 1.x via co-pin | yes | Multi-cam triangulation core. Wants numba. |
| annotated-types | 0.7.0 | py3-none-any | agnostic | yes | pydantic dep |
| audioread | 3.1.0 | py3-none-any | agnostic | yes | librosa dep |
| cffi | 2.0.0 | cp311-cp311-macosx_11_0_arm64 | agnostic | yes | librosa via soundfile |
| colorlog | 6.10.1 | py3-none-any | agnostic | yes | skelly_synchronize dep |
| contourpy | 1.3.3 | cp311-cp311-macosx_11_0_arm64 | >=1.25 | yes | matplotlib backend |
| cycler | 0.12.1 | py3-none-any | agnostic | yes | matplotlib dep |
| decorator | 5.3.1 | py3-none-any | agnostic | yes | librosa dep |
| deffcode | 0.2.6 | py3-none-any | unbounded | yes | skelly_synchronize video decoder |
| filelock | 3.29.0 | py3-none-any | agnostic | yes | pooch dep (librosa) |
| flatbuffers | 25.12.19 | py2.py3-none-any | agnostic | yes | mediapipe dep |
| fonttools | 4.63.0 | cp311-cp311-macosx_10_9_universal2 | agnostic | yes | matplotlib dep |
| iniconfig | 2.3.0 | py3-none-any | agnostic | yes | pulled by pytest (skelly_viewer dev). Probably droppable. |
| jax | 0.6.1 | py3-none-any | >=1.25 | yes | mediapipe macOS dep |
| jaxlib | 0.6.1 | cp311-cp311-macosx_11_0_arm64 | >=1.25 | yes | mediapipe macOS dep |
| Jinja2 | 3.1.6 | py3-none-any | n/a | yes | mediapipe dep |
| joblib | 1.5.3 | py3-none-any | agnostic | yes | scikit-learn + librosa |
| kiwisolver | 1.5.0 | cp311-cp311-macosx_11_0_arm64 | n/a | yes | matplotlib dep |
| lazy-loader | 0.5 | py3-none-any | n/a | yes | librosa/skimage idiom |
| librosa | 0.10.1 | py3-none-any | >=1.20.3,!=1.22.* | yes | audio sync core. Pulls numba, soundfile, soxr, pooch. |
| llvmlite | 0.47.0 | cp311-cp311-macosx_11_0_arm64 | agnostic | yes | numba LLVM backend |
| markdown-it-py | 4.2.0 | py3-none-any | n/a | yes | rich console formatting (logging cosmetics) |
| MarkupSafe | 3.0.3 | cp311-cp311-macosx_11_0_arm64 | agnostic | yes | Jinja2 dep |
| matplotlib | 3.8.2 | cp311-cp311-macosx_11_0_arm64 | <2,>=1.21 | yes | numpy-1 constraint. skellyforge uses it. |
| mdurl | 0.1.2 | py3-none-any | agnostic | yes | markdown-it-py dep |
| mediapipe | 0.10.14 | cp311-cp311-macosx_11_0_universal2 | unbounded | yes | core tracker |
| ml_dtypes | 0.5.4 | cp311-cp311-macosx_10_9_universal2 | >=1.23.3 (3.11) | yes | jax dep |
| mpmath | 1.3.0 | py3-none-any | n/a | yes | could be transitive elsewhere; small |
| msgpack | 1.1.2 | cp311-cp311-macosx_11_0_arm64 | n/a | yes | librosa/cache dep |
| networkx | 3.6.1 | py3-none-any | n/a | yes | scipy/jax dep |
| numba | 0.65.1 | cp311-cp311-macosx_12_0_arm64 | <2.5,>=1.22 | yes | aniposelib + librosa |
| numpy | 1.26.2 | cp311-cp311-macosx_11_0_arm64 | self | NO* | *Blender already ships 1.26.4. See Section 5. |
| opencv-contrib-python | 4.8.1.78 | cp37-abi3-macosx_11_0_arm64 | numpy-1 only (constraint set) | yes | the version FreeMoCap is built around |
| packaging | 23.2 | py3-none-any | n/a | yes | many deps need it; FreeMoCap pins ===23.2 |
| pandas | 2.1.4 | cp311-cp311-macosx_11_0_arm64 | <2,>=1.23.2 | yes | numpy-1 constraint. aniposelib + skelly_synchronize. |
| Pillow | 12.2.0 | cp311-cp311-macosx_11_0_arm64 | agnostic | yes | matplotlib backend |
| platformdirs | 4.9.6 | py3-none-any | n/a | yes | pooch + appdirs replacement |
| pluggy | 1.6.0 | py3-none-any | n/a | maybe | pytest-runtime. Possibly droppable; check skelly_viewer. |
| polars-runtime-32 | 1.41.0 | cp310-abi3-macosx_11_0_arm64 | n/a | yes? | pulled by skellytracker. Verify needed. |
| polars | 1.41.0 | py3-none-any | n/a | yes? | same |
| pooch | 1.9.0 | py3-none-any | agnostic | yes | librosa data cache |
| protobuf | 4.25.9 | cp37-abi3-macosx_10_9_universal2 | n/a | yes | mediapipe core |
| psutil | 5.9.6 | cp38-abi3-macosx_11_0_arm64 | n/a | yes | skelly_synchronize uses it |
| pycparser | 3.0 | py3-none-any | n/a | yes | cffi dep |
| pydantic | 2.13.4 | py3-none-any | agnostic | yes | freemocap data models |
| pydantic_core | 2.46.4 | cp311-cp311-macosx_11_0_arm64 | agnostic | yes | pydantic backend |
| Pygments | 2.20.0 | py3-none-any | n/a | yes | rich logging cosmetics |
| pyparsing | 3.3.2 | py3-none-any | n/a | yes | matplotlib dep |
| pyqtgraph | 0.13.3 | py3-none-any | >=1.20 | **no - GUI** | only used by skellyforge widgets |
| PySide6 / _Addons / _Essentials | 6.6.3.1 | cp38-abi3-macosx_11_0_universal2 | n/a | **no - GUI** | only used by skellyforge widgets & gui/qt |
| pytest | 9.0.3 | py3-none-any | n/a | **no - dev** | pulled by skelly_viewer dev-bleed |
| python-dateutil | 2.9.0.post0 | py2.py3-none-any | n/a | yes | pandas dep |
| pytz | 2026.2 | py2.py3-none-any | n/a | yes | pandas dep |
| PyYAML | 6.0.3 | cp311-cp311-macosx_11_0_arm64 | n/a | yes? | trace usage; possibly mediapipe |
| QtPy | 2.4.1 | py3-none-any | n/a | **no - GUI** | pandas optional, harmless to drop |
| rich | 13.7.0 | py3-none-any | n/a | yes | skelly_* logging |
| scikit-learn | 1.8.0 | cp311-cp311-macosx_12_0_arm64 | >=1.24.1 | yes | librosa transitively |
| scipy | 1.11.4 | cp311-cp311-macosx_12_0_arm64 | <1.28,>=1.21.6 | yes | core math |
| setproctitle | 1.3.3 | cp311-cp311-macosx_10_9_universal2 | n/a | yes | only listed by skellycam — drop with skellycam |
| setuptools | 75.8.0 | py3-none-any | n/a | yes | skelly_synchronize pin |
| shiboken6 | 6.6.3.1 | cp38-abi3-macosx_11_0_universal2 | n/a | **no - GUI** | PySide6 binding glue |
| six | 1.17.0 | py2.py3-none-any | n/a | yes | python-dateutil/anipose dep |
| skelly_synchronize | 2025.4.1037 | py3-none-any | ==1.26.2 | yes | audio sync core |
| skellyforge | 2024.12.1009 | py3-none-any | ==1.26.2 | yes | post-processing core |
| skellytracker | 2025.10.1024 | py3-none-any | <2 | yes | mediapipe wrapper |
| sounddevice | 0.5.5 | py3-none-macosx_10_6_*universal2 | n/a | yes | audio capture (skelly_synchronize) |
| soundfile | 0.13.1 | py2.py3-none-macosx_11_0_arm64 | unbounded | yes | librosa dep |
| soxr | 1.1.0 | cp311-cp311-macosx_11_0_arm64 | unbounded | yes | librosa dep |
| threadpoolctl | 3.6.0 | py3-none-any | n/a | yes | scikit-learn dep |
| toml | 0.10.2 | py2.py3-none-any | n/a | yes | freemocap config |
| tqdm | 4.67.3 | py3-none-any | n/a | yes | progress bars |
| typing-inspection | 0.4.2 | py3-none-any | n/a | yes | pydantic 2.x dep |
| tzdata | 2026.2 | py2.py3-none-any | n/a | yes | pandas dep |

**Direct deps of FreeMoCap that I'm marking droppable end-to-end:** skellycam, skelly_viewer, libsass, ipykernel, plotly, PySide6. **Drop the `[all]` extra** on skellytracker (use `[mediapipe]`).

---

## Section 5 — Numpy-1.x risk register

This is the column that decides bundle vs. fallback. Every constraint in the resolved tree:

| Constraint | Satisfied by Blender's numpy 1.26.4? |
|---|---|
| `numpy <2,>=1.21` (matplotlib 3.8.2) | yes |
| `numpy <2,>=1.23.2` (pandas 2.1.4 @ py3.11) | yes |
| `numpy <1.28.0,>=1.21.6` (scipy 1.11.4) | yes |
| `numpy <2.5,>=1.22` (numba 0.65.1) | yes |
| `numpy <2` (skellytracker 2025.10.1024) | yes |
| `numpy >=1.23.5` (opencv-contrib-python 4.8.1.78 @ py3.11) | yes |
| `numpy >=1.25` (jax/jaxlib/contourpy) | yes |
| `numpy >=1.21.2` (ml_dtypes @ py3.11 — has separate stricter rule at >=3.13 only) | yes |
| `numpy ==1.26.2` (skellycam, skelly_viewer, skelly_synchronize, skellyforge) | **conditional — see below** |
| `numpy >=1.20.3, !=1.22.0, !=1.22.1, !=1.22.2` (librosa 0.10.1) | yes |

**The exact-pin caveat:** the four `skelly_*` packages hard-pin `numpy==1.26.2`. If we ever tried to `pip install` these into Blender's site-packages, pip would refuse — Blender has 1.26.4. But the Blender Extensions pipeline doesn't run pip's resolver at install. It extracts whatever `.whl` files we list and lets Python import them. At runtime, `numpy.__version__ == '1.26.4'` works fine — none of the skelly_* code does a version-string check, they just use the numpy API which is stable across 1.26.x patch releases.

**This is the central architectural insight for the bundle path:** Blender Extensions = manifest declares wheels, Blender extracts them. No dep solver runs. We are the dep solver, at build time. The runtime cost is: if a skelly_* changes its imports and our wheel set silently misses a new dep, students get an `ImportError` after install — there's no fallback installer to fix it.

**Conclusion: numpy-1 risk is low.** The single exact-pin on numpy 1.26.2 is annoying but doesn't matter at runtime. There's no numpy-2 landmine in the tree.

---

## Section 6 — Missing / source-only wheels

**None.** All 87 wheels in the full pip resolution were `.whl` files with cp311 macOS arm64 (or universal2 / py3-none-any) tags. No `--no-binary` deps. No build-from-source required. Confirmed by reading the `download_info.url` field of every package in `/tmp/wheel_dryrun/report_FULL.json` — every URL ends in `.whl`.

This is the strongest single argument for the bundle path: pip already proved this resolves with binaries-only on macOS arm64.

---

## Section 7 — Bundle-or-fallback recommendation

**Bundle viable, with caveats.** Concretely:

- **At ~270 MB** (drop GUI, drop `[all]` extras, don't ship numpy), the zip is large but defensible. For reference: Mathis's standalone FreeMoCap macOS installer is ~1.5 GB. We're roughly 5x smaller.
- **At ~810 MB** (ship everything FreeMoCap's pyproject declares), we are way past "single zip students download." This is a non-starter for the HIHO experimental animation club's late-June 2026 launch.
- **The cost of bundling: we own the dep manifest forever.** Every time FreeMoCap publishes new skelly_* versions we need to re-run the dry-run, re-check imports, re-download wheels, re-zip. There's no auto-update story. For v1.0 with the club as first users, this is fine. For v1.1 broader release this needs an automated build-wheels script.

**The trimmed bundle (~270 MB) should be the default proposal to David.** It buys:
- Single-click install via Blender Extensions
- No internet required at install time
- No pip prompt at first launch
- Identical wheel set across student machines (zero "works on my machine")

**Fallback would be required if:**
- David vetoes the 270 MB zip as too big to host on his SCRAP server / GitHub release
- We discover at integration time that FreeMoCap calls a code path that does in fact `import PySide6` somewhere we missed
- We need Windows/Linux support in v1.0 — multiplies the wheel count by 3 platforms

For the macOS-arm64-only / BASEMENT-studio / SJSU-club use case at the v1.0 launch window, **bundle wins on every axis except disk size, and disk size at 270 MB is manageable.**

---

## Section 8 — Open questions for David / Claude (next session)

Ranked by how much they matter to the bundle/fallback decision:

1. **Will FreeMoCap's processing functions actually run if PySide6 is absent at runtime?** This audit found the FUNCTIONS we import don't directly `import PySide6`, but Python imports are transitive — a chain `freemocap.core_processes.X` → `skellyforge.Y` → `…postprocessing_widgets…` could detonate even though our function call never reaches the widget. Verification step before committing: install the trimmed wheel set into a clean venv and run the actual capture+process pipeline against a known-good multicam recording. (NOT in scope for this audit — this is the next acceptance test.)
2. **Do we need `ajc27_freemocap_blender_addon` at all?** It's Mathis's standalone Blender addon for visualizing FreeMoCap output. HIHO MOCAP is also a Blender addon doing more. We may absorb the relevant parts and drop the dep entirely (saving 2.8 MB and one moving piece).
3. **Is `aniposelib==0.4.3` the right version?** It pins to FreeMoCap's lock but has known issues (the line-2089 patch David applied to anipose on 2026-05-09 — see `project_basement_multicam_install.md`). Decide whether we bundle the patched aniposelib (vendored as source) or the pristine PyPI wheel.
4. **What's the install footprint on disk after extraction?** Our 270 MB number is the sum of wheel file sizes. Wheels expand 2-3x on disk. Real on-disk size after Blender installs the extension will be ~600-800 MB. Worth a head-up for students with small SSDs.
5. **Should we ship our own numpy 1.26.2 wheel anyway to match the skelly_* exact pin perfectly?** Probably no — Blender's 1.26.4 will work and bundling numpy risks the addon's numpy shadowing Blender's other addons' numpy. Worth confirming.
6. **What does `polars` need to do in the resolution?** It got pulled by skellytracker but it's not obvious why. Worth a 5-minute dive at integration time.
7. **Should the dropped GUI wheels become an OPTIONAL `[gui]` extension users can install separately?** Probably no for v1.0 (scope creep) but worth keeping in mind if students ever want skelly_viewer for review.

---

## Appendix A — Reproducing this audit

All commands run against Blender 5.0's bundled Python:

```bash
PY="/Applications/Blender.app/Contents/Resources/5.0/python/bin/python3.11"
mkdir -p /tmp/wheel_dryrun

# Full resolution (what FreeMoCap declares)
"$PY" -m pip install --dry-run --report /tmp/wheel_dryrun/report_FULL.json --quiet \
    'skellycam==2025.09.1097' 'skelly_viewer==2025.04.1028' \
    'skellyforge==2024.12.1009' 'skelly_synchronize==2025.04.1037' \
    'skellytracker[all]==2025.10.1024' \
    'ajc27_freemocap_blender_addon==2025.11.1038' \
    'opencv-contrib-python==4.8.*' 'toml==0.10.2' 'aniposelib==0.4.3' \
    'pydantic==2.*' 'packaging===23.2'

# Trimmed (drop GUI, drop torch/ultralytics)
"$PY" -m pip install --dry-run --report /tmp/wheel_dryrun/report_TRIMMED.json --quiet \
    'skellyforge==2024.12.1009' 'skelly_synchronize==2025.04.1037' \
    'skellytracker[mediapipe]==2025.10.1024' \
    'ajc27_freemocap_blender_addon==2025.11.1038' \
    'opencv-contrib-python==4.8.*' 'toml==0.10.2' 'aniposelib==0.4.3' \
    'pydantic==2.*' 'packaging===23.2'
```

Both succeeded. Reports are in `/tmp/wheel_dryrun/` until cleared. Wheel sizes in `/tmp/wheel_dryrun/sizes.json`. Unzipped skelly_* wheels for grep-verification in `/tmp/wheel_dryrun/*_extract/`.

---

## Appendix B — Quick command to download the proposed bundled set

This is the next step IF David approves bundling. Save here for handoff — **do not run as part of this audit**.

```bash
PY="/Applications/Blender.app/Contents/Resources/5.0/python/bin/python3.11"
"$PY" -m pip download --dest ./wheels/ \
    --only-binary=:all: \
    --platform macosx_11_0_arm64 \
    --python-version 3.11 \
    'skellyforge==2024.12.1009' \
    'skelly_synchronize==2025.04.1037' \
    'skellytracker[mediapipe]==2025.10.1024' \
    'opencv-contrib-python==4.8.1.78' \
    'toml==0.10.2' \
    'aniposelib==0.4.3' \
    'pydantic==2.13.4' \
    'packaging==23.2'
# Then DELETE PySide6*.whl, shiboken6*.whl, QtPy*.whl, pyqtgraph*.whl, pytest*.whl, iniconfig*.whl, pluggy*.whl from ./wheels/
# Then DELETE numpy*.whl too (Blender has its own)
# Then list the remaining ~55 wheels under `wheels = [...]` in blender_manifest.toml
```
