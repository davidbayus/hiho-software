# Lever A — Across-Palm `side_ref` for Hand Bones (Design Doc)

> ⚠️ **ERRATA / cross-machine context find — 2026-05-01:** This doc was written without first finding [`HAND_SIDE_REF_RESEARCH.md`](HAND_SIDE_REF_RESEARCH.md) (dated 2026-04-30, written by an earlier session on a different machine). The earlier doc covers the same lever with sharper analysis, including a sign-error catch I missed: **`palm_normal` flips between hands without a correction; `across_palm` (= `pinky_MCP - index_MCP`) does not.** The shipped v2.0.1 code uses `across_palm` per the earlier doc's recommendation, NOT `palm_normal` as my original draft proposed. Original wrong-math text below is preserved for historical record but should be read with the correction in mind. **Canonical math: `HAND_SIDE_REF_RESEARCH.md` §3-4. Canonical implementation choice: `across_palm`.**
>
> Cross-machine workflow takeaway: this is exactly the gap David flagged earlier — V2 docs distributed across sessions, prior research from one machine not surfaced before duplicate work starts on another. Worth designing a fix for the workflow itself (see V2 HANDOFF top-of-status note).

Pre-code design per `feedback_research_doc_first_pattern` and `feedback_no_code_before_design`. This doc is the precise "what changes where" companion to [`HAND_ROTATION_NOISE_RESEARCH.md`](HAND_ROTATION_NOISE_RESEARCH.md) and [`HAND_SIDE_REF_RESEARCH.md`](HAND_SIDE_REF_RESEARCH.md). Goal: ship as `v2.0.1.zip` (or whatever the next number is — the recent benchmark cycle ended at day8d).

The design lives entirely in `core/receiver.py`. No sender changes. No new files.

---

## Goal in One Sentence

Compute a stable per-hand "side reference" vector from MediaPipe wrist + MCP landmarks once per frame, and pass it as `side_ref=` to every hand bone's `_drive_bone_segment` call, eliminating the `to_track_quat('Y','Z')` degenerate-fallback flicker on near-vertical hand bones.

---

## Pre-State (current code, day8d benchmark)

