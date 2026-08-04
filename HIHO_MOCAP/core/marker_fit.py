"""HIHO MOCAP — fit the ajc27-named body skeleton to student-placed markers.

Builds the 23 body bones (no fingers — no markers drive them) with heads and
tails derived from the 13 HIHO markers, so the live constraint table in
bind_to_rig.py drives the result with no translation layer. Parenting and
connect flags come from build_rig._ARMATURE_DEFINITION; each fitted bone's
roll is aligned to the same local-Z direction its ajc27 T-pose counterpart
has, so constraint-driven twist behaves like the canonical rig.

See STUDIO_SECTION_DESIGN_2026-07-01.md (Feature 3, amendment).
"""

from typing import Dict, List, Optional, Tuple

import bpy
from mathutils import Euler, Vector

from .build_rig import _ARMATURE_DEFINITION, _TPOSE

BODY_BONES: Tuple[str, ...] = tuple(
    name for name in _ARMATURE_DEFINITION
    if not any(part in name for part in ("thumb", "palm", "f_index", "f_middle", "f_ring", "f_pinky"))
)

REQUIRED_MARKERS: Tuple[str, ...] = (
    "head",
    "shoulder.L", "shoulder.R",
    "elbow.L", "elbow.R",
    "wrist.L", "wrist.R",
    "hip.L", "hip.R",
    "knee.L", "knee.R",
    "ankle.L", "ankle.R",
)


def detect_forward(meshes: List[bpy.types.Object],
                   markers: Dict[str, Vector],
                   mirror_axis: str) -> Vector:
    """Which way the character faces, as a unit world vector.

    Sides differ across the mirror axis, so facing is along the other
    horizontal axis. Sign heuristic: toes push the mesh volume forward of the
    ankles, so compare low-height vertex centroid against the ankle markers.
    Falls back to -Y / -X (Blender's usual facing) when ambiguous.
    """
    axis = 1 if mirror_axis == 'X' else 0
    forward = Vector((0, 0, 0))
    forward[axis] = -1.0

    ankle_mid = (markers["ankle.L"] + markers["ankle.R"]) / 2
    foot_top = ankle_mid.z
    total = 0.0
    count = 0
    for ob in meshes:
        for v in ob.data.vertices:
            co = ob.matrix_world @ v.co
            if co.z <= foot_top:
                total += co[axis]
                count += 1
    if count:
        offset = total / count - ankle_mid[axis]
        span = max((markers["head"].z - ankle_mid.z), 1e-6)
        if abs(offset) > span * 0.01:
            forward[axis] = 1.0 if offset > 0 else -1.0
    return forward


def center_marker_depth(marker_objects: Dict[str, bpy.types.Object],
                        meshes: List[bpy.types.Object],
                        mirror_axis: str) -> int:
    """Push each marker to the middle of the character's volume along the
    depth (forward/back) axis.

    Students place markers in front view, which leaves every marker at one
    flat depth — the rig then sits outside the body from any other angle.
    For each marker we cast a line through the character along the depth
    axis at the marker's other two coordinates, collect every surface
    crossing over all mesh pieces, and move the marker to the midpoint of
    the outermost crossings. Markers whose line misses the mesh entirely
    are left where the student put them. Returns how many markers moved.
    """
    depth_axis = 1 if mirror_axis == 'X' else 0
    span = max((max((ob.matrix_world @ Vector(c))[depth_axis]
                    for ob in meshes for c in ob.bound_box)
                - min((ob.matrix_world @ Vector(c))[depth_axis]
                      for ob in meshes for c in ob.bound_box)), 0.01)
    direction = Vector((0, 0, 0))
    direction[depth_axis] = 1.0

    moved = 0
    for empty in marker_objects.values():
        if empty is None:
            continue
        origin = empty.location.copy()
        origin[depth_axis] -= span * 2
        hits = []
        for ob in meshes:
            inv = ob.matrix_world.inverted()
            local_origin = inv @ origin
            local_dir = (inv.to_3x3() @ direction).normalized()
            start = local_origin
            for _ in range(64):
                ok, loc, _normal, _index = ob.ray_cast(start, local_dir)
                if not ok:
                    break
                hits.append((ob.matrix_world @ loc)[depth_axis])
                start = loc + local_dir * 1e-4
        if len(hits) >= 2:
            mid = (min(hits) + max(hits)) / 2
            if abs(empty.location[depth_axis] - mid) > 1e-6:
                empty.location[depth_axis] = mid
                moved += 1
    return moved


