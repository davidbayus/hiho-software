# Experiment: quads that shrink where the shape tightens (2026-10-03, not shipped)

Prototype only. It is not part of the add-on. Written after David's blind picks (Exoside 9, Quadre 1)
and his markup: Exoside's quads get smaller where the shape tightens (the Chibi's neck and crotch, the
film head's chin), and Quadre's are all one size.

**The idea.** The engine makes every quad the same size and cannot be told otherwise without a rebuild.
So between step 1 and the layouts, the engine's working mesh (`_rem.obj`) is reshaped: stretched where
the surface turns fast. The engine lays even quads over the reshaped mesh. Each quad vertex is then
carried back to the real shape through the triangle it sits on (same triangle, same position inside
it). Stretched areas come back with smaller quads.

**How (version 2, `warp.py`).** One reshaped mesh per flow map. Around each vertex the mesh is
stretched along the map's two directions, each by how fast the surface turns along it (no quad should
span more than `TURN_PER_QUAD` = 0.45 radians either way, stretch capped at `MAX_SCALE` = 2). The
reshaping is an as-rigid-as-possible solve with that stretch as the target (numpy, about 1 s per map).
The map is carried onto the reshaped triangles so the engine traces the same directions. Version 1
scaled both directions alike (`QWARP_ISO=1` reproduces it).

**To run it:** copy `quadre/` somewhere, apply the three patches (`reshape_flow.patch`,
`reshape_operator.patch`, `reshape_relax.patch`, made against 0.4.7, commit b63baac), drop `warp.py`
in, and point `run_quadre.py` at that copy. `QWARP_OFF=1` turns the reshaping off (this reproduces
0.4.7 exactly). Knobs: `QWARP_V=3` (version 3 below), `QWARP_TURN`, `QWARP_SMAX`, `QWARP_GROW`,
`QWARP_COUNT=adapt`, `QRELAX_EVEN`, `QRELAX_ROUNDS`.

## Version 3 (2026-10-03, late session): the neck gets its rings

Setting used for every picture and number below:
`QWARP_V=3 QWARP_TURN=0.3 QWARP_SMAX=5 QWARP_GROW=0.8 QWARP_COUNT=adapt QRELAX_EVEN=0`.

**Why versions 1 and 2 gave the neck one tall ring.** Three separate causes, each found by looking
at the close-up next to Exoside's:

1. The bending was read across a whole quad and then smoothed, so a crease read as a mild bend one
   quad wide: at most one extra ring. Version 3 reads the bending over a quarter of a quad edge
   (`fine_bending`), and then lets the stretch spread outward from each tight spot and fade with
   distance (`stretch_tensors_graded`, fading by 1/e over `GROW` quad edges). That fading is what
   makes a stack of rings that grow back to full size, instead of one small ring.
2. The typed count was held, so shrinking one place starved another. `QWARP_COUNT=adapt` keeps the
   typed quad size on the plain areas and lets the tight areas add quads (Exoside does the same:
   5,956 quads on the Chibi for 5,000 typed).
3. The finishing pass evens out neighbouring quad sizes (`SIZE_EVEN`). With graded sizes that is
   wrong; the runs below switch it off (`QRELAX_EVEN=0`).

**Three faults that showed up once the stretch was strong, all fixed in `warp.py`:**

- The stretched mesh folded along the mirror plane (90 folded triangle pairs on the film head).
  Mirror-plane points were being clamped after each solve; now that coordinate is taken out of the
  solve, and the stretch at those points is made the same on both sides of the plane. 90 folds to 6.
- Remaining folds: `reshape_safe` gives up the stretch around any fold and solves again (up to 4
  tries; if it still folds, that map is left unstretched).
- Where the stretched mesh passes through itself (two lips pressed together), carrying a quad
  point back picked the wrong lip, and the mouth came out torn. Reshaping only ever stretches, so a
  quad edge that comes back longer than it went in gives a wrong pick away; those points try the
  other triangles within reach (`carry_back`). Points on the mirror plane are put back on it.

**What it measured** (Quad Count 5,000 typed; quads delivered / loops off the form / corners off
square / detail lost / worst spot):

