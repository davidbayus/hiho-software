# QUADRE — Flow Quality: A/B against Exoside, findings, and design (2026-10-02, laptop)

**Occasion:** David: "do side by side testing between Exoside Quad Remesher and Quadre... study the
differences in quad flow and quad uniformity... our goal is a qualitative jump in Quadre's remeshing
quality."

**Test subject:** the Chibi sculpt (`Cube.001`, 1.44M quads) inside
`SJSU_ALL/ART102_FA26/CHIBI_LOWPOLY_BASE.blend`, the sculpt the class `CHIBI_LOWPOLY_BASE.obj` was
retopologized from. Supporting cases: the student bucket (`BUG_REPORTS/ORGANIC TEST2.blend`,
`Roundcube.001`) and Suzanne at subdivision 3.

---

## 1. Read this first (plain English)

Both tools were run on the same sculpt with the same Quad Count and the same symmetry setting, then
measured with the same ruler and rendered from the same camera.

**What Exoside does that Quadre 0.3.8 did not:**

1. **Its loops follow the form.** Rings go around the arms, legs, neck, and eye sockets. Quadre's loops
   wandered diagonally (the "chevron" pattern down the Chibi's torso and a mess inside the eye sockets).
2. **Its quads are square.** Quadre's were sheared into parallelograms.
3. **Every vertex sits exactly on the sculpt.** Quadre's vertices floated off the surface, because
   the engine only ever sees a simplified copy.
4. **Fewer poles** (the spots where 3 or 5 edges meet instead of 4): 75 against Quadre's 112.

**Why Quadre was doing that (three causes, all on our side of the engine):**

1. **Fake hard edges.** Quadre marks every edge sharper than 35 degrees as a crease the flow must
   follow. Fine on a clean model. But a dense sculpt first goes through an automatic simplify step, and
   that step leaves hundreds of tiny false creases. The engine dutifully bent the flow around every one.
   This alone caused most of the poles and the eye-socket mess.
2. **The engine's flow map ignores soft creases.** It is good on tubes (arms, legs) but treats a rounded
   crease like the eye-socket rim as nothing special.
3. **No finishing pass.** The engine hands back quads that are sheared and sitting on its own rough
   copy of the shape. Nothing squared them up or put them back on the real sculpt.

**The fix (three changes, same engine, no new dependencies):**

1. Only look for hard edges on the student's own geometry, never on the auto-simplified copy.
2. Quadre draws its own flow map: follow the shape's curvature where the shape clearly has a direction
   (creases, tubes), stay as smooth as possible everywhere else, and hand that to the engine.
3. A finishing pass after the engine: square the quads up, turn them toward the flow, even out
   neighbouring sizes, and snap every vertex onto the original sculpt.

**Result on the six-case suite (lower is better everywhere):**

| Measure | Quadre 0.3.8 | New recipe | Exoside 1.4 |
|---|---|---|---|
| Loops off the form (degrees; random = 22.5) | 15.9 | 10.3 | 8.4 |
| Quads badly off the form (% over 20 degrees) | 32 | 16 | 11 |
| Corner angle error (degrees from square) | 12.6 | 7.7 | 7.7 |
| Badly bent corners (%) | 1.75 | 0.38 | 0.32 |
| Quad twist (degrees) | 4.9 | 3.3 | 2.8 |
| Neighbour size jump (95th percentile ratio) | 1.54 | 1.43 | 1.55 |
| Vertices off the sculpt (per mille of size) | 0.47 | 0.01 | 0.02 |
| Sculpt detail lost (per mille of size) | 1.18 | 0.72 | 0.41 |

Chibi alone at 5,000 quads with X symmetry: poles 112 → 48 (Exoside 75), corner error 12.6 → 6.1
(Exoside 7.0), loops now ring the eye sockets with poles at the four corners, the way Exoside's do.

**Still behind Exoside:** it follows the form a little better (8.4 against 10.3), and it uses smaller
quads where the shape is tight (its "Adaptive Size"), which keeps more detail at low counts. Both are
on the open list in section 6.

---

## 2. How the test was run

Harness: `CADRE_REMESHER/ab_harness/` (headless Blender 5.2.0 LTS, one script per job).

- **Exoside** is driven the way its own Blender bridge drives it: FBX out, `xremesh -s
  RetopoSettings.txt`, FBX in. Defaults: Adaptive Size 50%, Adapt Quad Count on, Detect Hard Edges on.
  The engine only accepts the bridge's own exchange folder (`/var/tmp/Exoside/QuadRemesher/Blender`).
- **Quadre 0.3.8** runs through the real operator from source (`--factory-startup` + `sys.path`).
- **Experiments** run through `exp_quadre.py`, a parametrised copy of the operator's pipeline. Its
  default settings reproduce the shipped operator exactly (6,122 faces on the Chibi, same as the
  operator).
- **Reference surface:** the sculpt, collapse-decimated to 150K triangles.

Measures (`metrics.py`):

- **Poles:** interior vertices where the edge count is not 4.
- **Loops off the form:** for each quad, the angle between the quad's two axes and the sculpt's
  principal curvature directions, measured at the quad's own scale (how the surface normal turns across
  one quad). Only quads where the shape clearly has a direction are counted. 0 is perfect, 22.5 is
  random.
