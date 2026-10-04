# QUADRE v0.3.8 — the Quad Count field (2026-09-16, laptop)

**Occasion:** David, on a class day: "build a new version of
Quadre for today's class. I want it specifically to bring back the QUAD COUNT value, and remove the
current LOW to HI decimal setup. Also audit the code against leading edge open source tech for any easy
improvements. If nothing is worth implementing today then just bring back the Quad count value."

**What "Quad Count" is:** the integer field in Exoside Quad Remesher that every recorded ART 102 demo
uses ("set the quad count to 500", "2000", "5000 is the default"; grep of `TEACHING/ART102/transcripts`).
Quadre never had it: v0.1.0 already shipped the 0–1 "Low ↔ High" Detail slider (checked
`ARCHIVES/OLD_ZIPS/quadre-v0.1.0.zip`). So this is *match the language of the demos*, not a revert.
Exoside's own manual calls the number a target and warns it "won't return exactly the number of quads
you have set"; Quadre now says the same thing in its finish message.

Zip: `CADRE_REMESHER/quadre-v0.3.8.zip` (Blender 5.2.0 LTS `--command extension build`). v0.3.7 kept as
the one previous zip; v0.3.0 moved to `SOFTWARE/ARCHIVES/OLD_ZIPS/`.

---

## What changed (four small changes, each measured before the next)

1. **Quad Count replaces the Detail slider.** `props.py`: `detail` FloatProperty (0–1) → `quad_count`
   IntProperty, default **5000**, min 100, drag range to 25,000, typing allowed up to 50,000.
   `ui.py`: one number field labelled "Quad Count"; the Low/High slider row is gone. `operator.py`: the
   typed count is the target the v0.2.0 absolute-count solver already used; the finish message now reads
   **"Done! Clean shape has 2,014 faces (you asked for 2,000)"** so the student sees how close it landed.
2. **Density constant recalibrated, 0.42 → 0.50.** Measured today on Blender 5.2.0 LTS: with 0.42 every
   mid-range ask came back ~20% heavy (5,000 → 6,041). With 0.50 the same asks land within ±3% (table
   below). The old value was measured 2026-07-06 on 5.1.2 with a sphere and torus; today's data is
   Suzanne at two densities plus the bug-report bucket.
3. **Symmetry halves the engine's target.** With X or Y symmetry on, the engine only ever sees one half
   (or quarter) of the shape and the mirror step doubles the result afterwards. Nobody noticed under the
   slider; under a typed number it was glaring: X symmetry delivered **2.7×** the ask (2,000 → 5,514).
   Now the half aims for half the count.
4. **Between-stage file checks** (idea ported from the xtrytofindme/QRemeshify fork, commit a9afdf1,
   2026-08-11): after step 1 and step 2 the worker checks that the engine actually wrote its file. The
   native stages can report success without writing anything, and handing the next native stage a
   missing file is a hard-crash road (Blender dies, unsaved work with it). Now it stops with the normal
   plain-English failure message. Cannot change any result; only the failure path.

Also: the typed maximum is 50,000 rather than unbounded, because the engine tops out near 38K faces
(see limits). `QUADRE_ABOUT.md` and `QUADRE_SETUP_MAC.md` wording updated.

## Measured (headless Blender 5.2.0 LTS, laptop, final code)

Suzanne, subdivision 3 (63K triangles, no auto-simplify), symmetry off:

| Typed | Delivered | Note |
|---|---|---|
| 100 | 652 | floor |
| 300 | 706 | floor |
| 500 | 846 | floor |
| 1,000 | 1,204 | floor still pulling |
| 2,000 | 2,014 | |
| 5,000 | 5,140 | |
| 10,000 | 10,155 | |
| 25,000 | 25,483 | 10 s |
| 50,000 | 38,670 | ceiling, 12 s |

