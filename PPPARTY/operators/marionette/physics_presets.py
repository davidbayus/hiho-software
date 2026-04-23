# SPDX-License-Identifier: GPL-3.0-or-later
"""Physics presets — preset dictionaries for chain sim + jiggle sim.

=============================================================================
Why this file exists
=============================================================================
PPParty's in-house secondary-motion engine (`operators/marionette/physics.py`)
needs starting-point parameter values. Rather than inventing them from
scratch, we lift them verbatim from Cody Winchester's Goo Physics addon —
the reference implementation our algorithm is patterned after. Cody's
studio has been using these presets in production for two years, so the
numbers are trustworthy.

See `PPPARTY/GOO_PHYSICS_RESEARCH.md` for the full analysis and
`PPPARTY/NATIVE_PHYSICS_DESIGN.md` for how these feed the GN build.

=============================================================================
What's in here
=============================================================================
CHAIN_PRESETS      — 4 named presets for multi-segment chain sim
                     (fingers, skirts, hair — any bone chain that dangles).
                     Each preset is 9 floats matching the interface-socket
                     names in NATIVE_PHYSICS_DESIGN.md §New Group Input.

JIGGLE_PRESETS     — 3 named presets for single-bone spring-mass jiggle.
                     Each preset is 6 floats. Used for palm-corner flop.

CHAIN_PRESET_BY_ROLE — maps PPParty rig roles ("finger") to preset names.
                     Wrist role removed 2026-04-23 per David: V1 has no
                     wrist bone, palm attaches directly to forearm.

JIGGLE_PRESET_FOR_PALM — which jiggle preset the 4 palm corners use.

=============================================================================
What got dropped from Cody's JSON
=============================================================================
- `gp_chain_wind_*` (3 params) — wind forcing. V1 skips; revisit if the
  hand feels too static after tuning.
- `gp_chain_collision_*` (2 params) — collider-collection-based bounce.
  V1 skips; fingers don't need to collide with anything.
- `gp_sim_influence` on chain presets — Cody's per-bone sim-vs-rest
  blend. V1 folds this responsibility into Root Falloff on the chain
  side; preserved on jiggle presets where it's the cleaner knob.

=============================================================================
Float rounding
=============================================================================
Cody's JSON values are float32→float64 round-trips (e.g. `0.10000000149011612`).
We round to the value Cody actually typed in his slider (`0.1`). Precision
beyond ~4 decimals is JSON noise, not tuning intent.

=============================================================================
No Blender dependency
=============================================================================
This file imports nothing. It's importable by the Python prototype
(`/tmp/chain_sim_prototype.py` — scratch, not committed) AND by the
real Blender build pipeline. Keeping it dependency-free lets us tune
the algorithm outside Blender, where iteration is faster.
"""


# ===========================================================================
# CHAIN PRESETS — 4 × 9 params each
# ===========================================================================
# Source: /tmp/goo_reference/goo_physics/presets/geo_nodes_presets.json
# Preset names match Goo's convention (shouty caps) so anyone cross-
# referencing Cody's addon can find the mapping instantly.

CHAIN_PRESETS = {
    "DEFAULTGEONODES": {
        "Chain Velocity":  1.0,
        "Chain Dampening": 0.1,
        "Chain Gravity":   0.02,
        "Root Falloff":    0.25,
        "Chain Stiffness": 0.25,
        "Stiff End Fac":   0.25,
        "Stiff Vel Fac":   0.2,
        "Stiff Vel Min":   0.1,
        "Stiff Vel Max":   1.0,
    },
    "HAIRFRINGE": {
        # Cody: "bangs/fringe — base doesn't move much, slight tip
        # movement to prevent character going off-model." Highest root
        # pinning in the set (0.92). Useful if we want fingers that
        # barely break silhouette.
        "Chain Velocity":  1.0,
        "Chain Dampening": 0.1,
        "Chain Gravity":   0.02,
        "Root Falloff":    0.92,
        "Chain Stiffness": 0.5,
        "Stiff End Fac":   0.2,
        "Stiff Vel Fac":   0.2,
        "Stiff Vel Min":   0.1,
        "Stiff Vel Max":   1.0,
    },
    "HAIRSIDE": {
        # Cody: "medium-length side strands, longer than bangs. Can
        # also be used for skirts." Middle of the road — this is our
        # default pick for PPParty fingers (CHAIN_PRESET_BY_ROLE below).
        "Chain Velocity":  1.0,
        "Chain Dampening": 0.1,
        "Chain Gravity":   0.02,
        "Root Falloff":    0.5,
        "Chain Stiffness": 0.41,
        "Stiff End Fac":   0.2,
        "Stiff Vel Fac":   0.2,
        "Stiff Vel Min":   0.1,
        "Stiff Vel Max":   1.0,
    },
    "HAIRPONYTAIL": {
        # Cody: "long bone chains with lots of drag at the end. Can be
        # used for dresses and capes." Near-zero stiffness = maximum
        # noodle. Probably too floppy for fingers; kept in the dict for
        # completeness and future tuning experiments.
        "Chain Velocity":  1.0,
        "Chain Dampening": 0.1,
        "Chain Gravity":   0.02,
        "Root Falloff":    0.42,
        "Chain Stiffness": 0.0,
        "Stiff End Fac":   0.2,
        "Stiff Vel Fac":   0.2,
        "Stiff Vel Min":   0.1,
        "Stiff Vel Max":   1.0,
    },
}


