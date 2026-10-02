# QUADRE v0.4.2 — flow quality (2026-10-02, laptop)

**Occasion:** David asked for side-by-side testing against Exoside Quad Remesher on the Chibi and "a
qualitative jump in Quadre's remeshing quality." Full findings, measurements, and design:
`QUADRE_FLOW_QUALITY_DESIGN_2026-10-02.md`. Pictures and a blend with the meshes: `AB_2026-10-02/`.

Zip: `CADRE_REMESHER/quadre-v0.4.2.zip` (Blender 5.2.0 LTS `--command extension build`). v0.3.8 kept
as the one previous zip; v0.3.7 moved to `SOFTWARE/ARCHIVES/OLD_ZIPS/`. A copy of the new zip is in
`SJSU_ALL/ART102_FA26/ADDONS_ASSETS/` for the class.

## What changed (four changes, one commit each, each measured before the next)

1. **0.3.9 — hard edges only from the student's own geometry.** The 35-degree crease test no longer
   runs on the auto-simplified copy of a dense sculpt (it was finding hundreds of false creases).
   `operator.py`.
2. **0.4.0 — Quadre draws the flow map.** New `quadre/flow.py`: a curvature-following cross field
   written over the engine's own before step 2. Loops now ring creases such as eye sockets.
3. **0.4.1 — finishing pass.** New `quadre/relax.py`: squares the quads, turns them toward the flow,
   evens neighbouring sizes, snaps every vertex onto the original shape. Runs after step 3.
4. **0.4.2 — lands closer to the typed count.** One corrected retry of step 3 when the engine is more
   than 5% off.

Nothing in the panel changed. No new dependencies (numpy ships with Blender). Engine binaries
untouched.

## Measured (six-case suite, real operator, Blender 5.2.0 LTS)

| | 0.3.8 | 0.4.2 | Exoside 1.4 |
|---|---|---|---|
| Loops off the form (deg) | 15.9 | 11.5 | 8.4 |
| Corner error (deg) | 12.6 | 7.7 | 7.7 |
| Badly bent corners (%) | 1.75 | 0.46 | 0.32 |
| Vertices off the sculpt (‰) | 0.47 | 0.03 | 0.02 |
| Sculpt detail lost (‰) | 1.18 | 0.77 | 0.41 |

Chibi, 5,000 quads, X symmetry: 112 poles → 48; delivered 6,122 → 4,776.

## Checked

- Headless: Chibi (500 to 25,000, symmetry on and off), student bucket, Suzanne (none / X / XY),
  cube, torus, rotated + scaled cylinder, four overlapping spheres at two densities.
- Student's path: zip installed with the real installer in a sandboxed Blender window, button
  pressed, same result as headless, window stayed alive.
- Failure paths: flow-map or finishing-pass errors fall back to the engine's result (by design; not
  fault-injected today).

## Not checked / known

- **David's live look in his own Blender.** Not installed there.
- **Windows.** Still never observed running.
- **A flat open grid hangs the engine** (also in 0.3.8). On the open list.
- The window pauses 1–2 s at the end while the finishing pass runs.
