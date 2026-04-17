# PPParty Refactor Plan — `create_marionette.py` → Curriculum

**Status:** Design doc (pre-code)
**Authors:** David Bayus + Claude (Opus 4.7)
**Created:** 2026-04-16
**Target:** PPParty V1.0.0-alpha.4

---

## Why this refactor

Two goals, one piece of work:

### 1. Performance — "runs on nothing"
217 GN nodes re-evaluate on every slider change. Slider lag is the first thing a kid notices — before color, before face tracking, before anything. "Runs on nothing" is the Scrap in a Box prime directive (e-waste laptops, ~8GB RAM, integrated GPU, offline, localhost). Splitting the file isolates subtrees so we can audit which can be cached, instanced, or lifted outside the sim zone.

### 2. Pedagogy — the code as curriculum
PPParty will pass through future CADRE student developers (months to years out, not imminent). More immediately, David reads this code and needs to navigate it himself. The refactored code doubles as an **intro-to-geonodes-and-CS course** for a specific reader — the ART102 graduate.

Both goals are served by the same split. Performance clarity and reading clarity converge.

---

## The audience

Every comment is written for a student who has completed **ART 102 (3D Modeling with Blender)** at SJSU and is curious about how Blender works under the hood and general CS concepts.

**Can assume they know:**
- Blender UI, basic modeling, what a modifier does
- Basic geometry nodes (Set Position, Combine XYZ, Math node)
- Vertex / face / normal / UV
- Python console and Text Editor inside Blender

**Cannot assume they know:**
- Classes, inheritance, decorators
- Threads, state, closures
- Linear algebra beyond "vectors are arrows"
- CS vocabulary (cache, O(1), heap, reference, mutable/immutable)

**They want to learn** why the code is structured the way it is, what "state" means, what a sim zone actually does computationally, and how Python-driven geometry differs from shader math.

### Comment style rules

