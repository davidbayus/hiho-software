# QUADRE v0.4.6 — keeps hard edges, picks the best of four layouts, cannot freeze Blender (2026-10-03, laptop)

**Occasion:** David, Saturday evening: "can we pick up our dev work from where we last left off on the
Quadre add-on... feel free to go hard on this for a bit." Phase 1 of the plan to match Exoside
(`QUADRE_EXOSIDE_PARITY_PLAN_2026-10-02.md`). Findings, design, and every table:
`QUADRE_PHASE1_DESIGN_2026-10-03.md`. Pictures: `AB_2026-10-03/`.

Zip: `CADRE_REMESHER/quadre-v0.4.6.zip` (Blender 5.2.0 LTS `--command extension build`). v0.4.3 kept as
the one previous zip (it is what David's Blender has); v0.3.8 moved to `SOFTWARE/ARCHIVES/OLD_ZIPS/`.
**Not installed in David's Blender** (his has 0.4.3). **Not staged for students** (the staged class
package still holds 0.4.3). Three local commits, unpushed.

## What changed (three changes, one commit each, each measured before the next)

1. **0.4.4 — the finishing pass keeps the lines.** A point the engine placed on a hard edge or an
   open border now slides along that line and never leaves it; where a line has a corner the point
   stays put. Before, hard edges came out wavy (the bracket lost fifteen times more of its shape than
   0.3.8 did) and border points were frozen. `relax.py`.
2. **0.4.5 — four layouts, the best one kept.** The engine's patch layout is touchy: the same flow
   map gives clean quads on one shape and skewed ones on the next. Quadre now draws three flow maps of
   its own, adds the engine's built-in one, builds a layout from each, measures them (loops off the
   form + corners off square), and finishes the best. `flow.py`, new `score.py`, new `stages.py`,
   `operator.py`.
3. **0.4.6 — the engine runs outside Blender.** Each engine step is a child process. A hang is
   stopped after 300 seconds with a plain-English message; a crash no longer closes Blender; Esc stops
   the work at once; and the four layouts run side by side, so they cost about what one did. If the
   child process cannot start on a computer, everything runs inside Blender as before and gives the
   same mesh. New `child.py`, new `engine_runner.py`, `operator.py`.

What the student sees: the same panel (one button, one number). The status line now reads "Step 2 of
3 — building quad layouts… (2 of 4 done)" and "Step 3 of 3 — squaring up the best layout…". One new
message, when the engine hangs: "QUADRE's engine got stuck on this shape and was stopped. Blender and
your shape are fine. Flat sheets and paper-thin shapes can do this: give the shape some thickness
(Solidify), or try Blender's Voxel Remesh first".

No new dependencies. Engine binaries untouched.

## Measured (real operator, Blender 5.2.0 LTS)

Nine benchmark shapes that all five tools finished (lower is better):

| | Exoside 1.4 | Quadre 0.4.6 | Quadre 0.4.3 | AutoRemesher 1.2 | QuadriFlow |
|---|---|---|---|---|---|
| Loops off the form (deg) | 10.4 | 12.0 | 12.7 | 13.4 | 16.6 |
| Corner error (deg) | 7.9 | 7.3 | 9.0 | 8.0 | 8.8 |
| Badly bent corners (%) | 0.43 | 0.35 | 0.91 | 1.94 | 0.94 |
| Poles | 202 | 131 | 151 | 156 | 101 |
| Sculpt detail lost (‰) | 0.39 | 0.80 | 0.77 | 1.05 | 1.17 |
| Finished, of 11 | 10 | 11 | 11 | 11 | 10 |

Six-case suite: loops off the form 11.5 → 10.4 (Exoside 8.4), corner error 7.7 → 6.6 (Exoside 7.7),
bent corners 0.46% → 0.20% (Exoside 0.32%).

Yesterday's weak spots:

| | 0.4.3 | 0.4.6 | Exoside |
|---|---|---|---|
| Hand: corner error / bent % | 11.3 / 1.11 | 5.8 / 0.05 | 5.3 / 0.02 |
| Suzanne with symmetry: corner error / bent % | 11.7 / 3.05 | 6.6 / 0.17 | 6.9 / 0.16 |
| Bracket: poles / detail lost | 152 / 1.81 | 48 / 0.18 | 42 / 0.90 |
| Film head: poles / corner error / detail lost | 198 / 9.5 / 0.74 | 96 / 7.6 / 0.94 | 138 / 7.6 / 0.37 |

Time: about one second more per run than 0.4.3 on this laptop with nothing else running (Chibi
8.1 s → 8.7 s; a 4.9M-triangle sculpt 16.5 s → 17.5 s).

## Checked

- Suite and all eleven shapes after each of the three changes. 0.4.6 gives the same mesh as 0.4.5 on
  every case.
- `ab_harness/test_child.py`: normal run; child unavailable (falls back, identical mesh); child dies
  mid-step; Esc during the layouts; the flat open grid that hangs the engine, with the limit at 8 s.
  All pass, and no child process is ever left running.
- Extremes: 500 to 25,000 quads, X and X+Y symmetry.
- Student's path: zip installed with the real installer in a sandboxed Blender window, button pressed,
  same result as headless (5,074 faces on the Chibi), window stayed alive.

## Not checked / known

- **David has not looked at any of it.** New blind sheets (Exoside against 0.4.6) are in
  `AB_2026-10-03/BLIND_*.png`; the key is `BLIND_KEY.json` in the same folder.
- **Windows.** Never observed, and the child process is new code there. The fallback is the safety net.
- **Old or slow Macs.** Timings are from the M4 laptop only.
- **The film head keeps slightly less detail than in 0.4.3** (0.94 against 0.74) in exchange for half
  the poles. Exoside is still clearly ahead on that shape.
- Detail kept overall did not move. That is the adaptive-sizing gap (parity plan, Phase 3).
- The window still pauses a second or two at the end for the finishing pass.
