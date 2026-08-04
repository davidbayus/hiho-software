# Native Physics Design — Dropout Delta

**Date:** 2026-04-25
**Purpose:** Translate the three deltas from `FINGERTIP_PHYSICS_RESEARCH.md` into concrete diffs against `NATIVE_PHYSICS_DESIGN.md`'s 14-step plan. Pre-code. The chain physics itself, the preset values, the sub-group internals, the assembly order — all unchanged from the parent doc. This file only specifies what gets layered on so that the chain handles MediaPipe dropouts gracefully when it lands.
**Status:** Pre-code. Pattern: research → design-delta → prototype → code, per `feedback_research_doc_first_pattern`.
**Authors:** David Bayus + Claude (Opus 4.7).

---

## Relationship to the Existing Docs

```
GOO_PHYSICS_RESEARCH.md       ← algorithm, 9 chain params, preset value tables
        ↓
NATIVE_PHYSICS_DESIGN.md      ← 14-step plan, 21 sockets, 48 state items, 2 sub-groups
        ↓
FINGERTIP_PHYSICS_RESEARCH.md ← the dropout seam: three-mode model, prior art
        ↓
THIS DOC                      ← concrete diffs against the 14-step plan
        ↓
(next) Python prototype (Step 2 of parent plan, +2 new test cases)
        ↓
(then) code, one commit per substep
```

This doc does **not** restate the chain algorithm, the sub-group node graphs, or the 14-step ordering. Read the parent doc for those.

---

## Resolved Open Question (research-doc OQ #2)

The research doc left one design-phase TBD: **does seg1 (the tip segment) bypass Verlet and pin directly to the tracked socket, or run through Verlet with a Live-gated tip pull like seg0 does?**

**Decision: tip segment runs through Verlet (Shape B).** Same `PP_ChainVerletSegment` instance as seg0, with a Live-gated tip-pull term pulling toward `tracked_tip`. No GN Switch keyed on Live, no special-case branch.

**Why:**
1. The research doc's central claim — "the chain solver has a single mode of operation; only one term's strength is dynamic" — only holds if seg1 doesn't have a separate code path.
2. Cody's `gp_sim_influence` already taught us that a single float gating one term is the right shape; a Switch-driven branch is the shape of an ad-hoc hack.
3. Tracker jitter absorption (the upside of running Verlet on the tip) is a free win at chain-physics frame rates. The downside (small visible lag on the tip pixel) is real but uniform with what the mid joint already does — visually consistent rather than seg0-Verlet-but-seg1-snappy.

**Fallback path** (if the Step 2 prototype shows the tip lag is unacceptable): keep Shape B as the structure, but raise `Tip Pull Strength` for seg1 specifically so its convergence per-frame is closer to "pinned." That's a parameter tuning change, not a code-path change. Shape A (a hard Switch keyed on Live ≥ threshold) is only re-introduced if the tuning pass fails.

---

## Delta 1 — Receiver: per-hand presence timer + lerped tracked write

**Location:** [`PPPARTY/core/osc_receiver.py`](PPPARTY/core/osc_receiver.py).

**New per-instance state in `__init__` (after line ~390, alongside `self._dep_graph_dirty`):**

```python
self._hand_last_seen = {'l': 0.0, 'r': 0.0}      # time.monotonic() of last
                                                  # frame that brought a hand
                                                  # section in _pending
self._hand_live      = {'l': 1.0, 'r': 1.0}      # Live float [0..1] per side;
                                                  # written to "Hand <S> Live"
                                                  # socket each tick. Default
                                                  # 1.0 so a freshly-built rig
                                                  # before tracking starts sees
                                                  # full tip-pull and rests on
                                                  # the constant rest-pose
                                                  # fallback in hands.py.
self._hand_held_pos  = {                          # last fully-tracked position
    'bt_thumb_l': None, 'bt_index_l': None,       # per tracked-tip socket;
    'bt_thumb_r': None, 'bt_index_r': None,       # captured at the moment Live
    'bt_wrist_l': None, 'bt_wrist_r': None,       # leaves 1.0 (TRACKED →
}                                                 # REACQUIRING boundary). Used
                                                  # as the lerp source on
                                                  # recovery. None means "no
                                                  # tracked value has ever been
                                                  # seen" → fall through to
                                                  # raw_mp_value.
```

