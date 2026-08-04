"""Save Out operator — export the baked performance as a portable file.

Studio panel section 5. The student bakes (real keyframes), picks FBX / GLB /
.blend, and Save Out writes the file through a save dialog. Refuses loudly on
an unbaked (constraint-driven) rig — exporting one produces a T-pose file,
the classic silent failure. Design: SAVE_OUT_DESIGN_2026-07-04.md.
"""

import os

import bpy

from ..core.bind_to_rig import HIHO_CONSTRAINT_PREFIX
from . import STATE

_EXTENSIONS = {'FBX': ".fbx", 'GLB': ".glb", 'BLEND': ".blend"}


class HIHO_MOCAP_OT_save_out(bpy.types.Operator):
    """Save the selected baked rig (and its character meshes) as a file you
    can hand to a game engine, web viewer, or another Blender"""
    bl_idname = "hiho_mocap.save_out"
    bl_label = "Save Out"

    filepath: bpy.props.StringProperty(subtype='FILE_PATH')
    check_existing: bpy.props.BoolProperty(default=True, options={'HIDDEN'})

    @classmethod
    def poll(cls, context):
        return context.object is not None and context.object.type == 'ARMATURE'

    def _refuse_unbaked(self, arm):
        # Only HIHO_ constraints mean "not baked yet" — a character's own
        # rigging (IK, limits) is normal on a baked rig and must not block export.
        if any(c.name.startswith(HIHO_CONSTRAINT_PREFIX)
               for pb in arm.pose.bones for c in pb.constraints):
            self.report(
                {'ERROR'},
                "This rig still runs on live constraints - press Bake "
                "Animation first so the motion is real keyframes.",
            )
            return True
        return False

    def invoke(self, context, event):
        arm = context.object
        if self._refuse_unbaked(arm):
            return {'CANCELLED'}

        ext = _EXTENSIONS[context.scene.hiho_mocap.export_format]
        default_name = arm.name
        if arm.animation_data and arm.animation_data.action:
            default_name = arm.animation_data.action.name
        self.filepath = os.path.join(os.path.expanduser("~/Desktop"),
                                     default_name + ext)
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        arm = context.object
        if self._refuse_unbaked(arm):
            return {'CANCELLED'}
        fmt = context.scene.hiho_mocap.export_format
        ext = _EXTENSIONS[fmt]
        filepath = bpy.path.abspath(self.filepath)
        if not filepath.lower().endswith(ext):
            filepath += ext

        # Students click the armature; the skinned character meshes must come
        # along without anyone remembering to shift-click them.
        if fmt in ('FBX', 'GLB'):
            bpy.ops.object.select_all(action='DESELECT')
            arm.select_set(True)
            for child in arm.children_recursive:
                child.select_set(True)
            context.view_layer.objects.active = arm

        try:
            if fmt == 'FBX':
                bpy.ops.export_scene.fbx(
                    filepath=filepath,
                    use_selection=True,
                    add_leaf_bones=False,
                )
            elif fmt == 'GLB':
                bpy.ops.export_scene.gltf(
                    filepath=filepath,
                    export_format='GLB',
                    use_selection=True,
                )
            else:  # BLEND
                bpy.ops.wm.save_as_mainfile(filepath=filepath, copy=True)
        except Exception as exc:
            self.report({'ERROR'}, f"Save Out failed: {type(exc).__name__}: {exc}")
            return {'CANCELLED'}

        if not os.path.isfile(filepath):
            self.report({'ERROR'}, f"Save Out finished but no file at {filepath}")
            return {'CANCELLED'}

        size_mb = os.path.getsize(filepath) / (1024 * 1024)
        msg = f"Saved {os.path.basename(filepath)} ({size_mb:.1f} MB)."
        if fmt == 'BLEND':
            msg += " A .blend saves the whole scene; your open file is untouched."
        STATE["status_text"] = msg
        self.report({'INFO'}, msg)
        return {'FINISHED'}
