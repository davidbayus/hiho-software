"""Terminal check for the 1.5.7 finger-length fix (FINGER_LENGTH_FIX_DESIGN_2026-10-04.md).

Runs the real core/enforce_rigid_bodies.py on a take's landmark files (system python3,
no Blender) and prints the index fingertip length the rig would get, per hand.
Run:  python3 finger_length_check_2026-10-15.py <take name> [<take name> ...]
"""
import importlib.util
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.join(os.path.dirname(HERE), "core")
ROOT = os.path.expanduser("~/Desktop/HIHO_ALL/HIHO_CAPTURES")


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(CORE, name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


erb = load("enforce_rigid_bodies")
topo = load("topology")

HAND = [
    "wrist", "thumb_cmc", "thumb_mcp", "thumb_ip", "thumb_tip",
    "index_finger_mcp", "index_finger_pip", "index_finger_dip", "index_finger_tip",
    "middle_finger_mcp", "middle_finger_pip", "middle_finger_dip", "middle_finger_tip",
    "ring_finger_mcp", "ring_finger_pip", "ring_finger_dip", "ring_finger_tip",
    "pinky_mcp", "pinky_pip", "pinky_dip", "pinky_tip",
]
BODY = {"left_elbow": 13, "right_elbow": 14, "left_wrist": 15, "right_wrist": 16}

for take in sys.argv[1:]:
    out = os.path.join(ROOT, take, "output_data")
    body = np.load(os.path.join(out, "mediapipe_body_3d_xyz.npy")) / 1000.0
    pos = {k: body[:, i].astype(np.float64) for k, i in BODY.items()}
    for side, fname in (("right", "right"), ("left", "left")):
        hand = np.load(os.path.join(out, f"mediapipe_{fname}_hand_3d_xyz.npy")) / 1000.0
        for i, n in enumerate(HAND):
            pos[f"{side}_hand_{n}"] = hand[:, i].astype(np.float64)
    bones = {b: ht for b, ht in topo.BONE_HEAD_TAIL_MAP.items()
             if ht[0] in pos and ht[1] in pos}
    print(f"== {take}")
    fixed = erb.enforce_rigid_bodies(pos, bones)
    for bone in ("f_index.03", "thumb.03", "palm.01"):
        row = []
        for side in ("R", "L"):
            h, t = bones[f"{bone}.{side}"]
            L = np.linalg.norm(fixed[t] - fixed[h], axis=1)
            row.append(f"{side} {np.nanmedian(L) * 1000:5.1f} mm")
        print(f"   {bone:11s} {'   '.join(row)}")
