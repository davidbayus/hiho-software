# Quadre + PaWrappa Improvements — Design Doc

**Date:** 2026-07-06 (Fable 5 session, laptop)
**Method:** Full read of both codebases, then every suspicion tested in headless Blender 5.1.2 before touching code. Test scripts in session scratchpad; results reproduced below.

---

## What Was Tested (and What Survived Testing)

| # | Hypothesis | Result |
|---|-----------|--------|
| H1 | Quadre's OBJ exporter uses stale bmesh indices after bisect+triangulate | **REJECTED** — indices stay sequential. No bug. No change made. |
| H2 | Quadre's auto-decimate (fixed 0.02 voxel size) can INCREASE triangle count | **CONFIRMED** — a 4K-tri sphere of radius 2 became 376K tris after "simplification" |
| H3 | PaWrappa's "Hide Seams on Back (+Y)" is inverted — pushes seams to the FRONT | **CONFIRMED** — in this algorithm seams form along *expensive* edges; discounting back edges (×0.85) repels seams from the back. Sphere test: bias ON put 163 seams front vs 148 back. |
| H4 | PaWrappa clustering can collapse to 1 chart → degenerate unwrap | **REJECTED** — `max(2, ...)` guarantees ≥2 clusters. 0 degenerate UV faces at thresholds 0.85–0.95. No change made. |
| H5 | The bucket bug report (`BUG_REPORTS/ORGANIC TEST2.blend`) shows detail slider is input-relative, not absolute | **CONFIRMED** — same file contains the chain 299K tris → 43K → 160K → 6K from repeated cleanups. Cleaning a clean 43K mesh *grew* it to 160K. |

## Root Causes (plain English)

**Quadre #1 — auto-decimate is scale-blind.** The "shape too dense, simplifying first" step uses a fixed voxel size of 0.02 Blender units regardless of how big the object is. On a small object that's coarse; on a normal character-scale object it can *multiply* the triangle count by 100x. The student's bucket (299K tris, ~4 units tall) hit exactly this path.

**Quadre #2 — the Detail slider doesn't mean anything stable.** QuadWild's density parameter is relative to the input mesh's resolution. Same slider position + denser input = denser output. So results feel random ("doesn't seem to work too well"). Fix: make the slider target an absolute face count. After QuadWild's first stage we can read the intermediate remeshed mesh's triangle count, and output faces ≈ k·R/density² (verified empirically before coding), so we can solve for the density that hits a target count.

**PaWrappa — back bias inverted.** One line: back-facing edges get cost ×0.85, but cluster boundaries (seams) form along HIGH-cost edges. Fix: boost instead of discount.

## Planned Changes (one at a time, test after each)

### Quadre v0.1.1
1. **Adaptive auto-decimate.** Compute voxel size from the mesh's surface area so the result lands near (not over) the 100K budget: `voxel = sqrt(area / target_quads)`. Verify the modifier actually reduced the count; if not, retry coarser. Test: r=2 sphere and the real bucket must come out ≤100K tris.
2. **Detail slider targets face count.** Slider 0→1 maps to ~1,000→25,000 target faces (log scale). After stage 1, read remeshed tri count R, set `density = sqrt(k·R/target)` with k measured empirically. Report the achieved face count. Test: same slider position on a 2K-tri and a 300K-tri input should produce similar output counts; repeated cleanup of the bucket must not balloon.
3. **Preflight warnings, plain English.** Before running: count loose parts, wire edges, loose verts. Warn ("Your shape is 3 separate pieces — Quadre works best on one solid piece") but don't block. Addresses the "loose faces" half of the bug report.

### PaWrappa v0.3.4
1. **Fix back_bias direction** (×0.85 discount → ×1.25 boost on +Y-facing edges). Test: sphere seam distribution must flip to back-heavy.
2. **Cluster-average normal instead of seed normal** during face assignment — charts become flatter/more developable, which is what makes unwraps paintable. Keep only if the measured UV stretch improves; revert if worse.
3. **Stretch feedback after unwrap.** Measure per-face UV-vs-3D area distortion; append a plain-English verdict to the result message ("Low stretch — good to paint!" / "Some stretching — try the slider further left").

### Deferred (recommended next, not today)
- **Quadre progress/no-freeze:** the QuadWild call freezes Blender for minutes; students think it crashed. Right fix is a modal operator + worker thread (ctypes releases the GIL, so this works). Structural change — deserves its own session.
- **Extensions packaging for PaWrappa** (blender_manifest.toml, like Quadre already has) — needed before club-scale student installs.
- **Thin-wall guidance for buckets/cups:** QuadWild inherently struggles with thin double-walled shells at low target counts; a preflight "this shape has thin walls — keep Detail above X" hint would be honest. Needs more research.

## Results (all implemented and verified headless in Blender 5.1.2)