**Cleared in `stop()` (after line ~482):**

```python
for d in (self._hand_last_seen, self._hand_live, self._hand_held_pos):
    for k in d:
        d[k] = (0.0 if d is self._hand_last_seen
                else (1.0 if d is self._hand_live else None))
```

**On packet ingest** (extend the `_handle_message` branch at line ~518 where `_pending['_hand_endpoints']` is set): every time the hand-endpoints section is non-empty, update `self._hand_last_seen[side]` for each side present. **Do this in the ingest path, not in `_apply_updates`,** because per-tick we only see the merged `_pending` snapshot — the last-seen timestamp wants the freshest packet arrival, not the tick boundary.

**On every push tick** (in `_apply_updates` / `_push_to_puppet`, replacing the simple write block at lines 824-859): two changes.

1. **Compute Live per side.** Constants live as module-level floats at the top of the file:
   ```python
   _DROPOUT_HOLD_S = 0.20    # 200 ms — swallows single-frame MP dropouts
   _DROPOUT_TAU_S  = 0.20    # ramp 1→0 over 200 ms once hold expires
   _REACQ_TAU_S    = 0.08    # ramp 0→1 over 80 ms on recovery (asymmetric:
                              # drop slow to cushion, recover fast to snap in)
   ```
   Each tick, per side `s`:
   ```python
   dt_since   = now - self._hand_last_seen[s]
   target     = 1.0 if dt_since < _DROPOUT_HOLD_S else 0.0
   tau        = _REACQ_TAU_S if target > self._hand_live[s] else _DROPOUT_TAU_S
   step       = dt_tick / tau
   self._hand_live[s] += max(-step, min(step, target - self._hand_live[s]))
   ```
2. **Lerp the tracked-tip socket write.** When writing `bt_thumb_<s>` / `bt_index_<s>` / `bt_wrist_<s>`:
   ```python
   live   = self._hand_live[s]
   raw    = puppet_pos                  # already MP→puppet transformed
   held   = self._hand_held_pos[name]
   if live >= 0.999:
       self._hand_held_pos[name] = list(raw)   # capture for next dropout
       out = raw
   elif held is None:
       out = raw                                # no held value yet — pass-through
   else:
       out = [held[i] + (raw[i] - held[i]) * live for i in range(3)]
   # then the existing _value_changed + mod[sid] = out write
   ```
3. **Push the Live floats themselves.** After the hand-endpoint loop, two extra writes:
   ```python
   for s in ('l', 'r'):
       sid = self._bt_socket_ids.get(f'Hand {s.upper()} Live')
       if sid:
           live = self._hand_live[s]
           if self._value_changed(f'Hand {s.upper()} Live', live, eps=1e-3):
               mod[sid] = live
               wrote_any = True
   ```

**Approximate diff size:** ~50 lines net (init + stop + tick block + 2 module constants). No new imports — `time.monotonic` already used elsewhere in the file. Sender and packet format unchanged.

**Affected lines in the parent doc's Step 9** (`Hand tracking wiring — receiver side`): the step description "Direct modifier push" stays, but the implementation now includes the timer + lerp logic above. ~40 → ~90 lines for that step.

---

## Delta 2 — Modifier interface: 2 new Float sockets

In the parent doc's **§New Group Input Sockets** table, add a new section:

### Hand liveness (2 sockets — driven by receiver)

| Socket name | Type | Default | Purpose |
|---|---|---|---|
| `Hand L Live` | Float | 1.0 | Liveness factor for left hand. 1.0 = tracked, 0.0 = released, in-between = transitioning. Receiver-computed per tick from presence timer. |
| `Hand R Live` | Float | 1.0 | Same, right hand. |

**Updated total:** new socket count goes **21 → 23** (15 physics params + 6 tracked positions + 2 liveness floats).

These are added to the Group Input alongside the existing 6 hand-tracking Vectors. No change to the existing physics params or tracked positions.

**Affected lines in the parent doc's Step 9 build:** add to the receiver's socket-id discovery — the `_bt_socket_ids` dict already auto-discovers Vector sockets starting with `bt_`; for these two Float sockets, either extend the auto-discovery to also pick up sockets named `Hand <S> Live`, or hardcode them in a small static table. **Prefer the small static table** — `Hand L Live` / `Hand R Live` is a known list of two, autodiscovery's value is for the open-ended Vector set.