def _axis_params(meshes: List[bpy.types.Object],
                 point: Vector, axis: Vector) -> List[float]:
    """Signed distances from `point` to every mesh-surface crossing along
    `axis`. Empty list if the line misses the character entirely."""
    span = 100.0
    origin = point - axis * span
    params = []
    for ob in meshes:
        inv = ob.matrix_world.inverted()
        local_origin = inv @ origin
        local_dir = (inv.to_3x3() @ axis).normalized()
        start = local_origin
        for _ in range(64):
            ok, loc, _n, _i = ob.ray_cast(start, local_dir)
            if not ok:
                break
            params.append(((ob.matrix_world @ loc) - point).dot(axis))
            start = loc + local_dir * 1e-4
    return sorted(params)


def _derive_bone_points(markers: Dict[str, Vector],
                        forward: Vector,
                        floor_z: float,
                        meshes: List[bpy.types.Object]) -> Dict[str, Tuple[Vector, Vector]]:
    """Head/tail world positions per body bone, from the 13 markers."""
    m = markers
    mid_hip = (m["hip.L"] + m["hip.R"]) / 2
    mid_sho = (m["shoulder.L"] + m["shoulder.R"]) / 2
    up = mid_sho - mid_hip
    head_vec = m["head"] - mid_sho
    down = Vector((0, 0, -1))
    back = -forward

    spine_mid = mid_hip + up * 0.5

    # Head bones from the silhouette: the neck is where the character's
    # front-to-back thickness pinches between the shoulders and the crown,
    # and the skull starts at the top of that narrow band. Outermost-surface
    # widths, so eye sockets, mouths, and connected necks can't fake a
    # "head bottom" the way a single vertical probe could (1.4.4 bug,
    # found by David on his chibi). Marker-only fallback when sampling
    # fails or shows no real pinch.
    # (A skull-spanning `face` bone shipped briefly in 1.4.6 and was
    # REVERTED by David 2026-07-01: it required a bind-recipe override he
    # doesn't want to touch before BASEMENT. This is the 1.4.5 layout,
    # which the stock ajc27 constraint table drives as-is.)
    neck_tail = mid_sho + head_vec * 0.5
    z_hits = _axis_params(meshes, m["head"], Vector((0, 0, 1)))
    head_top = m["head"].z + (z_hits[-1] if z_hits else head_vec.length * 0.6)
    samples = []
    if meshes and head_top > mid_sho.z:
        for i in range(1, 24):
            z = mid_sho.z + (head_top - mid_sho.z) * i / 23
            line_point = Vector((m["head"].x, m["head"].y, z))
            hits = _axis_params(meshes, line_point, forward)
            if len(hits) >= 2:
                samples.append((z, hits[-1] - hits[0], (hits[0] + hits[-1]) / 2))
    if len(samples) >= 4:
        # The pinch must sit BELOW the skull's widest slice — a round head
        # tapers to nothing at the crown, which would otherwise win the
        # "narrowest" contest.
        z_widest = max(samples, key=lambda s: s[1])[0]
        candidates = [s for s in samples if s[0] < z_widest]
        max_width = max(w for _, w, _ in samples)
        if len(candidates) >= 2:
            min_width = min(w for _, w, _ in candidates)
            if min_width < max_width * 0.75:
                narrow = [s for s in candidates if s[1] < min_width * 1.15]
                z_junction, _w, mid_offset = max(narrow, key=lambda s: s[0])
                base_z = z_junction + (head_top - z_junction) * 0.1
                neck_tail = (Vector((m["head"].x, m["head"].y, base_z))
                             + forward * mid_offset)
    face_len = max(head_vec.length * 0.7, 0.02)
    f_hits = [p for p in _axis_params(meshes, neck_tail, forward) if p > 0]
    if f_hits:
        face_len = max(f_hits[-1] * 0.75, 0.02)
    points: Dict[str, Tuple[Vector, Vector]] = {
        "pelvis": (mid_hip, mid_hip + back * max(up.length * 0.1, 0.02)),
        "pelvis.R": (mid_hip, m["hip.R"]),
        "pelvis.L": (mid_hip, m["hip.L"]),
        "spine": (mid_hip, spine_mid),
        "spine.001": (spine_mid, mid_sho),
        "neck": (mid_sho, neck_tail),
        "face": (neck_tail, neck_tail + forward * face_len),
        "shoulder.R": (mid_sho, m["shoulder.R"]),
        "shoulder.L": (mid_sho, m["shoulder.L"]),
    }
    for side in ("R", "L"):
        hand_dir = (m[f"wrist.{side}"] - m[f"elbow.{side}"]).normalized()
        forearm_len = (m[f"wrist.{side}"] - m[f"elbow.{side}"]).length
        points[f"upper_arm.{side}"] = (m[f"shoulder.{side}"], m[f"elbow.{side}"])
        points[f"forearm.{side}"] = (m[f"elbow.{side}"], m[f"wrist.{side}"])
        points[f"hand.{side}"] = (m[f"wrist.{side}"],
                                  m[f"wrist.{side}"] + hand_dir * forearm_len * 0.35)

        ankle = m[f"ankle.{side}"]
        drop = max(ankle.z - floor_z, 0.01)
        points[f"thigh.{side}"] = (m[f"hip.{side}"], m[f"knee.{side}"])
        points[f"shin.{side}"] = (m[f"knee.{side}"], ankle)
        points[f"foot.{side}"] = (ankle, ankle + forward * drop * 1.3 + down * drop * 0.7)
        points[f"heel.02.{side}"] = (ankle, ankle + back * drop * 0.4 + down * drop * 0.9)
    return points