- **Corner angle error / badly bent:** mean distance of each corner from 90 degrees; share of corners
  more than 45 degrees off.
- **Twist:** angle between the two triangles of each quad.
- **Neighbour size jump:** area ratio of quads that share an edge (the local uniformity students see).
- **Off the sculpt / detail lost:** distance result → sculpt at the vertices, and sculpt → result.

Renders (`render.py`): same camera, wireframe, poles marked (red = 3 edges, blue = 5).

## 3. Findings, in the order they were found

1. **The engine never sees the sculpt.** Dense input is voxel-remeshed to ~50K triangles (the formula
   aims for 80K and lands low), then the engine re-triangulates to ~10K (hard-coded in the binary:
   `ExpectedEdgeL`, `MinFaces=10000`). The flow map, the patches, and the final vertex positions all
   live on that 10K copy.
2. **Angle creases on the voxel copy are noise.** On the Chibi half: 191 real border edges + 186 crease
   fragments. Dropping the fragments: poles 112 → 48, corner error 12.6 → 8.8. On the un-simplified
   Suzanne the 35-degree creases are real and help, so the rule is "not on the simplified copy", not
   "never".
3. **The engine's own flow map is decent on tubes (7 degrees off the form) but blind to soft creases,**
   and `alpha` in `Parameters` is not read by this build (`alpha_curv=0.3`, `curv_thr=0.8` are
   hard-coded in `remeshAndField`).
4. **The engine accepts a replacement flow map.** `trace2` reads `<mesh>_rem.rosy` from disk, so
   overwriting that file between step 1 and step 2 swaps the map with no binary change.
5. **The engine's smoothing knobs in `QRParameters` do nothing in this build** (six settings, identical
   output). The ILP knobs do respond. Any finishing pass has to be ours.
6. **Quads follow the flow map loosely.** The map is 4.5 degrees off the form, the quads built from it
   11. The engine cuts the surface into a few dozen big patches and fills each with a plain grid, so
   inside a patch nothing steers the quads. A finishing pass that turns each quad toward the map
   recovers part of that.
7. **Count accuracy rides on the crease count.** With the fake creases gone, asks land closer (Chibi
   5,000 → 5,180 instead of 6,122; 1,500 → 1,870 instead of 2,664).

## 4. Design

Three changes, shipped one at a time, each measured on the suite through the real operator.

### Change 1 — creases only from the student's own geometry (v0.3.9)

