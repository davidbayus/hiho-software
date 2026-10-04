# QUADRE — Phase 1: squeeze the current engine (findings + design, 2026-10-03, laptop)

**Occasion:** David: "can we pick up our dev work from where we last left off on the Quadre add-on."
This is Phase 1 of `QUADRE_EXOSIDE_PARITY_PLAN_2026-10-02.md`. It follows
`QUADRE_PHASE0_BENCHMARK_2026-10-02.md`.

**Status:** built the same evening as **v0.4.4, v0.4.5, v0.4.6 and v0.4.7**, one commit each, each
measured through the real operator before the next. Sections 2 and 3 were written first, from measurements on
throwaway copies of the add-on in the session scratch folder. Section 5 records what was built and
what it measured. **David's blind picks came in the same evening: Exoside 9, Quadre 1** (section 5.7).

---

## 1. Read this first (plain English)

Before changing anything, the test shapes were rebuilt and 0.4.3 was measured again. The numbers came
out the same as yesterday's to the digit, so everything below is measured from a known starting point.

Then the question was: where do 0.4.3's ugly quads actually sit, and why? Three findings.

**1. The engine is moody, and Quadre was taking its first answer.**
The engine lays quads out in a few dozen big patches. Small changes to the flow map it is handed move
the poles around and can skew whole patches. Yesterday's new flow map (the 0.4.0 change) helps most
shapes. On some it gives a clearly worse layout than the engine's own built-in map:

- the hand came out with sheared quads across the whole back of the hand;
- the hard-surface bracket got 152 poles where the engine's own map gives 48;
- Suzanne with symmetry got three corners in every hundred bent past 45 degrees.

Neither map wins everywhere. Across the eleven benchmark shapes, Quadre's map follows the form better
(11.6 against 12.6 degrees) and the engine's map gives squarer quads with half the poles (66 against
138). No single setting of Quadre's map was better on both counts (five were tried).

**2. The finishing pass was sanding the hard edges off.**
It squares the quads up by moving points around. It was moving points that sit ON a hard edge off that
edge, so the edge came out wavy. On the bracket that lost fifteen times more of the shape than 0.3.8
did. Points on an open border had the opposite problem: they were frozen in place.

**3. A hang or a crash inside the engine still takes Blender with it.** Known since August. Phase 0
put a time limit at the top of the Phase 1 list.

**The three changes, in the order they will be built:**

1. **Keep the lines (0.4.4).** In the finishing pass, a point on a hard edge or an open border slides
   along that line and never leaves it. Where a line has a corner, that point does not move at all.
