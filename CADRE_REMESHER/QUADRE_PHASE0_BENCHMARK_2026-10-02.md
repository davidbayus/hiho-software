# QUADRE — Phase 0: the wider benchmark (2026-10-02, laptop)

**What this is:** Phase 0 of `QUADRE_EXOSIDE_PARITY_PLAN_2026-10-02.md`. Eleven shapes instead of three,
five remeshers instead of two, same ruler, same camera. David said "go ahead with phase 0, yes download
autoremesher."

Pictures: `AB_2026-10-02/PHASE0/` — one `LABELED_<shape>.png` per shape (all five tools) and one
`BLIND_<shape>.png` per shape (Exoside and Quadre 0.4.3 as A and B, order shuffled; the answers are in
`BLIND_KEY.json` in the same folder, so do not open that until after picking).

---

## 1. Read this first (plain English)

**1. The wider test found a real bug, in the version students have.** Two of the eleven shapes are open
shells (the film head has no neck cap, the hand is open at the wrist). Quadre's auto-simplify step turns
a dense open shape into scraps. On the hand, 0.3.8 then **hung forever**. On the film head, 0.3.8
"finished" and delivered **scattered fragments of lips and ears**, reporting 13,272 faces as if nothing
were wrong. Fixed today as **v0.4.3**: open shapes are simplified a different way. Both now come out
whole (hand in 8 s, head in 30 s).

**2. Quadre 0.4.3 is the best of the free tools, and second to Exoside.** Averages over the eight
shapes that every tool finished (lower is better):

| | Exoside 1.4 | Quadre 0.4.3 | AutoRemesher 1.2 | QuadriFlow | Quadre 0.3.8 |
|---|---|---|---|---|---|
| Loops off the form (degrees) | 11.1 | 13.0 | 14.2 | 17.5 | 17.4 |
| Corners off square (degrees) | 8.3 | 8.7 | 8.2 | 9.1 | 13.5 |
| Sculpt detail lost | 0.41 | 0.79 | 1.13 | 1.23 | 8.43 |
| Finished all 11 shapes | 10 | **11** | **11** | 10 | 10 |

**3. The gap to Exoside is smaller on real sculpts than on the Chibi.** This morning's Chibi number was
Exoside 7 against Quadre 11 on flow. Across the wider set it is 11.1 against 13.0. On messy, lumpy
sculpts (the first-class sculpt, the alien tree, student A) the two are within one or two degrees, and
Quadre's corners are squarer on two of the three. On the bucket Quadre is ahead on both. The gap is
widest on clean, smooth shapes: the Chibi, Suzanne, the hand.

**4. Part of Exoside's detail advantage is that it does not give you the count you asked for.** Asked
for 5,000, it delivered between 4,657 and 12,301 (its "Adapt Quad Count" is on by default). Quadre
delivered between 4,765 and 5,486. More quads keep more detail.

**5. Nobody is perfect.** Exoside failed outright on one student shape ("Remeshing Failed", with and
without symmetry). QuadriFlow refused the hard-surface part. AutoRemesher finished everything but
left non-quads in 10 of 11 results, mangled open borders, and needed its target raised 1.5 to 3 times
to land near the count.

**6. Where Quadre is weakest, shape by shape** (this is the Phase 1 to-do list, in order):

- **Hard surface (the bracket):** 152 poles against Exoside's 42, and twice the detail lost. Hard edges
  are found, but the flow around them is busy.
- **Suzanne with symmetry:** corners 11.7 degrees off square. Without symmetry this morning the same
  shape scored 6.8. Something about symmetry plus open borders or creases is costing five degrees.
- **The hand:** corners 11.3 against Exoside's 5.3. This is the open-shape path (edge collapse), which
  hands the engine a rougher copy than the voxel path does.
- **The film head:** 198 poles against 138, loops a little busier around the mouth and brow.
- **Thin flappy shapes (student A):** detail lost 2.35 against 0.77, though Exoside spent 12,301 quads
  to Quadre's 5,481.

**What this does to the plan:**

