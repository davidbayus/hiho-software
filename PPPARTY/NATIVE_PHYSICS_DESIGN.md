# PPParty Native Physics — Design Doc

**Purpose:** Translate `GOO_PHYSICS_RESEARCH.md` into a concrete implementation plan for PPParty's in-house secondary-motion module. Specifies architecture, file layout, GN sub-groups, preset data, and an ordered step list so a later session can start coding without re-deciding anything.

**Scope (V1):** the chest-up puppet — fingers, wrist joint(s), palm corner jiggle. Lower-body deferred. Wind + collision skipped.

**Status:** 2026-04-23 — written after `GOO_PHYSICS_RESEARCH.md` and David's 3D hand prototype. Pre-code. One commit per step downstream.

---

## Architectural Decision (ADR)

**Decision:** extend the existing Geometry Nodes simulation zone in `operators/marionette/physics.py`. Add reusable GN sub-groups (`PP_ChainVerletSegment`, `PP_JiggleSpring`) and new state items for per-segment positions. No sidecar mesh objects. No DAMPED_TRACK bone constraints. No Python-only bone sim.

**Why not a second sim zone?** Two zones means two re-eval envelopes, two `initialized` flags, two delta-time sources. The existing zone already carries `pos_hand_l/r` + `floated_shl/shr` — hand chains slot in cleanly as more state items.

**Why not Python-handler bone sim?** The body is already pure GN. Hand physics living in a pre-frame Python handler would split the "where does secondary motion happen" answer in two. GN keeps it one.

**Why not Cody's sibling-mesh + DAMPED_TRACK?** Already rejected in the research doc. Sibling mesh per chain is fine for a layer-on-top animator tool; PPParty builds physics into the rig itself.

**Trade-off accepted:** state-item count grows meaningfully (see §5). Sim zone re-evaluation cost scales with state-item count; we mitigate by keeping segments small (2–3 per chain) and deferring any "Bone Resolution > 1" subdivision to V2.

---

## Module Layout

```
ppparty/operators/marionette/
    physics.py              [EXTEND] — add sub-groups + state items + chain wiring
    physics_presets.py      [NEW]    — Python dicts, verbatim from Goo JSON
    hands.py                [NEW]    — build hand geometry + connect tracked inputs to physics
    assembly.py             [EDIT]   — wire hands.py into the main build order
    _common.py              [EXTEND] — helper for chain-segment state-item naming
```

`hands.py` is a sibling of `body_parts.py`. Same style: takes the GN tree + Group Input + attachment sockets, builds nodes, returns output sockets. No `bpy.data` side effects beyond the tree it's handed.

---

## New Group Input Sockets

Added to the marionette modifier interface. Defaults come from the `DEFAULTGEONODES` + `DEFAULTJIGGLE` presets.

### Chain sim (9 sockets — shared across all chain segments for V1)

| Socket name | Type | Default | Source |
|---|---|---|---|
| `Chain Velocity` | Float | 1.0 | `gp_chain_velocity` |
| `Chain Dampening` | Float | 0.25 | `gp_chain_dampening` |
| `Chain Gravity` | Float | 0.02 | `gp_chain_gravity` |
| `Root Falloff` | Float | 0.5 | `gp_chain_root_falloff` |
| `Chain Stiffness` | Float | 0.35 | `gp_chain_stiffness` |
| `Stiff End Fac` | Float | 1.0 | `gp_chain_stiff_end_fac` |
| `Stiff Vel Fac` | Float | 0.1 | `gp_chain_stiff_vel_fac` |
| `Stiff Vel Min` | Float | 0.05 | `gp_chain_stiff_vel_min` |
| `Stiff Vel Max` | Float | 0.5 | `gp_chain_stiff_vel_max` |

### Jiggle sim (6 sockets)

| Socket name | Type | Default | Source |
|---|---|---|---|
| `Jiggle Speed` | Float | 0.80 | `gp_sim_speed` |
| `Jiggle Friction` | Float | 5.0 | `gp_sim_friction` |
| `Jiggle Mass` | Float | 0.15 | `gp_sim_mass` |
| `Jiggle Stiffness` | Float | 0.10 | `gp_sim_stiffness` |
| `Jiggle Damping` | Float | 8.0 | `gp_sim_damping` |
| `Jiggle Sim Influence` | Float | 1.0 | `gp_sim_influence` |

### Hand tracking positions (6 Vector sockets — driven by MediaPipe receiver)

