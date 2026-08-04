# Capture Cameras + Camera-Accurate Video Billboards — Design (2026-06-06)

**Status:** design, pre-code. Parity item #1 from [AJC27_PARITY_ROADMAP_2026-06-06.md](AJC27_PARITY_ROADMAP_2026-06-06.md).
**Context:** continues the 1.3.3 build. Today's **Add Camera Videos** lays the take's videos flat in a row; this item upgrades them to sit where the real cameras stood, and adds the camera objects themselves.
**Look chosen:** camera objects **plus** fanned video billboards (the FreeMoCap "hero shot"). David was offered cameras-only / billboards-only and deferred to the recommendation; this doc builds the recommended both-look and is easy to dial back to either subset.

**BUILD STATUS (2026-06-06):** Steps 1–2 + the operator/panel/registration are **built and verified**, shipped in **`SOFTWARE/hiho_mocap-1.3.4.zip`** (65 KB, wheel-less).
- Step 1 `loader.recording_alignment` — verified on a real take (clean rotation, skeleton stands at origin).
- Step 2 `core/capture_cameras.py` + `operators/capture_cameras.py` + **Add Cameras** button — verified end-to-end in headless Blender 5.2: registers, runs, creates 4 cameras at the calibration-derived poses, all aiming at the performer (3–12°); Blender's matrix math matched the headless numpy prediction to 2 decimals.
- **Pending:** David's in-Blender look-through eyeball, then Steps 3–4 (background images + billboards). Ships cameras-only for now.

## 0. TL;DR

Port ajc27's `add_capture_cameras` into a clean-room `core/capture_cameras.py`: read each camera's saved place + angle from the calibration `.toml`, create a Blender **camera object** there with the right lens, and snap a **video billboard** (the take's footage) in front of each one. Result: four cameras fanned around the captured volume, each with its clip floating in front, and you can render through any of them.

Two research findings reshape the naive port:

1. **The 3D math is already on disk.** Every calibration `.toml` stores `world_position` + `world_orientation` per camera (FreeMoCap computes them during *every* calibration). We do **not** re-derive any geometry — we read four arrays per camera.
2. **A literal port places zero cameras on David's files, and would put them in the wrong frame.** ajc27 hard-returns unless `groundplane_calibration = true` (David's calibrations are `false`), and it places cameras in FreeMoCap's *raw* world frame. But HIHO re-grounds the skelly (`loader.py` stands it up at the origin). So we must (a) drop the groundplane gate and (b) run each camera through HIHO's **same straighten-up transform** so the cameras line up with the skelly. This is strictly more capable than ajc27 — it works on any calibration, ground plane or not — and the alignment doubles as the correctness check.

## 1. What ajc27 does (the template)

`ajc27_freemocap_blender_addon/core_functions/add_capture_cameras/add_capture_cameras.py`:

1. Finds the `*.toml` in the recording folder, loads it with `tomllib`.
2. **Bails unless `metadata.groundplane_calibration` is true.** ← the gate we drop.
3. For each `cam_N` section:
   - `location = world_position / 1000` (mm → m).
   - `rotation = Matrix(world_orientation).to_quaternion() @ Quaternion((1,0,0), pi)` — the 180°-about-X flip converts the computer-vision camera convention (looks +Z) to Blender's (looks −Z).
   - lens: `f_mm = fx * (sensor_width / max(width_px, height_px))`, `sensor_width = 36 mm`.
   - parents the camera under a `capture_cameras_parent` empty (itself under the `_origin` empty).
   - attaches the matching `synchronized_videos/` clip as the camera's **background image** (MOVIE_CLIP), which only shows when you look *through* that camera.
4. Sets render resolution to `cam_0`'s size.

Note ajc27 shows footage as a **camera background image**, not a billboard. The "fanned video panels you see from any angle" look comes from positioning *planes* at the cameras — that's the HIHO upgrade described here. We can additionally set background images on the cameras (cheap, faithful) so rendering through a camera shows its plate.

## 2. What's actually in David's calibration `.toml`

