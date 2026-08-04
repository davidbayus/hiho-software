"""HIHO Test Face — the diagnostic puppet for face takes.

Generates a cartoon debug head with ALL 52 ARKit shape keys so every channel
of a Live Link Face (or DeadFace) take lands somewhere inspectable. Fifteen
keys get real modeled deformation (jaw, blinks, wide eyes, brows, smile,
frown, funnel, pucker, close); the rest are zero-delta keys whose sliders
still animate — nothing imported is ever dropped (FACE_CAPTURE_DESIGN
2026-07-20).

Construction is "sticker face": a head sphere with flat feature discs
floating just proud of the surface (eyes, pupils, brows, lips, mouth
backing). Every part records its vertex index range at build time, so shape
keys are exact per-vertex offsets of known vertex sets — no spatial
guessing, fully deterministic. Blinks squash the eye discs into a dark slit
(cartoon closed-eye) rather than sliding a lid object.

Left/Right follow ARKit semantics: the PERFORMER's left. The head faces -Y
(toward Blender's front view), so performer-left features sit at +X.
"""

import math

import bpy

FACE_OBJECT_NAME = "HIHO Test Face"
FACE_COLLECTION_NAME = "HIHO MOCAP Face"

# Apple's ARKit blendshape set — the interchange standard every capture
# source targets (FACIAL_MOCAP_RESEARCH_2026-05-29). Grouped for slider
# readability, not stream order: importers match by NAME, never position.
ARKIT_SHAPE_NAMES = (
    "browDownLeft", "browDownRight", "browInnerUp",
    "browOuterUpLeft", "browOuterUpRight",
    "eyeBlinkLeft", "eyeBlinkRight",
    "eyeLookDownLeft", "eyeLookDownRight",
    "eyeLookInLeft", "eyeLookInRight",
    "eyeLookOutLeft", "eyeLookOutRight",
    "eyeLookUpLeft", "eyeLookUpRight",
    "eyeSquintLeft", "eyeSquintRight",
    "eyeWideLeft", "eyeWideRight",
    "jawForward", "jawLeft", "jawOpen", "jawRight",
    "mouthClose",
    "mouthDimpleLeft", "mouthDimpleRight",
    "mouthFrownLeft", "mouthFrownRight",
    "mouthFunnel",
    "mouthLeft",
    "mouthLowerDownLeft", "mouthLowerDownRight",
    "mouthPressLeft", "mouthPressRight",
    "mouthPucker",
    "mouthRight",
    "mouthRollLower", "mouthRollUpper",
    "mouthShrugLower", "mouthShrugUpper",
    "mouthSmileLeft", "mouthSmileRight",
    "mouthStretchLeft", "mouthStretchRight",
    "mouthUpperUpLeft", "mouthUpperUpRight",
    "cheekPuff", "cheekSquintLeft", "cheekSquintRight",
    "noseSneerLeft", "noseSneerRight",
    "tongueOut",
)

HEAD_RADIUS = 0.25

_EYE_X = 0.095
_EYE_Z = 0.055
_EYE_R = 0.058
_PUPIL_R = 0.024
_BROW_Z = 0.150
_BROW_HALF_LEN = 0.062
_BROW_HALF_H = 0.014
_MOUTH_Z = -0.095
# Backing hides behind the lips at rest (only the center line shows);
# jawOpen drags its lower half down to become the open-mouth dark. Sized
# with margin inside the lip bars so edges never peek through edge-on.
_MOUTH_BACK_RX = 0.108
_MOUTH_BACK_RZ = 0.026
_LIP_HALF_LEN = 0.112
_LIP_HALF_H = 0.014
_JAW_DROP = 0.060

# Features are built flat, then projected onto a shell just proud of the
# head sphere — each layer at its own radius so stacking order holds from
# every viewing angle (pupils over whites, lips over backing, brows on top).
_SHELL_OFFSETS = (
    ("backing", 0.004),
    ("eye_", 0.006),
    ("lip_lower", 0.009),  # own layer: mouthClose overlaps lips, no z-fight
    ("lip_", 0.010),
    ("pupil_", 0.012),
    ("brow_", 0.017),
    ("nose", 0.017),
)

