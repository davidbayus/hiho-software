"""Import Character operator — brings a student's .fbx or .obj character
into the scene under its own HIHO_Character collection.

First step of the Studio Character pipeline (STUDIO_SECTION_DESIGN_2026-07-01.md):
Import Character -> Add Markers -> Auto-Rig -> Send to Character.
"""

import os

import bpy

from . import STATE


class HIHO_MOCAP_OT_import_character(bpy.types.Operator):
    """Pick a .fbx or .obj character file and bring it into the scene."""
    bl_idname = "hiho_mocap.import_character"
    bl_label = "Import Character"
    bl_options = {'REGISTER', 'UNDO'}

    filepath: bpy.props.StringProperty(subtype='FILE_PATH')
    filter_glob: bpy.props.StringProperty(
        default="*.fbx;*.obj",
        options={'HIDDEN'},
    )

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        path = self.filepath
        ext = os.path.splitext(path)[1].lower()
        if not os.path.isfile(path):
            self.report({'ERROR'}, f"File not found: {path}")
            return {'CANCELLED'}
        if ext not in {".fbx", ".obj"}:
            self.report({'ERROR'}, "Pick a .fbx or .obj file.")
            return {'CANCELLED'}

        before = set(bpy.data.objects)
        try:
            if ext == ".fbx":
                bpy.ops.import_scene.fbx(filepath=path)
            else:
                bpy.ops.wm.obj_import(filepath=path)
        except Exception as exc:
            self.report({'ERROR'}, f"Import failed: {type(exc).__name__}: {exc}")
            return {'CANCELLED'}

        new_objects = [ob for ob in bpy.data.objects if ob not in before]
        if not new_objects:
            self.report({'ERROR'}, "The file imported nothing. Is it a valid character file?")
            return {'CANCELLED'}

        base = bpy.path.clean_name(os.path.splitext(os.path.basename(path))[0])
        coll_name = f"HIHO_Character_{base}"
        coll = bpy.data.collections.get(coll_name)
        if coll is None:
            coll = bpy.data.collections.new(coll_name)
            context.scene.collection.children.link(coll)
        for ob in new_objects:
            for other in list(ob.users_collection):
                other.objects.unlink(ob)
            coll.objects.link(ob)

        context.scene.hiho_mocap.character_collection = coll_name

        meshes = [ob for ob in new_objects if ob.type == 'MESH']
        armatures = [ob for ob in new_objects if ob.type == 'ARMATURE']
        vert_count = sum(len(ob.data.vertices) for ob in meshes)
        msg = (f"Imported {len(meshes)} mesh piece(s), {vert_count} vertices, "
               f"into {coll_name}. Next: Add Markers.")
        if armatures:
            msg += (f" Heads up: the file also contains {len(armatures)} armature(s); "
                    "Auto-Rig builds its own and leaves those untouched.")
        STATE["status_text"] = msg
        self.report({'INFO'}, msg)
        return {'FINISHED'}
