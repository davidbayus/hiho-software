# SOFTWARE/ — HIHO Software Projects

## What This Is
Active code workspace. Canonical project = **HIHO MOCAP**. Smaller HIHO tools (PaWrappa, Quadre, Green Room) also live here. Each has its own home directory.

## Start Here for Any Code Session
1. Read [HIHO_MOCAP/HIHO_MOCAP_v1_PLAN.md](HIHO_MOCAP/HIHO_MOCAP_v1_PLAN.md) — the v1 plan anchor (mandatory).
2. Then [HIHO_MOCAP/HIHO_MOCAP_WRAPPER_ARCHITECTURE.md](HIHO_MOCAP/HIHO_MOCAP_WRAPPER_ARCHITECTURE.md) — the wrapper architecture doc (2026-05-27 pivot, section 8 locked 2026-05-28).
3. Memory's `project_hiho_mocap_wrapper_architecture.md` is the live state pointer. `project_hiho_mocap_current_state.md` is superseded (kept for v1.1 history).
4. If touching other tools, read their dir's README + their memory file.

## Folder Map
- **HIHO_MOCAP/** — canonical. Multi-cam Blender mocap addon, bundled-vendored FreeMoCap, AGPL-3.0. (Was PPPARTY/, renamed 2026-05-17.)
- **PPPARTY_V1_ARCHIVE/** — V1 phone-era puppet show. Retired (tagged `v0.9.6-phone-era-final`). Read-only.
- **PPPARTY_V2/** — V2 single-cam puppet show. Parked at v2.0.4. Inert escape valve.
- **UV_UNWRAPER/** — PaWrappa, auto-UV for Studio Track. v0.3.5, Extensions-packaged, student-testing ready.
- **CADRE_REMESHER/** — Quadre quad remesher (alt to Exoside). **v0.4.7 (2026-10-03)**: Phase 1 of the plan to match Exoside, four changes, one commit each (0.4.4 → 0.4.7): the finishing pass keeps hard edges and open borders (points slide along the line, corners stay put); Quadre draws three flow maps, adds the engine's own, builds one layout from each and keeps the best by measurement (`quadre/score.py`; engine steps in `quadre/stages.py`); the engine runs as child processes (`quadre/child.py` + `quadre/engine_runner.py`) with a 300 s limit, so a hang or crash cannot take Blender down, Esc stops at once, and the four layouts run side by side (falls back to running inside Blender if a child cannot start); the finishing pass turns quads toward the form only where the form has a direction (a strength-scaled "guide" map). Nine shapes all tools finish: Exoside 10.4 / Quadre 0.4.7 12.1 / Quadre 0.4.3 12.7 degrees off the form; corners 7.9 / 7.0 / 9.0. Before that, **v0.4.3 (2026-10-02)**: own flow map (`quadre/flow.py`), finishing pass (`quadre/relax.py`), count retry, open shapes simplified by edge collapse. Read in this order: `QUADRE_PHASE1_DESIGN_2026-10-03.md` (where it stands + how the new parts work), `QUADRE_EXOSIDE_PARITY_PLAN_2026-10-02.md` (what is next: Phase 3, own the engine), `QUADRE_PHASE0_BENCHMARK_2026-10-02.md` (the eleven shapes), `QUADRE_FLOW_QUALITY_DESIGN_2026-10-02.md` (flow map + finishing pass). Harness `CADRE_REMESHER/ab_harness/` (run `suite_op.sh` before and after any Quadre change; `test_child.py` after touching the child-process code). Canonical zip `CADRE_REMESHER/quadre-v0.4.7.zip`, installed in David's Blender 5.2 (10-03); pushed 10-03; the staged student package stays at 0.4.3 (David's call). **David's blind picks 10-03: Exoside 9, Quadre 1** (design doc 5.7): the ruler misses something his eye sees, and finding it comes before more engine work.
- **green_room/** — Procedural character design. Recently reactivated as standalone HIHO software.
- **R&D/** — Research docs + upstream reference codebases (freemocap, skellycam, freemocap_blender_addon, faceit, foscap, snowmocap).
- **PUPPET_RIG_R&D/**, **ARCHIVES/**, **FOR_PROFITS_TESTCASES/** — reference material.

## Hard Rules
- **NEVER delete files.** David handles deletions manually.
- **No code before design.** Research → design doc → code, in that order.
- **One change at a time.** Test after each. Revert if worse.
- **AGPL-3.0** for anything touching FreeMoCap or the HIHO ecosystem.
- **Zero paid dependencies.** Non-negotiable.
- **Word discipline:** "bundled" / "vendored" FreeMoCap. Never "fork." See `project_hiho_mocap_freemocap_relationship.md` for why.

## Where Things Live (memory pointers)
- HIHO MOCAP anchor + supporting memories: see `MEMORY.md` "HIHO MOCAP" section.
- Green Room reactivation: `project_green_room_reactivated.md`
- Quadre: `reference_quadre.md`
- BASEMENT 4-cam install: `project_basement_multicam_install.md`
- License philosophy: `project_software_philosophy_free_open.md`
- Extensions packaging: `project_ppparty_extensions_migration.md`

## Git
Live on GitHub since 2026-08-05: **github.com/davidbayus/hiho-software — PUBLIC since 2026-08-10** (viewable-but-closed: Issues off, contact = email). **Repo boundary rule (2026-08-11): only HIHO-dev-specific material is tracked — code plus design/research/status/audit docs. Dialogue-class artifacts (session handoffs, debriefs, session notes) and anything personal stay OUT; .gitignore carries the patterns.** Laptop pushes at the end of dev sessions (gh CLI, laptop only); desktop never pushes. History was cleaned pre-publish (third-party media + all personal names stripped via filter-repo — snapshot in `ARCHIVES/GIT_BACKUP_PRE_FILTER_2026-08-05/`). GOTCHA: filter-repo hard-resets tracked files; commit or stash before any rewrite. Public flip = David's call after his README pass (`STATUS.md` GitHub bullet has the state).

## Communication & Code Style
- Plain language, artist not engineer. Show what changed, not how it works internally.
- Type hints where reasonable. PEP 8.
- Default to no comments. Only comment WHY when non-obvious.

## Legacy Reference
Previous CLAUDE.md (582 lines, framed around PPParty puppet show + MediaPipe pivot) preserved at [CLAUDE_LEGACY_2026-05-17.md](CLAUDE_LEGACY_2026-05-17.md). Pre-2026-05-06 framing, superseded by V3 multi-cam reframe + 2026-05-17 HIHO MOCAP rename.