| | 0.4.7 | version 3 | Exoside |
|---|---|---|---|
| Chibi, X symmetry | 5,074 / 9.4 / 5.2 / 0.57 / 14.0 | 6,250 / 9.8 / 5.6 / 0.34 / 11.3 | 5,956 / 7.0 / 7.2 / 0.27 / 3.7 |
| Bucket | 4,909 / 10.2 / 6.8 / 0.33 / 3.9 | 5,330 / 10.1 / 7.9 / 0.28 / 2.5 | 4,657 / 12.2 / 9.6 / 0.31 / 2.4 |
| Film head, X symmetry | 5,150 / 14.7 / 7.1 / 0.94 / 14.1 | 7,312 / 14.6 / 9.7 / 0.50 / 11.2 | 8,126 / 12.0 / 7.6 / 0.37 / 4.6 |
| Hand | 5,029 / 8.1 / 5.5 / 0.45 / 6.1 | 6,210 / 7.4 / 6.8 / 0.22 / 2.2 | 5,325 / 5.1 / 5.3 / 0.27 / 2.3 |

**Read:** "detail lost" was the one gap Phase 1 could not move (0.79 against Exoside's 0.39 over nine
shapes). On these four it goes from 0.57 to 0.34 on average, against Exoside's 0.31. Corners get a
little less square (stretched quads are oblong by design, and the ruler counts that against them).
Pictures: `AB_2026-10-03/EXP_RESHAPE_V3/` (NECK, CROTCH, FACE, BUCKET, HAND, WHOLE). In the
pictures: the film head's nose, lips and chin now read like Exoside's; the Chibi's neck has three or
four rings where Exoside has six; **the crotch is not right** (thin upright strips down the inside of
the legs instead of rings wrapped around the bend).

**Still open, in the order I would take them:**

1. The crotch: find out why the stretch there runs along the legs instead of around the bend.
2. The layout lottery is still there. The same setting gave a better Chibi neck on one run than
   another, depending on which of the four layouts won. The score (loops + corners) does not see
   quad size at all. Give it a term that does, and add the plain layouts as candidates.
3. Only four shapes were run. The other seven, the six-case suite, and other Quad Counts (500 to
   25,000) have not been.
4. The fold repair and the carry-back fix cost time on the film head (36 s to 49 s). Not tuned.
5. The finishing pass's travel and snap limits are measured in average quad edges; with quads a
   fifth of the average size they are loose. No damage seen yet.
6. Crease lines as engine features (the bucket crop): not started.
7. Before any of it ships: a design section in the Phase 1 doc, then one change per commit.

## Versions 1 and 2 (2026-10-03, early session)

**What it measured** (Quad Count 5,000; loops off the form / corners off square / detail lost / worst spot):

| | 0.4.7 | version 1 (even scale) | version 2 (along the map) | Exoside |
|---|---|---|---|---|
| Hand | 8.1 / 5.5 / 0.45 / 6.1 | 6.7 / 6.1 / 0.35 / 3.0 | 6.0 / 4.6 / 0.43 / 9.2 | 5.1 / 5.3 / 0.27 / 2.3 |
| Chibi, X symmetry | 9.4 / 5.2 / 0.57 / 14.0 | 11.4 / 5.8 / 0.51 / 13.1 | 11.7 / 8.3 / 0.54 / 13.6 | 7.0 / 7.2 / 0.27 / 3.7 |

**Read:** it works end to end and the hand gets close to Exoside. The Chibi gets worse, for a reason
that is not the reshaping itself: only 3% of its surface asks for any stretch, but the four layouts
built on the reshaped mesh all happened to come out worse than the one lucky plain layout 0.4.7 kept
(scores 26 to 32 against 19.4). The engine's layout lottery again. And in the picture the neck did not
get Exoside's stack of thin rings.

**Not tried yet, in the order I would try them:**

1. Reshaped layouts as extra candidates next to the four plain ones (eight in all), so a bad draw
   cannot make things worse.
2. A score that rewards what the reshaping is for (the ruler's "detail lost", or small quads where
   the surface turns fast). Today's score (loops + corners) is blind to it.
3. More stretch at sharp creases (cap 3 instead of 2) and adding quads instead of holding the typed
   count (`QWARP_COUNT=adapt`), which is what Exoside does by default.
4. Running the engine's step 1 again on the reshaped mesh, so its triangles are even there too
   (stretched triangles may be part of why layouts get worse).
5. Crease lines as engine features: snap a chain of working-mesh edges onto each strong crease and
   add it to `_rem.sharp`, so a loop runs exactly along it (David's bucket crop).
