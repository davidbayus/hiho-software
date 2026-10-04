# QUADRE — plan for matching Exoside's quality (draft, 2026-10-02, laptop)

**Status:** Phase 0 is done (same day): results in `QUADRE_PHASE0_BENCHMARK_2026-10-02.md`, waiting on
David's blind picks and markup. Phases 1 to 4 are not built. Follows the v0.4.2 work recorded in
`QUADRE_FLOW_QUALITY_DESIGN_2026-10-02.md`.

**Update 2026-10-03: Phase 1 was built as v0.4.4 to v0.4.6**, but not as the four items listed under
Phase 1 below. The diagnosis found bigger wins elsewhere (`QUADRE_PHASE1_DESIGN_2026-10-03.md`): the
finishing pass now keeps hard edges and borders, Quadre builds four layouts and keeps the best, and
the engine runs outside Blender with a time limit (the item Phase 0 put first). On the nine shapes all
tools finish: loops off the form 12.7 to 12.0 (Exoside 10.4), corners 9.0 to 7.3 (Exoside 7.9), detail
lost 0.77 to 0.80 (Exoside 0.39). Corners are now ahead of the finish line; loops and detail still
need Phase 3. The four items below (curvature from the real sculpt, the simplify step's aim, crease
detection on the original, finishing pass version 2) were not built and stay open; the measurements
say none of them is where the remaining gap is.

**What Phase 0 changed in this plan:** (a) it found and fixed a hang / shatter bug on dense open
shapes (v0.4.3); (b) Phase 2's question is mostly answered: neither AutoRemesher nor QuadriFlow is a
better base, one check left (AutoRemesher plus Quadre's finishing pass); (c) Phase 1 gets a new first
item, a time limit around the engine, and a sharper target list: hard-surface pole count, symmetry on
shapes with borders or creases, the open-shape path's rougher corners, faces.

---

## 1. Read this first (plain English)

After today, two things separate Quadre from Exoside. Everything else is level or ahead.

**Gap 1: Exoside changes quad size to fit the shape. Quadre uses one size everywhere.**
Exoside's "Adaptive Size" (on by default, 50%) puts small quads where the shape is tight (eye-socket
rims, the neck, fingertips) and big quads on the flat parts. That is why its rims look crisp and why it
keeps more of the sculpt. I measured this directly by turning Adaptive Size off in Exoside:

| Chibi, Quad Count 5000, X symmetry | Exoside default | Exoside, Adaptive Size off | Quadre 0.4.2 |
|---|---|---|---|
| Loops off the form (degrees) | 6.8 | 8.2 | 11.1 |
| Corners off square (degrees) | 7.0 | 8.4 | 8.0 |
| Sculpt detail lost | 0.27 | 0.54 | 0.59 |

With Adaptive Size off, Exoside loses detail at the same rate Quadre does, and its corners are slightly
worse than Quadre's. So adaptive sizing is the whole detail gap and about a third of the flow gap.

**Gap 2: Quadre's quads follow its own flow map only loosely.**
The flow map Quadre draws is good (4.5 degrees off the form). The quads the engine builds from it are
11 degrees off. The engine cuts the surface into a few dozen big patches and fills each one with a plain
grid, so inside a patch nothing steers the quads. This is the other two thirds of the flow gap.

