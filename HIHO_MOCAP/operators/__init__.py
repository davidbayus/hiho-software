"""Module-level runtime state for HIHO MOCAP operators.

Holds live CameraManager + BlenderCameraPreview instances + record-modal
state so different operators can find them. Module-level is the right home —
only one mocap session is active at a time, and these objects aren't
serializable scene state.
"""
import os

import bpy

STATE = {
    "manager": None,                    # CameraManager instance, or None
    "preview": None,                    # BlenderCameraPreview instance, or None
    "recording_modal_active": False,    # True while the Record modal operator is live
    "recording_stop_requested": False,  # Set by the Stop button; record modal honors it
    "processor": None,                  # FreeMocapRunner instance, or None
    "capture": None,                    # ExternalProcessRunner watching record_take.py, or None
    "capture_kind": "",                 # "preview" | "record" | "calibration"
    "capture_take_attr": "",            # scene prop to fill with the take path on success
    "status_text": "",                  # Live status text shown in the panel
}


def get_env_python(context) -> str:
    """The configured FreeMoCap-env python, normalized.

    Machine-level config lives in AddonPreferences (survives restarts and new
    files); the old per-Scene property is deprecated and ignored (audit M18).
    """
    addon = context.preferences.addons.get(__package__.rsplit(".", 1)[0])
    if addon is not None and addon.preferences is not None:
        return norm_path(addon.preferences.freemocap_env_python)
    return ""


def get_data_home(context) -> str:
    """The machine's HIHO data home, expanded to an absolute path.

    HIHO_CAPTURES and HIHO_CALIBRATIONS live under it. Same machine-level
    AddonPreferences home as the env python, for the same reason.
    """
    addon = context.preferences.addons.get(__package__.rsplit(".", 1)[0])
    if addon is not None and addon.preferences is not None:
        home = climb_to_data_home(norm_path(addon.preferences.data_home))
        if home:
            return home
    return os.path.expanduser("~/Desktop")


# Folders the addon itself creates under the data home. "Save to" must never
# point INSIDE one of these.
DATA_HOME_SUBFOLDERS = ("HIHO_CAPTURES", "HIHO_CALIBRATIONS")


def climb_to_data_home(path: str) -> str:
    """Return the real data home even when "Save to" was picked one level deep.

    Blender's folder picker accepts whichever folder you are standing IN, so
    browsing into HIHO_ALL/HIHO_CAPTURES and clicking Accept stores that
    subfolder as the home — and every later take lands at
    HIHO_CAPTURES/HIHO_CAPTURES/<stamp> (seen live 2026-08-17, both kinds).
    If the chosen path is, or sits anywhere below, one of the addon's own
    subfolders, climb to the parent of the OUTERMOST such folder (an already
    doubled HIHO_CAPTURES/HIHO_CAPTURES pick must not stop one level short).
    Anything else passes through.
    """
    if not path:
        return ""
    cur = os.path.normpath(path)
    home = cur
    while True:
        head, tail = os.path.split(cur)
        if not tail or head == cur:
            return home
        if tail in DATA_HOME_SUBFOLDERS:
            home = head
        cur = head


def norm_path(p: str) -> str:
    """Resolve a user-supplied path for os.path checks.

    Blender's file browser stores '//'-relative paths in saved .blend files
    (default "Relative Paths" preference), and students type '~' paths —
    os.path.isdir/isfile reject both, which made the pickers fail exactly
    when they are the restart-recovery mechanism.
    """
    if not p:
        return ""
    return os.path.expanduser(bpy.path.abspath(p))


def shutdown():
    """Tear down any live preview + camera session. Safe to call multiple times.

    `manager.stop()` also stops any in-progress recording — no separate call needed.
    """
    if STATE["preview"] is not None:
        STATE["preview"].stop()
        STATE["preview"] = None
    if STATE["manager"] is not None:
        STATE["manager"].stop()
        STATE["manager"] = None
    if STATE["processor"] is not None:
        STATE["processor"].stop()
        STATE["processor"] = None
    if STATE["capture"] is not None:
        STATE["capture"].stop()
        STATE["capture"] = None
    STATE["capture_kind"] = ""
    STATE["capture_take_attr"] = ""
    STATE["recording_modal_active"] = False
    STATE["recording_stop_requested"] = False
    STATE["status_text"] = ""