# ===========================================================================
# JIGGLE PRESETS — 3 × 6 params each
# ===========================================================================
# Source: /tmp/goo_reference/goo_physics/presets/jiggle_spring_presets.json

JIGGLE_PRESETS = {
    "DEFAULTJIGGLE": {
        "Jiggle Speed":          0.8,
        "Jiggle Friction":       5.0,
        "Jiggle Mass":           0.15,
        "Jiggle Stiffness":      0.1,
        "Jiggle Damping":        8.0,
        "Jiggle Sim Influence":  1.0,
    },
    "JIGGLELOOSE": {
        # Cody: "location-based jiggle offset for secondary animation."
        # PPParty palm-corner pick — floppy but not chaotic.
        "Jiggle Speed":          0.77,
        "Jiggle Friction":       5.0,
        "Jiggle Mass":           0.2,
        "Jiggle Stiffness":      0.1,
        "Jiggle Damping":        10.064,
        "Jiggle Sim Influence":  1.0,
    },
    "JIGGLESTIFF": {
        # Cody: "less bounce." 3× the stiffness of LOOSE.
        "Jiggle Speed":          0.83,
        "Jiggle Friction":       5.0,
        "Jiggle Mass":           0.15,
        "Jiggle Stiffness":      0.298,
        "Jiggle Damping":        10.064,
        "Jiggle Sim Influence":  1.0,
    },
}


# ===========================================================================
# ROLE → PRESET MAPPINGS
# ===========================================================================
# Which preset the build pipeline loads for each rig role. Changed these
# to re-tune without touching the per-preset numbers.

CHAIN_PRESET_BY_ROLE = {
    "finger": "HAIRSIDE",
}

JIGGLE_PRESET_FOR_PALM = "JIGGLELOOSE"


# ===========================================================================
# Sanity checks — run at import time so typos fail fast
# ===========================================================================

_EXPECTED_CHAIN_KEYS = {
    "Chain Velocity", "Chain Dampening", "Chain Gravity",
    "Root Falloff", "Chain Stiffness", "Stiff End Fac",
    "Stiff Vel Fac", "Stiff Vel Min", "Stiff Vel Max",
}
_EXPECTED_JIGGLE_KEYS = {
    "Jiggle Speed", "Jiggle Friction", "Jiggle Mass",
    "Jiggle Stiffness", "Jiggle Damping", "Jiggle Sim Influence",
}

for _name, _preset in CHAIN_PRESETS.items():
    assert set(_preset.keys()) == _EXPECTED_CHAIN_KEYS, (
        f"CHAIN_PRESETS['{_name}'] keys drifted from interface sockets: "
        f"extra={set(_preset.keys()) - _EXPECTED_CHAIN_KEYS}, "
        f"missing={_EXPECTED_CHAIN_KEYS - set(_preset.keys())}"
    )

for _name, _preset in JIGGLE_PRESETS.items():
    assert set(_preset.keys()) == _EXPECTED_JIGGLE_KEYS, (
        f"JIGGLE_PRESETS['{_name}'] keys drifted from interface sockets"
    )

assert CHAIN_PRESET_BY_ROLE["finger"] in CHAIN_PRESETS
assert JIGGLE_PRESET_FOR_PALM in JIGGLE_PRESETS

del _name, _preset
