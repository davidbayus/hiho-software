# BlendArMocap Foot Math — Research Note for V2 Tier 1 Feet

**Date:** 2026-04-29
**Purpose:** Capture the technique BlendArMocap (cgtinker, GPL-3, discontinued July 2023) uses to derive foot orientation from MediaPipe pose landmarks. Translate it into a clean-room recipe V2 can implement when [HANDOFF.md](HANDOFF.md)'s Tier 1 #2 lands (`foot.L/R` + `toe.L/R` bones).
**Status:** Research doc, pre-code. Sits before any code edits to `core/rig.py` or `core/receiver.py`. Pattern: research → design delta → code, per `feedback_research_doc_first_pattern` memory.
**Authors:** David Bayus + Claude (Opus 4.7).
**License posture:** BlendArMocap is GPL-3. We describe the *technique* in math terms and reimplement clean-room — no code copy. Math itself is not copyrightable; algorithm-level chunks are.

---

## Why This Doc Exists

Two sets of MediaPipe pose landmarks currently flow through the V2 sender and get thrown on the floor at the receiver:

- **Heel.** lm 29 (left), lm 30 (right).
- **Foot_index.** lm 31 (left), lm 32 (right). This is roughly the big-toe knuckle / ball-of-foot region — MediaPipe's name for it.

V2's current `_BODY_DRIVEN_BONES` ends at `lower_leg.L/R`. The leg chain stops at the ankle. There are no `foot.L/R` or `toe.L/R` bones in the rig — those landmarks have nowhere to land.

When [HANDOFF.md](HANDOFF.md)'s Tier 1 #2 ships, that changes. We add foot and toe bones to the rig and need a math recipe for **how to orient them from three pose landmarks per side**. BlendArMocap solved exactly this problem in `mp_calc_pose_rot.py`. The technique is short, sound, and worth preserving even though the project itself is dormant.

This doc is the recipe. The next coding session can implement it directly without re-reading their source.

---

## What We Want To End Up With

Two new bones per side:

```
shin (lower_leg.L)        — already exists, head at knee, tail at ankle
└── foot.L                — NEW. head at ankle, tail at ball-of-foot
    └── toe.L             — NEW. head at ball-of-foot, tail at toe-forward
```

For each new bone we need:

