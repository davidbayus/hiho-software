# Outlier Rejection on the Process Button — Design Note (2026-07-03)

**Status:** Draft for David's sign-off. 1.4.17 candidate.
**Decision being implemented:** locked 2026-07-02 by numbers AND eyes — outlier
rejection goes on Process, default ON. A/B on take `14-10-31`: wrist jitter
−55%, feet −19%, torso negligible. David, watching the raw outlier version
next to his Butterworth-cleaned default bake: "omg... so much better."
(Dev log, 2026-07-02 close.)

## What outlier rejection is (plain language)

With four cameras looking at you, every joint's 3D position is solved by
combining all four views. If one camera has a bad frame — a blur, a
half-blocked wrist, a wrong guess — the default solve averages the bad view
in with the good ones and the joint jumps. Outlier rejection notices when one
camera disagrees with the other three and drops that camera's vote for that
joint, that frame. It's built into the FreeMoCap we already bundle
(v1.8.2); it has just been switched off the whole time — same story as the
ground plane.

## Verified facts (checked in the real freemocap-env, 2026-07-03)

- The switch: `AniposeTriangulate3DParametersModel.use_triangulate_outlier_rejection`,
  ships default `False`.
- Its neighbors (we do NOT touch these in 1.4.17, listed so the next reader
  knows they exist): `minimum_cameras_for_triangulation = 3`,
  `maximum_cameras_to_drop = 1`. With our 4-camera rig that means it can drop
  at most one bad camera and still needs three good ones — exactly the safe
  behavior we want, no tuning needed.
- The seam: `external/process_take.py` line ~126 already builds
  `params = ProcessingParameterModel(recording_info_model=recording_info)`.
  The change is setting
  `params.anipose_triangulate_3d_parameters_model.use_triangulate_outlier_rejection`
  right after that line. One file, a few lines.

## The change (1.4.17)

`process_take.py` grows one dial, following the 1.4.14 lesson (the panel
passes NO flags, so the flag's DEFAULT is what David and students actually
get — the default must be the desired behavior):

- New argument: `--outlier-rejection {on,off}`, **default `on`**.
- `on` → set the param `True` before the solve. `off` → leave FreeMoCap's
  `False` (escape hatch for future A/Bs, same spirit as the one we just ran).
- The script echoes which mode it ran (`INFO outlier rejection: on`) so the
  take's process log records it — matches the GROUNDPLANE_STATUS pattern of
  loud, on-disk truth.

**No new panel UI in 1.4.17.** One change at a time: the panel path simply
inherits the new default. If a visible checkbox ever earns its place it's a
separate build; for students, fewer knobs is the right call.

**Not touched:** the Blender-side runner (`core/external_runner.py`) passes
no new arguments — that's the point. Vendored code untouched. No new
dependencies.

## Verification plan (test the user's path)

1. Copy take `2026-07-02_14-10-31` to a fresh folder (copy, never move —
   the original and its `_OUTLIER_AB` sibling stay untouched).
2. Process the copy **from the Studio panel's actual Process button** —
   not a hand-run command.
3. Artifact-on-disk checks: solve completes, sentinel written, process log
   shows `outlier rejection: on`, and the new
   `output_data/mediapipe_body_3d_xyz.npy` matches the existing
   `_OUTLIER_AB` output (same input + same setting → same numbers).
   Claude runs the numeric comparison; David eyeballs the rig if he wants.
4. Escape hatch check (cheap, command-line): `--outlier-rejection off` on
   `--check` mode confirms the flag parses; no second full solve needed.
5. Fresh versioned zip `hiho_mocap-1.4.17.zip`, built from `SOFTWARE/`
   (correct cwd — the alpha.49 lesson), David installs.

## Cost note

The A/B reprocess ran in the same ballpark as a default solve (minutes, not
a new order of magnitude) — outlier rejection is math inside the existing
triangulation, not an extra pass over video. The 3–4× cost of 720p60 itself
is the turnaround concern already on the list; this doesn't move it.

## Out of scope, noted for later

- Per-frame timestamps and the Pose2Sim-style checks
  (`PRE_BASEMENT_CAPTURE_RESEARCH_2026-07-01.md` §6 queue).
- Whether "Smooth hands" becomes Butterworth-on-baked-curves (open design
  question from 2026-07-02).
- Any tuning of `maximum_cameras_to_drop` / reprojection targets.
