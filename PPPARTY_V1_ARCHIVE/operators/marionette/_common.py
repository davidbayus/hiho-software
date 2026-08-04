# SPDX-License-Identifier: GPL-3.0-or-later
"""Shared helpers used across the marionette modules.

=============================================================================
Why this file exists
=============================================================================
When you write code that lives in more than one file, Python needs a place
for the "plumbing" the other files reach for — the small utilities that
are NOT about puppets specifically, just about getting nodes onto the
canvas and keeping the Geometry Nodes tree readable.

Think of this file like the pegboard in a shop: it holds the five tools
every workbench borrows. None of these helpers knows anything about arms,
legs, or blob heads.

Helpers in this file:
    add_node        — place a new node on the canvas at a given position
    FRAME_COLORS    — the palette used for the labeled Frames that
                      organize sections of the marionette tree
    _snap_nodes     — "remember which nodes exist in the tree right now"
    _new_nodes      — "list the nodes that appeared since we remembered"
    _frame_section  — wrap a set of nodes in a colored, labeled Frame so
                      the GN editor reads like a blueprint
    _vector_lerp    — blend two Vector sockets by a float factor
                      (result = a + (b - a) * factor)

About the leading underscore on some names: in Python, a leading
underscore is a convention meaning "this is internal to the package —
don't import it from outside." It doesn't change behavior; it's a hint
to other readers (and to your future self) that these are implementation
details, not public API.
"""


# ===========================================================================
# NODE CREATION HELPER
# ===========================================================================
# `add_node` is the most-called helper in the refactor. Every single
# geometry node in the marionette tree — and there are ~217 of them —
# comes through here. A tiny convenience that pays off hundreds of
# times per build.

def add_node(tree, node_type, x, y, label=None):
    """Add a node to a GN tree at position (x, y), optionally labeled.

    Think of `tree` as the blank Geometry Nodes editor canvas. `node_type`
    is the node you'd pick from the Add menu (e.g. 'ShaderNodeMath' for
    a Math node, 'GeometryNodeMeshCube' for a Cube primitive). `(x, y)`
    is where it lands. `label` is the little text in the node header —
    super useful for reading the tree later.
    """
    node = tree.nodes.new(node_type)
    node.location = (x, y)
    if label:
        node.label = label
    return node


# ===========================================================================
# NODE TREE ORGANIZATION — colored frames for readability
# ===========================================================================
# These colors are purely cosmetic. A Frame in the GN editor is like a
# colored background box you can drag around a group of nodes. We give
# each "section" of the puppet its own color so the tree reads like a
# labeled blueprint instead of a spaghetti graph.
#
# FRAME_COLORS is a Python `dict` — a lookup table from a short name
# ('face', 'strings', …) to an RGB triplet. Using a dict here instead
# of a long `if/elif` chain keeps the code short and makes it easy to
# add a new section color later without touching any other code.

FRAME_COLORS = {
    'face':     (0.25, 0.55, 0.65),  # Teal — the puppet's head / expressions
    'control':  (0.30, 0.40, 0.70),  # Blue — control bar (input mapping)
    'strings':  (0.70, 0.50, 0.25),  # Orange — marionette strings (torso)
    'attach':   (0.65, 0.60, 0.30),  # Yellow — attachment points
    'rest':     (0.55, 0.55, 0.40),  # Olive — rest positions
    'simzone':  (0.50, 0.30, 0.50),  # Purple — simulation zone boundary
    'physics':  (0.65, 0.30, 0.35),  # Red — physics core (Verlet, IK)
    'float':    (0.55, 0.35, 0.60),  # Violet — shoulder float
    'verlet':   (0.70, 0.25, 0.30),  # Dark red — Verlet integration
    'body':     (0.35, 0.60, 0.35),  # Green — visual body parts
    'skeleton': (0.40, 0.55, 0.50),  # Teal-green — limb curves / IK
    'output':   (0.50, 0.50, 0.50),  # Grey — final assembly
}