- **Phase 2's question is mostly answered.** Neither free alternative is a better base than what
  Quadre already stands on. AutoRemesher's adaptive sizing is real but its meshes are rougher. One
  check remains before closing the question: AutoRemesher's output with Quadre's finishing pass on top.
- **Phase 1 gets a sharper list** (item 6 above), and one addition at the top: the engine should run
  with a time limit, so a hang becomes a plain-English message instead of a frozen Blender. Today's
  hang came from a bad input Quadre itself produced; the next one will come from somewhere else.
- **Still wanted from David:** the blind picks, and markup of anything the numbers miss.

---

## 2. The shapes

| Code | What | Triangles in | Symmetry | Notes |
|---|---|---|---|---|
| B01_chibi | class Chibi sculpt | 2.9M | X | this morning's subject |
| B02_bucket | student bug-report bucket | 299K | off | |
| B03_suzanne | Suzanne, subdivision 3 | 63K | X | not simplified; has creases, open eye sockets, loose eyeballs |
| B04_filmhead | David's film head, multires 5 | 3.7M | X | **open at the neck** |
| B05_hand | hand with fingers | 287K | off | **open at the wrist** |
| B06_firstsculpt | first-class sculpt demo | 4.9M | off | lumpy organic |
| B07_alientree | alien tree | 2.4M | off | thin branches |
| B08_bracket | built hard-surface part | 2.6K | X | booleans + bevel; not simplified |
| B09_studentA | student A1 sculpt | 6.5M | off | thin wing-like sheets |
| B10_studentB | student A1 sculpt | 525K | X | rounded box |
| B11_studentC | student A1 sculpt | 1.8M | X | character with ears and wings |

Sources for each code are in a private key outside this repo
(`SJSU_ALL/ART102_FA26/QUADRE_BENCHMARK_KEY_2026-10-02.md`). Student work appears here by code only.

## 3. How it was run

- Quad Count 5,000 everywhere, X symmetry where the shape is symmetric.
- **Exoside 1.4:** its defaults (Adaptive Size 50%, Adapt Quad Count on, Detect Hard Edges on), full sculpt in.
- **Quadre 0.4.3 and 0.3.8:** the real operator, full sculpt in.
- **AutoRemesher 1.2:** its command line with defaults (adaptivity 1.0, anisotropy 1.0), given the 150K
  reference copy of each sculpt. It has no symmetry option. It undershoots the count badly (5,000 asked
  gave 1,700 to 3,400), so it got one corrected rerun, the same courtesy Quadre gives itself.
  Downloaded from the project's GitHub releases to `SOFTWARE/R&D/autoremesher/` (not in git).
- **QuadriFlow:** Blender's built-in, on the same 150K reference copy, symmetry on where applicable.
- Every run had a hard time limit (150 to 400 s). A killed run counts as "no result".
- Scripts: `ab_harness/bench_prep.py`, `bench_run.sh`, `bench_report.sh`, `bench_table.py`.

## 4. Reliability

| Tool | Finished | What went wrong |
|---|---|---|
| Quadre 0.4.3 | 11 / 11 | |
| AutoRemesher 1.2 | 11 / 11 | non-quads in 10 results (up to 155); open borders mangled |
| Exoside 1.4 | 10 / 11 | B10_studentB: "Remeshing Failed" after 29 s, with and without symmetry |
| QuadriFlow | 10 / 11 | B08_bracket: refused (cancelled at once) |
| Quadre 0.3.8 | 10 / 11 | B05_hand: hung (killed at 150 s). B04_filmhead: "finished" with fragments |

Time on the largest shape (B09, 6.5M triangles): Exoside 38 s, Quadre 0.4.3 19 s, AutoRemesher 12 s.
Quadre's slowest was the film head at 30 s (edge-collapse simplify of 3.7M triangles).

## 5. Numbers

### Averages over the shapes every tool finished

Shapes counted: 8 of 11 (B01_chibi, B02_bucket, B03_suzanne, B04_filmhead, B06_firstsculpt, B07_alientree, B09_studentA, B11_studentC)

