# Mocap Correction Tools — Landscape Research — 2026-08-11

**What this is.** The research pass (research → design → code) on a new area David
opened 2026-08-11: post-bake **mocap correction** — fixing a captured take after
smoothing, at the pose level. Pin a sliding foot, nudge a drifting arm over a frame
range, hold a hand on a prop, and bake the fix back down without flattening the
performance. Prompted by a 2026-08 r/mocap post announcing GoodGood3d's "Mocap
Corrector" plugin (Patreon-gated, closed source), whose pitch is a tidy requirements
list for everything artists want at this stage. Questions: what already exists, where
are the gaps, what can HIHO build?

This is the research layer only. No design doc, no code. Scope discipline: correction
operates on the **rig surface** (baked bones in the .blend), after the data surface
(npy filtering, outlier rejection) and after per-region smoothing. It is the stage the
old panel stubs called "Polish" (retired 1.4.40) and the natural core of the 1.5
ARTIST_INTUITION theme.

---

## Verdict up front

1. **Mocap correction in Blender is a paid cottage industry with zero open-source
   players.** At least eight commercial addons sell some slice of it (~$10–25 or
   patron-gated). The free side offers raw material (graph editor filters, NLA), rig
   converters, and curve helpers — but nobody free ships the actual workflow: pin,
   adjust over a range with falloff, bake back preserving nuance. **The gap is the
   whole lane, and it is exactly HIHO's lane** — the artist layer on top of the
   science bake, free forever.
2. **Rung 0 is already on disk.** The vendored ajc27 baseline includes a complete
   foot-locking operator (height threshold, anti-flicker window, eased attenuation,
   toe/heel targeting, knee/hip compensation) that our panel never surfaces.
   `SMOOTHING_RESEARCH_PRIOR_ART_2026-08-04.md` §2.5 already recommends exposing it as
   a standard pipeline step. First move in this whole area costs nearly nothing.