def _snap_nodes(tree):
    """Remember which nodes exist in the tree right now.

    Returns a `set` of node names. A set is like a list, but optimized
    for one specific question: "is this name in the collection?"
    Looking an item up in a set is nearly instant, no matter how big
    the set gets — so when we ask the same "did this node exist
    before?" question across many nodes, a set is the right shape.
    """
    return {n.name for n in tree.nodes}


def _new_nodes(tree, snap):
    """List the nodes that appeared in `tree` since `snap` was taken.

    Compares the current tree against the snapshot and returns
    everything that wasn't there before — minus Frame nodes, since
    those ARE the decorative backgrounds we're about to wrap around
    whatever was added.
    """
    return [n for n in tree.nodes
            if n.name not in snap and n.type != 'FRAME']


def _frame_section(tree, label, color_key, nodes):
    """Wrap `nodes` in a labeled, colored Frame.

    The pattern across the marionette code is:

        snap  = _snap_nodes(tree)          # remember current state
        …build a chunk of the tree…
        fresh = _new_nodes(tree, snap)     # what got added
        _frame_section(tree, label, color_key, fresh)

    That way every section of the puppet ends up visually grouped in
    the GN editor, without having to track node references by hand.

    Purely visual — parenting nodes to a Frame does not change any
    node connections or evaluation behavior.
    """
    if not nodes:
        return None
    frame = tree.nodes.new('NodeFrame')
    frame.label = label
    frame.use_custom_color = True
    frame.color = FRAME_COLORS[color_key]
    frame.label_size = 20
    frame.shrink = True
    # Seed the frame at the bottom-left corner of its children before
    # parenting. shrink=True auto-fits the frame around its contents, but
    # Blender doesn't recompute that until the user first interacts with
    # the editor — so without this, every frame sits at (0, 0) the moment
    # a freshly built .blend is opened, stacked in a pile until dragged.
    # Blender rebases each child's offset when parented, so world
    # positions stay put.
    min_x = min((n.location.x for n in nodes if n.parent is None), default=0.0)
    min_y = min((n.location.y for n in nodes if n.parent is None), default=0.0)
    frame.location = (min_x, min_y)
    for n in nodes:
        if n.parent is None:
            n.parent = frame
    return frame


# ===========================================================================
# VECTOR LERP — blend between two Vector sockets
# ===========================================================================
# Used wherever two vector signals need to cross-fade based on a 0..1 slider.
# The marionette uses this to mix face-heuristic attachment deltas with
# real body-tracking deltas when the "Body Tracking" slider is above 0, and
# to blend default elbow/knee bend axes with expression-driven overrides.
#
# Math: result = a + (b - a) * factor
#   factor = 0 -> result = a
#   factor = 1 -> result = b
# Three nodes: (b - a), scaled by factor, added back to a. Returns the
# final ADD node so the caller can chain `.outputs['Vector']` off it.

def _vector_lerp(tree, x, y, label, a_out, b_out, factor_out):
    """Build a Vector lerp: result = a + (b - a) * factor.

    Returns the output socket of the final ADD node.
    """
    diff = add_node(tree, 'ShaderNodeVectorMath', x, y, f"{label} B-A")
    diff.operation = 'SUBTRACT'
    tree.links.new(b_out, diff.inputs[0])
    tree.links.new(a_out, diff.inputs[1])

    scaled = add_node(tree, 'ShaderNodeVectorMath', x + 200, y,
                      f"{label} *BT")
    scaled.operation = 'SCALE'
    tree.links.new(diff.outputs['Vector'], scaled.inputs[0])
    tree.links.new(factor_out, scaled.inputs['Scale'])

    result = add_node(tree, 'ShaderNodeVectorMath', x + 400, y,
                      f"{label} Lerp")
    result.operation = 'ADD'
    tree.links.new(a_out, result.inputs[0])
    tree.links.new(scaled.outputs['Vector'], result.inputs[1])
    return result
