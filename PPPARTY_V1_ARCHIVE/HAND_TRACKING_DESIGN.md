# PPParty Hand Tracking Design — Option C (Hybrid Endpoint + Physics)

**Status:** Design doc (pre-code, R&D phase)
**Authors:** David Bayus + Claude (Opus 4.7)
**Created:** 2026-04-20
**Target:** PPParty V1.0.0 — after refactor Steps 2–8 complete, after template system and recording pipeline

---

## Why this doc

Hand tracking is on the V1.0.0 next-steps list but queued behind the `create_marionette.py` refactor, template system, and recording pipeline. This doc captures the architecture decided 2026-04-20 so it survives the gap until it's time to build.

MediaPipe Holistic Landmarker gives us 21 landmarks per hand for free — the cost is in model inference, not readout. The design question is **which landmarks to believe**, not whether there's enough data. This doc records the answer.

---

## The three architectures we considered

| Option | What it tracks | What it feels like |
|---|---|---|
| A — Per-finger Verlet | All 21 landmarks, tips as endpoints, full IK chains | Realistic, 3D floppy fingers. Inherits MediaPipe fingertip jitter directly into the rig. |
| B — Scalar channels | `grip` + `thumb` scalars + wrist rotation matrix | Muppet paddle. Robust (averaging kills jitter) but fingers animate on a pre-designed path — no flop. |
| **C — Hybrid (3 endpoints + physics)** | Wrist + thumb tip + index tip only | Tracked spatial intent for grab/point. Goo Physics handles everything else. Muppet inertia for free. |

**Chosen: Option C.** Matches puppet design (cartoon hand, 3 fingers + thumb). Reuses existing Verlet/IK/Goo-Physics machinery. Answers all three design constraints — pointing, grabbing, Studio Track friendliness — while keeping tracked data at 3 points per hand instead of 21.

---

## Architectural note — Goo Physics is the unified secondary-motion engine

David confirmed during this session (2026-04-20): **all untracked elements on PPParty puppets run on tweaked Goo Physics**, not a mix of Verlet-only, hand-rolled dampers, or bone-constraint hacks. **One physics engine project-wide.**

**Scope beyond hands:** future hair, cheeks-under-impact, earrings, clothes, accessories, any dangling body part — anything that wobbles or lags behind tracked pose. Today most of this doesn't exist yet; the decision locks the engine choice for when it does.

**Why:**
- Pedagogically clean — ART102 student learns one system, one preset library
- Goo's velocity-scaled stiffness (`gp_chain_stiff_vel_fac`) is the marquee feature for Muppet-inertia motion — no other Blender system ships this out of the box
- David's existing Wiggle Bones mental model maps directly (same CS: per-bone Verlet + stiffness/damping; Goo adds modern GN sim + velocity scaling)

**The split:**
- **Tracked bones** → MediaPipe endpoints + Verlet + analytical IK (existing PPParty architecture, unchanged)
- **Untracked bones** → Goo Physics with a preset chosen per chain type

---

## Puppet anatomy