| Socket name | Type | Purpose |
|---|---|---|
| `Hand L Wrist`, `Hand R Wrist` | Vector | Tracked wrist position (MP hand landmark 0) |
| `Thumb L Tip`, `Thumb R Tip` | Vector | Tracked thumb tip (MP hand landmark 4) |
| `Middle L Tip`, `Middle R Tip` | Vector | Tracked "middle" finger tip — driven by MP **index** landmark 8 per `HAND_TRACKING_DESIGN.md` (translation is invisible to the performer) |

**Total new sockets: 21** — 15 physics params + 6 tracked positions.

---

## New Sim Zone State Items

Added to `sim_out.state_items` in `physics.py`. Naming convention: `pos_<chain>_<side>_seg<N>` / `prev_<chain>_<side>_seg<N>`.

### Chain state items

Per hand, 4 chains:
- `fingerA` (thumb, 2 segments — base → mid → tip)
- `fingerB` (tracked middle, 2 segments — base → mid → tip)
- `fingerC`, `fingerD` (untracked side fingers, 2 segments each)

Wrist chain (V1: 1 segment — see open questions): `wrist_<side>_seg0`.

Per-segment state = (pos, prev) as vec3.

Count:
- 4 fingers × 2 segments × 2 sides × 2 vecs = **32 items**
- 1 wrist × 1 segment × 2 sides × 2 vecs = **4 items**
- 4 palm corners × 2 sides × 2 vecs = **16 items**

**Total new state items: 52.** Added to existing 11 → 63 total. Re-eval cost: modest (state is just vec3 read/writes; actual sim math already scales with chain count).

If this proves too heavy at frame time, fallback is to move palm-corner jiggle out of the sim zone and run it as GN Point-Domain attributes on the palm mesh (vertex-level, no state items). That's a V1.1 optimization, not a V1 necessity.

---

## Reusable GN Sub-Groups

Two new node groups live in `physics.py`, patterned on the existing `PP_ShoulderFloat`.

### `PP_ChainVerletSegment`

Computes one segment of a chain, one frame.

**Inputs:**
- `Pos` (Vec3) — current position from sim zone
- `Prev` (Vec3) — previous position
- `Parent Pos` (Vec3) — position of the previous segment in the chain (or the anchor, for segment 0)
- `Goal` (Vec3) — rest-pose position (world-space, computed from palm basis + local offset)
- `Root Falloff Factor` (Float 0–1) — how strongly this segment resists sim (1.0 = fully pinned, 0.0 = fully free). Quadratic falloff by `chain_index / chain_length` computed outside the group.
- `Delta Time` (Float)
- 9 chain-sim params (passed through from Group Input)

**Outputs:**
- `New Pos` (Vec3) — feeds back into sim_out state item
- `New Prev` (Vec3) — previous-frame pos for next tick (= current `Pos`)

**Internal graph (sketch):**

```
# velocity
vel = (Pos - Prev) * Chain Velocity

# damping
vel_d = vel * (1 - Chain Dampening)

# gravity
grav_vec = (0, 0, -Chain Gravity * dt²)

# goal pull (rest-pose memory)
to_goal = Goal - Pos
goal_pull = to_goal * Chain Stiffness * (end_factor_scale)

# velocity-scaled stiffness (the marquee feature)
vel_len = length(vel)
vel_t = clamp((vel_len - Stiff Vel Min) / (Stiff Vel Max - Stiff Vel Min), 0, 1)
vel_stiff = Stiff Vel Fac * vel_t
velocity_stiffness_pull = to_goal * vel_stiff

# integrate
physics_pos = Pos + vel_d + grav_vec + goal_pull + velocity_stiffness_pull

# root falloff blend — segments near the root stay pinned
new_pos = mix(physics_pos, Goal, Root Falloff Factor)

# init
new_pos = mix(Goal, new_pos, not_first_frame)
```

Node types: `ShaderNodeVectorMath` (SUBTRACT, ADD, SCALE, LENGTH, NORMALIZE), `ShaderNodeMath` (MULTIPLY, DIVIDE, CLAMP), `ShaderNodeMix` for the Root Falloff blend. Falloff Factor is computed *outside* the group as `clamp(1 - (chain_index / chain_length) * (1 - Root Falloff), 0, 1)` — the caller passes one pre-computed float per segment.

### `PP_JiggleSpring`

One bone, one frame. Much simpler than chain — no chain index, no velocity scaling.

**Inputs:** `Pos`, `Prev`, `Parent Pos`, `Rest Offset` (Vec3 from parent), `Delta Time`, 6 jiggle params.
**Outputs:** `New Pos`, `New Prev`.

**Internal graph:**

