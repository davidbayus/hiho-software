# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared helpers used across marionette modules.

Anything imported in more than one marionette module lives here:
    add_node         — create a GN node at a position with an optional label
    FRAME_COLORS     — color palette for section Frame nodes
    _snap_nodes      — snapshot node names before a section starts
    _new_nodes       — list nodes added since a snapshot
    _frame_section   — wrap a group of nodes in a labeled, colored Frame

These are pure utilities — no puppet-specific logic.
"""


# ===================================================================
# NODE CREATION HELPER
# ===================================================================

def add_node(tree, node_type, x, y, label=None):
    """Add a node to the tree at position (x, y) with optional label."""
    node = tree.nodes.new(node_type)
    node.location = (x, y)
    if label:
        node.label = label
    return node


# ===================================================================
# NODE TREE ORGANIZATION — colored frames for readability
# ===================================================================
# Purely visual. No functional changes to the node tree.
# Each section of the marionette gets a labeled, colored Frame node
# so the GN editor reads like a blueprint of the puppet's design.

FRAME_COLORS = {
    'face':     (0.25, 0.55, 0.65),  # Teal — the puppet's head/expressions
    'control':  (0.30, 0.40, 0.70),  # Blue — control bar (input mapping)
    'strings':  (0.70, 0.50, 0.25),  # Orange — strings (torso dynamics)
    'attach':   (0.65, 0.60, 0.30),  # Yellow — attachment points
    'rest':     (0.55, 0.55, 0.40),  # Olive — rest positions
    'simzone':  (0.50, 0.30, 0.50),  # Purple — simulation zone boundary
    'physics':  (0.65, 0.30, 0.35),  # Red — physics core
    'float':    (0.55, 0.35, 0.60),  # Violet — shoulder float
    'verlet':   (0.70, 0.25, 0.30),  # Dark red — Verlet integration
    'body':     (0.35, 0.60, 0.35),  # Green — visual body parts
    'skeleton': (0.40, 0.55, 0.50),  # Teal-green — limb curves / IK
    'output':   (0.50, 0.50, 0.50),  # Grey — final assembly
}


def _snap_nodes(tree):
    """Snapshot current node names for section framing."""
    return {n.name for n in tree.nodes}


def _new_nodes(tree, snap):
    """Get nodes added since snapshot (excluding Frame nodes)."""
    return [n for n in tree.nodes
            if n.name not in snap and n.type != 'FRAME']


def _frame_section(tree, label, color_key, nodes):
    """Wrap nodes in a labeled, colored Frame for GN editor readability.

    Purely visual — does not change any node connections or behavior.
    """
    if not nodes:
        return None
    frame = tree.nodes.new('NodeFrame')
    frame.label = label
    frame.use_custom_color = True
    frame.color = FRAME_COLORS[color_key]
    frame.label_size = 20
    frame.shrink = True
    for n in nodes:
        if n.parent is None:
            n.parent = frame
    return frame
