# ActionForge study: what the new free "Mixamo killer" does, and what it means for the HIHO Studio section (2026-10-13)

**What this is.** Research only, written on the iMac (desktop = research, laptop = dev). No code was changed. David
sent the CGDive video "This new, free app is off the hook! (ActionForge)" (youtube.com/watch?v=Si1z4VAdi4A, posted
2026-10-12, 41K views in a day) and asked whether we can study its detection and binding functions and its UI, "thinking
ahead for next semester's mocap class", because he wants the Studio portion of the HIHO addon ready for student use.
That class is ART 175-02, Spring 2027 (`project_hiho_dma_class_goal.md`).

**Companion docs:** `AUTORIG_RESEARCH_2026-05-28.md` (the May research that chose markers + voxel skinning),
`STUDIO_SECTION_DESIGN_2026-07-01.md` (the design that was built), `DEV_LOG_STUDIO_SECTION_JULY2026.md` (how it was
built, 1.4.0 to 1.4.25), `PANEL_REDESIGN_DESIGN_2026-09-19.md` section 1 (why Studio left the student panel).

---

## 1. Bottom line

1. **We cannot study their code, and we should not try.** ActionForge is closed source: the page says "© CGstuff", no
   license is stated for the app itself, and the shipped scripts are deliberately obfuscated (string-array obfuscation,
   hex-indexed names). Reading it would be reverse engineering, it would take days, and anything learned could not be
   used cleanly in an AGPL project. The May research already found the open method behind this whole family of tools
   (Pinocchio 2007: fixed skeleton, fit to markers, heat skinning), and HIHO already built it.
2. **We can study everything else, and it is all legitimately reusable:** the UI flow (by using the app, which is free
   and needs no login), the third-party notices (which name the stack), the maker's own notes, and the CC0 animation
   library the app is built on (Quaternius).
3. **HIHO already has the equivalent feature.** The Studio section in 1.5.6 does Import Character, 13 markers, mirror,
   Auto-Rig (23 ajc27-named bones), voxel or automatic skinning, Send to Character, Load Take, Play, and Bake + Export.
   The whole pipeline ran end to end on David's chibi on 2026-07-01 (build 1.4.8). It is hidden behind the "Studio tools"
   checkbox since 2026-09-19 because David said it "needs the time to do the design and testing", not because it is
   broken.
4. **So the real question is not "how do we copy ActionForge" but "what does ActionForge do that a student would miss
   in ours, and what does ours need before Spring."** Section 5 is that list. Section 6 is the proposed path.

---

## 2. What ActionForge is (facts, checked 2026-10-13)

- **Maker:** CGstuff (Hassan Charafeddine, cgstuff.xyz, YouTube @cgstuff87). One person, labeled **Beta**.
- **Where it runs:** in the browser at actionforge.app, free, no login, no install. The character panel says: "Your
  characters are read and kept in this browser only — never uploaded." So the rigging is computed on the student's
  machine, in JavaScript. The maker says "a future offline version is in the works" (cached desktop copy), and that
  project saving is "experimental, and I might drop it later".
- **Stack (from its THIRD-PARTY-NOTICES.txt):** three.js 0.165 (MIT), @comfyorg/fbx-exporter-three (MIT), fflate (MIT),
  webm-muxer (MIT), @mediapipe/tasks-vision 1.0.1 + the MediaPipe Hand Landmarker model (Apache 2.0). **No ML rigging
  model is shipped** (no ONNX, no TensorFlow, no UniRig-style weights). The auto-rig is therefore geometric, marker
  driven, in the Pinocchio family: the same family as ours. The hand landmarker is almost certainly for webcam hand
  posing, not for rigging.
- **Content:** the default rig and all 85 clips are by Quaternius, CC0, "from the free versions of his Universal
  Animation Library packs" (ActionForge's notices; verify on quaternius.com before we ship anything).
- **Licensing of the app:** not open source. App and code "© CGstuff". Only the animations are CC0.
- **Known bug the maker acknowledged under the video:** "The flipped legs on auto-rig are noted." Our fitter solved
  exactly this class of problem in July (depth centering 1.4.3, forward-facing detection in `core/marker_fit.py`).

## 3. The UI, as a student would meet it

Left rail, nine tabs: **Character, Camera, Compose, Adjust, Props, IK, Pose, Import, Projects.** Right rail: the clip
library (85 clips, search by name or tag, tick several) and the export block. Bottom: a timeline with Sec/Strips views,
undo/redo, speed 0.25x to 2x, Loop, Auto-key, Bones, Wireframe, Follow, Mirror, Reverse, Origin, In Place (X/Y/Z/Yaw),
Reframe. A "Motion Lab" page reshapes one clip's curves and generates 8-direction locomotion sets.

**The Character tab is the part that matters to us. It offers three doors:**