`operator.py`, `_prep`: when the shape went down the auto-simplify path, skip the 35-degree test.
Borders, the symmetry cut, seams, material borders, and face-set borders stay (those are the
student's own marks). Un-simplified shapes behave exactly as before.

### Change 2 — Quadre's own flow map (v0.4.0)

New module `quadre/flow.py`, pure numpy plus `mathutils.kdtree`. Runs on the worker thread between
step 1 and step 2. If anything in it fails, the engine's own map is left in place.

1. Read the engine's remeshed triangles (`_rem.obj`) and its border/crease list (`_rem.sharp`).
2. **Curvature at quad scale.** For each triangle, sample the smoothed normal of the prep mesh a
   half-quad step either side along two tangent axes. The difference is how the surface bends across
   one quad: a 2x2 shape operator, giving a direction and a strength (`|k1 - k2| x quad size`).
   Two rounds of neighbour averaging calm the sampling noise.
3. **Confidence.** `min(strength / 1.0, 1)^2`. Only places where the normal turns clearly more one way
   than the other get a say. Flat and ball-like areas get none. (Softer confidence put poles in the
   middle of the forehead; this setting puts them at the eye-socket corners.)
4. **Solve.** Standard 4-direction cross field: each triangle holds a complex number `e^(i4θ)`,
   neighbours are compared through the shared edge, confident triangles are pulled to their curvature
   direction (weight 5), border and crease triangles are pinned to their edge. One sparse linear
   system, solved by conjugate gradient in numpy (10K unknowns, ~200 iterations, 0.3 s).
5. Write the result over `_rem.rosy`.

### Change 3 — finishing pass (v0.4.1)

New module `quadre/relax.py`, numpy on the main thread in `_finish`, on the half mesh before the
mirror step. 60 rounds of:

1. For each quad, build its best-fit rectangle: same centre, same two side lengths, axes = the nearest
   square frame to the quad's own axes.
2. Turn that rectangle 30% of the way toward the flow map (fully, for quads touching the mirror line,
   so loops cross the centre line square).
3. Blend each quad's size halfway toward the average of the quads around it.
4. Move each vertex to the average of the corners its quads want.
5. Snap to the original object with `closest_point_on_mesh`. A snap is refused if it would move the
   vertex more than one quad-edge away or onto a surface facing the other way (thin walls).
6. Mirror-line vertices stay on the mirror plane. Open-border vertices do not move.

If the original object is gone, or the pass fails, the engine's result is used as is.

Cost: 1–2 s at 5,000 quads. For large counts the snap runs every few rounds instead of every round,
to hold the main-thread pause near that.

### Change 4 — land on the typed count (v0.4.2)

`Job.run`, step 3: after the engine builds the quads, compare the face count with the ask. If it is
more than 8% off, rescale the density by `sqrt(got / asked)` and run step 3 once more (0.3–1 s). Keep
whichever is closer.

## 5. What was tried and dropped

- Collapse-decimate instead of voxel for the simplify step: 16 s instead of 2, and its crease
  fragments are worse (522 poles).
- Smoothing the voxel copy: no gain.
- Stronger pull to the flow map in the finishing pass (100%): better on the ruler, visible zigzags.
- Softer curvature confidence: poles land mid-forehead.
- The engine's `HALF` flow config, other `alpha` values: no gain or worse.
- Curvature from the engine's own 10K triangles: works, but quad-scale sampling from the prep mesh is
  steadier.

## 6. Open list (not built today)

1. **Adaptive quad size** (Exoside's default): smaller quads where the shape is tight. Biggest
   remaining difference at low counts.
2. **Quads still follow the map loosely inside big patches.** A real fix means steering the engine's
   patch layout or adding a parametrisation step.
3. **Creases on a simplified sculpt** are followed by the flow map but not pinned by an edge loop, so a
   crisp rim rounds slightly. A robust crease detector on the original sculpt would let them be pinned.
4. **The simplify step lands at ~50K triangles when it aims for 80K.**
5. Blender's built-in QuadriFlow was not measured (script error, not chased).