| Tool | Finished | Poles | Loops off form | Corner error | Bent corners % | Size jump | Off sculpt ‰ | Detail lost ‰ | Worst spot ‰ |
|---|---|---|---|---|---|---|---|---|---|
| Exoside 1.4 | 10/11 | 222 | 11.1 | 8.3 | 0.48 | 1.52 | 0.05 | 0.41 | 6.3 |
| Quadre 0.4.3 | 11/11 | 165 | 13.0 | 8.7 | 0.88 | 1.55 | 0.02 | 0.79 | 15.8 |
| Quadre 0.3.8 | 10/11 | 363 | 17.4 | 13.5 | 2.56 | 1.80 | 0.63 | 8.43 | 56.2 |
| AutoRemesher 1.2 | 11/11 | 169 | 14.2 | 8.2 | 2.07 | 1.77 | 0.24 | 1.13 | 21.3 |
| QuadriFlow | 10/11 | 108 | 17.5 | 9.1 | 0.88 | 1.27 | 0.09 | 1.23 | 26.8 |

### Exoside vs Quadre 0.4.3 on every shape both finished

| Shape | Loops off form (E / Q) | Corner error (E / Q) | Detail lost (E / Q) | Poles (E / Q) | Quads (E / Q) |
|---|---|---|---|---|---|
| B01_chibi | 7.0 / 11.1 | 7.2 / 8.0 | 0.27 / 0.59 | 79 / 48 | 5,956 / 4,776 |
| B02_bucket | 12.2 / 10.3 | 9.6 / 7.4 | 0.31 / 0.33 | 68 / 91 | 4,657 / 4,909 |
| B03_suzanne | 8.6 / 13.1 | 6.9 / 11.7 | 0.33 / 0.51 | 92 / 95 | 6,210 / 5,220 |
| B04_filmhead | 12.0 / 14.8 | 7.6 / 9.5 | 0.37 / 0.74 | 138 / 198 | 8,126 / 5,418 |
| B05_hand | 5.1 / 10.9 | 5.3 / 11.3 | 0.27 / 0.54 | 40 / 38 | 5,325 / 4,765 |
| B06_firstsculpt | 12.9 / 14.2 | 9.1 / 7.9 | 0.38 / 0.63 | 330 / 265 | 7,175 / 5,442 |
| B07_alientree | 11.7 / 13.7 | 8.4 / 9.1 | 0.40 / 0.65 | 240 / 226 | 6,807 / 5,486 |
| B08_bracket | 12.9 / 9.9 | 6.7 / 6.7 | 0.90 / 1.81 | 42 / 152 | 10,298 / 5,308 |
| B09_studentA | 16.3 / 16.8 | 10.1 / 8.5 | 0.77 / 2.35 | 603 / 251 | 12,301 / 5,481 |
| B11_studentC | 7.9 / 9.5 | 7.1 / 7.3 | 0.41 / 0.55 | 228 / 143 | 9,016 / 5,314 |

## 6. Every shape, every tool

### B01_chibi — class Chibi sculpt (2,889,716 triangles in, symmetry X)

| Tool | Quads | Non-quads | Poles | Loops off form | Corner error | Bent corners % | Size jump | Off sculpt ‰ | Detail lost ‰ | Worst spot ‰ |
|---|---|---|---|---|---|---|---|---|---|---|
| Exoside 1.4 | 5,956 | 8 | 79 | 7.0 | 7.2 | 0.40 | 1.48 | 0.01 | 0.27 | 3.7 |
| Quadre 0.4.3 | 4,776 | 0 | 48 | 11.1 | 8.0 | 0.16 | 1.34 | 0.01 | 0.59 | 10.1 |
| Quadre 0.3.8 | 6,122 | 0 | 112 | 15.1 | 12.6 | 1.04 | 1.48 | 0.52 | 1.14 | 16.0 |
| AutoRemesher 1.2 | 2,563 | 4 | 61 | 10.7 | 5.1 | 0.31 | 1.51 | 0.12 | 0.93 | 18.3 |
| QuadriFlow | 4,649 | 0 | 64 | 12.1 | 5.6 | 0.05 | 1.16 | 0.03 | 0.56 | 11.8 |

