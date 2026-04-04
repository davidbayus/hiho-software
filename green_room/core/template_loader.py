"""Load, validate, and instantiate puppet templates from .blend files.

A puppet template is a .blend file containing a procedural character
(geometry nodes), an armature with a "head" bone, and optionally an
ARKitShapeKeys.Dummy mesh. This module handles:

1. Discovering available templates (bundled + user templates)
2. Appending template objects into the current scene
3. Validating the template structure
4. Wiring up drivers from the dummy mesh to geonode inputs
"""

import os
from pathlib import Path

import bpy

from .osc_receiver import BLENDSHAPE_MAP, DUMMY_MESH_NAME, ensure_dummy_mesh
from .template_spec import (
    KNOWN_FACE_INPUTS,
    TemplateInfo,
    validate_template,
)


def get_templates_dir():
    """Return the path to the bundled templates directory."""
    return Path(__file__).parent.parent / "assets" / "templates"


def discover_templates():
    """Find all available puppet templates.

    Scans the bundled templates directory for folders containing .blend files.
    Returns a list of dicts with template metadata:
        [{'name': 'Blob', 'path': '/path/to/blob_puppet.blend', 'dir': '/path/to/blob/'}, ...]
    """
    templates_dir = get_templates_dir()
    results = []

    if not templates_dir.exists():
        return results

    for folder in sorted(templates_dir.iterdir()):
        if not folder.is_dir():
            continue

        # Find the first .blend file in the folder
        blends = [f for f in folder.iterdir()
                   if f.suffix == '.blend' and not f.name.endswith('.blend1')]
        if not blends:
            continue

        blend_path = blends[0]

        # Derive a display name from the folder name
        display_name = folder.name.replace('_', ' ').title()

        results.append({
            'name': display_name,
            'path': str(blend_path),
            'dir': str(folder),
        })

    return results


def load_template(blend_path):
    """Append a puppet template from a .blend file into the current scene.

    Steps:
    1. Append all objects from the .blend file
    2. Validate the template structure
    3. Ensure the dummy mesh exists
    4. Wire up drivers from dummy mesh shape keys to geonode inputs

    Args:
        blend_path: Path to the .blend file

    Returns:
        TemplateInfo with validation results. Check info.is_valid.
    """
    blend_path = str(blend_path)

    if not os.path.exists(blend_path):
        info = TemplateInfo()
        info.errors.append(f"File not found: {blend_path}")
        return info

    # --- Append all objects from the template file ---
    existing_objects = set(bpy.data.objects.keys())
    existing_trees = set(bpy.data.node_groups.keys())

    with bpy.data.libraries.load(blend_path, link=False) as (data_from, data_to):
        data_to.objects = data_from.objects
        data_to.node_groups = data_from.node_groups
        data_to.materials = data_from.materials
        data_to.armatures = data_from.armatures

    # Link newly appended objects into the active collection
    new_objects = []
    for obj in data_to.objects:
        if obj is not None and obj.name not in existing_objects:
            bpy.context.collection.objects.link(obj)
            new_objects.append(obj)

    if not new_objects:
        info = TemplateInfo()
        info.errors.append("No objects found in template file")
        return info

    # --- Validate ---
    info = validate_template(new_objects, bpy.data.node_groups)

    if not info.is_valid:
        # Clean up appended objects on failure
        for obj in new_objects:
            bpy.data.objects.remove(obj, do_unlink=True)
        return info

    # --- Ensure dummy mesh + wire drivers ---
    dummy = ensure_dummy_mesh()
    _ensure_dummy_has_keys(dummy, info.face_inputs.keys())

    puppet = bpy.data.objects.get(info.puppet_object)
    if puppet:
        _setup_drivers(puppet, info, dummy)

    # --- Set head bone rotation mode to Euler ---
    armature = bpy.data.objects.get(info.armature)
    if armature and armature.type == 'ARMATURE':
        bone = armature.pose.bones.get(info.head_bone)
        if bone:
            bone.rotation_mode = 'XYZ'

    return info


def _ensure_dummy_has_keys(dummy, face_input_names):
    """Make sure the dummy mesh has shape keys for all face tracking inputs."""
    if not dummy.data.shape_keys:
        dummy.shape_key_add(name='Basis')

    existing = {kb.name for kb in dummy.data.shape_keys.key_blocks}

    for name in face_input_names:
        if name in KNOWN_FACE_INPUTS and name not in existing:
            dummy.shape_key_add(name=name)


def _setup_drivers(puppet, info, dummy):
    """Wire drivers from the dummy mesh shape keys to geonode modifier inputs.

    Each face tracking input on the geometry nodes modifier gets a driver
    that reads the corresponding shape key value from the dummy mesh.
    """
    shape_keys = dummy.data.shape_keys
    if not shape_keys:
        return

    modifier_name = info.modifier_name

    for input_name, sock_info in info.face_inputs.items():
        # Only drive inputs that have matching shape keys
        if input_name not in KNOWN_FACE_INPUTS:
            continue

        kb = shape_keys.key_blocks.get(input_name)
        if not kb:
            continue

        # Check if driver already exists (template may ship with drivers)
        data_path = f'modifiers["{modifier_name}"]["{sock_info.identifier}"]'
        existing_drivers = {d.data_path for d in puppet.animation_data.drivers} \
            if puppet.animation_data else set()
        if data_path in existing_drivers:
            continue

        driver_fc = puppet.driver_add(data_path)
        driver_fc.driver.type = 'SCRIPTED'

        v = driver_fc.driver.variables.new()
        v.name = 'var'
        v.type = 'SINGLE_PROP'
        v.targets[0].id_type = 'KEY'
        v.targets[0].id = shape_keys
        v.targets[0].data_path = f'key_blocks["{input_name}"].value'
        driver_fc.driver.expression = 'var'


def unload_template(info):
    """Remove a loaded template's objects from the scene.

    Args:
        info: TemplateInfo from a previous load_template() call
    """
    names_to_remove = []

    if info.puppet_object:
        names_to_remove.append(info.puppet_object)
    if info.armature:
        names_to_remove.append(info.armature)
    # Don't remove the dummy mesh — it's shared across templates

    for name in names_to_remove:
        obj = bpy.data.objects.get(name)
        if obj:
            bpy.data.objects.remove(obj, do_unlink=True)