```
target = Parent Pos + Rest Offset
vel = (Pos - Prev) * Jiggle Speed

force_spring = (target - Pos) * Jiggle Stiffness
force_damp = -vel * Jiggle Damping * dt
force = force_spring + force_damp

accel = force / Jiggle Mass
vel_next = (vel + accel * dt) * (1 - Jiggle Friction * dt)
new_pos = Pos + vel_next
new_pos = mix(new_pos, target, 1 - Jiggle Sim Influence)

# init
new_pos = mix(target, new_pos, not_first_frame)
```

---

## Preset Data (`physics_presets.py`)

Verbatim Python translation of the two JSONs. Used by `hands.py` to set modifier socket defaults at Create-Marionette time and by `load_preset(name)` for any runtime re-tune.

```python
# ppparty/operators/marionette/physics_presets.py

CHAIN_PRESETS = {
    "DEFAULTGEONODES": {
        "Chain Velocity": 1.0,   "Chain Dampening": 0.25, "Chain Gravity": 0.02,
        "Root Falloff":   0.5,   "Chain Stiffness": 0.35, "Stiff End Fac":  1.0,
        "Stiff Vel Fac":  0.1,   "Stiff Vel Min":   0.05, "Stiff Vel Max":  0.5,
    },
    "HAIRFRINGE":     {...},   # lifted verbatim from presets/geo_nodes_presets.json
    "HAIRSIDE":       {...},
    "HAIRPONYTAIL":   {...},
}

JIGGLE_PRESETS = {
    "DEFAULTJIGGLE":  {...},   # lifted verbatim from presets/jiggle_spring_presets.json
    "JIGGLELOOSE":    {...},
    "JIGGLESTIFF":    {...},
}

# Per-chain preset assignment for PPParty's hand rig
CHAIN_PRESET_BY_ROLE = {
    "finger":  "HAIRSIDE",     # 3 cartoon fingers + tracked thumb/middle — Cody's side-hair = shoulder-length, matches finger scale
    "wrist":   "HAIRSIDE",     # the flappy-noodle wrist chain
}
JIGGLE_PRESET_FOR_PALM = "JIGGLELOOSE"
```

"..." in the sketch above is a placeholder — the real file hardcodes every number from the JSON, no runtime loading.

---

## Chain Topology (from David's build + `HAND_TRACKING_DESIGN.md`)

Per hand:

| Chain | Anchor (seg 0) | Tracked tip? | Segments | Preset | Notes |
|---|---|---|---|---|---|
| Thumb (`fingerA`) | Palm SW corner | Yes (`Thumb Tip`) | 2 (mid-joint + tip) | HAIRSIDE | Tip is pinned to tracked pos; mid runs chain sim |
| Middle (`fingerB`) | Palm center-bottom | Yes (`Middle Tip`, driven by MP index) | 2 | HAIRSIDE | Same hybrid: tip pinned, mid free |
| Side-A (`fingerC`) | Palm center-bottom | No | 2 | HAIRSIDE | Fully sim-driven — "ambient" finger |
| Side-B (`fingerD`) | Palm center-bottom | No | 2 | HAIRSIDE | Fully sim-driven |
| Wrist | Forearm tip | Palm plate (derived) | 1 | HAIRSIDE | See open question — 1 or 2 segments |
| Palm corners (×4) | Palm center | N/A (jiggle, not chain) | — | JIGGLELOOSE | Each corner is a one-off jiggle bone parented to palm plate |

**Goals (rest poses):** computed per-frame from the palm basis (hand orientation matrix) + local-space finger rest offsets. For David's current build: fingers splay gently downward in rest pose — three fingers curl ~10° inward, thumb offsets laterally.

