# World-Space Anchoring — Research Doc (V2 Items #2 + #3)

Pre-code research per `feedback_research_doc_first_pattern`. Written 2026-05-01 against the v2.0.1 benchmark. Covers two coupled problems — hip translation and foot+floor contact — together because they're both about anchoring the puppet in world space and the design choices interact.

This doc has three layers, same shape as `HAND_ROTATION_NOISE_RESEARCH.md`:
1. **TL;DR** — what we're doing and why, in plain English
2. **The two problems + why they're coupled**
3. **Candidate solutions (4 for hip translation, 3 for foot+floor)**, then recommendation pairing

---

## TL;DR (plain English)

Right now V2's puppet floats in place. When the kid walks across the basement, the puppet's pelvis stays glued to the world origin and only the upper body wiggles. When the kid stands on the floor, the puppet's feet hang in space at whatever rest-pose height they were rigged at — they don't plant on the ground.

These are two different problems with two different fixes, but they interact: a "walking puppet" with un-planted feet would slide across the floor weird; "planted feet" without translation would have feet stuck while the body shifts. So we design them together.

For a K-12 puppet show — which is what HIHO/CACHE deployment is — we don't need Hollywood mocap fidelity. We need the puppet to feel alive AND look intentional. The simplest pairing that achieves this:

- **For hip translation:** start with **constant-stance assumption** (puppet stays planted at world origin, kid's walking is captured in upper-body lean rather than world-translation). This is what classical marionettes do — the stage is fixed, the puppet performs in place. It's pedagogically defensible AND trivially simple to ship.
- **For foot+floor contact:** add a **ground-plane clamp** on foot tail Z (push up to 0 if it dips below). Cheap to implement, eliminates the worst visible artifact (foot dipping into the floor when the kid sits down).

Together: ~20 lines of code, ships as v2.0.2, no architectural surgery. Saves the heavy lifting (IK rig, image-landmark hip estimation) for V2.x territory if/when classroom testing surfaces a real need.

---

## The Two Problems

### Problem 1 — Hip translation

**The artifact:** kid walks left-to-right across the basement floor. Puppet's pelvis stays at world origin; kid's body lean is captured in chest tilt + arm sway, but the puppet doesn't physically move.

**The root cause:** MediaPipe's `pose_world_landmarks` are **hip-centered by design** — the origin of MP's world coordinate system is the kid's mid-hip. This means MP gives us body geometry in metric units relative to the hip, but **zero information about where the hip is in the actual world.** Asking MP "where is the kid standing?" via `pose_world_landmarks` is a category error.

V2 currently anchors the pelvis at `rest_head_local` (world origin) and accepts this. The puppet's pelvis literally CANNOT translate based on the body packet's content as currently structured.

**Why this matters pedagogically:** kids performing a puppet show want their puppet to "go places." Walking across the stage is one of the most basic narrative beats in puppetry. Without translation, the puppet's narrative range collapses — every scene is "puppet at center stage."

**Why this might NOT matter as much as we think:** classical marionettes also stay roughly in one stage location. Puppeteers compensate via lean, gesture, and verbal storytelling. The puppet's expressive range comes from the body, not the position. K-12 kids have never seen V2 with translation; they won't miss it on first install.

### Problem 2 — Foot+floor contact

**The artifact:** kid stands on the basement floor. Puppet's feet hang in space at whatever Z-height they were rigged at (in V2's rig, that's roughly Z = 0.05m above origin — they don't visibly plant). Worse: when the kid sits at a desk, the foot landmarks get occluded; V2 falls back to rest pose; feet float at rest height regardless of where the actual chair/floor is.

**The root cause:** V2's foot bones are rotation-only. There's no IK chain pulling the foot tail toward a world-space target. The bone direction tracks MP's foot landmarks (when visible) but the bone's POSITION is determined by the parent chain (lower_leg.tail), which is determined by the upper_leg, which is determined by the pelvis (anchored at origin). If the pelvis is at world origin and rest leg lengths are 0.85m total, foot bones are at z=-0.85m... unless you count the foot bone offset, which lands them roughly at z = 0 to z = 0.10m. Either way, NOT a function of where the kid's actual floor is.

