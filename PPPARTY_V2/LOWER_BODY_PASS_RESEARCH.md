# Lower-Body Pass — Research Scoping Note

**Status:** Scoping only, written 2026-05-01 in response to David's framing during the v2.0.2 review. Captures the question and surfaces the open questions. Does NOT recommend candidate solutions yet — needs more discussion. Future research direction; NOT on the v2.0.2 critical path.

**Cross-doc:** sits alongside `WORLD_SPACE_ANCHORING_RESEARCH.md` (which assumes a single-pass body recording) — together they define the V2.x lower-body roadmap.

---

## The Question (David's framing, 2026-05-01)

> "we need to be smart about is making sure that the bottom half, the legs, and the upper half the body are are capable of being recorded separately, and that's gonna be hard to figure out because it's easy to record the top half. But how do you record the top half and then the bottom half if there's floor restrictions?"

Plain English: V2's deployable unit is a laptop on a desk. Kids sit at desks. At desk-distance camera framing, **legs are cropped out of the frame.** MP can't track what it can't see → no leg data → puppet's lower body falls back to rest pose / occlusion behavior.

If kids stand up to put their legs in frame, the camera framing changes (kid is now further away) and **upper-body fidelity degrades** — face landmarks at greater distance have lower pixel density, hand landmarks too. The two halves of the body have fundamentally incompatible camera framing requirements at consumer-laptop scale.

This is the same problem we already solved for face vs body via the **two-pass architecture** (Pass 1 = body+hands, Pass 2 = face). The proposed solution: extend the pattern. Add a third pass. Pass 1A = upper body + hands; Pass 1B = lower body / legs. Record each in the framing that suits it; combine in the bake.

---

## What This Is, And What It Isn't

**This is:** an extension of the existing layered-pass recording pattern. Each pass owns a disjoint set of bones; NLA strips combine them into one performance. Same architecture, more passes.

**This is NOT:** real-time multi-camera body tracking, ML-based mocap from recorded video (Wonder Dynamics class), or anything requiring training data. We stay within MediaPipe single-frame inference. The puppet/marionette restriction discipline from V0/V1 is preserved: simple inputs, simple recording, simple combine.

**Why this restriction-respecting framing matters:** the alternative (Wonder Dynamics-class ML pipeline) requires recorded video, training compute, per-deployment retraining. CACHE/HIHO deployment can't carry that. Layered passes work on the existing infrastructure with no new dependencies.

---

## The Pedagogy Frame

David's V0/V1 lesson: **restrictions enable creativity.** Kid Pix's tool reduction, Bunraku threshold toggles, Henson's "maximum expression from minimum controls." V2's two-pass body+face split already embodies this — kid records body (focusing on gesture), then face (focusing on expression), then watches them combined. Each pass has its own discipline.

A lower-body pass extends the pattern naturally: **kid records walking/legs as its own discipline.** Stand up, do the leg performance (e.g., character walks in place, paces, stomps), sit down. Combine with the upper-body pass already recorded. The narrative arc gains a "physicality" beat that desk-bound recording can't capture.

This isn't a workaround for a technical limitation — it's a pedagogical opportunity. Recording legs as a SEPARATE creative act (rather than incidentally as part of full-body) makes the kid think about how legs contribute to character.

---

## Open Questions (the part that needs design work)

### 1. Workflow / recording UX

- Does the kid record passes sequentially in one session, or across sessions?
- Does each pass have its own button (Body / Face / Legs) or is there a unified "Record Pass N" interface?
- How does the kid signal "this take is upper body" vs "this take is legs"? Manual selection, or auto-detect from MP's visibility scores?
- What's the framing instruction for each pass? (Maybe a viewport overlay: "Move back until you see your full body in frame.")

### 2. NLA strip ownership

V2 already disjoint-owns bones across passes:
- Pass 1 (body): owns 55 bones (everything except head)
- Pass 2 (face): owns head only

Adding Pass 1B would split Pass 1's 55:
- Pass 1A (upper body): owns chest, shoulders, arms, hands (~38 bones)
- Pass 1B (lower body): owns pelvis (rotation), legs, feet (~10 bones)
- Pass 2 (face): unchanged

Does pelvis belong to upper or lower? Probably lower (because pelvis tilt couples with leg motion). Does chest? Upper. The bone-class boundary needs clean definition.

### 3. Frame-restriction interactions

