# Lock Feet (Foot Locking) — Design — 2026-08-11

**What this is.** Design for surfacing foot locking as a one-button HIHO panel step
— rung 0 of `MOCAP_CORRECTION_RESEARCH_2026-08-11.md`, blessed by David the same
day ("let's get that part of the workflow going, we can test it out on our best
take footage"). The algorithm already exists in the vendored ajc27 baseline;
`SMOOTHING_RESEARCH_PRIOR_ART_2026-08-04.md` §2.5 recommended surfacing it as a
standard pipeline step. This doc translates that into HIHO's actual architecture.

**Target build: 1.4.44. One change, one zip, tested on the 2026-08-01 perimeter
walk (`HIHO_CAPTURES/2026-08-01_17-22-03_REFILTERED60`) before anything else.**

---

## Why a port, not a call

Shipped zips exclude `vendor/` (audit M16, 2026-06-09 — the ajc27 self-installer
is retired; `core/` is self-sufficient). So the addon cannot invoke
`bpy.ops.freemocap._foot_locking` at runtime. The move is the same one the rest
of the addon already made: port the algorithm into `core/`, credit ajc27 in the
header, operate on our own `hiho_*` empties and slotted actions. AGPL-3.0 → 
AGPL-3.0.

## What the algorithm does (plain English)

While you walk, each foot takes turns being planted on the floor. The capture
never quite agrees — a planted heel wobbles a centimeter up and down. This tool
finds every stretch where a heel or toe stays below a height threshold long
enough to be a real plant, and holds it at floor height for that stretch, easing
in and out so nothing pops. Then it re-solves the ankle so the foot's bones keep
their true lengths, and (optionally) lets the knee, hip, and upper body absorb
the tiny shift so the whole character stays honest.

## Where it lives

**Studio panel, section 2 (Preview), one row under Play: `Lock Feet`.** The
artist loop is: play the take, see skating, click Lock Feet, play again. It
edits the tracking empties (pre-bake surface), so it must run before Bake —
same slot the smoothing research assigned it: *filter positions → foot-lock →
bake → per-region rotation smoothing*.

Fine-tuning lives in the operator's redo panel (F9 / bottom-left collapse), not
in the panel — the panel stays one verb.

## Pieces

1. **`core/foot_locking.py`** (new; pure numpy, no bpy) — `lock_feet(markers,
   ...) -> stats`. Markers = `{name: (3, N) array}` of empty locations in
   keyframe-index space. Ports: contact-window detection, quadratic ease in/out,
   below-ground clamp for short contacts, ankle re-solve by central-difference
   gradient descent (called values: lr 1e-4, tol 1e-7, max 5000) against the
   take's own median ankle→toe / ankle→heel lengths, knee+hip compensation
   coefficient, upper-body steadying (hips_center := avg of hips; delta applied
   to every non-leg marker).
2. **`operators/lock_feet.py`** (new) — `HIHO_MOCAP_OT_lock_feet`. Finds the
   skelly root from `last_processed_path` (same derivation as Spawn Rig), reads
   the `hiho_*` empties' location fcurves (channelbag-aware, same recipe as
   `output_rig`), runs the core, writes values back with frame numbers
   untouched, reports counts.
3. **`panel/studio_panel.py`** — the one row.
4. Registration + version bump (`__init__.py`, `blender_manifest.toml`).

## Controls (redo panel; plain words, few numbers)

| Control | Default | Meaning |
|---|---|---|
| Feet | Both | Both / left only / right only |
| Contact height | 0.02 m | Below this, a heel/toe counts as touching down |
| Floor height | 0.0 m | Where planted markers are held (floor calibration puts the floor at 0) |
| Knees absorb | 1.0 | How much the knee+hip take up the ankle's shift (ajc27 semantics) |
| Steady the body | On | Carry the hip shift through the whole upper body |

Frame-count parameters are **derived from the take's real fps**, not exposed:
minimum hold = fps/3 (⅓ s — ajc27's 10 frames at their 30 fps default), ease
in/out = fps/6 each. Hardcoded frame counts at 30 fps was exactly the 1.4.34
bug class; never again.

## Deviations from the ajc27 original (all deliberate, all documented)

a. **Keyframe-index space.** The original mixes scene frames and array indices
   and rewrites key frame-numbers to 0..N-1 on write-back (renumbers takes whose
   keys start at frame 1). We operate purely on key indices and preserve the
   original frame numbers.
b. **fps-scaled defaults** (above) instead of fixed frame counts.
c. **`lock_xy_at_ground_level` dropped** — read but never used in the vendored
   operator body (dead upstream); we don't port dead switches.
d. **Missing markers are skipped, not crashed on** — a take with an untracked
   marker gets locking for what exists plus an honest report line.
e. **Upper-body steadying is set-based** (every marker except the two legs'
   chains and hips_center) instead of hierarchy recursion — same member set,
   no KeyError class, covers hand/face markers regardless of tracking state.
f. **Ease guards** — windows shorter than the ease counts degrade gracefully
   (linear, then single-frame set) instead of hitting a singular matrix.
g. **Exact ankle solve instead of gradient descent** — found during the oracle
   run on the perimeter walk (2026-08-11). Upstream's GD (lr 1e-4, tol 1e-7)
   produces steps below its own tolerance on real-world gradients, so it never
   leaves its initial guess of foot-height + 0.1 m: the ankle gets parked at
   ~10 cm on every plant frame (+14 mm lift, left ankle→heel median 94.1 →
   106.5 mm, a rhythmic body bob at walk cadence). The objective's derivative
   is cubic in ankle-z, so we solve it exactly (np.roots) and keep the
   physical root nearest the current ankle height — deterministic, no pop,
   and the 25 s solve loop drops to ~1 s. Worth reporting upstream alongside
   the other findings (UPSTREAM_NOTES pattern); their operator has the same
   under-step.

## Guards (silent-failure doctrine)

- No take loaded / skelly root missing → "Load a take first — Lock Feet works
  on the tracking empties, before Bake."
- Foot markers absent → error naming exactly which.
- Rig present but no `HIHO_` constraints (already baked) → still runs on the
  empties, but the report warns: re-Spawn and lock before Bake to see it on
  the rig.
- Report always states what changed: windows locked per foot, frames planted,
  frames clamped, body-steadied frame count.

## Test protocol (before David's eyeball pass)

Headless, `--factory-startup`, addon from the tree, on the REFILTERED60
perimeter walk:
1. Spawn the take; snapshot heel/toe/ankle curves.
2. Run Lock Feet with defaults.
3. Oracle checks: (i) ≥ some contact windows found on each foot for a walk
   take; (ii) inside each locked plateau, planted marker Z variance == 0 at
   floor height, XY untouched; (iii) ankle→heel and ankle→toe median lengths
   preserved within 1%; (iv) key counts and frame numbers byte-identical;
   (v) no NaNs anywhere; (vi) markers outside the changed set untouched.
4. Bake smoke: Bake Animation completes; rig ankle Z over a locked window is
   flat (constraints carried the lock through).
5. David: load the walk, Lock Feet, Play — the eyeball verdict is the real one.

## Out of scope (rungs 1+)

Range fixes, pinning, correction zones — all gated on their own design doc per
`MOCAP_CORRECTION_RESEARCH_2026-08-11.md`. This build only makes feet stop
skating.
