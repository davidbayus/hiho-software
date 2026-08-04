# v2.0.2 Design — Constant-Stance + Floor Constraint

Pre-code design per `feedback_research_doc_first_pattern` and `feedback_no_code_before_design`. Companion to [`WORLD_SPACE_ANCHORING_RESEARCH.md`](WORLD_SPACE_ANCHORING_RESEARCH.md). Goal: ship as `PPPARTY_V2_v2.0.2.zip`. Implements the recommended pairing (1a + 2a) from the research doc, using **Option 2 — declarative bone constraint** per David's design choice (2026-05-01 afternoon, after a comparison of imperative-clamp vs. constraint approaches).

The design touches `core/rig.py` (new constraint setup) and `core/receiver.py` (documentation-only comment block). No sender changes. No new files.

---

## Goal in One Sentence

Document constant-stance as an explicit design choice (not an unfixed bug), and add a `LimitLocation` bone constraint to each foot bone in `Create V2 Rig` so puppet feet can't dip below the rest-pose floor when MP loses lower-body tracking or estimates feet below ground.

---

## Why Constraint, Not Imperative Python (recap from chat)

**Imperative clamp** (modify `pose_bone.matrix.translation.z` in `apply_landmarks_to_rig`) was the original proposal. It works during live drive but doesn't apply during NLA playback or timeline scrubbing if no live drive is running. Lives in code, not in the rig — less inspectable.

**Declarative constraint** (LimitLocation on each foot bone with `min_z = rest-pose foot Z`, `owner_space='WORLD'`) was the chosen approach. Standard Blender pattern; works in live drive AND NLA playback AND scrubbing AND hand-keyframed test poses; visible in the Bone Properties panel; pedagogically clean (students who know Blender constraints understand it immediately); zero changes to `apply_landmarks_to_rig`.

**V1's Verlet-in-geonodes approach** is a third option that doesn't carry forward — V2 retired physics entirely; there's no mesh, no particles to collide. Bone constraints are the natural V2 substitute.

---

## Two Changes, Designed Together

### Change A — Constant-stance documentation (no behavior change)

Add a comment block at the pelvis-anchor site in `_drive_bone_segment` ([`core/receiver.py`](core/receiver.py)) explaining that the parent-less branch (which lands the pelvis at world origin via `rest_head_local`) is intentional puppet-show pedagogy, not a bug. So future readers don't try to "fix" a deliberate choice.

### Change B — Floor constraint on foot bones (rig setup)

Add a LimitLocation constraint to each foot bone in `build_v2_rig`, after bones are created and the rig settles into rest pose. The constraint clamps foot bone Z in world space.

---

## Pre-State (current code, v2.0.1 benchmark)

### Receiver — pelvis anchor (no change planned, just documentation)

In `core/receiver.py`, `_drive_bone_segment` has a parent-less branch that anchors the pelvis at world origin:

```python
if pose_bone.parent is not None:
    parent = pose_bone.parent
    rest_head_in_parent_local = (
        parent.bone.matrix_local.inverted() @ pose_bone.bone.head_local
    )
    head_armature = parent.matrix @ rest_head_in_parent_local
else:
    head_armature = pose_bone.bone.head_local.copy()  # PELVIS LANDS HERE
```

### Rig — foot bones in rest pose

