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

**To run it:** copy `quadre/` somewhere, apply the four patches (`reshape_flow.patch`,
`reshape_operator.patch`, `reshape_relax.patch`, `reshape_score.patch`, made against 0.4.7, commit b63baac), drop `warp.py`
in, and point `run_quadre.py` at that copy. `QWARP_OFF=1` turns the reshaping off (this reproduces
0.4.7 exactly). Knobs: `QWARP_V=3` (version 3 below), `QWARP_TURN`, `QWARP_SMAX`, `QWARP_GROW`,
`QWARP_COUNT=adapt`, `QRELAX_EVEN`, `QRELAX_ROUNDS`.

## Blind three-way picks (2026-10-03, about 22:00)

Ten whole-shape sheets (`AB_2026-10-03/BLIND3/`, key `BLIND3_KEY.json`), A/B/C shuffled: Exoside, Quadre
0.4.7, and the version 3 setting run with the version 4 code (`QWARP_V=3 TURN=0.3 SMAX=5 GROW=0.8
COUNT=adapt QRELAX_EVEN=0`). David ranked before the key was opened.

| Shape | Best | Second | Worst | His words |
|---|---|---|---|---|
| B01_chibi | Exoside | 0.4.7 | experiment | "a center line buildup of vertices ... along the middle of the torso" |
| B02_bucket | Exoside | 0.4.7 | experiment | "buildup issues where the vertices are getting too close to one another" |
| B03_suzanne | 0.4.7 | Exoside | experiment | "this one's closer" |
| B04_filmhead | Exoside | experiment | 0.4.7 | |
| B05_hand | Exoside | experiment | 0.4.7 | "pretty darn indistinguishable" |
| B06_firstsculpt | Exoside | experiment | 0.4.7 | "a hard call" |
| B07_alientree | Exoside | 0.4.7 | experiment | "close" |
| B08_bracket | Exoside | 0.4.7 | experiment | both Quadres: "the lines aren't straight ... zigzagging" |
| B09_studentA | experiment | 0.4.7 | Exoside | "hard to tell" |
| B11_studentC | experiment | (0.4.7 or experiment, not ranked) | | Exoside's column: "some weird doubling up of vertices" |

**Firsts: Exoside 7, experiment 2, Quadre 0.4.7 1. Experiment against 0.4.7 head to head: 5 to 5.**
The experiment wins where the shape has fine organic detail (film head, hand, first sculpt, two
student sculpts) and loses on clean, smooth or hard-edged shapes (Chibi, bucket, Suzanne, alien tree,
bracket). What he named against it is crowding: vertices bunching up, along the centre line on the
Chibi and in patches on the bucket.

**The Chibi in this test was damaged by a change made after he first saw it.** Checked afterwards
(same camera, torso crop): the version 3 result he called "overall better" earlier in the evening has
a clean centre line; the one in the blind sheet has quads slanting into the centre line and piling
up there. Same setting, later code (the mirror-plane changes and the new fold repair came in between).
So one of those changes, or the layout draw, did this, and it has to be found before anything else.

**What this says:** shrinking quads is worth something on detailed organic shapes and costs
something on clean ones, and the cost is crowding. Not a step forward as it stands. Next, in order:
(1) find what put the pile-up on the Chibi's centre line; (2) stop the crowding: no stretch on shapes
or regions that do not need it (bracket, bucket), and a floor on how close lines may get; (3) the
bracket's zigzag is in 0.4.7 too and is a separate job (straight lines on flat faces).

## Version 4 (2026-10-03, night): the crotch, and neck and face at the same time

Setting: `QWARP_V=3 QWARP_TURN=0.45 QWARP_POWER=2 QWARP_SMAX=4 QWARP_GROW=0.8 QWARP_EVEN_TURN=0.35
QWARP_EVEN_MAX=1.5 QWARP_COUNT=adapt QRELAX_EVEN=0`. Pictures: `AB_2026-10-03/EXP_RESHAPE_V4/`
(four columns: Exoside, 0.4.7, version 3, version 4).

