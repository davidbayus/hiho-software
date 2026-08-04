# Bake Animation — Design Note (2026-07-02, evening debrief)

**Status: DESIGN — David's ask from the Day-2 debrief. Open choices at bottom; code after he answers.**

**The ask (David, verbatim intent):** "we need to create a new bake animation button... so the bones carry the keyframes. Then I can try manual cleanup and also play with the natural framerate." Lineage: PPParty V2 auto-pushed recorded Actions to NLA ([[project_v2_nla_push_recording]]); HIHO MOCAP's Export section is still a stub; the program deliverable has always been baked animation ([[project_ppparty_deliverable_is_baked_animation]]).

**Why it's needed:** both HIHO rigs animate through live constraints (skelly bones follow empties; auto-rigged characters COPY_ROTATION from the skelly). Constraint-driven motion has no editable keyframes — no graph-editor cleanup, no retiming, no clean FBX. Baking samples the final visual pose each frame and writes real keyframes onto the bones.

**Design:**
- **"Bake Animation" button** in the Export section (above Save Out — Save Out ultimately needs a baked rig anyway; later Save Out can auto-bake if unbaked).
- Operates on the active/selected armature (skelly or character — same mechanism).
- Mechanics: `bpy.ops.nla.bake` (or manual visual-keying sample loop if operator context fights us) over the scene frame range, visual keying ON, one key per frame at the take's native rate.
- **After baking, strip the animation constraints** on baked bones so the keyframes own the motion (this is what "bones carry the keyframes" means). The driving empties stay in the file but get hidden — never deleted. A baked rig is fully portable.
- Frame rate: v1 bakes 1:1 at the take's rate (60fps take = 60 keys/sec). David wants to hand-play with retiming (his filmic-24 conform lands in AE per current plan); a "resample to 24" bake option is a v2 candidate if manual retime proves painful.
- Report what happened: "Baked N bones × M frames; constraints removed; empties hidden."

**Undo safety:** single undo step (operator-standard). The unbaked state is also always recoverable by Load Take → Spawn Rig again.

**Choices — LOCKED by David (2026-07-02 evening debrief):**
1. Bake target: **whatever is selected** (skelly or character; button greys out unless an armature is active).
2. Post-bake: **strip constraints + hide empties** (never deleted; Load Take + Spawn Rig rebuilds the live rig anytime).

**Test plan (the user's path):** panel button on today's take (14-10-31): bake skelly → scrub with empties hidden → graph editor shows fcurves per bone → export FBX → reimport in a fresh file plays identically. Version 1.4.16 or .17 depending on order vs the Load-Take-fps fix (`LOAD_TAKE_FPS_DESIGN_2026-07-02.md`).

---

# Addendum — Quaternion continuity pass (2026-08-04, build 1.4.33)

**Status: DESIGN LOCKED — David's go 2026-08-04 ("first thing next session"). Root cause,
measurement, and validation: `Z_JITTER_DIAGNOSIS_2026-08-04.md`.**

The bake derives each frame's rotation independently (matrix decomposition always returns
the w-positive spelling), so any bone turning past 180° silently flips between the two
spellings of the same pose. Invisible when scrubbing — catastrophic under smoothing, which
averages +q against -q and swings the root.

**Chosen shape — the diagnosis doc's recommendation, shape 1: a continuity pass over the
newly written curves at the end of the bake.** The pass is the validated repair recurrence
ported 1:1 from `HIHO_quaternion_continuity_repair.py`: compare each frame against the
previous frame AS ALREADY CORRECTED, and negate whole keyframes (values and handles, never
frame numbers) on a hemisphere flip. Bake loop untouched; provably pose-neutral.

The report line grows one clause — "quaternion spelling: N keys re-spelled on M bones" or
"verified continuous" — so this class of silent failure stays visible either way.
