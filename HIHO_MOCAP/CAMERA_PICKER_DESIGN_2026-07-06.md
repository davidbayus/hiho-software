# Camera Picker UI — Design (2026-07-06)

**Context:** Promoted from the polish backlog in the 2026-07-05 handoff. Today the
student types camera indices into a comma box (`camera_ids`, default "0,1,2,3") and
confirms with Show Cameras. USB enumeration order is NOT stable across reboots/replugs
(`project_hiho_mocap_camera_enumeration.md`): at home the laptop cam is 0, at BASEMENT
it's 4, and per-camera rotations saved in `~/.hiho_mocap/camera_rotations.json` are
keyed by index — a shuffle lands them on the wrong cameras. With 6 cameras
(2+2+2 across three USB lanes, post hub test) "preview, read the tiles, then type
numbers" becomes untenable, and the failure mode is silent garbage triangulation,
not an error.

**Decision — pick by eyes, not by hardware ID.** Two options considered:

- **A (chosen): make per-session visual confirmation trivial.** Turn the existing
  Show Cameras window into the picker: see every camera, click to include/exclude,
  click to rotate, close, done. Per-session confirmation is already doctrine
  (per-session calibration; "confirm rotation AND identity in the preview before
  recording"), so the workflow doesn't change — it just stops requiring typing.
- **B (rejected for now): stable hardware identity** (USB serial / AVFoundation
  uniqueID → index remap). OpenCV doesn't expose device IDs; identical C922s
  frequently report absent or duplicate serials; the plumbing is macOS-specific.
  Logged as a v2/adoptable-innovations candidate, not a v1.x build.

**Change (one logical change, four files):**

1. `external/record_take.py` — the preview becomes the picker.
   - `--preview` now ALWAYS detects all cameras (today it only detects-all when the
     box is blank), so an excluded/forgotten camera is always visible and re-includable.
   - New `--selected <csv>` arg carries the current panel value in; those tiles start
     INCLUDED, everything else starts EXCLUDED (dimmed + "EXCLUDED — right-click to
     include" banner; laptop face-cam gets excluded once, visually).
   - **Left-click = rotate (unchanged). Right-click = include/exclude toggle** (new).
     Two-finger click on the trackpad. Excluded cameras keep streaming so you can
     see what you're re-including.
   - Window title gains the current selection count: "recording 4 of 5 cameras".
   - On Q/ESC close: emit `HIHO_CAMERAS::<sorted csv of included>` on stdout
     (same line-marker protocol as `HIHO_DONE::`). Window closed via the X /
     killed: no marker, nothing changes in Blender.
2. `core/external_runner.py` — `_consume_line` learns the `HIHO_CAMERAS::` prefix,
   stores payload as `runner.cameras_csv` (None until seen).
3. `operators/external_capture.py` — Show Cameras passes `--selected` from
   `camera_ids`; `_poll_capture` on a finished preview with `cameras_csv` set writes
   it into `scene.hiho_mocap.camera_ids` and says so in the status line
   ("Recording cameras 0,1,2,3."). The comma box stays visible and hand-editable
   in the panel (operator-picker rule: the picker augments the visible control,
   never replaces it).
4. `ui/panels.py` — hint line under the box: "Show Cameras: right-click a tile to
   include/exclude, left-click to rotate."

**Not in this change:** hardware-ID remapping (option B); auto-excluding the laptop
cam by name (no names available through OpenCV); any change to the Record path
(it still reads the comma box); rotation storage (still `camera_rotations.json`,
still index-keyed — the picker makes wrong-rotation-after-shuffle visible and
one-click-fixable, which is the doctrine-level cure); grid layout is already
N-camera-generic (`_grid` takes the id list; 6 cams = 3×2).

**Failure behavior:**
- Zero cameras included at close → do NOT write an empty string (an empty box
  currently means "detect everything" on preview and falls back to "0,1,2,3" on
  Record — both wrong here). Keep the previous value, status line explains:
  "No cameras selected — kept 0,1,2,3."
- Preview cancelled/crashed → no marker → box untouched (fail-safe no-op,
  same principle as the GN sub-group defaults).
- New .blend resets the box to the default "0,1,2,3" (existing scene-property
  behavior, unchanged; Show Cameras before recording remains the ritual).

**Test plan:** `py_compile` all four files. Headless, no GUI needed:
- `external_runner` unit: feed `HIHO_CAMERAS::0,1,2,3` through `_consume_line`,
  assert `cameras_csv`; assert None when absent.
- `record_take` selection state machine factored into a plain function
  (toggle/include/exclude/sorted-csv-out) and tested with synthetic ids;
  `_grid` render with numpy fake frames incl. excluded-tile dimming.
- Headless Blender 5.2 `--factory-startup`: poll applies a fake finished runner's
  `cameras_csv` to the scene property; zero-selection keeps the old value.
Live validation (David's path, per `feedback_test_the_users_path.md` — Claude's
shell has no camera permission): at home with laptop cam + any C922 — exclude the
laptop by right-click, close, watch the box update; then Record and confirm only
the included camera writes an .mp4. Full 4-cam check next BASEMENT visit.
Version 1.4.23 → **1.4.24**, fresh zip via Extensions build from `SOFTWARE/`.

**Open question for David:** right-click as the toggle gesture OK? (Alternative:
hover + spacebar. Right-click recommended — discoverable from the banner text,
works as two-finger click, leaves left-click's learned meaning alone.)
