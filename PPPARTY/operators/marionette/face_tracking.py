# SPDX-License-Identifier: GPL-3.0-or-later
"""Face tracking inputs — the 18 ARKit shape keys + 3 head rotation axes.

=============================================================================
Why this file exists
=============================================================================
The puppet's face isn't animated by hand — a webcam watches the performer
and MediaPipe produces 52 ARKit-compatible "blend shapes" every frame.
PPParty subscribes to 18 of those (the ones actually wired to the blob
head and body movement) plus 3 head rotation angles, and exposes each one
as a float socket on the Geometry Nodes modifier.

This module creates those sockets. The OSC / MediaPipe receiver on the
other side of the pipeline writes values into them at ~30 Hz, and
downstream nodes in the tree read them to drive facial expressions,
torso sway, and the rest of the body-movement cascade.

=============================================================================
What's an ARKit blend shape?
=============================================================================
Apple's ARKit defines 52 named facial expressions — `jawOpen`, `eyeBlinkLeft`,
`mouthSmileLeft`, etc. Each one is a normalized 0..1 "intensity." The
webcam tracker (MediaPipe Face Landmarker) outputs the same 52 names, so
any pipeline that speaks ARKit — Apple's Live Link Face, MediaPipe, or
third-party tools — can drive the puppet without translation.

We only subscribe to 18 of the 52 because those are the ones the blob head
and body-movement code actually reads. Adding a new one later is a two-line
edit: add the name to FACE_INPUTS, and hook up whatever geometry reads it.

=============================================================================
Why direct modifier push, not drivers?
=============================================================================
In Blender 5.0–5.1 you could wire a shape key's `.value` to a GN modifier
input via a driver — "whenever the shape key changes, update this socket."
Blender 5.2 refactored the RNA paths for GN modifier properties, and that
driver pattern stopped working silently: no error, the socket just never
updated.

Our workaround is older and dumber than drivers: the receiver writes the
value into the modifier as a Python dict set —

    mod[socket_id] = value

— and calls `obj.update_tag()` so Blender knows to re-evaluate. No driver
graph involved. Just: receive a number over UDP, stuff it into the right
socket, tell Blender the modifier is dirty.

That's also why every socket this module creates is marked
`hide_in_modifier = True`. The student never touches these sliders by
hand — the webcam drives them. Hiding them keeps the modifier panel
uncluttered and stops the student from wondering why a "jawOpen" slider
isn't making the puppet's mouth open (it would, until the next frame when
the receiver overwrites it).

=============================================================================
What this module exports
=============================================================================
    FACE_INPUTS                    — list of 18 ARKit blend-shape names.
                                     Used by blob_head passthrough (to skip
                                     face-driven inputs when enumerating
                                     customization sockets) and by
                                     build_blob_group (to wire face inputs
                                     through to the blob head).
    HEAD_ROT_INPUTS                — tuple of 3 head rotation axis names
                                     (headRotX, headRotY, headRotZ).
    build_face_tracking_interface  — creates both panels + all 21 sockets
                                     on a tree's interface.
"""


# ===========================================================================
# FACE_INPUTS — the 18 ARKit blend shapes PPParty reads
# ===========================================================================
# Order here doesn't matter for correctness — the receiver matches sockets
# by NAME, not by index — but grouping by facial region makes the list
# easier to skim:
#
#   Jaw + mouth shape :  jawOpen, mouthSmile L/R, mouthFunnel, mouthPucker
#   Mouth corner     :  mouthFrown L/R, mouthLeft, mouthRight, mouthClose
#   Eyes             :  eyeBlink L/R, eyeWide L/R, eyeLookIn L/R
#   Cheeks           :  cheekSquint L/R

FACE_INPUTS = [
    'jawOpen', 'mouthSmileLeft', 'mouthSmileRight',
    'mouthFunnel', 'mouthPucker',
    'mouthFrownLeft', 'mouthFrownRight', 'mouthLeft', 'mouthRight',
    'mouthClose', 'eyeBlinkLeft', 'eyeBlinkRight',
    'eyeWideLeft', 'eyeWideRight', 'eyeLookInLeft', 'eyeLookInRight',
    'cheekSquintLeft', 'cheekSquintRight',
]


# ===========================================================================
# HEAD_ROT_INPUTS — the 3 head rotation axes
# ===========================================================================
# These are Euler angles in radians (not ARKit blend shapes). MediaPipe
# produces them from the face landmarker's transformation matrix; the OSC
# receiver writes them into these sockets the same way it writes face
# inputs.
#
# Downstream: headRot{X,Y,Z} are used by the blob head transform (to rotate
# the whole head group) and by body_movement code (e.g. headRotY drives
# lateral torso sway and gait).

HEAD_ROT_INPUTS = ('headRotX', 'headRotY', 'headRotZ')


# ===========================================================================
# build_face_tracking_interface — add both panels to a tree
# ===========================================================================
# In Blender, a GN modifier exposes whatever "Group Input" sockets the tree
# declares on its interface. Those sockets become the controls a user sees
# in the modifier panel. `new_panel(...)` and `new_socket(...)` are the two
# API calls that add entries to that interface.
#
# `hide_in_modifier = True` tells Blender "don't render this socket in the
# modifier UI." The socket still exists in the tree and can be written to
# programmatically — it just doesn't show up as a slider the student can
# grab. That's exactly what we want for plumbing.

def build_face_tracking_interface(tree):
    """Create Face Tracking + Head Rotation panels on `tree`'s interface.

    Adds 18 FACE_INPUTS sockets (0..1 floats, FACTOR subtype) under a
    "Face Tracking" panel, then 3 HEAD_ROT_INPUTS sockets (±π floats)
    under a "Head Rotation" panel. Every socket is marked
    `hide_in_modifier = True` — they're plumbing, not controls the
    student adjusts.

    Call this after `tree.interface.clear()` (so the panels land at the
    top of the interface where the receiver expects them) and before
    creating any downstream sockets that might need to reference the face
    inputs by name.

    Returns None. Once a Group Input node exists in the tree, the sockets
    are addressable via `group_in.outputs[name]` — e.g.
    `group_in.outputs['jawOpen']` or `group_in.outputs['headRotY']`.
    """
    # Face tracking (driven by MediaPipe / Live Link Face receiver).
    # These are plumbing: the receiver writes per-frame, no student ever
    # touches them by hand, so they stay hidden from the modifier UI.
    ft_panel = tree.interface.new_panel("Face Tracking")
    for name in FACE_INPUTS:
        s = tree.interface.new_socket(
            name, in_out='INPUT', socket_type='NodeSocketFloat',
            parent=ft_panel)
        s.default_value = 0.0
        s.min_value = 0.0
        s.max_value = 1.0
        s.subtype = 'FACTOR'
        s.hide_in_modifier = True

    # Head rotation (driven by armature head bone) — also plumbing.
    rot_panel = tree.interface.new_panel("Head Rotation")
    for rname in HEAD_ROT_INPUTS:
        s = tree.interface.new_socket(
            rname, in_out='INPUT', socket_type='NodeSocketFloat',
            parent=rot_panel)
        s.default_value = 0.0
        s.min_value = -3.14159
        s.max_value = 3.14159
        s.hide_in_modifier = True