2. **Build four layouts, keep the best (0.4.5).** Quadre draws four flow maps instead of one (its own,
   a smoother one, a stricter one, and the engine's built-in one), has the engine build quads from each,
   measures every result with the same ruler the benchmark uses, and keeps the best.
3. **The engine runs outside Blender (0.4.6).** It becomes a small separate program that Blender
   starts and watches. A hang is stopped after five minutes with a plain-English message. A crash no
   longer closes Blender. Esc stops it at once. And the four layouts are built at the same time on
   separate processor cores, so four cost about the same wait as one.

A fourth, small change came out of looking at the pictures afterwards (0.4.7, Change 4 in section 3):
the finishing pass now turns quads toward the form only where the form has a direction, which stopped
the grid lines wandering on flat faces.

**What it measured once built** (lower is better; full tables in section 5):

| Nine shapes every tool finished | Exoside 1.4 | Quadre 0.4.7 | Quadre 0.4.3 |
|---|---|---|---|
| Loops off the form (degrees) | 10.4 | 12.1 | 12.7 |
| Corners off square (degrees) | 7.9 | 7.0 | 9.0 |
| Corners bent past 45 degrees (%) | 0.43 | 0.27 | 0.91 |
| Poles | 202 | 131 | 151 |
| Sculpt detail lost | 0.39 | 0.79 | 0.77 |

In words: the quads are now squarer than Exoside's and fewer of them are badly bent. The gap in
following the form closed by about a quarter. Kept detail did not move; that gap is the adaptive
sizing in the parity plan (Phase 3), and it shows most on the film head.

And for the lines: the bracket's lost detail went from 1.81 to 0.18 (0.3.8 had 0.12, Exoside 0.90),
and its bottom edge is straight again.

**What it costs:** about one second more per run than 0.4.3.

**What this does not fix:** the two gaps named in the parity plan (Exoside sizes its quads to the
shape; the engine fills big patches with plain grids). Those are still Phase 3. This phase gets more
out of the engine as it is.

---

## 2. How the diagnosis went

Set-up: the eleven benchmark inputs were rebuilt from the private key with `bench_prep.py` into the
session scratch folder (`AB_WORK`), not the repo. All eleven reference surfaces came out byte-identical
to yesterday's. `suite_op.sh` on the untouched source gave yesterday's row exactly (Chibi 5,000 with X
symmetry: 4,776 faces, 48 poles; suite mean 11.45 / 7.68 / 0.77).

One harness oddity: the rebuilt `<code>.json` files gave different symmetry scores for seven shapes
(the hand came back as "X"). Yesterday's files were kept so every run uses yesterday's settings. Not
chased; see the open list.

### 2.1 Where the bent corners sit

Corners were sorted by how far they are from a pole or an open border (`where_bad.py`, scratch).

| Shape (0.4.3) | Corner error far from any pole or border | Exoside, same region |
|---|---|---|
| Suzanne, X symmetry | 10.8 degrees, 2.4% bent | 5.9 degrees, 0.01% bent |
| Hand | 11.1 degrees, 1.0% bent | 4.9 degrees, 0% bent |
| Film head | 6.8 degrees | 6.5 degrees |
| Chibi | 7.7 degrees | 6.4 degrees |

So on Suzanne and the hand the trouble is not at borders or poles. Ordinary quads in the middle of
nowhere are sheared. On the film head the ordinary quads are fine; the trouble is the pole count (198
against 138) and the rows next to the neck border.

### 2.2 The flow map is the cause

Same shapes, finishing pass on, only the flow map swapped:

| Shape | Quadre's map: loops / corners / bent % / poles | Engine's own map |
|---|---|---|
| Hand | 10.9 / 11.3 / 1.11 / 38 | 8.5 / 5.7 / 0.08 / 38 |
| Suzanne, X symmetry | 13.1 / 11.7 / 3.05 / 95 | 14.5 / 7.4 / 0.32 / 56 |
| Bracket | 9.9 / 6.7 / 0.23 / 152 | 10.2 / 4.0 / 0.18 / 48 |
| Film head | 14.8 / 9.5 / 2.07 / 198 | 15.5 / 7.5 / 0.60 / 96 |
| Bucket | 10.3 / 7.4 / 0.26 / 91 | 15.1 / 9.3 / 0.35 / 40 |
| Chibi, X symmetry | 11.1 / 8.0 / 0.16 / 48 | 11.5 / 9.4 / 0.29 / 48 |
| Eleven-shape mean | 11.6 / 8.1 / 0.77 / 138 | 12.6 / 7.0 / 0.28 / 66 |

Both maps are smooth and have about the same number of singular points (checked on the hand: 36 each).
The difference is where those points land. Quadre's map follows curvature at the scale of one quad, so
it reacts to knuckles and lumps; the engine then has to thread its patches between more poles, and the
patches come out skewed.

### 2.3 No single setting fixes it

Five settings of Quadre's map were run over the suite and all eleven shapes: curvature read at twice
and three times the scale, more smoothing, a weaker pull, a stricter confidence. Each trades poles for
loop-following along the same line. None is better on both.

| Setting (eleven-shape mean) | Poles | Loops off form | Corners | Bent % |
|---|---|---|---|---|
| 0.4.3 | 138 | 11.6 | 8.1 | 0.77 |
| Curvature at 2x scale | 117 | 11.9 | 8.4 | 0.66 |
| Curvature at 3x scale | 97 | 12.0 | 8.0 | 0.46 |
| Six smoothing rounds | 116 | 12.0 | 8.2 | 0.55 |
| Pull 2 instead of 5 | 112 | 12.1 | 7.8 | 0.68 |
| Confidence threshold doubled | 105 | 12.0 | 8.3 | 0.62 |
| Engine's own map | 66 | 12.6 | 7.0 | 0.28 |

### 2.4 But the best one per shape is much better

Taking, for every shape, whichever of those seven runs scored best (loops + corners):

| | Loops off form | Corners | Bent % |
|---|---|---|---|
| Suite, 0.4.3 | 11.5 | 7.7 | 0.46 |
| Suite, best of seven per case | 10.1 | 6.6 | 0.23 |
| Eleven shapes, 0.4.3 | 11.6 | 8.1 | 0.77 |
| Eleven shapes, best of seven per shape | 10.8 | 6.4 | 0.31 |

Pairing 0.4.3 with a near-copy of itself (six smoothing rounds) gains as much as pairing it with the
engine's map. So most of the gain is not "the right map for the right shape". It is the engine's
moodiness: give it several slightly different maps and one of the layouts comes out clean. Yesterday's
finding 8 said the same thing from the other side ("tiny input changes move face counts by 10% and
shift poles").

The best four of the seven (`0.4.3 + engine + six smoothing rounds + doubled confidence threshold`)
get nearly all of it (suite 10.1 / 6.8, eleven shapes 10.8 / 6.6).

### 2.5 The finishing pass and lines

| Bracket | Detail lost | Worst spot | Corners |
|---|---|---|---|
| 0.3.8 (no finishing pass) | 0.12 | 2.2 | 6.7 |
| 0.4.3 | 1.81 | 7.3 | 6.7 |
| Exoside | 0.90 | 6.6 | 6.7 |

The engine puts its points exactly on the crease and border lines it was given (measured: within a
hundredth of a quad edge, and the next-nearest points are a third of a quad away or more). The
finishing pass then moved them.

---

## 3. Design

Three changes, shipped one at a time, each measured through the real operator on the suite and the
eleven shapes before the next one starts.

### Change 1 — the finishing pass keeps the lines (0.4.4)

`quadre/relax.py` only.

1. **Read the lines.** After step 1 the engine has written its own copy of the shape (`_rem.obj`) and
   the list of crease and border edges on it (`_rem.sharp`). Open edges of that copy are added. Lines
   that lie in a mirror plane are left out: the mirror step already owns those.
2. **Which lines count.** Connected runs of edges are measured. A run shorter than four quad edges is
   a stray mark (a pinhole, a crease fragment), not a line. Found on the hand: two stray edges between
   the fingers.
3. **Which points are on a line.** A result point within 0.02 quad edges of a kept line is on it.
4. **Corners.** Where three or more line edges meet, or where a line turns more than 35 degrees, the
   point there does not move. The same goes for a point that sits on a line and on a mirror plane.
   A line's loose end is not a corner.
5. **In every round,** a point on a line moves like any other point and is then put back on the
   nearest spot of its own line (never another line that happens to run close by). It is not snapped
   to the original surface; the line is already on it.
6. Border points that are not on any kept line stay frozen, as before.

Measured with the test copy: bracket detail lost 1.81 to 0.14, worst spot 7.3 to 2.1, corners 6.7 to
6.8. Hand: the wrist rows go from 4.2 degrees off square to 0.8. Shapes with no creases or open borders
(seven of the eleven) come out identical.

Honest note: on Suzanne with symmetry this change alone makes the eye-socket rows slightly worse
(bent corners 3.05% to 3.45%). That layout is already a mess there, and holding points to the socket
rim keeps the mess from being smeared. Change 2 replaces that layout.

### Change 2 — four layouts, keep the best (0.4.5)

`quadre/flow.py`, new `quadre/score.py`, `quadre/operator.py`.

1. **Four flow maps from one reading.** The slow part of the map (reading curvature off the shape) is
   done once. From it:
   - *ours*: 0.4.3's map exactly (2 smoothing rounds, confidence threshold 1.0);
   - *smoother*: 6 smoothing rounds;
   - *stricter*: confidence threshold 2.0 (only strong curvature steers);
   - *engine*: the map the engine wrote in step 1, saved before it is overwritten.
2. **One layout per map.** Steps 2 and 3 (trace, build quads, the count retry from 0.4.2) run once
   per map. In this version they run one after the other.
3. **Measure each result** (`score.py`, numpy, 0.1 s each): loops off the form and corners off square,
   the same arithmetic as the harness ruler (`metrics.py`), read against the shape handed to the
   engine. The score is the sum of the two, in degrees. Lowest wins.
4. **Finishing pass** runs on the winner only, and always turns quads toward the *ours* map, whichever
   layout won (measured: 0.3 degrees better on loops, 0.2 worse on corners than using the winner's own
   map).
5. If a layout fails, the others still count. If Quadre's maps cannot be built at all, the engine's
   map alone is used (0.3.9 behaviour).
6. The status line says how many layouts are done.

Cost in this version: about 2 to 3 seconds per extra layout on this laptop (trace about 1 s, quads
1 to 2 s), so roughly 7 seconds more per run until Change 3 runs them side by side.

Not in the score: pole count and lost detail. Poles are a matter of taste David has not ruled on yet
(the blind sheets will say); detail cannot be read reliably before the finishing pass.

Eight layouts instead of four were also measured: corners 6.2 instead of 6.4 on the eleven shapes,
loops unchanged. Not worth twice the work.

### Change 3 — the engine in its own process (0.4.6)

New `quadre/stages.py` and `quadre/engine_runner.py`, `quadre/operator.py`.

1. **`stages.py`:** the engine steps as plain functions (rebuild; trace + quads + count retry). No
   Blender calls. Used by both paths below, so there is one copy of the logic.
2. **`engine_runner.py`:** a tiny script started with Blender's own bundled Python (`sys.executable`).
   It loads the engine, writes a "ready" marker file, runs one step, and exits with a code that says
   which step failed, if any. Checked on this Mac: the bundled Python loads the engine libraries.
3. **Step 1** runs in one child process. The flow maps and the scoring stay inside Blender on the
   worker thread (they need numpy and Blender's own maths library, and they cannot hang).
4. **The four layouts** run in four child processes at once, each in its own folder, at most one per
   processor core minus one.
5. **Time limit:** 300 seconds per child. Past that the child is stopped and the student reads:
   "QUADRE's engine got stuck on this shape and was stopped. Blender and your shape are fine..." The
   child also carries its own alarm, so one orphaned by a Blender quit cannot run forever.
6. **A crash** in the engine (it calls `exit()` on bad input) ends the child, not Blender. The student
   gets the usual "this shape confused the engine" message.
7. **Esc** stops the children at once. The old "(stopping after this step)" wording goes.
8. **Fallback:** if the child never reports "ready" (it could not start, or could not load the
   engine), the whole job runs inside Blender exactly as in 0.4.5: same four layouts, one after the
   other, same result. No time limit on that path, as today.
9. **Unchanged:** `_prep` still loads the engine inside Blender first, so the macOS "blocked" message
   still appears before any heavy work.
10. **Windows:** the child is started without a console window, and it is told where Blender's own
    runtime libraries are. Still unobserved, like everything else on Windows. The fallback is the
    safety net.

Results must not change with this change. The check is that the suite and the eleven shapes give the
same face counts and the same numbers as 0.4.5.

Tests beyond the suite: a shape that hangs the engine (the flat open grid from yesterday's finding 9)
with the limit turned down; a child killed mid-run; Esc from a second thread; the zip installed in a
sandboxed Blender window and the button pressed (`gui_test.py`).

### Change 4 — turn quads toward the form only where the form has a direction (0.4.7)

Added after looking at the 0.4.6 pictures. `quadre/flow.py`, `quadre/relax.py`, `quadre/operator.py`.

**What was seen:** on the bracket's flat faces the grid lines of 0.4.6 wander. The layout that won
there was built from the engine's map, and the finishing pass was turning its quads toward Quadre's
own map. On a flat face Quadre's map has no curvature to follow, so its direction there is arbitrary,
and it disagrees with the layout. Measured: bracket corners 4.0 degrees when the finishing pass uses
the winning layout's own map, 5.8 when it uses Quadre's.

On curved shapes the opposite holds: turning toward Quadre's map is what gains the 0.3 degrees of
loop-following in Change 2 (hand 8.5 to 8.0, film head 15.5 to 14.5).

**The change:** the finishing pass gets a "guide" instead of a bare map. It is Quadre's own map with
each direction scaled by how clearly the shape has a direction there: 0 on a flat or ball-like patch,
rising to 1 where the normal turns 0.3 radians more one way than the other across one quad, and 1 on
any triangle pinned to a crease or border. A quad is turned toward the guide by 30% times that
strength. So flat faces keep the grid the layout gave them, and curved ones are pulled as before.

Quads on the mirror line still turn all the way. If Quadre's maps could not be drawn, the engine's
map is the guide at full strength, as in 0.3.9.

---

## 4. Tried and dropped

- **One better setting of Quadre's map** (five tried, section 2.3): each trades poles for loops.
- **Eight layouts:** small gain over four.
- **Only regular points slide** (two quads at a border point, four at a crease point): slightly worse
  than letting them all slide on Suzanne and the film head, same on the hand.
- **Borders stay frozen, only creases slide:** no better on Suzanne, slightly worse on the film head,
  and it gives up the squarer rows at the hand's wrist.
- **Count accuracy in the score.** Looked at after the build: at low counts the four layouts land on
  quite different face counts (bucket, 500 asked: 926 / 950 / 798 / 585). The layout that wins on
  quality was also the closest to the typed count in five of seven low-count checks, so a count
  penalty was left out. On the open list.

## 5. As built

Four commits on the SOFTWARE repo, local, unpushed: `d92175e` (0.4.4), `4de5cf4` (0.4.5), `8a2413c`
(0.4.6), `b63baac` (0.4.7). Zip: `quadre-v0.4.7.zip`. Notes: `QUADRE_v0.4.7_NOTES_2026-10-03.md`.
Pictures: `AB_2026-10-03/` (one `LABELED_` sheet per shape with all five tools, and a fresh set of
`BLIND_` sheets, Exoside against 0.4.7, with their own `BLIND_KEY.json`).

### 5.1 Each version, real operator

Six-case suite, means:

| Version | Poles | Loops off form | Corner error | Bent corners % | Twist | Size jump | Off sculpt ‰ | Detail lost ‰ |
|---|---|---|---|---|---|---|---|---|
| 0.4.3 | 75 | 11.45 | 7.68 | 0.46 | 3.7 | 1.46 | 0.03 | 0.77 |
| 0.4.4 lines kept | 75 | 11.35 | 7.67 | 0.62 | 3.8 | 1.47 | 0.02 | 0.77 |
| 0.4.5 four layouts | 70 | 10.38 | 6.55 | 0.20 | 3.2 | 1.39 | 0.01 | 0.81 |
| 0.4.6 engine outside Blender | 70 | 10.38 | 6.55 | 0.20 | 3.2 | 1.39 | 0.01 | 0.81 |
| 0.4.7 guided turn | 70 | 10.48 | 6.27 | 0.16 | 3.2 | 1.37 | 0.01 | 0.80 |
| Exoside 1.4 | 79 | 8.4 | 7.7 | 0.32 | 2.8 | 1.55 | 0.02 | 0.41 |

All eleven benchmark shapes, means (Exoside is left out here because it failed one shape):

| Version | Poles | Loops off form | Corner error | Bent corners % | Detail lost ‰ |
|---|---|---|---|---|---|
| 0.4.3 | 138 | 11.62 | 8.05 | 0.77 | 0.85 |
| 0.4.4 lines kept | 138 | 11.58 | 8.05 | 0.80 | 0.70 |
| 0.4.5 four layouts | 112 | 10.92 | 6.65 | 0.30 | 0.73 |
| 0.4.6 engine outside Blender | 112 | 10.92 | 6.65 | 0.30 | 0.73 |
| 0.4.7 guided turn | 112 | 10.95 | 6.32 | 0.24 | 0.72 |

0.4.4 on its own raised the suite's bent corners (0.46% to 0.62%). That is one case, Suzanne with
symmetry, as the design said it would be; 0.4.5 took it to 0.20%. 0.4.6 gives the same mesh as 0.4.5
on every case, to the digit, which was its test. 0.4.7 squared the corners up a little more on every
case but one (the rounded-box student shape, 1.4 to 1.5) and moved loop-following by a tenth of a
degree either way.

### 5.2 Five tools, nine shapes all of them finished

Shapes counted: B01_chibi, B02_bucket, B03_suzanne, B04_filmhead, B05_hand, B06_firstsculpt,
B07_alientree, B09_studentA, B11_studentC. (Yesterday's table counted eight: 0.3.8 could not do the
hand. So these Exoside numbers differ a little from yesterday's.)

| Tool | Finished | Poles | Loops off form | Corner error | Bent corners % | Size jump | Off sculpt ‰ | Detail lost ‰ | Worst spot ‰ |
|---|---|---|---|---|---|---|---|---|---|
| Exoside 1.4 | 10/11 | 202 | 10.4 | 7.9 | 0.43 | 1.49 | 0.05 | 0.39 | 5.9 |
| Quadre 0.4.7 | 11/11 | 131 | 12.1 | 7.0 | 0.27 | 1.43 | 0.01 | 0.79 | 16.3 |
| Quadre 0.4.3 | 11/11 | 151 | 12.7 | 9.0 | 0.91 | 1.52 | 0.02 | 0.77 | 15.3 |
| AutoRemesher 1.2 | 11/11 | 156 | 13.4 | 8.0 | 1.94 | 1.73 | 0.24 | 1.05 | 21.6 |
| QuadriFlow | 10/11 | 101 | 16.6 | 8.8 | 0.94 | 1.26 | 0.10 | 1.17 | 24.5 |

### 5.3 Exoside against Quadre 0.4.7, shape by shape

| Shape | Loops off form (E / Q) | Corner error (E / Q) | Detail lost (E / Q) | Poles (E / Q) | Quads (E / Q) | Layout kept |
|---|---|---|---|---|---|---|
| B01_chibi | 7.0 / 9.4 | 7.2 / 5.2 | 0.27 / 0.57 | 79 / 64 | 5,956 / 5,074 | stricter |
| B02_bucket | 12.2 / 10.2 | 9.6 / 6.8 | 0.31 / 0.33 | 68 / 91 | 4,657 / 4,909 | own |
| B03_suzanne | 8.6 / 11.3 | 6.9 / 6.3 | 0.33 / 0.48 | 92 / 99 | 6,210 / 5,262 | smoother |
| B04_filmhead | 12.0 / 14.7 | 7.6 / 7.1 | 0.37 / 0.94 | 138 / 96 | 8,126 / 5,150 | engine |
| B05_hand | 5.1 / 8.1 | 5.3 / 5.5 | 0.27 / 0.45 | 40 / 38 | 5,325 / 5,029 | engine |
| B06_firstsculpt | 12.9 / 14.4 | 9.1 / 7.6 | 0.38 / 0.62 | 330 / 265 | 7,175 / 5,442 | own |
| B07_alientree | 11.7 / 14.1 | 8.4 / 8.4 | 0.40 / 0.71 | 240 / 172 | 6,807 / 5,392 | stricter |
| B08_bracket | 12.9 / 9.1 | 6.7 / 5.1 | 0.90 / 0.18 | 42 / 48 | 10,298 / 5,200 | engine |
| B09_studentA | 16.3 / 16.9 | 10.1 / 8.2 | 0.77 / 2.34 | 603 / 251 | 12,301 / 5,481 | own |
| B11_studentC | 7.9 / 9.7 | 7.1 / 7.8 | 0.41 / 0.70 | 228 / 104 | 9,016 / 5,284 | engine |

Against 0.4.3 on yesterday's weak spots:

| Shape | 0.4.3 | 0.4.7 |
|---|---|---|
| Hand: loops / corners / bent % | 10.9 / 11.3 / 1.11 | 8.1 / 5.5 / 0.05 |
| Suzanne, X symmetry: loops / corners / bent % | 13.1 / 11.7 / 3.05 | 11.3 / 6.3 / 0.11 |
| Bracket: poles / corners / detail lost | 152 / 6.7 / 1.81 | 48 / 5.1 / 0.18 |
| Film head: poles / corners / bent % / detail lost | 198 / 9.5 / 2.07 / 0.74 | 96 / 7.1 / 0.68 / 0.94 |
| Chibi, X symmetry: loops / corners | 11.1 / 8.0 | 9.4 / 5.2 |

**The one trade to look at: the film head.** The layout that won has half the poles and far fewer
bent corners, and it keeps a little less of the sculpt (0.94 against 0.74). Exoside is still clearly
ahead on that shape (it spends 8,126 quads and sizes them to the face).

### 5.4 Time

Same laptop, three runs sharing the processor (the harness runs three shapes at once):

| Shape | 0.4.4 (one layout) | 0.4.5 (four, one after another) | 0.4.6 (four, side by side) |
|---|---|---|---|
| Chibi | 9.1 s | 13.1 s | 10.5 s |
| Bucket | 8.9 s | 14.8 s | 10.5 s |
| Film head | 38.0 s | 45.2 s | 39.3 s |
| Student A (6.5M triangles) | 22.0 s | 33.1 s | 23.4 s |

With nothing else running, 0.4.3 against 0.4.6: Chibi 8.1 s against 8.7 s (two runs each), the
4.9M-triangle first sculpt 16.5 s against 17.5 s. So about one second more per run than 0.4.3.

Chibi at 25,000 quads: 20 s. In a real window from the installed zip: 9.6 s at 5,000 with X symmetry.

### 5.5 Checked

- Suite and eleven shapes through the real operator after every change.
- `ab_harness/test_child.py`, five cases, all pass: a normal run; the child process made
  unavailable (falls back inside Blender, identical mesh); a child that dies mid-step (plain failure
  message, Blender carries on); Esc during the layouts (stops in a fraction of a second, no child left
  running); and the flat open grid that hangs the engine, with the limit turned down to 8 s (stopped
  at 8.1 s with the "got stuck" message, no child left running).
- Extremes: Chibi at 500 / 10,000 with X symmetry and 25,000 without; Suzanne at 500, 2,000 with X and
  Y symmetry, 25,000 with X. All finish.
- Student's path (run for the 0.4.6 zip and again for the 0.4.7 zip): the zip installed with the real
  installer in a sandboxed Blender window, button pressed, 5,074 faces, the same as headless; the
  window stayed alive; the status line read "Step 3 of 3" before the finishing pass.
- `test_child.py` was run again on 0.4.7: all five pass.

### 5.6 Not checked

- **David's live look in his own Blender.** 0.4.7 was installed there the same evening (verified
  headless with his preferences); he has seen the pictures, not yet the add-on at work.
- **Windows.** The child process is new code that has never run there (nor has any other part of
  Quadre been observed there). If the child cannot start, the fallback runs everything inside Blender.
- **An old or slow Mac.** All timings are from the M4 laptop.
- The 300-second limit has only been exercised turned down to 8.

### 5.7 David's blind picks (2026-10-03)

Ten sheets (`AB_2026-10-03/BLIND_*.png`), Exoside against Quadre 0.4.7, shuffled as A and B. He picked
before the key was opened.

| Shape | His pick |
|---|---|
| B01_chibi | Exoside |
| B02_bucket | Exoside |
| B03_suzanne | Quadre |
| B04_filmhead | Exoside |
| B05_hand | Exoside |
| B06_firstsculpt | Exoside |
| B07_alientree | Exoside |
| B08_bracket | Exoside |
| B09_studentA | Exoside |
| B11_studentC | Exoside |

**Exoside 9, Quadre 1.** The second half of the finish line in the parity plan (he cannot reliably
tell which one is Exoside) is not met.

**What this says about the ruler.** It had Quadre ahead on corner squareness overall, and ahead in
every column on the bucket and the bracket, and he picked Exoside on both. So the ruler does not
count something his eye weighs. Two things were measured afterwards that it had left out:

- **How straight the loops run** (the bend of each edge loop at every ordinary vertex, measured in
  the surface; 0 is ruler-straight). Exoside's loops are straighter on seven of the ten shapes, and
  this measure agrees with his pick on eight of ten. The widest difference is the bracket: 1.7 degrees
  against 4.0. On most organic shapes the two are within half a degree.
- **How many quads, and how their size varies.** Exoside delivered more quads than Quadre on eight of
  the ten (up to 12,228 where 5,000 was asked) and it varies quad size far more (smaller quads on
  tight features). On the one shape he gave to Quadre the two are closest on both counts.

**His answer, the same evening.** The goal: "we want to get as close to 1:1 with exoside as possible
if not better." All three of these tipped his picks: smaller quads on tight spots, straighter and
calmer lines, loops that ring the forms. He marked up three crops:

- **Chibi neck and crotch:** "look at the areas where things tighten up". Exoside stacks thin rings
  into the neck crease and the bend between the legs; Quadre's quads stay one size.
- **Bucket:** "look at how exoside's mesh follows the details like the line moving across the center
  of the shape". Exoside lays an edge loop exactly along the crease and runs its neighbours parallel.
- **Film head chin:** "look at how the lower chin quads are adjusted to contour the general shape of
  the chin dimple detail".

So what the eye wants is quad size that follows the shape (and not evenly: thin rings stacked across a
crease, normal width along it), and loops laid on crease lines. Neither is in the ruler, and neither
can be asked of the engine as it is.

### 5.8 First experiment toward that (not shipped)

`ab_harness/exp_reshape/` (README inside). Between step 1 and the layouts, the engine's working mesh is
stretched where the surface turns fast, the engine lays its even quads on the stretched mesh, and the
quads are carried back to the real shape, where the stretched areas now have smaller quads. It runs
end to end in about a second per flow map. On the hand it brings loops and corners close to Exoside
(6.0 / 4.6 against 5.1 / 5.3; 0.4.7 has 8.1 / 5.5). On the Chibi it is worse than 0.4.7, because the
four layouts on the stretched mesh all drew worse than the one lucky plain layout, and the neck did not
get Exoside's stack of rings. The README lists what to try next, in order.

## 6. Open list after this phase

0. **Get as close to 1:1 with Exoside as possible** (David, section 5.7): quad size that follows the
   shape, loops laid on crease lines, straighter lines. The reshape experiment (section 5.8,
   `ab_harness/exp_reshape/README.md`) is the first try at the first of these without rebuilding the
   engine; its next steps are listed there. The ruler needs two new columns to steer this: loop
   straightness (`ab_harness/straight.py`, not yet in `metrics.py`) and something that sees quad size
   following the shape. And a blind round with Quadre run at the quad count Exoside actually
   delivered, so plain density is not the difference.

1. **The two gaps in the parity plan are untouched:** adaptive quad size (all of the detail gap) and
   quads following the map loosely inside big patches (most of the remaining flow gap). Phase 3.
2. **Taste, for David to rule on:** the score is loops + corners. Poles and typed-count accuracy are
   not in it. The new blind sheets are the test.
3. **A count penalty in the score** if low-count runs turn out to stray (section 4).
4. **One slow layout holds up the other three** until the 300-second limit. Not seen happen; if it
   does, give stragglers a shorter leash once one layout is done.
5. **More than four layouts** on machines with cores to spare: eight measured a little better.
6. **The finishing pass still pauses the window** for a second or two (it needs Blender's own
   closest-point lookup). The status line now says so first.
7. **The harness's symmetry verdict is not repeatable:** `bench_prep.py` rebuilt today gave different
   `sym` values for seven shapes than yesterday's saved `.json` files (the hand came back "X").
   Yesterday's files were used. Until this is found, keep the saved `.json` files when rebuilding inputs.
8. Carried: the simplify step lands at about 50K triangles when it aims for 80K; curvature is read off
   the simplified copy, not the sculpt; Windows volunteer test; materials on the result; non-ASCII paths.
