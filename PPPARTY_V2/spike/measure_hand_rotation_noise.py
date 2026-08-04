"""Measure hand-bone rotation noise on the most recent NLA strip.

Paste this script into Blender's Text Editor and click Run Script (or
press Alt+P) AFTER recording a take with hands held still in
PP_V2_Rig. Output prints to the System Console (Window menu →
Toggle System Console on Windows, or run Blender from a terminal on
macOS/Linux to see it).

What this measures: mean frame-to-frame quaternion delta (Δq) on
each hand bone class. Δq is the angle between consecutive-frame
rotations of a bone, in radians — small values = stable, large
values = jittery.

Reference baseline (pre-v2.0.1, day8d build):
  palm + thumb base : 0.08-0.10
  thumb tip (.03)   : 0.19
  finger tips (.03) : 0.30-0.44   <- THE KEY METRIC
  body bones        : 0.001-0.004 (300x lower than fingertips)

Decision tree (per HAND_SIDE_REF_DESIGN.md Measurement Protocol):
  finger.03 < 0.10 : Lever A was sufficient. Done with hand rotation
                     work. Move to next priority.
  finger.03 0.10-0.20 : Noticeable but tolerable for K-12 puppet
                        show. Document, defer Lever B/C, revisit if
                        classroom testing complains.
  finger.03 > 0.20 : Lever B (heavier tip One Euro filter on tip
                     landmarks specifically) is worth pursuing.
                     Open HAND_TIP_SMOOTHING_DESIGN.md, ship as
                     next patch.

Recording protocol:
  1. Open PPParty V2 N-panel
  2. Click "Start Body Mirror" — confirm hands tracked in viewport
  3. Click "Start Recording (Pass 1)"
  4. Hold both hands STILL in front of camera in a typical
     performance pose (palms forward, fingers slightly spread) for
     10 seconds. Don't gesture.
  5. Click "Stop Recording"
  6. Run THIS script
"""

import bpy
import math
import re

RIG_NAME = "PP_V2_Rig"

# ---------------------------------------------------------------------------
# Find rig + most recent NLA strip
# ---------------------------------------------------------------------------

rig = bpy.data.objects.get(RIG_NAME)
if rig is None:
    print(f"\nERROR: {RIG_NAME} not found in scene. Run 'Create V2 Rig' first.\n")
    raise SystemExit

if rig.animation_data is None:
    print(f"\nERROR: {RIG_NAME} has no animation_data. Record a take first.\n")
    raise SystemExit

strips = []
for track in rig.animation_data.nla_tracks:
    for strip in track.strips:
        if strip.action is not None:
            strips.append(strip)

if not strips:
    print(f"\nERROR: No NLA strips on {RIG_NAME}. Record a take first.\n")
    raise SystemExit

# Most recent = highest frame_end
latest = max(strips, key=lambda s: s.frame_end)
action = latest.action
print(f"\nUsing NLA strip: {latest.name!r}")
print(f"  Action: {action.name!r}")
print(f"  Frame range: {int(latest.frame_start)} - {int(latest.frame_end)}")

# ---------------------------------------------------------------------------
# Collect rotation_quaternion fcurves per bone
# (Blender 5.2+ Slotted Actions — fcurves live in channelbags)
# ---------------------------------------------------------------------------

bone_fcurves = {}  # bone_name -> {0: w_fc, 1: x_fc, 2: y_fc, 3: z_fc}

for layer in action.layers:
    for strip in layer.strips:
        if strip.type != "KEYFRAME":
            continue
        for bag in strip.channelbags:
            for fc in bag.fcurves:
                m = re.match(
                    r'pose\.bones\["([^"]+)"\]\.rotation_quaternion',
                    fc.data_path,
                )
                if not m:
                    continue
                bone_name = m.group(1)
                bone_fcurves.setdefault(bone_name, {})[fc.array_index] = fc

# ---------------------------------------------------------------------------
# Compute Δq per bone (mean of frame-to-frame quaternion-angle deltas)
# ---------------------------------------------------------------------------

def quaternion_delta_angle(q1, q2):
    """Angle between two unit quaternions in radians, shortest-arc."""
    dot = q1[0] * q2[0] + q1[1] * q2[1] + q1[2] * q2[2] + q1[3] * q2[3]
    dot = max(-1.0, min(1.0, abs(dot)))
    return 2.0 * math.acos(dot)

bone_deltas = {}  # bone_name -> mean Δq

