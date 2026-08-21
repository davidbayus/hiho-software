# Unlock Feet — A/B toggle for Lock Feet (design, 2026-08-12)

## Where this came from

David's first live eyeball pass on Lock Feet (1.4.44, this morning, laptop):
"good start. TBH hard to compare without an 'unlock' toggle." The artist's
verdict on a correction tool comes from flipping between before and after —
Ctrl+Z technically does it but breaks the moment anything else is clicked,
and students won't juggle undo. Comparison is not a convenience here: the
rung-2 decision (XY pinning) rides on David being able to SEE what vertical
locking did and didn't fix.

## Shape

One button slot in Studio §2 that toggles by state:

- Not locked → **Lock Feet** (magnet on)
- Locked      → **Unlock Feet** (magnet off) — restores the exact pre-lock curves

Toggle any number of times, including during playback. Dials keep working
exactly as before (redo panel).

## Mechanism

Lock Feet already reads every marker's curves into numpy before editing them.
The change: before the first lock of a take, keep a copy of those arrays —
that copy IS the raw take. Store in operators.STATE (RAM):

    STATE["lock_feet_stash"] = {
        "take":   <skelly root name>,      # which take the stash belongs to
        "arrays": {marker: 3xN copy},      # every gathered marker, pre-lock
        "locked": bool,                    # current toggle position
    }

- **Lock Feet** — if a live stash exists for this take and it is locked,
  restore the originals into the working arrays first, then lock with the
  current dials (idempotent re-lock: clicking Lock twice, or moving a dial,
  can never lock twice or poison the stash). Otherwise snapshot fresh, lock,
  mark locked.
- **Unlock Feet** — write the stashed arrays back through the same
  foreach_set path, mark unlocked, keep the stash (so Lock again = instant).
- One stash total: locking a different take replaces it. ~7 MB RAM for a
  60 s take — nothing.

## Honest limits (also the tooltip teaching)

- The stash lives in RAM: it survives undo and file-saves but dies when
  Blender closes. The raw take itself is never touched on disk, so the
  fallback is always: **Load Take again = raw take back.** Unlock's error
  when there's no stash says exactly that.
- After Bake the empties no longer drive the rig — Unlock then only moves
  the empties. Same warning pattern Lock Feet already uses (_rig_is_baked).
- Known cosmetic edge, accepted: Ctrl+Z after locking reverts curves while
  STATE still says "locked" — the button reads Unlock, clicking it rewrites
  the same raw values. Harmless, not chased.

## Non-goals

No XY changes (rung 2), no .blend persistence, no multi-take stash history.

## Test plan (before David touches it)

Headless, on a copy of REFILTERED60, connector-independent:
1. lock → unlock → every fcurve array byte-equal to pre-lock. 
2. lock → lock (double-click) ≡ single lock from raw (idempotence).
3. unlock with no stash → friendly error, nothing modified.
4. key counts + frame numbers untouched throughout.
Then live: David toggles during playback, judges plants + sideways skate.

## Files touched (one change)

`operators/lock_feet.py` (stash + Unlock operator + one report sentence),
`panel/studio_panel.py` (conditional button), `__init__.py` + manifest
(register + version 1.4.45).
