# ajc27 Parity Roadmap — "our own version of everything ajc27 does" (2026-06-06)

**Direction (David, 2026-06-06):** HIHO MOCAP is a **clean-room re-implementation** that emulates the full ajc27 / FreeMoCap Blender output. ajc27 is a **reference template, not a dependency** — we do not bundle or call it. "Nothing in that code is special; it's a good template to emulate."

**This SUPERSEDES the 2026-05-27/28 "thin wrapper around bundled ajc27" architecture.** See `project_hiho_mocap_wrapper_architecture.md` (now marked reversed). The wheel-less 1.3.x build already dropped the ajc27 bundle, so the code already matches this direction.

**Discipline:** emulate ajc27's behavior/math faithfully and verify against it. Re-implementing re-introduces the "did we match it?" surface — the 2026-06-06 wrist-flip (we'd dropped ajc27's hand LIMIT_ROTATION) is the cautionary tale; the video planes (trivial) are the easy case. Verify each port against an ajc27-exported `.blend` or the live ajc27 addon.

## Parity table

| ajc27 output | ajc27 template (under `ajc27_freemocap_blender_addon/`) | HIHO status |
|---|---|---|
| Tracked-point empties | `empties/creation/create_freemocap_empties.py` | ✅ `core/output_rig.py` |
| Virtual trajectories | `freemocap_data_handler/.../put_skeleton_on_ground.py` | ✅ `core/loader.py` + `virtual_landmarks.py` |
| Armature / skelly | `core_functions/create_rig/create_rig.py` | ✅ `core/build_rig.py` |
| Bone constraints | `data_models/bones/bone_constraints.py` | ✅ `core/bind_to_rig.py` (+ wrist LIMIT_ROTATION 2026-06-06) |
| enforce_rigid_bodies | (ajc27 data handler) | ✅ `core/enforce_rigid_bodies.py` |
| **Capture video planes** | `core_functions/load_videos/load_videos.py` | ✅ `core/video_planes.py` (1.3.3) — **row layout only** |
| **Capture cameras** (objects at calibration positions) | `core_functions/add_capture_cameras/add_capture_cameras.py` | ❌ TODO — enables camera-accurate video-plane placement |
| **Skelly mesh** (the body mesh on the rig) | `core_functions/meshes/skelly_mesh/attach_skelly_mesh.py` | ❌ TODO |
| **Rigid-body meshes** (bone-segment "puppet" meshes) | `core_functions/meshes/rigid_body_meshes/attach_rigid_body_meshes_to_rig.py` | ❌ TODO |
| **Ground plane** | `setup_scene/scene_objects/ground_plane/create_ground_plane.py` | ❌ TODO |
| **Center of mass** (mesh + trails) | `core_functions/meshes/center_of_mass/center_of_mass_mesh.py` + `center_of_mass_trails.py` | ❌ TODO (Science-ish) |
| Scene objects (lighting/world) | `setup_scene/scene_objects/create_scene_objects.py` | ❌ TODO (Blender default for now) |
| Parent-empty hierarchy (tidy outliner) | `setup_scene/make_parent_empties.py` | ❌ TODO (organizational) |
| Joint/bone angles (biomechanics data) | `core_functions/create_rig/save_bone_and_joint_angles_from_rig.py` | ❌ TODO (Science Mode) |

## Recommended build order (art-first, Science Mode last)

HIHO's purpose is storytelling/animation, so prioritize what makes the result look like a character on a stage, then the science overlays.

1. **Capture cameras + camera-accurate video-plane placement.** Port `add_capture_cameras` (read the calibration TOML extrinsics → place camera objects), then position each video plane at its camera. Completes the video work; gives the reference's "frustum" look. *Needs calibration parsing.*
2. **Ground plane.** Cheap, high grounding value.
3. **Skelly mesh.** The visible body — biggest "it's a figure, not sticks" win.
4. **Rigid-body meshes.** The bone-segment puppet look (the BUGS_AND_BACKLOG "bone-mesh cones").
5. **Parent-empty hierarchy.** Tidy outliner (Data/Empties/Videos parents) — pairs with the existing "tidy" idea.
6. **Scene objects (lighting/world).** Polish.
7. **Center of mass (mesh + trails)** and **joint angles** — Science Mode, behind a toggle (per the original wrapper-doc Science Mode plan). Lowest priority for art use.

## Notes
- Each item = one clean-room module under `core/` + (where user-triggered) an operator + panel button, then verify against ajc27.
- Several extras (skelly mesh, rigid-body meshes, COM) are exactly the "FreeMoCap raw clutter" the BUGS_AND_BACKLOG "Tidy" idea wanted to HIDE. Reconcile: make them opt-in toggles, off by default for a clean student view, on for full-reference parity. Decide per item.
- "Add Camera Videos" today loads planes flat in a row; item 1 upgrades placement.
