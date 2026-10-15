# Auto-rigging in Blender, October 2026: where it stands and what HIHO Studio should take from it

*2026-10-15, laptop. Research only, no Studio code changed. David's ask: "a deep dive on the current state of the art for
auto-rigging in Blender. AutoRig Pro to my knowledge is still the top tier... our goal is to get a design and interface
set up, an engine that is working as closely as well as the commercial model... something that's really intuitive."
Both axes count: rig quality (how the mesh deforms) and interface (how few steps). He put his own Auto-Rig Pro 3.78.63
on the Desktop for hands-on study; it is now installed and enabled in the laptop's Blender 5.2 (scripts/addons,
`auto_rig_pro-master`).*

**Companions:** `AUTORIG_SURVEY_2026-10-15.md` (the full web survey: 23-tool table, per-tool notes with URLs, licence
evidence, what changed since May), `AUTORIG_RESEARCH_2026-05-28.md` (May: Pinocchio family, voxel skinning chosen),
`ACTIONFORGE_STUDY_2026-10-13.md`, `STUDIO_SECTION_DESIGN_2026-07-01.md` (what Studio is today).

## 1. Bottom line

1. **David is right: Auto-Rig Pro (3.78) is still the reference.** Nothing free or open has caught its Smart workflow
   plus bind fix-ups plus export. But its engine is not magic: read from its source today, Smart is markers plus
   silhouette scanning, "Guess Markers" is a 2D pose detector run on screenshots of the model, and its best bind mode
   is the same voxel heat-diffuse method HIHO already vendors. HIHO Studio is in the same family with a smaller UI.
2. **The 2026 action is in skinning, not skeleton fitting.** Three new or refreshed add-ons sell the exact student
   problem (many pieces, not watertight): Adaptive Auto Skinning, WeightMend, Voxel Heat Diffuse Skinning 4.3. The
   fixed-skeleton fit itself is settled 2007 geometry.
3. **Neural rigging is real but not for HIHO's machines yet.** SkinTokens (MIT, Feb 2026) is the first open model that
   will skin a skeleton you hand it, which is exactly HIHO's shape, but it needs an NVIDIA GPU with 14 GB. Watch for a
   CPU or ONNX path; do not build on it now.
4. **So the design work is the interface, not the engine.** Studio's engine stays geometric (marker fit to the 63-bone
   rig + the MIT voxel solver). What Studio lacks is ARP's sequence: normalize silently, few mirrored markers with an
   editable guess, fingers as an optional sub-step, a preview before bind, one Bind button with named fix-up checkboxes.

## 2. Auto-Rig Pro, read from its own source (3.78.63, 2026-10-15)

**Licence:** `LICENSE.txt`: "The add-on source code components of Auto-Rig Pro are released under the terms of the GNU
General Public License, version 3." Assets (icons, rig .blends) are royalty-free / CC0; generated rigs belong to the user.
GPL-3 code may legally be combined with an AGPL-3 work (GPL v3 section 13). **Recommendation anyway: study, do not
copy.** It is one person's paid product and HIHO's goodwill with upstream projects is worth more than a shortcut. The
AI inference binaries are not in the zip (separate download, "AI files are missing or not up to date" check in code).

**The Smart panel, in order (`auto_rig_smart.py`, panel draw at line ~8220):**
1. Mac warning up front: "If Mac freezes or crashes, click this: Disable FX" (the GPU marker icons crash some Macs).
2. **Get Selected Objects**: duplicates and joins the selected meshes into a hidden `body_temp`, removes shape keys and
   risky modifiers, checks scene unit scale is 1.0, frames the character. Turn buttons rotate it to face -Y.
3. **Symmetrical Character** checkbox (default on), then **Guess Markers!** (AI) or manual markers in this order:
   Neck, Chin, Shoulders, Wrists, Hand Tip, Spine Root, Ankles. Markers are empties named `neck_loc`, `chin_loc`,
   `shoulder_loc` (+ `_sym`), `hand_loc`, `root_loc`, `foot_loc`; placed by mouse in a modal, clamped to the body's
   width and height. Required set for Go: chin, foot, hand, neck, root, shoulder (six).