---

## Delta 3 — `PP_ChainVerletSegment`: optional `Tip Pull Live` input

In the parent doc's **§Reusable GN Sub-Groups** §`PP_ChainVerletSegment`, **Inputs** list, add one entry:

| Input | Type | Default | Purpose |
|---|---|---|---|
| `Tip Pull Live` | Float | 1.0 | Multiplier on the tip-pull contribution. 1.0 = full pull toward tracked tip; 0.0 = no pull (free chain). |

**Internal graph change** — in the integrate sketch from the parent doc (the snippet just before "root falloff blend"), change:

```
# (old) — no tip pull term in the parent sketch at all; the chain is two-anchor
#         via Verlet's distance constraint pass alone

# (new) explicit tip-pull term, gated by Live
to_tip      = Tracked Tip - Pos
tip_pull    = to_tip * Tip Pull Strength * Tip Pull Live
physics_pos = Pos + vel_d + grav_vec + goal_pull + velocity_stiffness_pull + tip_pull
```

**Two new sub-group inputs total:** `Tracked Tip` (Vec3, default `(0,0,0)`) and `Tip Pull Live` (Float, default 1.0). For untracked chains (`fingerC`, `fingerD`), `Tip Pull Live = 0.0` is hardcoded at instantiation in `hands.py`, which makes the tip-pull term contribute zero regardless of `Tracked Tip`. For tracked chains (`fingerA`, `fingerB`), `Tracked Tip` is wired to the `Thumb <S> Tip` / `Middle <S> Tip` socket and `Tip Pull Live` is wired to `Hand <S> Live`.

**`Tip Pull Strength`** is a new module-level constant in `physics_presets.py`, not a Group Input socket — same status as `MIDLINE_MARGIN` etc. in `body_parts.py`. Starting value: `0.6`. Verified in the Step 2 prototype.

**Affected lines in the parent doc's Step 10** (`Wire chain physics`): one extra wiring line per tracked chain (`fingerA`, `fingerB`, both sides — 4 wires total) + the hardcoded zero on the untracked chains. ~5 GN-graph nodes added inside `PP_ChainVerletSegment`.

---

## Updated Step List (only steps that change)

Steps 1–8 in the parent doc: **unchanged.**

**Step 9 — Hand tracking wiring — receiver side.** Now includes:
- The 6 Vector socket writes (existing).
- The 2 Float Live socket writes (new, Delta 2).
- The presence timer + Live ramp (new, Delta 1).
- The held-position lerp on the 6 Vector writes during REACQUIRING (new, Delta 1).
Estimated size: ~50 lines net added to `osc_receiver.py`.

**Step 10 — Wire chain physics.** Now includes:
- `PP_ChainVerletSegment` exposes `Tracked Tip` and `Tip Pull Live` inputs (Delta 3).
- `hands.py` wires `fingerA` seg0 + seg1: `Tracked Tip = Thumb <S> Tip`, `Tip Pull Live = Hand <S> Live`.
- `hands.py` wires `fingerB` seg0 + seg1: `Tracked Tip = Middle <S> Tip`, `Tip Pull Live = Hand <S> Live`.
- `hands.py` wires `fingerC` + `fingerD` seg0 + seg1: `Tracked Tip = (0,0,0)`, `Tip Pull Live = 0.0`.

Steps 11–14 in the parent doc: **unchanged.**

---

## Updated Step 2 (Python Prototype) — two new test cases

The parent doc's Step 2 prototype validates the chain algorithm under each preset on a still + moving root. Add two cases derived from `FINGERTIP_PHYSICS_RESEARCH.md §Failure-Mode Smoke-Test Matrix` rows 4–6:

**Case 2a — Dropout transition.** Run the 4-bone chain with HAIRSIDE preset, root anchor moving in a slow horizontal arc. At t = 0.5 s, ramp `Tip Pull Live` from 1.0 → 0.0 over 200 ms (matching `_DROPOUT_TAU_S`). Plot tip and mid positions. Pass: no positional discontinuity at the ramp start; tip eases into a downward dangle within ~0.5 s of the ramp completing; no oscillation.