**Couples with Problem 1:** if we DID solve hip translation, foot floor-contact becomes essential — a puppet whose pelvis translates but whose feet don't ground would look like it's gliding (foot tails permanently 5cm above the floor). And conversely, if the puppet stays planted (no translation) but its feet DO clamp to a floor, we'd have to decide: does the floor live at world Z=0, or at some Z-offset that matches the puppet's pelvis-to-floor distance?

**Why this matters pedagogically:** "feet planted on the ground" is a strong visual signal of weight + presence. A character whose feet float looks ghostly. Even subtle floor-contact (toes brushing a defined floor plane) anchors the puppet emotionally as "a body in a place."

### Why we design them together

Three interactions:

1. **Floor Z reference depends on hip Z.** If pelvis is anchored at world origin AND legs are rest-length, the floor is roughly at z = -0.85m (rough leg height). If pelvis translates, the floor reference moves with it OR stays fixed in world space — and those two choices have different visual implications.

2. **Stance assumption couples both.** If we say "puppet stays planted in world space" (constant-stance for hip translation), then the floor is at a known fixed Z and foot clamping is trivial. If we say "pelvis translates with kid," foot clamping needs to know the absolute floor Z, which we'd have to commit to or detect.

3. **Failure modes share a workaround.** Both problems have the same edge case: when MP loses the lower body (kid sits at desk, occlusion), the puppet's lower body should "freeze gracefully" rather than wobble. Both fixes need to handle the lost-tracking case the same way.

---

## Candidate Solutions

### For Problem 1 (hip translation)

#### 1a. Constant-stance (RECOMMENDED for v2.0.2)

**What:** keep the current behavior. Pelvis stays at world origin. Document this as an explicit design decision instead of an unfixed bug. Update the rig comment to say "puppet anchors at stage center; performer's translation is captured via upper-body lean."

**Cost:** zero lines of code. The current behavior IS the implementation.

**Pedagogical value:** matches classical marionette tradition (fixed stage, performer in place). K-12 students with no V2 reference don't miss what they never had. Storytelling pedagogy reasons puppets shouldn't translate independent of the puppeteer's voice / story arc anyway.

**Limitations:**
- Kid walks across the room → puppet doesn't follow → narrative range capped at "puppet performs in place."
- Some performance ideas become awkward (e.g., "puppet runs away from a monster").

**Why this is the right first move:** for K-12 puppet show, the dollar value of "puppet is alive in the body and face" >> "puppet can translate in space." Constant-stance saves us implementing something complicated for a feature that's nice-to-have, not need-to-have. If classroom testing reveals kids consistently asking for translation, revisit then.

#### 1b. Image landmarks + camera depth assumption

**What:** instead of `pose_world_landmarks`, use `pose_landmarks` (image-space, with normalized x/y in [0,1] and a noisy z). Map image-space hip position to a world-space hip position assuming a fixed camera distance (e.g., kid is 2 meters from camera) and fixed FOV.

**Cost:** moderate. Sender modifications to broadcast image-space landmarks alongside world-space; receiver math to map; calibration parameters (camera distance, FOV) per-installation.

**Limitations:**
- **Camera distance assumption is brittle.** Kid moves toward/away from camera → mapping shifts → puppet appears to scale weirdly.
- Image-space Z is MP's least-trusted output. Incorporating it adds noise.
- Per-installation calibration violates "ships in a backpack, runs without setup" deployment posture.

**Why deferred:** the calibration burden contradicts CACHE/HIHO deployment goals. Worth revisiting if classroom testing demands translation AND we have a separate hardware-calibration solution for the room.

#### 1c. Tracking marker on the floor (Charuco-style)

**What:** print a fiducial marker, place it on the floor in the kid's frame. Sender detects the marker, derives the camera's intrinsic + extrinsic calibration from it, then maps `pose_world_landmarks` into actual world space.

