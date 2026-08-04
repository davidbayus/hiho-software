"""HIHO MOCAP — artist-friendly multi-camera mocap on current Blender.

Free, open-source Blender addon. Records a multi-webcam rig, runs FreeMoCap
in an EXTERNAL Python env (as a watched subprocess — never inside Blender;
see external/ + core/external_runner.py), and builds the animated skelly rig
from the output. That headless split is what lets the addon run on current
Blender with zero bundled wheels. Maintained by the HIHO 4D ART CLUB at SJSU.
See HIHO_MOCAP_WRAPPER_ARCHITECTURE.md + AUDIT_2026-06-09.md.
"""

bl_info = {
    "name": "HIHO MOCAP",
    "author": "David Bayus + HIHO 4D ART CLUB",
    "version": (1, 4, 38),
    "blender": (5, 0, 0),
    "location": "View3D > N-panel > HIHO MOCAP",
    "description": "Multi-camera mocap: record, process via an external FreeMoCap env, spawn an animated rig.",
    "category": "Animation",
}

import bpy

from .properties import HIHO_MOCAP_AddonPreferences, HIHO_MOCAP_PG_settings
from .operators import shutdown as _operator_state_shutdown
from .operators.external_capture import (
    HIHO_MOCAP_OT_preview_cameras,
    HIHO_MOCAP_OT_record_external,
    HIHO_MOCAP_OT_stop_capture,
)
from .operators.process import (
    HIHO_MOCAP_OT_process_mocap,
    HIHO_MOCAP_OT_cancel_process,
)
from .operators.autorig import HIHO_MOCAP_OT_auto_rig
from .operators.import_character import HIHO_MOCAP_OT_import_character
from .operators.markers import (
    HIHO_MOCAP_OT_add_markers,
    HIHO_MOCAP_OT_mirror_markers,
)
from .operators.bake_animation import HIHO_MOCAP_OT_bake_animation
from .operators.face_sync import (
    HIHO_MOCAP_OT_add_face_video,
    HIHO_MOCAP_OT_line_up_face,
    HIHO_MOCAP_OT_mark_flash_body,
    HIHO_MOCAP_OT_mark_flash_face,
)
from .operators.load_face_take import HIHO_MOCAP_OT_load_face_take
from .operators.load_take import HIHO_MOCAP_OT_load_take
from .operators.output import HIHO_MOCAP_OT_spawn_output_rig
from .operators.save_out import HIHO_MOCAP_OT_save_out
from .operators.send_to_character import HIHO_MOCAP_OT_send_to_character
from .operators.spawn_rig import HIHO_MOCAP_OT_spawn_rig
from .operators.spawn_test_face import HIHO_MOCAP_OT_spawn_test_face
from .operators.video_planes import HIHO_MOCAP_OT_add_camera_videos
from .operators.calibration import (
    HIHO_MOCAP_OT_check_calibration,
    HIHO_MOCAP_OT_record_calibration,
    HIHO_MOCAP_OT_solve_calibration,
)
from .operators.volume_map import HIHO_MOCAP_OT_volume_map
from .ui.panels import HIHO_MOCAP_PT_main
from .panel.studio_panel import (
    HIHO_MOCAP_OT_studio_stub,
    HIHO_MOCAP_PT_studio,
)


