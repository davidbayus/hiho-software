"""Spawn Test Face operator — the diagnostic puppet for face takes.

Generates the HIHO Test Face (core/test_face.py): a cartoon debug head with
all 52 ARKit shape keys, 15 of them modeled. Face takes loaded with Load
Face Take land on it with zero setup, so capture problems and import
problems can't hide behind character problems (FACE_CAPTURE_DESIGN
2026-07-20).

Idempotent like Spawn Rig: re-clicking replaces the prior Test Face and its
shape-key action instead of erroring or stacking duplicates.
"""

import bpy

from ..core.test_face import build_test_face, purge_test_face
from . import STATE


class HIHO_MOCAP_OT_spawn_test_face(bpy.types.Operator):
    """Build the cartoon debug head that face takes play on (52 sliders)."""
    bl_idname = "hiho_mocap.spawn_test_face"
    bl_label = "Spawn Test Face"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        purge_test_face()
        try:
            obj, modeled = build_test_face(context.scene)
        except Exception as exc:
            self.report({'ERROR'}, f"Spawn Test Face failed: {type(exc).__name__}: {exc}")
            return {'CANCELLED'}

        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        context.view_layer.objects.active = obj
        try:
            bpy.ops.view3d.view_selected(use_all_regions=False)
        except RuntimeError:
            pass

        key_count = len(obj.data.shape_keys.key_blocks) - 1
        msg = (f"Built {obj.name}: {key_count} sliders, {modeled} move the mesh. "
               f"Load Face Take drops a recording on it.")
        STATE["status_text"] = msg
        self.report({'INFO'}, msg)
        return {'FINISHED'}
