# HIHO MOCAP — Facial Mocap / Face-It Replacement Research (2026-05-29)

**What this is.** Durable findings from a deep-research pass run 2026-05-29 on whether
a free, open-source pipeline can replace the paid Blender addon **Face-It**
(superhivemarket.com/products/faceit) for facial motion capture and facial rigging, for
the HIHO MOCAP project. Sister document to `AUTORIG_RESEARCH_2026-05-28.md` (the
"HIHO Mixamo" body-rig research); same structure, same clean-room discipline.

**New hardware context.** David built a DIY head-mounted facial-capture rig (a
repurposed helmet with a boom holding a camera in front of the performer's face). This
lets face and body be captured in ONE simultaneous take. Targets are stylized humanoid
to chibi (large eyes, simplified features), NOT photoreal. Everything must run OFFLINE
on a ~2023-iMac hardware floor for under-resourced classrooms.

**Method.** Automated fan-out web research; claims extracted and adversarially verified
(3-vote). 21 claims survived verification, 4 were refuted. This doc keeps the durable
conclusions. Clean-room rule honored throughout: Face-It is characterized only from its
PUBLIC docs (faceit-doc.readthedocs.io), marketplace copy, and changelog — NOT from its
code, even though a reference copy is vendored in `SOFTWARE/R&D/`.

---

## Bottom line: ASSEMBLE an open-source pipeline (do not adopt one tool, do not build from scratch)

No single free tool replaces Face-It. But Face-It itself is **not a monolith** — its own
docs reveal it is mostly an *integration hub* that wires together external engines and
adds Blender-side rigging/retargeting/bake plumbing. The capture engine it leans on for
the free path is *already open-source* (MediaPipe, via "Face Landmark Link"). So the job
is to recompose the same external pieces ourselves, exactly the pattern HIHO MOCAP
already uses for body capture.

Three of the four functional layers have a clean, AGPL-3.0-compatible open-source answer
that is current and lightweight. The one weak layer is **rig generation onto stylized/
chibi faces** — that is the frontier, and it is the same *kind* of problem (transfer a
template onto a messy/extreme user mesh) that skinning was in the body-rig research.

---

## What Face-It actually is (the quality bar to clear)

Decomposed from its public docs, Face-It is four layers stacked on a 52-shape standard:

- **The standard.** Face-It's canonical expression set is Apple's **52 ARKit
  blendshapes** (it also supports a 46-shape Nvidia Audio2Face set). ARKit-52 is the de
  facto facial-mocap interchange format; even competitors (Audio2Face, KeenTools) have
  converged on emitting ARKit. *This is the coefficient standard our pipeline must
  produce and consume.* (Confirmed, high.)

- **Layer 1 — Rig generation (the headline feature).** Semi-automatically generates the
  52 ARKit shape keys onto an *arbitrary user-supplied character mesh* with **no
  sculpting/modeling required**, "non-destructive," adapting a built-in template to the
  user's own topology/morphology. Docs explicitly claim it works for "photorealistic
  human, anthropomorphic or cartoon" models. *This is the bar.* (Confirmed, high.)
  - **Important caveat for HIHO:** Face-It's chibi support *degrades exactly at our
    target extreme.* Its own FAQ + Blender Artists threads report that flat/large anime
    eyes need manual pivot-point relocation, automatic weights "sometimes return bad
    results" needing hand weight-painting, and one user got "fairly horrifying" results
    on an exaggerated-eye character ("the eyes are just too big… pushed the plugin past
    its limits"). So even the paid tool treats extreme chibi as in-scope-but-imperfect.
    The bar to clear on stylized faces is therefore lower than the marketing implies.
    (Confirmed, high — this is the single most strategically useful finding for scoping.)

- **Layer 2 — Capture.** Face-It ships **no proprietary tracker of its own.** It is an
  importer/recorder that wires external engines: ARKit depth-iPhone apps (Live Link
  Face, Face Cap, iFacialMocap, Facemotion3D, BMC), a webcam app (Hallway Tile), and the
  **open-source MediaPipe path "Face Landmark Link."** Because the capture layer is
  external integration, an open-source pipeline replaces it by wiring the same engines —
  and the free path's engine is already OSS. (Confirmed, high.)

- **Layer 3 — Retargeting.** A many-to-one / one-to-many mapping: each captured source
  expression (ARKit or A2F) is assigned to one or more target shape keys on the user's
  *own* registered mesh or an auto-generated control rig (not a fixed template). Shape
  keys "do not need to match the source expressions exactly." Assignment is via a
  fuzzy-name-matching "Find Target Shapes" operator plus manual dropdowns. Crucially,
  **this layer assumes the shape keys already exist** — rig generation (Layer 1) is a
  separate workflow. (Confirmed, high.)

- **Layer 4 — Bake.** A driver-based ARKit "Control Rig" whose bones drive the 52 shape
  keys; bake operators commit animation bidirectionally and non-destructively between
  control-rig keyframes and the actual shape keys. Live recording is *not* auto-baked —
  it is a one-click post-step after stopping the receiver. "Without external tools" is
  scoped to the Blender side (an upstream capture app still produces the stream).
  (Confirmed, high.)

---

## Per-layer open-source answers

### Layer 2 — CAPTURE: SOLVED. Use a MediaPipe Face Landmarker bridge (recommend DeadFace).

This is the strongest layer. The recommended capture path for the head-mounted RGB
helmet cam is **MediaPipe Face Landmarker**, consumed via a small open-source bridge.

| Tool | Source | License | Maintenance | What it does | Fit |
|---|---|---|---|---|---|
| **MediaPipe Face Landmarker** | ai.google.dev/edge/mediapipe/solutions/vision/face_landmarker | Apache-2.0 (code + model weights, confirmed via the official Blendshape V2 model card) | Current, Google-maintained | Outputs **52 blendshape coefficients per face** with ARKit-style category names (browDownLeft, browInnerUp, …), from **plain 2D RGB** (image/video/live), **no depth sensor** | The engine. AGPL-compatible, offline, lightweight, RGB-only → fits helmet cam exactly |
| **DeadFace** | github.com/Qaanaaq/DeadFace | **MIT** (deps MeFaMo + PyLiveLinkFace also MIT) | **Alive** — created Aug 2025, last push Feb 26 2026, v1.1.0, not archived | Wraps MediaPipe; **Stream Mode** (live UDP) + **Video Mode** (prerecorded .mp4/.mov → normalized blendshape **CSV** in Live Link Face format) | **Top pick.** Video Mode → CSV is the natural one-take offline path; MIT |
| **Face Landmark Link** | github.com/Qaanaaq/Face_Landmark_Link | Apache-2.0 | Alive — v0.23.6 (May 2025), 81 commits | The MediaPipe bridge Face-It itself integrates; writes Live-Link-compatible blendshape CSV | Proven (Face-It consumes it). DeadFace is its newer sibling by the same author |

**Two important precision notes (confirmed):**
1. MediaPipe's docs say "52 blendshapes" with ARKit-*style* names but do **not** assert
   ARKit-*standard* compatibility on the page. In practice the usable count on the
   MediaPipe path is **~51, not 52** — `tongueOut` is effectively absent (no MediaPipe
   keypoints describe the tongue). For HIHO's stylized targets this is immaterial.
2. Both bridges emit a **Live Link Face-style CSV**, which is *exactly the format
   Face-It's own importer already ingests.* That CSV is the clean hand-off seam.

### Layer 2 — the RGB-vs-depth decision: choose RGB MediaPipe, NOT the iPhone path.

The research question asked to recommend ONE path for a head-mounted helmet cam used at
the same time as the RGB body cameras. **Recommendation: RGB MediaPipe (path a).**
Rationale, grounded in confirmed facts:
- The helmet rig is already an RGB camera; MediaPipe is RGB-only and needs no depth
  sensor. The depth-iPhone path (TrueDepth + Live Link Face) adds a second proprietary
  device, an iOS dependency, and cost — all hostile to the offline/under-resourced floor.
- **One-take time sync.** Body capture is RGB video through FreeMoCap. If the helmet face
  cam is *also* plain RGB video, the face stream and body streams are the same kind of
  artifact and can be synced by the same clapper/timecode method already used for the
  multi-cam body rig. A depth-iPhone Live Link stream is a different clock and a
  different file type, which complicates the single-take sync HIHO wants.
- Fidelity tradeoff is acceptable: TrueDepth/ARKit is higher-fidelity on subtle
  micro-expressions, but HIHO targets large-eyed simplified faces where that subtlety is
  stylized away. The chibi target *lowers* the fidelity bar, which is exactly when RGB
  MediaPipe is good enough.

### Layer 3 — RETARGETING: SOLVED in principle. ARKit-CSV → shape keys is a known bridge.

ARKit-52 is the interchange standard, MediaPipe already emits ARKit-named coefficients,
and the mapping behavior to replicate (one source expression → one-or-more target shape
keys, names need not match exactly) is well-understood from Face-It's docs. The
open-source seam is the **Live Link Face CSV**: any ARKit-CSV → Blender shape-key bridge
covers this layer. This is a small, tractable build (a coefficient-to-shape-key mapping
table plus a per-frame keyframe writer), not a research problem. *It presupposes the
target shape keys exist — which is Layer 1, the frontier.*

### Layer 4 — BAKE: SOLVED. This is native Blender plumbing.

Committing per-frame ARKit coefficients to shape-key keyframes is ordinary Blender
fcurve writing — the same baking HIHO MOCAP already does for body bones. Face-It's extra
nicety (a bone control rig that drives shapes via auto-generated drivers, with
non-destructive bidirectional bake) is optional polish, not a blocker. The minimum
viable bake is "write coefficient C to shape-key value at frame F," which is trivial.

### Layer 1 — RIG GENERATION: THE FRONTIER. No clean free tool transfers 52 ARKit shapes onto a chibi mesh.

This is the headline Face-It feature and the weakest open-source layer — the facial
analogue of "robust skinning" in the body-rig research. The verified leads do **not**
solve it:
- The capture/bridge tools (MediaPipe, DeadFace, Face Landmark Link, OpenSeeFace) all
  *consume or assume* shape keys; **none generates them.**
- Blender-native shape-key transfer building blocks exist (Surface Deform, Data Transfer
  modifier, deformation-transfer / example-based methods) but were not verified here as a
  packaged, chibi-robust 52-shape generator. They are the most promising raw material,
  not a finished tool.
- Face-It's own chibi degradation (above) tells us even the paid solution is
  semi-automatic-plus-manual-cleanup at this extreme, so the bar to clear is "decent
  template transfer + a manual fix-up pass," not "flawless automation."

---

## Ruled out (with reasons)

- **OpenSeeFace** — github.com/emilianavt/OpenSeeFace. License is fine (**BSD-2-Clause**,
  AGPL-compatible), but it outputs **66-point landmarks + a small custom feature set
  (eye/brow/mouth) + head pose, NOT ARKit-52 blendshape coefficients.** Its expression
  component is a per-user-calibrated SVM over a handful of *discrete* user-defined
  expressions, not a continuous ARKit stream. Using it would require building a separate
  landmark→blendshape solver — strictly more work than MediaPipe, which emits
  coefficients directly. Ruled out *for the capture layer* on capability, not license.
  (Confirmed, high.)
- **Depth-iPhone / Live Link Face capture path** — works and is higher fidelity, but adds
  a proprietary iOS device, cost, a second clock for one-take sync, and violates the
  offline/under-resourced-floor ethos. Ruled out as the *recommended* path (still a
  fallback for a high-fidelity realistic target someday).
- **Adopting Face-It itself** — paid, and (per project hard rule) zero paid
  dependencies. It is the quality bar and the architecture template, not a component.

### Leads named in the brief but NOT verified this pass (do not assume)

These were in the "known leads" list but did **not** surface in the 21 confirmed claims,
so treat them as OPEN, not cleared:
- **MeFaMo** (github.com/JimWest/MeFaMo) — confirmed only indirectly: it is MIT and is a
  *dependency of DeadFace* (MediaPipe → ARKit blendshapes → PyLiveLinkFace). DeadFace
  supersedes it as the thing to actually run. (Medium confidence via DeadFace lineage.)
- **FACSvatar**, **NVIDIA Audio2Face** (license unverified here; A2F is audio-driven, not
  video-face capture, and its set is 46-shape), **KeenTools FaceBuilder/FaceTracker**
  (paid), **Rokoko Face** (paid) — none verified; the paid ones are presumptively out on
  the zero-paid-deps rule but were not individually license-checked this pass.
- **Blender-native deformation-transfer / Surface Deform / Data Transfer for rig
  generation** — named as the Layer-1 hope but **not** verified as a working chibi-robust
  52-shape generator. This is the frontier lead to chase, not a confirmed answer.

---

## The frontier (where open source is weakest)

**Rig generation onto stylized/chibi faces (Layer 1).** Capture, retarget, and bake all
have clean AGPL-compatible answers; generating the 52 ARKit shape keys on an arbitrary
large-eyed chibi mesh does not. This mirrors the body-rig finding precisely: the
*motion* side is solved by recomposing existing tools, and the **mesh-deformation
authoring side is the genuinely hard, unsolved-in-free-tools part.** And as with
skinning, the saving grace is that HIHO's stylized target *lowers* the fidelity bar and
tolerates a manual cleanup pass, so "good template transfer + artist fix-up" is a viable
scope rather than "flawless automation."

---

## The single first thread to pull next session

**Test whether a Blender-native shape-key-transfer approach (deformation transfer via
Surface Deform / Data Transfer, or an example-based method) can carry the 52 ARKit shapes
from one rigged donor face onto a chibi student mesh — accepting a manual fix-up pass.**

This is the exact analogue of the body-rig report's "test Blender bone-heat first before
building a robust solver." If a native-Blender donor→target shape transfer gets us 80%
of the way on a real chibi face, the whole facial rig-generation layer shrinks to
"transfer the 52 shapes, then hand-fix the eyes," and the entire Face-It replacement
becomes an assemble-and-glue job:

> **MediaPipe/DeadFace (capture, RGB helmet cam) → Live Link CSV → ARKit-coeff→shape-key
> mapping (retarget) → fcurve bake → Blender, with a one-time donor→chibi shape-key
> transfer (rig gen) per character.**

Build the cheap rig-gen experiment first; the capture/retarget/bake legs are already
de-risked.

---

## Open questions for future sessions

1. **Rig gen:** Does Blender-native deformation transfer (Surface Deform / Data Transfer)
   carry all 52 ARKit shapes onto a chibi mesh acceptably, or do the large eyes/simplified
   mouth break it the same way they strain Face-It? (THE frontier question — test first.)
2. **Donor asset:** Is there an AGPL-compatible, already-rigged 52-ARKit-shape *stylized*
   donor head to transfer FROM? (A realistic donor may transfer poorly to chibi.)
3. **One-take sync mechanics:** What exact clapper/timecode method aligns the helmet RGB
   face stream to the multi-cam body streams in a single take? (Confirm it reuses the
   existing body-rig sync, as assumed.)
4. **MeFaMo vs DeadFace vs Face Landmark Link:** hands-on fidelity comparison of the three
   MediaPipe bridges on real helmet-cam footage; confirm DeadFace's CSV drops cleanly into
   the HIHO bake. (Capability is confirmed; relative quality is not.)
5. **Audio2Face / FACSvatar / KeenTools licenses** — not individually verified; only
   matters if a non-MediaPipe path is ever wanted.

---

## Caveats (read before quoting)

- **Clean-room preserved.** Every Face-It claim is from PUBLIC docs/marketing/changelog,
  not its code, even though a reference copy is vendored in `SOFTWARE/R&D/`.
- **"52" is really ~51 on the MediaPipe path** (`tongueOut` absent). Immaterial for chibi.
- **MediaPipe model weights are Apache-2.0** (verified via the official Blendshape V2 model
  card PDF, Nov 2022, still the shipping model); the out-of-scope notes (no facial
  recognition, not life-critical) are usage caveats, not license restrictions.
- **The capture/retarget/bake "solved" verdicts are high-confidence; the rig-gen frontier
  rests on the ABSENCE of a confirmed tool**, not on a tested failure. The Blender-native
  transfer hope is unverified and could clear the bar — test before building.
- Four claims were adversarially **refuted** and are NOT relied on here, notably the
  framing that Face-It is "purely an importer with no capture role" (it does have
  Blender-side live recording) and that its control rig architecture is the *required*
  retargeting model (a plain coefficient→shape-key write also works). Do not cite those.
- Several named leads (FACSvatar, Audio2Face, KeenTools, Rokoko, native deformation
  transfer) were NOT verified this pass — listed as open, not cleared.

---

## Key sources

- Face-It docs (clean-room reference): https://faceit-doc.readthedocs.io/
  (mocap_general, target_shapes, mocap_importers, control_rig)
- Face-It product page: https://superhivemarket.com/products/faceit (HTTP 403 to bots;
  copy corroborated via the readthedocs docs)
- MediaPipe Face Landmarker: https://ai.google.dev/edge/mediapipe/solutions/vision/face_landmarker/web_js
- MediaPipe Blendshape V2 model card (Apache-2.0): https://storage.googleapis.com/mediapipe-assets/Model%20Card%20Blendshape%20V2.pdf
- DeadFace (MIT, top capture pick): https://github.com/Qaanaaq/DeadFace
- Face Landmark Link (Apache-2.0, the bridge Face-It integrates): https://github.com/Qaanaaq/Face_Landmark_Link
- MeFaMo (MIT, DeadFace dependency): https://github.com/JimWest/MeFaMo
- OpenSeeFace (BSD-2; landmarks only, ruled out for capture): https://github.com/emilianavt/OpenSeeFace