Confirmed against `~/freemocap_data/calibrations/import_2026-05-12_15-22-12_camera_calibration.toml`:

```
[cam_0] … [cam_3]
  size               = [1024, 576]
  matrix             = [[fx,0,cx],[0,fy,cy],[0,0,1]]   # intrinsics, pixels
  distortions        = [...]
  rotation, translation                                # raw extrinsics (world→cam)
  world_orientation  = 3x3                             # camera→world, RAW frame  ← we use
  world_position     = [x,y,z] (mm)                    # camera in RAW frame      ← we use
[metadata]
  groundplane_calibration = false                      # ← ajc27 would bail here
```

`get_real_world_matrices` (in FreeMoCap's `anipose_camera_calibrator.py`) runs on every calibration and writes `world_position` / `world_orientation`, so they are **always present**, groundplane or not. cam_0 is the raw-frame origin (identity orientation, zero position); the others are placed relative to it.

## 3. The placement math (the one section with numbers — skip to §4 for the plan)

HIHO's `loader.py` transforms the captured points like this (loader.py:135):

```
aligned = (raw_meters − translation) @ rotation.T
```

where `translation` (a 3-vector, meters) and `rotation` (a 3×3) come from `loader._compute_alignment` on the most-still "good frame." We apply the **same** transform to each camera so it lands in the skelly's frame.

**Position** (identical formula to the points):
```
P_raw_m   = world_position * (1/1000)              # mm → m, raw frame
P_aligned = rotation @ (P_raw_m − translation)      # = (P_raw_m − translation) @ rotation.T
```

**Orientation** — `world_orientation` is camera→raw-world (columns are the camera's axes in raw world). Rotating the whole world by `rotation` rotates those axes the same way:
```
R_aligned = Matrix(rotation) @ Matrix(world_orientation)
quat      = R_aligned.to_quaternion() @ Quaternion((1,0,0), pi)   # keep ajc27's CV→Blender flip
```

**Lens** — intrinsics are unaffected by a rigid world move, so copy ajc27 verbatim:
```
f_mm = fx * (36.0 / max(width_px, height_px));  sensor_width = 36.0
```

Why this is the correctness test: a camera placed this way, looked through, sees the aligned skelly from exactly the angle the real camera saw the performer. If the footage (background image / billboard) lines up with the skelly silhouette through the lens, the port is right. If it's rotated or offset, the compose is wrong. That's an eyeball check, no numbers needed.

`rotation` is orthonormal and right-handed (built from cross products and normalized in `_compute_alignment`), so it's a pure rotation — no scale or skew sneaks in.

## 4. Locating the calibration for a take

Reuse the existing convention (no new picker needed — `properties.py` already has these, and the override is a `FILE_PATH` picker per the file-picker rule):

1. `scene.hiho_mocap.calibration_toml_path` if the student set it (explicit override).
2. else `~/freemocap_data/last_successful_calibration.toml`.
3. else the first `*.toml` inside the take folder (matches ajc27's "look in the recording folder").

If none found: report a clear message ("No calibration found — pick one in the panel or run Calibrate") and add no cameras. (Billboards-flat-in-a-row remain available via the current behavior as a fallback — see §5.)

## 5. The video billboards (planes at the frustums)

Reuse the existing `core/video_planes.py` plumbing (the `import_as_mesh_planes` import + the "HIHO MOCAP Videos" collection); change only **where each plane goes**.

For each camera, place its clip as a plane that looks like the camera's image projected onto a screen a short distance in front of it:
- a distance `d` in front along the camera's view direction,
- rotated to share the camera's orientation (so it faces back down the lens),
- sized to fill the camera's field of view at distance `d`: `height_m = d * height_px / fy` (aspect follows the image), so the billboard exactly overlays what that camera sees at depth `d`.

`d` default: a fixed, sensible value (start ~1.0 m; the performer is near the origin and cameras are a few meters out, so the panels fan *between* the cameras and the performer). Exposed as a slider later; **I pick the number, not David.** Match by filename: `Camera_0_*.mp4 → cam_0`, etc. (ajc27 matches by the `_N` index; we do the same).

Matching the clip to the camera by index is the one fragile spot (folder sort vs. `cam_N`): assert counts match and label by the camera's `name` field from the TOML.

## 6. Files

**New:**
- `core/capture_cameras.py` — clean-room. `add_capture_cameras(recording_folder, toml_path, alignment, *, make_billboards=True, set_backgrounds=True, billboard_distance=1.0)`:
  parse TOML → per camera: create camera object (pose from §3, lens), optionally set background image, optionally place a billboard plane. Returns created object names. No `bpy.ops` for the math; `bpy.data`/`bpy.ops.object.camera_add` for creation. Cameras + billboards go in a **"HIHO MOCAP Cameras"** collection, parented to the take's `HIHO_MOCAP_Skelly_<take>` root if present (so they move/scale/purge with it).
- `operators/capture_cameras.py` — `HIHO_MOCAP_OT_add_capture_cameras` ("Add Cameras"): resolve the take + calibration (§4), pull the alignment (§7), call the core. Plain-English error reports.

**Edited:**
- `core/loader.py` — add a small public `recording_alignment(recording_folder) -> (translation, rotation)` that loads just the body + reprojection-error npys and calls the existing `_estimate_good_frame` + `_compute_alignment`. Deterministic, so it returns the *same* transform the skelly was built with. **Leaves `load_aligned_data` untouched** (no risk to the proven rig path).
- `ui/panels.py` — an **Add Cameras** button in the Output section, next to **Add Camera Videos**. (Keep the row-of-videos button as the no-calibration fallback.)
- `__init__.py` — register the new operator.
- `blender_manifest.toml` — bump to 1.3.4.

## 7. Build order (one change at a time, test after each)

1. **`recording_alignment` helper in loader.py.** Test: on the 14-55-09 take, assert it returns a `(3,)` translation + `(3,3)` rotation, and that they match what `load_aligned_data` used (spawn a skelly, compare a landmark's world position to `rotation @ (raw − translation)`). No scene change yet.
2. **`core/capture_cameras.py` — camera objects only** (no billboards, no backgrounds). Test live via the Blender connector: 4 cameras appear; look through `Camera_2` and confirm the (already-spawned) skelly is framed like the real Camera_2 saw it. This is the make-or-break alignment check.
3. **Background images** on each camera. Test: through-the-lens view shows the plate behind the skelly, aligned.
4. **Billboards** (planes at frustums). Test: from an outside 3D view, four video panels fan around the skelly; each overlays its camera's view.
5. **Operator + panel button + register + manifest 1.3.4.** Test: click **Add Cameras** end-to-end on a take; build the zip from `SOFTWARE/` and confirm install in 5.2.

## 8. Verification

- **Alignment (primary):** look through each camera; the footage (background or billboard) lines up with the skelly silhouette. Misalignment = compose bug.
- **Cross-check against ajc27 (optional):** if a groundplane calibration is ever produced, run ajc27's `add_capture_cameras` on it and compare camera transforms to ours on the *same* take — they should match when groundplane alignment ≈ HIHO alignment.
- **Regression:** existing **Add Camera Videos** (row layout) and Spawn Rig untouched and still pass.
- **Lens sanity:** rendered framing through a camera matches the original clip's framing.

## 9. Open decisions / defaults (recommended, confirm if you disagree)

- **Look:** cameras + billboards + background images, all on (recommended). Easy to split into toggles later (the roadmap's "opt-in extras, off by default" note); since this is button-triggered it's already opt-in at the click.
- **Billboard distance `d`:** fixed ~1.0 m default, slider later.
- **Button:** new **Add Cameras** alongside the existing row-of-videos button (rather than replacing it), so the no-calibration fallback survives.
- **Parenting:** under the take's skelly root when present, else a standalone "HIHO MOCAP Cameras" empty.
- **Render resolution:** ajc27 sets the scene render res to cam_0's size. Hold off — that's a global scene change a student might not want from an "add cameras" click. Leave it; revisit if rendering through a camera needs it.
