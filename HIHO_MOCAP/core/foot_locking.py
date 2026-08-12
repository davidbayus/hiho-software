"""Foot locking — hold each foot still while it is planted on the floor.

Port of the foot-locking operator from ajc27's freemocap_blender_addon
(AGPL-3.0, kept for reference in vendor/), rewritten for HIHO's own
hiho_* empties and slotted actions. Algorithm is 1:1 — contact windows by
height threshold, quadratic ease in/out, below-ground clamp for short
contacts, ankle re-solve against the take's own median bone lengths,
knee/hip compensation, upper-body steadying. Deliberate deviations
(keyframe-index space, fps-scaled defaults handled by the caller, dead
lock_xy switch dropped, missing markers skipped, set-based upper body,
exact cubic ankle solve where upstream's gradient descent under-steps):
FOOT_LOCKING_DESIGN_2026-08-11.md.

Pure numpy — no bpy. Arrays are modified in place; the operator owns all
Blender I/O.
"""

import math

import numpy as np

FOOT_MARKERS = {
    "left": {
        "base": ["left_foot_index", "left_heel"],
        "ankle": "left_ankle",
        "compensation": ["left_knee", "left_hip"],
    },
    "right": {
        "base": ["right_foot_index", "right_heel"],
        "ankle": "right_ankle",
        "compensation": ["right_knee", "right_hip"],
    },
}

# Everything the upper-body steadying pass moves: all markers EXCEPT the
# leg chains and hips_center (hips_center is set directly, the legs were
# already paid their share via the compensation coefficient). Same member
# set as ajc27's trunk_center-down hierarchy recursion, without the
# KeyError on untracked children.
_LOWER_BODY = {
    f"{side}_{part}"
    for side in ("left", "right")
    for part in ("hip", "knee", "ankle", "heel", "foot_index")
} | {"hips_center"}


def _runs_below(z, threshold):
    """Maximal consecutive runs where z < threshold, as (start, stop) pairs."""
    mask = (z < threshold).astype(np.int8)
    edges = np.flatnonzero(np.diff(np.concatenate(([0], mask, [0]))))
    return list(zip(edges[0::2], edges[1::2]))


def _ease_values(count, y_from, y_to):
    """The ajc27 quadratic ease: passes 3/4 of the way to y_to by midpoint."""
    if count <= 0:
        return np.empty(0)
    if count == 1:
        return np.array([y_to], dtype=float)
    if count == 2:
        return np.array([y_from, y_to], dtype=float)
    xs = np.array([0.0, count / 2.0, count - 1.0])
    ys = np.array([y_from, y_from + (y_to - y_from) * 0.75, y_to])
    a, b, c = np.linalg.solve(np.stack([xs**2, xs, np.ones(3)], axis=1), ys)
    t = np.arange(count, dtype=float)
    return a * t**2 + b * t + c


def _solve_ankle_z(current_z, ankle_xy, toe, heel, len_toe, len_heel):
    """Exact ankle height minimizing both foot-bone length violations.

    The ajc27 original runs gradient descent here (lr 1e-4, tol 1e-7); on
    real takes the quartic's gradients are so small that GD never leaves
    its initial guess of foot-height + 0.1 m, which lifts the ankle ~1.5 cm
    on every plant frame (measured on the 2026-08-01 perimeter walk —
    design doc, deviation g). The objective
        f(z) = (|ankle-toe|^2 - len_toe^2)^2 + (|ankle-heel|^2 - len_heel^2)^2
    has f'(z)/4 cubic in z, so we solve it exactly and keep the physical
    root (above the foot) nearest the ankle's current height.
    """
    ht2 = (ankle_xy[0] - toe[0]) ** 2 + (ankle_xy[1] - toe[1]) ** 2
    hh2 = (ankle_xy[0] - heel[0]) ** 2 + (ankle_xy[1] - heel[1]) ** 2
    at = ht2 - len_toe**2
    ah = hh2 - len_heel**2
    zt, zh = float(toe[2]), float(heel[2])
    roots = np.roots([
        2.0,
        -3.0 * (zt + zh),
        3.0 * (zt * zt + zh * zh) + at + ah,
        -(zt**3 + zh**3 + at * zt + ah * zh),
    ])
    real = roots[np.abs(roots.imag) < 1e-9].real
    cand = real[real >= max(zt, zh)]
    if cand.size == 0:
        cand = real if real.size else np.array([current_z])
    return float(cand[np.argmin(np.abs(cand - current_z))])