From [`core/rig.py:89-90`](core/rig.py#L89), foot bone rest positions:

```python
"foot.L": ((0.10, 0.00, 0.05), (0.10, -0.10, 0.00)),
"foot.R": ((-0.10, 0.00, 0.05), (-0.10, -0.10, 0.00)),
```

Foot HEAD (ankle) at z=0.05; tail (ball-of-foot) at z=0.00. The rig comment at line 69 explicitly notes: "T-pose: feet on the ground (z=0), head top around z=1.75." So **the rig is already built with the floor at z=0**, the puppet stands on the floor in rest pose. No rig-rebuild needed for v2.0.2.

`build_v2_rig` ends at line 317, returning the rig object after all bones are created and parented. We add constraint setup right before the return.

---

## Post-State (proposed change)

### Change A — Constant-stance comment block in `_drive_bone_segment`

Find the parent-less branch:

```python
else:
    head_armature = pose_bone.bone.head_local.copy()
```

Replace with:

```python
else:
    # CONSTANT-STANCE (v2.0.2 explicit design choice):
    # The parent-less branch lands the pelvis at world origin via
    # rest_head_local. The puppet does NOT translate when the
    # kid walks. This is intentional puppet-show pedagogy — see
    # WORLD_SPACE_ANCHORING_RESEARCH.md for rationale and
    # candidate alternatives if revisited in V2.x. Performer
    # translation is captured via upper-body lean (chest /
    # shoulder / arm sway), not pelvis position. Classical
    # marionette stage convention; matches V0/V1 PPParty restriction
    # discipline ("simple inputs, expressive outputs").
    head_armature = pose_bone.bone.head_local.copy()
```

### Change B — Floor constraint setup in `build_v2_rig`

At the end of `build_v2_rig`, after `bpy.ops.object.mode_set(mode='OBJECT')` and before `return rig_object`:

```python
# v2.0.2: ground-plane (Floor) clamp via LimitLocation constraint.
# Prevents foot bones from dipping below the puppet's "stage floor"
# when (a) MP loses lower-body tracking (kid sits at desk), or
# (b) MP estimates a foot below ground (extreme poses, occlusion
# noise). The constraint reads the rest-pose foot head Z so it
# self-calibrates if the rig dimensions ever change.
#
# Owner space = WORLD: clamps the bone's world-space location.
# With the armature at world origin (V2's default), this matches
# the rig comment "T-pose: feet on the ground (z=0)."
#
# Clamps the bone HEAD (ankle). Foot tail (toe) can still dip
# slightly below floor when toes-pointed-down — that's a v2.0.3
# candidate (custom driver, or second constraint targeting tail).
# See WORLD_SPACE_ANCHORING_RESEARCH.md "Cost" section.
#
# Bone constraints chosen over imperative receiver-side clamping
# per V2_0_2_DESIGN.md "Why Constraint, Not Imperative" — applies
# during live drive AND NLA playback AND timeline scrubbing,
# survives in rig state for inspection.
for foot_name in ('foot.L', 'foot.R'):
    pb_foot = rig_object.pose.bones[foot_name]
    rest_head_z = pb_foot.bone.head_local.z  # 0.05 per BONE_REST_POSITIONS
    constraint = pb_foot.constraints.new('LIMIT_LOCATION')
    constraint.name = "Floor (v2.0.2)"
    constraint.use_min_z = True
    constraint.min_z = rest_head_z
    constraint.owner_space = 'WORLD'
```

### bl_info bump

In `__init__.py`:

```python
"version": (2, 0, 1),  →  "version": (2, 0, 2),
```

---

## How the Constraint Interacts with V2's Drive

V2's `_drive_bone_segment` writes `pose_bone.matrix = M` to set the bone's world-space matrix. Blender computes the basis matrix needed to produce M given the parent chain. **Constraints then apply on top of the basis** during dependency-graph evaluation.

So the order of operations per frame is:

1. `apply_landmarks_to_rig` writes `pose_bone.matrix` for foot.L, foot.R via the existing `_try_drive_foot` calls. Blender derives basis from these writes.
2. Blender evaluates pose: rest matrix → parent chain → basis → CONSTRAINT STACK
3. The LimitLocation constraint sees the bone's world-space location. If Z < min_z, it clamps Z up to min_z.
4. The final `pose_bone.matrix` (post-constraint) reflects the clamped position. Visual = clamped feet.

**Recording/bake interaction:** the recorder reads `pose_bone.matrix_basis` (or rotation_quaternion / scale, equivalently) to keyframe. The basis is the PRE-CONSTRAINT value — what `_drive_bone_segment` wrote. So the bake stores un-clamped basis values; the constraint applies again at NLA playback time, clamping each frame on the fly.

This means the bake is "live" — if FLOOR_Z ever changes (e.g., rebuilt rig), recordings from the old rig adapt automatically to the new floor. Robust.

If the constraint is ever REMOVED from the rig, recordings would render un-clamped (no floor). The constraint IS the contract; removing it removes the floor by design.

---

## Edge Cases

### 1. Foot detection lost (MP doesn't see legs)

Already handled by existing `_try_drive_foot` visibility check. When MP loses the foot, the function falls back to rest-pose basis (foot at rest position, ankle at z=0.05). Constraint is a no-op in this case (rest position is exactly at min_z). Feet rest at floor — exactly the desired behavior.

### 2. Legs visible AND foot estimated above ground

Constraint only fires when world-Z < min_z. If MP estimates foot above floor, constraint does nothing. Foot animates freely.

### 3. One foot off the ground (kid on one leg)

Standing foot's drive lands near floor; constraint may or may not fire depending on exact rotation. Lifted foot's drive lands above floor; constraint silent. Each foot independent.

### 4. Toes pointed down (foot rotated such that tail Z < head Z)

Constraint clamps head Z. Tail (toe) can dip slightly below floor. Minor visible artifact for v2.0.2; v2.0.3 candidate to fix via a second constraint or driver targeting the tail.

### 5. Recording / bake interaction

Already covered above — basis stores un-clamped, constraint applies live during playback. No recorder changes needed.

### 6. Constraint removed by accident (e.g., kid in pose mode deletes it)

Visible artifact: feet pass through floor. Recovery: re-run `Create V2 Rig` (which is idempotent — clicking the button re-creates the rig with constraints intact). Per the operator's existing docstring: "If a rig of the same name already exists in the file it is removed first so this operator is idempotent."

---

## Verification Plan (Pre-Shipping)

1. **Parse-check** with `python3 -m py_compile core/rig.py core/receiver.py __init__.py`
2. **Live diagnostic via Anthropic Blender Connector:**
   - Install zip in Blender 5.2 alpha
   - Run `Create V2 Rig`
   - Select `foot.L` in pose mode → Bone Properties → Bone Constraints panel: confirm "Floor (v2.0.2)" LimitLocation constraint is present with `use_min_z=True, min_z=0.05, owner_space='WORLD'`
   - Same for `foot.R`
3. **Visual inspection during live mirror:**
   - Stand fully in frame; verify feet animate normally
   - Sit at desk (occluded feet); feet should rest at floor (z=0.05 head, ~z=0 tail) instead of dipping below
   - Pose foot manually in pose mode (rotate ankle bone Z to push tail down through floor); confirm constraint clamps head at z=0.05
4. **Bake test:**
   - Record a short take with sit/stand transitions
   - Play back the NLA strip; verify feet stay at floor

---

## Implementation Checklist

- [ ] Add Floor constraint setup loop in `build_v2_rig` after `mode_set('OBJECT')` and before `return rig_object`
- [ ] Add CONSTANT-STANCE comment block at parent-less branch in `_drive_bone_segment` (`core/receiver.py`)
- [ ] Bump `__init__.py` `bl_info["version"]` from (2, 0, 1) to (2, 0, 2)
- [ ] Parse-check via `python3 -m py_compile core/rig.py core/receiver.py __init__.py`
- [ ] Build `PPPARTY_V2_v2.0.2.zip` from `SOFTWARE/`
- [ ] David install-tests in Blender 5.2 alpha
- [ ] Verify constraint exists per Verification Plan step 2 (Connector inspection)
- [ ] Visual inspection per step 3
- [ ] If passes: update HANDOFF + BENCHMARKS to mark v2.0.2 as new benchmark; preserve v2.0.1 entry as historical record
- [ ] Add comment-only TODOs for v2.x candidates: stance-blend, foot-tail clamp, dynamic floor empty

---

## Rollback Plan

If v2.0.2 introduces a regression:

1. Comment out the constraint loop in `build_v2_rig`. Run `Create V2 Rig` again to rebuild the rig without constraints. Revert behavior to v2.0.1.
2. Or: select foot.L / foot.R in pose mode, delete the "Floor (v2.0.2)" constraint manually. Same effect.
3. Re-zip if needed; `v2.0.2-revert.zip`. Latest installable returns to `v2.0.1.zip`.
4. Document the failure mode in V2 HANDOFF + update `WORLD_SPACE_ANCHORING_RESEARCH.md`.

The constant-stance comment block has no rollback — it's documentation, no behavior change.

---

## V2.0.3 Candidates (out of scope here)

- **Floor empty target** — replace LimitLocation with a Floor constraint that targets a "Floor" empty in the scene. Kid/teacher can drag the empty to set custom stage floors (tabletop puppet shows, raised platforms, etc.). Pedagogically interesting affordance.
- **Foot-tail clamp** — second constraint or driver to keep the tail (toe) above floor when foot rotates toes-down. Eliminates the residual minor artifact.
- **N-panel floor-height slider** — exposes FLOOR_Z as user-adjustable for teachers. Lives in "Advanced Setup" collapsed section so kids don't see it.
- **Stance-blend** — visibility-driven blend toward planted rest pose when MP loses lower body. Currently the rest pose IS planted (foot at floor by design), so this is mostly nice-to-have for smoothing transitions.
- **Rebuild rig with pelvis at z=0.95 vs z=0 baseline** — already done! Rig is already built with feet at floor. No work needed here.
