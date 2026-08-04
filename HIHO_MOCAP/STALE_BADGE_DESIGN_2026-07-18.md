# Stale Badge Trap — Design Note (2026-07-18)

**Status:** 1.4.27 candidate. Same silent-state family as the process-quality
scorer bug (fixed in 1.4.26).

## The trap (found live, 2026-07-17 evening)

The Calibrate badges (Quality + Floor) are scene properties set by the last
Solve / Check Calibration, and the panel draws them any time they're
non-empty. Nothing ties them to the take named in the "Board take" field.

What happened: David recorded a NEW calibration take in the evening. The
panel still showed the morning's "Quality: Excellent (0.40px)" and "Floor:
OK" badges. Reasonable read: "it's been calibrated." It hadn't — the new
take was never solved. Nothing on the board said so.

## What's actually true when this happens

Subtlety worth preserving: after recording a new board take, the morning's
badges are still TRUE — they describe the active calibration
(`last_successful_calibration.toml`), which stays in force until a new solve
replaces it. The bug isn't that the badges are wrong; it's that they're
anonymous, so they get read as describing whatever take is in the box.

So: don't just clear the badges. **Name them, and call out the unsolved
take explicitly.**

## Disk truth

A solved board take folder contains `<take-name>_camera_calibration.toml`
(the solve writes it there, plus the calibrations folder, plus
last_successful). Presence of that file in the "Board take" folder = solved.
This check is what would have stopped the evening error cold.

## The change (1.4.27)

1. **Two stamp properties** (`properties.py`):
   - `calibration_badge_take` — which board take the Quality badge describes.
   - `groundplane_badge_take` — which board take the Floor badge describes.

2. **Solve completion** (`_poll_calibration` in `operators/calibration.py`):
   - stamp `groundplane_badge_take` = basename of the solved take folder;
   - CLEAR the Quality badge (verdict, px, stamp) — a fresh solve means the
     new calibration's quality is unknown until Check Calibration runs
     (status line already says exactly that).

3. **Check Calibration** (`operators/calibration.py`):
   - on success, stamp `calibration_badge_take` from the scored toml's
     filename (`X_camera_calibration.toml` → `X`); generic filenames
     (`last_successful_calibration.toml`) stamp "" — badge shows unsuffixed,
     never guesses;
   - on failure, clear the stamp along with the verdict (already cleared).

4. **Panel** (`ui/panels.py`):
   - Quality badge reads `Quality: Excellent (0.40 px) — 13-17-18` when the
     stamp is known (display form: basename minus the year prefix);
   - Floor badge gets the same suffix from its stamp;
   - **the trap-killer:** if the "Board take" folder is set and does NOT
     contain `<basename>_camera_calibration.toml`, draw an alert row:
     "Board take not solved yet — click Solve." This is a pure disk check,
     independent of the stamps, so it also covers legacy/blank-stamp states.

## Not doing

- Auto-clearing badges when the Board take field changes — loses the
  still-true fact that the previous calibration remains active.
- Deriving a take name for `last_successful_calibration.toml` via mtime
  correlation — guessing. Blank suffix is honest.

## Verification plan (user's path, at BASEMENT today)

1. Fresh Blender, install 1.4.27, open the panel with yesterday's state:
   Board take = an unsolved folder → alert row shows. (This is literally
   yesterday evening's scenario replayed.)
2. Solve it → Floor badge appears WITH take suffix, Quality badge clears,
   alert row disappears.
3. Check Calibration → Quality badge returns with take suffix.
4. Point Board take back at an older solved folder → no alert (toml
   present), badges keep naming their own take.
