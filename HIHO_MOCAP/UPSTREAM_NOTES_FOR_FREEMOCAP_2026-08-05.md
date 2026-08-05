# Notes for the FreeMoCap community, from a classroom

**Status: internal draft, not yet shared.** This document collects what HIHO MOCAP has learned while driving FreeMoCap in a classroom setting, written for the FreeMoCap maintainers and community to go over when we share it. Nothing here has been posted or sent; sharing is a deliberate later step. Claims are tagged: **[VERIFIED 2026-08-05]** means checked against the installed freemocap 1.8.2 source or the public GitHub project that day; **[OUR DOCS]** means the evidence lives in this repository's dated docs (pointer given); anything less certain says so.

## 1. Why we built on FreeMoCap instead of building an engine

HIHO MOCAP exists so a student can make a mocap short in one class period, on donated hardware, without a terminal and without a subscription. The founding rule of this codebase, written the day the project folder was claimed: **we write less code than we wire.** The hard math already existed in open source, and it was FreeMoCap: camera sync, ChArUco calibration, triangulation, post-processing. We add the classroom layer on top and nothing underneath. (`ARCHITECTURE.md` section 0, 2026-05-06.)

Two decisions along the way made that respect concrete:

- **We run the engine, we never modify it.** FreeMoCap 1.8.2 runs unmodified in its own Python environment as a watched subprocess. Our addon is 49 KB of Blender-side coordination. When we briefly maintained a 1:1 parallel port of the ecosystem's Blender layer, we wrote down the honest verdict: "we are not behind the upstream; we are running in parallel to it," and every upstream bugfix was becoming a port we had to redo. So we cut our code surface from "the whole pipeline" to "the wrapper" and pointed every gap we found at one of two destinations: a contribution upstream, or a HIHO-specific layer on top. (`HIHO_MOCAP_WRAPPER_ARCHITECTURE.md` sections 1.1 to 1.3.)
- **A full reimplementation was considered and rejected in writing:** "Years of work. Skip." Keep FreeMoCap for the hard math. (`HIHO_MOCAP_v1_PLAN.md`.)

The evidence that convinced us the engine was sound came early: in May, every one of the 22 problems we logged lived in the GUI and orchestration layer, and the same Blender export that hung the GUI for 15 minutes ran in 13 seconds from the command line. The engine was never the problem. That list became the case for this addon: replace the brittle layer above the engine, not the engine. (`BUGS_AND_BACKLOG.md`, May 2026.)

Word discipline, stated in our project rules since May: FreeMoCap is run, bundled, or vendored. It is never called a fork, because it is not one.

## 2. How we run it