**Two-sided pinning for tracked chains** (the novel bit Goo doesn't handle): seg 0 is anchored to palm, seg N is anchored to tracked tip, seg 1 runs sim between them. The Verlet distance-constraint pass already handles this — each segment projects onto a sphere of `segment_length` around its parent. With both endpoints fixed, the middle relaxes toward the rest pose via the Goal Pull term.

---

## Hand Geometry (mesh synthesis in GN)

Pattern: extend `body_parts.py`-style dynamic Minkowski capsules + a single chunky palm mesh.

- **Palm plate** — one rounded cuboid, dimensions from David's build. Not a dynamic capsule — it's a static cupped-square mesh generated by a small Mesh Primitive + Subdivision + Bevel subtree. In V1.0 the 4 corner flop is external (separate jiggle bones drive 4 small spheres *on* the corners) — this matches David's build of "ball joints where fingers meet palm." In V2, revisit as weighted vertex groups on the palm mesh.
- **Finger segments** — small dynamic capsules, radius ~0.015 in world units (scaled to puppet), 2 segments per finger. Ball joints at every mid-point and tip are small spheres. Pattern lifted from existing `_add_limb` + joint-sphere code.
- **Thumb** — same as finger but with lateral offset rest pose.
- **Wrist** — one small ball joint between forearm capsule and palm plate.

Geometry follows the `Custom Hand` Object Info switch pattern: if the student has plugged a custom hand mesh into the existing `Custom Hand` socket, the procedural hand is skipped and the custom geometry is used instead. That socket already exists — `hands.py` just respects it.

---

## Slider UI (N-panel)

Section: **"Physics Tuning"** (collapsed by default, advanced users only). Sub-sections:
- **Chain** — 9 sliders, tooltips from `GOO_PHYSICS_RESEARCH.md` parameter decoder.
- **Jiggle** — 6 sliders.
- **Preset dropdown** (bonus, V1.1): pick HAIRFRINGE/HAIRSIDE/etc., apply to all chain sliders at once.

No per-chain overrides in V1 (single param set drives all chains). If "the wrist needs to be floppier than the fingers" becomes a validated finding during tuning, add a `Wrist Stiffness Multiplier` float for V1.1.

Kid-facing sections ("Make It Yours", "Head Design") are untouched.

---

## Implementation Plan (ordered, one per commit)

Each step ends with a zip build + install-test per HANDOFF.md §8. "Revert if worse."

1. **`physics_presets.py`** — verbatim dict of 4 chain + 3 jiggle presets, plus `CHAIN_PRESET_BY_ROLE` + `JIGGLE_PRESET_FOR_PALM`. Pure data, no logic. No Blender dependency — importable anywhere.
2. **Python prototype** (`/tmp/chain_sim_prototype.py`) — standalone `numpy` + `matplotlib`. Simulate a 4-bone chain hanging from a pinned root, apply each of the 4 chain presets, plot settling curves. Reference target: Cody's HAIRSIDE preset visually "looks like hair." Not committed — scratch only. Goal: verify the 9-parameter algorithm before porting to GN.
3. **Jiggle prototype** (`/tmp/jiggle_sim_prototype.py`) — same idea, single-bone spring-mass. Verify JIGGLELOOSE settles without oscillation.
4. **Sim-zone state-item extension** — add 52 new state items to `physics.py`'s `sim_out.state_items.new(...)` calls. Tag section in `_frame_section`. No geometry wiring yet; the state items exist but nothing reads/writes them. Validates the sim zone still evaluates at full state-count.
5. **`PP_ChainVerletSegment` sub-group** — build the node group alongside `PP_ShoulderFloat`. Standalone test: drop one instance into the tree by hand, feed dummy inputs, inspect output in Spreadsheet. No hand geometry wired yet.
6. **`PP_JiggleSpring` sub-group** — same pattern.
7. **`hands.py` geometry** — build palm plate + 4 finger capsules + wrist ball. No physics yet. Tracked positions snap directly to bone positions (same as existing body tracking). Hands work but feel wooden.
8. **Hand tracking wiring — sender side** — extend `mediapipe_sender.py` to the Holistic Landmarker. Send 21 landmarks × 2 hands. Only 3 per hand actually reach the GN inputs in V1; the rest are recorded for V1.1 finger-tracking extension.
9. **Hand tracking wiring — receiver side** — extend `core/osc_receiver.py` for the new Vector sockets (`Hand L Wrist`, `Thumb L Tip`, `Middle L Tip`, etc.). Direct modifier push.
10. **Wire chain physics** — `hands.py` calls `_add_chain_verlet_segment` per finger segment, wires state items through. Test: a still hand shows the rest pose, a moving hand shows chain lag.
11. **Wire jiggle physics** — `hands.py` attaches `_apply_jiggle_spring` to each palm corner. Test: hand acceleration → visible flop.
12. **Assembly wiring** — `assembly.py` calls `build_hands()` between `build_body_parts()` and `build_physics()` (or whatever the correct frame order ends up being — see `REFACTOR_PLAN.md`). Final integration check.
13. **Pedagogical comment pass** on `hands.py` + `physics.py` additions. Match the existing "why this file exists" docstring style from `physics.py` lines 1–103.
14. **Ship `PPPARTY_v1.0.0-alpha.31.zip`.** Install via Blender's Install… dialog. Smoke-test: marionette with physics-driven hand flop.

---

## Validation Plan

Each step has a concrete visual check in Blender:

| Step | Check | Pass criterion |
|---|---|---|
| 2 | Python chain prototype | Matplotlib plot shows chain settle under 30 frames, no oscillation |
| 3 | Python jiggle prototype | Plot shows damped oscillation returning to rest |
| 4 | Sim-zone state items | Marionette still builds; existing body physics unchanged |
| 5 | `PP_ChainVerletSegment` | Spreadsheet shows output vec matches Python prototype for same inputs |
| 7 | Hand geometry | Hands appear at wrist position, follow tracked wrist, but otherwise rigid |
| 10 | Chain physics active | Moving the arm fast: fingers lag behind, settle after arm stops |
| 11 | Jiggle active | Shaking hand: palm corners visibly wobble, stop within ~0.5s of stillness |
| 14 | Full integration | 30 FPS tracking + physics in EEVEE on target hardware |

---

## Open Questions

1. **Wrist: 1 or 2 segments?** David's 3D build shows 1 visible ball joint between forearm and palm. `HAND_TRACKING_DESIGN.md` §Wrist calls for 2 (`forearm → wrist_A → wrist_B → palm_plate`) for more whip. **Proposal:** start with 1 for V1 (matches build, half the state items), add the second in V1.1 if the wrist doesn't read as "floppy enough." Documented divergence from design doc, re-visit after first tuning pass.

2. **Palm 4-corner topology: discrete bones or vertex groups?** David's build = one chunky cuboid mesh. Two options:
   - **(a) Discrete corner bones** — 4 small spheres parented to palm plate, each with its own `PP_JiggleSpring`. Visible as 4 bulges. Matches the existing "ball-joints-are-visible" PPParty aesthetic. Simple to wire.
   - **(b) Weighted vertex groups** — palm mesh has 4 vertex groups (NE/NW/SE/SW corners), each driven by a jiggle bone. Visually smoother — the palm *deforms*, corners don't pop out.
   - **Proposal V1:** (a) — discrete corner spheres. Matches the build, easier to debug, consistent with the "every joint is a visible ball" puppet style. V1.1 can revisit if corners look too distracting.

3. **Rest-pose goal computation.** For each chain segment, the goal is palm-basis-relative. Who computes the palm basis — `hands.py` in GN, or the receiver in Python? **Proposal:** receiver computes once per frame (MP already gives the 3 landmarks we need: 0, 5, 17), sends as a quaternion socket (`Palm Basis L/R`). Saves GN the matrix math.

4. **Chain index → root-falloff factor.** Research doc open question 1 (short chains with quadratic falloff). **Proposal:** compute falloff factor in `hands.py` at build time and hardcode per-segment as a socket default. No runtime math. For a 2-segment finger with Root Falloff = 0.5: seg 0 gets 0.5, seg 1 gets 0.0 (free). Adjust empirically after first tuning pass.

5. **Do we expose `Bone Resolution`?** Cody's "extra subdivision" for smoother chains. **Proposal:** no, V1. Fingers are short; the 2-segment chain is already at the minimum useful length. Skipping this saves 30+ state items.

---

## Non-Goals (V1)

- Per-chain parameter overrides (one chain params set drives all chains)
- Wind forcing (`gp_chain_wind_*` — skipped per research doc)
- Collision (`gp_chain_collision_*` — skipped)
- Preset UI / preset switching at runtime (baked at build time)
- Bone Resolution subdivision
- Vertex-group palm-corner flop (deferred to V1.1)
- Lower-body chains (deferred to Phase 3+)
- User-tunable preset authoring

---

## Next Artifacts

1. **This doc committed** (single commit, no code).
2. **`physics_presets.py`** (next code commit) — the preset dict file. Smallest possible change, no other logic.
3. **Python prototype** — scratch-only, not committed. Verifies algorithm before GN port.
4. After prototype passes visual check: sim-zone state-item extension (commit #3), then sub-groups (#4 + #5), then hand geometry (#6), etc., per the 14-step plan above.

---

## References

- `PPPARTY/GOO_PHYSICS_RESEARCH.md` — the source-of-truth for the algorithm, preset values, and architectural context. This doc is the translation.
- `PPPARTY/HAND_TRACKING_DESIGN.md` — the tracking side of the hand pipeline (Option C, 3 tracked endpoints).
- `ppparty/operators/marionette/physics.py` — the existing sim-zone module this doc extends. Read lines 1–103 for the existing pattern's docstring style.
- `ppparty/operators/marionette/body_parts.py` — the reference pattern for the new `hands.py` module.
- `SOFTWARE/CURVATURE_SEAM_RESEARCH.md` — the style template this doc is descended from (research → design → code, one artifact per commit).

End of design doc.
