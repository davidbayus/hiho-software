# SPDX-License-Identifier: GPL-3.0-or-later
"""PPParty marionette subpackage.

Curriculum order (read in this sequence):
    1. capsules.py      — the Minkowski capsule primitive
    2. materials.py     — material sockets and passthrough
    3. blob_head.py     — blob puppet as a GN group
    4. body_parts.py    — anatomy composition (hands, feet, etc.)
    5. face_tracking.py — ARKit inputs
    6. body_movement.py — face-channel → body-motion mapping
    7. physics.py       — sim zone, Verlet, IK
    8. studio_track.py  — Object Info mesh overrides
    9. assembly.py      — orchestrator (reads like a table of contents)

Shared helpers live in _common.py. See REFACTOR_PLAN.md in the PPPARTY root.
"""
