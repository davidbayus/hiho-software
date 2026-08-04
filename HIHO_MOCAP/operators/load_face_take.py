"""Load Face Take operator — phone face recording onto a face mesh.

Reads the Live Link Face CSV picked in the panel (core/face_take.py) and
writes it as a shape-key action, by default onto the HIHO Test Face,
otherwise onto the selected mesh if it has ARKit-named shape keys. The
import lands at the scene start; Line Up Face (next build) shifts it onto
the body take's clock via the flash marker.

Same picker convention as every other path in the panel: a Scene property
the student types or browses into — no fileselect popup (those run in the
file-browser context, the 1.4.8 lesson).
"""

import os

import bpy

from ..core.face_take import FaceTakeError, apply_face_take, parse_llf_csv
from . import STATE, norm_path


class HIHO_MOCAP_OT_load_face_take(bpy.types.Operator):
    """Put the picked face recording on the Test Face (or selected face mesh)."""
    bl_idname = "hiho_mocap.load_face_take"
    bl_label = "Load Face Take"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return bool(context.scene.hiho_mocap.face_take_csv)

    def execute(self, context):
        csv_path = norm_path(context.scene.hiho_mocap.face_take_csv)
        if not csv_path or not os.path.isfile(csv_path):
            self.report({'ERROR'}, f"Face take CSV not found: {csv_path}")
            return {'CANCELLED'}

        target = bpy.data.objects.get("HIHO Test Face")
        if target is None:
            active = context.active_object
            if (active is not None and active.type == 'MESH'
                    and active.data.shape_keys is not None):
                target = active
        if target is None:
            self.report({'ERROR'},
                        "No face to put this on. Click Spawn Test Face first "
                        "(or select a face mesh that has ARKit shape keys).")
            return {'CANCELLED'}

        take_label = os.path.basename(os.path.dirname(csv_path)) \
            or os.path.splitext(os.path.basename(csv_path))[0]

        try:
            parsed = parse_llf_csv(csv_path)
            matched, missing, last_frame = apply_face_take(
                target, parsed, context.scene, take_label, csv_path)
        except FaceTakeError as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        except Exception as exc:
            self.report({'ERROR'},
                        f"Load Face Take failed: {type(exc).__name__}: {exc}")
            return {'CANCELLED'}

        duration = parsed["times"][-1] if parsed["times"] else 0.0
        msg = (f"{take_label} on {target.name}: {len(parsed['times'])} frames "
               f"({duration:.1f}s at {parsed['fps']:.0f} fps), "
               f"{len(matched)} of {len(parsed['shape_names'])} sliders"
               f" ({parsed['kind']} file). Press Spacebar to play.")
        for warning in parsed["warnings"]:
            self.report({'WARNING'}, warning)
        if missing:
            self.report({'WARNING'},
                        f"{len(missing)} slider(s) not on {target.name}: "
                        + ", ".join(missing[:5])
                        + ("..." if len(missing) > 5 else ""))

        # A fresh load lands unshifted at the scene start, so the face side
        # of any earlier Line Up Face is stale: clear it (the body flash mark
        # stays — the body take hasn't moved).
        settings = context.scene.hiho_mocap
        settings.flash_face_frame = -1.0
        settings.face_flash_offset_at_mark = 0.0
        settings.face_applied_offset = 0.0

        STATE["status_text"] = msg
        self.report({'INFO'}, msg)
        return {'FINISHED'}
