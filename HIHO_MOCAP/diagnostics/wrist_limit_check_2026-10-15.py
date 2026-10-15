"""Wrist limit check (2026-10-15). Run INSIDE Blender with the HIHO MOCAP addon
installed (Text Editor > Run Script, or exec through the connector).

For a take, builds the rig in A-pose and in T-pose and, for each hand, measures
how far the hand bone points away from its own tracking target (wrist to
hand_middle) with the wrist Limit Rotation on and off, plus how many times the
hand's local Z axis flips (a jump of more than 120 degrees between frames).
Prints a table. Set TAKE below.
"""
import math
import os

import bpy
import mathutils

TAKE = os.path.expanduser("~/Desktop/HIHO_ALL/HIHO_CAPTURES/2026-09-19_16-06-36")
STEP = 2  # sample every Nth frame

addon = bpy.context.preferences.addons["bl_ext.user_default.hiho_mocap"]
prefs = addon.preferences
scene = bpy.context.scene


def run(pose_choice, use_limit):
    prefs.rest_pose = pose_choice
    bpy.ops.hiho_mocap.load_take(directory=TAKE)
    label = os.path.basename(TAKE)
    rig = [o for o in bpy.data.objects if o.type == 'ARMATURE' and label in o.name][0]
    rows = {}
    for side in ("R", "L"):
        pb = rig.pose.bones[f"hand.{side}"]
        target = [c for c in pb.constraints if c.type == 'DAMPED_TRACK'][0].target
        for c in pb.constraints:
            if c.type == 'LIMIT_ROTATION':
                c.influence = 1.0 if use_limit else 0.0
        errs, flips, prev_z = [], 0, None
        for f in range(scene.frame_start, scene.frame_end + 1, STEP):
            scene.frame_set(f)
            m = rig.matrix_world @ pb.matrix
            y = (m.to_3x3() @ mathutils.Vector((0, 1, 0))).normalized()
            z = (m.to_3x3() @ mathutils.Vector((0, 0, 1))).normalized()
            d = target.matrix_world.translation - m.translation
            if d.length > 1e-6:
                errs.append(math.degrees(y.angle(d.normalized())))
            if prev_z is not None and math.degrees(z.angle(prev_z)) > 120:
                flips += 1
            prev_z = z
        n = max(len(errs), 1)
        rows[side] = (100 * sum(e > 10 for e in errs) / n, max(errs), sum(errs) / n, flips)
    return rows


results = {}
for pose in ("APOSE", "TPOSE"):
    for lim in (True, False):
        results[(pose, lim)] = run(pose, lim)
prefs.rest_pose = "APOSE"
scene.frame_set(1)

print(f"\nWrist check on {os.path.basename(TAKE)} (every {STEP}th frame)")
print(f"{'pose':6s} {'limit':6s} {'hand':5s} {'>10deg':>7s} {'max':>6s} {'mean':>6s} {'flips':>6s}")
for (pose, lim), rows in results.items():
    for side, (pct, mx, mean, flips) in rows.items():
        print(f"{pose:6s} {'on' if lim else 'off':6s} {side:5s} {pct:6.1f}% {mx:6.1f} {mean:6.1f} {flips:6d}")
RESULTS = results
