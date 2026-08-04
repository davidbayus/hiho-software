# SPDX-License-Identifier: GPL-3.0-or-later
"""The blob head — Green Room's face, absorbed as a reusable GN Group node.

=============================================================================
What this module does
=============================================================================
Before V1.0.0, PPParty and Green Room were two separate addons. Green Room
drew the face, PPParty drew the body. They're now one addon: the blob head
is baked into a .blend file (blob_puppet.blend) and loaded as a Geometry
Nodes "Group" — a reusable sub-tree.

This file answers three questions:
    1. How do we LOAD the blob head from its .blend file?
         → load_blob_head_tree
    2. What CUSTOMIZATION SLIDERS does the blob expose?
         → enumerate_blob_custom_sockets
    3. How do we WIRE the blob into the marionette tree?
         → add_head_customization_sockets + build_blob_group

=============================================================================
Why the blob is a "node group" and not just inline nodes
=============================================================================
A Group node in Geometry Nodes is like a function call. You build the
logic once (in blob_puppet.blend), then every marionette that needs a face
just drops that Group node into its tree. If David tweaks the blob — a new
slider, a different eye shape — we re-save blob_puppet.blend and every
marionette picks up the change automatically on the next Create Marionette.

It also means the blob is READABLE as a standalone artist tool. A student
can open blob_puppet.blend, see the face logic by itself, and tinker
without the ~3700-line marionette code getting in the way.

=============================================================================
The auto-passthrough pattern — why this file has so little code
=============================================================================
The blob exposes 37+ customization sliders (eye size, ear spread, brow
height, nine material slots, and so on). We DON'T hand-duplicate those 37
sockets on the marionette interface — that would mean editing two files
every time David adds a slider.

Instead, at build time we READ the blob's interface, COPY each slider onto
the marionette's interface under a panel like "Head Shape" / "Eyes" /
"Mouth", and WIRE marionette socket → blob group input. Adding a new
slider to the blob just works — PPParty picks it up next Create Marionette.

The small trick: the blob calls its main-shape panel "Body" and names
those sockets "Body Width", "Body Height", etc. In the marionette context
"Body" means the torso, not the head, so we RENAME four sockets on the
way through:

    "Body Width"    → "Head Width"
    "Body Height"   → "Head Height"
    "Body Rotation" → "Head Tilt"
    "Body Material" → "Head Material"

Face tracking sockets (jawOpen, eyeBlinkLeft, …) are SKIPPED during this
auto-passthrough — those values come from the webcam/phone, not an
N-panel slider, so build_blob_group wires them separately.

=============================================================================
Public entry points
=============================================================================
    load_blob_head_tree()
        Import GN_BlobPuppet from blob_puppet.blend. Idempotent.

    enumerate_blob_custom_sockets(blob_tree, face_inputs)
        Walk the blob's interface; return a list of
        (pp_name, blob_name, socket_type, default, min, max, subtype, panel)
        tuples, one per customization socket (face tracking skipped).

    add_head_customization_sockets(tree, blob_custom)
        For each tuple, create a matching pass-through socket on the
        marionette's interface, grouped by panel.

    build_blob_group(tree, group_in, blob_tree, blob_custom, face_inputs)
        Drop the blob GN Group into the marionette tree and wire its
        face-tracking + customization inputs. Returns the group node so
        the caller can continue wiring its Geometry output downstream.
"""

import os
import bpy

from ._common import add_node


# ===========================================================================
# CONSTANTS
# ===========================================================================
# Path to the bundled blob head .blend. Walk up from THIS file
# (operators/marionette/blob_head.py) to the PPPARTY root, then into assets/.
_THIS_FILE = os.path.abspath(__file__)
_MARIONETTE_DIR = os.path.dirname(_THIS_FILE)        # .../operators/marionette
_OPERATORS_DIR  = os.path.dirname(_MARIONETTE_DIR)   # .../operators
ADDON_DIR       = os.path.dirname(_OPERATORS_DIR)    # .../PPPARTY
ASSETS_DIR      = os.path.join(ADDON_DIR, "assets")
BLOB_HEAD_BLEND = os.path.join(ASSETS_DIR, "blob_puppet.blend")


# Rename blob "Body X" sockets so they don't collide with the marionette's
# own Body Width / Body Material. The blob thinks its blob IS the body; in
# the marionette, the blob is the head. We translate on the way through.
_BLOB_RENAME = {
    'Body Width':    'Head Width',
    'Body Height':   'Head Height',
    'Body Rotation': 'Head Tilt',
    'Body Material': 'Head Material',
}
# Reverse map — currently unused, preserved for symmetry.
_BLOB_UNRENAME = {v: k for k, v in _BLOB_RENAME.items()}