4. Skeleton settings: presets (ARP default, UE4 Mannequin, ...), spine count (default 4), neck count, twist bones,
   Root Up, spine shape, shoulders alignment, Fingers on/off + count (5 or 4), finger engine (AI or geometric), facial
   on/off with per-feature toggles (ears, eyebrows, nose, cheeks, eyes, mouth, tongue, teeth, chin), Use Markers Depth.
5. **Go!** (`id.go_detect`): validates markers, appends the ARP human rig (345 bones, 67 deform), scans the mesh between
   markers (ray casts and BVH on the temp body) to place elbows, knees, hips, head, then aligns limbs.
6. **Match to Rig**, then **Bind to Rig** with engine: **Heat Maps** (Blender's bone heat, "accurate but may be
   inconsistent with multiple layers of clothes, props"), **Voxelized** (ARP's own approximate volume skinning, "more
   consistent than heat maps but less accurate with small details, fingers, facial"), or **Voxel Heat Diffuse Skinning
   (addon)** ("true volume skinning, requires the Voxel Heat Diffuse Skinning addon", the meshonline product whose MIT
   sibling HIHO vendors). 3.78 also lists Adaptive Auto Skinning as a fourth engine. Bind fix-ups are checkboxes: Split
   Parts, Scale Fix, Smooth Twist Weights, Improve Hips, Improve Heel, Refine Head.

**How "Guess Markers" works (the part worth copying as an idea):** `arp.guess_markers` screenshots the character from
front, side and top, runs an external inference binary per view (`inference_front`, `inference_side`, `inference_top`,
several front samples), fetches 2D keypoints, and sets the markers from them. That is a 2D pose estimator on rendered
images. HIHO already ships two of those for live footage (MediaPipe in 1.x, RTMPose in 2.0). **A HIHO "Guess Markers"
could render the character front and side in the viewport and run the tracker it already has.** No new dependency.

**Hands-on result today:** installed and enabled fine in 5.2. A scripted run of Smart (Get Selected Objects, six
markers from a silhouette scan, Go, Match, Bind) on the chibi test mesh failed at Blender's context checks (Smart's
operators need a live 3D viewport and mouse-placed markers; the ARP rig appended but never fitted), so the quality
comparison on the chibi is David's to run by hand: ARP Smart vs HIHO Studio on `CHIBI_PAWRAPPA_TEST.obj`, same bind
engine (Voxel), look at knees, shoulders, fingers. The test scene was removed afterwards.

## 3. The field in one table (details and URLs in the survey)

| Tool | What it is | Licence | Fits HIHO's rules (free, offline, old Macs)? |
|---|---|---|---|
| Auto-Rig Pro 3.78 | The reference. Markers + silhouette fit, AI marker guess, 3 to 4 bind engines, fix-ups, export | Code GPL-3, AI binaries proprietary | Study only |
| Easy Rigify (mid-2026) | ARP-shaped front end to Rigify: Mark, Detect (on-device AI), Align, Generate, Smart Bind | GPL-3.0-or-later (verified on the listing) | Yes to read; buy one seat ($15/$30), check headers in the zip |
| Adaptive Auto Skinning (2026) | GPU voxel skinning, Metal/Vulkan, Force CPU mode, body + clothes in one pass | "GPL", version not shown | Only if the zip says GPL-3-or-later |
| WeightMend (Oct 2026) | Voxel visibility + heat tolerant of broken meshes | "GPL", version not shown | Same |
| Voxel Heat Diffuse Skinning 4.3 | The commercial sibling of our vendored MIT solver; new diffuse controls | Python GPL, C++ core NOT GPL | No for the core; ours is the MIT sibling |
| Rigify (Blender 5.2) | No auto-fit; bugfixes only | GPL-2-or-later | Plumbing only, as in May |
| BlenRig 6 | Guided placement + mesh-deform cage + weight-transfer meshes | GPL-3 | Idea to borrow: cage transfer is CPU-only and survives messy meshes |
| Mixamo | Alive, degraded, five markers, server-side | Proprietary | No |
| AccuRIG 2 | Free, Windows only, auto guides + bind | Proprietary | No (Windows) |
| ActionForge | Browser, closed; studied 10-13 | Closed | Comparison demo only |
| UniRig / SkinTokens | Neural skeleton + skin; SkinTokens skins a given skeleton | MIT, MIT | Not on HIHO machines (CUDA 8 to 14 GB); watch |
| Make-It-Animatable v2 | Humanoid, Mixamo-style output | MIT repo, Apache weights | GPU only; watch |
| RigAnything, Anymate, AniGen | Neural | Adobe non-commercial / no licence file / NOASSERTION | No |

