"""
QUADRE — User-facing properties.

Only the knobs a student might actually need.
Everything else is hard-coded to character-friendly defaults.
"""

import bpy
from bpy.props import BoolProperty, IntProperty
from bpy.types import PropertyGroup


class QuadreProperties(PropertyGroup):
    """Properties exposed in the QUADRE UI panel."""

    symmetry_x: BoolProperty(
        name="X",
        description="Symmetrical quads across the X axis",
        default=False,
    )

    symmetry_y: BoolProperty(
        name="Y",
        description="Symmetrical quads across the Y axis",
        default=False,
    )

    # Speaks the same language as the paid remesher the class demos use:
    # an absolute number of quads, typed straight in. Replaced the 0–1
    # "Low ↔ High" Detail slider on 2026-09-16 — students follow the
    # recorded demos, and the demos say "set the quad count to 500"
    quad_count: IntProperty(
        name="Quad Count",
        description=(
            "How many quads you want in the clean shape. "
            "500–5,000 is the sweet spot for characters: lower is easier "
            "to rig and paint, higher keeps more detail. The finish message "
            "says how close the engine landed"
        ),
        min=100,
        soft_max=25_000,
        max=50_000,      # engine tops out near 38K faces (see v0.3.8 notes)
        default=5000,
    )