**Case 2b — Reacquisition transition.** Continuation of 2a. At t = 2.0 s, ramp `Tip Pull Live` from 0.0 → 1.0 over 80 ms (matching `_REACQ_TAU_S`), with `Tracked Tip` set to a position 30 cm offset from where the dangling tip currently sits. Plot. Pass: tip drifts toward `Tracked Tip` over the ramp, no overshoot, settles within ~10 frames of the ramp completing.

**Both cases use Shape B** (single Verlet code path, no GN Switch). If either case fails — specifically if 2b shows a visible snap or 2a shows oscillation in the released chain — fall back to Shape A (hard switch keyed on Live ≥ 0.5) and re-run.

These two cases are the gate before any GN node-graph code lands. If the prototype matches expectations, the GN port is mechanical translation. If it doesn't, the failure mode tells us whether to retune `Tip Pull Strength`, lengthen the ramps, or fall back to Shape A.

---

## What This Doc Does Not Change

- The 9 chain params + 6 jiggle params + their preset values (`physics_presets.py`).
- The 48 state items declared in `physics.py` lines 1380-1400.
- The chain topology (4 fingers per hand, 2 segments per finger, palm corners as separate jiggle bones).
- The build order in `assembly.py`.
- The two-sided Verlet pinning approach for tracked chains — that's the algorithm. This delta only modulates *how strong* the tip-pull term is per-frame.
- The "no wrist segment in V1" decision.
- The Studio Track Custom Hand override path.

---

## What Memory Should Capture (when alpha.51 ships)

Two project-memory candidates, written so they're self-explanatory in a future session:

1. **"Liveness signals don't live in the data"** — one-line rule. Stale-vs-silent is unrecoverable from socket values alone. Every push-protocol that drives physics needs an explicit liveness float computed by the side that has a clock (the receiver). Reason: alpha.50 dropout-freeze bug. How to apply: when designing new tracking-driven sockets, always pair them with a `<thing> Live` Float that the receiver maintains via a per-thing presence timer.

2. **"Three-mode model for tracked physics"** — TRACKED / RELEASED / REACQUIRING. The pattern from MediaPipe + SteamVR + FreeMoCap + Vicon. Reason: standard convergent solution. How to apply: any future tracked input (face-tracking shape keys, body landmarks already covered by `arm_l/r_factor`, future markerless full-body) gets the same shape — Live float + asymmetric ramp + receiver-side lerp.

Both deferred until the alpha.51 implementation passes the smoke-test matrix. Don't save speculatively.

---

## References

- `PPPARTY/FINGERTIP_PHYSICS_RESEARCH.md` — research artifact; this doc is its concrete-code translation.
- `PPPARTY/NATIVE_PHYSICS_DESIGN.md` — parent build plan; only steps 9 + 10 + the socket count change.
- `PPPARTY/GOO_PHYSICS_RESEARCH.md` — chain algorithm + preset values (unchanged).
- [`PPPARTY/core/osc_receiver.py:350-394`](PPPARTY/core/osc_receiver.py:350) — `__init__` + state declarations (Delta 1 lands here).
- [`PPPARTY/core/osc_receiver.py:450-482`](PPPARTY/core/osc_receiver.py:450) — `stop()` (Delta 1 cleanup).
- [`PPPARTY/core/osc_receiver.py:518`](PPPARTY/core/osc_receiver.py:518) — packet-ingest `_pending['_hand_endpoints']` (timestamp update site).
- [`PPPARTY/core/osc_receiver.py:824-859`](PPPARTY/core/osc_receiver.py:824) — current hand-endpoint write loop (Delta 1 lerp lands here).
- [`PPPARTY/operators/marionette/hands.py:330-366`](PPPARTY/operators/marionette/hands.py:330) — current `_with_fallback`. Once chain physics + Live gate land, this helper is no longer needed for tracked chains: Live=0 already produces "free chain" behavior, which is the correct fallback. The constant rest-pose target `_with_fallback` was switching to was always a lie; the correct fallback is physics, not a constant.
- [`PPPARTY/operators/marionette/hands.py:598-673`](PPPARTY/operators/marionette/hands.py:598) — `_add_finger_chain` — where Step 10's chain wiring (with the new `Tip Pull Live` arg) plugs in.

End of design-delta doc.