# ===========================================================================
# LOADING THE BLOB HEAD
# ===========================================================================

def load_blob_head_tree():
    """Load the GN_BlobPuppet node group from blob_puppet.blend.

    Returns the node group, or None if loading fails. The blob head is
    loaded as an independent COPY (not linked), so PPParty stays fully
    self-contained — nothing breaks if the source .blend moves later.

    If a group named "GN_BlobPuppet" already exists in this Blender
    session (say the user already ran Create Marionette once), we hand
    back the existing one instead of duplicating it. That property is
    called "idempotent" — calling the function twice has the same
    effect as calling it once.
    """
    existing = bpy.data.node_groups.get("GN_BlobPuppet")
    if existing:
        return existing

    if not os.path.exists(BLOB_HEAD_BLEND):
        print(f"PPParty: blob head not found at {BLOB_HEAD_BLEND}")
        return None

    # `libraries.load` is Blender's way of importing data from another
    # .blend file. The `with` statement gives us two objects:
    #   data_from — what's available in the source file
    #   data_to   — what we want to pull in (we fill this in)
    with bpy.data.libraries.load(BLOB_HEAD_BLEND) as (data_from, data_to):
        if "GN_BlobPuppet" in data_from.node_groups:
            data_to.node_groups = ["GN_BlobPuppet"]

    return bpy.data.node_groups.get("GN_BlobPuppet")


# ===========================================================================
# READING THE BLOB'S CUSTOMIZATION INTERFACE
# ===========================================================================

def enumerate_blob_custom_sockets(blob_tree, face_inputs):
    """Walk the blob's interface; return a list of its customization sockets.

    Each entry is a tuple:
        (pp_name, blob_name, socket_type, default, min, max, subtype, panel)

    where `pp_name` is the name the socket gets on PPParty's interface
    (possibly renamed via _BLOB_RENAME) and `blob_name` is the name it
    keeps inside the blob group.

    Sockets named in `face_inputs` are SKIPPED — those are driven by the
    webcam or phone, not by N-panel sliders. Sockets that are not Float
    or Material are also skipped (e.g. internal vector plumbing the blob
    happens to expose).
    """
    blob_skip = set(face_inputs)
    blob_custom = []

    if blob_tree is None:
        return blob_custom

    for item in blob_tree.interface.items_tree:
        # Only INPUT sockets — Group Outputs are for the blob's result
        # geometry, not customization.
        if not (hasattr(item, 'item_type') and item.item_type == 'SOCKET'
                and item.in_out == 'INPUT'):
            continue
        if item.name in blob_skip:
            continue
        if item.socket_type not in ('NodeSocketFloat',
                                    'NodeSocketMaterial'):
            continue

        pp_name = _BLOB_RENAME.get(item.name, item.name)

        # Blender lets sockets live inside named panels (collapsible UI
        # groups in the N-panel). Read which panel this socket sits
        # under; "Body" on the blob side means main-shape controls,
        # which we re-label to "Head Shape" so kids don't confuse it
        # with the marionette's torso.
        panel = item.parent.name if item.parent else 'Other'
        if panel == 'Body':
            panel = 'Head Shape'

        blob_custom.append((
            pp_name, item.name, item.socket_type,
            getattr(item, 'default_value', None),
            getattr(item, 'min_value', 0.0),
            getattr(item, 'max_value', 1.0),
            getattr(item, 'subtype', 'NONE'),
            panel,
        ))

    return blob_custom


# ===========================================================================
# BUILDING MATCHING SOCKETS ON THE MARIONETTE INTERFACE
# ===========================================================================