_classes = (
    HIHO_MOCAP_PG_settings,
    HIHO_MOCAP_AddonPreferences,
    HIHO_MOCAP_OT_preview_cameras,
    HIHO_MOCAP_OT_record_external,
    HIHO_MOCAP_OT_stop_capture,
    HIHO_MOCAP_OT_process_mocap,
    HIHO_MOCAP_OT_cancel_process,
    HIHO_MOCAP_OT_import_character,
    HIHO_MOCAP_OT_add_markers,
    HIHO_MOCAP_OT_auto_rig,
    HIHO_MOCAP_OT_mirror_markers,
    HIHO_MOCAP_OT_bake_animation,
    HIHO_MOCAP_OT_add_face_video,
    HIHO_MOCAP_OT_line_up_face,
    HIHO_MOCAP_OT_mark_flash_body,
    HIHO_MOCAP_OT_mark_flash_face,
    HIHO_MOCAP_OT_load_face_take,
    HIHO_MOCAP_OT_load_take,
    HIHO_MOCAP_OT_send_to_character,
    HIHO_MOCAP_OT_save_out,
    HIHO_MOCAP_OT_spawn_output_rig,
    HIHO_MOCAP_OT_spawn_rig,
    HIHO_MOCAP_OT_spawn_test_face,
    HIHO_MOCAP_OT_add_camera_videos,
    HIHO_MOCAP_OT_check_calibration,
    HIHO_MOCAP_OT_record_calibration,
    HIHO_MOCAP_OT_solve_calibration,
    HIHO_MOCAP_OT_volume_map,
    HIHO_MOCAP_OT_studio_stub,
    HIHO_MOCAP_PT_main,
    HIHO_MOCAP_PT_studio,
)


# RETIRED (2026-06-09, audit M16): the bundled-ajc27 self-installer below is
# from the dissolved pre-headless architecture. register() no longer calls it
# — core/ is self-sufficient and shipped zips exclude vendor/, so it could
# only ever print misleading warnings. Kept on disk per the never-delete
# policy; do not re-wire without reading AUDIT_2026-06-09.md.
#
# (Original rationale: ajc27 uses absolute imports that only resolve from the
# top of sys.path, so it was copied into Blender's user addons dir, tracked
# with a marker file.)
_AJC27_ADDON_NAME = "ajc27_freemocap_blender_addon"
_AJC27_BUNDLED_VERSION = "v2026.04.1041"
_AJC27_MARKER_FILENAME = ".hiho_mocap_managed"


def _ensure_ajc27_installed():
    """Copy bundled ajc27 to Blender's user addons dir if not present or out of date.

    Returns: 'installed' | 'updated' | 'current' | 'foreign' | 'missing'.
    'foreign' means a non-HIHO ajc27 is already there. Leave it alone.
    """
    import shutil
    from pathlib import Path

    bundled_src = Path(__file__).parent / "vendor" / _AJC27_ADDON_NAME
    if not bundled_src.exists():
        print(f"HIHO MOCAP: bundled ajc27 missing at {bundled_src}, skipping install.")
        return "missing"

    user_addons = Path(bpy.utils.user_resource("SCRIPTS", path="addons", create=True))
    install_dst = user_addons / _AJC27_ADDON_NAME
    marker_path = install_dst / _AJC27_MARKER_FILENAME

    if install_dst.exists() and not marker_path.exists():
        print(f"HIHO MOCAP: ajc27 already installed at {install_dst} (no HIHO marker), leaving alone.")
        return "foreign"

    current_version = marker_path.read_text().strip() if marker_path.exists() else None
    if current_version == _AJC27_BUNDLED_VERSION:
        return "current"

    if install_dst.exists():
        shutil.rmtree(install_dst)
    shutil.copytree(bundled_src, install_dst)
    marker_path.write_text(_AJC27_BUNDLED_VERSION)
    state = "updated" if current_version is not None else "installed"
    print(f"HIHO MOCAP: {state} ajc27 {_AJC27_BUNDLED_VERSION} to {install_dst}")
    return state


def _enable_ajc27():
    """Enable the ajc27 addon if it is not already enabled."""
    if _AJC27_ADDON_NAME in bpy.context.preferences.addons:
        return False
    try:
        bpy.ops.preferences.addon_enable(module=_AJC27_ADDON_NAME)
        print(f"HIHO MOCAP: enabled {_AJC27_ADDON_NAME}")
        return True
    except Exception as e:
        print(f"HIHO MOCAP: failed to enable {_AJC27_ADDON_NAME}: {e!r}")
        return False


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.hiho_mocap = bpy.props.PointerProperty(type=HIHO_MOCAP_PG_settings)


def unregister():
    _operator_state_shutdown()
    if hasattr(bpy.types.Scene, "hiho_mocap"):
        del bpy.types.Scene.hiho_mocap
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