def _tpose_z_references(edit_bones) -> Dict[str, Vector]:
    """Local-Z world direction of each body bone in the canonical ajc27
    T-pose, read off temporary bones (Blender derives bone axes from
    direction + roll, so building the bone is the reliable way to get them)."""
    refs: Dict[str, Vector] = {}
    temps = []
    for name in BODY_BONES:
        rotation, roll = _TPOSE[name]
        tb = edit_bones.new(f"HIHO_TMP_{name}")
        tb.head = Vector((0, 0, 0))
        tb.tail = Euler(rotation, "XYZ").to_matrix() @ Vector((0, 0, 0.1))
        tb.roll = roll
        refs[name] = tb.matrix.to_3x3().col[2].copy()
        temps.append(tb)
    for tb in temps:
        edit_bones.remove(tb)
    return refs


def build_marker_armature(markers: Dict[str, Vector],
                          meshes: List[bpy.types.Object],
                          rig_name: str,
                          mirror_axis: str = 'X') -> bpy.types.Object:
    """Build the fitted body armature. Caller validates markers first."""
    floor_z = min((ob.matrix_world @ Vector(c)).z
                  for ob in meshes for c in ob.bound_box) if meshes else 0.0
    forward = detect_forward(meshes, markers, mirror_axis) if meshes else Vector((0, -1, 0))
    points = _derive_bone_points(markers, forward, floor_z, meshes)

    bpy.ops.object.armature_add(enter_editmode=False, align="WORLD", location=(0, 0, 0))
    rig = bpy.context.active_object
    rig.name = rig_name
    rig.data.name = f"{rig_name}_data"
    rig.show_in_front = True

    bpy.ops.object.mode_set(mode="EDIT")
    eb = rig.data.edit_bones
    for default in list(eb):
        eb.remove(default)

    z_refs = _tpose_z_references(eb)
    # ajc27's T-pose faces -Y; mirror the axis references when this character
    # faces the other way so twist semantics stay consistent.
    canonical_forward = Vector((0, -1, 0))
    flip = forward.dot(canonical_forward) < 0 if abs(forward.y) > abs(forward.x) else False

    for name in BODY_BONES:
        info = _ARMATURE_DEFINITION[name]
        head, tail = points[name]
        bone = eb.new(name)
        bone.head = head
        bone.tail = tail if (tail - head).length > 1e-5 else head + Vector((0, 0, 0.01))
        z_ref = z_refs[name].copy()
        if flip:
            z_ref.x, z_ref.y = -z_ref.x, -z_ref.y
        bone.align_roll(z_ref)
        if info["parent"] is not None:
            bone.parent = eb[info["parent"]]
            bone.use_connect = info["connected"] and (bone.head - eb[info["parent"]].tail).length < 1e-4

    bpy.ops.object.mode_set(mode="OBJECT")
    return rig


def missing_markers(markers: Dict[str, Optional[Vector]]) -> List[str]:
    return [name for name in REQUIRED_MARKERS if markers.get(name) is None]