def lock_feet(
    markers,
    *,
    z_threshold=0.02,
    ground_level=0.0,
    frame_window_min_size=10,
    initial_attenuation_count=5,
    final_attenuation_count=5,
    knee_hip_compensation_coefficient=1.0,
    compensate_upper_body=True,
    target_feet=("left", "right"),
):
    """Lock planted feet in place. markers: {name: (3, N) array}, edited in place.

    Returns a stats dict; 'modified_markers' says exactly which arrays the
    caller must write back to Blender.
    """
    stats = {
        "windows": {},
        "planted_frames": 0,
        "clamped_frames": 0,
        "ankle_adjusted": 0,
        "body_frames": 0,
        "skipped_feet": [],
        "modified_markers": set(),
    }

    overall_changed = set()

    for side in target_feet:
        spec = FOOT_MARKERS[side]
        needed = spec["base"] + [spec["ankle"]]
        if any(m not in markers for m in needed):
            stats["skipped_feet"].append(side)
            continue

        ankle = markers[spec["ankle"]]
        toe = markers[spec["base"][0]]
        heel = markers[spec["base"][1]]

        # The take's own truth about this foot, measured before locking.
        len_toe = float(np.median(np.linalg.norm(ankle - toe, axis=0)))
        len_heel = float(np.median(np.linalg.norm(ankle - heel, axis=0)))

        changed = set()
        windows = 0

        for base_name in spec["base"]:
            z = markers[base_name][2]
            for start, stop in _runs_below(z, z_threshold):
                length = stop - start
                if length < frame_window_min_size:
                    # Too brief to be a plant — just keep it above the floor.
                    below = np.flatnonzero(z[start:stop] < ground_level) + start
                    if below.size:
                        z[below] = ground_level
                        changed.update(int(f) for f in below)
                        stats["clamped_frames"] += below.size
                    continue

                init_n = min(initial_attenuation_count, length)
                final_n = min(final_attenuation_count, length - init_n)
                if stop >= len(z):
                    final_n = 0  # plant runs off the end of the take

                z[start:start + init_n] = _ease_values(
                    init_n, z_threshold, ground_level)
                z[start + init_n:stop - final_n] = ground_level
                if final_n:
                    z[stop - final_n:stop] = _ease_values(
                        final_n, ground_level, z_threshold)

                changed.update(range(start, stop))
                windows += 1
                stats["planted_frames"] += length

            stats["modified_markers"].add(base_name)

        stats["windows"][side] = windows

        # Re-solve the ankle height on every changed frame so the foot's
        # bones keep their median lengths, then pay the shift up the chain.
        for f in sorted(changed):
            current = float(ankle[2, f])
            solved = _solve_ankle_z(
                current,
                (float(ankle[0, f]), float(ankle[1, f])),
                toe[:, f], heel[:, f], len_toe, len_heel,
            )
            ankle[2, f] = solved
            stats["ankle_adjusted"] += 1

            delta = solved - current
            if knee_hip_compensation_coefficient != 0.0:
                for comp in spec["compensation"]:
                    if comp in markers:
                        markers[comp][2, f] += (
                            delta * knee_hip_compensation_coefficient)
                        stats["modified_markers"].add(comp)

        stats["modified_markers"].add(spec["ankle"])
        overall_changed |= changed

    if (compensate_upper_body and overall_changed
            and all(m in markers for m in ("hips_center", "left_hip",
                                           "right_hip"))):
        hips_center = markers["hips_center"]
        upper = [name for name in markers if name not in _LOWER_BODY]
        for f in sorted(overall_changed):
            new_z = (markers["left_hip"][2, f]
                     + markers["right_hip"][2, f]) / 2.0
            delta = new_z - hips_center[2, f]
            hips_center[2, f] = new_z
            for name in upper:
                markers[name][2, f] += delta
            stats["body_frames"] += 1
        stats["modified_markers"].add("hips_center")
        stats["modified_markers"].update(upper)

    if not any(stats["windows"].values()) and not stats["clamped_frames"]:
        # Nothing met the criteria — report honestly, write nothing back.
        stats["modified_markers"] = set()

    return stats
