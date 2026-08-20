# QUADRE — Retopo Landscape Cross-Reference & Improvement Plan

**Date:** 2026-08-20 (laptop). **Occasion:** Quadre v0.3.0 is now in ART 102 students'
hands as the free alternative to Exoside Quad Remesher, so it has to actually work.
**Method:** two parallel research passes (read-only code audit of v0.3.0; web survey of
the open-source auto-retopology field as of today), followed by an adversarial
verification pass — three independent fact-checkers against primary sources (GitHub
API, release pages, vendor PDFs, the full extensions.blender.org catalog). One
material error in the survey was caught and corrected below. Local binary licensing
was checked directly on this machine today.

---

## 1. Read this first (plain English)

**The Mac lab is safe.** No Blender 5.x breakage anywhere in the addon, the student's
original mesh is provably never touched, cancel and undo behave, and the bundled
engine binaries run on both Apple Silicon and Intel Macs. The packaging is correct
for Blender 5.2 Extensions install.

**Four real risks, in order:**

1. **Linux is advertised but there is no Linux engine binary in the zip.** A Linux
   student can install Quadre and the first button press produces a scary wall of
   code. One line in the manifest fixes this.
2. **Windows has never been observed working.** The Windows engine files ship and
   look right, but no confirmed run exists anywhere in the project records. Half of
   the students' personal laptops are Windows. One volunteer test retires this.
3. **Three predictable student moments still show raw code tracebacks** instead of a
   plain sentence: the Mac first-run Gatekeeper block, symmetry on an off-center
   sculpt (which can silently empty the mesh and then hard-crash Blender), and a
   quiet engine failure. All are small fixes.
4. **The thin-wall crusher is still unshipped.** A dense sculpt with thin walls can
   silently lose volume (34% measured on the test cup) and still report "Done!".
   The warning is already designed and worded in `THIN_WALL_RESEARCH_2026-07-06.md`.

**And one piece of genuinely good news:** the licensing of the shipped binaries was
checked today and is clean (details in §3). Nothing in Quadre's zip violates its
GPL-3.0 license.

---

## 2. The field, August 2026 (all claims verified against primary sources today)

