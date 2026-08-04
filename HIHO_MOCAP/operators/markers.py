"""Add Markers operator — spawns the 13 joint markers the student drags
onto their character before pressing Auto-Rig.

Marker identity lives in a custom property (`ob["hiho_marker"]`), never the
object name, so students can rename markers freely without breaking Auto-Rig.
Template positions are classic human proportions as fractions of the
character's bounding-box height, so markers land near-right on most
characters and the student only nudges.
"""

import bpy
from mathutils import Vector

from . import STATE

MARKER_PROP = "hiho_marker"
MARKER_COLLECTION = "HIHO_Markers"

# marker id -> (plain-language object name, x as height-fraction, z as height-fraction)
# +X is the character's left side (Blender convention, character facing -Y).
MARKER_TEMPLATE = {
    "head":       ("Head",           0.00, 0.93),
    "shoulder.L": ("Left Shoulder",  0.11, 0.82),
    "shoulder.R": ("Right Shoulder", -0.11, 0.82),
    "elbow.L":    ("Left Elbow",     0.21, 0.71),
    "elbow.R":    ("Right Elbow",    -0.21, 0.71),
    "wrist.L":    ("Left Wrist",     0.29, 0.61),
    "wrist.R":    ("Right Wrist",    -0.29, 0.61),
    "hip.L":      ("Left Hip",       0.06, 0.52),
    "hip.R":      ("Right Hip",      -0.06, 0.52),
    "knee.L":     ("Left Knee",      0.07, 0.28),
    "knee.R":     ("Right Knee",     -0.07, 0.28),
    "ankle.L":    ("Left Ankle",     0.07, 0.05),
    "ankle.R":    ("Right Ankle",    -0.07, 0.05),
}


def character_meshes(context):
    """Meshes of the imported character: its HIHO_Character collection if set,
    else whatever meshes are selected."""
    settings = context.scene.hiho_mocap
    coll = bpy.data.collections.get(settings.character_collection)
    if coll is not None:
        meshes = [ob for ob in coll.all_objects if ob.type == 'MESH']
        if meshes:
            return meshes
    return [ob for ob in context.selected_objects if ob.type == 'MESH']


def find_marker(marker_id):
    for ob in bpy.data.objects:
        if ob.type == 'EMPTY' and ob.get(MARKER_PROP) == marker_id:
            return ob
    return None


def _world_bounds(meshes):
    corners = [ob.matrix_world @ Vector(c) for ob in meshes for c in ob.bound_box]
    lo = Vector((min(c[i] for c in corners) for i in range(3)))
    hi = Vector((max(c[i] for c in corners) for i in range(3)))
    return lo, hi


class HIHO_MOCAP_OT_add_markers(bpy.types.Operator):
    """Place the 13 joint markers around the character, ready to drag into place"""
    bl_idname = "hiho_mocap.add_markers"
    bl_label = "Add Markers"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        meshes = character_meshes(context)
        if not meshes:
            self.report({'ERROR'},
                        "No character found. Import Character first (or select your character's meshes).")
            return {'CANCELLED'}

        lo, hi = _world_bounds(meshes)
        height = hi.z - lo.z
        if height <= 0:
            self.report({'ERROR'}, "Character has no height — is the mesh empty?")
            return {'CANCELLED'}
        center_x = (lo.x + hi.x) / 2
        center_y = (lo.y + hi.y) / 2

        coll = bpy.data.collections.get(MARKER_COLLECTION)
        if coll is None:
            coll = bpy.data.collections.new(MARKER_COLLECTION)
            context.scene.collection.children.link(coll)

        moved = 0
        created = 0
        for marker_id, (label, x_frac, z_frac) in MARKER_TEMPLATE.items():
            empty = find_marker(marker_id)
            if empty is None:
                empty = bpy.data.objects.new(label, None)
                empty[MARKER_PROP] = marker_id
                coll.objects.link(empty)
                created += 1
            else:
                moved += 1
            empty.empty_display_type = 'SPHERE'
            empty.empty_display_size = max(height * 0.02, 0.005)
            empty.show_in_front = True
            empty.show_name = True
            empty.location = (center_x + x_frac * height,
                              center_y,
                              lo.z + z_frac * height)

        msg = f"{created + moved} markers placed"
        if moved:
            msg += f" ({moved} reset to template)"
        msg += ". Drag each marker onto the matching body part, then Auto-Rig."
        STATE["status_text"] = msg
        self.report({'INFO'}, msg)
        return {'FINISHED'}


class HIHO_MOCAP_OT_mirror_markers(bpy.types.Operator):
    """Copy one side's marker positions to the other side, mirrored across
    the character's middle — place one side by hand, mirror the rest"""
    bl_idname = "hiho_mocap.mirror_markers"
    bl_label = "Mirror Markers"
    bl_options = {'REGISTER', 'UNDO'}

    direction: bpy.props.EnumProperty(
        name="Direction",
        items=[
            ('L2R', "Left to Right", "Right-side markers snap to mirrored left-side positions"),
            ('R2L', "Right to Left", "Left-side markers snap to mirrored right-side positions"),
        ],
        default='L2R',
    )

    def execute(self, context):
        settings = context.scene.hiho_mocap
        axis = 0 if settings.marker_mirror_axis == 'X' else 1

        meshes = character_meshes(context)
        if meshes:
            lo, hi = _world_bounds(meshes)
            center = (lo[axis] + hi[axis]) / 2
        else:
            positions = [find_marker(m).location[axis]
                         for m in MARKER_TEMPLATE if find_marker(m)]
            if not positions:
                self.report({'ERROR'}, "No markers in the scene. Add Markers first.")
                return {'CANCELLED'}
            center = sum(positions) / len(positions)

        src_suffix, dst_suffix = (".L", ".R") if self.direction == 'L2R' else (".R", ".L")
        mirrored = 0
        missing = []
        for marker_id in MARKER_TEMPLATE:
            if not marker_id.endswith(src_suffix):
                continue
            src = find_marker(marker_id)
            dst = find_marker(marker_id[:-len(src_suffix)] + dst_suffix)
            if src is None or dst is None:
                missing.append(marker_id)
                continue
            loc = list(src.location)
            loc[axis] = 2 * center - loc[axis]
            dst.location = loc
            mirrored += 1

        if mirrored == 0:
            self.report({'ERROR'}, "No marker pairs found to mirror. Add Markers first.")
            return {'CANCELLED'}
        msg = f"Mirrored {mirrored} marker(s) {src_suffix[1]} to {dst_suffix[1]} across {settings.marker_mirror_axis}"
        if missing:
            msg += f" (couldn't find: {', '.join(missing)})"
        STATE["status_text"] = msg
        self.report({'INFO'}, msg)
        return {'FINISHED'}