1. **Name the concept.** ("This is a Minkowski sum.")
2. **Give the visual intuition first.** ("Imagine sweeping a sphere across the surface of a box — the shape you trace out is our capsule.")
3. **Then the code.** ("We do this by clamping each vertex into the inner box, then offsetting by a unit direction × radius.")
4. **Teach CS vocab as it shows up.** When we say "we cache the socket lookup," explain what caching means and why it matters here (we'd be looking up the same thing hundreds of times per frame otherwise).
5. **No jargon shortcuts.** Don't say "O(1) dict access" — say "Python dicts let us jump to the value directly, without scanning through every item."
6. **Connect to art intuition when it helps.** ("Think of a sim zone like a cloth or fluid simulation — it runs forward over time, with state carried from frame to frame.")

---

## End-state module map

Inside `PPPARTY/operators/marionette/` subpackage:

| # | File | ~Lines | Teaches |
|---|------|--------|---------|
| 1 | `capsules.py` | ~400 | **The Minkowski capsule.** The one primitive everything else uses. GN basics: modifiers, sockets, vertex fields, CombineXYZ, clamping. The novel math of PPParty lives here. |
| 2 | `materials.py` | ~200 | Material sockets + Set Material node. The socket-passthrough pattern on easy mode. |
| 3 | `blob_head.py` | ~300 | Blob puppet as a GN Group node. Group nodes, interface enumeration, auto-passthrough loop. |
| 4 | `body_parts.py` | ~700 | Hands, feet, shoulders, hips, cheeks, limb tubes. Composition — applies capsule knowledge to build anatomy. |
| 5 | `face_tracking.py` | ~300 | 18 ARKit inputs + the direct-modifier-push pattern. Why we bypass drivers in Blender 5.2. |
| 6 | `body_movement.py` | ~500 | The 7-channel face→body mapping + MediaPipe body-tracking blend. Composite motion from multiple inputs. |
| 7 | `physics.py` | ~500 | Sim zones, Verlet integration, analytical IK (law of cosines + double cross product). Hardest chapter. |
| 8 | `studio_track.py` | ~200 | Object Info Switch pattern for custom geometry. Small "advanced customization" chapter. |
| — | `assembly.py` | ~100 | Orchestrator — reads like a table of contents. Calls each module in order. |

The Blender operator class and register/unregister stay in `operators/create_marionette.py`, now thin.

---

## Reading order = learning order

Why each module comes where:

1. **`capsules.py` first** because it's the one idea to understand deeply. Everything else uses it. It's also the novel bit of PPParty — student sees where the craft is up front.
2. **`materials.py` second** because it's the easiest socket-passthrough pattern. Builds confidence with sockets before harder vector math.
3. **`blob_head.py`** introduces GN Group nodes and the auto-passthrough loop — small clever pattern they can admire.
4. **`body_parts.py`** is composition practice — apply capsule knowledge to build anatomy. Teaches naming convention = maintainability.
5. **`face_tracking.py`** is small and concrete — ARKit inputs + the 5.2 workaround. Sets up the next chapter.
6. **`body_movement.py`** — one input (headRotY) drives three outputs (torso sway + gait + bob). The "cascaded mapping" pattern.
7. **`physics.py` last of the majors** because sim zones and IK are the hardest concepts. Student earns it.
8. **`studio_track.py`** as a cherry on top — the Switch-based override pattern, standalone and simple.

---

## Execution plan

**One module per commit. Test after each. Revert if worse.**

| Step | Action | Validation |
|------|--------|------------|
| 0 | Tag current state as `v1.0.0-alpha.3-pre-refactor` (safe harbor) | — |
| 1 | Create `operators/marionette/` subpackage with empty `__init__.py` | Addon still loads |
| 2 | Extract `capsules.py` | Puppet builds identically |
| 3 | Extract `materials.py` | All 14 materials assign correctly |
| 4 | Extract `blob_head.py` | All 37 head sliders work |
| 5 | Extract `body_parts.py` | Hands/feet/shoulders build, mirrored rotations work |
| 6 | Extract `face_tracking.py` | All 18 ARKit inputs appear on modifier |
| 7 | Extract `body_movement.py` | Face→body channels still drive torso sway, gait, arm gestures |
| 8 | Extract `physics.py` | Verlet dangling, IK joints, ground collision, constraints all intact |
| 9 | Extract `studio_track.py` | Custom torso/hand/foot Object sockets functional |
| 10 | Shrink to `assembly.py` orchestrator | Puppet builds in the same order |
| 11 | Pedagogical comment pass — rewrite docstrings/comments for the ART102 reader | Reads cleanly top-to-bottom |
| 12 | Tag completion as `v1.0.0-alpha.4-refactor-complete` | — |

### Test checklist (run after every step)

- [ ] Addon loads without console errors in Blender 5.2 Alpha
- [ ] "Create Marionette" builds a rig visually identical to pre-refactor
- [ ] All N-panel sections appear (Body Movement, Physics, Proportions, Make It Yours, Materials, Head Design, Connect, Debug)
- [ ] All 37+ customization sliders respond
- [ ] MediaPipe webcam tracking drives face + body
- [ ] Phone fallback (Live Link Face) still works
- [ ] Reset Physics jumps to frame 1 correctly

**If any step breaks the demo:** revert that one commit, investigate, try again. Never stack failing changes.

---

## Performance wins the split unlocks

These are **follow-up work, not part of the initial refactor.** The split makes them local and testable — it does not perform them automatically.

- **L/R instancing.** Once `capsules.py` is isolated, building ONE capsule and instancing it for L/R pairs (hands, feet, shoulders, ears, eyes, eyebrows) becomes a local change.
- **Constant-math lift.** Nodes inside the sim zone that don't depend on simulation state can be moved OUT. Easier to spot with `physics.py` separated.
- **Lazy material resolution.** Materials assigned once at creation rather than re-linked via sockets every eval. Auditable inside `materials.py`.

Refactor first. Optimize second. Never both at once.

---

## What this refactor is NOT doing

- **Not changing behavior.** The puppet builds, moves, and tracks identically after the refactor.
- **Not adding features.** The MediaPipe alpha.3 feature set is frozen during this work.
- **Not modernizing style** beyond what clarity demands. No type-hint sweep, no linter cleanup unrelated to readability.
- **Not touching PaWrappa, QUADRE, or retired Green Room.** PPParty only.
- **Not rewriting any geonode logic.** Math stays byte-identical. Only structure moves.

---

## Open questions before execution

1. **Subpackage or flat?** Recommendation: **subpackage** (`operators/marionette/…`). Cleaner imports, visual grouping in the file tree. Alternative: flat with naming convention (`operators/marionette_capsules.py` etc.) — rejected because it clutters the `operators/` folder.

2. **When do we start?** Not today (2026-04-16). Ideally a fresh session with a clean Blender 5.2 test environment open, after David has reviewed this plan.

3. **Companion doc?** Consider adding `PPPARTY/NOTES_FOR_READERS.md` — a 1-page "how to read this codebase" pointing to the curriculum order. Can be written during step 11 (comment pass).

4. **Blender version lock.** Confirm we're refactoring against Blender 5.2 Alpha. If 5.2 goes stable mid-refactor, retest against stable before continuing.

---

## Review and update cadence

This is a living plan. Update whenever the shape changes mid-execution. Every step commit should reference this doc (`See REFACTOR_PLAN.md step N`).

After completion, this doc becomes a historical artifact — keep it in the repo as the record of how and why the split happened. Future CADRE student developers will read this before touching the code.