### B02_bucket — student bug-report bucket (299,264 triangles in, symmetry off)

| Tool | Quads | Non-quads | Poles | Loops off form | Corner error | Bent corners % | Size jump | Off sculpt ‰ | Detail lost ‰ | Worst spot ‰ |
|---|---|---|---|---|---|---|---|---|---|---|
| Exoside 1.4 | 4,657 | 0 | 68 | 12.2 | 9.6 | 0.14 | 1.36 | 0.01 | 0.31 | 2.4 |
| Quadre 0.4.3 | 4,909 | 0 | 91 | 10.3 | 7.4 | 0.26 | 1.36 | 0.01 | 0.33 | 3.9 |
| Quadre 0.3.8 | 5,010 | 0 | 42 | 15.8 | 10.5 | 0.01 | 1.21 | 0.52 | 0.87 | 5.8 |
| AutoRemesher 1.2 | 3,767 | 6 | 50 | 12.7 | 8.2 | 0.98 | 1.47 | 0.13 | 0.46 | 3.5 |
| QuadriFlow | 4,634 | 0 | 16 | 19.6 | 6.2 | 0.09 | 1.11 | 0.02 | 0.36 | 4.8 |

### B03_suzanne — Suzanne subdiv 3, not simplified (62,976 triangles in, symmetry X)

| Tool | Quads | Non-quads | Poles | Loops off form | Corner error | Bent corners % | Size jump | Off sculpt ‰ | Detail lost ‰ | Worst spot ‰ |
|---|---|---|---|---|---|---|---|---|---|---|
| Exoside 1.4 | 6,210 | 0 | 92 | 8.6 | 6.9 | 0.16 | 1.47 | 0.04 | 0.33 | 3.8 |
| Quadre 0.4.3 | 5,220 | 0 | 95 | 13.1 | 11.7 | 3.05 | 1.56 | 0.10 | 0.51 | 4.4 |
| Quadre 0.3.8 | 4,942 | 0 | 56 | 16.5 | 10.1 | 0.24 | 1.27 | 0.17 | 0.86 | 7.5 |
| AutoRemesher 1.2 | 4,323 | 8 | 106 | 12.7 | 10.2 | 3.60 | 1.84 | 0.11 | 1.08 | 34.9 |
| QuadriFlow | 4,509 | 0 | 60 | 18.3 | 8.0 | 0.12 | 1.23 | 0.05 | 0.83 | 14.0 |

### B04_filmhead — film head, multires 5 (3,698,688 triangles in, symmetry X)

| Tool | Quads | Non-quads | Poles | Loops off form | Corner error | Bent corners % | Size jump | Off sculpt ‰ | Detail lost ‰ | Worst spot ‰ |
|---|---|---|---|---|---|---|---|---|---|---|
| Exoside 1.4 | 8,126 | 0 | 138 | 12.0 | 7.6 | 0.41 | 1.46 | 0.03 | 0.37 | 4.6 |
| Quadre 0.4.3 | 5,418 | 0 | 198 | 14.8 | 9.5 | 2.07 | 1.86 | 0.02 | 0.74 | 13.0 |
| Quadre 0.3.8 | 13,272 | 0 | 1,518 | 20.0 | 14.1 | 3.63 | 2.84 | 0.73 | 58.65 | 347.9 |
| AutoRemesher 1.2 | 3,823 | 22 | 131 | 14.9 | 9.1 | 3.83 | 1.91 | 0.21 | 1.57 | 43.9 |
| QuadriFlow | 4,532 | 0 | 95 | 18.1 | 9.7 | 0.71 | 1.30 | 0.08 | 1.29 | 39.3 |

### B05_hand — hand with fingers (287,232 triangles in, symmetry off)

