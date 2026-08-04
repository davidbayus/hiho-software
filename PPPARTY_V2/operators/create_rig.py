"""PPParty V2 — Create V2 Rig operator.

The user-facing button. Calls the rig builder in core.rig and
reports success. This is intentionally thin — all real logic
lives in core.rig so it can be reused by Start Mirror later
(which needs to ensure a rig exists before driving it).
"""

import bpy

from ..core.rig import build_v2_rig


class PPPARTY_V2_OT_create_rig(bpy.types.Operator):
    """Build the PPParty V2 bones-only rig in the scene."""

    bl_idname = "ppparty_v2.create_rig"
    bl_label = "Create V2 Rig"
    bl_description = "Create a bones-only humanoid rig for V2 capture (no mesh)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        rig_object = build_v2_rig(context)
        self.report({'INFO'}, f"Created {rig_object.name} (12 bones, no mesh)")
        return {'FINISHED'}