**Cost:** high. Charuco / ArUco detection in the sender; calibration math; distribution of fiducial markers with the deployable kit; installation procedure.

**Limitations:**
- Adds a physical artifact to the classroom — a fiducial marker that has to be visible AND positioned correctly. Kid steps on it = drift.
- Per-installation setup overhead.
- Kid moving the marker mid-session = recalibration mid-session.

**Why deferred:** this is FreeMoCap's path because they want full-body absolute world tracking. Our use case (puppet show) doesn't need that fidelity. Save for a research paper, not a classroom kit.

#### 1d. Estimate from inter-frame body deltas (optical-flow-on-pose-landmarks)

**What:** track the body's image-space center of mass frame-to-frame. Translate the puppet's pelvis by an amount proportional to the inter-frame delta. Doesn't need absolute calibration — just relative motion.

**Cost:** moderate. New field in the body packet (inter-frame delta vector). Translation logic in the receiver. Tunable scaling factor.

**Limitations:**
- Drift accumulates over time. Unless we cap it (clamp puppet to a stage-area bounding box), the puppet eventually walks off-screen.
- Sensitive to camera shake. If the camera bumps, puppet "jumps."
- Scaling factor is per-deployment magic number.

**Why interesting later but not now:** matches the "puppet follows kid" feel without absolute calibration, which is the right trade for puppet-show deployment. But it has its own subtleties (drift, clamping). Best as a v2.1+ revisit AFTER constant-stance has been classroom-tested and we know whether translation matters.

### For Problem 2 (foot+floor contact)

#### 2a. Ground-plane clamp (RECOMMENDED for v2.0.2)

**What:** after the foot-drive math runs, check if the foot bone's tail-Z is below 0 (or below a `FLOOR_Z` constant). If so, project the bone's tail up to Z = FLOOR_Z. Cheap post-hoc clamp.

**Cost:** ~10 lines in `_drive_foot_basis` or `_try_drive_foot`. One constant (`FLOOR_Z = 0.0` or similar). Optional UI for kid to set floor height per their stage setup (slider in N-panel, "Floor Height: -0.85m for standing kids, 0.4m for kids sitting at desks").

