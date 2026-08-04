"""PPParty V2 — Pass 2 hand operators (RETIRED 2026-04-29).

This module used to define Start/Stop Hand Mirror and Start/Stop Hand
Recording for the three-pass architecture. The two-pass refactor
(see V2_DESIGN.md §5 and HANDOFF.md §Phase-6) folded arms + fingers
into Pass 1 (body), so a separate hand pass no longer exists.

The file is preserved as a tombstone — David's hard rule is never to
delete files. It registers no operators and is no longer imported by
the addon's `__init__.py`. The original implementation lives in the
day5e zip (`PPPARTY_V2_v2.0.0-day5e.zip`) if reference is ever needed.

For the body+hands gate previously defined here, see
`operators/_nla.py::body_pass_baked`.
"""