What changed since May: ARP 3.76 to 3.78 (Blender 5.2, Guess Facial, a fourth bind engine); three skinning add-ons
aimed at messy meshes; Easy Rigify appeared with a free licence; SkinTokens replaced UniRig; Rigify got no auto-fit;
Mixamo degraded; Unity Muse gone.

## 4. What this means for HIHO Studio (design direction, David decides)

**Engine: keep.** Fixed 63-bone rig fitted to markers, voxel or automatic skinning. Two engine upgrades worth a build
each, both free and CPU-only: (a) **finger bones on the auto-rig** (the mocap side now captures fingers; the rig has
none), via ARP's own trick in reverse: no finger markers, find the five tips as the farthest points of each hand's
silhouette, with a finger-count field; (b) **a "Guess Markers" button** using our own 2D tracker on a front + side
viewport render, editable before Go, so a student places zero markers on a clean character.

**Interface: copy ARP's sequence, in HIHO words.** Studio today: Import Character, Add Markers (13), Mirror, Auto-Rig,
Skinning mode, Send to Character. Proposed order for ART 175:
1. **Bring in your character** (normalizes silently: centre, face -Y, apply transforms, unit scale check; refuses with
   a plain sentence if two rigs exist or the mesh is empty).
2. **Where are the joints?** Guess (one click) or place; mirrored by default; one side only; a count of what is left.
   Fingers: a separate optional line, "spread your fingers, palms down", count field.
3. **Preview the skeleton** over the mesh (a quick pose test, like AccuRIG's Check Animation) before any weights.
4. **Bind**, one button, engine chosen for the student (Voxel if the character has several pieces, Automatic if one),
   with three or four named checkboxes, default on (Split Parts, Fix Scale, Smooth Twist, Improve Hips).
5. **Put the motion on it** (Send to Character, unchanged).
Plus the second door from `APOSE_REST_DESIGN_2026-10-15.md` section 5: model around the shipped A-pose rig, bind, done.

**The messy-mesh list every tool fails on, for the Studio handout:** unapplied scale or rotation; a posed or
asymmetric character; many loose pieces; non-manifold geometry and doubled verts; hidden inner geometry; props and
clothes in the body selection; arms crossing the body; fingers not spread.

## 5. Next steps (each its own doc then build, David's OK)

1. David runs ARP Smart by hand on the chibi (10 minutes) so we have a quality baseline against Studio, same bind engine.
2. Buy one Easy Rigify seat ($30) and read its detection code: the one free-licence tool shaped like ARP.
3. `STUDIO_FOR_STUDENTS_DESIGN_<date>.md`: the five-step sequence above, finger tips from the silhouette, Guess Markers
   from our own tracker, the blockout-rig door. Then builds, one change at a time, Dec/Jan before ART 175.

## 6. Questions for David

1. Study only, or is reusing GPL-3 code from ARP / Easy Rigify acceptable to him? (Recommendation: study only.)
2. Does Studio's auto-rig need fingers for ART 175, or is the blockout-rig door (63 bones, fingers for free) enough?
3. Is $30 for an Easy Rigify seat OK, purely to read it?