for bone_name, fcs in bone_fcurves.items():
    if len(fcs) < 4:
        continue  # need W, X, Y, Z all present
    times = sorted({int(kp.co.x) for kp in fcs[0].keyframe_points})
    if len(times) < 2:
        continue
    deltas = []
    for i in range(len(times) - 1):
        t1, t2 = times[i], times[i + 1]
        q1 = (fcs[0].evaluate(t1), fcs[1].evaluate(t1),
              fcs[2].evaluate(t1), fcs[3].evaluate(t1))
        q2 = (fcs[0].evaluate(t2), fcs[1].evaluate(t2),
              fcs[2].evaluate(t2), fcs[3].evaluate(t2))
        deltas.append(quaternion_delta_angle(q1, q2))
    if deltas:
        bone_deltas[bone_name] = sum(deltas) / len(deltas)

# ---------------------------------------------------------------------------
# Aggregate by bone class + print results
# ---------------------------------------------------------------------------

CLASSES = [
    ("palm.*",       lambda n: n.startswith("palm.")),
    ("f_thumb.01",   lambda n: n.startswith("f_thumb.01.")),
    ("f_thumb.02",   lambda n: n.startswith("f_thumb.02.")),
    ("f_thumb.03",   lambda n: n.startswith("f_thumb.03.")),
    ("f_*.01 (avg)", lambda n: any(n.startswith(f"f_{f}.01.")
                                   for f in ("index", "middle", "ring", "pinky"))),
    ("f_*.02 (avg)", lambda n: any(n.startswith(f"f_{f}.02.")
                                   for f in ("index", "middle", "ring", "pinky"))),
    ("f_*.03 (avg)", lambda n: any(n.startswith(f"f_{f}.03.")
                                   for f in ("index", "middle", "ring", "pinky"))),
    # Reference body bones for comparison
    ("pelvis/chest", lambda n: n in ("pelvis", "chest")),
    ("upper_arm",    lambda n: n.startswith("upper_arm.")),
    ("lower_arm",    lambda n: n.startswith("lower_arm.")),
]

print("\n=== Hand Bone Rotation Noise (mean frame-to-frame Δq, radians) ===")
print(f"\n{'Class':<18} {'Mean Δq':<12} {'# bones':<10}")
print("-" * 42)

key_finger_03 = None  # capture the f_*.03 average for the decision

for class_name, predicate in CLASSES:
    matching_vals = [d for n, d in bone_deltas.items() if predicate(n)]
    if matching_vals:
        mean_d = sum(matching_vals) / len(matching_vals)
        marker = " <-- KEY METRIC" if class_name == "f_*.03 (avg)" else ""
        print(f"{class_name:<18} {mean_d:<12.4f} {len(matching_vals):<10}{marker}")
        if class_name == "f_*.03 (avg)":
            key_finger_03 = mean_d

# ---------------------------------------------------------------------------
# Decision tree
# ---------------------------------------------------------------------------

print("\n=== Reference Baseline (pre-v2.0.1, day8d) ===")
print("  palm + thumb base : 0.08-0.10")
print("  thumb tip (.03)   : 0.19")
print("  finger tips (.03) : 0.30-0.44   <-- the build to beat")
print("  body bones        : 0.001-0.004")

print("\n=== Decision (per HAND_SIDE_REF_DESIGN.md Measurement Protocol) ===")
if key_finger_03 is None:
    print("  Could not compute f_*.03 average — no finger-tip bones found in")
    print("  the strip. Was a recording made AFTER installing v2.0.1+?")
elif key_finger_03 < 0.10:
    print(f"  f_*.03 = {key_finger_03:.4f}  <  0.10")
    print("  -> Lever A was sufficient. Done with hand rotation work.")
    print("     Move to next priority (foot drive empirical test, hip+foot")
    print("     research already done, Lower Body Pass scoping done).")
elif key_finger_03 < 0.20:
    print(f"  f_*.03 = {key_finger_03:.4f}  in [0.10, 0.20)")
    print("  -> Noticeable but tolerable for K-12 puppet show.")
    print("     Document, defer Lever B/C. Revisit if classroom testing")
    print("     surfaces complaints about fingertip jitter.")
else:
    print(f"  f_*.03 = {key_finger_03:.4f}  >=  0.20")
    print("  -> Lever B is worth pursuing. Open HAND_TIP_SMOOTHING_DESIGN.md,")
    print("     ship as next patch (heavier One Euro min_cutoff/beta on tip")
    print("     landmarks 4/8/12/16/20 in mediapipe_sender.py make_hand_filters).")

print()
