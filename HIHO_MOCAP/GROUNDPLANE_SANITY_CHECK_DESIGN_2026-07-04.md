# Groundplane Sanity Check (1.4.21) — Design Note (2026-07-04)

**Status:** David approved the queue item 2026-07-04 ("do 1–3 on your own");
this note records the decisions before code.
**Trigger:** the 2026-07-03 evening incident — the charuco groundplane picked
the wrong side of the planar pose ambiguity, reported OK, and put all four
cameras underground. Reprojection scored GOOD while the world was upside
down. Detection method proven by hand that night and re-verified today:
camera heights in the calibration's own world frame (good solve: all ~+1.6m;
flipped solve: −0.5 to −2.2m — reproduced exactly from both TOMLs on disk).
Research context: `FOUR_CAM_OPTIMIZATION_RESEARCH_2026-07-03.md` §2c
(OpenCV planar two-fold ambiguity; undocumented upstream).

## Decision

`external/calibrate.py` grows a post-solve check, run ONLY when the
groundplane solve reports success (when groundplane fails, positions are in
the camera-0 frame where height means nothing):

1. Parse the solved TOML (`tomllib`, stdlib). Per camera: rotation rvec →
   matrix (`cv2.Rodrigues`), camera center = −Rᵀ·t, height = center z (mm).
2. **If any camera height ≤ 0 (at or below the floor), the world is flipped.**
   `GROUNDPLANE_STATUS.txt` and the `HIHO_INFO::groundplane` line become:
   `FAILED: world is flipped upside down (camera heights read <list>m — all
   cameras should be ABOVE the floor). The board was seen too small or too
   edge-on. Re-record calibration with the board's opening spot central and
   large in every camera's view.` — same FAILED-loudly convention as the
   1.4.12 groundplane status; the existing status stream carries it.
3. Otherwise append `; cameras above floor at <list>m` to the OK status —
   the heights become part of the calibration's on-disk record (David's
   drift-checking habit gets the numbers for free).

**Deliberately NOT checked: height consistency between cameras.** The
6-camera plan staggers cameras across three height bands (0.7–2.2m,
`SIX_CAMERA_SCALING_RESEARCH_2026-07-04.md`), so a spread test would
false-alarm on the future rig. Above-floor is the invariant that survives
every layout.

**Deliberately NOT auto-fixed.** Flipping the solve back is possible in
principle but is new geometry code on the student path; the honest v1 move is
loud failure + the ritual fix (bigger/more central board). The auto-fix
belongs upstream (FreeMoCap report queued once this check is field-tested).

**Failure containment:** the check wraps in try/except — a TOML parse hiccup
must never fail an otherwise good calibration; on exception the status gains
`(height check skipped: <reason>)` instead.

## Test plan

Standalone (no cameras needed — pure post-processing of TOMLs on disk):
- Good fixture `HIHO_CALIBRATIONS/2026-07-02_14-02-02` → OK + heights ~1.6m.
- Flipped fixture `HIHO_CALIBRATIONS/2026-07-03_15-14-56` → FAILED loudly.
Test harness calls the extracted check function directly on both TOMLs
(the solve itself is upstream code we don't re-run at home).

David's path: next BASEMENT calibration shows heights in the status; if a
flip ever recurs, the panel says FAILED at solve time instead of David's
eyes catching it an hour later.

**Version:** 1.4.21.
