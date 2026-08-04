# Quadre No-Freeze — Design Doc

**Date:** 2026-07-06 (same session as the v0.2.0 improvements — this is the deferred structural item)
**Problem:** "Clean Up My Shape" freezes Blender for minutes on a real sculpt. Students think it crashed and force-quit. The bug report said exactly this.
**Version this ships as:** Quadre v0.3.0 (structural change → minor bump)

## Why it freezes

The operator's `execute()` runs three heavy native QuadWild calls back-to-back on
Blender's main thread — `remeshAndField()`, `trace()`, `quadrangulate()`. While they
run, Blender can't redraw, so the whole app beachballs.

## Why a background thread is safe here

Verified by reading `lib/__init__.py`: the QuadWild wrapper is pure `ctypes` + file
reading — it never touches `bpy`. Python's `ctypes` releases the interpreter lock
during native calls, so a worker thread running these calls leaves the main thread
free to redraw. Only one job can run at a time (enforced), so the native library is
never called from two threads at once — same serialization as today, just off the
main thread.

## The split (what runs where)

**Phase 1 — Prep (main thread, fast, seconds):** everything that touches Blender data.
Evaluate modifiers, auto-decimate copy, loose-geometry cleanup, piece counting,
rotation/scale bake, symmetry bisect, sharp-edge marking, triangulate, export the OBJ
and sharp-feature files. Ends by packaging a plain-Python job object: file paths, the
target face count from the slider, symmetry flags, the original object's name and
location, the piece count.

**Phase 2 — Heavy work (worker thread, minutes):** the three QuadWild stages, plus the
density solve (reads the intermediate OBJ file — no bpy). The job records which stage
it's on and when it started. Between stages it checks a cancel flag. Any exception is
caught and stored on the job, never raised into nowhere.

**Phase 3 — Finish (main thread, fast):** when the worker ends, the modal timer sees it
and — on success — imports the result OBJ, creates the `_clean` object, applies the
mirror if symmetry was on, hides the original, reports the same "Done!" message as
v0.2.0. On error: the same friendly error report as v0.2.0. On cancel: report
"Cancelled — your shape is untouched."

## What the student sees

- Button press → button greys out (poll returns False while a job runs).
- Status bar + a line in the QUADRE panel: **"Step 1 of 3 — rebuilding the surface… 12s"**,
  then "Step 2 of 3 — tracing quad flow…", then "Step 3 of 3 — building the final quads…".
  The timer tick tags the viewport for redraw so the seconds visibly count up —
  living proof Blender is not frozen.
- **ESC cancels.** Honest limitation: a native call can't be interrupted mid-flight,
  so ESC means "stop after the current step". The status line says so:
  "Stopping after this step…".
- Blender stays fully usable — orbit, tweak, read the panel — while Quadre works.

## Fallback path (headless / scripting)

`invoke()` (button press with a window) runs the modal version. `execute()` (script
call, or `--background` with no window) runs everything synchronously exactly like
v0.2.0. This keeps every existing headless test runnable and gives scripts a blocking
call, which is what scripts want.

## Failure & safety notes

- **One job at a time:** class-level running flag; poll blocks re-entry.
- **Native crash risk unchanged:** if QuadWild segfaults it takes Blender down today
  and it still would — the thread doesn't change that. Nothing new to warn about.
- **Undo:** the result object is created on the main thread at finish;
  REGISTER/UNDO stays; the undo step lands when the modal ends.
- **Blender quit mid-job:** worker is a daemon thread; it dies with Blender; temp
  files live in Blender's session tempdir which Blender cleans up.

## Test plan (headless 5.1.2, then David live)

1. **Regression, sync path:** dense sphere + the real bug-report bucket
   (`BUG_REPORTS/ORGANIC TEST2.blend`, slider 0.64) through `execute()` — must
   match v0.2.0 counts (~9.0K faces, stable on re-clean).
2. **Thread liveness:** run prep on the main thread, stages in a worker, and have the
   main thread count poll ticks while the worker grinds. Many ticks during the heavy
   stage = the lock really is released = the UI really would stay live.
3. **Cancel:** request cancel during stage 1, verify stages 2–3 never run and no
   result object appears.
4. **Error:** point the job at a nonsense file, verify the stored error surfaces as
   the friendly message, running flag resets, button un-greys.
5. **David, live (the user's path):** install the v0.3.0 zip, run on a heavy sculpt,
   confirm the seconds tick, orbit the viewport mid-run, try ESC once. Headless can't
   prove UI feel — only this step can.

## Out of scope

Progress *percentage* within a QuadWild stage (the library doesn't report it),
running multiple jobs, and interrupting a native call mid-flight.