Six webcams record through our own direct-to-disk recorder (written because the built-in multi-camera recorder's RAM accumulation bug, freemocap/freemocap#650, was open when we started and remains open **[VERIFIED 2026-08-05]**). Processing calls `process_recording_folder` headlessly inside a frozen environment (freemocap 1.8.2, skellycam 2025.09.1097, skellytracker 2025.10.1024, aniposelib 0.4.3, mediapipe 0.10.14). Blender floats to any current version because nothing version-sensitive runs inside it. Completion is signaled by atomic on-disk sentinel files because FreeMoCap's child processes inherit the stdout pipe and outlive the parent, so a pipe watcher can never trust EOF (`external/process_take.py` docstring).

## 3. Findings we believe are worth upstream's time

### 3.1 The post-processing filter clock (their issue #849, filed independently the same day we verified)

**[VERIFIED 2026-08-05]** In freemocap 1.8.2, `data_layer/recording_models/post_processing_parameter_models.py:32` sets `framerate: float = 30.0`. `core_processes/post_process_skeleton_data/post_process_skeleton.py:50` uses that value as the Butterworth sampling rate. The GUI does expose a "Framerate" field and passes it correctly (`create_parameter_groups.py:272-274`), but the field lives in a collapsed-by-default parameter group, is preset to 30, and its own tooltip reads: "Framerate of the recording. TODO - Calculate this from the recorded timestamps...." So the gap is acknowledged in the source; what has been missing is a measurement of its cost, and auto-detection.

**What it costs, measured on our rig:** at 60 fps the intended 7 Hz cutoff becomes an effective ~14 Hz, and every take arrives half filtered. Re-processing the same videos with the same calibration and only the clock corrected cut above-8 Hz noise by roughly 90 percent at every landmark group (wrists 5.40 to 0.50 mm RMS, ankles 4.51 to 0.39, shoulders 1.05 to 0.10, hips 1.02 to 0.10) while the 0 to 6 Hz real-motion band changed by about 0.01 percent. (`SESSION_HANDOFF_2026-08-04_DESKTOP_BUILD.md`; fix shipped in our 1.4.34, `external/process_take.py:165-176`, which sets `framerate` and `butterworth_filter_parameters.sampling_rate` from the take's recorded fps sidecar.)

**Upstream status [VERIFIED 2026-08-05]:** open issue freemocap/freemocap#849, "[BUG] Post-processing Butterworth filter uses a hardcoded 30 fps regardless of recording rate," filed 2026-08-05 by an independent user against the V2 code, zero comments at time of writing. Our contribution when shared: the 1.x code path references above, the A/B measurements, and the sidecar-driven fix pattern.

### 3.2 The ground-plane flip (not reported anywhere upstream that we can find)

When calibrating from a ChArUco board, a mostly planar view of the board has two mathematically valid poses (the OpenCV planar ambiguity). FreeMoCap's ground-plane alignment can pick the wrong one: the world comes out mirrored below the floor, every camera lands underground, and the reprojection error still reads excellent because reprojection cannot see orientation. **[VERIFIED 2026-08-05]** there is no ambiguity handling anywhere in the installed calibration path, and the only failure behavior is a silent revert to camera-0 origin with a log line (`anipose_camera_calibrator.py:240,247`). **[VERIFIED 2026-08-05]** no upstream issue describes this (the three "ground plane" issues are unrelated).

We hit it in the field on 2026-07-03: a solve scored "Excellent 0.28 px" while heels sat 59 cm underground and 71 percent of frames were below the floor. A matched good/flipped calibration pair is preserved for reproduction. Our shipped mitigation is a post-solve sanity check: parse the calibration TOML, recover each camera's world position, and refuse loudly if any camera sits at or below the floor. Suggested upstream direction: use the ambiguity-aware solver so both candidate poses and their errors are visible, making the flip detectable instead of silent. (`FOUR_CAM_OPTIMIZATION_RESEARCH_2026-07-03.md` sections 2c and 5; `GROUNDPLANE_SANITY_CHECK_DESIGN_2026-07-04.md`; repro pair `HIHO_CALIBRATIONS/2026-07-02_14-02-02` vs `2026-07-03_15-14-56`.)

### 3.3 Outlier rejection default (their open RFC #782)

**[VERIFIED 2026-08-05]** freemocap/freemocap#782, "[RFC] Should we set 'outlier rejection' to default On?", is open. We can answer with field data: we A/B tested it on a real take (wrist jitter down 55 percent, feet down 19 percent, torso negligible, posture unchanged, byte-exact reproducibility confirmed) and shipped default ON for our students in July with the stock guardrails. Classrooms vote yes. (`OUTLIER_REJECTION_DESIGN_2026-07-03.md`.)

### 3.4 A one-line calibration patch we owe as a PR

FreeMoCap's vendored anipose code requires at least 7 detected corners per frame (`len(o) >= 7`), which makes the officially recommended small 5x3 board (8 corners total) nearly uncalibratable. We have run `>= 6` since May with stable pose estimation. **[VERIFIED 2026-08-05]** our environment carries the patch with a dated comment; upstream source is unchanged. Whether anyone has reported it upstream has not been checked yet. (`BUGS_AND_BACKLOG.md` #7; snippet in `MOCAP_CALIBRATION_FILES/anipose_patch_line2089.txt`.)

### 3.5 Recorder-side field notes (context for #650 and V2 camera work)

Our recorder is our own, so these are field observations rather than bug reports: USB enumeration order is unstable across reboots on identical cameras that expose no serial numbers, so we made the live preview itself the camera picker. A keyboard sharing a camera's USB hub silently starved that camera to 5 fps with a normal-looking image, which stalls any frame-count-bounded recording forever; our rule is now cameras only on camera hubs, and a three-second per-camera fps preflight is queued. Frame-count parity across cameras is a hard engine requirement, so early stop must equalize counts upward rather than trim. Per-frame timestamps at grab time remain, in our view, the single highest-value capture improvement in the family, and skellycam v1's own `timestamp_ns` work is a proven in-family reference. (`CAMERA_PICKER_DESIGN_2026-07-06.md`; `BUGS_AND_BACKLOG.md` 2026-08-01; `ESC_EARLY_STOP_DESIGN_2026-06-09.md`; `HIHO_ADOPTABLE_INNOVATIONS.md` Tier 1.)

### 3.6 Measurements the community may simply find useful

- **Noise is a gradient across the body, spanning roughly 200 to 1.** Ratio of above-8 Hz noise to real motion, per region, on a 60 fps take: pelvis ~0.00 percent, thighs 0.12, shoulders 0.16, spine 0.28, forearms 1.07, feet 2.28, fingers 9.05, thumbs 22.13, palms 30.29, hands at the wrist 36.74. Pelvis translation is essentially noise free (0.003 percent), which is why smoothing root travel is nearly pure loss. The gradient tracks landmark visibility more than distance from center. (`SMOOTHING_METHODOLOGY_2026-08-04.md`.)
- **One filter cutoff cannot serve both ends of that gradient**; per-region strength matched the gentlest global setting on motion preservation and the most aggressive one on cleanup in head-to-head tests. **Caveat: every smoothing number above was measured on data that had passed through the mis-clocked 30 fps pre-filter and is queued for re-derivation on the corrected take before any of it is shared.** (`SMOOTHING_RESEARCH_PRIOR_ART_2026-08-04.md`, verification notes.)
- **Camera geometry:** a 270 degree, three-height, six-camera ring produced our best calibration (0.42 px) and grew the clean tracking volume from about 0.75 m radius to at least 1.00 m. Ceiling mounts in an old building drifted 3 to 7 cm between consecutive days, both days scoring "excellent," which is why calibration is a per-session ritual here. (`STATUS.md` 2026-08-01; `SIX_CAMERA_SCALING_RESEARCH.md`.)
- **Verdict design:** reprojection error cannot see a flipped world, and a poisoned mean can read 4.5 million px where the median reads 15.75. Median-based scoring plus named badges (every quality verdict carries the name of the take it describes) ended a whole class of stale-trust incidents for us. (`PROCESS_QUALITY_SCORE_DESIGN_2026-07-03.md` and addendum.)

### 3.7 For the Blender wing of the family (ajc27's addon and anyone baking constraint-driven rigs)

The one-frame whole-body snap that appears only after smoothing a baked take is quaternion sign flipping manufactured by the bake itself: per-frame matrix decomposition always returns the canonical spelling with no frame-to-frame memory, so any bone crossing 180 degrees silently flips, and a filter later averages +q against -q into one frame of nonsense. Blender's Euler Filter cannot fix it (Euler channels only) and `pose.quaternions_flip` operates on the current pose only. The fix is a continuity pass over the baked curves, comparing each frame against the previous frame as already corrected. Ours runs inside the bake and reports what it did. (`Z_JITTER_DIAGNOSIS_2026-08-04.md`.)

## 4. What is uniquely ours (the classroom layer)

So the boundary is explicit: everything in section 3 sits on top of an engine we did not write. What HIHO adds is the layer for rooms full of fourteen-year-olds: honest quality badges that name their take; a five-step Studio panel with a Science Mode gate for the technical machinery; a blank camera list that refuses to guess; a bake that repairs its own rotation spelling and says so; crash messages in plain language; scene clocks set from the take's own sidecar instead of silent 24 fps defaults; a per-machine data home; capture protocol cards (calibrate every session, measure the printed board, sync flash while standing still); and a bake-first deliverable philosophy, because the classroom product is a student-owned .blend file, not a live puppet. None of it is engine work. All of it is the reason the engine survives contact with a classroom.

## 5. Influences and credits, precisely

- **FreeMoCap** (AGPL-3.0) is the engine: capture conventions, calibration, triangulation, post-processing, and the output formats our whole artist layer keys off. Run unmodified, always.
- **ajc27's freemocap_blender_addon** is the reference template for our Blender-side rig work. Our constraint table's content is carried verbatim from theirs by deliberate decision, our 63-bone skeleton topology, T-pose tables, virtual landmark formulas, and hand-data alignment are faithful re-implementations, and we adopted their bone naming as an interoperability standard so a take can drive characters with no translation layer. Two of their small tolerance rules were lifted directly from their code comments; instructively, the one we failed to carry (substring matching on empty names) caused one of our worst silent bugs, which is its own argument for how much care their details deserve. No ajc27 code ships in our builds; the relationship is documented in `AJC27_PARITY_ROADMAP_2026-06-06.md`.
- **skellycam and skelly_synchronize** gave us the per-frame timestamp reference implementation and the brightness-flash sync method we adopted as doctrine.
- Beyond the family: meshonline's MIT-licensed heat-diffuse skinning solver (vendored with license, our own Blender wrapper written clean because theirs is GPL-2), the Pinocchio paper lineage for auto-rigging, published capture guidance from the FreeMoCap docs adopted wholesale as classroom doctrine, and the wider prior art credited by name in `SMOOTHING_RESEARCH_PRIOR_ART_2026-08-04.md` and `PRE_BASEMENT_CAPTURE_RESEARCH_2026-07-01.md`.

## 6. The documentation trail

Every claim above has a dated document in this repository: the audits (`AUDIT_2026-06-09.md`, `AUDIT_2026-08-04.md`), the diagnosis writeups (`Z_JITTER_DIAGNOSIS_2026-08-04.md`), the design docs (every feature), the research docs (every adoption decision), the running bug ledger (`BUGS_AND_BACKLOG.md`), and the live state (`STATUS.md`). That trail is the development history of this project, and it is offered as evidence in the oldest sense: not "trust us," but "here is everything, go over it."

## 7. Sharing posture

Nothing in this document has been sent anywhere. When we share, the likely order is: measurements and code references added to open issue #849; the ground-plane report filed with its reproduction case; the outlier data added to RFC #782; the one-line corner-count patch offered as a PR; and this document linked for the rest. Timing matters and favors soon: V2 is being rearchitected right now, including calibration. But the decision and the words belong to the human whose program this is.