| Tool | Quads | Non-quads | Poles | Loops off form | Corner error | Bent corners % | Size jump | Off sculpt ‰ | Detail lost ‰ | Worst spot ‰ |
|---|---|---|---|---|---|---|---|---|---|---|
| Exoside 1.4 | 5,325 | 0 | 40 | 5.1 | 5.3 | 0.02 | 1.25 | 0.01 | 0.27 | 2.3 |
| Quadre 0.4.3 | 4,765 | 0 | 38 | 10.9 | 11.3 | 1.11 | 1.32 | 0.00 | 0.54 | 11.2 |
| Quadre 0.3.8 | **no result** | | | | | | | | |  |
| AutoRemesher 1.2 | 5,068 | 6 | 52 | 6.6 | 6.1 | 0.84 | 1.38 | 0.17 | 0.43 | 24.6 |
| QuadriFlow | 3,912 | 0 | 44 | 9.3 | 6.6 | 1.40 | 1.18 | 0.21 | 0.66 | 6.8 |

### B06_firstsculpt — first-class sculpt demo (4,889,708 triangles in, symmetry off)

| Tool | Quads | Non-quads | Poles | Loops off form | Corner error | Bent corners % | Size jump | Off sculpt ‰ | Detail lost ‰ | Worst spot ‰ |
|---|---|---|---|---|---|---|---|---|---|---|
| Exoside 1.4 | 7,175 | 0 | 330 | 12.9 | 9.1 | 0.56 | 1.57 | 0.06 | 0.38 | 9.4 |
| Quadre 0.4.3 | 5,442 | 0 | 265 | 14.2 | 7.9 | 0.36 | 1.60 | 0.01 | 0.63 | 23.2 |
| Quadre 0.3.8 | 7,708 | 0 | 220 | 18.7 | 14.1 | 2.23 | 1.69 | 0.73 | 1.12 | 10.6 |
| AutoRemesher 1.2 | 4,305 | 6 | 75 | 17.6 | 6.8 | 0.20 | 1.47 | 0.26 | 0.87 | 12.4 |
| QuadriFlow | 5,045 | 0 | 72 | 19.9 | 9.7 | 0.37 | 1.22 | 0.05 | 0.69 | 14.6 |

### B07_alientree — alien tree, thin branches (2,368,376 triangles in, symmetry off)

| Tool | Quads | Non-quads | Poles | Loops off form | Corner error | Bent corners % | Size jump | Off sculpt ‰ | Detail lost ‰ | Worst spot ‰ |
|---|---|---|---|---|---|---|---|---|---|---|
| Exoside 1.4 | 6,807 | 0 | 240 | 11.7 | 8.4 | 0.36 | 1.55 | 0.04 | 0.40 | 6.9 |
| Quadre 0.4.3 | 5,486 | 0 | 226 | 13.7 | 9.1 | 0.33 | 1.54 | 0.01 | 0.65 | 14.4 |
| Quadre 0.3.8 | 7,150 | 0 | 203 | 17.6 | 15.1 | 3.55 | 1.70 | 0.92 | 1.34 | 14.3 |
| AutoRemesher 1.2 | 4,925 | 2 | 94 | 15.6 | 7.0 | 0.13 | 1.45 | 0.22 | 0.73 | 10.9 |
| QuadriFlow | 5,014 | 0 | 98 | 19.3 | 10.6 | 2.67 | 1.29 | 0.06 | 0.86 | 15.1 |

### B08_bracket — built hard-surface part, bevelled (2,604 triangles in, symmetry X)

| Tool | Quads | Non-quads | Poles | Loops off form | Corner error | Bent corners % | Size jump | Off sculpt ‰ | Detail lost ‰ | Worst spot ‰ |
|---|---|---|---|---|---|---|---|---|---|---|
| Exoside 1.4 | 10,298 | 2 | 42 | 12.9 | 6.7 | 0.24 | 1.27 | 0.11 | 0.90 | 6.6 |
| Quadre 0.4.3 | 5,308 | 0 | 152 | 9.9 | 6.7 | 0.23 | 1.51 | 0.00 | 1.81 | 7.3 |
| Quadre 0.3.8 | 4,342 | 0 | 48 | 11.1 | 6.7 | 0.51 | 1.34 | 0.06 | 0.12 | 2.2 |
| AutoRemesher 1.2 | 4,573 | 32 | 140 | 13.1 | 11.0 | 4.65 | 1.85 | 0.17 | 2.93 | 11.5 |
| QuadriFlow | **no result** | | | | | | | | |  |