| Door | Their words | What it means |
|---|---|---|
| Mannequin | (default) | Quaternius rig, plays every clip. |
| + Rigged character | "Keeps its own skeleton." | Bring a Mixamo / UE / Reallusion-rigged file; they retarget the clips onto it. Maker's tip: download Mixamo clips on Y Bot or X Bot, other Mixamo characters have "small bone differences that can break the import". |
| + Unrigged model | "Rigged here, in the browser." | Their auto-rig. From the video's "Character Rigging" chapter (0:42 to 4:41) and the fragments of UI text visible in the bundle: upload in A or T pose, a **marker editor** where you "pick a joint" and place it, **mirror left to right**, a "Hips & spine" step, and a parts step where separate pieces are classed as **cloth, held (props), or alone (detached pieces)** before weights are computed ("Automatic Weights" appears in the UI text). A viewer asked whether props and cloth are "already separate meshes in the model" or picked out smartly; from the text they are separate meshes the user labels. |
| Make a character on our skeleton | (link) | A fourth, quiet door: model your character around their skeleton, so there is nothing to fit at all. |

**Export block:** current clip or all; Include character mesh; In place; One file per clip (.zip); Format GLB or FBX;
Units Blender / Unreal / Unity; **Skeleton: Default, Unreal Engine 5, Unreal Engine 4, Reallusion (CC / ActorCore),
Mixamo**; "Character only (rest pose)".

The maker's own post-release notes (pinned under the video): set In Place in the toolbar first; Motion Lab motion trails
are buggy, use the curve editor; saving is experimental; offline version coming.

## 4. Where HIHO Studio stands today (1.5.6, from the docs, not re-tested today)

Panel `panel/studio_panel.py`, visible only with the "Studio tools" preference ticked:

1. **Choose Take**: Load Take (any processed HIHO take folder), path box.
2. **Preview**: Play.
3. **Character**: Import Character (.fbx / .obj, into its own collection), Add Markers (13: head, shoulders, elbows,
   wrists, hips, knees, ankles, plain names, template scaled to the character), Mirror Left to Right / Right to Left
   (X or Y axis), Skinning: Voxel (vendored MIT solver, universal binary, multi-piece safe) or Automatic, **Auto-Rig**
   (23 ajc27-named body bones fitted to the markers; depth centering; neck found by silhouette pinch; idempotent re-run),
   character target picker, **Send to Character** (the live ajc27 constraint table drives the new rig from the 33 mocap
   empties).
4. Diagnostics: Map the Volume, Spawn Empties (debug).

Bake Animation + Save Out (FBX / GLB / .blend, refuses an unbaked rig) are step 6 of the main panel and work on any rig.

