# QUADRE v0.4.3 — flow quality, and open shapes fixed (2026-10-02, laptop)

**Occasion:** David asked for side-by-side testing against Exoside Quad Remesher on the Chibi and "a
qualitative jump in Quadre's remeshing quality." Full findings, measurements, and design:
`QUADRE_FLOW_QUALITY_DESIGN_2026-10-02.md`. Pictures and a blend with the meshes: `AB_2026-10-02/`.

Zip: `CADRE_REMESHER/quadre-v0.4.3.zip` (Blender 5.2.0 LTS `--command extension build`). v0.3.8 kept
as the one previous zip (it is what students have); v0.3.7 and the never-distributed v0.4.2 are in
`SOFTWARE/ARCHIVES/OLD_ZIPS/`. A copy of the new zip is in `SJSU_ALL/ART102_FA26/ADDONS_ASSETS/` for
the class. Installed in David's Blender 5.2.

## What changed (five changes, one commit each, each measured before the next)

1. **0.3.9 — hard edges only from the student's own geometry.** The 35-degree crease test no longer
   runs on the auto-simplified copy of a dense sculpt (it was finding hundreds of false creases).
   `operator.py`.
2. **0.4.0 — Quadre draws the flow map.** New `quadre/flow.py`: a curvature-following cross field
   written over the engine's own before step 2. Loops now ring creases such as eye sockets.
3. **0.4.1 — finishing pass.** New `quadre/relax.py`: squares the quads, turns them toward the flow,
   evens neighbouring sizes, snaps every vertex onto the original shape. Runs after step 3.
4. **0.4.2 — lands closer to the typed count.** One corrected retry of step 3 when the engine is more
   than 5% off.

5. **0.4.3 — open shapes no longer hang or shatter.** Found by the eleven-shape benchmark
   (`QUADRE_PHASE0_BENCHMARK_2026-10-02.md`): the auto-simplify step voxel-remeshed dense OPEN shapes
   (a hand open at the wrist, a head with no neck cap) into scraps. 0.3.8 then hung on the hand and
   returned fragments of the head. Voxel remeshing now runs only on watertight shapes and its output is
   checked; open shapes are edge-collapsed instead. Six-case suite unchanged to the digit.

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

Eleven-shape benchmark, five tools (averages over the eight shapes all five finished):

| | Exoside 1.4 | Quadre 0.4.3 | AutoRemesher 1.2 | QuadriFlow | Quadre 0.3.8 |
|---|---|---|---|---|---|
| Loops off the form (deg) | 11.1 | 13.0 | 14.2 | 17.5 | 17.4 |
| Corner error (deg) | 8.3 | 8.7 | 8.2 | 9.1 | 13.5 |
| Sculpt detail lost (‰) | 0.41 | 0.79 | 1.13 | 1.23 | 8.43 |
| Finished, of 11 | 10 | 11 | 11 | 10 | 10 |

## Checked

- Headless: Chibi (500 to 25,000, symmetry on and off), student bucket, Suzanne (none / X / XY),
  cube, torus, rotated + scaled cylinder, four overlapping spheres at two densities.
- Student's path: zip installed with the real installer in a sandboxed Blender window, button
  pressed, same result as headless, window stayed alive.
- Failure paths: flow-map or finishing-pass errors fall back to the engine's result (by design; not
  fault-injected today).

## Not checked / known

- **David's live look in his own Blender.** Installed there (0.4.3, verified headless with his preferences), not yet looked at by him.
- **Windows.** Still never observed running.
- **A flat open grid hangs the engine** (also in 0.3.8). On the open list. More generally the engine can still hang on input it dislikes; a time limit around it is the top Phase 1 item.
- The window pauses 1–2 s at the end while the finishing pass runs.
