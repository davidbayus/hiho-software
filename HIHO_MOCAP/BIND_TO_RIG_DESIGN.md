# BIND_TO_RIG_DESIGN.md — v1.1 "Bind to Rig" operator

**Status:** design. Awaiting David signoff before code.
**Prereq:** [BIND_TO_RIG_RESEARCH.md](BIND_TO_RIG_RESEARCH.md). Bone-name mapping confirmed against David's Blender 5.0.1 Rigify metarig screenshot (2026-05-26).
**Goal:** Bridge from v1.0 (33 keyframed empties play in viewport) to a rigged character animation — point at any Rigify-metarig-style armature, click one button, the armature follows the mocap.

---

## User flow

1. Student has already pressed **Spawn Rig** — 33 empties are in scene, motion plays.
2. Student adds a Rigify metarig (`Add → Armature → Human (Meta-Rig)`) **or** has imported any armature whose bones use Rigify metarig naming.
3. Student opens HIHO MOCAP panel → **Bind** section → picks the armature → clicks **Bind to Rig**.
4. Operator:
   a. Computes 6 virtual landmark empties from the 33 (midpoints).
   b. Clears any prior HIHO MOCAP constraints on the rig.
   c. For each bone in our constraint table that exists in the rig, adds Copy Location / Damped Track / Locked Track constraints pointing at the empties.
5. Student presses Space → armature plays the motion.

**One button.** No remapping UI for v1.1. Bones either match the Rigify metarig naming convention (in which case it works) or they don't (in which case the bone is skipped with a console warning).

---

## Bone-name translation table (ajc27 logical → Rigify metarig)

ajc27 built their own armature with names like `neck` and `face`. Rigify metarig uses a spine-chain naming convention. We translate once, in our constraint table.

| Body part | ajc27 name | Rigify metarig | Verified in screenshot? |
|---|---|---|---|
| Root of torso | `pelvis` | `spine` | ✓ visible as root |
| Hip stub (right) | `pelvis.R` | `pelvis.R` | ✓ direct child of spine |
| Hip stub (left) | `pelvis.L` | `pelvis.L` | ✓ |
| Lower spine | `spine` | `spine.001` | ✓ child of spine (15 descendants implies full chain) |
| Upper spine (shoulders attach) | `spine.001` | `spine.003` | inferred from 15-descendant count |
| Neck | `neck` | `spine.004` | inferred from canonical metarig |
| Head | `face` | `spine.005` | inferred — we use this bone as the "face" target |
| Shoulder R/L | `shoulder.R/L` | `shoulder.R/L` | ✓ identical |
| Upper arm R/L | `upper_arm.R/L` | `upper_arm.R/L` | ✓ identical |
| Forearm R/L | `forearm.R/L` | `forearm.R/L` | ✓ identical |
| Hand R/L | `hand.R/L` | `hand.R/L` | ✓ identical |
| Thigh R/L | `thigh.R/L` | `thigh.R/L` | ✓ direct child of spine |
| Shin R/L | `shin.R/L` | `shin.R/L` | ✓ (one of 4 thigh descendants) |
| Foot R/L | `foot.R/L` | `foot.R/L` | ✓ |
| Heel R/L | `heel.02.R/L` | `heel.02.R/L` | ✓ |

