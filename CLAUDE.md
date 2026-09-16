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
- **CADRE_REMESHER/** — Quadre quad remesher (alt to Exoside). **v0.3.8 (2026-09-16)**: the 0–1 Detail slider is gone, replaced by an Exoside-style **Quad Count** integer field (default 5000) that the finish message reports against ("2,014 faces (you asked for 2,000)"); density constant recalibrated 0.42→0.50 (asks now land within ~±3%, was ~20% heavy); symmetry halves the engine target (was delivering 2.7× the ask); between-stage file checks close a hard-crash path. Floor ~650–1,400 faces, ceiling ~38K, symmetry still 10–30% heavy at low counts. Tested headless on 5.2.0 LTS (Suzanne ×2 densities, bucket 7,846→7,799/7,675) and installed from the zip in a sandboxed Blender. Canonical zip `CADRE_REMESHER/quadre-v0.3.8.zip`; notes `CADRE_REMESHER/QUADRE_v0.3.8_NOTES_2026-09-16.md`. Awaiting David's live look in the 09-16 class.
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
