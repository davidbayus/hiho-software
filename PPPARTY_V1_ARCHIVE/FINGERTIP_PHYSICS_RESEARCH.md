# Fingertip Physics — Tracked ↔ Untracked Transition Research

**Date:** 2026-04-25
**Purpose:** Close the one gap the existing physics docs leave open — what the fingertip chain *does* when MediaPipe stops seeing the hand. The alpha.50 dropout symptom (fingertips frozen at last-tracked position above the puppet) made that gap visible. This doc researches the transition before any code lands.
**Status:** Research doc, pre-code. Sits **between** `GOO_PHYSICS_RESEARCH.md` (algorithm) and `NATIVE_PHYSICS_DESIGN.md` (build plan). Pattern: research → design delta → code, per `feedback_research_doc_first_pattern`.
**Authors:** David Bayus + Claude (Opus 4.7).

---

## Why This Doc Exists (and Why It's Narrow)

Two docs already cover the in-house Goo-style chain physics:

- **`GOO_PHYSICS_RESEARCH.md`** — the algorithm: Verlet + goal pull + velocity-scaled stiffness + root-pin falloff. The 9 chain params, the 6 jiggle params, the four preset value-tables lifted verbatim from Cody's JSON.
- **`NATIVE_PHYSICS_DESIGN.md`** — the architecture: extend the existing sim zone, two reusable sub-groups (`PP_ChainVerletSegment`, `PP_JiggleSpring`), 48 new state items already declared and passthrough-wired in [`physics.py:1380-1400`](SOFTWARE/PPPARTY/operators/marionette/physics.py:1380), 14-step build plan.

Both docs assume **tracking is always available**. The chain has two anchors: palm (root) and tracked tip (end). They model it as a "two-sided pinning" boundary problem — Verlet relaxation between two fixed points, with the goal-pull term holding the rest pose.

What they do not address: **tracking is intermittent**. MediaPipe loses the hand the moment it leaves frame, gets occluded, drops below detection confidence, or rotates past gimbal limits. On a webcam feed with kids waving their arms in a classroom, dropouts are not an exception — they're a constant. The puppet must look natural across the seam.

This doc is just about the seam.

---

## The alpha.50 Symptom (Restated as a Physics Problem)

What David saw: hand in frame → fingertips track. Hand leaves frame → fingertips appear "snapped to a single anchor point above the puppet" while the palm relaxes back toward the body. Arm tubes stretch between the two. Reads as a teleport.

What's actually happening (diagnosed [HANDOFF.md:54-62](SOFTWARE/HANDOFF.md:54)):

1. Sender omits the hand section from its UDP packet when no hand is detected ([osc_receiver.py:218-219](SOFTWARE/PPPARTY/core/osc_receiver.py:218): *"Missing hands are omitted from the entries dict so the push side can distinguish 'not present' from 'present at origin'"*).
2. Receiver's `_pending` dict is drained per tick. No hand entry → no write.
3. The `bt_thumb_*` / `bt_index_*` / `bt_wrist_*` modifier sockets retain their **last written value** — i.e., the last in-frame world position, often "near my face" because that's where my hands typically were when they exited.
4. The current `_with_fallback` helper in [hands.py:330-366](SOFTWARE/PPPARTY/operators/marionette/hands.py:330) length-checks the primary socket and switches to the rest pose only if length ≈ 0. Frozen-at-last-value is **nonzero**, so the switch picks "primary" → fingertip stays frozen at the last-tracked location.
5. The palm, meanwhile, is computed from `hand_l/r_pos` ([body_parts.py](SOFTWARE/PPPARTY/operators/marionette/body_parts.py)) which lerps Verlet endpoint with `tracked_hand_l = shoulder_visual + normalize(bt_shl_delta) × bt_arm_l_ext × Arm Length`. `bt_shl_delta` is from POSE landmarks (MP 11/13/15) — those keep flowing while body tracking is on, **independent of HandLandmarker**. So palm continues moving while fingertips don't.

In other words: the existing fallback is correctly handling **first-frame zero** (pre-tracking startup), and it **cannot** handle **post-acquisition dropout** (tracking came and then went). Two different operating conditions look the same from inside the GN graph because the GN graph cannot see "is data flowing right now" — only "what value is on the socket right now."

