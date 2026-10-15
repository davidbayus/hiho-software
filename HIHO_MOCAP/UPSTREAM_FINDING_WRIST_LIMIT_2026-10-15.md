# Upstream finding (draft for David's words): the hand Limit Rotation pulls the hand off its own target

*2026-10-15, laptop. DRAFT ONLY. Nothing posted. David rewrites in his voice before anything goes to
github.com/freemocap/freemocap_blender_addon (gratitude first, collaborator register). Facts below are measured; the
suggested wording at the end is provisional.*

## What we measured

Rig: the freemocap armature exactly as upstream main defines it (63 bones, `freemocap_tpose` and `freemocap_apose`,
`bone_constraints.py` targets and axes verbatim), built by HIHO MOCAP 1.5.8 on two six-camera takes (60 fps, RTMPose
through FreeMoCap 2.0 alpha.23). The `hand.R` / `hand.L` constraint stack is Damped Track to `hand_middle`, Locked Track
to `thumb_cmc`, then the Limit Rotation from `bone_constraints.py` (x -45..45, y -36..25, z -86..90 on the right, mirrored
on the left, local space).

Test: for every 2nd frame, the angle between the hand bone's Y axis and the direction from the wrist to its own Damped
Track target. With no limit the angle is 0 by construction. Script: `diagnostics/wrist_limit_check_2026-10-15.py`.

| Take | Rest pose | Limit | hand.R frames more than 10 degrees off | max | Z-axis flips | hand.L frames off | flips |
|---|---|---|---|---|---|---|---|
| clean, one performer, standing (09-19) | T | on | 43% | 101 | 0 | 45% | 0 |
| same | T | off | 0% | 0 | 0 | 0% | 0 |
| same | A | on | 64% | 102 | 0 | 68% | 0 |
| same | A | off | 0% | 0 | 0 | 0% | 0 |
| right hand badly tracked for half the take (10-02) | T | on | 58% | 135 | 16 | 85% | 0 |
| same | T | off | 0% | 0 | 21 | 0% | 2 |
| same | A | on | 85% | 135 | 8 | 96% | 0 |
| same | A | off | 0% | 0 | 21 | 0% | 2 |

Reading: on a clean take the limit only hurts (half the frames, up to 100 degrees off the data; the finger chains start at
the wrist and aim at their own markers, so the bare skeleton hides it, but a skinned palm twists). On the noisy take it
removes only some of the flips it exists for. The A-pose makes it worse because the limit is evaluated in the bone's local
frame and the A-pose wrist roll is 0 instead of -90, with the same limit table.

Upstream already ships this limit behind an opt-in ("Limit Hand Markers Range of Motion", off by default, PR #77), so the
default user never sees it. The finding matters for anyone who turns it on, and for the A-pose option.

## What HIHO did

1.5.9: the constraint is created at influence 0 (same bones, same stack, same values), so a user can raise it if a hand
flips. The real fix for flips is a per-frame hand cleanup, not a clamp (backlog).

## Provisional wording for the issue (David's rewrite)

Title: Hand Limit Rotation pulls hand.R/L off its Damped Track target (numbers on two takes, T and A pose)

Body: thanks first (the A-pose export option landed exactly when we needed it); what we measured, the table, the
script; the A-pose local-frame point; that we set influence 0 in our build and would gladly share the takes; a question:
would a per-pose limit table be the intended fix, or should the limit stay opt-in as it is?