1. **Head world position** (where the bone starts).
2. **Aim direction** (the bone's local +Y axis, which way it points).
3. **Roll reference** (which way the bone's local +Z faces — i.e., is the foot pronated, supinated, or neutral).
4. **Length** (rest length, so `pose_bone.scale.y` can match MP segment length per [HANDOFF.md:23](HANDOFF.md:23)'s dynamic-scale convention).

The final write-out follows the day6c convention from [HANDOFF.md:23](HANDOFF.md:23):

```
pose_bone.matrix = LocRotScale(loc, rot, (1, 1, 1))
pose_bone.scale.y = segment_length / rest_length
```

— never the all-in-one `LocRotScale(loc, rot, (1, y_scale, 1))` path, because Blender's basis-decomposition corrupts under non-uniform scale.

---

## The MediaPipe Foot Landmarks (Left Side, Mirrored for Right)

| MP idx | Anatomical | Notes |
|---|---|---|
| 25 | left_knee | Reliable when leg visible |
| 27 | left_ankle | Reliable when leg visible |
| 29 | left_heel | Sometimes occluded behind sock/shoe; quality varies |
| 31 | left_foot_index | Roughly big-toe knuckle / ball of foot |

Three of these — knee, ankle, foot_index — span a triangle that includes the leg's last segment AND the foot. The fourth (heel) lies inside or near that triangle's plane and is mostly redundant once we have the other three.

This is convenient: **with three landmarks we can build a full orthonormal basis** (a 3×3 rotation matrix), which is exactly what we need to orient the foot bone in 3D.

---

## BlendArMocap's Recipe (Stated In Math Terms)

For each foot, BlendArMocap takes the three points `knee, ankle, foot_index` and constructs an orthonormal basis. Their reasoning, reverse-engineered:

### Step 1 — Pick three points that form a stable, non-collinear triangle

`P0 = knee`, `P1 = ankle`, `P2 = foot_index`. These three are non-collinear in any natural standing or seated pose — the foot bends at the ankle, so foot_index is never on the leg's line. The triangle they span is roughly the **leg-foot sagittal plane** (the front-back vertical slice through the leg).

### Step 2 — Build three direction vectors from that triangle

```
plane_normal  = (P1 - P0) × (P2 - P0)        # perpendicular to the leg-foot plane
                                             # ≈ left/right side direction
edge_a        = P0 - P2  =  knee - foot_index   # diagonal, knee-down-back-to-toe
edge_b        = P1 - P2  =  ankle - foot_index  # foot bone direction reversed
```

Cross product `plane_normal` is the side direction (lateral). The two edges are along the triangle's edges.

### Step 3 — Normalize and orthonormalize

The three vectors above are not yet a clean orthonormal basis (`edge_a` and `edge_b` are not perpendicular to each other). BlendArMocap relies on Blender's `mathutils` matrix construction to handle the orthonormalization — implicitly Gram-Schmidt — but for a clean-room implementation we should be explicit:

```
side  = normalize(plane_normal)
aim   = normalize(P2 - P1)               # ankle → foot_index, the foot bone direction
up    = normalize(side × aim)            # forced perpendicular to both
side  = normalize(aim × up)              # re-derive side so all three are mutually perpendicular
```

Now `(side, aim, up)` is a right-handed orthonormal frame.

### Step 4 — Pack into a 3×3 rotation matrix

For a Blender bone whose local +Y is the aim axis (Blender's bone convention):

```
R = [ side.x  aim.x  up.x ]
    [ side.y  aim.y  up.y ]
    [ side.z  aim.z  up.z ]
```

Each basis vector becomes a column of the matrix. `R` is the rotation that takes the bone's local frame to world space.

### Step 5 — Convert to quaternion

`q = mathutils.Matrix(R).to_quaternion()` — handle Blender-side, no need to reimplement.

This `q` is what we feed into `LocRotScale(loc, q, (1, 1, 1))`.

---

## Why The Cross Product Direction Matters (And Per-Side Sign Flip)

Cross products are handed. `(P1 - P0) × (P2 - P0)` gives one direction; `(P2 - P0) × (P1 - P0)` gives the opposite.

For the LEFT foot, the natural cross-product direction (using BlendArMocap's order) points laterally outward — to the puppet's left. For the RIGHT foot, the SAME formula on the mirrored landmarks (knee = lm 26, ankle = lm 28, foot_index = lm 32) ends up pointing inward, because the knee-ankle-foot_index triangle has the opposite winding.

This matches V2's hand mirror gotcha (per HANDOFF.md history). The fix is the same: **negate one axis on the right side**, empirically determined.

> **Open question (resolve at code time):** which axis on the right side gets negated? Likely `side` (i.e., flip the X column of `R` for `.R` bones). Test both signs against the Rigify metarig at world (2, 0, 0) — the foot should bend down-and-forward when the kid points their toe.

---

## V2 Adaptation — Differences From BlendArMocap's Choices

We don't have to follow their landmark choice exactly. Our constraints differ:

### A. Heel landmark availability

BlendArMocap uses `knee, ankle, foot_index` and ignores heel. Reasoning: the leg-foot triangle is more stable than the foot-only triangle when heel is occluded.

For V2's classroom use case (kids sit at desks), the LEG is the unreliable part — already gated by V1's leg vis-threshold of 0.5 (per [HANDOFF.md:38](HANDOFF.md:38)). The foot itself is more often visible than the leg. So our calculus is reversed.

**Recommendation:** primary basis from `ankle, heel, foot_index` (the foot's own triangle); fall back to BlendArMocap's `knee, ankle, foot_index` only if heel visibility < 0.5. This gives a basis frame that lies *in the foot's plane*, not the leg's plane — which is anatomically more correct (`up` then literally points out the dorsal surface).

For the foot's own triangle:

```
P0 = ankle, P1 = foot_index, P2 = heel

aim   = normalize(P1 - P0)              # ankle → foot_index, "forward"
back  = normalize(P2 - P0)              # ankle → heel, "backward and down"
up    = normalize(aim × back)           # out of dorsal surface (sign flip per side TBD)
side  = normalize(up × aim)
```

The `up` direction is now the foot's actual "up" — what we want for roll.

### B. Ball-of-foot calculation (toe bone head position)

MP doesn't give us a ball-of-foot landmark explicitly. We synthesize:

```
ball = midpoint(heel, foot_index)
```

Defensible: the metatarsal heads (anatomical "ball of foot") sit roughly midway between heel and toe in a flat foot. A more anatomically tuned weight would be `ball = heel + 0.6 * (foot_index - heel)`, but the midpoint is close enough and avoids tuning.

If we want a single foot bone (option A) instead of split foot+toe (option B):

- **Option A:** Foot bone = ankle → foot_index. No toe bone. Simpler. Loses toe articulation but kids barely articulate their toes anyway.
- **Option B:** Foot bone = ankle → ball, toe bone = ball → foot_index. Matches Rigify pattern. Worth the extra bone since the math is essentially free once we have the basis.

**Recommendation:** Option B, matching HANDOFF.md's stated Rigify pattern (`shin → foot → toe`).

### C. Visibility gate

Per V2's existing leg vis-gate convention (kids sit at desks, occluded-leg guesses are garbage):

```
if all of {ankle, heel, foot_index}.visibility >= 0.5:
    drive foot + toe bones with computed orientation
else:
    reset foot + toe bones to rest pose (same pattern as day6c hands)
```

The "reset to rest" path matters — without it the bones freeze in the last detected pose when MP loses the foot, exactly like the day6c hand-stale-freeze bug.

### D. Dynamic Y-scale (foot length)

Day6c established the convention for hands: bone Y stretches per-frame to match MP segment length, so the puppet sizes to whoever's in front of the camera.

For feet: kids' shoes vary, but the camera rarely shows the full foot anyway (desk occludes). The visual payoff of dynamic foot scaling is marginal.

**Recommendation:** skip dynamic scale for v1 of feet. Use fixed rest lengths from the Rigify metarig. We can revisit if classroom testing shows mismatches that read as wrong.

---

## Concrete V2 Implementation Plan (For Next Coding Session)

In priority order, all in [`core/rig.py`](core/rig.py) and [`core/receiver.py`](core/receiver.py):

### 1. Add bones to `BONE_REST_POSITIONS` and `BONE_PARENTS`

Lift rest positions from the Rigify metarig sitting at `(2, 0, 0)` per HANDOFF.md's "Use Rigify metarig as canonical bone reference" pattern. Use the live Anthropic Blender Connector (`mcp__Blender__execute_blender_code`) to read the metarig's `foot.L`, `foot.R`, `toe.L`, `toe.R` head/tail world positions directly — don't guess.

```
foot.L  parent = lower_leg.L
foot.R  parent = lower_leg.R
toe.L   parent = foot.L
toe.R   parent = foot.R
```

### 2. Add `_drive_foot_segment(...)` helper in `receiver.py`

Inputs: ankle, heel, foot_index landmark positions in world space (after MP→Blender axis remap and global anchor).

Output: writes `pose_bone.matrix` for `foot.L/R` and `toe.L/R` per the recipe above.

Pseudocode:

```
def drive_foot(side, ankle, heel, foot_index, pb_foot, pb_toe, vis):
    if min(vis) < 0.5:
        reset_to_rest(pb_foot)
        reset_to_rest(pb_toe)
        return

    aim   = normalize(foot_index - ankle)
    back  = normalize(heel - ankle)
    up    = normalize(cross(aim, back))
    side  = normalize(cross(up, aim))

    if side == '.R':
        side = -side       # empirical sign flip — verify against metarig

    R = matrix_from_columns(side, aim, up)
    q = R.to_quaternion()

    # foot bone
    pb_foot.matrix = LocRotScale(ankle, q, (1, 1, 1))

    # toe bone — same orientation, head at ball-of-foot
    ball = (heel + foot_index) * 0.5
    pb_toe.matrix = LocRotScale(ball, q, (1, 1, 1))
```

### 3. Add `foot.L/R`, `toe.L/R` to `_BODY_DRIVEN_BONES` in `recorder.py`

Per HANDOFF.md's recorder convention so Pass 1 keyframes the new bones.

### 4. Test against the Rigify metarig live

Before declaring done, drop the kid in front of the camera, point one toe forward, point the other toe sideways. Compare against the metarig's foot.L pose under the same input. Sign flips will be obvious — the foot will bend the wrong way.

---

## Adjacent BlendArMocap Techniques — Filed For Future Research Docs

Three other math recipes from `cgt_calculators_nodes/` that are NOT load-bearing for Tier 1 feet but worth their own research docs as adjacent V2 work lands:

### Whole-hand orientation from palm triangle (`mp_calc_hand_rot.py`)

Landmarks 1 (thumb_cmc), 5 (index_mcp), 13 (ring_mcp) form an orthonormal basis for the wrist itself. Currently V2 derives wrist orientation from the body pose chain (Pose 11/12 → arm chain → wrist). BlendArMocap's approach uses the *hand's own internal landmarks*, which could be more robust when the body pose's wrist landmark is occluded but HandLandmarker still has good detection. **File for Phase 7 hand axis-remap calibration.**

### Finger flexion via plane projection (`mp_calc_hand_rot.py`)

For each finger, project all four joints onto the plane defined by `wrist + MCP + fingertip`. Joint angles become 2D-in-plane — out-of-plane noise cancels. Currently V2's `_drive_bone_segment` aims bones along raw landmark-to-landmark vectors with no plane projection. Could clean up jittery finger flex without touching the One Euro layer. **File for noise-reduction iteration on hands.**

### Spine via hip-shoulder triangle (`mp_calc_pose_rot.py`)

MediaPipe pose has no spine landmarks. BlendArMocap synthesizes `hip_center` (idx 33) and `shoulder_center` (idx 34) as midpoints, then forms a triangle (hip_left, hip_right, shoulder_center) and decomposes its plane to get torso orientation. **File for V2.x spine-bone work** if/when chest+pelvis as separate masses isn't enough and we want a real spine chain.

---

## Open Questions

- **Per-side sign flip on `up`:** which axis exactly? `up` itself, or `side`? Resolve empirically against the metarig.
- **Heel-occluded fallback:** is BlendArMocap's `knee, ankle, foot_index` triangle a clean fallback when heel vis < 0.5, or does the basis change discontinuously enough that the foot would visibly snap on the threshold? May need a smooth blend instead of hard switch.
- **Foot scale:** stick with fixed rest length, or join hands in dynamic per-frame scaling? Probably fixed for v1; revisit after classroom testing.
- **Toe bone aim:** same matrix as foot, or recompute? Same matrix is simpler and probably fine — toe articulation in MP is degenerate (no landmarks beyond foot_index). Worth verifying that toe-bone-locked-to-foot-orientation still reads naturally.

---

## References

- [BlendArMocap GitHub repo](https://github.com/cgtinker/BlendArMocap)
- `src/cgt_core/cgt_calculators_nodes/mp_calc_pose_rot.py` — the foot orientation calculator (GPL-3)
- `src/cgt_core/cgt_calculators_nodes/cgt_math.py` — `normal_from_plane`, `generate_matrix`, `decompose_matrix` helpers (GPL-3)
- [V2_DESIGN.md](V2_DESIGN.md) — V2 architecture, two-pass capture
- [HANDOFF.md:46-58](HANDOFF.md:46) — Tier 1 #2 plan for foot.L/R + toe.L/R
- `feedback_use_rigify_as_bone_reference` memory — drop Rigify metarig in scene, read it via the connector
- `feedback_blender_locrotscale_scale_buggy` memory — `pose_bone.matrix = LocRotScale(loc, rot, (1,1,1))` first, scale.y separate
- `feedback_research_doc_first_pattern` memory — research doc → design → clean-room code, no reverse-engineering
- `reference_anthropic_blender_connector` memory — live Blender debug for sign-flip verification