### Quadre's own lineage: QRemeshify is abandoned — and its users are stranded
- **ksami/QRemeshify** (GPL-3.0, 1,175 stars): frozen at v1.1.0, **2024-10-08, which
  is also the last commit**. Fresh unanswered issues through July 2026: instant crash
  on Blender 4.5 (#34), Blender 5.1.2 crash (#45), UV/material loss (#46), "cannot
  use" reports (#47/#48). The maintainer has replied to none of them.
- **Correction from the verify pass:** QRemeshify's macOS build IS Apple Silicon
  (`macos-arm64` in its manifest). Its Mac complaints (#25/#36) are **Intel** Mac
  users being refused at install. So the addon Quadre grew from does run on the lab
  Macs — it just crashes on modern Blender for many users and preserves nothing.
- **New this month:** two forks woke up. **xtrytofindme/QRemeshify** (2026-08-11,
  two commits) adds **material/UV/vertex-weight preservation and solver-output
  validation** — exactly two of Quadre's gaps; worth reading their diff before
  building ours. **TamKungZ/ReQRemeshify** (2026-08-17, self-versioned "1.2.1") adds
  a Pointed Tip Cleanup pass. Both are days old, zero track record — watch, don't
  depend.

### The engine upstream: cgg-bern/quadwild-bimdf woke up two weeks ago
- First commits since Oct 2024: a 9-commit burst on **2026-08-03** by Martin
  Heistermann — full dependency refresh (Eigen 5.0.1, OpenMesh, CoMISo, vcglib,
  nlohmann-json 3.12.0, lemon, satsuma, Timekeeper) plus a build fix. No new
  features, but the tree now compiles against 2026 toolchains.
- Official binaries are still the 2023 prereleases (v0.0.1 / v0.0.2). Verifier
  downloaded the 2023 macOS assets and confirmed they are universal x86_64+arm64.
- **Meaning for Quadre:** when we next need to rebuild the native engine (e.g., to
  produce a real Linux .so, or for the subprocess-isolation project), build from the
  fresh Aug 2026 tree with `-DSATSUMA_ENABLE_BLOSSOM5=0` (the default) and no Gurobi.

### The MIT sibling: AutoRemesher is suddenly the most active project in the field
- **huxingyi/autoremesher** (Jeremy Hu, the Dust3D author): v1.0.0 on **2026-07-06**
  with a verified GPLv3→**MIT** relicense; **v1.1.0 on 2026-08-16** (repo pushed
  08-17) — native quad parameterizer replacing Geogram, anisotropic quad sizing,
  mesh simplification with preview, Accelerate/BLAS on macOS. Ships a macOS .dmg
  that is Apple-Silicon-native (CI inference, verified sound), Windows x64 zip,
  Linux AppImage. Has a headless CLI with `--target-quads` as an absolute count —
  independent validation of Quadre's v0.2.0 absolute-face-count slider decision.
- Different algorithm lineage (frame-field); historically trails QuadWild on feature
  preservation; **quality on the BUG_REPORTS meshes still unverified** — the A/B
  test (ORGANIC TEST2 bucket + thin-wall cup) remains the gate before any claim.
- **Architecture lesson stands:** it runs remeshing in a separate process, so engine
  crashes can't kill the host app. MIT license = zero friction to vendor its CLI as
  a crash-safe fallback backend later. A third-party Blender bridge already exists
  (adriflex/autoremesher-blender-bridge, July 2026, crude OBJ round-trip).

### Blender itself: nothing moved, and the official addon shelf is empty
- Built-in Quad Remesh is **still 2019-era QuadriFlow**, unchanged through 5.2
  (release notes for 4.5→5.2 grepped: zero remesh algorithm work).
- The full extensions.blender.org catalog (1,383 extensions) contains **zero
  automatic quad remeshers** — only manual retopo tools (PolyQuilt fork, Bsurfaces,
  EdgeFlowDraw) and a triangle remesher (MMGpy). The "one-click quads" slot on
  Blender's official platform is empty, and Quadre's bundled-binary, all-GPL design
  already matches the platform's packaging rules. Whether to ever submit is David's
  strategic call (visibility vs. viewable-but-closed posture) — noted, not urged.

### The commercial bar: Exoside Quad Remesher has been standing still
- Current version **1.4 (July 2025)**, maintenance-grade changes only; nothing newer
  as of today. The feature bar students compare against is finite and frozen:
  target quad count, adaptive size 0–100%, adaptive quad count, painted density
  (vertex colors), guides from materials/hard edges/normal creasing/angle detection,
  X/Y/Z symmetry, keep-materials, one-click REMESH IT.

### The research horizon (watch, don't build)
- **CrossGen** (SIGGRAPH Asia 2025, AGPL, code through Mar 2026): first feed-forward
  neural cross-field method (~1 s instead of minutes of per-shape optimization).
  The plausible future is a neural field stage feeding a conventional extractor —
  a v2.0-era idea, not a fall-semester one. NeurCross (SIGGRAPH 2025, AGPL) is the
  heavyweight per-shape ancestor. The autoregressive "artist mesh" generation wave
  (QuadGPT, QuadLink, TopGen…) generates meshes from scratch; none is a drop-in
  retopo engine, most have no code.
- **Ministry of Flat** is frequently mislabeled retopo: it is automatic **UV
  unwrapping**, closed-source, Windows-only. Not usable in the Mac lab, not
  bundleable, and it's PaWrappa's neighbor, not Quadre's. Don't point students at it.

---

## 3. Licensing audit of the shipped binaries (done locally today — CLEAN)

Checked `quadre/lib/` directly with `lipo`/`nm`/`strings`:

- **Blossom-V (non-free) is NOT compiled in.** The only blossom symbol is satsuma's
  stub, and the binaries contain the string "Satsuma was built without blossom-V
  support." No `PerfectMatching`/`blossom5` symbols anywhere. Same profile on the
  Windows DLLs.
- **Gurobi (proprietary) is NOT compiled in.** All Gurobi strings are "not
  available / built without Gurobi" error paths.
- **Both mac dylibs are universal x86_64+arm64** — Intel Macs are supported by the
  binary even though the manifest currently refuses them (see fix #1 below).

Conclusion: distributing Quadre's zip to students and hosting it in the public repo
is GPL-3.0-clean. If binaries are ever rebuilt, keep `SATSUMA_ENABLE_BLOSSOM5=0`
(the upstream default) and no Gurobi, then re-run this strings check.

---

## 4. Where Quadre stands vs. the bar

**Already ahead of the field:** no-freeze worker thread with live "Step N of 3"
progress and Esc cancel (neither QRemeshify nor AutoRemesher's bridge has this
inside Blender); absolute face-count Detail slider (validated by AutoRemesher's
independent choice of the same design); the original mesh is never touched;
plain-English messages where they exist; automatic edge guides (35° angle + seams +
boundaries + material and face-set borders) — a feature Exoside makes users configure.

**Feature gaps vs. Exoside 1.4** (deliberate one-button philosophy notwithstanding):

| Exoside feature | Quadre v0.3.0 | Verdict |
|---|---|---|
| Target quad count | Detail slider, absolute 1K–25K | ✔ equivalent, simpler |
| One-click, new object, hide input | Same | ✔ equivalent |
| Guides from materials/hard edges | Automatic (35°+seams+materials+face sets) | ✔ automatic version |
| Symmetry | X/Y only (and the off-center bug, fix #4) | Partial — Z missing, guard missing |
| Keep materials on result | Not transferred (stay on hidden original) | ✘ top student-visible gap |
| Adaptive size / adaptive count | Not exposed | ✘ candidate v0.4+ knob (QuadWild adaptivity / AutoRemesher-style) |
| Painted density (vertex colors) | Not exposed | Deliberate omission — keep out (one-button philosophy) |

---

## 5. The plan — one change at a time, in order

Small, independent, each with its own zip and test. Items 1–8 are realistically
pre-midterm; 9–11 are the v0.4.0 horizon.

1. **Manifest platform truth (S, zero risk).** Drop `linux-x64` (no .so exists —
   installing is a guaranteed traceback), and **add `macos-x64`** (the dylibs are
   universal; Intel-Mac students are currently refused an install that would work).
   Also fix the Linux line in `QUADRE_ABOUT.md`.
2. **Catch engine-load failure and speak human (S).** Wrap the library construction
   (`operator.py:247` / `lib/__init__.py:52`) so a Mac Gatekeeper block says
   "QUADRE's engine was blocked by macOS — follow the 30-second fix in the Mac Setup
   Guide, then restart Blender" instead of a ctypes traceback. This is every Mac
   student's *first* experience when the zip came through a browser.
3. **Close the traceback holes (S).** Broaden the two `except QuadreException` nets
   to `except Exception` (`operator.py:339, 401`) and check the ignored `trace()` /
   `quadrangulate()` return codes (`operator.py:113, 131`) so polite engine failures
   get the friendly message. (Two one-change steps if preferred.)
4. **Guard the symmetry bisect (S).** After the bisect, if zero faces remain, stop
   with: "Symmetry removed everything — your shape sits to one side of its center.
   Turn off Symmetry, or set Object → Set Origin → Origin to Geometry and try
   again." Currently an unguarded road to the hard crash.
5. **One confirmed Windows run (organizational, this week).** Recruit one Windows
   student — install v0.3.0 (after #1's zip), remesh a sphere, screenshot. If it
   fails, that failure becomes the new #1.
6. **Thin-wall warning (S/M).** Implement exactly the proposal in
   `THIN_WALL_RESEARCH_2026-07-06.md` (wall estimate 2·volume/area vs. voxel size,
   closed meshes only, warn don't block). The only silent data-corruption path.
7. **"Save first" nudge (S).** Unsaved changes at button press → "Tip: save your
   file first — just in case." The honest interim answer to the native-crash risk
   until #11.
8. **UI batch (S each):** explain the greyed-out button ("Select your shape in
   Object Mode to begin"); give Y symmetry the same mirror icon as X; reword the
   catch-all error (the "apply all modifiers" advice is wrong — modifiers are
   already evaluated; suggest Voxel Remesh / check for holes instead); name repeat
   results `X_clean.001` not `X_clean_clean`.
9. **Materials-on-result (M).** Top student-visible feature gap ("my texture
   disappeared"). The xtrytofindme QRemeshify fork just built material/UV/weight
   transfer — read their approach first (GPL-compatible lineage), then design doc.
10. **Non-ASCII path hardening (M, pairs with #5).** Hash/transliterate the object
    name in temp paths (`operator.py:244`); a Windows student named José or an
    object named with emoji currently risks a native-level failure.
11. **Subprocess isolation (L — the v0.4.0 structural project).** The only real
    cure for "engine crash kills Blender and unsaved work." Two candist routes:
    helper-process wrapper around the current QuadWild stages (rebuild from the
    fresh Aug 2026 upstream tree), or vendor MIT AutoRemesher's CLI as a crash-safe
    fallback backend for meshes that kill QuadWild — gated on the A/B quality test
    (ORGANIC TEST2 + thin-wall cup). Design doc first, per house rules.

**Class messaging meanwhile (no code needed):** Mac students — if the first run
shows an error, it's the 30-second Gatekeeper fix in `QUADRE_SETUP_MAC.md`; Windows
students — wanted: one volunteer tester; Linux students — not supported yet, use
Blender's built-in Remesh → Quad for now. And for 3D printing specifically, remind
students they usually don't need retopo at all — slicers eat triangles happily;
Quadre is for when they sculpt → animate/subdivide.

## 6. What NOT to do (settled today, don't reopen without new evidence)

- No neural methods this era (CrossGen is AGPL research code needing PyTorch+GPU).
- No painted-density or knob farm — the one-button philosophy is the product.
- No per-stage progress percent (engine doesn't report it; ruled out in the
  no-freeze design doc).
- No auto-fixes that modify the student's original mesh — the never-touch guarantee
  is currently honored perfectly; keep it that way.
- Don't recommend Ministry of Flat to students (closed, Windows-only, and it's a UV
  unwrapper, not retopo).

---

## Sources & verification

Code audit: local, read-only, `quadre/` source + design docs, path:line cites
throughout §1/§5 (full audit in the 2026-08-20 session record). Landscape survey +
three-agent adversarial verify pass, all primary sources, 2026-08-20: GitHub API
(huxingyi/autoremesher releases & workflows; cgg-bern/quadwild-bimdf commits &
releases incl. downloaded 2023 macOS binaries checked with lipo; ksami/QRemeshify
releases, issues, forks), exoside.com What's New PDF (live, modified 2025-08-25),
extensions.blender.org full catalog API (1,383 extensions), docs.blender.org
release notes 4.5–5.2. Binary licensing: `lipo`/`nm`/`strings` on `quadre/lib/*`
this morning. One survey error (QRemeshify macOS arch, inverted) was caught by the
verify pass and corrected here; "no active QRemeshify fork" was corrected to the
two August 2026 forks named above.