**Limitations:**
- Visual continuity: when kid sits down, foot tail snaps to floor (rather than dipping below) — but the upper leg now has weird length (since bones are rotation-only with constant rest length, the lower_leg can't "shorten" when its tail is clamped). Result: foot floats below ground BEFORE the clamp; foot snaps to floor AFTER the clamp; legs look stretched.
- Doesn't solve the inverse problem (foot too HIGH when MP estimates foot is above ground).

**Mitigations:**
- Accept the leg-stretch artifact for K-12; it's better than feet sinking through floor.
- Pair with stance-blend (2c) for a cleaner fix.

#### 2b. Foot IK rig (full inverse kinematics)

**What:** add IK chains from pelvis → leg → foot, with foot controllers as targets. Drive foot CONTROLLERS to MP foot landmark positions; let Blender's IK solver compute leg bend.

**Cost:** high. Restructure the rig to add IK constraints; modify recorder to bake controllers instead of bones; drive controllers from MP. Architectural change to the rig structure. ~200+ lines.

**Limitations:**
- Adds rig complexity for kids who later want to read/edit the addon.
- Blender 5.2 IK has its own quirks; may interact weirdly with the simulation-zone-physics code path.
- Likely overkill for puppet show fidelity.

**Why deferred:** this is the "correct" fix for film-grade mocap. For puppet show, ground-plane clamp + stance-blend gets 80% of the visual benefit at 20% of the engineering cost.

#### 2c. Stance-blend (pair with 2a)

**What:** detect "kid is standing" vs "kid is sitting/occluded" from MP visibility scores on lower-body landmarks. When standing, drive feet from MP. When sitting/occluded, blend toward a planted "rest stance" pose that has feet on the floor.

**Cost:** moderate. Visibility threshold tuning; rest-stance pose definition; blend logic. Existing code already has the lost-hand reset pattern that's similar in spirit (per `feedback_three_mode_tracked_physics`).

**Pedagogical value:** kid sits at desk → puppet "stands" gracefully on the stage. Kid stands up → puppet feet animate. Smooth state transition.

**Why interesting:** this is the right pair for ground-plane clamp. Together they handle the two main visual failures (sinking through floor, feet drift on occlusion).

---

## Recommendation

**For v2.0.2 — ship constant-stance + ground-plane clamp.** Together: ~20 lines of code, no architectural surgery.

| Problem | Recommendation | Rationale |
|---|---|---|
| Hip translation | **1a (constant-stance)** — explicit design decision | K-12 puppet show doesn't need translation; classical marionette tradition supports fixed-stage puppetry; saves us calibration overhead that contradicts deployment posture |
| Foot+floor | **2a (ground-plane clamp)** + comment-out 2c hooks for later | Cheap to implement, eliminates worst visible artifact (feet sinking through floor), accepts minor leg-stretch artifact as K-12-acceptable |

**Order of operations:**

1. **Document constant-stance as an explicit choice.** Add a comment block at the pelvis-anchor site in `core/receiver.py` and in `V2_DESIGN.md` (when it gets its overdue update). State: "V2's puppet is anchored at world origin by design. Performer translation is expressed via upper-body lean. This is a puppet-show pedagogy choice, not an MP limitation. Revisit in V2.1 if classroom testing demands translation."

2. **Implement ground-plane clamp.** Add `FLOOR_Z` constant (probably 0.0 to start). In `_drive_foot_basis` or right after the foot drive call, clamp `foot_pose_bone.matrix.translation.z` if below `FLOOR_Z`. Test with kid sitting (occluded feet should land at floor) and kid standing (visible feet should track MP, clamping only when MP estimates foot below ground).

3. **Stub stance-blend hooks** without implementing the full logic. Leave commented `# TODO(v2.1): stance-blend` markers at the right spots so the future implementation has obvious landing pads.

4. **Optional N-panel slider for floor height.** Kid sitting at desk → set floor higher; standing → floor lower. ~5 lines for the UI; pairs with the clamp constant.

5. **Test environment:** basement / open-space. The K-12 deployment scenario IS standing kids in front of a laptop, so the standing-kid-with-visible-feet test is the canonical case. Desk testing (occluded feet) is the secondary case.

---

## Cross-Cutting Design Concerns

### How does this interact with MP's lower-body L/R inversion fix (day7f)?

Recall: legs use direct mapping (MP-L → puppet-L) to undo MP's flip-induced inversion. Foot bones currently use mirror (MP-L → puppet-R) — but per HANDOFF Open Issue #2 ("foot drive empirical test"), this is untested in standing pose. The foot+floor work above doesn't change this; the L/R question stays separate.

### Sim-zone physics interaction

V1 had Verlet physics in geometry nodes. V2's bones-only-during-capture approach skips the physics entirely (mesh attaches post-bake). So foot+floor clamp doesn't fight physics — it's pure post-drive math.

### Recording / bake interaction

The clamp happens during live drive AND should happen during the bake. Since the bake is "constant scale per-bone applied at stop_recording time + per-frame rotation fcurves," clamping happens at the `_drive_foot_basis` call which runs during BOTH live mirror AND record. The clamped position automatically becomes the keyframe value. No additional recorder changes needed.

### What if the kid ALSO has a chair / desk in frame?

MP's pose model is human-only. Furniture occlusion of feet is one of the main expected failure cases — that's exactly why ground-plane clamp + stance-blend is the right pairing.

---

## Open Questions

1. **What's the right `FLOOR_Z` default?** v0 = 0.0 (world origin). v1 might be set by a calibration step at session start ("kid stands neutrally; we read the foot-tail Z and use that as floor"). v2 could be UI slider per-deployment. Probably ship v0, expose via UI in v2.0.3 if classroom testing demands it.

2. **Does `Create V2 Rig` need updating?** Currently the rig is built with rest pose feet at some Z. If `FLOOR_Z` differs from rest foot Z, the puppet's "neutral pose" (when no kid is detected) won't have feet on the floor. Two options: (a) rebuild rig with feet exactly at FLOOR_Z, or (b) accept that the no-detection rest pose has floating feet. Probably (a) for v2.0.2.

3. **How does the `Constant stance` decision interact with `Reset Physics` operator?** V1 had a Reset Physics button that snapped state. V2 doesn't have physics (bones-only), but there's a "lost hand → reset to identity" pattern. Foot reset should match: lost foot detection → reset to FLOOR-clamped rest pose, not arbitrary rest.

4. **N-panel slider for floor height — UI scope creep?** Adding any UI surface area for K-12 kids violates Kid Pix's "one button per operation" principle. But this slider is genuinely useful for the teacher / TA setting up the room. Probably belongs in an "Advanced Setup" collapsed section, not in the main flow.

5. **What about overhead camera angles?** If a teacher mounts the laptop high (looking down at kid), MP's depth axis re-projects oddly. The foot+floor system as designed assumes camera roughly at kid's chest level. Document this constraint.

---

## What This Doc Does NOT Cover

- **Full physics-based foot dynamics.** V2 is bones-only; mesh attaches post-bake. Soft-body foot squish is V2.x territory at earliest.
- **Multi-floor environments / stairs / ramps.** V2 assumes one flat floor. Stage design with elevation changes is a V2.1+ research question.
- **Body-scale auto-calibration.** Every kid is a different size; current code uses rest-pose proportions for everything except hands. Whether the puppet's leg length should match the kid's leg length is a separate body-calibration research question.
- **Multi-puppet scenes.** Puppet-puppet interaction (one puppet hands an object to another) is not in scope.

---

## Cross-References

- **Source files this work would touch:** `core/receiver.py` (`_drive_foot_basis` or `_try_drive_foot` — foot clamp); `core/rig.py` (`Create V2 Rig` — possible rest-pose Z adjustment); `ui/panels.py` (optional floor-height slider); `__init__.py` (bl_info bump to v2.0.2)
- **Related research docs:** `BLENDARMOCAP_FOOT_MATH.md` — foot triangle math; `FREEMOCAP_RESEARCH.md` — multi-cam triangulation reference
- **Related memories:** `feedback_research_doc_first_pattern`, `feedback_three_mode_tracked_physics` (TRACKED / RELEASED / REACQUIRING — relevant to stance-blend if it ships), `project_ppparty_deliverable_is_baked_animation` (informs the "K-12 doesn't need film-grade mocap" thesis)
- **HANDOFF references:** Open Issues #2 (Hip translation) and #3 (Foot + floor contact) — this doc supersedes both as a research artifact
- **Pedagogy reference:** `STUDIO/DOCUMENTATION/VISION_2026-04-17.md` — HIHO/CACHE pedagogical posture, K-12 puppet show framing

---

## David — Decision Point

Two questions before any code:

1. **Confirm the recommendation (1a + 2a — constant-stance + ground-plane clamp) as v2.0.2.** Or push back: do you want to revisit constant-stance with a stronger argument for translation, or skip foot-floor clamp because the desk-occlusion case is rare?

2. **Approve the design framing?** In particular:
   - Constant-stance documented as a design choice, not a bug
   - Stub-only for stance-blend (commented hooks for v2.1 later)
   - Optional N-panel floor-height slider in "Advanced Setup" sub-section
   - `Create V2 Rig` adjusts so rest-pose feet land at `FLOOR_Z`

If yes to both → next step is the design doc for v2.0.2 (precise callsites, exact math, edge cases) — same shape as `HAND_SIDE_REF_DESIGN.md`. Then code.

If you want to redirect (e.g., go straight to foot IK because you've had it with the rotation-only feet, or push to ship 1d for translation now), tell me which and I'll revise.