**Skipped for v1.1:** Rigify face sub-rig (separate complex bone group), toe bones (no MediaPipe data drives them — `foot_index` empty handles foot orientation), spine.002 (unused — our constraint table doesn't have a mid-spine bone), spine.006 (head top — same), breast.L/R (no mocap signal). All cleanly skipped because our table doesn't reference them.

---

## 6 virtual landmarks (computed at bind time, not eagerly)

Added as `hiho_<name>` empties parented to the same skelly root, keyframed across the same frame range as the 33 originals.

| Empty name | Formula |
|---|---|
| `hiho_head_center` | mean(left_ear, right_ear) |
| `hiho_neck_center` | mean(left_shoulder, right_shoulder) |
| `hiho_trunk_center` | mean(left_shoulder, right_shoulder, left_hip, right_hip) |
| `hiho_hips_center` | mean(left_hip, right_hip) |
| `hiho_right_hand_middle` | mean(right_index, right_pinky) |
| `hiho_left_hand_middle` | mean(left_index, left_pinky) |

Reads the body npy file from `last_processed_path`'s recording folder, computes the 6 averaged trajectories, spawns 6 more empties using the same slotted-actions recipe as `output_rig.py`.

**Why lazy not eager:** Eager (in `output_rig.py`) clutters the outliner for students who'll never bind. Lazy (in `bind_to_rig.py`) keeps the 33-empty outliner clean and only adds when needed. Idempotent — re-binding skips if empties already exist.

---

## File map (what we'll create / change)

| File | Status | Purpose |
|---|---|---|
| `core/virtual_landmarks.py` | NEW | Compute the 6 midpoints from body npy and spawn keyframed empties. ~80 lines. |
| `core/bind_to_rig.py` | NEW | The constraint table (translated to Rigify names) + the binder function. ~200 lines including the table. |
| `operators/bind.py` | NEW | `HIHO_MOCAP_OT_bind_to_rig` operator + poll. ~60 lines. |
| `operators/__init__.py` | EDIT | Register the new operator. |
| `properties.py` | EDIT | Add `target_rig: PointerProperty(type=bpy.types.Object, poll=is_armature)`. |
| `ui/panels.py` | EDIT | Add Bind section: rig picker + Bind button. |
| `__init__.py` | EDIT | Version bump 1.0.0 → 1.1.0. |
| `blender_manifest.toml` | EDIT | Same version bump. |
| `HIHO_MOCAP_v1_PLAN.md` | EDIT | v1.1 backlog item #1 marked done. |

No changes to the FreeMoCap runner, the camera manager, or the existing empties spawner. Pure additive.

---

## Operator behavior — pseudocode

```python
def execute(self, context):
    rig = context.scene.hiho_mocap.target_rig
    if rig is None or rig.type != 'ARMATURE':
        self.report({'ERROR'}, "Pick an armature in the Target Rig field")
        return {'CANCELLED'}

    recording_folder = _recording_folder_from_last_processed_path(...)
    if not recording_folder:
        self.report({'ERROR'}, "No processed mocap data. Run Process Mocap first.")
        return {'CANCELLED'}

    skelly_root = _find_skelly_root_for_recording(recording_folder)
    # If skelly_root is None, Spawn Rig hasn't run for this recording — fail clearly

    # 1. Ensure 6 virtual landmark empties exist (idempotent — skip if present)
    virtual_landmarks.ensure_virtual_empties(recording_folder, skelly_root)

    # 2. Clear any prior HIHO MOCAP constraints on this rig
    bind_to_rig.clear_hiho_constraints(rig)

    # 3. Apply the constraint stack
    skipped_bones = bind_to_rig.apply_constraints(rig, skelly_root)

    if skipped_bones:
        self.report({'WARNING'}, f"Skipped {len(skipped_bones)} bone(s): {', '.join(skipped_bones[:5])}...")
    else:
        self.report({'INFO'}, "Bound 20 bones to mocap. Press Space to play.")

    return {'FINISHED'}
```

**Constraint identification (for clear-on-rebind):** Each HIHO-applied constraint gets a name prefix `"HIHO_"` (e.g., `HIHO_CopyLoc`, `HIHO_DampedTrack_0`). `clear_hiho_constraints` walks every pose bone, removes any constraint whose name starts with `HIHO_`. Safe — doesn't touch user-added constraints with other names.

---

## Architecture decisions (committed)

1. **Skip the bake.** Leave constraints live. Pros: user can adjust influence, disable per-bone, see what's driving what. Cons: armature has a constraint stack instead of clean fcurves. v1.2 can add an optional "Bake to Keyframes" button — but the bake will need a slotted-actions-safe implementation, separate effort.
2. **Skip LimitRotation.** ajc27's degree limits assume their FREEMOCAP_ARMATURE bone orientations. Applying to Rigify metarig may clip valid poses. v1.2 can add a toggle once we test on real motion.
3. **Skip fingers.** No Pose-set landmark data for finger phalanges. Hands move as rigid blocks via `hand_middle` virtual empty.
4. **Skip Rigify face sub-rig.** Too many bones, no MediaPipe data drives most of them. Face = `spine.005` head bone only, tracked toward `nose`.
5. **Rigify metarig is the target.** Not the Rigify-generated rig (DEF- / MCH- prefixed). Reason: metarig is what you place pre-Generate; binding before Generate means motion flows through to the generated rig naturally if user generates later.
6. **One armature at a time.** No multi-rig batch bind for v1.1. Each click = one rig.
7. **Picker, not auto-detect.** Per [[operator-file-pickers]]. Even if there's only one armature in the scene, user picks it explicitly.
8. **Substring match for empty targets.** Same as ajc27. Safe given our `hiho_` prefix — no name collisions among the 33 + 6.

---

## Panel layout (new section)

```
HIHO MOCAP
├── Cameras Up
├── Record
├── Process Mocap
│   ├── Take folder: [picker]
│   ├── Calib: [picker]
│   └── [Process Mocap] [Cancel]
├── Output
│   └── [Spawn Rig]
└── Bind (NEW)
    ├── Target Rig: [armature picker]
    └── [Bind to Rig]
```

The Bind section's Target Rig picker is a PointerProperty filtered to ARMATURE type. The Bind to Rig button is grayed out (poll returns False) when no rig is picked or no processed mocap exists.

---

## Edge cases — handled

- **No empties in scene yet.** Operator fails with "Run Spawn Rig first." (Poll catches before button is clickable.)
- **Rig is not in rest pose.** Constraints work from current pose. We document in the report: "If results look bad, clear pose transforms (Pose → Clear → All) before binding." Not auto-clearing — too invasive for users who've customized the metarig pose intentionally.
- **Rig is missing some bones.** Skipped silently per ajc27 line 67. Reported as warning at end.
- **Multiple skelly roots** (user processed two takes). Operator binds to the skelly root matching `last_processed_path`. UI clarity: rename in Properties → Display, e.g. show take date in the picker.
- **Rebind after editing.** `clear_hiho_constraints` removes only HIHO-prefixed constraints. User-added IK, copy rotation, etc. survive.

---

## What we promise tonight

A **Bind to Rig** button that, given:
- A processed mocap take (Spawn Rig has run),
- A Rigify metarig in the scene,

…makes the metarig play back the captured motion. Tested against David's existing 2026-05-26_12-10-19 take + a fresh metarig drop.

---

## What we DON'T promise tonight (v1.2+ backlog additions)

- "Bake constraints to keyframes" button (slotted-actions safe).
- LimitRotation toggle.
- Finger articulation (needs Holistic upgrade — large effort).
- Non-Rigify rig support / bone-name remap UI.
- Foot IK / pole targets / cleanup. ajc27's `hand.IK.R` and `foot.IK.R` entries in the table are unused even there.

---

## Ready-to-code checklist

Once David signs off:

- [ ] `core/virtual_landmarks.py` — write 6 midpoints + spawn empties helper
- [ ] `core/bind_to_rig.py` — translate ajc27 constraint table to Rigify names; write `apply_constraints` and `clear_hiho_constraints`
- [ ] `operators/bind.py` — operator class with poll
- [ ] Register in `operators/__init__.py`
- [ ] `properties.py` — `target_rig` PointerProperty
- [ ] `ui/panels.py` — Bind section
- [ ] Version bump 1.0.0 → 1.1.0 in `__init__.py` + `blender_manifest.toml`
- [ ] Build `HIHO_MOCAP_v1.1.0.zip`
- [ ] David tests at BASEMENT: install zip, run bind on existing take + fresh metarig
- [ ] Update `HIHO_MOCAP_v1_PLAN.md` + `project_hiho_mocap_current_state.md`
- [ ] Write session handoff