Suzanne, subdivision 5 (1,007,616 triangles → auto-simplify path): 300 → 1,400 (floor), 1,000 → 1,950,
5,000 → 5,540. The bug-report bucket (`ORGANIC TEST2.blend`, `Roundcube.001`, 299K triangles) at 7,846
(= the old slider's 0.64): **7,799 first clean, 7,675 re-clean** (99% / 98% of the ask). Under the old
constant the same run still gave the historic 9,066 exactly, so the pipeline itself is unchanged.

Suzanne subdivision 3 with X symmetry: 300 → 730, 2,000 → 2,648, 5,000 → 5,582. Every run 100% quads.
Runs took 3–12 seconds on this laptop.

Install test = the student's path: the zip installed into a fresh sandboxed Blender through the real
Extensions installer (`extensions.package_install_files`), registered as `bl_ext.user_default.quadre`,
and ran a cleanup (2,000 asked with X symmetry → 2,648, same as the source-tree run). David's own Blender
config was not touched.

## Honest limits (tell students the finish message is the truth)

- **Floor.** The engine cannot go below what the shape's feature lines and patch layout need: about
  650 faces on Suzanne, about 1,400 on a voxel-remeshed sculpt. Typing 300 gives ~700–1,400 and the
  message says so. Exoside goes lower on the same shapes. Possible future lever: relax the 35° sharp
  detection for tiny asks; that is an art call, not for a class-day build.
- **Ceiling.** Step 1 resamples every input to ~11–12K triangles regardless of what came in, and the
  density is clamped at 0.4, so ~38K faces is the most any ask can deliver. Fine for this class
  (500–5,000); noted for the record.
- **Symmetry still lands 10–30% heavy at low counts.** The cut edge is treated as a feature line (it has
  to be, so the mirror seam merges cleanly), which adds a strip of quads the target math doesn't see.
  Same on every shape, so it is calibratable later; not tuned on one shape today.
- **Re-clean drift between Blender builds.** Under the old constant the bucket re-clean is 8,479 on
  5.2.0 LTS final vs 8,599 recorded on the 5.2.0 beta, with the first clean identical (9,066). Build-to-
  build triangulation drift, not a Quadre change. New regression references (K = 0.50): 7,799 / 7,675.

## The audit: open-source delta since the 2026-08-20 landscape doc

Read-only web pass against primary sources (GitHub API, release pages, extensions.blender.org, Exoside's
PDFs), 2026-09-16:

- **cgg-bern/quadwild-bimdf** (the engine): nothing since the 08-03 dependency refresh; binaries still
  the 2023 prereleases. One fork (Paulbauing, 09-11) makes curvature/crease knobs config-readable; needs
  an engine rebuild, so not for us today.
- **QRemeshify forks:** no commits since 08-17. xtrytofindme's two commits = the file-existence
  validation (ported today as change 4) and a `util/transfer.py` that carries materials/UVs/weights to the
  result via a BVH nearest-face lookup plus a DATA_TRANSFER modifier. That is the design to read for the
  "my texture disappeared" gap (#9 on the 08-20 list); medium risk (needs operator context), not today.
  ReQRemeshify's pointed-tip cleanup pass: not today.
- **AutoRemesher** 1.2.0 (08-23): different engine, no action. Their "validate input before calling the
  solver" idea is the same spirit as change 4.
- **extensions.blender.org:** still zero automatic quad remeshers. The niche is still open.
- **Blender:** 5.2.2 LTS shipped 09-15 (5.2.1 on 08-18). Nothing in either fix list touches bmesh, the
  Remesh modifier, modifier_apply, modal timers, or property UI; manifest schema still 1.0.0. No action.
  5.2.3 due 10-20, 5.3 due 11-10.
- **Exoside:** still 1.4 (July 2025). Their Blender panel: Quad Count integer field, default 5000,
  described as a target. Matched.
- **New tools/papers:** nothing that runs offline on a Mac without a GPU. **Hazard for students:** a
  GitHub repo named like a free "Quad Remesher Add-on Windows Download" appeared 09-12 with zero stars;
  it looks like a cracked-software lure. Worth one sentence in class: the free tool is Quadre, from David.

Verdict: nothing else worth shipping on a class day. Change 4 was the one "easy improvement" that
qualified (ten lines, cannot change results).

## Follow-ups (in rough order)

1. Symmetry calibration (measure the cut-edge strip on a few shapes; subtract it from the half target).
2. Materials/UVs on the result (#9): read xtrytofindme `util/transfer.py`, then design doc.
3. Still zero confirmed Windows runs (#5). One volunteer, one screenshot.
4. Non-ASCII temp paths (#10); subprocess isolation (#11, the real cure for engine crashes).
5. Low-count floor: try relaxing sharp detection for asks under ~1,000 (art call, David decides).

## David's live check (what headless cannot prove)

Install `quadre-v0.3.8.zip` (Preferences → Get Extensions → Install from Disk; on a new Mac the
Gatekeeper fix in `QUADRE_SETUP_MAC.md` still applies once). The panel should show **Quad Count 5000**
and no Low/High row. Type 2000, turn X symmetry on, press the button, watch the seconds tick, and read
the finish line: it should say "(you asked for 2,000)". Try Esc once mid-run.
