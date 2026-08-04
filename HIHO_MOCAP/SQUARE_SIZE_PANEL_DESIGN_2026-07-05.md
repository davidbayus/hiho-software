# Charuco Square Size as a Panel Setting — Design (2026-07-05)

**Context:** BASEMENT session, first varied-heights calibration (0.35px, groundplane OK).
David tape-measured the house Skelly Shop board: **one black square = 110mm**, 5 squares
along the long edge (the board's own printed edge text confirms `squares_x=5, squares_y=3`).
Every calibration to date passed the hardcoded `--square-mm 100`
(`operators/calibration.py:171`), so every solve so far is uniformly ~10% small.
Harmless for retargets, wrong for real-world distances (camera heights, floor scale).
David's call: **a value slot in the panel's Calibrate section, default 110.**

**Change (one logical change, three files + scorer plumbing):**
1. `properties.py` — new scene property `charuco_square_mm` (FloatProperty,
   default **110.0**, min 10, max 500, precision 1). Saved with the scene like the
   other panel fields.
2. `ui/panels.py` — one prop row in the Calibrate block, under "Board take":
   `Square size (mm)`.
3. `operators/calibration.py` — Solve passes `--square-mm <value>` from the property
   instead of the literal `"100"`. Check Calibration passes the same value to the
   scorer via `run_score` (new optional `square_mm` arg in
   `core/calibration_quality.py` → `--square-mm` to `external/score_calibration.py`,
   which already accepts it). **Solve and score must use the same number** — the
   scorer builds its 3D board from this value, so a mismatch would inflate the
   reprojection error and corrupt the verdict.

**Not in this change:** the board shape stays hardcoded `5x3` (we own exactly one
board). If a 7×5 board ever enters the kit, shape becomes an enum next to this field.
External scripts keep their CLI defaults at 100.0 — the panel is the student path and
always passes the flag explicitly, so the CLI default is inert for students; changing
it is a separate decision.

**Failure behavior:** none new — value is clamped by the property min/max; blank is
impossible (FloatProperty). Old takes re-solved with 110 simply come out true-scale.

**Test plan:** `py_compile` on the three edited files; headless Blender 5.2
`--factory-startup` (addon from source, David's install untouched): property exists,
default 110.0, Solve arg construction yields `--square-mm 110`; scorer cmd includes
the same. Version 1.4.22 → **1.4.23**, fresh zip via Extensions build.
Live validation: re-solve today's 13-00-16 BASEMENT take — groundplane heights should
land ~1.1× the 100mm solve (1.33/1.25/1.72/0.74m expected), reprojection px unchanged,
then compare against David's tape-measured lens heights.