_MATERIALS = (
    ("HIHO Face Skin", (0.87, 0.72, 0.58, 1.0)),
    ("HIHO Face White", (0.95, 0.95, 0.93, 1.0)),
    ("HIHO Face Pupil", (0.08, 0.06, 0.06, 1.0)),
    ("HIHO Face Brow", (0.25, 0.16, 0.10, 1.0)),
    ("HIHO Face Lips", (0.65, 0.35, 0.30, 1.0)),
    ("HIHO Face Mouth", (0.22, 0.08, 0.08, 1.0)),
)
_MAT_SKIN, _MAT_WHITE, _MAT_PUPIL, _MAT_BROW, _MAT_LIPS, _MAT_MOUTH = range(6)


class _MeshBuilder:
    """Accumulates verts/faces/material indices; records index ranges per part."""

    def __init__(self):
        self.verts = []
        self.faces = []
        self.face_mats = []
        self.parts = {}

    def add_part(self, name, verts, faces, material_index):
        base = len(self.verts)
        self.verts.extend(verts)
        self.faces.extend(tuple(base + i for i in f) for f in faces)
        self.face_mats.extend(material_index for _ in faces)
        self.parts[name] = range(base, base + len(verts))
        return self.parts[name]


def _uv_sphere(radius, segments, rings, center):
    cx, cy, cz = center
    verts = [(cx, cy, cz + radius)]
    for ring in range(1, rings):
        phi = math.pi * ring / rings
        z = radius * math.cos(phi)
        r = radius * math.sin(phi)
        for seg in range(segments):
            theta = 2.0 * math.pi * seg / segments
            verts.append((cx + r * math.cos(theta),
                          cy + r * math.sin(theta),
                          cz + z))
    verts.append((cx, cy, cz - radius))
    last = len(verts) - 1

    faces = []
    for seg in range(segments):
        faces.append((0, 1 + seg, 1 + (seg + 1) % segments))
    for ring in range(rings - 2):
        a = 1 + ring * segments
        b = a + segments
        for seg in range(segments):
            s2 = (seg + 1) % segments
            faces.append((a + seg, b + seg, b + s2, a + s2))
    a = 1 + (rings - 2) * segments
    for seg in range(segments):
        faces.append((last, a + (seg + 1) % segments, a + seg))
    return verts, faces


def _disc(center, radius, n=24, rx=None, rz=None):
    """Flat fan disc in the XZ plane facing -Y (the face's front)."""
    cx, cy, cz = center
    rx = radius if rx is None else rx
    rz = radius if rz is None else rz
    verts = [(cx, cy, cz)]
    for i in range(n):
        t = 2.0 * math.pi * i / n
        verts.append((cx + rx * math.cos(t), cy, cz + rz * math.sin(t)))
    faces = [(0, 1 + i, 1 + (i + 1) % n) for i in range(n)]
    return verts, faces


def _bar(center, half_len, half_h, cols=12):
    """Flat horizontal grid strip in the XZ plane facing -Y (brows, lips)."""
    cx, cy, cz = center
    verts = []
    for row in (-1, 1):
        for col in range(cols + 1):
            x = cx - half_len + 2.0 * half_len * col / cols
            verts.append((x, cy, cz + row * half_h))
    faces = []
    for col in range(cols):
        a = col
        b = col + (cols + 1)
        faces.append((a, a + 1, b + 1, b))
    return verts, faces


def _build_geometry():
    b = _MeshBuilder()

    verts, faces = _uv_sphere(HEAD_RADIUS, 32, 16, (0.0, 0.0, 0.0))
    b.add_part("head", verts, faces, _MAT_SKIN)

    for side, sx in (("L", 1.0), ("R", -1.0)):
        x = sx * _EYE_X
        verts, faces = _disc((x, 0.0, _EYE_Z), _EYE_R)
        b.add_part(f"eye_{side}", verts, faces, _MAT_WHITE)
        verts, faces = _disc((x, 0.0, _EYE_Z), _PUPIL_R, n=16)
        b.add_part(f"pupil_{side}", verts, faces, _MAT_PUPIL)
        verts, faces = _bar((x, 0.0, _BROW_Z), _BROW_HALF_LEN, _BROW_HALF_H, cols=8)
        b.add_part(f"brow_{side}", verts, faces, _MAT_BROW)

    verts, faces = _disc((0.0, 0.0, _MOUTH_Z),
                         _MOUTH_BACK_RX, rx=_MOUTH_BACK_RX, rz=_MOUTH_BACK_RZ)
    b.add_part("backing", verts, faces, _MAT_MOUTH)
    verts, faces = _bar((0.0, 0.0, _MOUTH_Z + 0.002 + _LIP_HALF_H),
                        _LIP_HALF_LEN, _LIP_HALF_H)
    b.add_part("lip_upper", verts, faces, _MAT_LIPS)
    verts, faces = _bar((0.0, 0.0, _MOUTH_Z - 0.002 - _LIP_HALF_H),
                        _LIP_HALF_LEN, _LIP_HALF_H)
    b.add_part("lip_lower", verts, faces, _MAT_LIPS)

    verts, faces = _disc((0.0, 0.0, -0.010), 0.024, n=16)
    b.add_part("nose", verts, faces, _MAT_BROW)

    _project_features_onto_shell(b)
    return b