### Quadre v0.2.0 (was v0.1.0)
- **Adaptive auto-decimate:** 146K-tri sphere that previously exploded to 376K now comes out under budget. Bonus fix found during implementation: the old code voxel-remeshed the **student's original mesh** destructively before hiding it; the new code works on a temporary copy and the original is untouched (verified).
- **Detail slider now targets face count** (log scale, ~1K at left, ~25K at right, ~5K at middle). Calibration measured: output faces ≈ 0.42 × remeshed_tris / density², k stable across sphere/torus (0.41–0.44); sharp features set a floor so results land at-or-above target. Verified: 968-tri, 37K-tri, and 147K-tri inputs at slider 0.5 → 6.6K / 5.1K / 5.5K faces.
- **THE BUG-REPORT BUCKET IS FIXED:** real `ORGANIC TEST2.blend`, student's slider setting (0.64): 299K tris → 9,066 faces; re-cleaning the result → 8,599 (stable). Before: 299K → 43K → 160K.
- **Preflight:** wire edges and stray vertices removed from the working copy; disconnected shapes get a friendly "your shape was N separate pieces" note (correctly counted Suzanne's eyes).

### PaWrappa v0.3.4 (was v0.3.3)
- **Back-bias direction corrected** (was pushing seams to the FRONT). Honest finding: with Lloyd clustering the whole surface gets tiled, so this option can only ever nudge boundaries locally — it is inherently weak. Corrected + made additive so it at least acts in smooth regions, but don't oversell it.
- **Charts now grow against their average normal** (recomputed each Lloyd pass) instead of the seed face's normal. Judged by an area-stretch metric across 4 shapes × 2 thresholds: eliminated the catastrophic case (torus at threshold 0.85 — the panel's recommended character setting — mean stretch 1.48 → 1.08, worst 5.6 → 2.0); sphere improved; cylinder regressed mildly (1.03 → 1.06). Kept because students are hurt most by the worst case. Area-weighted averaging was also tried and measured WORSE — reverted.
- **Stretch feedback:** every run now ends with a plain-English verdict ("low stretching — good to paint!" / "try the slider further LEFT"), computed from actual UV area distortion.

## Zips
Built from the canonical dirs per zip discipline: `SOFTWARE/PaWrappa_v0.3.4.zip`, `SOFTWARE/CADRE_REMESHER/quadre-v0.2.0.zip`. Not yet installed into any Blender — David installs from zips himself.

## Test Scripts
Headless test/calibration scripts live in the session scratchpad (temporary). The methodology worth keeping: register the addon from source with `sys.path` + `--factory-startup`, drive the real operators, measure (face counts, UV area stretch, seam distribution). Re-runnable against any future change.

---

## ADDENDUM (same evening) — all three deferred items done

### PaWrappa v0.3.5 — Extensions packaging ✅
`blender_manifest.toml` added (mirrors Quadre's), zip now built with Blender's own
`--command extension build`. Verified in a sandboxed Blender 5.1.2 (isolated
extensions folder, David's config untouched): installs, enables, all classes
register, and the one-click unwrap ran end-to-end on a test sphere.
**Zip: `SOFTWARE/PaWrappa_v0.3.5.zip`.** Legacy drag-install still works too
(bl_info kept).

### Quadre v0.3.0 — no more freezing ✅
Design doc: `CADRE_REMESHER/QUADRE_NOFREEZE_DESIGN_2026-07-06.md`. The three heavy
QuadWild stages now run on a background thread (they're pure ctypes — verified they
release Python's lock) while Blender stays fully usable. Students see
"Step 1 of 3 — rebuilding the surface… 12s" counting up in the panel and status
bar, the button greys out while it works, and Esc cancels (after the current step —
a native call can't be stopped mid-flight, and the panel says so).
Headless verification in 5.1.2:
- **Liveness proven:** main thread kept ticking at 43 checks/second while the
  worker ran all three stages.
- **Bucket regression EXACT:** real `ORGANIC TEST2.blend` original sculpt at
  slider 0.64 → 9,066 faces, re-clean → 8,599 — identical to v0.2.0. The
  restructure changed no results.
- Cancel, error-capture, poll-guard, and script/headless fallback all tested.
- Zip installs + runs as an Extension in a sandboxed Blender.
**Zip: `SOFTWARE/CADRE_REMESHER/quadre-v0.3.0.zip`.**
**Still pending: David's live check** — install, run on a heavy sculpt, watch the
seconds tick while orbiting the viewport, try Esc once. Headless can't prove UI feel.
Also: native library failures (bad input file) still hard-crash Blender — that's
pre-existing QuadWild behavior, unchanged, discovered again during testing.

### Thin-wall research ✅ (research only, no code — by design)
Doc: `CADRE_REMESHER/THIN_WALL_RESEARCH_2026-07-06.md`. The deferred hypothesis was
WRONG in a useful way: QuadWild handles thin walls fine (cups with quads 4.8× wider
than the wall survived perfectly — 100% volume, zero holes). The real danger is the
**auto-simplify voxel step** on dense meshes: a 459K-tri cup with 0.025 walls got a
0.028 voxel and silently lost 34% of its volume — walls fused, no warning, "Done!".
Also measured: the bug-report bucket was never thin-walled (wall ≈ 0.93 units, 30×
the voxel) — its problems were purely the density bug, already fixed.
Proposed for a future v0.3.x: closed-mesh thickness estimate (2×volume/area, costs
nothing) + plain-English warning when the voxel would crush the walls.

### Also fixed in passing
`QUADRE_SETUP_MAC.md` quarantine command referenced the stale v0.1.0 zip filename.