Constant-stance (per `WORLD_SPACE_ANCHORING_RESEARCH.md` recommendation for v2.0.2) means pelvis stays at world origin. Lower-body pass records pelvis ROTATION (tilt) but not position. That's compatible.

If the kid stands during the lower-body pass, MP gives different `pose_world_landmarks` (different baseline scale, possibly different perspective foreshortening). Does the recorded lower-body pass need any normalization to match the upper-body pass's expectations?

### 4. The temporal alignment problem

If Pass 1A is recorded with the kid sitting, and Pass 1B is recorded later with the kid standing, the takes are likely DIFFERENT LENGTHS. How does the bake combine them?

Options:
- Force same length (kid records both to same beat / metronome)
- NLA strip per pass, looped or held independently — kid's "1B leg loop" plays under "1A body performance"
- Trim/pad either pass to the other's length

### 5. The "what about hands during the leg pass" question

When kid is standing for Pass 1B, MP CAN see hands (probably). Does Pass 1B drive hand bones too? Probably no — Pass 1A owns hands. But MP doesn't know our pass conventions. The receiver needs to ignore hand data during a Pass 1B record.

### 6. Failure mode — partial visibility during a pass

If kid records "Pass 1A upper body" and accidentally has legs partially in frame (occluded chair edge cropping at thighs), does MP try to track legs? Currently V2 always uses all 33 landmarks. A pass-aware receiver might mask landmarks per pass.

### 7. Calibration / per-pass baseline

Pass 1B's leg landmarks need a baseline calibration (rest stance) to compute meaningful joint angles. Same way Pass 1A already calibrates running-min spine length on shoulder shrug. Does Pass 1B need its own session-start calibration step?

---

## Why This Is V2.x, Not v2.0.x

The current V2 deliverable is "puppet performs in place from a desk." Lower-body pass requires:
- New UI surfaces (record buttons per pass, framing instructions)
- Receiver pass-aware logic (mask landmarks per pass)
- Recorder pass-aware logic (write to different NLA strips)
- Workflow design (sequential vs parallel sessions)
- Pedagogical guidance for teachers

That's an architectural arc, not a 30-line patch. Probably 2-4 ship cycles after the current world-anchoring + rotation-noise work lands.

**When to revisit:** after v2.0.2 ships AND classroom testing happens, if teachers/kids consistently ask for "puppet that walks." The strongest signal would be unprompted requests for lower-body fidelity from kids themselves during classroom testing.

---

## What's NOT In Scope For This Direction

- **Multi-camera body capture.** That's the parked dual-cam work — different question (per-frame noise reduction via fusion). Lower-body-pass is single-camera, two-recording, layered.
- **Real-time ML upscaling of partial body data.** Wonder-Dynamics class. Out of CACHE/HIHO deployment scope.
- **Body proportion calibration to match the kid's body.** Separate research direction (see Phase 7 backlog).
- **Locomotion / IK / physics for legs.** v2.0.2 ships ground-plane clamp; full IK is V2.x territory; lower-body-pass is orthogonal to both.

---

## Cross-References

- **Existing pattern this extends:** V2's two-pass architecture (Pass 1 body + Pass 2 face). See V2 HANDOFF "Architectural state" item #2-3 and `core/recorder.py` `_BODY_DRIVEN_BONES` for current pass ownership.
- **Coupled doc:** [`WORLD_SPACE_ANCHORING_RESEARCH.md`](WORLD_SPACE_ANCHORING_RESEARCH.md) — assumes single-pass body recording. Future iteration of THIS doc would update to multi-pass.
- **Pedagogy framing:** `STUDIO/DOCUMENTATION/VISION_2026-04-17.md` (HIHO/CACHE pedagogy), `feedback_three_smoothing_physics_surfaces` (different problems need different tools), `project_ppparty_deliverable_is_baked_animation` (V2 is bake-pipeline-first, which makes layered passes natural).
- **Restriction-discipline lineage:** Green Room V0.7.0 (template-based; constraints enable creativity), V1 phone-era PPParty (face-tracking-only marionette; minimal inputs, maximum expression), V2's two-pass split.

---

## David — No Decision Needed Right Now

This doc captures the question. It explicitly does NOT recommend an implementation path because the open questions need more conversation before that's responsible.

When we revisit (probably after v2.0.2 ships and classroom test data starts coming in), the right next move is a workflow design session — start with question #1 (recording UX) since that drives the rest. Then a proper research+design+code arc.

For now: noted, parked, ready to pick up.