def _project_features_onto_shell(builder):
    """Wrap each flat feature onto its layer shell: y = -sqrt(r² - x² - z²).

    Curved caps hug the ball, so features never float free of the head at
    oblique viewing angles the way flat stickers do."""
    for part_name, indices in builder.parts.items():
        if part_name == "head":
            continue
        offset = next(off for prefix, off in _SHELL_OFFSETS
                      if part_name.startswith(prefix))
        shell_r = HEAD_RADIUS + offset
        for i in indices:
            x, _, z = builder.verts[i]
            y = -math.sqrt(max(1e-6, shell_r * shell_r - x * x - z * z))
            builder.verts[i] = (x, y, z)


def _corner_weight(x, sign):
    """1.0 at the mouth corner on the given side (+1 = performer left),
    fading to 0 at the mouth center. Powers the smile/frown shapes."""
    t = max(0.0, min(1.0, (x * sign) / _LIP_HALF_LEN))
    return t ** 1.5


def _brow_inner_weight(x, sx):
    """1.0 at the brow's inner (nose-side) end, 0 at the outer end."""
    inner = sx * (_EYE_X - _BROW_HALF_LEN)
    outer = sx * (_EYE_X + _BROW_HALF_LEN)
    t = (x - outer) / (inner - outer)
    return max(0.0, min(1.0, t))


def _chin_weight(x, y, z):
    """How much a head vert belongs to the chin: front (-y) and low (-z)."""
    if y > -0.06 or z > -0.08:
        return 0.0
    wy = min(1.0, (-y - 0.06) / 0.12)
    wz = min(1.0, (-0.08 - z) / 0.12)
    return wy * wz


def _modeled_deltas(builder):
    """name -> {vert_index: (dx, dy, dz)} for the 15 modeled shape keys."""
    verts = builder.verts
    parts = builder.parts
    deltas = {}

    def move(name, indices, fn):
        d = deltas.setdefault(name, {})
        for i in indices:
            x, y, z = verts[i]
            offset = fn(x, y, z)
            if offset != (0.0, 0.0, 0.0):
                px, py, pz = d.get(i, (0.0, 0.0, 0.0))
                d[i] = (px + offset[0], py + offset[1], pz + offset[2])

    move("jawOpen", parts["lip_lower"], lambda x, y, z: (0.0, 0.0, -_JAW_DROP))
    move("jawOpen", parts["backing"],
         lambda x, y, z: (0.0, 0.0, -_JAW_DROP) if z < _MOUTH_Z - 1e-9
         else (0.0, 0.0, 0.0))
    move("jawOpen", parts["head"],
         lambda x, y, z: (0.0, 0.0, -0.055 * _chin_weight(x, y, z)))

    for side, sx in (("Left", 1.0), ("Right", -1.0)):
        tag = "L" if side == "Left" else "R"
        # Blink squashes the eye flat into a dark slit (the white flattens
        # almost fully; the pupil keeps a sliver = the closed-eye line).
        move(f"eyeBlink{side}", parts[f"eye_{tag}"],
             lambda x, y, z: (0.0, 0.0, -0.95 * (z - _EYE_Z)))
        move(f"eyeBlink{side}", parts[f"pupil_{tag}"],
             lambda x, y, z: (0.0, 0.0, -0.75 * (z - _EYE_Z)))
        move(f"eyeWide{side}",
             list(parts[f"eye_{tag}"]) + list(parts[f"pupil_{tag}"]),
             lambda x, y, z: (0.0, 0.0, 0.22 * (z - _EYE_Z)))
        move(f"browDown{side}", parts[f"brow_{tag}"],
             lambda x, y, z: (0.0, 0.0, -0.030))
        move("browInnerUp", parts[f"brow_{tag}"],
             lambda x, y, z, s=sx: (0.0, 0.0, 0.040 * _brow_inner_weight(x, s)))

        lips = list(parts["lip_upper"]) + list(parts["lip_lower"])
        move(f"mouthSmile{side}", lips,
             lambda x, y, z, s=sx: (0.012 * s * _corner_weight(x, s), 0.0,
                                    0.035 * _corner_weight(x, s)))
        move(f"mouthFrown{side}", lips,
             lambda x, y, z, s=sx: (0.0, 0.0, -0.035 * _corner_weight(x, s)))

    lips = list(parts["lip_upper"]) + list(parts["lip_lower"])
    move("mouthFunnel", lips, lambda x, y, z: (-0.45 * x, -0.040, 0.0))
    move("mouthFunnel", parts["backing"], lambda x, y, z: (-0.45 * x, 0.0, 0.0))
    move("mouthFunnel", parts["lip_upper"], lambda x, y, z: (0.0, 0.0, 0.012))
    move("mouthFunnel", parts["lip_lower"], lambda x, y, z: (0.0, 0.0, -0.012))
    move("mouthPucker", lips, lambda x, y, z: (-0.60 * x, -0.055, 0.0))
    move("mouthPucker", parts["backing"], lambda x, y, z: (-0.60 * x, 0.0, 0.0))
    move("mouthPucker", parts["lip_upper"], lambda x, y, z: (0.0, 0.0, -0.006))
    move("mouthPucker", parts["lip_lower"], lambda x, y, z: (0.0, 0.0, 0.006))
    move("mouthClose", parts["lip_upper"], lambda x, y, z: (0.0, 0.0, -0.006))
    move("mouthClose", parts["lip_lower"], lambda x, y, z: (0.0, 0.0, 0.006))

    return deltas


