# Goo Physics — Research Notes

**Date:** April 23, 2026
**Purpose:** Understand how Cody Winchester's Goo Physics addon produces "stylized, rest-pose-preserving secondary motion" on bone chains, so PPParty can reimplement the algorithm natively for its cartoon-hand physics — without vendoring Goo itself.
**Status:** Research doc, pre-code. Sibling: `NATIVE_PHYSICS_DESIGN.md` (next, based on this).
**Authors:** David Bayus + Claude (Opus 4.7)

---

## The Big Insight

Goo isn't novel physics. It's **Wiggle Bones + two design choices**:

1. **Velocity-scaled stiffness** — when the root moves fast, the chain gets floppier; when the root is still, the chain stiffens back into rest pose.
2. **Rest-pose memory** — every bone has a goal position it's pulled toward. Not "dangle under gravity" (cloth), but "return to the shape the rigger drew."

Those two are what make it look like Muppet inertia and what lets anime hair keep its silhouette. The other 13 parameters are dials on top.

**Cody's craft is in the preset values, not the algorithm.** We lift the values. We write the algorithm.

---

## What Goo Actually Is

Four physics types, shipped as one addon. Only two matter for PPParty:

| Type | Engine under the hood | PPParty need? |
|---|---|---|
| **Geo Nodes Chain** | Custom GN sim node tree (Cody's own) — 15 params per chain | **YES** — fingers + wrist |
| **Jiggle Physics** | Wraps Blender's built-in Jiggle modifier — 6 params per bone | **YES** — palm corner pivots |
| Soft Body Chain | Wraps Blender's built-in Soft Body modifier | No |
| Cloth Chain | Wraps Blender's built-in Cloth modifier | No |

Only Geo Nodes Chain is "original." Soft Body / Cloth / Jiggle are wrappers that expose Blender's native simulators with Cody's preset curation on top.

Cody, verbatim in the tutorial: *"cloth… responds to gravity very, very highly… it doesn't retain its shape at all… that's actually a really good example of why you can't use this for an anime character, because it will just completely flatten their hair."* Geo Nodes Chain is the answer to that problem — it's the stylized one.

---

## Cody's Architecture (and Why We Skip Most of It)

How Goo wires itself up, from `functions.py:create_geonodes_chains`:

1. For each bone chain, **create a new MESH object** — a row of verts + edges mirroring the bone positions.
2. Create a second object (Empty) as the chain's "Root Ref Object."
3. Add a GN modifier to the mesh object, linked to a node group `GooPhysics_SimulationProcess` from `gp_sim_nodes_tree.blend`.
4. Push the 15 chain parameters onto the modifier as Group Input values.
5. On the original armature, add `DAMPED_TRACK` (+ other) **bone constraints** pointing each simulated bone at the corresponding sim-mesh vertex.

In Cody's own words: *"Goo is not a tool for riggers, it's a tool for animators. It's meant to be a tool that layers on top of an existing rig rather than being built into a rig."*

**The consequences we want to avoid:**

- **Rig-edit breaks it.** Cody: *"if you're trying to do any kind of rig edit mode changes while goofy is active, it will break."* The mesh-chain was built from bone positions at creation time; it doesn't track edits.
- **Blender 5.2 RNA refactor breaks it.** Confirmed today — `mod[inputs["Root Ref Object"].identifier] = chain_root_ref` throws `TypeError: id properties not supported for this type` because Object-type GN inputs can no longer be assigned via ID-property syntax. Same bug species that killed Green Room's drivers and forced PPParty's "direct modifier push" workaround.
- **Workflow is bake-and-edit.** Cody: *"as soon as this finished baking… this is purely just animation on keyframes on your bones directly."* Goo is designed for offline animation, not live tracking. We need the sim to run every frame, driven by webcam input.

**What we want instead:** physics built **into** the puppet's existing GN modifier tree, driven by **direct modifier push** from the MediaPipe receiver, same pattern that already works for the body. One rig, one modifier, one render.

---

## The Algorithm — Wiggle Bones + Velocity Scaling + Goal Pull

For David's mental model: this is **Wiggle Bones with three bolt-ons**.

Wiggle Bones (the reference you already know):
```
for each bone in chain:
    pos_new = pos + velocity * (1 - damping)
    velocity = pos_new - pos_prev
    constrain distance to parent
    apply stiffness toward rest
```

Goo adds:

**1. Goal-position pull (rest-pose memory).** Each bone has a target position — the rigger's intended shape. A spring force pulls each bone toward its goal:
```
force_goal = (goal_pos - pos) * stiffness
```
Without this, cloth collapses under gravity. With it, anime hair holds its silhouette.

**2. Velocity-scaled stiffness (the Muppet-inertia trick).** Stiffness isn't constant — it scales with how fast the root is moving:
```
stiffness_effective = stiffness_base * lerp(vel_min, vel_max, root_speed / vel_fac)
```
- Root still → stiffness high → chain snaps back to goal quickly.
- Root whipping around → stiffness low → chain trails with real inertia.
This is the feature no other Blender system ships out of the box. It's what makes stylized secondary motion feel alive.

**3. Root-pin falloff.** Influence of the sim on the chain decays from the root outward. At the root: 0% sim, 100% rigger intent. At the tip: 100% sim. Controlled by a quadratic curve whose shape is the `Root Pin Size` parameter. Cody describes the falloff as *"quadratic… taking on this central property."*

That's the whole Geo Nodes Chain algorithm. Everything else is parameters on top.

---

## The 15 Parameters — Geo Nodes Chain

Lifted verbatim from `gp_sim_nodes_tree.blend` interface (seen via `mod[inputs[...]]` writes in `functions.py:432-439` and the preset JSON).

| # | Name (on modifier) | Bone-property name | What it does |
|---|---|---|---|
| 1 | Velocity Scaler | `gp_chain_velocity` | Global time-scale on the sim. 1.0 = real time. <1 = underwater. >1 = frenetic. |
| 2 | Velocity Dampening | `gp_chain_dampening` | Drag on each bone's velocity per step. Higher = settles faster. |
| 3 | Gravity Strength | `gp_chain_gravity` | Downward acceleration constant. Most presets use 0.02 (very light). |
| 4 | Root Pin Size | `gp_chain_root_falloff` | How many bones near the root are pinned to rigger intent. Higher = more pinning, less sim. |
| 5 | Goal Strength | `gp_chain_stiffness` | Spring force pulling each bone toward its rest-pose goal. The marquee stylization dial. |
| 6 | Goal End Strength | `gp_chain_stiff_end_fac` | Multiplier on goal strength at the chain tip (usually weaker — lets the tip swing). |
| 7 | Goal Velocity Factor | `gp_chain_stiff_vel_fac` | How strongly root velocity modulates stiffness. The Muppet-inertia knob. |
| 8 | Goal Velocity Min | `gp_chain_stiff_vel_min` | Lower clamp on the velocity-scaled stiffness (floor for "how floppy can it get"). |
| 9 | Goal Velocity Max | `gp_chain_stiff_vel_max` | Upper clamp on the velocity-scaled stiffness (ceiling for "how stiff when still"). |
| 10 | Wind Strength | `gp_chain_wind_strength` | Amplitude of a built-in stylized wind oscillation. |
| 11 | Wind Noise Strength | `gp_chain_wind_noise_strength` | Noise overlaid on wind direction. |
| 12 | Wind Noise Scale | `gp_chain_wind_noise_scale` | Spatial frequency of wind noise. |
| 13 | Collision Distance | `gp_chain_collision_dist` | Distance at which the sim starts resolving collision. |
| 14 | Collision Friction | `gp_chain_collision_friction` | Tangential damping on contact. |
| 15 | Sim Influence | `gp_sim_influence` | Overall blend between sim output and rigger rest pose. 1 = full sim, 0 = no sim. |

Parameters 10–12 (wind) and 13–14 (collision) are orthogonal to the core algorithm. **PPParty V1 should skip both** — we don't need wind for cartoon fingers, and collision adds a whole dependency chain (collider objects, GN collision shader). Scope: 9 parameters (1–9 + 15).

---

## The Four Geo Nodes Presets — Catalogued Verbatim

From `presets/geo_nodes_presets.json`:

| Preset | velocity | dampening | gravity | root_falloff | stiffness | end_fac | vel_fac | vel_min | vel_max | wind | coll_dist | sim_influence |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **DEFAULTGEONODES** | 1.00 | 0.10 | 0.02 | 0.25 | 0.25 | 0.25 | 0.20 | 0.10 | 1.00 | 0.25 | 0.010 | 1.00 |
| **HAIRFRINGE** (bangs) | 1.00 | 0.10 | 0.02 | **0.92** | **0.50** | 0.20 | 0.20 | 0.10 | 1.00 | 0.06 | 0.010 | 1.00 |
| **HAIRSIDE** (medium) | 1.00 | 0.10 | 0.02 | **0.50** | 0.41 | 0.20 | 0.20 | 0.10 | 1.00 | 0.08 | 0.010 | **0.5** |
| **HAIRPONYTAIL** (long) | 1.00 | 0.10 | 0.02 | 0.42 | **0.00** | 0.20 | 0.20 | 0.10 | 1.00 | 0.125 | 0.010 | 0.5 |

**Pattern recognition:**

- **`velocity`, `dampening`, `gravity`, `end_fac`, `vel_*` don't change across presets** — those are the engine constants. Cody settled on them once.
- **`root_falloff` is the short-chain vs long-chain knob.** Bangs = 0.92 (mostly pinned, tips wiggle), ponytails = 0.42 (sim dominates).
- **`stiffness` is the silhouette-holding knob.** Bangs = 0.50 (strong goal pull, stays framed on face), ponytails = 0.00 (no rest-pose, free-swinging).
- **`sim_influence` at 0.5 for longer chains** — halving the sim means the rest pose bleeds through more. Cody uses this to soften long-hair motion.

**Starting values for PPParty hand chains (hypothesis, to tune in code):**

- **Fingers (3 bones, tracked-tip)** → clone HAIRSIDE but bump `root_falloff` to ~0.65 (shorter chain, more pinning). `stiffness` ~0.40 (cartoon fingers want to read as "hand-shaped").
- **Wrist chain (2 bones, A+B, untracked)** → HAIRSIDE base. This is the "gesture lag" chain Cody's velocity-factor was made for.
- **Non-tracked fingers (full flop)** → DEFAULTGEONODES or HAIRSIDE.

These are guesses. Tune in Blender after the module lands.

---

## Jiggle Physics — The Sibling Model

For palm corners. 6 parameters, from `presets/jiggle_spring_presets.json`:

| Preset | speed | friction | mass | stiffness | damping | influence |
|---|---|---|---|---|---|---|
| **DEFAULTJIGGLE** | 0.80 | 5.0 | 0.15 | 0.10 | 8.0 | 1.0 |
| **JIGGLELOOSE** | 0.77 | 5.0 | 0.20 | 0.10 | **10.06** | 1.0 |
| **JIGGLESTIFF** | 0.83 | 5.0 | 0.15 | **0.30** | 10.06 | 1.0 |

**How it's different from chain sim:** each bone is an **independent spring-mass** with one parent. No chain structure, no velocity-scaled stiffness, no goal positions beyond the parent. Cody: *"each bone is actually an independent bone that just happens to have one parent… it's mostly meant for little one-off things that have one parent that can kind of like move around, like the backpack example."*

**Algorithm (much simpler than chain):**
```
for each jiggle bone:
    target = parent_pos + rest_offset
    force_spring = (target - pos) * stiffness
    force_damp = -velocity * damping
    velocity += (force_spring + force_damp) / mass
    velocity *= (1 - friction * dt)
    pos += velocity * speed
```

Classic mass-spring-damper. That's it.

**HAND_TRACKING_DESIGN uses JIGGLELOOSE for the 4 palm corner pivots** — it's a match: one-parent (the palm plate), location-based offset, secondary animation only.

---

## Chain Settings vs Bone Settings (the Blender Pattern)

Cody stores parameters on **pose bones**, because pose bones are the only persistent property host that survives save/load. But some params are **chain-scoped** (apply to all bones in a chain) and some are **bone-scoped** (per-individual-bone).

Implemented via two update callbacks in `properties.py`:
- `update_chain_prop()` — writes the value to *every* bone in the chain. Used for the 15 Geo Nodes params.
- `update_bones_prop()` — writes only to the selected bones. Used for `gp_sim_influence` (the falloff).

**Cody's SIM influence falloff** is the one per-bone knob: a linear or quadratic curve from 1.0 at root to lower values at tip. Press "Apply Linear Sim Falloff" and it writes `1.0, 0.75, 0.5, 0.25` down a 4-bone chain. The quadratic version is more aggressive — `1.0, 0.56, 0.25, 0.06`.

**For PPParty:** we don't need this pattern at all. Our puppet's physics parameters live on the **GN modifier** as interface sockets, not on pose bones — they're already "chain-scoped" by modifier assignment, and we drive them from code, not from selected bones. One less thing to port.

---

## What Cody Says (Transcript Quotes for the Record)

From `~/Desktop/Automatic Stylized Simulation for Bones - Goo Physics-1.mp4`:

1. *"Goo is not a tool for riggers, it's just a tool for animators… meant to be a tool that layers on top of an existing rig rather than being built into a rig."* (00:01:14) — defines the scope Goo was built for; defines the scope we're breaking.
2. *"Return to like a straight rest pose, even though it's got a little wibbly-wobbly-ness to it… will actually maintain the shape a little better… which is really important for anime characters who need their hair to kind of be a certain shape."* (00:02:37) — marquee stylization claim.
3. *"Jiggle physics is interesting because it doesn't really have a chain… each bone is actually an independent bone that just happens to have one parent."* (00:18:55) — cements jiggle as the "palm corner" model.
4. *"We've been using this add-on for like two years internally, specifically so that we can create these stylized animations with physical simulations as a foundation and increase our speed of production."* (00:00:51) — it's a production-tested recipe. The values work.
5. *"Presets are only applied when you press the Apply preset button."* (00:14:10) — one-shot writes, not live bindings. Mirrors our own preset-loader pattern.

---

## What to Keep, What to Drop

| Keep | Drop |
|---|---|
| The 15-parameter algorithm model (9 of them, skipping wind + collision for V1) | Mesh-chain sibling object pattern |
| Preset VALUES verbatim (HAIRFRINGE / HAIRSIDE / HAIRPONYTAIL / DEFAULTGEONODES + 3 jiggle presets) | DAMPED_TRACK bone-constraint wiring |
| Chain vs per-bone sim-influence falloff concept | Linked `gp_sim_nodes_tree.blend` (we write our own GN) |
| Velocity-scaled stiffness as the marquee feature | Bake-to-keyframe workflow |
| Jiggle as a separate simpler mode for palm corners | Collision collection / collider objects (V1 skip) |
| Rest-pose goal pull | Stylized wind (V1 skip; revisit if the hand feels too static) |

---

## Design Implications for PPParty's Native Module

1. **Physics lives INSIDE the existing GN modifier**, not as a sibling mesh object. Specifically: extend `operators/marionette/physics.py` (the Verlet sim zone) with a new "chain sim" pattern alongside the existing endpoint-based sim. Same sim zone, same re-evaluation envelope.

2. **Drive bones via sim-zone output, not bone constraints.** PPParty already does this for tracked endpoints (chest, hips, hands, feet). Extend the pattern: untracked finger bones read their position from sim-zone outputs just like tracked ones do — the only difference is whether the position came from MediaPipe (tracked) or the chain solver (untracked).

3. **Two sim modes in the module:**
   - **`chain_sim(chain_endpoints, params)`** — Verlet + goal + velocity-scaled stiffness. For fingers and wrist chain.
   - **`jiggle_sim(bone, parent_pos, params)`** — mass-spring-damper, per-bone. For palm corners.
   Both share the same time-step and live in the same GN frame.

4. **Preset values as a Python dict**, not a JSON file. PPParty doesn't need user-facing preset editing in V1 — students don't tune physics. Bake the 4 GN presets + 3 jiggle presets directly into `physics_presets.py`.

5. **Interface sockets on the modifier** for the 9 chain params + 6 jiggle params = 15 total new sockets. Far fewer than Cody's 30+ bone properties, because we don't have the "select bones and push values" UX — we drive from code.

6. **Tracked endpoints anchor the chain.** For the pointer finger (partially tracked per `HAND_TRACKING_DESIGN`): tip is a tracked endpoint, base is anchored to the palm plate, the middle bone runs chain sim between them. This is the novel integration that Cody's addon doesn't support — his chains are fully sim-driven or fully rigger-driven, not hybrid.

---

## Open Questions

1. **Chain length sensitivity.** Cody's presets assume hair-length chains (6–20 bones). Our fingers are 3-bone chains. The `root_falloff` quadratic curve may need retuning for short chains — the "quadratic from 1.0 to 0.0 across N bones" function is sensitive to N.
2. **Division parameter.** Cody exposes `Bone Resolution` (default 1) — extra sub-bone vertices for a smoother sim. Do we need it? Probably not for fingers (3 bones × 3 joints = 9 sim points is enough). Keep the option in the API, default to 1.
3. **Tracked-endpoint integration.** How exactly does a chain sim behave when the TIP is a pinned tracked point and the ROOT is also pinned (both palm + pointer tip)? The middle bone has two hard constraints — the usual Verlet relaxation + goal pull should solve this, but it's a two-sided boundary problem we haven't prototyped.
4. **World-scale vs character-scale.** Cody's gravity = 0.02 is tuned for a character-height rig of ~1.8 m. PPParty's puppet is at world-scale ~1.0. Gravity might need a ~1.8× bump, or everything feels too floaty. Verify empirically.
5. **Root velocity source.** For fingers, is the "root velocity" measured at the wrist, the palm plate, or the whole hand's world transform? Affects how the Muppet-inertia feature reads. Likely: palm plate — it's the parent of everything.

---

## References

- **Goo Physics source** — `/tmp/goo_reference/goo_physics/` (scratch-unzipped from `~/Desktop/goo_physics 1_0_1.zip`)
  - `functions.py:292` — `create_geonodes_chains` (the mesh-chain builder)
  - `functions.py:416` — the 5.2 RNA break
  - `properties.py:584–824` — the 30 pose-bone properties (15 chain + 6 sim + others)
  - `presets/geo_nodes_presets.json` — the 4 chain presets, verbatim values
  - `presets/jiggle_spring_presets.json` — the 3 jiggle presets
  - `gp_sim_nodes_tree.blend` — the actual GN simulation logic (readable only in Blender)
- **Cody Winchester tutorial** — `~/Desktop/Automatic Stylized Simulation for Bones - Goo Physics-1.mp4` + transcript `~/Desktop/Automatic Stylized Simulation for Bones - Goo Physics-1.txt`
- **Shane Addy, "Wiggle Bones"** — the canonical Blender secondary-motion pattern David already knows. Goo is "Wiggle Bones + goal + velocity scaling."
- **Verlet integration** — Müller et al., "Position Based Dynamics" (2006) for the distance-constraint relaxation that underlies chain sim.
- **Related PPParty docs:**
  - `PPPARTY/HAND_TRACKING_DESIGN.md` — the architecture this physics module serves
  - `SOFTWARE/CURVATURE_SEAM_RESEARCH.md` — this doc's style template and the pattern we're repeating (research → design → code)
  - `PUPPET_RIG_R&D/JIM_ROSE_MARIONETTE_RESEARCH.md` — the waist-cord principle that's already shaping the body rig

---

## Next Steps

1. **Write `NATIVE_PHYSICS_DESIGN.md`** (separate commit). Answers the one open architectural question — single sim-zone pattern or a new one for chains? Lean: extend the existing sim-zone with chain solvers, keep one re-evaluation envelope.
2. **Prototype in Python (not GN) first.** A standalone script that runs the 9-parameter chain sim on a list of points, outputs positions over time. Plots in matplotlib. Compare settling behavior against Cody's HAIRSIDE visually. This is the "does the algorithm actually work in isolation" test.
3. **Port to GN once the Python prototype matches.** The GN port is mechanical; the algorithm tuning happens in Python.
4. **Defer everything else until hand geometry is confirmed** — David's 3D hand prototype in Blender tells us exactly how many bones, what rest pose, what scale. Physics tuning is downstream of that.

End of research doc.
