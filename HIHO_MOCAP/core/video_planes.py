"""HIHO MOCAP — load a take's camera videos as planes in the scene.

Recreates the FreeMoCap-reference look (the Camera_N_mediapipe planes in shot)
using Blender 5.x's native `import_as_mesh_planes` operator — no ajc27, no
OpenCV, no bundle. Planes are emission-shaded animated movies gathered into a
'HIHO MOCAP Videos' collection. Prefers annotated_videos (the MediaPipe overlay,
what the reference uses) and falls back to synchronized_videos.

Every other plane is turned 180° (David's arrangement, 2026-06-06): the cameras
alternate front/back around the performer, so flipping the odd ones makes the
four read as a ring around the subject rather than a flat filmstrip.
"""
import math
import os

import bpy
import mathutils

VIDEO_COLLECTION = "HIHO MOCAP Videos"
FACE_PLANE_NAME = "HIHO Face Video"
FACE_VIDEO_EXTS = (".mov", ".mp4", ".m4v")


def _video_dir(take_dir):
    """annotated_videos preferred (MediaPipe overlay); synchronized_videos fallback."""
    for sub in ("annotated_videos", "synchronized_videos"):
        d = os.path.join(take_dir, sub)
        if os.path.isdir(d) and any(f.endswith(".mp4") for f in os.listdir(d)):
            return d
    return None


def _video_collection():
    coll = bpy.data.collections.get(VIDEO_COLLECTION)
    if coll is None:
        coll = bpy.data.collections.new(VIDEO_COLLECTION)
        bpy.context.scene.collection.children.link(coll)
    return coll


def load_camera_video_planes(take_dir, video_scale=3.0, spacing=4.0):
    """Import each Camera_*.mp4 in the take's video folder as an animated plane,
    laid out in a centered row in the 'HIHO MOCAP Videos' collection.

    Returns (created_object_names, video_dir); ([], None) if no videos found.
    """
    vdir = _video_dir(take_dir)
    if vdir is None:
        return [], None
    vids = sorted(f for f in os.listdir(vdir) if f.endswith(".mp4"))

    coll = _video_collection()
    created = []
    center = (len(vids) - 1) * spacing / 2.0
    roll_y = mathutils.Matrix.Rotation(math.pi, 3, 'Y')  # 180° about the facing axis
    canonical = None  # the first plane's pose = the importer's "upright, facing the row"
    for i, name in enumerate(vids):
        before = set(bpy.data.objects)
        bpy.ops.image.import_as_mesh_planes(
            files=[{"name": name}], directory=vdir,
            shader='EMISSION', align_axis='+Y', size_mode='ABSOLUTE', height=video_scale,
        )
        # The operator's selection state is unreliable across Blender versions;
        # diff the datablocks (materialized BEFORE we mutate collections, or the
        # lazy generator skips the new plane) to get exactly what it just created.
        new_planes = [o for o in bpy.data.objects if o not in before and o.type == 'MESH']
        for obj in new_planes:
            # Move into the HIHO video collection, out of wherever the op put it.
            for c in list(obj.users_collection):
                c.objects.unlink(obj)
            coll.objects.link(obj)
            # Normalize every plane off the FIRST one (the importer can hand a
            # later plane a flipped rotation OR a mirrored scale, which would
            # desync the row). Even planes take that canonical pose; odd planes
            # (the back-view cameras) take it rolled 180° about the facing axis,
            # so the flat row becomes a ring around the performer (David's look).
            if canonical is None:
                canonical = obj.matrix_basis.to_3x3()  # rotation + scale of plane 0
            rot_scale = (roll_y @ canonical) if i % 2 == 1 else canonical
            location = mathutils.Matrix.Translation((i * spacing - center, 0.0, video_scale / 2.0))
            obj.matrix_basis = location @ rot_scale.to_4x4()
            created.append(obj.name)
    return created, vdir


def find_face_video(csv_path):
    """The reference video AirDropped beside the face take's CSV, or None."""
    folder = os.path.dirname(csv_path)
    if not os.path.isdir(folder):
        return None
    vids = sorted(f for f in os.listdir(folder)
                  if f.lower().endswith(FACE_VIDEO_EXTS))
    if not vids:
        return None
    return os.path.join(folder, vids[0])


def purge_face_video_plane():
    """Remove a previous face plane so Add Face Video stays idempotent."""
    obj = bpy.data.objects.get(FACE_PLANE_NAME)
    if obj is not None:
        mesh = obj.data
        bpy.data.objects.remove(obj)
        if mesh is not None and mesh.users == 0:
            bpy.data.meshes.remove(mesh)


def _plane_image_user(obj):
    """The movie image-user on a video plane's material, or None."""
    for slot in obj.material_slots:
        mat = slot.material
        if mat is None or not mat.use_nodes:
            continue
        for node in mat.node_tree.nodes:
            if (node.type == 'TEX_IMAGE' and node.image is not None
                    and node.image.source == 'MOVIE'):
                return node.image_user
    return None


def load_face_video_plane(video_path, video_scale=3.0, spacing=4.0):
    """Import the face reference video as one more plane beside the camera
    planes. Idempotent: replaces a previous face plane. Returns the object,
    or None if the importer produced nothing (unreadable video)."""
    purge_face_video_plane()
    coll = _video_collection()
    others = [o for o in coll.objects if o.name != FACE_PLANE_NAME]
    x = (min(o.location.x for o in others) - spacing) if others else -spacing

    before = set(bpy.data.objects)
    bpy.ops.image.import_as_mesh_planes(
        files=[{"name": os.path.basename(video_path)}],
        directory=os.path.dirname(video_path),
        shader='EMISSION', align_axis='+Y', size_mode='ABSOLUTE',
        height=video_scale,
    )
    new_planes = [o for o in bpy.data.objects if o not in before and o.type == 'MESH']
    if not new_planes:
        return None
    obj = new_planes[0]
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    coll.objects.link(obj)
    obj.name = FACE_PLANE_NAME
    obj.location = (x, 0.0, video_scale / 2.0)
    image_user = _plane_image_user(obj)
    obj["hiho_base_frame_start"] = int(image_user.frame_start) if image_user else 1
    obj["hiho_applied_offset"] = 0.0
    obj["hiho_face_source"] = video_path
    return obj


def set_face_plane_offset(obj, offset):
    """Start the face plane's video `offset` frames later than where it was
    imported. Applied absolutely from the stored base so re-running heals
    rather than compounds. Video lands on whole frames (the shape-key action
    keeps the subframe precision)."""
    image_user = _plane_image_user(obj)
    if image_user is None:
        return False
    image_user.frame_start = (int(obj.get("hiho_base_frame_start", 1))
                              + round(offset))
    obj["hiho_applied_offset"] = float(offset)
    return True