def _ensure_materials(mesh):
    for name, rgba in _MATERIALS:
        mat = bpy.data.materials.get(name)
        if mat is None:
            mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf is not None:
            bsdf.inputs["Base Color"].default_value = rgba
        mat.diffuse_color = rgba
        mesh.materials.append(mat)


def _ensure_collection(scene):
    coll = bpy.data.collections.get(FACE_COLLECTION_NAME)
    if coll is None:
        coll = bpy.data.collections.new(FACE_COLLECTION_NAME)
    if coll.name not in {c.name for c in scene.collection.children}:
        scene.collection.children.link(coll)
    return coll


def purge_test_face():
    """Remove a prior Test Face + its mesh + orphaned shape-key action.

    Same idempotency contract as Spawn Rig: re-clicking rebuilds fresh
    instead of erroring or silently reusing stale data.
    """
    obj = bpy.data.objects.get(FACE_OBJECT_NAME)
    if obj is None:
        return
    mesh = obj.data
    actions = []
    if obj.animation_data is not None and obj.animation_data.action is not None:
        actions.append(obj.animation_data.action)
    if (mesh is not None and mesh.shape_keys is not None
            and mesh.shape_keys.animation_data is not None
            and mesh.shape_keys.animation_data.action is not None):
        actions.append(mesh.shape_keys.animation_data.action)
    bpy.data.objects.remove(obj, do_unlink=True)
    if mesh is not None and mesh.users == 0:
        bpy.data.meshes.remove(mesh)
    for action in actions:
        if action.users == 0:
            bpy.data.actions.remove(action)


def build_test_face(scene):
    """Build the Test Face object with all 52 shape keys; returns (object,
    number of modeled keys)."""
    builder = _build_geometry()

    mesh = bpy.data.meshes.new(FACE_OBJECT_NAME)
    mesh.from_pydata(builder.verts, [], builder.faces)
    mesh.update()
    _ensure_materials(mesh)
    for poly, mat_index in zip(mesh.polygons, builder.face_mats):
        poly.material_index = mat_index
    mesh.shade_smooth()

    obj = bpy.data.objects.new(FACE_OBJECT_NAME, mesh)
    obj.location = (0.0, 0.0, HEAD_RADIUS + 0.01)
    _ensure_collection(scene).objects.link(obj)

    obj.shape_key_add(name="Basis", from_mix=False)
    deltas = _modeled_deltas(builder)
    for name in ARKIT_SHAPE_NAMES:
        key = obj.shape_key_add(name=name, from_mix=False)
        for index, (dx, dy, dz) in deltas.get(name, {}).items():
            x, y, z = builder.verts[index]
            key.data[index].co = (x + dx, y + dy, z + dz)

    return obj, len(deltas)