**Already level or ahead:** corner squareness, points sitting on the sculpt, neighbour size evenness,
fewer poles (48 against Exoside's 75 on the Chibi).

**The plan in one line:** measure wider first, squeeze what is left out of the current engine, test
whether a different free engine is a better base, then take ownership of the engine so adaptive sizing
can be built into it.

**What "same quality" will mean (the finish line):**

1. On the test set, against Exoside at its default settings: loops off the form within 1 degree, detail
   lost within 20%, corners at least as square.
2. David's eye: in a blind side-by-side of the test set, he cannot reliably pick which one is Exoside.

---

## 2. The phases

Each phase ends with the suite run through the real operator and a go / no-go from David. One change
at a time inside each phase.

### Phase 0 — widen the measurement (1 session, no code changes to Quadre)

Today's verdict rests on one simple character, one bucket, and Suzanne. Before more engine work:

- **More test subjects, about ten:** a real face (nose, lips, ears), a hand with fingers, a clothed
  figure, one hard-surface piece, two or three real student sculpts from A1, something of David's from
  the film (a HEAD blend). David picks them; they become the permanent benchmark.
- **David marks up what he sees.** The ruler measures flow, squareness, and fidelity. It does not know
  what a rigger wants around a mouth or a shoulder. His notes on the sheets become new checks.
- **Blind sheets:** same camera, labels hidden, so his picks are not steered.
- **Measure the neighbours too:** Blender's built-in QuadriFlow and AutoRemesher 1.2, same ruler, so
  the next phases start from facts.

*Needs from David:* the test subjects, and an OK to download AutoRemesher (MIT licensed, from its
GitHub releases page).

### Phase 1 — squeeze the current engine (1 to 2 sessions, no engine rebuild)

Four changes, smallest first:

1. **Read curvature from the real sculpt, not the simplified copy.** The flow map currently reads the
   voxel copy, which has stair-step artifacts. Sample the original's normals instead.
2. **Fix the simplify step's aim.** It asks for 80K triangles and lands near 50K, so the engine starts
   from a blurrier copy than intended.
3. **Find real creases on the original and pin loops to them.** A crease detector that works at quad
   scale on the original sculpt (long, continuous, strongly bent lines only), fed to the engine as hard
   edges. This is what makes a rim crisp without adaptive sizing.
4. **Finishing pass, version 2.** Today's pass nudges each quad toward the flow on its own. Version 2
   solves all the quads together (one alignment solve per round), which should turn loops further
   without the zigzags that stopped today's pass at 30%.

*Expected:* loops off the form from about 11.5 to about 10; crisper creases; detail lost from 0.77 to
about 0.65. This phase does not close either gap. It is the cheap part.

### Phase 2 — is there a better free engine to stand on? (1 session, decision gate)

QuadWild (the engine inside Quadre) fills big patches with plain grids. That design is the root of
Gap 2 and it has no sizing control, which is Gap 1. Before investing in rebuilding it:

- Run **AutoRemesher 1.2** (MIT, Apple Silicon native, has a command-line mode with a target quad
  count, and lists "anisotropic quad sizing" as a feature) through the full suite, raw and with
  Quadre's finishing pass on top.
- Same for **QuadriFlow**, already inside Blender.

**Gate:** if another engine plus our finishing pass beats QuadWild plus our finishing pass on the
suite and to David's eye, Phase 3 changes shape: Quadre gets a second engine (run as a separate
process, which also ends the "engine crash takes Blender down" problem) and the QuadWild rebuild
shrinks or drops. If not, Phase 3 goes ahead as written.

### Phase 3 — own the engine (3 to 5 sessions)

Rebuild QuadWild-BiMDF from source (the upstream tree was refreshed in August 2026 and compiles on
current toolchains; keep the build GPL-clean: no Blossom-V, no Gurobi). Then change it:

1. **Build pipeline first.** Mac universal on the laptop; Windows and Linux through GitHub Actions on
   the public repo. Nothing else in this phase ships until all three build and the suite matches
   today's numbers with the unmodified source.
2. **Adaptive sizing (Gap 1).** The quad-layout step currently takes one edge length for the whole
   shape. Give each patch its own target, driven by the curvature Quadre already measures. Add an
   "Adaptive Size" slider to the panel, defaulting to Exoside's 50%, so the class demos match.
3. **Let the engine's working copy grow with the Quad Count.** It is fixed at about 10K triangles
   today, which caps accuracy at high counts.
4. **Smaller patches / tighter tracing (Gap 2).** Expose the tracer's settings so patches follow the
   flow map more closely.
5. **Robustness, while in there:** the flat-open-grid hang found today, the hard crash on bad input
   (the engine calls exit instead of reporting), and run the engine as a separate process.

*Expected:* detail lost to Exoside's level; loops off the form to about 9.

### Phase 4 — only if Phase 3 lands short on flow

Replace the patch-and-grid step with a global parametrisation (an "integer-grid map"), the approach
where every quad follows the flow map by construction. This is the heavy option: new C++ libraries, a
new solver, weeks rather than sessions. Not worth planning in detail until Phases 1 to 3 show how
much gap is left.

---

## 3. Order, effort, and what could go wrong

| Phase | Effort | Closes | Main risk |
|---|---|---|---|
| 0 Measure wider | 1 session | nothing; makes the target honest | New shapes may show problems today's suite hides |
| 1 Squeeze | 1–2 sessions | a little of both gaps | Crease detector fires on sculpt noise (same failure as the old angle test) |
| 2 Other engines | 1 session | decision only | AutoRemesher may be better on some shapes and worse on others, giving no clean answer |
| 3 Own the engine | 3–5 sessions | Gap 1, part of Gap 2 | The Windows build. Nobody has seen Quadre run on Windows even today |
| 4 New extraction | weeks | rest of Gap 2 | Large, and may not be needed |

**Recommendation:** do Phases 0, 1 and 2 before deciding anything about 3. They are cheap, each one
ships something or settles a question, and Phase 2 can change what Phase 3 is.

**Things this plan does not cover** (Exoside features that are about control, not mesh quality):
painting density with vertex colours, guiding loops with materials or normals, Z symmetry, keeping
materials on the result.

## 4. Decisions for David

1. Go on Phase 0, and which shapes go in the benchmark.
2. OK to download AutoRemesher for the Phase 0 / Phase 2 measurement.
3. Whether an "Adaptive Size" slider belongs in the panel when it exists (the panel is one button and
   one number today, on purpose).
4. Whether Windows students can be asked for one volunteer test before Phase 3.
