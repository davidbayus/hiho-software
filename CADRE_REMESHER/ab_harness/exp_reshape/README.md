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

**To run it:** copy `quadre/` somewhere, apply `reshape_flow.patch` and `reshape_operator.patch`
(made against 0.4.7, commit b63baac), drop `warp.py` in, and point `run_quadre.py` at that copy.
`QWARP_OFF=1` turns the reshaping off; `QWARP_TURN`, `QWARP_SMAX`, `QWARP_COUNT=adapt` are the knobs.

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