3. **Blender's native layer system cannot carry this yet — verified live.** Headless
   probe of this laptop's Blender 5.2.0 LTS (build 2026-07-14, `--factory-startup`,
   2026-08-11): the layered-Action API exists (`Action.layers`, `Action.slots`) but
   hard-errors past one layer ("An Action may not have more than one layer") and one
   strip per layer. Project Baklava's multi-layer phase is still upstream work
   (tracking issue blender/blender#154504). With the backend frozen per semester, no
   native layers before at least next term.
4. **We don't need to wait, and we don't need to build a layer system.** Because the
   HIHO deliverable is a baked take, a correction can live as temporary scaffolding
   (an empty + constraint, or a disposable IK chain) that is **collapsed by an
   additive delta-bake onto the existing dense keys**. The original high-frequency
   performance survives because we add a smooth delta to it rather than re-keying
   through the correction. That is the same property GoodGood3d advertises ("bakes
   over the original keyframe set... keeps all the original nuance") — and it needs
   neither NLA gymnastics nor Baklava. When Baklava's layers mature, they replace the
   scaffolding, not the UI.

---

## What we already have (why this fits)

- **A dense-keyframe bake with provenance.** Load Take → Spawn → Bake, quaternion
  continuity built in (1.4.33), `TAKE_raw` / `TAKE_clean` duplicate doctrine already
  in the cleanup recipe. Corrections have a stable, sign-continuous substrate.
- **Foot locking + joint limits, vendored.**
  `vendor/ajc27_freemocap_blender_addon/.../foot_locking/` (see §2.5 of the smoothing
  prior-art doc for the full parameter inventory), plus `set_bone_rotation_limits` and
  `limit_markers_range_of_motion`. Never surfaced in the HIHO panel.
- **Constraint hygiene.** Bake and Save Out already filter on `HIHO_`-prefixed
  constraints only (1.4.36), so temp correction scaffolding is safe by construction —
  a character's own rigging survives, and our scaffolds are identifiable and
  removable.
- **The trust signals.** Per-joint quality scoring and the volume map say where a take
  is likely to need correction (low-trust joints and low-trust room regions are where
  fixes concentrate). The badge machinery can someday *suggest* correction zones.
- **Bone-collection tiers.** The smoothing methodology's tier tables (root → torso →
  limbs → extremities) double as the falloff vocabulary for corrections: how far up
  the chain a fix is allowed to spend.
- **Motion paths** exist both in Blender and as an ajc27 operator — the standard
  before/after verification view for exactly this work.

---

## The landscape

### Free / open source

| Tool | What it gives | License / state | Correction relevance |
|---|---|---|---|
| Blender graph editor | Butterworth, Gaussian, decimate, F-modifiers | GPL, built-in | Already our smoothing stage; no pose-level workflow |
| Blender NLA additive tracks | Manual layered offsets | GPL, built-in | Functional but hostile UI — the thing every paid addon wraps |
| Copy Global Transform (bundled addon) | World-space copy/paste, "fix to camera" relative hold | GPL, built-in | Closest native thing to pinning; per-frame, no falloff |
| ajc27 foot locking (vendored) | Contact detect + lock with eased attenuation, compensation up-chain | AGPL, **already ours** | Rung 0; pre-bake on empties |
| [AnimAide](https://github.com/aresdevo/animaide) | Curve ease/blend/tween helpers | GPL, active | Polish-stage helpers; not mocap-aware, no pinning |
| [Expy Kit](https://github.com/pKrime/Expy-Kit) | Rig conversion, FK↔IK convert + bake | GPL, active | Proves disposable-IK-over-bake is practical in pure bpy |
| [Retarget](https://extensions.blender.org/add-ons/retarget/) (fork of Expy Kit + AnimAide) | Merged toolkit, updated 2026-08-03 | GPL, active | The one actively-maintained free neighbor; still no correction loop |
| [Footskate Solver](https://research.cs.wisc.edu/graphics/Gallery/FootskateSolver) (Kovar et al. 2002) | The academic contact-cleanup algorithm | Open, standalone C++ | Math reference, not a Blender tool |
| skellyforge / QuickMocap / SnowMocap | Data-side smoothing | (cataloged in smoothing doc §2.6) | Wrong surface — npy, not pose |

### Paid Blender addons (characterized from public material only — clean-room rule)

| Tool | Pitch | Cost |
|---|---|---|
| **GoodGood3d "Mocap Corrector"** (Pro Constantinou, 2026-08) | Auto IK rigs, correction-zone overlays + blends, Pin and Pin-follow, per-bone keyframe mode, motion paths, quick previews, blend-curve presets, additive bake preserving original keys | Patreon-gated, closed |
| **Animation Layers** (Tal Hershkovich) | NLA wrapped in a Maya-style layer UI; extract-marked-keys for mocap cleanup; the incumbent since 2020 | ~$20, Superhive |
| **Mocap Bone Lock** | Manual bone locks at frames + auto flat-ground contact detection; NLA non-destructive; bake preserves the rig's own constraints | Paid, Superhive/Gumroad |
| **Foot Flow** (2026) | Foot sliding, jitter, floating feet, contact, planted-foot locking | Paid, Superhive |
| Foot Lock / Inverse Lock Bone / Animation Snapper Pro | Narrower slices of the same | Paid |
| Foot Locker, In Placer | Free tier but closed | Free-closed |
| Auto-Rig Pro | Retarget/remap + IK conversion (adjacent stage) | ~$40 |

The r/mocap post's own framing confirms the market read: "Blender is notoriously bad
for layered corrections and even with plugins like Animation Layers you still need IK
rigs and constraints" — i.e., even paying customers of the incumbent still lack the
loop, which is why a second paid tool just appeared.

### Outside Blender (reference only)

- **MotionBuilder** — the industry's mocap-correction home; layers + pinning are its
  bread and butter. Closed, expensive, reference-only.
- **Cascadeur** — physics-assisted posing and cleanup; closed freemium (free tier now
  exports only its proprietary .casc format — a live lesson in why free-tier closed
  tools fail classrooms). AutoPhysics already characterized in the infill research.
- **FreeMoCap upstream** — no correction layer at all; V2 alphas are capture- and
  calibration-focused. Correction sits firmly on our side of the classroom-layer
  boundary drawn in `UPSTREAM_NOTES_FOR_FREEMOCAP_2026-08-05.md`.

---

## The substrate question (why the timing is safe)

Verified on this machine (headless `--factory-startup` probe, 5.2.0 LTS):
`Action.layers.new()` succeeds once; a second layer raises *"An Action may not have
more than one layer"*; a second strip raises *"A layer may not have more than one
strip"*; `ActionLayer` exposes no influence/blend controls. So the Baklava data model
is present but deliberately capped — the multi-layer phase remains upstream
(blender/blender#154504), and our per-semester backend freeze means nothing native
arrives before next term at the earliest.

Two workable substrates today:

1. **NLA additive tracks** — what Animation Layers and Mocap Bone Lock wrap. Works,
   but drags students into the NLA editor's mental model, and any UI we build over it
   becomes throwaway when Baklava lands.
2. **Temp scaffold + additive delta-bake (recommended).** The correction lives as a
   `HIHO_`-prefixed constraint (or disposable IK chain) only while the artist is
   adjusting. Apply = sample the corrected pose over the affected range, subtract the
   original, ease the difference in and out over the falloff window, add it onto the
   existing dense keys, delete the scaffold. No layer infrastructure at all; the
   .blend ends where our doctrine says it should — a clean baked take. `TAKE_raw`
   remains the undo of last resort.

Option 2 is Baklava-proof (when real layers arrive they simply become nicer
scaffolding), NLA-free, and matches capture-and-bake.

---

## What HIHO can build — the ladder

Difficulty scale as in `HIHO_ADOPTABLE_INNOVATIONS.md` (1 = config, 5 = research).

**Rung 0 — "Feet stop skating" (difficulty 1–2, mostly UI).** Surface the vendored
ajc27 foot locking (+ rotation limits) in the panel at its documented pipeline slot:
filter positions → foot-lock → bake → per-region smoothing. Already recommended by
the smoothing research; zero new algorithms; instant classroom value.

**Rung 1 — "Fix this spot" (difficulty 3).** One operator: select bone(s) + frame
range → addon builds the temp scaffold → artist nudges the pose in the viewport → one
dial (falloff width) → Apply delta-bakes and cleans up. No layer UI, no NLA exposure,
one undo. This is most of the value of the entire paid category in a single
plain-language verb.

**Rung 2 — "Hold it there" (difficulty 3).** Pinning: hand on a table, foot on a
step, prop follow (pin-to-moving-target). Same falloff + delta-bake path, plus the
honest up-chain payment question the ajc27 compensation parameters already model
(who absorbs the correction — the knee or the whole body). Kovar's footskate math is
the citable reference.

**Rung 3 — Zones and presets (difficulty 3–4).** Correction-zone overlays on timeline
and body (bone-collection tiers as the body vocabulary), blend-curve presets, a
per-take correction list (re-apply after re-bake). Quality-of-life, only after rungs
1–2 earn it.

**Rung 4 — Baklava watch (no build).** When upstream ships real multi-layer actions
with influence controls, port the scaffolding onto native layers. UI survives,
plumbing shrinks. Re-check each Blender release per the existing re-test rule.

**Explicitly not building:** our own layer system (Baklava will obsolete it); fully
automatic correction (the artist's hand is the lesson — auto-everything turns
animators back into spectators); a Cascadeur-style physics posing engine (the infill
research already owns the physics-constraint thread on the data surface).

---

## Pedagogy note

Correction is where a capture becomes animation — where students stop being capture
subjects and start making animator's choices: what to keep, what to fix, what a
performance is allowed to cost. Every commercial tool above charges for that
threshold; several charge students specifically (Patreon subscriptions, per-seat
addons). Shipping this free, in plain verbs ("fix this spot", "hold it there"), is
the program's argument in miniature.

## Sequencing

Vegetables first: the recorder wave (A/C/B), the calibration blank-box guard, and the
queued audit items stay ahead of any of this. This doc feeds the **ARTIST_INTUITION
design doc** (already in STATUS "Next up" as the 1.5 theme); rung 0 could ride any
earlier build day as a one-change item. Next gate for rungs 1+: a design doc. No code
before design.

## Sources

- r/mocap post + screenshots (provenance; feature list quoted there), GoodGood3d
  [Patreon](https://www.patreon.com/GoodGood3D) (login-walled; characterized from the
  public post only)
- [Animation Layers — Superhive](https://superhivemarket.com/products/animation-layers) ·
  [BlenderArtists thread](https://blenderartists.org/t/animation-layers/1228418)
- [Mocap Bone Lock — BlenderArtists](https://blenderartists.org/t/addon-mocap-bone-lock-auto-foot-sliding-fix-for-mocap-and-general/1630357) ·
  [Foot Flow — BlenderArtists](https://blenderartists.org/t/foot-flow-new-foot-animation-cleanup-add-on/1640052) ·
  [cgdive mocap-cleanup index](https://addons.cgdive.com/sub-categories/blender-mocap-clean-up)
- [AnimAide](https://github.com/aresdevo/animaide) · [Expy Kit](https://github.com/pKrime/Expy-Kit) ·
  [Retarget extension](https://extensions.blender.org/add-ons/retarget/)
- [Footskate Solver (UW-Madison)](https://research.cs.wisc.edu/graphics/Gallery/FootskateSolver)
- Baklava: [Animation 2025 blog](https://code.blender.org/2024/02/animation-2025-progress-planning/) ·
  [layered-actions tracking #154504](https://projects.blender.org/blender/blender/issues/154504) ·
  local 5.2.0 LTS API probe 2026-08-11 (primary evidence, this doc §substrate)
- [Cascadeur licensing FAQ](https://cascadeur.com/blog/general/cascadeurs-new-licensing-structure-comprehensive-faq)
- Internal: `SMOOTHING_RESEARCH_PRIOR_ART_2026-08-04.md` §1.4–1.7, §2.5–2.6 ·
  `GENERATIVE_INFILL_RESEARCH_2026-07-21.md` · `HIHO_MOCAP_WRAPPER_ARCHITECTURE.md` ·
  `UPSTREAM_NOTES_FOR_FREEMOCAP_2026-08-05.md`
