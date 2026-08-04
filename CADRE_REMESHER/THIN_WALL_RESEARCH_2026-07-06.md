# Thin Walls in Quadre — Research Doc

**Date:** 2026-07-06 (same session as v0.2.0/v0.3.0)
**Status:** Research only — no code. Proposes a preflight warning for a future v0.3.x.
**Method:** Every claim below was measured in headless Blender 5.1.2 on synthetic
cups with known wall thicknesses, plus the real bug-report bucket. Scripts in
session scratchpad.

## The question

The v0.2.0 improvements doc deferred this: "QuadWild inherently struggles with thin
double-walled shells at low target counts; a preflight 'keep Detail above X' hint
would be honest." Is that true, and what should the warning actually say?

## Finding 1 — the hypothesis was wrong about WHO struggles

QuadWild itself handles thin walls fine. Cups with walls as thin as 0.03 units were
run at Detail settings that made the quads up to **4.8× wider than the wall** — and
every result kept 100% of its volume, zero holes, zero fused walls. So "keep Detail
above X" is the wrong warning; the Detail slider is not the danger.

| cup wall | Detail | quad width vs wall | volume kept | holes |
|---|---|---|---|---|
| 0.03 | 0.25 | 4.8× wider | 100% | 0 |
| 0.03 | 1.00 | 1.4× wider | 100% | 0 |
| 0.12 | 0.25 | 1.2× wider | 100% | 0 |
| 0.12 | 0.75 | 0.5× (safe) | 100% | 0 |

## Finding 2 — the real danger is the auto-simplify step, and it fails SILENTLY

The auto-simplify (voxel remesh, runs only when a shape is over 100K triangles)
uses a voxel size computed from surface area. If that voxel is bigger than the
wall, the voxel grid can't see the cavity between the walls — it fuses them.

Measured: a dense thin cup (459K triangles, 0.025-unit walls) got a 0.028 voxel
(1.13× the wall). Result: **34% of the volume silently vanished** and 23% of the
surface area with it. No error, no warning, "Done!" — the cup just came back with
its thin parts crushed. This is exactly the failure students can't diagnose.

So the risk zone is the AND of two conditions: **dense enough to trigger
auto-simplify (>100K tris) AND walls thinner than roughly 2× the computed voxel.**

## Finding 3 — the real bug-report bucket was never a thin-wall case

Measured `ORGANIC TEST2.blend`'s original sculpt: characteristic wall ≈ 0.93 units —
about 30× the auto-simplify voxel (0.031) and 5–23× any quad Quadre produces across
the full Detail range. Its problems were 100% the density bug, fixed in v0.2.0.
Nothing about that file needs thin-wall handling.

## The cheap thickness estimate (verified usable)

For a closed shell: **characteristic wall thickness ≈ 2 × volume / surface area.**
Both numbers come straight off the bmesh (`calc_volume` + summed face areas),
costing nothing next to QuadWild. Sanity-checked: the synthetic cup built with a
0.03 solidify measured 0.0246 by this formula; the built-to-be-chunky bucket
measured 0.93. It separates the cases cleanly.

Honest limits of the estimate:
- It's a global average. A chunky character with one thin flange (an ear, a fin)
  reads as chunky. Catching local thinness would need raycast sampling — real
  research project, not a one-liner.
- Volume is meaningless on open meshes (holes to the outside). Check
  `open edges == 0` first; skip the warning otherwise.

## Proposed change (a future v0.3.x, NOT tonight)

In `_prep`, when the auto-simplify path is about to run on a closed mesh:

1. thickness = 2 × volume / area
2. voxel = the already-computed auto-simplify voxel
3. If voxel > thickness / 2 → warn in plain English:
   *"Your shape is very dense and has thin walls — the automatic simplify step may
   crush the thin parts. If the result looks melted or solid where it should be
   hollow, try simplifying your sculpt yourself first (Remesh at a small voxel
   size), then run Quadre again."*

Warn, don't block — matching the v0.2.0 preflight philosophy. A stronger fix
(capping the voxel at thickness/2 and accepting a bigger mesh into QuadWild) trades
silent damage for longer waits; worth considering only after the warning ships and
we see how often students actually hit this.

## Why not tonight

v0.3.0 (no-freeze) is tonight's one Quadre change. One change at a time.
