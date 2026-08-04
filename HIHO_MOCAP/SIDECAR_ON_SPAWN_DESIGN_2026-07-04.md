# Scene Clock on the Spawn Path (1.4.20) — Design Note (2026-07-04)

**Status:** David approved the queue item 2026-07-04 ("do 1–3 on your own");
this note records the decisions before code, per the design-first rule.
**Parent design:** `LOAD_TAKE_FPS_DESIGN_2026-07-02.md` (its step 3 said the
sidecar read "belongs in process.py's post-process flow eventually" — David
hit exactly that gap on the first real BASEMENT recording 2026-07-03:
Record → Process → Spawn Rig never sets the scene clock; only Load Take does.
That's the PRIMARY student path.)

## Decision

Move the clock-set into a shared helper and call it from **Spawn Rig**, which
is the single place both student paths converge:

- `Record → Process → Spawn Rig` (the gap) — fixed.
- `Load Take` (verified in 1.4.18) — already wraps `spawn_rig`, so it gets the
  helper for free; its own inline block is replaced by the same helper call so
  there is exactly one copy of the logic. Messages stay byte-identical to the
  1.4.18-verified strings ("Scene clock set to Nfps…", "Old take - no
  recording info…") — the verified UX must not drift.

**New file:** `core/scene_clock.py` — `set_scene_clock_from_take(scene,
body_npy)` returns `(message, is_warning)`. Logic is the 1.4.18 block moved
verbatim: read `HIHO_RECORDING_INFO.json` two levels above the npy; on
success set `render.fps`, `fps_base=1.0`, `frame_start=1`,
`frame_end=<npy frame count>`; unreadable sidecar → warning, scene untouched;
missing sidecar → legacy warning, scene untouched. Never guess silently.

**Call sites after this change:**
- `operators/spawn_rig.py` — calls helper after the rig is built, appends the
  message to its report (WARNING if legacy/unreadable, INFO otherwise).
- `operators/load_take.py` — inline block replaced by helper call, identical
  composition of its final message. On the Load Take path the helper runs
  twice (once inside spawn_rig, once in load_take) — it is idempotent (same
  sidecar, same values) and cheap (one small JSON + npy header via mmap);
  accepted for single-source-of-truth. Documented here so nobody "fixes" it.
- `operators/output.py` (Spawn Empties) — untouched: debug feature, not a
  student path, and one change at a time.

**Interaction with `core/output_rig.py:101`** (grows `frame_end` via `max()`
on spawn, never shrinks, never touches fps — the 2026-07-03 incidental find):
unchanged. The helper runs AFTER spawn, so the exact range it sets wins,
same ordering Load Take already proved.

## Out of scope (deliberate)

- No panel UI changes, no properties, no recorder changes (sidecar write
  shipped and verified in 1.4.18).
- No fps handling in `process_take.py` — the clock belongs to whoever touches
  the scene, and only the spawn does.

## Test plan

Headless (Blender 5.2 CLI, addon loaded from source, David's install
untouched):
1. Fixture take WITH sidecar (`HIHO_CAPTURES/2026-07-02_14-10-31_OUTLIER_BUTTON_TEST`,
   fps 60): scene deliberately 24fps/250 frames → set `last_processed_path` →
   `spawn_rig` → expect fps 60, range 1–1800, INFO message.
2. Legacy take WITHOUT sidecar (`HIHO_CAPTURES/2026-07-02_14-10-31`): scene
   24fps → `spawn_rig` → expect fps still 24, WARNING message.
3. Load Take equivalence: helper output strings equal the 1.4.18 verified
   strings (string-compare in the test).

David's path (when he's next at the rig): record a junk take → Process →
Spawn Rig → scene clock reads 60fps without touching Load Take.

**Version:** 1.4.20.
