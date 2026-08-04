# PPParty (multi-cam) — under construction

Canonical PPParty as of 2026-05-06: a multi-camera markerless mocap addon for Blender, built on FreeMoCap + Skellycam. Project folder claimed 2026-05-06; architecture doc + code coming summer 2026.

**Goal:** open-source mocap students can use without a subscription or a mocap suit. First test site: BASEMENT studio (4 cams, ~2026-05-09). Second: SJSU CADRE Lab Art241 (5 cams, gated on the lab manager).

**Predecessors (don't conflate):**
- V1 archive: [`../PPPARTY_V1_ARCHIVE/`](../PPPARTY_V1_ARCHIVE) — live-puppet phone-era, retired Apr 2026, never delete.
- V2 single-cam: [`../PPPARTY_V2/`](../PPPARTY_V2) — record + bake, parked at v2.0.4. NOT under active development.

**Reference codebases (cloned for study, NOT vendored):**
- [`../R&D/freemocap-main/`](../R&D/freemocap-main) — FreeMoCap codebase (AGPL-3.0). Provides multi-cam pipeline: capture sync, ChArUco calibration, triangulation, post-processing.
- [`../R&D/skellycam/`](../R&D/skellycam) — Skellycam codebase (cloned 2026-05-06). FreeMoCap's spun-out cross-platform multi-cam capture lib.
- [`../R&D/snowmocap/`](../R&D/snowmocap) — SnowMocap (cloning 2026-05-06). MIT-license reference for Blender-side integration patterns.

**Existing design + planning docs (don't duplicate):**
- [`../R&D/MULTICAM_MOCAP_DESIGN.md`](../R&D/MULTICAM_MOCAP_DESIGN.md) — high-level architecture (2026-05-05, predates today's reframe; naming + phasing slightly stale, core architecture solid).
- [`../R&D/MULTICAM_SHOPPING_LIST.md`](../R&D/MULTICAM_SHOPPING_LIST.md) — BASEMENT hardware + first-day-setup walkthrough.

**Architecture (in plain English):**
- **Engine = Skellycam + FreeMoCap.** They handle webcam aggregation, calibration, triangulation. We don't reimplement.
- **Our work = thin Blender bridge.** Blender addon launches the engine, receives 3D landmarks, drives bones, records, NLA-push. Plus the student-facing UX layer (calibration walkthrough, "record" / "process" / "import" / "apply" buttons).
- **Patterns we cherry-pick from V2** (small, named list): Rigify hand rig, Slotted Actions fcurve handling, NLA-push pattern, operator scaffolding.
- **What we deliberately don't port from V2:** hand calibration estimators (irrelevant with true 3D), Lever A side_ref math (probably irrelevant with true 3D), `mediapipe_sender.py` (replaced by Skellycam).

**Pipeline (paraphrased from `MULTICAM_MOCAP_DESIGN.md`):**
```
N webcams → Skellycam (sync + calibration)
         → MediaPipe per camera (2D landmarks)
         → Triangulation (FreeMoCap core_processes) → 3D positions (numpy)
         → Post-process (gap fill, smoothing, outliers)
         → Blender bridge (this addon) → bones → NLA strip → student bakes / retargets to character
```

Live Blender mirror = nice-to-have, not load-bearing — students consume the BAKE, per `project_ppparty_deliverable_is_baked_animation` memory.