### B09_studentA — student A1 sculpt A (6,498,632 triangles in, symmetry off)

| Tool | Quads | Non-quads | Poles | Loops off form | Corner error | Bent corners % | Size jump | Off sculpt ‰ | Detail lost ‰ | Worst spot ‰ |
|---|---|---|---|---|---|---|---|---|---|---|
| Exoside 1.4 | 12,301 | 73 | 603 | 16.3 | 10.1 | 1.53 | 1.70 | 0.20 | 0.77 | 14.4 |
| Quadre 0.4.3 | 5,481 | 0 | 251 | 16.8 | 8.5 | 0.49 | 1.62 | 0.02 | 2.35 | 49.8 |
| Quadre 0.3.8 | 12,016 | 0 | 538 | 20.4 | 16.7 | 4.86 | 2.24 | 0.87 | 2.41 | 41.6 |
| AutoRemesher 1.2 | 5,728 | 155 | 656 | 19.1 | 12.8 | 7.16 | 2.97 | 0.32 | 2.00 | 30.4 |
| QuadriFlow | 5,474 | 0 | 251 | 18.9 | 13.7 | 2.51 | 1.56 | 0.32 | 4.36 | 105.4 |

### B10_studentB — student A1 sculpt B (hard-surface) (525,068 triangles in, symmetry X)

| Tool | Quads | Non-quads | Poles | Loops off form | Corner error | Bent corners % | Size jump | Off sculpt ‰ | Detail lost ‰ | Worst spot ‰ |
|---|---|---|---|---|---|---|---|---|---|---|
| Exoside 1.4 | **no result** | | | | | | | | |  |
| Quadre 0.4.3 | 5,040 | 0 | 8 | 3.5 | 1.1 | 0.00 | 1.04 | 0.02 | 0.67 | 6.3 |
| Quadre 0.3.8 | 4,368 | 0 | 8 | 2.7 | 2.0 | 0.00 | 1.03 | 0.20 | 1.08 | 5.6 |
| AutoRemesher 1.2 | 4,234 | 0 | 8 | 2.2 | 3.1 | 0.00 | 1.42 | 0.13 | 0.32 | 2.4 |
| QuadriFlow | 5,040 | 0 | 8 | 2.5 | 1.2 | 0.00 | 1.02 | 0.01 | 0.57 | 5.5 |

### B11_studentC — student A1 sculpt C (1,794,560 triangles in, symmetry X)

| Tool | Quads | Non-quads | Poles | Loops off form | Corner error | Bent corners % | Size jump | Off sculpt ‰ | Detail lost ‰ | Worst spot ‰ |
|---|---|---|---|---|---|---|---|---|---|---|
| Exoside 1.4 | 9,016 | 0 | 228 | 7.9 | 7.1 | 0.31 | 1.57 | 0.03 | 0.41 | 5.3 |
| Quadre 0.4.3 | 5,314 | 0 | 143 | 9.5 | 7.3 | 0.36 | 1.50 | 0.01 | 0.55 | 7.8 |
| Quadre 0.3.8 | 7,466 | 0 | 214 | 15.0 | 15.0 | 4.94 | 2.00 | 0.57 | 1.02 | 6.1 |
| AutoRemesher 1.2 | 4,433 | 22 | 179 | 10.4 | 6.9 | 0.38 | 1.56 | 0.59 | 1.38 | 15.8 |
| QuadriFlow | 4,735 | 0 | 212 | 14.0 | 9.2 | 0.53 | 1.32 | 0.09 | 0.90 | 9.0 |
