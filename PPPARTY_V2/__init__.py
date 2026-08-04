# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 David Bayus + CADRE Lab (SJSU)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version. See LICENSE for the full text.

"""PPParty V2 — bones-only capture-and-bake puppeteer.

V2 captures student performances pass-by-pass and bakes each pass to
keyframes, composed via the NLA editor into short student animations.
There is no mesh during capture; mesh attaches post-bake.

Two-pass architecture (refactored 2026-04-29):
    Pass 1 — Body + arms + hands (PoseLandmarker + HandLandmarker async)
    Pass 2 — Face (FaceLandmarker)

See V2_DESIGN.md (sibling to this file) for the full architecture.
"""

bl_info = {
    "name": "PPParty V2",
    "author": "David Bayus + CADRE Lab (SJSU)",
    "version": (2, 0, 4),
    "blender": (5, 2, 0),
    "location": "View3D > N-panel > PPPARTY V2",
    "description": "Capture-and-bake puppeteer (V2 — bones-only, two-pass).",
    "category": "Animation",
}

import bpy

from .operators.create_rig import PPPARTY_V2_OT_create_rig
from .operators.mirror import (
    PPPARTY_V2_OT_start_body_mirror,
    PPPARTY_V2_OT_stop_body_mirror,
)
from .operators.record import (
    PPPARTY_V2_OT_start_body_recording,
    PPPARTY_V2_OT_stop_body_recording,
)
from .operators.face_ops import (
    PPPARTY_V2_OT_start_face_mirror,
    PPPARTY_V2_OT_stop_face_mirror,
    PPPARTY_V2_OT_start_face_recording,
    PPPARTY_V2_OT_stop_face_recording,
)
from .ui.panels import PPPARTY_V2_PT_main


_classes = (
    PPPARTY_V2_OT_create_rig,
    PPPARTY_V2_OT_start_body_mirror,
    PPPARTY_V2_OT_stop_body_mirror,
    PPPARTY_V2_OT_start_body_recording,
    PPPARTY_V2_OT_stop_body_recording,
    PPPARTY_V2_OT_start_face_mirror,
    PPPARTY_V2_OT_stop_face_mirror,
    PPPARTY_V2_OT_start_face_recording,
    PPPARTY_V2_OT_stop_face_recording,
    PPPARTY_V2_PT_main,
)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    # Stop any active mirror / recording session before tearing down classes,
    # so we don't leave sender subprocesses, UDP sockets, or in-flight
    # recording state behind.
    try:
        from .core.receiver import get_receiver, get_face_receiver
        from .core.recorder import get_recorder, get_face_recorder
        from .core.sender_launcher import (
            get_sender_process, get_face_sender_process,
        )
        scene = bpy.context.scene

        recorder = get_recorder()
        if recorder.is_recording:
            recorder.stop_recording(scene)
        get_receiver().stop()
        get_sender_process().stop()

        face_recorder = get_face_recorder()
        if face_recorder.is_recording:
            face_recorder.stop_recording(scene)
        get_face_receiver().stop()
        get_face_sender_process().stop()
    except Exception:
        pass

    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