The hand drive loop in `apply_landmarks_to_rig` ([`core/receiver.py:625-659`](core/receiver.py#L625)):

```python
if hands:
    for handedness_str, lms_raw in hands:
        # Mirror: MP 'Left' → puppet side 'R', MP 'Right' → 'L'.
        puppet_side = 'R' if handedness_str == 'Left' else 'L'
        driven_sides.add(puppet_side)
        forearm_name = f"lower_arm.{puppet_side}"
        forearm = pb.get(forearm_name)
        if forearm is None:
            continue
        wrist_world = forearm.tail

        wx, wy, wz = lms_raw[0]
        projected = [
            wrist_world + mp_to_blender(
                (lm[0] - wx, lm[1] - wy, lm[2] - wz)
            )
            for lm in lms_raw
        ]

        for bone_suffix, head_idx, tail_idx in _HAND_BONE_SEGMENTS:
            bone_name = f"{bone_suffix}.{puppet_side}"
            if bone_name not in pb:
                continue
            _drive_bone_segment(
                pb[bone_name], projected[head_idx], projected[tail_idx],
                scale_to_segment=True,
            )
            # ... seg_length logging ...
```

**The problem:** the inner `_drive_bone_segment` call passes no `side_ref`. Per [receiver.py:257-271](core/receiver.py#L257), this falls through to `to_track_quat('Y','Z')`, which is degenerate when bone direction ≈ world ±Z. Tiny MP noise → fallback flips → frame-to-frame roll flicker.

**Body bones don't have this problem** because their callsites (lines 508-511, 552-555, 580-586) all pass `side_ref=hip_lateral`. Hands need their own stable side reference.

---

## Post-State (proposed change)

```python
if hands:
    for handedness_str, lms_raw in hands:
        puppet_side = 'R' if handedness_str == 'Left' else 'L'
        driven_sides.add(puppet_side)
        forearm_name = f"lower_arm.{puppet_side}"
        forearm = pb.get(forearm_name)
        if forearm is None:
            continue
        wrist_world = forearm.tail

        wx, wy, wz = lms_raw[0]
        projected = [
            wrist_world + mp_to_blender(
                (lm[0] - wx, lm[1] - wy, lm[2] - wz)
            )
            for lm in lms_raw
        ]

        # NEW: compute palm-normal as side_ref for this hand.
        palm_normal = _compute_palm_normal(projected, puppet_side)

        for bone_suffix, head_idx, tail_idx in _HAND_BONE_SEGMENTS:
            bone_name = f"{bone_suffix}.{puppet_side}"
            if bone_name not in pb:
                continue
            _drive_bone_segment(
                pb[bone_name], projected[head_idx], projected[tail_idx],
                scale_to_segment=True,
                side_ref=palm_normal,                  # NEW
            )
            # ... seg_length logging unchanged ...
```

**Plus a new helper function `_compute_palm_normal(projected, puppet_side)`** defined elsewhere in the module (sibling to `_drive_bone_segment`).

---

## The Math

Three landmarks define the palm plane robustly: wrist (lm 0), index MCP (lm 5), pinky MCP (lm 17). All three are MP's highest-confidence hand landmarks — palm structure has explicit anchors in the model.

```python
def _compute_palm_normal(projected, puppet_side):
    """Compute a stable side-reference vector from palm geometry.

    Returns a Vector pointing roughly perpendicular to the palm plane,
    in Blender world space. Used as `side_ref` for hand bones to avoid
    `to_track_quat('Y','Z')` roll flicker on near-vertical bones.

    The vector points OUT THE BACK OF THE HAND (dorsal direction) for
    both hands — the natural mirror behavior emerges from each hand's
    own landmark geometry, no explicit L/R sign flip needed here.

    Returns None if the cross product is degenerate (anatomically
    impossible — flag in caller and fall back to previous frame's value).
    """
    wrist     = projected[0]
    index_mcp = projected[5]
    pinky_mcp = projected[17]

    palm_x   = (pinky_mcp - index_mcp).normalized()                # lateral across palm
    palm_aim = (((index_mcp + pinky_mcp) * 0.5) - wrist).normalized()  # forward through palm
    palm_normal_raw = palm_x.cross(palm_aim)
    if palm_normal_raw.length_squared < 1e-6:
        return None  # degenerate; caller handles fallback
    return palm_normal_raw.normalized()
```

### Why this orientation, and the L/R sign question

- For the LEFT hand (MP-Left, puppet `.R`): wrist at landmark 0, index_MCP at 5 (lateral toward thumb side), pinky_MCP at 17 (lateral toward pinky side). `pinky_mcp - index_mcp` points from thumb side to pinky side. With `palm_aim` pointing forward through the palm, `palm_x.cross(palm_aim)` points DORSAL (back of hand) by right-hand-rule.

- For the RIGHT hand (MP-Right, puppet `.L`): same landmark indices, same anatomical relationships, BUT MP's coordinate system mirrors — index_MCP for the right hand sits on the OPPOSITE lateral side from the left hand. The `pinky_mcp - index_mcp` vector points the OPPOSITE way in world space, AND the cross product also flips sign — so the resulting `palm_normal` STILL points dorsal (out the back of the right hand). **Both hands end up with `palm_normal` pointing out the back of the hand. No explicit sign flip needed.**

This is the natural-anatomy-emergence pattern that body bones get from `(L_HIP - R_HIP)` for free. We get it for hands here too.

**Verification step before shipping:** add a `print(f"{puppet_side} palm_normal = {palm_normal}")` log line for one frame each side, hold both hands flat with palms facing the floor, confirm both palm_normals point upward (out the back of each hand = upward when palms face floor). If one points down, sign math is wrong; would need a `puppet_side == 'L' and palm_normal.negate()`-style flip, which I do NOT expect to need.

### What `_drive_bone_segment` does with `side_ref`

From [receiver.py:257-282](core/receiver.py#L257):

```python
if side_ref is not None:
    bone_x_proj = side_ref - target_y * side_ref.dot(target_y)
    if bone_x_proj.length_squared < 1e-10:
        # side_ref is parallel to bone direction — degenerate.
        ...fallback to to_track_quat...
    else:
        bone_x = bone_x_proj.normalized()
        bone_z = target_y.cross(bone_x).normalized()
        # build rotation matrix from (bone_x, target_y, bone_z)
```

`side_ref` gets projected onto the plane perpendicular to the bone direction (bone-Y), becomes the bone-X direction. Bone-Z = target_y × bone_x. This produces a consistent, non-degenerate rotation as long as side_ref is not parallel to the bone direction.

For hands, the worst case for "side_ref parallel to bone" is a finger pointing in the dorsal direction — anatomically impossible. The degenerate-projection fallback at line 271 will only trip in pathological MP outputs and self-corrects by falling through to `to_track_quat`. So lever A's worst-case behavior degrades gracefully to current behavior, not worse.

---

## Edge Cases & Fallback

### 1. Cross product near-zero (anatomically impossible but possible from MP noise)

`_compute_palm_normal` returns `None`. Caller substitutes previous frame's `palm_normal` for that side, or falls back to a default value.

```python
# In the hand drive loop:
palm_normal = _compute_palm_normal(projected, puppet_side)
if palm_normal is None:
    palm_normal = _last_palm_normal.get(puppet_side, Vector((0.0, 0.0, 1.0)))
else:
    _last_palm_normal[puppet_side] = palm_normal
```

`_last_palm_normal` is module-level dict, persisted across frames. Initialized empty; the very-first-frame fallback to `Vector((0.0, 0.0, 1.0))` (world up) is a no-worse-than-today behavior because today there's no side_ref at all.

### 2. MP loses the hand mid-session

Already handled by lines 666-673 (the existing reset block). Hand bones get `matrix_basis = _IDENTITY_4X4` when their side isn't in `driven_sides`. This block is unaffected by lever A — palm_normal is only consulted INSIDE the per-hand drive, which the existing code skips on lost hands.

When the hand reappears, `_compute_palm_normal` recomputes from fresh landmarks. `_last_palm_normal[side]` retains its old value but only matters if the cross product is degenerate on the first reacquired frame — extremely unlikely.

### 3. side_ref parallel to bone direction (handled by `_drive_bone_segment` already)

Already-existing code at line 271 falls back to `to_track_quat`. So in the rare pathological case, behavior degrades to today's behavior, not worse.

### 4. Cold-start frame (no prior `_last_palm_normal`)

Default to `Vector((0.0, 0.0, 1.0))`. World-up is a reasonable side reference for hands held in any common pose at session start.

---

## Mirror Convention Confirmation

V2's mirror conventions (per V2 HANDOFF "Architectural state" item 5):
- Upper body (arms, shoulders, hands): MP-L → puppet `.R` (mirror)
- Legs: MP-L → puppet `.L` (direct, undoes MP's flip-induced inversion)
- Feet: MP-L → puppet `.R` (mirror — not yet tested in standing pose)

Hands follow upper-body mirror convention. Lever A doesn't change this — it adds `side_ref=palm_normal` to the existing drive call. The mirror happens at the BONE NAME level (`f_index.01.{puppet_side}`), and the math operates on the projected[] points which are already in puppet world space via the existing `forearm.tail + mp_to_blender(...)` transform.

**No mirror-convention coordination needed for this lever.**

---

## Verification Plan (Pre-Shipping)

Before zipping `v2.0.1.zip`:

1. **Parse-check** with `python3 -m py_compile core/receiver.py` (per the standard resume-pointer recipe in V2 HANDOFF).
2. **Live diagnostic via Anthropic Blender connector** (load-bearing per `reference_anthropic_blender_connector`):
   - Install zip in Blender 5.2 alpha
   - Start Body Mirror, hold both hands flat with palms facing floor
   - Print `palm_normal_L` and `palm_normal_R` once each
   - Confirm both vectors point upward (positive Z component dominates)
3. **Visual inspection** during live mirror:
   - Hold each hand in the four "near-vertical" poses that historically flickered: palm-up open hand pointing forward; thumb-up; fingers-up like halt gesture; clenched fist
   - Pre-v2.0.1: thumb base + finger bases visibly twitch around their own axes
   - Post-v2.0.1: thumb base + finger bases hold steady

If 2 fails (palm_normals point down) → `puppet_side == 'L' and palm_normal.negate()` style flip needed; reopen design discussion before shipping.

If 3 doesn't show qualitative improvement → take a numeric measurement before declaring failure; eyeball can miss subtle improvements that show up in the bake.

---

## Measurement Protocol (Post-Shipping)

This is the data point that decides whether Lever B is worth pursuing. Skipping this means making B/C decisions on intuition.

### What to measure

Mean frame-to-frame quaternion delta on each hand bone class (same metric as the day8b post-shipping diagnostic). Specifically:

- `palm.01-04` (avg)
- `f_thumb.01`, `.02`, `.03`
- `f_*.01` avg across index/middle/ring/pinky
- `f_*.02` avg
- `f_*.03` avg (THE KEY METRIC — this is the 0.30-0.44 baseline)

### How to measure

1. Record a 10-second take with hands held still in a typical performance pose (palms forward, fingers slightly spread)
2. Use the Anthropic Blender connector to introspect the baked NLA strip's rotation fcurves
3. For each hand bone, compute Δq frame-to-frame as `2 * acos(abs(q1.dot(q2)))` per consecutive keyframe pair
4. Take the mean over all keyframe pairs

### Decision tree (post-measurement)

| Post-A `f_*.03` Δq | Verdict | Next move |
|---|---|---|
| `< 0.10` | Lever A was sufficient | Done with item 1.b. Move to next priority (foot drive standing test, OR hip translation research doc). |
| `0.10 - 0.20` | Noticeable but tolerable for K-12 | Document, defer B/C. Revisit if classroom testing complains. |
| `> 0.20` | Lever B becomes worthwhile | Open `HAND_TIP_SMOOTHING_DESIGN.md` for lever B; ship as `day8f.zip`. Re-measure after. |
| `> 0.20` AND palm/finger-base Δq also > 0.05 | Lever A didn't fully take | Diagnose before adding B. Possibly palm_normal itself is too noisy → would need sender-side One Euro on palm_normal. |

The last row is the unexpected-outcome branch and is worth keeping the design open to.

---

## Rollback Plan

If lever A introduces a regression (hands look broken in some pose that day8d handled fine):

1. Revert by removing the `side_ref=palm_normal` addition at the single callsite. Keep the `_compute_palm_normal` helper in place — it does no harm parked, and removing it would mean rewriting the change to re-introduce later. (Per the never-delete rule, dead code stays.)
2. Re-zip as `v2.0.1-revert.zip` from `SOFTWARE/`. Latest installable returns to `day8d.zip`.
3. Document the failure mode in V2 HANDOFF (what specifically broke), update `HAND_ROTATION_NOISE_RESEARCH.md` with the empirical lesson.

The full ~30-line change has a clean reversion footprint. No other systems need to be coordinated with.

---

## Implementation Checklist (for the eventual ship session)

- [ ] Add `_compute_palm_normal(projected, puppet_side)` helper (file-level scope, near the other helpers)
- [ ] Add `_LAST_PALM_NORMAL = {}` module-level dict
- [ ] In `apply_landmarks_to_rig` hand drive loop: compute `palm_normal`, handle `None` via `_LAST_PALM_NORMAL` fallback, store back into `_LAST_PALM_NORMAL`
- [ ] Add `side_ref=palm_normal` to the `_drive_bone_segment` call at line ~651
- [ ] Parse-check via `python3 -m py_compile core/receiver.py`
- [ ] Build `v2.0.1.zip` from `SOFTWARE/` (NOT from inside `PPPARTY_V2/`)
- [ ] David install-tests in Blender 5.2 alpha
- [ ] Verify palm_normal direction via connector print (verification step 2)
- [ ] Visual inspection in four near-vertical hand poses (verification step 3)
- [ ] Post-shipping numeric measurement per the Measurement Protocol above
- [ ] Update V2 HANDOFF with v2.0.1 ship section + post-shipping numbers
- [ ] Update `BENCHMARKS.md` with new entry IF v2.0.1 becomes the new benchmark (i.e., regression-free + measurable improvement)

---

## David — Decision Point

Two questions before code:

1. **Confirm "ship Lever A as v2.0.1" is still the call?** No new redirects?
2. **Approve the design as written?** In particular: the per-hand math (no explicit sign flip), the `_LAST_PALM_NORMAL` previous-frame fallback, and the post-shipping measurement protocol.

If yes to both → next session does the implementation. ~30 lines of code. Should land same-session.

If you want to redirect (e.g., a different fallback strategy, or skip the measurement protocol because it's too involved, or a different next-build numbering), tell me which and I'll revise.