**What was wrong with the crotch in version 3.** Not the crotch itself. The legs are round enough that
version 3's rule (one-directional stretch wherever a quad spans more than 0.3 radians) stretched them
all the way down, around the leg only. That made thin upright strips, and the strips ran up into the
torso and pinched at the leg roots. Seen from underneath, Exoside does two different things: on rounded
forms (legs, arms) its quads get evenly smaller and stay square; at real creases (neck, between the
legs) they get thin one way only. Version 4 does the same:

- **Even part:** where the surface turns more than `EVEN_TURN` per quad, both directions are stretched
  alike, up to `EVEN_MAX`. Legs and arms come out with smaller square quads.
- **Crease part:** the one-directional stretch now rises steeply (`POWER` 2) past `TURN`, so gentle
  roundness asks for nothing and a crease gets the full `SMAX`.

**Two more faults fixed in `warp.py`:**

- A kink along the centre line of mirrored shapes (lines met the mirror plane at a slant, in a V).
  The stretched surface was free to meet the plane at a slant. Points on the plane may now only turn
  about the plane's own axis, which is what the other half would agree to.
- Fold repair no longer gives up the whole stretch when a few folds remain: it halves the stretch
  around the fold first, and as a last resort turns the whole stretch down (60%, 35%, 15%).

**What it measured** (5,000 typed; quads / loops / corners / detail lost / worst spot):

| | 0.4.7 | version 4 | Exoside |
|---|---|---|---|
| Chibi, X symmetry | 5,074 / 9.4 / 5.2 / 0.57 / 14.0 | 6,576 / 9.6 / 7.6 / 0.35 / 12.3 | 5,956 / 7.0 / 7.2 / 0.27 / 3.7 |
| Bucket | 4,909 / 10.2 / 6.8 / 0.33 / 3.9 | 5,335 / 11.6 / 7.5 / 0.29 / 3.4 | 4,657 / 12.2 / 9.6 / 0.31 / 2.4 |
| Film head, X symmetry | 5,150 / 14.7 / 7.1 / 0.94 / 14.1 | 8,486 / 13.3 / 9.0 / 0.43 / 9.2 | 8,126 / 12.0 / 7.6 / 0.37 / 4.6 |
| Hand | 5,029 / 8.1 / 5.5 / 0.45 / 6.1 | 6,709 / 7.6 / 5.7 / 0.22 / 1.8 | 5,325 / 5.1 / 5.3 / 0.27 / 2.3 |

**In the pictures:** Chibi neck has a stack of rings, the crotch has loops around the bend, arms and
legs have smaller square quads, the centre line is straight. Film head: mouth and chin clean, one
small torn spot at the inner corner of the eye.

**David's verdict on the version 4 sheets (2026-10-03, about 21:40): "no in fact i would say the
current install is better than the experiment, especially on the eyes."** He is right, and the
sheets above missed it because they only cropped the places the work was aimed at. Close-ups of the
eyes afterwards: the Chibi's eye socket is packed with thin slivers, its rim has lost its shape and
the lines around it wander; the film head's eyes are smeared and partly collapsed, where 0.4.7 keeps
both lids. So version 4 is a step back overall, whatever the neck and crotch look like, and the
"detail lost" column did not catch it either. Lesson for the next round: judge whole shapes and the
places that were NOT being worked on before showing crops of the places that were.

**Tried and dropped on the way:** `TURN` 0.6 with no even part (crotch good, neck and face lost their
detail); `SMAX` 6 (film head: a notch at the mouth and a wrinkle by the nostril, and the fold repair
ran six times per map); a "quad too big for its spot" term in the score (`span` / `over` in
`score.py`, printed per candidate): it separates stretched from plain layouts clearly but does not
tell the four stretched layouts apart, so it is not used in the pick.

**Still open, in order:**

1. The small torn spot at the film head's inner eye corner (carry-back or a fold repair seam).
2. Time: film head 34 s to 54 s. The fold repair re-solves from scratch each try.
3. It delivers more quads than Exoside on three of four shapes (Chibi 6,576 against 5,956). The
   even part is the knob (`EVEN_MAX`).
4. The layout lottery: which of the four layouts wins still changes how calm the big surfaces are.
5. Only four shapes run. The other seven, the six-case suite, other Quad Counts: not run.
6. Crease lines as engine features (the bucket crop): not started.
7. Before it ships: a design section in the Phase 1 doc, then one change per commit.

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