def add_head_customization_sockets(tree, blob_custom):
    """Create pass-through sockets on `tree` mirroring `blob_custom`.

    All head sockets are grouped first under their declared sub-panel
    (e.g. "Eyes", "Mouth", "Head Shape"), then all sub-panels are nested
    under ONE parent panel called "Blob Head". The modifier view collapses
    the entire face rig into a single expandable section so the puppet
    panel doesn't scatter seven top-level blob sub-panels across the UI.

    Blender 5.2's `new_panel` doesn't accept a `parent=` keyword, so we
    create panels flat and then re-parent them with `move_to_parent` —
    which DOES accept a parent in 5.2 (requires the `to_position` arg).

    Returns the "Blob Head" parent panel so the caller can nest other
    facial feature sub-panels (e.g. Cheeks) under it.
    """
    head_parent = tree.interface.new_panel("Blob Head")

    head_panels = {}
    for pp_name, blob_name, sock_type, default, mn, mx, subtype, panel in blob_custom:
        if panel not in head_panels:
            head_panels[panel] = tree.interface.new_panel(panel)
        s = tree.interface.new_socket(
            pp_name, in_out='INPUT', socket_type=sock_type,
            parent=head_panels[panel])
        if sock_type == 'NodeSocketFloat':
            s.default_value = default
            s.min_value = mn
            s.max_value = mx
            if subtype and subtype != 'NONE':
                s.subtype = subtype

    # Re-parent every blob sub-panel under the Blob Head parent so the
    # modifier renders one collapsible container instead of a stack of
    # top-level panels.
    #
    # alpha.20 fix: iterate in REVERSE with to_position=0. The previous
    # forward+to_position=-1 pattern left the last few panels (Eyebrows,
    # Lips) stranded at top level in Blender 5.2 — `-1` appears to mean
    # "before the last sibling" rather than "append to end" for some
    # code paths in the interface API. Reverse + 0 sidesteps the issue
    # entirely: each reparent pushes the previously-moved children to
    # positions 1, 2, ..., producing final order
    # Head Shape, Eyes, Mouth, Nose, Ears, Eyebrows, Lips — the natural
    # reading order kids expect.
    for sub_panel in reversed(list(head_panels.values())):
        tree.interface.move_to_parent(sub_panel, head_parent, 0)

    return head_parent


def debug_dump_interface_panels(tree, label):
    """Dump the tree's interface panel/socket hierarchy to a Blender
    text block named "PPParty_Debug_Panels".

    Every call REPLACES the text block contents with the current state,
    so after Create Puppet finishes the block shows the final layout.
    Open the Text Editor and pick "PPParty_Debug_Panels" to read it —
    no terminal or system console required.

    Used to diagnose panel-reparenting regressions in the modifier UI:
    tells you which items actually landed under which parent,
    independent of how Blender RENDERS the modifier panel.
    """
    import bpy

    lines = [f"=== {label} ==="]
    for item in tree.interface.items_tree:
        parent_name = item.parent.name if item.parent else "<root>"
        item_type = getattr(item, 'item_type', '?')
        if item_type == 'SOCKET':
            extra = f"  [{item.in_out} {item.socket_type}]"
        else:
            extra = ""
        lines.append(
            f"  {item_type:7} {item.name!r:30}  "
            f"parent={parent_name!r}{extra}")

    text_name = "PPParty_Debug_Panels"
    text = bpy.data.texts.get(text_name)
    if text is None:
        text = bpy.data.texts.new(text_name)
    text.clear()
    text.write("\n".join(lines) + "\n")


# ===========================================================================
# WIRING THE BLOB GROUP INTO THE MARIONETTE TREE
# ===========================================================================

def build_blob_group(tree, group_in, blob_tree, blob_custom, face_inputs):
    """Drop the blob GN Group into the marionette tree and wire its inputs.

    Creates a GeometryNodeGroup set to `blob_tree` and links two families
    of sockets from the marionette's Group Input:

    1. Face tracking (jawOpen, eyeBlinkLeft, …) — driven by webcam/phone.
    2. Head customization — the sliders and materials discovered by
       enumerate_blob_custom_sockets.

    Returns the GeometryNodeGroup so the caller can continue wiring its
    Geometry output into the body-assembly chain.
    """
    blob_group = add_node(tree, 'GeometryNodeGroup', -3000, 600, "Blob Head")
    blob_group.node_tree = blob_tree

    # What sockets does THIS instance of the blob actually expose?
    # We read the node's effective inputs rather than trusting the
    # interface definition, because Blender sometimes omits sockets
    # whose defaults weren't initialized.
    blob_input_names = {inp.name for inp in blob_group.inputs}

    # Wire face tracking inputs: main tree → blob head Group node
    for name in face_inputs:
        if name in blob_input_names:
            try:
                tree.links.new(group_in.outputs[name],
                               blob_group.inputs[name])
            except KeyError:
                pass

    # Wire head customization passthrough: PPParty slider/material → blob
    for pp_name, blob_name, sock_type, *_ in blob_custom:
        if blob_name in blob_input_names:
            try:
                tree.links.new(group_in.outputs[pp_name],
                               blob_group.inputs[blob_name])
            except KeyError:
                pass

    return blob_group