**On record as unfinished or untested:**
- No finger bones on the auto-rig (fingers are skipped by the missing-bone handling), while the mocap side now captures
  fingers (bug #4, finger blow-up, is the next build). A mocapped hand on a student character has nothing to drive.
- The head-bone layout David designed live (1.4.6, one skull-spanning bone) was reverted for schedule (1.4.7) and is
  "a post-July-7 candidate". Still open.
- Import Character refuses files that already carry a rig (one rig at a time). There is no "keeps its own skeleton"
  door; the Rigify-name binder (`operators/bind.py`) is retired.
- No starter clips: a student with no take of their own has nothing to play on a freshly rigged character.
- No student has run the Studio pipeline in any session I can find in the docs; every live test was David's own chibi.
- Lock Feet lives in Cleanup, judged "a good start" on MediaPipe data only, never checked on RTMPose takes.

## 5. What ActionForge does that a student would miss in ours (ranked by value to ART 175)

| # | ActionForge has | HIHO has | Gap | Size |
|---|---|---|---|---|
| 1 | 85 CC0 clips on a shared skeleton: any character plays any clip the moment it is rigged. | Load Take = your own HIHO recordings only. | **A starter library.** Retarget the free Quaternius CC0 clips onto the ajc27 skelly once, ship them as HIHO takes. A student can test a rig before they have recorded anything, and a sick day does not stall them. CC0 is AGPL-safe. Needs `core/rotation_retarget.py` or a one-time Blender script, not new theory. | Medium |
| 2 | "Rigged character: keeps its own skeleton." Mixamo / UE / Reallusion rigs retargeted. | Refuses pre-rigged files. | **A second door for the many students who already have a Mixamo-rigged character.** Bind the existing armature with the constraint table, translated to Mixamo names (`mixamorig:Hips`...). The May BIND_TO_RIG design already did this for Rigify names; add a Mixamo column. | Medium |
| 3 | Parts step: cloth / held prop / detached piece, labeled before weights. | Voxel skinner handles detached pieces well; props get heat-skinned like skin. | **A "Prop" tag**: a held sword or a hat should bind rigidly to one bone (nearest hand or head), not be soft-weighted. One checkbox per piece, one vertex group. | Small |
| 4 | Skeleton export presets (Default / UE5 / UE4 / Reallusion / Mixamo). | FBX / GLB with ajc27 names. | **Rename-on-export** to Mixamo naming for Unity / Godot / Unreal students. A name table, applied to a copy at Save Out. | Small |
| 5 | "Make a character on our skeleton." | Nothing. | **Ship the skelly as a reference .blend for ART 102 / 175**: model around it in A-pose and the markers land by themselves. Zero-fit path, pure teaching material. | Small |
| 6 | Marker editor with mirror, "pick a joint" prompts. | 13 named markers, mirror both ways, labels in the viewport. | Parity. Ours is arguably better (depth centering, pinch-found neck, idempotent). Keep. | None |
| 7 | "Never uploaded" line in the panel. | Offline by construction. | Say it in the panel, one label. Students worry about this (the top comment under the video is about exactly that). | Tiny |
| 8 | In Place / root motion, IK posing, Motion Lab curve editor, 8-direction locomotion, procedural animation. | Blender itself (NLA, IK, graph editor). | Not Studio-section work. Teach these in Blender. Revisit after Spring. | Skip |
| 9 | Webcam hand posing (MediaPipe Hand Landmarker). | Hands come from the mocap. | Skip. | Skip |

Where **HIHO is ahead**: the capture itself (ActionForge has no mocap at all; it is a library player), multi-piece
voxel skinning (their "Automatic Weights" is the surface kind Blender has), the flipped-legs class of bug (solved),
offline and open source today (theirs is "coming"), and a Bake + Export that refuses to ship a T-pose by mistake.

## 6. Proposed path to "Studio ready for ART 175" (research first, then design, then laptop builds)

**Nothing here is a decision. David picks; one change at a time; code on the laptop only.**

1. **Test what exists before adding anything (this semester, David's hands, laptop).** Run the current Studio pipeline
   on two or three real student-style characters, not the chibi. The ART 102 A2 blockouts (due Sun 10/18) are the ideal
   test set, with the students' permission. Log each run in the take-log style: his words, what broke. This is the
   "design and testing" he named on 09-19, and it decides the list below better than any research can.
2. **Decide the two scope questions that shape the design doc:**
   a. Does the Spring class rig its own characters (the Unrigged door), bring Mixamo-rigged ones (the Rigged door), or
      both? Both is the honest answer for a 24-student class; it is also twice the surface.
   b. Fingers on the auto-rig: yes (match the mocap side) or no (body only in Spring)?
3. **Write `STUDIO_FOR_STUDENTS_DESIGN_<date>.md`** covering, in the order a student meets them: the door choice; the
   Prop tag; the starter clip library; export naming; the panel promotion (Studio stops being a hidden checkbox and
   becomes step 7, "Your Character", with the same hover-text discipline as the 09-19 redesign); and the head-bone
   question, settled by David's eye.
4. **Build in December / January, one zip per change**, with headless tests plus his live check, like July. Spring
   classes start late January; the kit moves to Art 141 for the class.
5. **ActionForge in the classroom:** fine as a comparison demo ("this is what a Mixamo-style tool does; now watch yours
   do it offline, with your own motion"). Not a dependency: it is online-only today, beta, closed, and one person's
   project.

## 7. Things to keep in mind

- **Do not decompile.** The bundle's obfuscation is the maker's choice; respect it. Nothing in HIHO may derive from it.
- **Quaternius CC0 is the one piece of their stack worth taking**, and it is not theirs; it is Quaternius's gift to
  everyone. Check the exact pack and license on quaternius.com before shipping clips.
- The "detection" David asked about (where the joints are) is done by the user in ActionForge, same as ours. The
  "binding" (weights) is their own JavaScript heat-style solver; ours is the MIT voxel solver, which is the stronger of
  the two on multi-piece student meshes by David's own hands-on judgment (May) and the July smoke test.
- Open question for a later research pass (carried from May, still unanswered): do the 2025 learned riggers (UniRig,
  RigAnything, Make-It-Animatable) offer a fixed-skeleton mode we could call offline for the "no markers at all" path?
  UniRig is MIT with skeleton + skinning checkpoints released; it needs PyTorch and a GPU-class machine, which cuts
  against "runs on old machines". Not for Spring.

## Sources

- The video: https://www.youtube.com/watch?v=Si1z4VAdi4A (CGDive, 2026-10-12; chapters: Intro 0:00, Character Rigging
  0:42, Posing & Animation 4:41, Project Save/Load 12:43, Procedural Animation 13:27, Auto Locomotion Sets 15:43)
- The app: https://actionforge.app/ · notices: https://actionforge.app/THIRD-PARTY-NOTICES.txt · Motion Lab:
  https://actionforge.app/motion-lab.html
- Maker: https://cgstuff.xyz · https://www.youtube.com/@cgstuff87 · their rigging video
  https://www.youtube.com/watch?v=p779LRtmuYo ("Rig and Animate Your Own Character in the Browser for Free")
- Quaternius (CC0 rig + clips): https://quaternius.com/
- UniRig (MIT): https://github.com/VAST-AI-Research/UniRig · RigAnything: https://github.com/Isabella98Liu/RigAnything
- Our own prior art: Pinocchio (Baran & Popović 2007), in `AUTORIG_RESEARCH_2026-05-28.md`