Cartoon hand, 3 fingers + 1 thumb. Captured in `~/Desktop/HANDSKETCH1.pdf` (David's sketches from session 2026-04-20).

### Palm plate
- Cupped-square shape, oriented with TOP facing up
- **4 corner pivots — ambient flop only (untracked).** Physics-driven secondary motion. Corners jiggle with hand acceleration, sells "rubber palm" aesthetic. **No gestural function** — no scooping, no flattening. Pure Goo Physics flourish.
- **3 finger-base pivots** on the top edge where fingers radiate out
- **1 thumb pivot** on the side

### Wrist — flappy, 2 physics joints
```
forearm → wrist_A → wrist_B → palm_plate (endpoint #1)
             ↑ both untracked, Goo Physics ↑
```

Both wrist joints are untracked. Goo Physics velocity-scaled stiffness drives "ambient gesture" — fast arm motion whips the wrist lag behind; still arm lets wrist hold pose. This is where gesture richness lives without spending tracking data.

### Fingers — 3 cartoon fingers + 1 thumb
- Each finger = 3-bone chain (base, mid, tip)
- **2 fingers fully untracked** — pure Goo Physics flop (HAIRSIDE-style preset: stiff base, flappy tip)
- **1 finger partially tracked — the pointer** (fingertip 2, the visually-centered middle cartoon finger). Tip is an endpoint.
- **Thumb partially tracked** — tip is an endpoint.

---

## The 3 tracked endpoints

| # | Puppet anchor | MediaPipe source | Role |
|---|---|---|---|
| 1 | Hand base (palm root, below wrist articulation) | Hand landmark 0 (WRIST), or equivalently the existing pose `LEFT/RIGHT_WRIST` position already piped in | Spatial position — "where the hand IS" |
| 2 | Thumb tip | Hand landmark 4 (THUMB_TIP) | Opposition, grab, thumbs-up |
| 3 | Pointer tip | Hand landmark 8 (INDEX_FINGER_TIP) | Pointing direction, spatial gesture |

### Index → middle-finger translation convention

The human's anatomical index finger (MP landmark 8) drives the puppet's **visually-centered middle cartoon finger**. The kid points with index; the puppet points with its center finger. Translation is silent — the performer never sees it. The middle position reads as "central axis" and keeps the pointing gesture on the palm axis, which looks more iconic than an off-center point.

### Palm basis (wrist orientation)
- Computed from hand landmarks 0 (wrist), 5 (index MCP), 17 (pinky MCP) → 3×3 rotation matrix (palm plane + normal)
- The 3 tracked endpoints are **local to the palm plate** and transform through this basis
- Goo Physics runs in world space on the transformed positions
- Same compositional pattern as existing body tracking — the palm basis plays the role `bt_shl_delta` plays for shoulders

---

## MediaPipe pipeline changes

**Current:** `mediapipe_sender.py` uses FaceLandmarker + PoseLandmarker (2 async detectors).

**Target:** `HolisticLandmarker` — face + pose + hands in one unified graph, reusing pose detection to localize hands. Cheaper than face+pose+hands as 3 asyncs.

This is a **structural refactor** to `mediapipe_sender.py` — not enormous, not free. Deferred until after the curriculum refactor completes.

---

## UDP packet extension

```
FLAG_HAS_HANDS = 0x04     (add to MPPT flags byte)

Per hand (both L and R):
  hand_base_xyz    : vec3        — duplicates pose wrist for redundancy
  thumb_tip_xyz    : vec3
  pointer_tip_xyz  : vec3
  palm_basis       : mat3 (or quat for compactness — 4 floats vs 9)
```

With quaternion palm basis: **13 floats per hand, 26 for both.** Trivial bandwidth.

Bump the version byte. Receiver must tolerate old senders (no hand data) and new senders (hands present) — same three-tier probe pattern as `TrackingReceiver`.

---

## Rig changes (Blender side)

1. **New bones in the armature** (currently only has a `head` bone):
   - `forearm_L/R` → `wrist_A_L/R` → `wrist_B_L/R` → `palm_plate_L/R`
   - 4 corner pivots per palm (`palm_corner_NE/NW/SE/SW_L/R`)
   - 4 finger chains per hand, 3 bones each (`thumb`, `finger_A`, `finger_B_pointer`, `finger_C`)

2. **New Verlet endpoints** in the sim zone: `hand_base_L/R`, `thumb_tip_L/R`, `pointer_tip_L/R` = 6 new endpoints. Added to GN Group Inputs, wired to modifier via direct push from receiver (same pattern as existing body tracking).

3. **Analytical IK for mid-joints** — reuse existing `_compute_mid_joint()` (law of cosines + double cross product):
   - Thumb mid joint: between thumb base (palm) and thumb tip (endpoint)
   - Pointer mid joint: between pointer base (palm) and pointer tip (endpoint)

4. **Goo Physics application** (preset picks are starting hypotheses — tune after install):
   - Wrist chain (A+B): GOOSIM or HAIRSIDE
   - 2 non-tracked finger chains: HAIRSIDE
   - Palm plate 4 corners: JIGGLELOOSE or custom low-stiffness

5. **Object Info sockets** (Studio Track) — 4 new sockets: `Custom Thumb`, `Custom Finger A`, `Custom Finger B Pointer`, `Custom Finger C`. Plus `Custom Palm Plate`. Student plugs in custom geometry; Switch node replaces the default capsule. Identical pattern to existing `Custom Chest`/`Custom Hips`/`Custom Hand`/`Custom Foot`.

---

## Open palm vs closed fist — does anything drive it?

**Today's decision: nothing drives it directly. It emerges from physics.**

- Closed fist → hand moves slowly; fingers settle toward palm via Goo stiffness at rest pose (which should be slightly curled)
- Open palm → hand moves fast / holds high; velocity-scaled stiffness lets fingers lift
- Explicit grip scalar NOT derived from MediaPipe in this design

**Revisit if:** physics alone doesn't read as "gripping." If so, add a derived grip scalar (average fingertip-to-wrist distance) and use it to bias the finger chain's rest pose. Low priority — try physics-only first.

---

## Performance / hardware notes

- Goo Physics chains per hand: 4 fingers + 4 palm corners + 1 wrist (2 joints) = ~9 chains per hand, ~18 for both
- Plus 2 tracked endpoints with analytical IK (thumb mid, pointer mid) per hand = 4 IK computations
- Needs benchmarking on weakest CACHE hardware before committing
- Mitigations available if slow:
  - Asymmetric update rates (face @ 30fps, pose @ 15fps, hands @ 10fps — One Euro hides the gap)
  - Single-hand mode (track dominant hand only)
  - Skip palm corner flop on low-end (graceful degradation — palm becomes rigid plate)
- One Euro filter per endpoint, tuned tighter than face (less latency is OK because hand motion is deliberate)

---

## Studio Track integration

Students design custom puppet hands by:
1. Modeling thumb + 3 finger meshes (any shape — cartoon, alien, mitten, tentacle, etc.)
2. Optionally modeling a custom palm plate
3. Plugging each into the corresponding Object Info socket
4. Physics just works — Goo presets apply regardless of geometry

The tracked endpoints are **invisible** to the student. They never see the tracking pipeline. They design silhouettes.

This mirrors what already works for `Custom Chest`/`Custom Hips` (Jim Rose waist-cord principle: shape is student expression, motion is engine).

---

## What this design does NOT do

- No per-finger articulation of the 2 non-tracked fingers (MediaPipe's noisy fingertip landmarks intentionally dropped)
- No fist-clench deformation of the palm plate
- No finger curling based on MP landmark data — only on physics inertia
- No chirality overrides from MP — receiver trusts MP's L/R labels, may flip under fast motion (see open questions)
- No object collision between fingers and the puppet body (future enhancement, not V1.0.0)

---

## Open questions to sit with

1. **Depth jitter.** MediaPipe Z is monocular-inferred. Wrist and fingertip Z will jitter more than XY. One Euro helps, but depth-axis gestures (point toward camera) may need a deadband.
2. **Hand leaves frame.** MP returns partial data — receiver needs clear behavior: freeze at last position? drop to idle? gravity-droop via physics?
3. **Chirality flip.** MediaPipe labels handedness but can flip under fast motion. May need to bias via pose wrist positions (if `pose_left_wrist` is on the left of frame, trust that over MP's hand label).
4. **Goo Physics install on student machines.** Addon is GPL, redistribution-friendly, but depends on matching Blender version. Lock to 5.2+. Installation becomes a setup step — document in CACHE deployment guide.
5. **Palm plate rig topology.** Is the 4-corner pivot implemented as separate bones with physics, as vertex groups weighted to a soft body, or as GN-driven mesh deformation? TBD during prototyping.

---

## Prerequisites (do these first)

Per the reordered V1.0.0 build sequence (CLAUDE.md, 2026-04-20 — "one great puppet before templates"), hands are **Phase 2**, immediately after the refactor. Template system and recording pipeline move to Phases 5 and 4 respectively.

1. Finish `create_marionette.py` refactor Steps 2–8 (see `REFACTOR_PLAN.md`) — tag `v1.0.0-alpha.4-refactor-complete`
2. Finalize The Puppet's hand geometry — extend current sketch with to-scale palm plate dimensions, finger lengths, thumb length + attachment angle, and idle rest pose (the Goo Physics anchor)
3. Install Goo Physics on the refactored PPParty rig and validate HAIRSIDE / GOOSIM / JIGGLELOOSE behavior on sample bone chains
4. Benchmark existing sender on weakest available laptop — establish baseline FPS before adding hand inference
5. Prototype Holistic Landmarker refactor of `mediapipe_sender.py` (face + pose + hands in one unified graph, replacing the two-async approach)

---

## Related documents

- `SOFTWARE/R&D/BODY_TRACKING_RESEARCH.md` — MP + Apple Vision + FreeMoCap analysis (parent research doc)
- `SOFTWARE/PPPARTY/REFACTOR_PLAN.md` — refactor that must finish first
- `DR_BAYUS/SESSION_HANDOFF_2026-04-20.md` — session this design came from
- `~/Desktop/HANDSKETCH1.pdf` — David's hand sketches (palm plate, flappy wrist, 3 control points)
- `~/Desktop/goo_physics 1_0_1.zip` — companion addon (source of physics presets)
- `~/Desktop/Automatic Stylized Simulation for Bones - Goo Physics.mp4` — Cody Winchester demo video

---

## Session spirit

This doc is R&D. No code is authorized by its existence. When hand tracking moves up the V1.0.0 priority list, revisit this doc first and confirm the decisions still hold — MediaPipe evolves, Blender 5.2 may have shipped stable, new landmarker APIs may exist. Architecture survives; implementation details may not.
