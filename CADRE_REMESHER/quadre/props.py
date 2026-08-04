"""
QUADRE — User-facing properties.

Only the knobs a student might actually need.
Everything else is hard-coded to character-friendly defaults.
"""

import bpy
from bpy.props import BoolProperty, FloatProperty
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

    detail: FloatProperty(
        name="Detail",
        description=(
            "Slide right for more detail (more faces), left for less. "
            "Middle aims for about 5,000 faces no matter how dense your sculpt is"
        ),
        min=0.0,
        max=1.0,
        default=0.5,
        subtype="FACTOR",
    )