This is the "stale-value-vs-no-value" problem that every distributed system runs into. Push-based protocols where "no message" means "no change" are fine for slow-moving truth (a config value, a person's name) and broken for fast-moving truth (sensor data, tracking landmarks). The fix lives outside the data — in a *liveness signal* that says "this stream is currently producing values."

---

## Prior Art — How Other Tracking Systems Handle the Same Seam

Research into how other systems model tracked → untracked transitions, since "fingertip chain physics with intermittent input" isn't a problem we invented.

### MediaPipe HandLandmarker itself

The MediaPipe Tasks API ships **two confidence scores** alongside every hand landmark frame:

- **`presence_score`** — model's confidence that *some hand* is in the frame. Drops sharply when the hand exits.
- **`handedness_score`** — model's confidence in left/right classification. More about identity than presence.

Per the MediaPipe docs (Apr 2026): *"When presence is below the configured threshold, no landmark output is emitted for that hand."* That's exactly our sender's current behavior — model says "no," sender drops the section. **What we are not doing is exposing the presence score itself.** It's available; we're throwing it away. (Verify in a future code session by checking `mediapipe_sender.py`'s `HandLandmarker` callback.)

### FreeMoCap (the cited reference codebase, AGPLv3, in `R&D/freemocap-main/`)

FreeMoCap is an offline pipeline — it processes recorded video into numpy arrays after the fact, then bakes to keyframes. Dropouts in the source video produce **NaN** entries in the output array. Downstream code (the Blender bake script) **interpolates across NaN runs of less than ~0.5 s** and **inserts no keyframe** for longer dropouts. So FreeMoCap's answer is: short dropouts → smooth interpolation, long dropouts → leave a hole, let the rig's pose-rest-on-the-armature behavior take over.

That's basically a **re-acquisition lerp** with a hard cutoff. Its lesson for us: don't try to predict the missing data, but DO smooth across the discontinuity when tracking returns.

### SteamVR / OpenXR controller tracking

When a Vive/Index controller leaves the lighthouse coverage volume, the runtime emits a `XR_TRACKING_LOST` event and then continues to emit pose samples flagged with `XR_SPACE_LOCATION_POSITION_VALID_BIT = 0`. Game code reads the bit, switches to a **damping mode** that lets the controller's last-known velocity carry it forward for a few frames before clamping to a "lost" rest pose (commonly: arm-by-side or floating in front of the headset). Re-acquisition triggers a snap-back, often spread over ~100 ms with an ease-in curve to hide the pop.

The pattern: **explicit liveness flag** on every frame, **inertial coast** through brief outages, **interpolated re-snap** on recovery. This is the model that maps cleanly onto our chain physics.

### Vicon / OptiTrack live-streaming

Optical mocap loses markers all the time (occlusion behind the actor's body, behind a prop, at frame edges). Their SDKs emit a per-marker `Quality` float [0..1]. Blender plugins (e.g., Mocap Live Link) commonly:

1. Below ~0.3, skip the write entirely (let the rig sag under whatever passive constraints exist).
2. Above ~0.5, write the position.
3. Between ~0.3 and ~0.5, lerp toward the last good position with a damping factor — **drift toward the new value over a few frames**, don't snap.

Same story: confidence is a first-class input to the kinematic blend, not a binary.

### Wiggle Bones (David's mental model)

Shane Addy's Wiggle Bones treats every bone as either **rigger-driven** (read transform from armature) or **physics-driven** (Verlet integration). There's no concept of "transitioning between modes." Each bone is one or the other for the lifetime of the rig.

But Wiggle Bones never had an external data input — it was always computing from rigger intent. We need a new state Wiggle doesn't have: **"the input is currently silent."** The natural extension is *the silence is just a third mode the Verlet solver handles differently.*

### Conclusion of the survey

There is a **standard pattern** every tracking-driven physics system converges on:

1. **An explicit liveness signal** propagated alongside the data — not derivable from the data itself.
2. **Three modes**, not two: *tracked*, *coasting / re-acquiring*, *fully released*.
3. **Smooth handoffs** at every mode boundary — a few frames of lerp/ease, not a frame-perfect snap.
4. **Physics is the floor.** When the data is gone, the rig falls back to whatever its passive simulation says — whether that's "dangle under gravity" (us), "arm by side" (SteamVR), or "no keyframe" (FreeMoCap).

PPParty's implementation should adopt all four. The remainder of this doc translates them into PPParty's specific architecture.

---

## The Three-Mode Model

Adopting the survey's standard, the fingertip chain has three operating modes per side:

| Mode | Trigger | Tip behavior | Chain solver |
|---|---|---|---|
| **TRACKED** | MediaPipe hand presence > threshold this frame | Tip pinned to MediaPipe landmark world position | Two-sided Verlet: anchor at palm, anchor at tracked tip, mid segment relaxes between them with goal-pull holding rest curve |
| **RELEASED** | No hand presence for > N frames (the dropout case) | Tip is a free Verlet point — no external anchor | One-sided Verlet: anchor at palm only, tip falls under gravity + chain constraints, settles into a dangle |
| **REACQUIRING** | Hand presence returns after a RELEASED period | Tip lerps from RELEASED-mode physics position toward incoming tracked position over K frames | One-sided → two-sided crossfade. Chain solver runs in two-sided mode but the "tracked tip" socket itself is the lerp output, not the raw MediaPipe socket |

**Mode boundaries are timer-driven, not threshold-driven, in this design.** A boolean "is the hand in frame right now" flips every time MP loses one frame, which would cause the chain to flicker between TRACKED and RELEASED dozens of times during normal flicker-prone tracking. The receiver smooths this with two timers:

- **Dropout timer** (~150–250 ms): how long without a packet before flipping TRACKED → RELEASED. Hides single-frame MP dropouts.
- **Reacquisition lerp** (~120–200 ms): how long after recovery before declaring full TRACKED again. Hides the snap.

Both are tunable. Starting values come from the SteamVR pattern (~100 ms ease) and FreeMoCap's interpolation window (~500 ms hold), modulated by our 30 FPS target → 5–8 frames is the natural unit.

---

## What the Sim Zone Sees: Two New Per-Side Inputs

The chain solver lives inside the GN sim zone. It cannot read Python-side state directly. The receiver needs to push two new pieces of information, per hand, per frame:

| Socket name | Type | Range | Meaning |
|---|---|---|---|
| `Hand L Live` / `Hand R Live` | Float | 0.0–1.0 | Liveness factor. 1.0 = fully tracked, 0.0 = fully released, in-between = currently transitioning. The receiver computes this from the dropout/reacq timers. |
| `bt_thumb_l` / `bt_thumb_r` / `bt_index_l` / `bt_index_r` | Vector | world | (Existing.) Tracked tip positions. **Receiver-side change:** when in REACQUIRING, write the lerp-interpolated value, not the raw MediaPipe value. Sim-zone-side reads the smoothed socket directly. |

That's it. One new Float socket per hand. Two total. The chain solver reads Live and uses it as the blend factor between two-sided Verlet output and one-sided Verlet output.

**Why a single Float and not separate booleans + lerp factor?** Cody's `gp_sim_influence` already taught us that "physics participation" is a float, not a bool — exactly so the rest pose can bleed through fractionally. Same shape here. A monotonic Live in [0..1] also lets us extend later (e.g., MediaPipe `presence_score` → Live directly, smoothed) without changing the GN graph.

**Why does the receiver compute Live, not the GN graph?** Two reasons:

1. The receiver is the only component that has a clock. GN sim zones get `Delta Time` from Blender's frame clock, which is fine for time integration but useless for "how long since the last packet" — the sim zone doesn't know what a packet is.
2. The receiver already manages `self._pending` and `self._last_written` ([osc_receiver.py:355-481](SOFTWARE/PPPARTY/core/osc_receiver.py:355)). Adding per-hand timestamps fits the existing ownership boundary. The sim zone reads a value; it doesn't reason about freshness.

---

## Chain Solver Behavior in Each Mode

Translating the three modes into concrete operations on the existing 48 Phase-2 state items.

### TRACKED mode (Live = 1.0)

**This is what `NATIVE_PHYSICS_DESIGN.md` already specifies.** No change.

- `pos_fingerA_l_seg0` (mid segment, base→tip): driven by `PP_ChainVerletSegment` with parent = palm SW corner, goal = palm-relative rest, **and an additional "tip pull" term** holding it on the line between palm and tracked tip.
- `pos_fingerA_l_seg1` (tip): set to tracked tip position. Bypasses sim. (Or: light Verlet smoothing for a frame of lag, applied AFTER the tracked write — TBD in design phase, see open question 3.)

The chain is one-step-ahead of the tracked tip and pulls the mid segment to lag behind the palm motion (the Goo-style velocity-scaled stiffness term). When David moves his hand, the fingertip is pinned to where his real fingertip is, and the mid joint trails through the motion arc. This is the marquee Goo behavior.

### RELEASED mode (Live = 0.0)

**The new case.** The chain becomes a free-falling Verlet rope anchored only at the palm.

- `pos_fingerA_l_seg0` and `pos_fingerA_l_seg1`: driven by `PP_ChainVerletSegment` with parent = palm anchor (seg 0) or seg 0 (seg 1), goal = palm-relative rest curl, gravity = `Chain Gravity × dt²`.
- The **tip pull term is zeroed** — there is no tracked tip to pull toward.
- The **goal pull term remains** — the rest pose holds the finger in a marionette-natural curl. Without the goal pull, the chain would fall straight down under gravity, producing 8 spaghetti strands hanging from each puppet's wrist. With it, the fingers settle into a soft curl that reads as a relaxed hand.
- **Velocity-scaled stiffness still applies.** When the palm whips around (because David's body is still moving), the released fingers trail behind with inertia. This is exactly the "hand drops out → marionette flop" that David asked for as the fix's success criterion.

This is a **one-sided pinned Verlet chain** — the textbook rope sim from Müller's PBD paper. Stable. Well understood.

### REACQUIRING mode (0 < Live < 1)

**The crossfade.** Both modes' outputs are computed and blended.

- The Verlet solver runs in TRACKED mode (two-sided pin), but the tracked tip socket `bt_thumb_l` is **already smoothed** by the receiver. On the first frame after recovery, the receiver lerps from the held-released-position toward the new MediaPipe landmark, ramping `Live` 0→1 over K frames.
- Result: from the chain solver's perspective, the tracked tip "drifts in" from where it was hanging in space toward where the real fingertip is. The chain follows naturally, no pop.

**Crucial detail:** the *receiver* smooths the tracked-position socket during REACQUIRING. The *chain solver* doesn't blend two physics outputs; it just runs in two-sided mode against a smoothed input. This keeps the GN graph simple — one mode of operation, just with more or less constraint.

The Live float is then used by the chain solver only to **gate the tip-pull term's strength**, not to switch between two solvers:

```
tip_pull_strength_effective = tip_pull_strength * Live
```

When `Live = 0`, no tip pull → released. When `Live = 1`, full tip pull → tracked. In between, the mid segment partially pulls toward the lerped tip.

This is exactly the `gp_sim_influence`/`Sim Influence` knob from Cody's preset model, repurposed per-hand-per-frame. The pattern was already in the algorithm; we're just driving it dynamically instead of statically.

---

## Velocity Seeding at Mode Transitions

The most fragile part of any tracking-physics system is the moment a constraint changes. Two scenarios need explicit handling:

### TRACKED → RELEASED

The tip socket has been writing tracked positions. The chain's `prev` state items have been carrying Verlet-driven previous-frame positions. When the dropout timer fires and Live ramps 1→0, the tip pull turns off. The chain has whatever velocity it had a moment ago — **and that's correct.** Verlet's velocity-from-(pos − prev) naturally inherits the motion the tracked tip was imparting. The chain doesn't need a velocity injection; the existing prev values already encode it.

The only thing to verify: when the tip-pull term is zeroed, the chain doesn't develop a sudden discontinuity in `pos − prev`. As long as the *pull strength* is what changes (not the tip target), the position change is continuous. ✓

### RELEASED → REACQUIRING

The tip has been free-Verlet-falling. Suddenly a tracked socket has a value again, often far from where the chain's tip currently is (because David's hand has moved during the dropout). If we pin the tip to the new tracked value in one frame, the chain snaps — and that snap propagates through Verlet as a high velocity spike, potentially with overshoot.

**Solution (already covered above):** the receiver lerps the tracked socket itself. The chain solver sees a slowly-drifting target. Verlet handles slowly-drifting targets gracefully — that's what it was designed for.

**Edge case:** if the dropout was very short (sub-150 ms), Live may not have reached 0 before the recovery. In that case the receiver should ease back to 1.0 along the same curve, with the tracked socket already at the live value. No popping because nothing was un-pinned long enough to drift apart.

---

## Specific Edits to the Existing Design

The 14-step plan in `NATIVE_PHYSICS_DESIGN.md §Implementation Plan` stands. This research adds three small deltas, all in steps 9 and 10:

### Delta 1 — Receiver: per-hand presence timer

**Location:** [`PPPARTY/core/osc_receiver.py`](SOFTWARE/PPPARTY/core/osc_receiver.py), `TrackingReceiver` class.

**New per-instance state** (added to `__init__`, cleared in `stop()` per the existing pattern from `self._last_written` / `self._dep_graph_dirty`):

```
self._hand_last_seen = {'l': 0.0, 'r': 0.0}   # monotonic clock, seconds
self._hand_live = {'l': 0.0, 'r': 0.0}        # current Live float [0..1]
self._hand_held_pos = {                        # frozen RELEASED-mode tip targets
    'bt_thumb_l': None, 'bt_index_l': None,
    'bt_thumb_r': None, 'bt_index_r': None,
}
```

**On every packet**: when a `bt_thumb_l` (etc.) entry arrives in `_pending`, update `self._hand_last_seen['l'] = time.monotonic()`. On every push tick (already running at 30 FPS), compute target Live:

- `dt_since_seen = now - self._hand_last_seen[side]`
- `target_live = 1.0 if dt_since_seen < DROPOUT_HOLD_S else 0.0`
- `self._hand_live[side] += clamp(target_live - self._hand_live[side], -dt/REACQ_TAU_S, dt/DROPOUT_TAU_S)` *(asymmetric ramp: drop slow, recover fast — feels less jittery)*

**On socket write**: if Live < 1.0 and the socket is a tracked-tip socket, write a lerped value:
- `held = self._hand_held_pos[key]` (last fully-tracked position, captured at TRACKED → REACQUIRING boundary)
- `lerped = lerp(held, raw_mp_value, self._hand_live[side])`
- Push `lerped` to the modifier socket, plus push `self._hand_live[side]` to the new `Hand <Side> Live` Float socket.

Approximate size: ~40 lines split across `__init__`, `stop()`, and the push tick. Adds two Float modifier writes per frame. No change to packet format, no change to sender — sender continues to omit the section on dropout, receiver infers via timer. **Same outcome as Option B in the handoff, but the receiver does the inference instead of the sender.** Sender stays simple.

### Delta 2 — Modifier interface: 2 new Float sockets

`Hand L Live`, `Hand R Live` (both Float, default 1.0). Added to the Group Input alongside the existing 6 Vector hand-tracking sockets. Total interface socket count grows by 2 (out of the 21 already projected by the design doc).

### Delta 3 — Chain solver: gate the tip-pull term by Live

In `PP_ChainVerletSegment` (the new sub-group from `NATIVE_PHYSICS_DESIGN §Reusable GN Sub-Groups`), add a new optional input `Tip Pull Live` (Float, default 1.0). Multiply the tip-pull contribution by this float before adding to the integrate step:

```
# (existing math from design doc)
tip_pull = (tracked_tip - Pos) * Tip Pull Strength * Tip Pull Live
```

For untracked chains (fingerC, fingerD), `Tip Pull Live` is hardcoded to 0.0 (or the term is skipped via Switch — TBD in design phase). For tracked chains (fingerA, fingerB), `Tip Pull Live` is wired to `Hand <side> Live`.

That's the entire physics-side change. The Verlet rope sim, the goal-pull rest-pose memory, the velocity-scaled stiffness, the gravity term, the chain-constraint relaxation — none of those care which mode we're in. They run identically. Only one term's strength is dynamic.

---

## Failure-Mode Smoke-Test Matrix

Concrete behaviors to verify when the dropout fix lands. Each row is a separate Blender session test, recorded if possible.

| # | Setup | Action | Pass criterion |
|---|---|---|---|
| 1 | Hand in frame, still | (none) | Fingers hold rest pose, no jitter |
| 2 | Hand in frame, slow translation | Move hand sideways 30 cm over 2 s | Tip follows hand; mid joint trails ~half a frame; no overshoot when stopped |
| 3 | Hand in frame, fast translation | Whip hand left → right in 0.3 s | Tip stays pinned to real position; mid joint lags then settles in <0.5 s |
| 4 | Hand exits frame, then idle | Drop hand below frame | Within ~200 ms (DROPOUT_HOLD), fingers ease into a soft dangle. **No teleport.** Palm continues to follow body motion. |
| 5 | Hand exits frame, body moving | Drop hand, walk torso left/right | Fingers swing freely with palm motion — visible inertia, settles when palm settles. **This is the marionette flop.** |
| 6 | Hand re-enters frame | Raise hand back into frame after >1 s gap | Tip snaps to new tracked position without overshooting. The snap is invisible (lerped over ~150 ms). |
| 7 | Single-frame MP dropout | Briefly occlude hand for ~30 ms | No visible mode change; tracking continues smoothly. (DROPOUT_HOLD swallows it.) |
| 8 | Both hands lost simultaneously | Drop both hands together | Both sides flop independently; no shared state corruption |
| 9 | Floor collision (out of scope V1) | Hand below puppet's feet | Fingers may pass through floor — collision is Phase 3 work, not V1 |
| 10 | Frame-rate dip from 30 → 15 FPS | Stress the viewport | Sim still settles correctly; Verlet damping should be FPS-independent (already a known property of the algorithm with proper `dt²` gravity scaling) |

Tests 4, 5, 6, 7 are the new ones this fix is for. Tests 1, 2, 3 are regression checks that the TRACKED-mode behavior is unaffected.

---

## Open Questions (for the Design-Doc Phase, not now)

1. **DROPOUT_HOLD_S exact value.** SteamVR uses ~100 ms. FreeMoCap uses ~500 ms. MediaPipe at 30 FPS gives one frame every 33 ms; a 150 ms hold = 4–5 frames swallowed. Starting hypothesis: 200 ms. Verify in tuning pass.
2. **Tip Verlet smoothing in TRACKED mode.** The current alpha.50 wires tracked tip *directly* to seg1 — bypasses Verlet entirely. Should the tip itself run a one-segment Verlet to absorb tracker jitter? Pro: smoother result. Con: another `Tip Pull Live` modulation point; small lag in the visible tip position. Worth a Python-prototype A/B test before deciding.
3. **Asymmetric vs symmetric Live ramp.** Drop slow (200 ms), recover fast (80 ms) feels right — sudden disappearances should be cushioned, sudden returns should snap into place. But "fast recover" might re-introduce snapping. Tunable, default to asymmetric.
4. **Per-finger Live, or per-hand Live?** Currently MP gives presence per-hand only. Per-finger would be possible if we use HandLandmarker landmark visibility (each landmark has its own confidence). Per-hand is simpler and matches MP's native model. **Recommend per-hand for V1**; revisit only if students complain that one finger drops while the others stay live (unlikely with classroom webcam).
5. **What if `bt_wrist_*` is ALSO frozen?** The palm uses `hand_l/r_pos` which lerps Verlet against tracked. The `bt_wrist_*` socket has the same dropout problem as the tip sockets. Currently the palm position relaxes correctly because of the lerp — but the tracked component is still feeding stale data. Not breaking anything visible, but worth lerping `bt_wrist_*` through the same Live-factor for consistency. Add to the receiver delta.
6. **Goo wind term as ambient idle motion?** Cody's wind oscillator is skipped in V1. But for the RELEASED state — when fingers are dangling — a tiny ambient wind would make them feel less inert. Worth revisiting only after the basic flop is in. **V1.1, not V1.**

---

## Non-Goals (this doc)

- Re-litigating the chain algorithm — see `GOO_PHYSICS_RESEARCH.md`.
- Re-litigating the build plan — see `NATIVE_PHYSICS_DESIGN.md`.
- Palm-corner jiggle physics. Jiggle bones don't have a tracked-input mode in our V1 design (palm corners always passively jiggle off the palm plate). No transition problem to research.
- Body-tracking dropout. The body chain (chest/hips/shoulders/Verlet endpoints) already has a working confidence-blend via `arm_l/r_factor` × visibility in `body_parts.py`. That pattern works because pose landmarks have per-landmark visibility scores; hand landmarks at the moment ship per-hand presence. The body case is not the same shape as the hand case and doesn't need this redesign.
- Wind, collision, finger-finger contact, palm-finger collision. All deferred per existing design.
- Sender-side changes. Sender continues to omit hand sections on dropout. All freshness logic lives in the receiver.

---

## Insertion Point in the 14-Step Plan

The deltas above slot into the existing `NATIVE_PHYSICS_DESIGN §Implementation Plan` like this:

- Step 8 (sender extension): **unchanged** — Holistic landmarker, 21 landmarks per hand sent, etc.
- Step 9 (receiver extension): **add the per-hand presence timer + Live socket writes**. Same step, ~40 more lines.
- Step 10 (chain physics wiring): **add `Tip Pull Live` input to `PP_ChainVerletSegment` and gate the tip-pull term**. No other change. Untracked chains hardcode `Tip Pull Live = 0`; tracked chains wire it to `Hand <side> Live`.
- Steps 11–14: **unchanged.**

Step 4 (Python prototype) gets one new test: simulate a 4-frame TRACKED → RELEASED transition with the Live ramp, plot positions, verify no oscillation or pop. Easy add.

The 21-socket interface count from `NATIVE_PHYSICS_DESIGN §New Group Input Sockets` becomes **23** with the two Live floats. The 48-state-item count is unchanged — Live is per-frame ephemeral, not per-frame integrated.

---

## What This Means for the Next Session

This research doc is the **vegetables before the fun**. The actual code is:

1. ~40 receiver lines for the timer + lerp + Live writes.
2. ~5 GN nodes added to the chain sim sub-group for the Live gate.
3. 2 new modifier interface sockets.

The interesting work — the chain physics itself, the rest-pose curl, the velocity-scaled stiffness, the goal pull — is the same work `NATIVE_PHYSICS_DESIGN.md` already specified. This research just makes sure that work doesn't trip over the dropout seam when it lands.

Per `feedback_eat_vegetables_before_fun`, the right next move is **not** to start coding the chain. The right next move is:

1. Write a thin **design-delta doc** (`NATIVE_PHYSICS_DESIGN_DELTA_DROPOUT.md` or fold into the existing design doc as an addendum) that translates the three deltas above into concrete diffs against the existing 14-step plan. ~50 lines.
2. Land step 10's chain wiring with the Live gate already designed in — one commit.
3. Land the receiver delta — one commit.
4. Smoke-test the matrix above.

The dropout fix and the chain physics ship together as alpha.51 (or .52 if it splits). They are not separable — a half-finished chain physics with the old `_with_fallback` would still freeze; a Live-gated `_with_fallback` without the chain physics would just produce a static rest-pose dangle (= Option A from the handoff, the bridge David rejected).

---

## References

- **Existing PPParty docs:**
  - `PPPARTY/GOO_PHYSICS_RESEARCH.md` — algorithm + presets
  - `PPPARTY/NATIVE_PHYSICS_DESIGN.md` — architecture + 14-step plan
  - `PPPARTY/HAND_TRACKING_DESIGN.md` — Option C tracking topology
  - `SOFTWARE/HANDOFF.md` §5 — the three options that triggered this doc
  - `SOFTWARE/CURVATURE_SEAM_RESEARCH.md` — the "research → design → code" template this doc mirrors
- **External:**
  - Müller, M., Heidelberger, B., Hennix, M., Ratcliff, J. (2007). *Position Based Dynamics.* The Verlet-with-distance-constraints sim that underlies both the chain and the body physics.
  - MediaPipe Tasks API docs, HandLandmarker section (Apr 2026 build) — `presence_score` and `handedness_score` fields.
  - SteamVR / OpenXR `XR_TRACKING_LOST` event documentation — the SteamVR pattern for tracking-lost handoffs.
  - FreeMoCap pipeline (`R&D/freemocap-main/`, AGPLv3) — NaN-interpolation pattern for offline mocap.
  - Vicon Tracker SDK / OptiTrack Motive Streaming SDK — per-marker quality threshold patterns.
  - Shane Addy's *Wiggle Bones* — David's mental model for bone secondary motion (per memory `user_wiggle_bones_mental_model`).
- **Code locations referenced:**
  - [PPPARTY/operators/marionette/physics.py:1380-1400](SOFTWARE/PPPARTY/operators/marionette/physics.py:1380) — Phase 2 state items + passthrough wiring.
  - [PPPARTY/operators/marionette/hands.py:330-366](SOFTWARE/PPPARTY/operators/marionette/hands.py:330) — `_with_fallback` (the alpha.50 wiring; the function that needs Live-gating).
  - [PPPARTY/operators/marionette/hands.py:598-673](SOFTWARE/PPPARTY/operators/marionette/hands.py:598) — `_add_finger_chain` (where `Tip Pull Live` will plug in).
  - [PPPARTY/core/osc_receiver.py:218-239](SOFTWARE/PPPARTY/core/osc_receiver.py:218) — sender's "missing means absent" protocol (the design point this research confirms can stay; receiver does the inference).
  - [PPPARTY/core/osc_receiver.py:355-481](SOFTWARE/PPPARTY/core/osc_receiver.py:355) — `_pending` / `_last_written` state ownership (where the new timers + held positions slot in).

End of research doc.
