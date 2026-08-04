# Volume Map — Panel Graduation Design Note (2026-07-18)

**Status:** 1.4.29 candidate. Backlog item 3 from the 2026-07-17 session.
Graduates `diagnostics/volume_noise_map.py` (the hand-run script that produced
the first turbulence map) into a panel button.

## What it answers

"Where in my capture volume does tracking stay clean, and where does it
fray?" On 2026-07-17 the hand-run version found: clean radius ~0.75 m from
ring center, west side frays first (thin coverage toward cam4), 93 of 120
seconds of the perimeter take were inside the clean zone. That's floor-tape
knowledge — worth a button, not a Claude session.

## What the diagnostic hardcoded (and where it comes from now)

| Hardcoded | Now |
|---|---|
| Ring center (-59, 180) | mean of camera world positions from the calibration TOML |
| 6 camera world positions | from the TOML: world = -Rᵀt per camera (cv2.Rodrigues). Verified today: reproduces the hardcoded values exactly. |
| FPS 60 | `HIHO_RECORDING_INFO.json` `fps` (fallback 60) |
| Output path | `volume_map.png` + `VOLUME_MAP.txt` in the take folder |

The metrics themselves don't change — they were validated against real takes
yesterday (second-difference jitter, median over joints; rolling ~0.5s
median; 25 cm radius bins; clean radius = last bin with jitter ≤ 2× central
walking jitter).

## The change (1.4.29)

1. **`external/volume_map.py`** (new) — the generalized script. Runs in the
   freemocap env (numpy + cv2 + matplotlib all present, checked today).
   - Args: `--recording`, `--calibration`, optional `--out`.
   - Needs a PROCESSED take (body/COM/reprojection npys); missing files →
     `HIHO_ERROR::process this take first`, loudly.
   - Writes `volume_map.png` (the two-panel figure: top-down path colored by
     jitter + jitter-vs-radius curve) and `VOLUME_MAP.txt` (first line =
     badge text, then the radius-bin table).
   - Prints `HIHO_VOLMAP::<clean_radius_m|unknown>::<png path>` for the
     operator to parse. Same marker pattern as scoring.

2. **`operators/volume_map.py`** (new) — "Map the Volume" operator.
   - Take = the Process section's Take field; calibration = Calib field or
     last_successful (same resolution as Process Mocap). Caveat documented:
     if the rig moved since that take was solved, camera dots shift — in
     practice the map is run right after processing.
   - Synchronous subprocess like Check Calibration (seconds, 120s timeout).
   - On success stores one scene string prop `volume_verdict`
     ("Clean radius ~0.75 m - 13-28-17" — named take, per today's badge
     doctrine) + `volume_map_path`.

3. **Panel** — in the Process section under the quality badge:
   - "Map the Volume" button;
   - badge row with `volume_verdict` when set;
   - "Open Map" button → `wm.path_open` on the PNG (opens in Preview — zero
     window-management code, students already know Preview).

## Out of scope, logged

- Directional analysis (naming WHICH side frays — the west-finding was
  human-read off the map). A quadrant breakdown is a candidate once the map
  has more mileage; keep the analysis code identical to the validated
  diagnostic for now.
- Auto-running after every Process (the map costs seconds and means most on
  perimeter/coverage takes; a button keeps it intentional).
- In-Blender image display (Image Editor window juggling) — Preview does it
  better for students.

## Verification plan (user's path, at BASEMENT today)

Run "Map the Volume" on yesterday's perimeter take `13-28-17` — the output
must reproduce yesterday's hand-run findings: clean radius ~0.75 m, same
shape of the jitter-vs-radius curve, cam4 sitting alone out west. Then on
today's fresh take.
