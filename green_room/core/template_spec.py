"""Template validation — checks that a .blend file is a valid puppet template.

A valid puppet template must have:
1. A mesh object with a Geometry Nodes modifier
2. The geonode tree must have a "Face Tracking" panel with recognized ARKit inputs
3. An armature with a bone named "head" (for phone head rotation)
4. Optionally: an ARKitShapeKeys.Dummy mesh with shape keys
5. Optionally: a "Customize" panel with kid-friendly parameter inputs

Validation returns a TemplateInfo dataclass with everything the loader
needs to instantiate and wire up the template.
"""

from dataclasses import dataclass, field
from typing import Optional


# The minimum ARKit inputs a template needs for basic face performance.
# Templates can have more, but must have at least these.
REQUIRED_FACE_INPUTS = {'jawOpen', 'eyeBlinkLeft', 'eyeBlinkRight'}

# All recognized face tracking input names (matching ARKit blend shapes).
# Inputs with these names get wired to the dummy mesh automatically.
KNOWN_FACE_INPUTS = {
    'jawOpen', 'mouthSmileRight', 'mouthFunnel', 'mouthPucker', 'mouthClose',
    'eyeBlinkLeft', 'eyeBlinkRight', 'eyeWideLeft', 'eyeWideRight',
    'eyeLookInLeft', 'eyeLookInRight', 'eyeLookOutLeft', 'eyeLookOutRight',
}


@dataclass
class SocketInfo:
    """Info about one geonode Group Input socket."""
    name: str
    identifier: str  # e.g. "Socket_2" — used in driver paths
    socket_type: str  # e.g. "NodeSocketFloat"
    default_value: object = None
    min_value: float = 0.0
    max_value: float = 1.0
    panel: str = ""  # Parent panel name, if any


@dataclass
class TemplateInfo:
    """Everything the loader needs to instantiate a puppet template."""
    # The puppet mesh object name
    puppet_object: str = ""
    # The geometry nodes modifier name
    modifier_name: str = ""
    # The node tree name
    node_tree: str = ""
    # Armature object name
    armature: str = ""
    # Head bone name on the armature
    head_bone: str = "head"
    # Dummy mesh name (if present in template)
    dummy_mesh: Optional[str] = None
    # Face tracking inputs (name -> SocketInfo)
    face_inputs: dict = field(default_factory=dict)
    # Customization inputs (name -> SocketInfo)
    customize_inputs: dict = field(default_factory=dict)
    # Validation errors (empty = valid)
    errors: list = field(default_factory=list)
    # Validation warnings (non-fatal)
    warnings: list = field(default_factory=list)

    @property
    def is_valid(self):
        return len(self.errors) == 0


def _read_sockets(tree):
    """Read all input sockets from a geonode tree interface.

    Returns a dict: panel_name -> list of SocketInfo.
    Sockets not in a panel go under "".

    Skips panel items entirely — just reads sockets and gets
    their parent panel name directly. Works in Blender 5.0+.
    """
    sockets_by_panel = {}  # panel name -> [SocketInfo, ...]

    for item in tree.interface.items_tree:
        # Only care about input sockets — skip panels, outputs, etc.
        if not hasattr(item, 'in_out') or item.in_out != 'INPUT':
            continue

        # Get parent panel name (if any)
        panel_name = ""
        if hasattr(item, 'parent') and item.parent:
            panel_name = getattr(item.parent, 'name', "")

        # Get socket identifier (for driver paths)
        sock_id = getattr(item, 'identifier', item.name)

        info = SocketInfo(
            name=item.name,
            identifier=sock_id,
            socket_type=item.socket_type,
            panel=panel_name,
        )
        # Read value range for numeric sockets
        if hasattr(item, 'default_value'):
            info.default_value = item.default_value
        if hasattr(item, 'min_value'):
            info.min_value = item.min_value
        if hasattr(item, 'max_value'):
            info.max_value = item.max_value

        sockets_by_panel.setdefault(panel_name, []).append(info)

    return sockets_by_panel


def validate_template(objects, node_groups):
    """Validate a set of Blender objects/node_groups as a puppet template.

    Pass in the objects and node_groups from a loaded .blend file.
    Returns a TemplateInfo with results.

    Args:
        objects: iterable of bpy.types.Object (from appended/linked data)
        node_groups: iterable of bpy.data.node_groups (from appended/linked data)
    """
    info = TemplateInfo()

    # --- Find the puppet mesh (has a Geometry Nodes modifier) ---
    puppet_obj = None
    for obj in objects:
        if obj.type != 'MESH':
            continue
        for mod in obj.modifiers:
            if mod.type == 'NODES' and mod.node_group:
                puppet_obj = obj
                info.puppet_object = obj.name
                info.modifier_name = mod.name
                info.node_tree = mod.node_group.name
                break
        if puppet_obj:
            break

    if not puppet_obj:
        info.errors.append("No mesh with a Geometry Nodes modifier found")
        return info

    # --- Find the armature with a "head" bone ---
    armature_found = False
    for obj in objects:
        if obj.type != 'ARMATURE':
            continue
        for bone in obj.data.bones:
            if bone.name.lower() == 'head':
                info.armature = obj.name
                info.head_bone = bone.name
                armature_found = True
                break
        if armature_found:
            break

    if not armature_found:
        info.errors.append('No armature with a "head" bone found')

    # --- Check for dummy mesh ---
    for obj in objects:
        if obj.type == 'MESH' and 'ARKitShapeKeys' in obj.name:
            if obj.data.shape_keys:
                info.dummy_mesh = obj.name
                break

    # --- Read geonode interface sockets ---
    tree = puppet_obj.modifiers[info.modifier_name].node_group
    sockets_by_panel = _read_sockets(tree)

    # Classify sockets into face tracking vs customization
    for panel_name, sockets in sockets_by_panel.items():
        for sock in sockets:
            if sock.name in KNOWN_FACE_INPUTS or panel_name == "Face Tracking":
                info.face_inputs[sock.name] = sock
            else:
                info.customize_inputs[sock.name] = sock

    # --- Validate face tracking inputs ---
    found_face = set(info.face_inputs.keys())
    missing = REQUIRED_FACE_INPUTS - found_face
    if missing:
        info.errors.append(
            f"Missing required face tracking inputs: {', '.join(sorted(missing))}"
        )

    # Warn about unknown face inputs in the Face Tracking panel
    for name in found_face - KNOWN_FACE_INPUTS:
        info.warnings.append(f"Unknown face input '{name}' — won't be driven by phone")

    if not info.customize_inputs:
        info.warnings.append("No customization inputs found — kids won't have sliders")

    return info
