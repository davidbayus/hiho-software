# Save Out (1.4.22) — Design Note (2026-07-04)

**Status:** David approved the queue item 2026-07-04 ("do 1–3 on your own");
this note records the decisions before code. Unblocked by Bake Animation
(1.4.16) — until bake existed there were no real keyframes to export.
**Panel contract:** Studio panel section 5 already has the format choice
(FBX / GLB / .blend, `export_format` property, shipped in the v1.2 skeleton)
and a stubbed Save Out button. This build replaces the stub with a real
operator; no new UI.

## What it does

`hiho_mocap.save_out` (new `operators/save_out.py`): with a baked armature
selected, opens a save-file dialog (a real picker — pickers survive Blender
restarts, `feedback_operator_file_pickers`) and writes the chosen format:

- **FBX** — `export_scene.fbx`, selection-only (the armature + its child
  meshes, i.e. the skinned character), `add_leaf_bones=False` (no junk
  end-bones in game engines), baked animation on. Exporter defaults
  otherwise.
- **GLB** — `export_scene.gltf`, `export_format='GLB'`, selection-only.
  Exporter defaults otherwise (animations export by default).
- **.blend** — `wm.save_as_mainfile(copy=True)`: saves a copy of the WHOLE
  scene, current file stays open and untouched. (A .blend cannot be
  selection-only; the report says "whole scene" so nobody is surprised.)

Default filename: `<armature's action name, else armature name>.<ext>`,
extension enforced on the typed name too.

## Guards (loud, student-proof)

1. Selected object must be an armature (poll, same as Bake).
2. **If any pose bone still has constraints → refuse:** "This rig still runs
   on live constraints - press Bake Animation first so the motion is real
   keyframes." Exporting a constraint-driven rig produces a T-pose file —
   the classic silent failure; we refuse loudly instead. (After Bake, and
   after Send to Character + Bake, constraint count is 0 — this is exactly
   the boundary Bake already established.)
3. Export failure (disk full, weird path) → the exporter's exception surfaces
   as an ERROR report, never a silent no-file.

Selection handling: the operator selects the armature + its child meshes
itself (students click the armature; forgetting to also shift-click the
character's mesh must not silently export a skeleton-only file).

## Out of scope (deliberate)

- No per-format option UI (Blender's exporters have dozens of dials; the
  student deliverable is "a file that plays in the target app" — defaults +
  the two chosen non-defaults do that). Power users have File > Export.
- The Polish stubs stay stubs; Trim/Smooth remain future builds.

## Test plan

Headless (fixture take, addon from source, factory startup):
1. Spawn rig from `_OUTLIER_BUTTON_TEST` → save_out WITHOUT baking →
   expect CANCELLED with the bake-first message (constraints present).
2. Bake Animation (1800 frames) → save_out FBX, GLB, BLEND to scratchpad →
   all three files exist and are non-trivially sized; FBX/GLB re-import into
   a fresh scene shows an armature with an action (round-trip proof).
3. Character path spot-check deferred to David's Blender (his chibi is his
   scene, not a fixture) — same code path, only the object differs.

David's path: select baked rig → pick format → Save Out → file lands where
he chose; .blend note visible in the report.

**Version:** 1.4.22.
