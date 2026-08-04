"""Scene clock from the recorder's sidecar.

The recorder writes HIHO_RECORDING_INFO.json (fps/width/height/...) into every
take folder (1.4.18). Whoever spawns motion into the scene calls this so the
take never plays at the wrong speed. Legacy takes have no sidecar: warn
loudly, never guess silently. Single source of truth for both student paths
(Record→Process→Spawn Rig and Load Take) — design:
SIDECAR_ON_SPAWN_DESIGN_2026-07-04.md.
"""

import json
import os


def set_scene_clock_from_take(scene, body_npy):
    """Set fps + frame range from the take's sidecar.

    body_npy is the processed output_data/*.npy path; the sidecar lives two
    levels up, in the take folder. Returns (message, is_warning). Idempotent —
    safe to call more than once for the same take.
    """
    recording_folder = os.path.dirname(os.path.dirname(body_npy))
    info_path = os.path.join(recording_folder, "HIHO_RECORDING_INFO.json")

    if not os.path.isfile(info_path):
        return ("Old take - no recording info; scene clock left alone. "
                "Set scene fps yourself (probably 30).", True)

    try:
        with open(info_path) as fh:
            fps = int(json.load(fh).get("fps", 0))
    except (OSError, ValueError):
        fps = 0
    if fps <= 0:
        return ("Take's recording info is unreadable - set scene fps "
                "yourself to match the take.", True)

    scene.render.fps = fps
    scene.render.fps_base = 1.0
    scene.frame_start = 1
    try:
        import numpy as np
        scene.frame_end = int(np.load(body_npy, mmap_mode="r").shape[0])
    except Exception:
        pass
    return (f"Scene clock set to {fps}fps to match the take.", False)
