"""Create Blob Puppet Template V2 — Geometry Nodes edition.

Run this script inside Blender 5.0+ to generate a procedural blob character
built entirely in one Geometry Nodes tree. Everything is visual — open the
Geometry Nodes editor and you'll see the whole character as a node graph.

The character has:
- Body (UV Sphere, scalable)
- Two eyes with irises (blink, widen, look direction)
- A mouth (jaw open, smile, pucker)
- Two ears (scalable)
- Face tracking Group Inputs driven by ARKitShapeKeys.Dummy
- Customization Group Inputs (body size, eye size, colors)
- Armature with "head" bone for phone rotation

Usage:
    Open Blender → Scripting workspace → Open this file → Run Script
    Then: File → Save As → blob_puppet.blend
"""

import math

import bpy
import mathutils


# ===================================================================
# 0. CLEAN SLATE
# ===================================================================

def clean_scene():
    """Remove default objects."""
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    for block in bpy.data.meshes:
        if block.users == 0:
            bpy.data.meshes.remove(block)
    for block in bpy.data.materials:
        if block.users == 0:
            bpy.data.materials.remove(block)
    for block in bpy.data.armatures:
        if block.users == 0:
            bpy.data.armatures.remove(block)
    for block in bpy.data.node_groups:
        if block.users == 0:
            bpy.data.node_groups.remove(block)


# ===================================================================
# 1. MATERIALS
# ===================================================================

def make_material(name, color):
    """Create a simple solid-color material."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = 0.8
    return mat


def make_color_attr_material(name, fallback_color):
    """Create a material that reads its Base Color from a named attribute 'Color'.

    This allows the geonode tree to control per-body-part colors via
    Store Named Attribute → material reads it back. The fallback_color
    is used if no attribute is present (e.g. viewing the mesh standalone).
    """
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    bsdf = nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = fallback_color
    bsdf.inputs["Roughness"].default_value = 0.8

    attr = nodes.new('ShaderNodeAttribute')
    attr.attribute_name = "Color"
    attr.attribute_type = 'GEOMETRY'
    attr.location = (-300, 300)
    links.new(attr.outputs['Color'], bsdf.inputs['Base Color'])

    return mat


def create_materials():
    """Create the color palette.

    Body, iris, mouth, and ear use attribute-reading materials so their
    colors can be controlled from the Customize panel. Eye whites and
    pupils stay fixed.
    """
    return {
        'body': make_color_attr_material("Blob_Body", (1.0, 0.78, 0.65, 1.0)),
        'mouth': make_color_attr_material("Blob_Mouth", (0.85, 0.35, 0.35, 1.0)),
        'eye_white': make_material("Blob_EyeWhite", (1.0, 1.0, 1.0, 1.0)),
        'iris': make_color_attr_material("Blob_Iris", (0.2, 0.65, 0.7, 1.0)),
        'pupil': make_material("Blob_Pupil", (0.05, 0.05, 0.05, 1.0)),
        'ear': make_color_attr_material("Blob_Ear", (1.0, 0.7, 0.55, 1.0)),
        'brow': make_color_attr_material("Blob_Brow", (0.3, 0.2, 0.15, 1.0)),
    }


# ===================================================================
# 2. DUMMY MESH (ARKit shape key receiver)
# ===================================================================

BLENDSHAPE_MAP = {
    2: 'eyeLookInRight',
    3: 'eyeLookInLeft',
    4: 'eyeLookOutRight',
    5: 'eyeLookOutLeft',
    19: 'mouthFunnel',
    20: 'mouthPucker',
    21: 'mouthLeft',
    22: 'mouthRight',
    23: 'mouthSmileRight',
    25: 'mouthFrownLeft',
    26: 'mouthFrownRight',
    27: 'mouthClose',
    37: 'jawOpen',
    41: 'eyeBlinkLeft',
    42: 'eyeBlinkRight',
    43: 'eyeWideLeft',
    44: 'eyeWideRight',
}


def create_dummy_mesh():
    """Create the hidden mesh that receives face data from the phone."""
    mesh = bpy.data.meshes.new("ARKitShapeKeys.Dummy")
    obj = bpy.data.objects.new("ARKitShapeKeys.Dummy", mesh)
    bpy.context.collection.objects.link(obj)
    mesh.from_pydata([(0, 0, 0)], [], [])
    obj.shape_key_add(name='Basis')
    for name in sorted(set(BLENDSHAPE_MAP.values())):
        obj.shape_key_add(name=name)
    obj.hide_viewport = True
    obj.hide_render = True
    obj.hide_select = True
    return obj


# ===================================================================
# 3. GEOMETRY NODES TREE — the heart of the character
# ===================================================================

# Helper: place a node at x, y and return it
def add_node(tree, node_type, x, y, label=None):
    """Add a node to the tree at position (x, y) with optional label."""
    node = tree.nodes.new(node_type)
    node.location = (x, y)
    if label:
        node.label = label
        node.use_custom_color = True
    return node


def build_geometry_nodes(mats):
    """Build the entire blob character as a geometry nodes tree.

    Returns the node group so it can be assigned as a modifier.
    """
    # Create the node tree
    tree = bpy.data.node_groups.new("GN_BlobPuppet", 'GeometryNodeTree')

    # ------------------------------------------------------------------
    # GROUP INTERFACE — inputs and outputs
    # ------------------------------------------------------------------

    # Output: geometry
    tree.interface.new_socket(
        "Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry'
    )

    # --- Face Tracking Inputs (driven by dummy mesh shape keys) ---
    # These are the "performance" inputs — they change in real time

    ft_panel = tree.interface.new_panel("Face Tracking")

    s = tree.interface.new_socket(
        "jawOpen", in_out='INPUT', socket_type='NodeSocketFloat',
        parent=ft_panel
    )
    s.default_value = 0.0
    s.min_value = 0.0
    s.max_value = 1.0
    s.subtype = 'FACTOR'

    s = tree.interface.new_socket(
        "mouthSmileRight", in_out='INPUT', socket_type='NodeSocketFloat',
        parent=ft_panel
    )
    s.default_value = 0.0
    s.min_value = 0.0
    s.max_value = 1.0
    s.subtype = 'FACTOR'

    s = tree.interface.new_socket(
        "mouthFunnel", in_out='INPUT', socket_type='NodeSocketFloat',
        parent=ft_panel
    )
    s.default_value = 0.0
    s.min_value = 0.0
    s.max_value = 1.0
    s.subtype = 'FACTOR'

    s = tree.interface.new_socket(
        "eyeBlinkLeft", in_out='INPUT', socket_type='NodeSocketFloat',
        parent=ft_panel
    )
    s.default_value = 0.0
    s.min_value = 0.0
    s.max_value = 1.0
    s.subtype = 'FACTOR'

    s = tree.interface.new_socket(
        "eyeBlinkRight", in_out='INPUT', socket_type='NodeSocketFloat',
        parent=ft_panel
    )
    s.default_value = 0.0
    s.min_value = 0.0
    s.max_value = 1.0
    s.subtype = 'FACTOR'

    s = tree.interface.new_socket(
        "eyeWideLeft", in_out='INPUT', socket_type='NodeSocketFloat',
        parent=ft_panel
    )
    s.default_value = 0.0
    s.min_value = 0.0
    s.max_value = 1.0
    s.subtype = 'FACTOR'

    s = tree.interface.new_socket(
        "eyeWideRight", in_out='INPUT', socket_type='NodeSocketFloat',
        parent=ft_panel
    )
    s.default_value = 0.0
    s.min_value = 0.0
    s.max_value = 1.0
    s.subtype = 'FACTOR'

    s = tree.interface.new_socket(
        "eyeLookInLeft", in_out='INPUT', socket_type='NodeSocketFloat',
        parent=ft_panel
    )
    s.default_value = 0.0
    s.min_value = 0.0
    s.max_value = 1.0
    s.subtype = 'FACTOR'

    s = tree.interface.new_socket(
        "eyeLookInRight", in_out='INPUT', socket_type='NodeSocketFloat',
        parent=ft_panel
    )
    s.default_value = 0.0
    s.min_value = 0.0
    s.max_value = 1.0
    s.subtype = 'FACTOR'

    s = tree.interface.new_socket(
        "mouthFrownLeft", in_out='INPUT', socket_type='NodeSocketFloat',
        parent=ft_panel
    )
    s.default_value = 0.0
    s.min_value = 0.0
    s.max_value = 1.0
    s.subtype = 'FACTOR'

    s = tree.interface.new_socket(
        "mouthFrownRight", in_out='INPUT', socket_type='NodeSocketFloat',
        parent=ft_panel
    )
    s.default_value = 0.0
    s.min_value = 0.0
    s.max_value = 1.0
    s.subtype = 'FACTOR'

    s = tree.interface.new_socket(
        "mouthLeft", in_out='INPUT', socket_type='NodeSocketFloat',
        parent=ft_panel
    )
    s.default_value = 0.0
    s.min_value = 0.0
    s.max_value = 1.0
    s.subtype = 'FACTOR'

    s = tree.interface.new_socket(
        "mouthRight", in_out='INPUT', socket_type='NodeSocketFloat',
        parent=ft_panel
    )
    s.default_value = 0.0
    s.min_value = 0.0
    s.max_value = 1.0
    s.subtype = 'FACTOR'

    # --- Customization Inputs (kid-friendly sliders) ---

    cust_panel = tree.interface.new_panel("Customize")

    s = tree.interface.new_socket(
        "Body Width", in_out='INPUT', socket_type='NodeSocketFloat',
        parent=cust_panel
    )
    s.default_value = 1.0
    s.min_value = 0.5
    s.max_value = 2.0

    s = tree.interface.new_socket(
        "Body Height", in_out='INPUT', socket_type='NodeSocketFloat',
        parent=cust_panel
    )
    s.default_value = 1.0
    s.min_value = 0.5
    s.max_value = 2.0

    s = tree.interface.new_socket(
        "Eye Size", in_out='INPUT', socket_type='NodeSocketFloat',
        parent=cust_panel
    )
    s.default_value = 1.0
    s.min_value = 0.3
    s.max_value = 2.0

    s = tree.interface.new_socket(
        "Eye Spacing", in_out='INPUT', socket_type='NodeSocketFloat',
        parent=cust_panel
    )
    s.default_value = 1.0
    s.min_value = 0.5
    s.max_value = 2.0

    s = tree.interface.new_socket(
        "Ear Size", in_out='INPUT', socket_type='NodeSocketFloat',
        parent=cust_panel
    )
    s.default_value = 1.0
    s.min_value = 0.0
    s.max_value = 2.0

    s = tree.interface.new_socket(
        "Mouth Size", in_out='INPUT', socket_type='NodeSocketFloat',
        parent=cust_panel
    )
    s.default_value = 1.0
    s.min_value = 0.3
    s.max_value = 2.0

    # --- Position controls: slide features around the face ---

    s = tree.interface.new_socket(
        "Eyes Height", in_out='INPUT', socket_type='NodeSocketFloat',
        parent=cust_panel
    )
    s.default_value = 1.0
    s.min_value = 0.5
    s.max_value = 1.5

    s = tree.interface.new_socket(
        "Eyes Depth", in_out='INPUT', socket_type='NodeSocketFloat',
        parent=cust_panel
    )
    s.default_value = 1.0
    s.min_value = 0.5
    s.max_value = 1.5

    s = tree.interface.new_socket(
        "Mouth Height", in_out='INPUT', socket_type='NodeSocketFloat',
        parent=cust_panel
    )
    s.default_value = 1.0
    s.min_value = 0.5
    s.max_value = 1.5

    s = tree.interface.new_socket(
        "Mouth Depth", in_out='INPUT', socket_type='NodeSocketFloat',
        parent=cust_panel
    )
    s.default_value = 1.0
    s.min_value = 0.5
    s.max_value = 1.5

    s = tree.interface.new_socket(
        "Ears Height", in_out='INPUT', socket_type='NodeSocketFloat',
        parent=cust_panel
    )
    s.default_value = 1.0
    s.min_value = 0.5
    s.max_value = 1.5

    s = tree.interface.new_socket(
        "Ears Spread", in_out='INPUT', socket_type='NodeSocketFloat',
        parent=cust_panel
    )
    s.default_value = 1.0
    s.min_value = 0.5
    s.max_value = 2.0

    s = tree.interface.new_socket(
        "Ears Depth", in_out='INPUT', socket_type='NodeSocketFloat',
        parent=cust_panel
    )
    s.default_value = 1.0
    s.min_value = 0.5
    s.max_value = 1.5

    # --- Color controls ---

    s = tree.interface.new_socket(
        "Body Color", in_out='INPUT', socket_type='NodeSocketColor',
        parent=cust_panel
    )
    s.default_value = (1.0, 0.78, 0.65, 1.0)

    s = tree.interface.new_socket(
        "Eye Color", in_out='INPUT', socket_type='NodeSocketColor',
        parent=cust_panel
    )
    s.default_value = (0.2, 0.65, 0.7, 1.0)

    s = tree.interface.new_socket(
        "Mouth Color", in_out='INPUT', socket_type='NodeSocketColor',
        parent=cust_panel
    )
    s.default_value = (0.85, 0.35, 0.35, 1.0)

    s = tree.interface.new_socket(
        "Ear Color", in_out='INPUT', socket_type='NodeSocketColor',
        parent=cust_panel
    )
    s.default_value = (1.0, 0.7, 0.55, 1.0)

    s = tree.interface.new_socket(
        "Eyebrow Size", in_out='INPUT', socket_type='NodeSocketFloat',
        parent=cust_panel
    )
    s.default_value = 1.0
    s.min_value = 0.3
    s.max_value = 2.0

    s = tree.interface.new_socket(
        "Eyebrow Height", in_out='INPUT', socket_type='NodeSocketFloat',
        parent=cust_panel
    )
    s.default_value = 1.0
    s.min_value = 0.5
    s.max_value = 1.5

    s = tree.interface.new_socket(
        "Eyebrow Color", in_out='INPUT', socket_type='NodeSocketColor',
        parent=cust_panel
    )
    s.default_value = (0.3, 0.2, 0.15, 1.0)  # dark brown

    # ------------------------------------------------------------------
    # NODES — organized left to right, top to bottom
    # ------------------------------------------------------------------

    # Column positions
    INPUT_X = -1800
    PRIM_X = -1200
    MATH_X = -800
    COMBINE_X = -500
    XFORM_X = -200
    MAT_X = 200
    JOIN_X = 600
    OUT_X = 900

    # Row positions (each body part gets a row)
    BODY_Y = 400
    EYE_L_Y = 100
    EYE_R_Y = -150
    IRIS_L_Y = -400
    IRIS_R_Y = -650
    PUPIL_L_Y = -900
    PUPIL_R_Y = -1100
    MOUTH_Y = -1350
    EAR_L_Y = -1650
    EAR_R_Y = -1900
    BROW_L_Y = -2150
    BROW_R_Y = -2400

    # --- Group Input & Output ---
    group_in = tree.nodes.new('NodeGroupInput')
    group_in.location = (INPUT_X, -400)

    group_out = tree.nodes.new('NodeGroupOutput')
    group_out.location = (OUT_X, -400)

    # We'll need a second Group Input for readability (Blender allows multiple)
    group_in2 = tree.nodes.new('NodeGroupInput')
    group_in2.location = (INPUT_X, -1400)

    # ------------------------------------------------------------------
    # POSITION HELPERS — shared multiply nodes for slider-driven placement
    # ------------------------------------------------------------------

    # Eyes Height: base Z = 1.25, scaled by Eyes Height slider
    eyes_height_z = add_node(tree, 'ShaderNodeMath', INPUT_X + 300, -200, "Eyes Height Z")
    eyes_height_z.operation = 'MULTIPLY'
    eyes_height_z.inputs[0].default_value = 1.25
    tree.links.new(group_in.outputs['Eyes Height'], eyes_height_z.inputs[1])

    # Mouth Height: base Z = 0.5, scaled by Mouth Height slider
    mouth_height_z = add_node(tree, 'ShaderNodeMath', INPUT_X + 300, -300, "Mouth Height Z")
    mouth_height_z.operation = 'MULTIPLY'
    mouth_height_z.inputs[0].default_value = 0.5
    tree.links.new(group_in.outputs['Mouth Height'], mouth_height_z.inputs[1])

    # Ears Height: base Z = 1.3
    ears_height_z = add_node(tree, 'ShaderNodeMath', INPUT_X + 300, -400, "Ears Height Z")
    ears_height_z.operation = 'MULTIPLY'
    ears_height_z.inputs[0].default_value = 1.3
    tree.links.new(group_in.outputs['Ears Height'], ears_height_z.inputs[1])

    # Ears Spread: base X = 0.85 (sign applied per-ear)
    ears_spread_x = add_node(tree, 'ShaderNodeMath', INPUT_X + 300, -500, "Ears Spread X")
    ears_spread_x.operation = 'MULTIPLY'
    ears_spread_x.inputs[0].default_value = 0.85
    tree.links.new(group_in.outputs['Ears Spread'], ears_spread_x.inputs[1])

    # Ears Spread negated for left ear (negative X)
    ears_spread_neg = add_node(tree, 'ShaderNodeMath', INPUT_X + 300, -560, "Ears Spread Neg")
    ears_spread_neg.operation = 'MULTIPLY'
    ears_spread_neg.inputs[1].default_value = -1.0
    tree.links.new(ears_spread_x.outputs[0], ears_spread_neg.inputs[0])

    # Ears Depth: base Y = -0.1
    ears_depth_y = add_node(tree, 'ShaderNodeMath', INPUT_X + 300, -620, "Ears Depth Y")
    ears_depth_y.operation = 'MULTIPLY'
    ears_depth_y.inputs[0].default_value = -0.1
    tree.links.new(group_in.outputs['Ears Depth'], ears_depth_y.inputs[1])

    # ------------------------------------------------------------------
    # BODY — UV Sphere, scaled by customization inputs
    # ------------------------------------------------------------------

    body_sphere = add_node(tree, 'GeometryNodeMeshUVSphere', PRIM_X, BODY_Y, "Body Sphere")
    body_sphere.inputs['Segments'].default_value = 32
    body_sphere.inputs['Rings'].default_value = 16
    body_sphere.inputs['Radius'].default_value = 1.0

    # Body scale: (0.9 * BodyWidth, 0.8, 1.1 * BodyHeight)
    body_scale_w = add_node(tree, 'ShaderNodeMath', MATH_X, BODY_Y, "Body Width Scale")
    body_scale_w.operation = 'MULTIPLY'
    body_scale_w.inputs[1].default_value = 0.9

    body_scale_h = add_node(tree, 'ShaderNodeMath', MATH_X, BODY_Y - 60, "Body Height Scale")
    body_scale_h.operation = 'MULTIPLY'
    body_scale_h.inputs[1].default_value = 1.1

    body_combine = add_node(tree, 'ShaderNodeCombineXYZ', COMBINE_X, BODY_Y, "Body Scale Vec")
    body_combine.inputs['Y'].default_value = 0.8

    body_xform = add_node(tree, 'GeometryNodeTransform', XFORM_X, BODY_Y, "Body Transform")
    body_xform.inputs['Translation'].default_value = (0, 0, 0.8)

    body_color = add_node(tree, 'GeometryNodeStoreNamedAttribute', MAT_X - 150, BODY_Y, "Body Color")
    body_color.data_type = 'FLOAT_COLOR'
    body_color.domain = 'POINT'
    body_color.inputs['Name'].default_value = "Color"

    body_mat = add_node(tree, 'GeometryNodeSetMaterial', MAT_X, BODY_Y, "Body Material")
    body_mat.inputs['Material'].default_value = mats['body']

    # Links: body
    tree.links.new(group_in.outputs['Body Width'], body_scale_w.inputs[0])
    tree.links.new(group_in.outputs['Body Height'], body_scale_h.inputs[0])
    tree.links.new(body_scale_w.outputs[0], body_combine.inputs['X'])
    tree.links.new(body_scale_h.outputs[0], body_combine.inputs['Z'])
    tree.links.new(body_sphere.outputs['Mesh'], body_xform.inputs['Geometry'])
    tree.links.new(body_combine.outputs['Vector'], body_xform.inputs['Scale'])
    tree.links.new(body_xform.outputs['Geometry'], body_color.inputs['Geometry'])
    tree.links.new(group_in.outputs['Body Color'], body_color.inputs['Value'])
    tree.links.new(body_color.outputs['Geometry'], body_mat.inputs['Geometry'])

    # ------------------------------------------------------------------
    # LEFT EYE — blink drives Z scale
    # ------------------------------------------------------------------

    eye_l_sphere = add_node(tree, 'GeometryNodeMeshUVSphere', PRIM_X, EYE_L_Y, "Eye L Sphere")
    eye_l_sphere.inputs['Segments'].default_value = 16
    eye_l_sphere.inputs['Rings'].default_value = 8
    eye_l_sphere.inputs['Radius'].default_value = 0.22

    # Blink: Z scale = (1 - eyeBlinkLeft * 0.9) * EyeSize
    eye_l_blink = add_node(tree, 'ShaderNodeMath', MATH_X - 200, EYE_L_Y, "L Blink Invert")
    eye_l_blink.operation = 'MULTIPLY'
    eye_l_blink.inputs[1].default_value = 0.9

    eye_l_open = add_node(tree, 'ShaderNodeMath', MATH_X, EYE_L_Y, "L Eye Openness")
    eye_l_open.operation = 'SUBTRACT'
    eye_l_open.inputs[0].default_value = 1.0

    # Eye size multiplied into all axes
    eye_l_sz = add_node(tree, 'ShaderNodeMath', MATH_X, EYE_L_Y - 60, "L Eye Size Z")
    eye_l_sz.operation = 'MULTIPLY'

    # Wide: X scale = (1 + eyeWideLeft * 0.2) * EyeSize
    eye_l_wide = add_node(tree, 'ShaderNodeMath', MATH_X - 200, EYE_L_Y - 120, "L Wide")
    eye_l_wide.operation = 'MULTIPLY'
    eye_l_wide.inputs[1].default_value = 0.2

    eye_l_wide_add = add_node(tree, 'ShaderNodeMath', MATH_X, EYE_L_Y - 120, "L Wide Add")
    eye_l_wide_add.operation = 'ADD'
    eye_l_wide_add.inputs[0].default_value = 1.0

    eye_l_sx = add_node(tree, 'ShaderNodeMath', MATH_X + 150, EYE_L_Y - 120, "L Eye Size X")
    eye_l_sx.operation = 'MULTIPLY'

    # Eye spacing: X position = -0.35 * EyeSpacing
    eye_l_pos_x = add_node(tree, 'ShaderNodeMath', MATH_X, EYE_L_Y + 60, "L Eye Pos X")
    eye_l_pos_x.operation = 'MULTIPLY'
    eye_l_pos_x.inputs[0].default_value = -0.35

    eye_l_pos_y = add_node(tree, 'ShaderNodeMath', MATH_X + 150, EYE_L_Y + 60, "L Eye Pos Y")
    eye_l_pos_y.operation = 'MULTIPLY'
    eye_l_pos_y.inputs[0].default_value = -0.55

    eye_l_pos = add_node(tree, 'ShaderNodeCombineXYZ', COMBINE_X, EYE_L_Y + 60, "L Eye Pos")
    eye_l_pos.inputs['Z'].default_value = 1.25  # overridden by Eyes Height link

    eye_l_scale = add_node(tree, 'ShaderNodeCombineXYZ', COMBINE_X, EYE_L_Y, "L Eye Scale")

    eye_l_xform = add_node(tree, 'GeometryNodeTransform', XFORM_X, EYE_L_Y, "Eye L Transform")

    eye_l_mat = add_node(tree, 'GeometryNodeSetMaterial', MAT_X, EYE_L_Y, "Eye L Material")
    eye_l_mat.inputs['Material'].default_value = mats['eye_white']

    # Links: left eye
    tree.links.new(group_in.outputs['eyeBlinkLeft'], eye_l_blink.inputs[0])
    tree.links.new(eye_l_blink.outputs[0], eye_l_open.inputs[1])
    tree.links.new(eye_l_open.outputs[0], eye_l_sz.inputs[0])
    tree.links.new(group_in.outputs['Eye Size'], eye_l_sz.inputs[1])

    tree.links.new(group_in.outputs['eyeWideLeft'], eye_l_wide.inputs[0])
    tree.links.new(eye_l_wide.outputs[0], eye_l_wide_add.inputs[1])
    tree.links.new(eye_l_wide_add.outputs[0], eye_l_sx.inputs[0])
    tree.links.new(group_in.outputs['Eye Size'], eye_l_sx.inputs[1])

    tree.links.new(eye_l_sx.outputs[0], eye_l_scale.inputs['X'])
    tree.links.new(group_in.outputs['Eye Size'], eye_l_scale.inputs['Y'])
    tree.links.new(eye_l_sz.outputs[0], eye_l_scale.inputs['Z'])

    tree.links.new(group_in.outputs['Eye Spacing'], eye_l_pos_x.inputs[1])
    tree.links.new(eye_l_pos_x.outputs[0], eye_l_pos.inputs['X'])
    tree.links.new(group_in.outputs['Eyes Depth'], eye_l_pos_y.inputs[1])
    tree.links.new(eye_l_pos_y.outputs[0], eye_l_pos.inputs['Y'])
    tree.links.new(eyes_height_z.outputs[0], eye_l_pos.inputs['Z'])

    tree.links.new(eye_l_sphere.outputs['Mesh'], eye_l_xform.inputs['Geometry'])
    tree.links.new(eye_l_pos.outputs['Vector'], eye_l_xform.inputs['Translation'])
    tree.links.new(eye_l_scale.outputs['Vector'], eye_l_xform.inputs['Scale'])
    tree.links.new(eye_l_xform.outputs['Geometry'], eye_l_mat.inputs['Geometry'])

    # ------------------------------------------------------------------
    # RIGHT EYE — mirror of left
    # ------------------------------------------------------------------

    eye_r_sphere = add_node(tree, 'GeometryNodeMeshUVSphere', PRIM_X, EYE_R_Y, "Eye R Sphere")
    eye_r_sphere.inputs['Segments'].default_value = 16
    eye_r_sphere.inputs['Rings'].default_value = 8
    eye_r_sphere.inputs['Radius'].default_value = 0.22

    eye_r_blink = add_node(tree, 'ShaderNodeMath', MATH_X - 200, EYE_R_Y, "R Blink Invert")
    eye_r_blink.operation = 'MULTIPLY'
    eye_r_blink.inputs[1].default_value = 0.9

    eye_r_open = add_node(tree, 'ShaderNodeMath', MATH_X, EYE_R_Y, "R Eye Openness")
    eye_r_open.operation = 'SUBTRACT'
    eye_r_open.inputs[0].default_value = 1.0

    eye_r_sz = add_node(tree, 'ShaderNodeMath', MATH_X, EYE_R_Y - 60, "R Eye Size Z")
    eye_r_sz.operation = 'MULTIPLY'

    eye_r_wide = add_node(tree, 'ShaderNodeMath', MATH_X - 200, EYE_R_Y - 120, "R Wide")
    eye_r_wide.operation = 'MULTIPLY'
    eye_r_wide.inputs[1].default_value = 0.2

    eye_r_wide_add = add_node(tree, 'ShaderNodeMath', MATH_X, EYE_R_Y - 120, "R Wide Add")
    eye_r_wide_add.operation = 'ADD'
    eye_r_wide_add.inputs[0].default_value = 1.0

    eye_r_sx = add_node(tree, 'ShaderNodeMath', MATH_X + 150, EYE_R_Y - 120, "R Eye Size X")
    eye_r_sx.operation = 'MULTIPLY'

    eye_r_pos_x = add_node(tree, 'ShaderNodeMath', MATH_X, EYE_R_Y + 60, "R Eye Pos X")
    eye_r_pos_x.operation = 'MULTIPLY'
    eye_r_pos_x.inputs[0].default_value = 0.35

    eye_r_pos_y = add_node(tree, 'ShaderNodeMath', MATH_X + 150, EYE_R_Y + 60, "R Eye Pos Y")
    eye_r_pos_y.operation = 'MULTIPLY'
    eye_r_pos_y.inputs[0].default_value = -0.55

    eye_r_pos = add_node(tree, 'ShaderNodeCombineXYZ', COMBINE_X, EYE_R_Y + 60, "R Eye Pos")
    eye_r_pos.inputs['Z'].default_value = 1.25  # overridden by Eyes Height link

    eye_r_scale = add_node(tree, 'ShaderNodeCombineXYZ', COMBINE_X, EYE_R_Y, "R Eye Scale")

    eye_r_xform = add_node(tree, 'GeometryNodeTransform', XFORM_X, EYE_R_Y, "Eye R Transform")

    eye_r_mat = add_node(tree, 'GeometryNodeSetMaterial', MAT_X, EYE_R_Y, "Eye R Material")
    eye_r_mat.inputs['Material'].default_value = mats['eye_white']

    tree.links.new(group_in.outputs['eyeBlinkRight'], eye_r_blink.inputs[0])
    tree.links.new(eye_r_blink.outputs[0], eye_r_open.inputs[1])
    tree.links.new(eye_r_open.outputs[0], eye_r_sz.inputs[0])
    tree.links.new(group_in.outputs['Eye Size'], eye_r_sz.inputs[1])

    tree.links.new(group_in.outputs['eyeWideRight'], eye_r_wide.inputs[0])
    tree.links.new(eye_r_wide.outputs[0], eye_r_wide_add.inputs[1])
    tree.links.new(eye_r_wide_add.outputs[0], eye_r_sx.inputs[0])
    tree.links.new(group_in.outputs['Eye Size'], eye_r_sx.inputs[1])

    tree.links.new(eye_r_sx.outputs[0], eye_r_scale.inputs['X'])
    tree.links.new(group_in.outputs['Eye Size'], eye_r_scale.inputs['Y'])
    tree.links.new(eye_r_sz.outputs[0], eye_r_scale.inputs['Z'])

    tree.links.new(group_in.outputs['Eye Spacing'], eye_r_pos_x.inputs[1])
    tree.links.new(eye_r_pos_x.outputs[0], eye_r_pos.inputs['X'])
    tree.links.new(group_in.outputs['Eyes Depth'], eye_r_pos_y.inputs[1])
    tree.links.new(eye_r_pos_y.outputs[0], eye_r_pos.inputs['Y'])
    tree.links.new(eyes_height_z.outputs[0], eye_r_pos.inputs['Z'])

    tree.links.new(eye_r_sphere.outputs['Mesh'], eye_r_xform.inputs['Geometry'])
    tree.links.new(eye_r_pos.outputs['Vector'], eye_r_xform.inputs['Translation'])
    tree.links.new(eye_r_scale.outputs['Vector'], eye_r_xform.inputs['Scale'])
    tree.links.new(eye_r_xform.outputs['Geometry'], eye_r_mat.inputs['Geometry'])

    # ------------------------------------------------------------------
    # LEFT IRIS — follows eye blink, driven by eye look
    # ------------------------------------------------------------------

    iris_l_sphere = add_node(tree, 'GeometryNodeMeshUVSphere', PRIM_X, IRIS_L_Y, "Iris L Sphere")
    iris_l_sphere.inputs['Segments'].default_value = 12
    iris_l_sphere.inputs['Rings'].default_value = 6
    iris_l_sphere.inputs['Radius'].default_value = 0.12

    # Iris blink scale (same as eye)
    iris_l_blink = add_node(tree, 'ShaderNodeMath', MATH_X - 200, IRIS_L_Y, "Iris L Blink")
    iris_l_blink.operation = 'MULTIPLY'
    iris_l_blink.inputs[1].default_value = 0.9

    iris_l_open = add_node(tree, 'ShaderNodeMath', MATH_X, IRIS_L_Y, "Iris L Open")
    iris_l_open.operation = 'SUBTRACT'
    iris_l_open.inputs[0].default_value = 1.0

    iris_l_sz = add_node(tree, 'ShaderNodeMath', MATH_X + 150, IRIS_L_Y, "Iris L Size Z")
    iris_l_sz.operation = 'MULTIPLY'

    # Look direction: X offset = -0.35 * spacing + lookInLeft * 0.08
    iris_l_look = add_node(tree, 'ShaderNodeMath', MATH_X - 200, IRIS_L_Y - 80, "Iris L Look")
    iris_l_look.operation = 'MULTIPLY'
    iris_l_look.inputs[1].default_value = 0.08

    iris_l_base_x = add_node(tree, 'ShaderNodeMath', MATH_X, IRIS_L_Y + 60, "Iris L Base X")
    iris_l_base_x.operation = 'MULTIPLY'
    iris_l_base_x.inputs[0].default_value = -0.35

    iris_l_final_x = add_node(tree, 'ShaderNodeMath', MATH_X + 150, IRIS_L_Y - 80, "Iris L Final X")
    iris_l_final_x.operation = 'ADD'

    iris_l_pos_y = add_node(tree, 'ShaderNodeMath', MATH_X + 150, IRIS_L_Y + 30, "Iris L Pos Y")
    iris_l_pos_y.operation = 'MULTIPLY'
    iris_l_pos_y.inputs[0].default_value = -0.72

    iris_l_pos = add_node(tree, 'ShaderNodeCombineXYZ', COMBINE_X, IRIS_L_Y, "Iris L Pos")
    iris_l_pos.inputs['Z'].default_value = 1.25  # overridden by Eyes Height link

    iris_l_scale = add_node(tree, 'ShaderNodeCombineXYZ', COMBINE_X, IRIS_L_Y - 80, "Iris L Scale")

    iris_l_xform = add_node(tree, 'GeometryNodeTransform', XFORM_X, IRIS_L_Y, "Iris L Transform")

    iris_l_color = add_node(tree, 'GeometryNodeStoreNamedAttribute', MAT_X - 150, IRIS_L_Y, "Iris L Color")
    iris_l_color.data_type = 'FLOAT_COLOR'
    iris_l_color.domain = 'POINT'
    iris_l_color.inputs['Name'].default_value = "Color"

    iris_l_mat = add_node(tree, 'GeometryNodeSetMaterial', MAT_X, IRIS_L_Y, "Iris L Material")
    iris_l_mat.inputs['Material'].default_value = mats['iris']

    tree.links.new(group_in.outputs['eyeBlinkLeft'], iris_l_blink.inputs[0])
    tree.links.new(iris_l_blink.outputs[0], iris_l_open.inputs[1])
    tree.links.new(iris_l_open.outputs[0], iris_l_sz.inputs[0])
    tree.links.new(group_in.outputs['Eye Size'], iris_l_sz.inputs[1])

    tree.links.new(group_in.outputs['eyeLookInLeft'], iris_l_look.inputs[0])
    tree.links.new(group_in.outputs['Eye Spacing'], iris_l_base_x.inputs[1])
    tree.links.new(iris_l_base_x.outputs[0], iris_l_final_x.inputs[0])
    tree.links.new(iris_l_look.outputs[0], iris_l_final_x.inputs[1])

    tree.links.new(iris_l_final_x.outputs[0], iris_l_pos.inputs['X'])
    tree.links.new(group_in.outputs['Eyes Depth'], iris_l_pos_y.inputs[1])
    tree.links.new(iris_l_pos_y.outputs[0], iris_l_pos.inputs['Y'])
    tree.links.new(eyes_height_z.outputs[0], iris_l_pos.inputs['Z'])
    tree.links.new(group_in.outputs['Eye Size'], iris_l_scale.inputs['X'])
    tree.links.new(group_in.outputs['Eye Size'], iris_l_scale.inputs['Y'])
    tree.links.new(iris_l_sz.outputs[0], iris_l_scale.inputs['Z'])

    tree.links.new(iris_l_sphere.outputs['Mesh'], iris_l_xform.inputs['Geometry'])
    tree.links.new(iris_l_pos.outputs['Vector'], iris_l_xform.inputs['Translation'])
    tree.links.new(iris_l_scale.outputs['Vector'], iris_l_xform.inputs['Scale'])
    tree.links.new(iris_l_xform.outputs['Geometry'], iris_l_color.inputs['Geometry'])
    tree.links.new(group_in.outputs['Eye Color'], iris_l_color.inputs['Value'])
    tree.links.new(iris_l_color.outputs['Geometry'], iris_l_mat.inputs['Geometry'])

    # ------------------------------------------------------------------
    # RIGHT IRIS — mirror of left
    # ------------------------------------------------------------------

    iris_r_sphere = add_node(tree, 'GeometryNodeMeshUVSphere', PRIM_X, IRIS_R_Y, "Iris R Sphere")
    iris_r_sphere.inputs['Segments'].default_value = 12
    iris_r_sphere.inputs['Rings'].default_value = 6
    iris_r_sphere.inputs['Radius'].default_value = 0.12

    iris_r_blink = add_node(tree, 'ShaderNodeMath', MATH_X - 200, IRIS_R_Y, "Iris R Blink")
    iris_r_blink.operation = 'MULTIPLY'
    iris_r_blink.inputs[1].default_value = 0.9

    iris_r_open = add_node(tree, 'ShaderNodeMath', MATH_X, IRIS_R_Y, "Iris R Open")
    iris_r_open.operation = 'SUBTRACT'
    iris_r_open.inputs[0].default_value = 1.0

    iris_r_sz = add_node(tree, 'ShaderNodeMath', MATH_X + 150, IRIS_R_Y, "Iris R Size Z")
    iris_r_sz.operation = 'MULTIPLY'

    iris_r_look = add_node(tree, 'ShaderNodeMath', MATH_X - 200, IRIS_R_Y - 80, "Iris R Look")
    iris_r_look.operation = 'MULTIPLY'
    iris_r_look.inputs[1].default_value = -0.08  # Inverted for right eye

    iris_r_base_x = add_node(tree, 'ShaderNodeMath', MATH_X, IRIS_R_Y + 60, "Iris R Base X")
    iris_r_base_x.operation = 'MULTIPLY'
    iris_r_base_x.inputs[0].default_value = 0.35

    iris_r_final_x = add_node(tree, 'ShaderNodeMath', MATH_X + 150, IRIS_R_Y - 80, "Iris R Final X")
    iris_r_final_x.operation = 'ADD'

    iris_r_pos_y = add_node(tree, 'ShaderNodeMath', MATH_X + 150, IRIS_R_Y + 30, "Iris R Pos Y")
    iris_r_pos_y.operation = 'MULTIPLY'
    iris_r_pos_y.inputs[0].default_value = -0.72

    iris_r_pos = add_node(tree, 'ShaderNodeCombineXYZ', COMBINE_X, IRIS_R_Y, "Iris R Pos")
    iris_r_pos.inputs['Z'].default_value = 1.25  # overridden by Eyes Height link

    iris_r_scale = add_node(tree, 'ShaderNodeCombineXYZ', COMBINE_X, IRIS_R_Y - 80, "Iris R Scale")

    iris_r_xform = add_node(tree, 'GeometryNodeTransform', XFORM_X, IRIS_R_Y, "Iris R Transform")

    iris_r_color = add_node(tree, 'GeometryNodeStoreNamedAttribute', MAT_X - 150, IRIS_R_Y, "Iris R Color")
    iris_r_color.data_type = 'FLOAT_COLOR'
    iris_r_color.domain = 'POINT'
    iris_r_color.inputs['Name'].default_value = "Color"

    iris_r_mat = add_node(tree, 'GeometryNodeSetMaterial', MAT_X, IRIS_R_Y, "Iris R Material")
    iris_r_mat.inputs['Material'].default_value = mats['iris']

    tree.links.new(group_in2.outputs['eyeBlinkRight'], iris_r_blink.inputs[0])
    tree.links.new(iris_r_blink.outputs[0], iris_r_open.inputs[1])
    tree.links.new(iris_r_open.outputs[0], iris_r_sz.inputs[0])
    tree.links.new(group_in2.outputs['Eye Size'], iris_r_sz.inputs[1])

    tree.links.new(group_in2.outputs['eyeLookInRight'], iris_r_look.inputs[0])
    tree.links.new(group_in2.outputs['Eye Spacing'], iris_r_base_x.inputs[1])
    tree.links.new(iris_r_base_x.outputs[0], iris_r_final_x.inputs[0])
    tree.links.new(iris_r_look.outputs[0], iris_r_final_x.inputs[1])

    tree.links.new(iris_r_final_x.outputs[0], iris_r_pos.inputs['X'])
    tree.links.new(group_in2.outputs['Eyes Depth'], iris_r_pos_y.inputs[1])
    tree.links.new(iris_r_pos_y.outputs[0], iris_r_pos.inputs['Y'])
    tree.links.new(eyes_height_z.outputs[0], iris_r_pos.inputs['Z'])
    tree.links.new(group_in2.outputs['Eye Size'], iris_r_scale.inputs['X'])
    tree.links.new(group_in2.outputs['Eye Size'], iris_r_scale.inputs['Y'])
    tree.links.new(iris_r_sz.outputs[0], iris_r_scale.inputs['Z'])

    tree.links.new(iris_r_sphere.outputs['Mesh'], iris_r_xform.inputs['Geometry'])
    tree.links.new(iris_r_pos.outputs['Vector'], iris_r_xform.inputs['Translation'])
    tree.links.new(iris_r_scale.outputs['Vector'], iris_r_xform.inputs['Scale'])
    tree.links.new(iris_r_xform.outputs['Geometry'], iris_r_color.inputs['Geometry'])
    tree.links.new(group_in2.outputs['Eye Color'], iris_r_color.inputs['Value'])
    tree.links.new(iris_r_color.outputs['Geometry'], iris_r_mat.inputs['Geometry'])

    # ------------------------------------------------------------------
    # LEFT PUPIL — small dark sphere inside iris
    # ------------------------------------------------------------------

    pupil_l_sphere = add_node(tree, 'GeometryNodeMeshUVSphere', PRIM_X, PUPIL_L_Y, "Pupil L Sphere")
    pupil_l_sphere.inputs['Segments'].default_value = 8
    pupil_l_sphere.inputs['Rings'].default_value = 4
    pupil_l_sphere.inputs['Radius'].default_value = 0.06

    pupil_l_pos_y = add_node(tree, 'ShaderNodeMath', MATH_X + 150, PUPIL_L_Y + 30, "Pupil L Pos Y")
    pupil_l_pos_y.operation = 'MULTIPLY'
    pupil_l_pos_y.inputs[0].default_value = -0.78

    pupil_l_pos = add_node(tree, 'ShaderNodeCombineXYZ', COMBINE_X, PUPIL_L_Y, "Pupil L Pos")
    pupil_l_pos.inputs['Z'].default_value = 1.25  # overridden by Eyes Height link

    # Share the X position from iris
    pupil_l_xform = add_node(tree, 'GeometryNodeTransform', XFORM_X, PUPIL_L_Y, "Pupil L Transform")

    pupil_l_mat = add_node(tree, 'GeometryNodeSetMaterial', MAT_X, PUPIL_L_Y, "Pupil L Material")
    pupil_l_mat.inputs['Material'].default_value = mats['pupil']

    tree.links.new(iris_l_final_x.outputs[0], pupil_l_pos.inputs['X'])
    tree.links.new(group_in2.outputs['Eyes Depth'], pupil_l_pos_y.inputs[1])
    tree.links.new(pupil_l_pos_y.outputs[0], pupil_l_pos.inputs['Y'])
    tree.links.new(eyes_height_z.outputs[0], pupil_l_pos.inputs['Z'])
    tree.links.new(pupil_l_sphere.outputs['Mesh'], pupil_l_xform.inputs['Geometry'])
    tree.links.new(pupil_l_pos.outputs['Vector'], pupil_l_xform.inputs['Translation'])
    tree.links.new(pupil_l_xform.outputs['Geometry'], pupil_l_mat.inputs['Geometry'])

    # ------------------------------------------------------------------
    # RIGHT PUPIL
    # ------------------------------------------------------------------

    pupil_r_sphere = add_node(tree, 'GeometryNodeMeshUVSphere', PRIM_X, PUPIL_R_Y, "Pupil R Sphere")
    pupil_r_sphere.inputs['Segments'].default_value = 8
    pupil_r_sphere.inputs['Rings'].default_value = 4
    pupil_r_sphere.inputs['Radius'].default_value = 0.06

    pupil_r_pos_y = add_node(tree, 'ShaderNodeMath', MATH_X + 150, PUPIL_R_Y + 30, "Pupil R Pos Y")
    pupil_r_pos_y.operation = 'MULTIPLY'
    pupil_r_pos_y.inputs[0].default_value = -0.78

    pupil_r_pos = add_node(tree, 'ShaderNodeCombineXYZ', COMBINE_X, PUPIL_R_Y, "Pupil R Pos")
    pupil_r_pos.inputs['Z'].default_value = 1.25  # overridden by Eyes Height link

    pupil_r_xform = add_node(tree, 'GeometryNodeTransform', XFORM_X, PUPIL_R_Y, "Pupil R Transform")

    pupil_r_mat = add_node(tree, 'GeometryNodeSetMaterial', MAT_X, PUPIL_R_Y, "Pupil R Material")
    pupil_r_mat.inputs['Material'].default_value = mats['pupil']

    tree.links.new(iris_r_final_x.outputs[0], pupil_r_pos.inputs['X'])
    tree.links.new(group_in2.outputs['Eyes Depth'], pupil_r_pos_y.inputs[1])
    tree.links.new(pupil_r_pos_y.outputs[0], pupil_r_pos.inputs['Y'])
    tree.links.new(eyes_height_z.outputs[0], pupil_r_pos.inputs['Z'])
    tree.links.new(pupil_r_sphere.outputs['Mesh'], pupil_r_xform.inputs['Geometry'])
    tree.links.new(pupil_r_pos.outputs['Vector'], pupil_r_xform.inputs['Translation'])
    tree.links.new(pupil_r_xform.outputs['Geometry'], pupil_r_mat.inputs['Geometry'])

    # ------------------------------------------------------------------
    # MOUTH — curve-profile with per-vertex deformation
    #
    # A filled circle (flat disc) where each vertex deforms based on
    # face tracking inputs. Bottom drops with jawOpen, corners lift
    # with smile, everything narrows with funnel. Reads like a flat
    # graphic mouth — think Adventure Time or OK Go puppet.
    # ------------------------------------------------------------------

    # Extra column positions for the mouth deformation chain
    MOUTH_DEFORM_X = MATH_X - 600
    MOUTH_FIELD_X = MATH_X - 400
    MOUTH_CALC_X = MATH_X - 200

    # --- Mesh Circle (the mouth shape — flat disc in XY plane) ---
    mouth_circle = add_node(tree, 'GeometryNodeMeshCircle', PRIM_X, MOUTH_Y, "Mouth Circle")
    mouth_circle.inputs['Vertices'].default_value = 24
    mouth_circle.inputs['Radius'].default_value = 1.0
    mouth_circle.fill_type = 'NGON'

    # --- Read vertex positions to compute per-vertex deformation ---
    mouth_pos_read = add_node(tree, 'GeometryNodeInputPosition', MOUTH_DEFORM_X, MOUTH_Y, "Mouth Vtx Pos")
    mouth_sep_xyz = add_node(tree, 'ShaderNodeSeparateXYZ', MOUTH_FIELD_X, MOUTH_Y, "Mouth Sep XYZ")
    tree.links.new(mouth_pos_read.outputs['Position'], mouth_sep_xyz.inputs['Vector'])

    # --- Bottom mask: how far below center (0 at top, gradual at bottom) ---
    # Negate Y so positive = below center
    mouth_neg_y = add_node(tree, 'ShaderNodeMath', MOUTH_FIELD_X, MOUTH_Y - 70, "Negate Y")
    mouth_neg_y.operation = 'MULTIPLY'
    mouth_neg_y.inputs[1].default_value = -1.0
    tree.links.new(mouth_sep_xyz.outputs['Y'], mouth_neg_y.inputs[0])

    # Clamp: max(0, -y) — only bottom vertices get affected
    mouth_bottom_amt = add_node(tree, 'ShaderNodeMath', MOUTH_CALC_X, MOUTH_Y - 70, "Bottom Amount")
    mouth_bottom_amt.operation = 'MAXIMUM'
    mouth_bottom_amt.inputs[1].default_value = 0.0
    tree.links.new(mouth_neg_y.outputs[0], mouth_bottom_amt.inputs[0])

    # --- Jaw drop: bottom vertices move down by jawOpen * strength * bottom_amount ---
    mouth_jaw_str = add_node(tree, 'ShaderNodeMath', MOUTH_CALC_X, MOUTH_Y - 140, "Jaw Strength")
    mouth_jaw_str.operation = 'MULTIPLY'
    mouth_jaw_str.inputs[1].default_value = -0.8  # negative = down in Y
    tree.links.new(group_in2.outputs['jawOpen'], mouth_jaw_str.inputs[0])

    mouth_jaw_offset = add_node(tree, 'ShaderNodeMath', MATH_X, MOUTH_Y - 140, "Jaw Offset")
    mouth_jaw_offset.operation = 'MULTIPLY'
    tree.links.new(mouth_jaw_str.outputs[0], mouth_jaw_offset.inputs[0])
    tree.links.new(mouth_bottom_amt.outputs[0], mouth_jaw_offset.inputs[1])

    # --- Corner amount: abs(x) — how far left/right from center ---
    mouth_abs_x = add_node(tree, 'ShaderNodeMath', MOUTH_FIELD_X, MOUTH_Y - 210, "Abs X")
    mouth_abs_x.operation = 'ABSOLUTE'
    tree.links.new(mouth_sep_xyz.outputs['X'], mouth_abs_x.inputs[0])

    # --- Smile lift: corners move up by smile * strength * abs(x) ---
    mouth_smile_str = add_node(tree, 'ShaderNodeMath', MOUTH_CALC_X, MOUTH_Y - 210, "Smile Strength")
    mouth_smile_str.operation = 'MULTIPLY'
    mouth_smile_str.inputs[1].default_value = 0.4  # positive = up in Y
    tree.links.new(group_in2.outputs['mouthSmileRight'], mouth_smile_str.inputs[0])

    mouth_smile_offset = add_node(tree, 'ShaderNodeMath', MATH_X, MOUTH_Y - 210, "Smile Offset")
    mouth_smile_offset.operation = 'MULTIPLY'
    tree.links.new(mouth_smile_str.outputs[0], mouth_smile_offset.inputs[0])
    tree.links.new(mouth_abs_x.outputs[0], mouth_smile_offset.inputs[1])

    # --- Frown drop: corners move down by frown * strength * abs(x) ---
    # Average left + right frown for symmetrical effect
    mouth_frown_avg = add_node(tree, 'ShaderNodeMath', MOUTH_CALC_X - 100, MOUTH_Y - 280, "Frown Avg")
    mouth_frown_avg.operation = 'ADD'
    tree.links.new(group_in2.outputs['mouthFrownLeft'], mouth_frown_avg.inputs[0])
    tree.links.new(group_in2.outputs['mouthFrownRight'], mouth_frown_avg.inputs[1])

    mouth_frown_str = add_node(tree, 'ShaderNodeMath', MOUTH_CALC_X, MOUTH_Y - 280, "Frown Strength")
    mouth_frown_str.operation = 'MULTIPLY'
    mouth_frown_str.inputs[1].default_value = -0.3  # negative = down (opposite of smile)
    tree.links.new(mouth_frown_avg.outputs[0], mouth_frown_str.inputs[0])

    mouth_frown_offset = add_node(tree, 'ShaderNodeMath', MATH_X, MOUTH_Y - 280, "Frown Offset")
    mouth_frown_offset.operation = 'MULTIPLY'
    tree.links.new(mouth_frown_str.outputs[0], mouth_frown_offset.inputs[0])
    tree.links.new(mouth_abs_x.outputs[0], mouth_frown_offset.inputs[1])

    # --- Combine Y offset: jaw_drop + smile_lift + frown_drop ---
    mouth_y_smile_frown = add_node(tree, 'ShaderNodeMath', MATH_X + 80, MOUTH_Y - 210, "Smile+Frown")
    mouth_y_smile_frown.operation = 'ADD'
    tree.links.new(mouth_smile_offset.outputs[0], mouth_y_smile_frown.inputs[0])
    tree.links.new(mouth_frown_offset.outputs[0], mouth_y_smile_frown.inputs[1])

    mouth_y_total = add_node(tree, 'ShaderNodeMath', MATH_X + 150, MOUTH_Y - 175, "Mouth Y Total")
    mouth_y_total.operation = 'ADD'
    tree.links.new(mouth_jaw_offset.outputs[0], mouth_y_total.inputs[0])
    tree.links.new(mouth_y_smile_frown.outputs[0], mouth_y_total.inputs[1])

    # --- Funnel/pucker: narrow the X toward center ---
    # new_x = x * (1 - funnel * 0.4)
    mouth_funnel_factor = add_node(tree, 'ShaderNodeMath', MOUTH_CALC_X, MOUTH_Y - 280, "Funnel Factor")
    mouth_funnel_factor.operation = 'MULTIPLY'
    mouth_funnel_factor.inputs[1].default_value = 0.4
    tree.links.new(group_in2.outputs['mouthFunnel'], mouth_funnel_factor.inputs[0])

    mouth_funnel_inv = add_node(tree, 'ShaderNodeMath', MATH_X, MOUTH_Y - 280, "1 - Funnel")
    mouth_funnel_inv.operation = 'SUBTRACT'
    mouth_funnel_inv.inputs[0].default_value = 1.0
    tree.links.new(mouth_funnel_factor.outputs[0], mouth_funnel_inv.inputs[1])

    mouth_new_x = add_node(tree, 'ShaderNodeMath', MATH_X + 150, MOUTH_Y - 280, "New X")
    mouth_new_x.operation = 'MULTIPLY'
    tree.links.new(mouth_sep_xyz.outputs['X'], mouth_new_x.inputs[0])
    tree.links.new(mouth_funnel_inv.outputs[0], mouth_new_x.inputs[1])

    # --- Squish Y: flatten circle to thin oval at rest ---
    # Without this, the circle looks like an open mouth even when jaw is closed.
    # Factor 0.25 = mouth is a thin horizontal line. jawOpen pushes it open.
    mouth_squish_y = add_node(tree, 'ShaderNodeMath', MOUTH_FIELD_X + 100, MOUTH_Y - 35, "Mouth Squish Y")
    mouth_squish_y.operation = 'MULTIPLY'
    mouth_squish_y.inputs[1].default_value = 0.12
    tree.links.new(mouth_sep_xyz.outputs['Y'], mouth_squish_y.inputs[0])

    # --- Build new position: (new_x, squished_y + y_offset, 0) ---
    mouth_new_y = add_node(tree, 'ShaderNodeMath', MATH_X + 150, MOUTH_Y - 70, "New Y")
    mouth_new_y.operation = 'ADD'
    tree.links.new(mouth_squish_y.outputs[0], mouth_new_y.inputs[0])
    tree.links.new(mouth_y_total.outputs[0], mouth_new_y.inputs[1])

    mouth_new_pos = add_node(tree, 'ShaderNodeCombineXYZ', COMBINE_X, MOUTH_Y - 140, "Mouth New Pos")
    mouth_new_pos.inputs['Z'].default_value = 0.0
    tree.links.new(mouth_new_x.outputs[0], mouth_new_pos.inputs['X'])
    tree.links.new(mouth_new_y.outputs[0], mouth_new_pos.inputs['Y'])

    # --- Set Position (apply deformation field to mesh circle) ---
    mouth_set_pos = add_node(tree, 'GeometryNodeSetPosition', COMBINE_X + 200, MOUTH_Y, "Mouth Set Pos")
    tree.links.new(mouth_circle.outputs['Mesh'], mouth_set_pos.inputs['Geometry'])
    tree.links.new(mouth_new_pos.outputs['Vector'], mouth_set_pos.inputs['Position'])

    # --- Transform: scale to mouth proportions, rotate into face plane,
    #     position on blob face. Circle is in XY plane, face looks toward -Y,
    #     so rotate 90° around X to stand it up into XZ plane. ---
    #
    #     Scale X = width (0.12 * MouthSize)
    #     Scale Y = height (0.08 * MouthSize) — the circle's Y becomes Z on face
    #     Scale Z = depth (thin — 0.02)
    mouth_scale_w = add_node(tree, 'ShaderNodeMath', MATH_X, MOUTH_Y - 350, "Mouth Width")
    mouth_scale_w.operation = 'MULTIPLY'
    mouth_scale_w.inputs[0].default_value = 0.28
    tree.links.new(group_in2.outputs['Mouth Size'], mouth_scale_w.inputs[1])

    mouth_scale_h = add_node(tree, 'ShaderNodeMath', MATH_X, MOUTH_Y - 420, "Mouth Height")
    mouth_scale_h.operation = 'MULTIPLY'
    mouth_scale_h.inputs[0].default_value = 0.28  # bumped from 0.20 to compensate for Y squish
    tree.links.new(group_in2.outputs['Mouth Size'], mouth_scale_h.inputs[1])

    mouth_scale_vec = add_node(tree, 'ShaderNodeCombineXYZ', COMBINE_X, MOUTH_Y - 350, "Mouth Scale")
    mouth_scale_vec.inputs['Z'].default_value = 0.06
    tree.links.new(mouth_scale_w.outputs[0], mouth_scale_vec.inputs['X'])
    tree.links.new(mouth_scale_h.outputs[0], mouth_scale_vec.inputs['Y'])

    # Mouth center position on blob (drops slightly when jaw opens)
    mouth_drop = add_node(tree, 'ShaderNodeMath', MATH_X + 150, MOUTH_Y - 490, "Jaw Drop")
    mouth_drop.operation = 'MULTIPLY'
    mouth_drop.inputs[1].default_value = -0.08
    tree.links.new(group_in2.outputs['jawOpen'], mouth_drop.inputs[0])

    mouth_center_z = add_node(tree, 'ShaderNodeMath', COMBINE_X, MOUTH_Y - 490, "Mouth Center Z")
    mouth_center_z.operation = 'ADD'
    mouth_center_z.inputs[0].default_value = 0.5  # overridden by Mouth Height link
    tree.links.new(mouth_height_z.outputs[0], mouth_center_z.inputs[0])
    tree.links.new(mouth_drop.outputs[0], mouth_center_z.inputs[1])

    mouth_center_y = add_node(tree, 'ShaderNodeMath', COMBINE_X - 150, MOUTH_Y - 420, "Mouth Center Y")
    mouth_center_y.operation = 'MULTIPLY'
    mouth_center_y.inputs[0].default_value = -0.88

    # Mouth left/right shift: (mouthRight - mouthLeft) * 0.15
    mouth_lr_diff = add_node(tree, 'ShaderNodeMath', COMBINE_X - 300, MOUTH_Y - 350, "Mouth LR Diff")
    mouth_lr_diff.operation = 'SUBTRACT'
    tree.links.new(group_in2.outputs['mouthRight'], mouth_lr_diff.inputs[0])
    tree.links.new(group_in2.outputs['mouthLeft'], mouth_lr_diff.inputs[1])

    mouth_lr_shift = add_node(tree, 'ShaderNodeMath', COMBINE_X - 150, MOUTH_Y - 350, "Mouth LR Shift")
    mouth_lr_shift.operation = 'MULTIPLY'
    mouth_lr_shift.inputs[1].default_value = 0.15
    tree.links.new(mouth_lr_diff.outputs[0], mouth_lr_shift.inputs[0])

    mouth_center = add_node(tree, 'ShaderNodeCombineXYZ', COMBINE_X, MOUTH_Y - 420, "Mouth Center")
    tree.links.new(mouth_lr_shift.outputs[0], mouth_center.inputs['X'])
    tree.links.new(group_in2.outputs['Mouth Depth'], mouth_center_y.inputs[1])
    tree.links.new(mouth_center_y.outputs[0], mouth_center.inputs['Y'])
    tree.links.new(mouth_center_z.outputs[0], mouth_center.inputs['Z'])

    # Rotation: 90° around X to stand circle up
    mouth_rot = add_node(tree, 'ShaderNodeCombineXYZ', COMBINE_X, MOUTH_Y - 560, "Mouth Rotation")
    mouth_rot.inputs['X'].default_value = 1.5708  # pi/2
    mouth_rot.inputs['Y'].default_value = 0.0
    mouth_rot.inputs['Z'].default_value = 0.0

    mouth_xform = add_node(tree, 'GeometryNodeTransform', XFORM_X, MOUTH_Y, "Mouth Transform")
    tree.links.new(mouth_set_pos.outputs['Geometry'], mouth_xform.inputs['Geometry'])
    tree.links.new(mouth_center.outputs['Vector'], mouth_xform.inputs['Translation'])
    tree.links.new(mouth_scale_vec.outputs['Vector'], mouth_xform.inputs['Scale'])
    tree.links.new(mouth_rot.outputs['Vector'], mouth_xform.inputs['Rotation'])

    mouth_color = add_node(tree, 'GeometryNodeStoreNamedAttribute', MAT_X - 150, MOUTH_Y, "Mouth Color")
    mouth_color.data_type = 'FLOAT_COLOR'
    mouth_color.domain = 'POINT'
    mouth_color.inputs['Name'].default_value = "Color"

    mouth_mat = add_node(tree, 'GeometryNodeSetMaterial', MAT_X, MOUTH_Y, "Mouth Material")
    mouth_mat.inputs['Material'].default_value = mats['mouth']
    tree.links.new(mouth_xform.outputs['Geometry'], mouth_color.inputs['Geometry'])
    tree.links.new(group_in2.outputs['Mouth Color'], mouth_color.inputs['Value'])
    tree.links.new(mouth_color.outputs['Geometry'], mouth_mat.inputs['Geometry'])

    # ------------------------------------------------------------------
    # EARS — simple spheres, scalable
    # ------------------------------------------------------------------

    ear_l_sphere = add_node(tree, 'GeometryNodeMeshUVSphere', PRIM_X, EAR_L_Y, "Ear L Sphere")
    ear_l_sphere.inputs['Segments'].default_value = 12
    ear_l_sphere.inputs['Rings'].default_value = 6
    ear_l_sphere.inputs['Radius'].default_value = 0.18

    ear_l_scale = add_node(tree, 'ShaderNodeCombineXYZ', COMBINE_X, EAR_L_Y, "Ear L Scale")

    ear_l_scale_x = add_node(tree, 'ShaderNodeMath', MATH_X, EAR_L_Y, "Ear L Sx")
    ear_l_scale_x.operation = 'MULTIPLY'
    ear_l_scale_x.inputs[0].default_value = 0.7

    ear_l_scale_y = add_node(tree, 'ShaderNodeMath', MATH_X, EAR_L_Y - 60, "Ear L Sy")
    ear_l_scale_y.operation = 'MULTIPLY'
    ear_l_scale_y.inputs[0].default_value = 0.8

    ear_l_scale_z = add_node(tree, 'ShaderNodeMath', MATH_X, EAR_L_Y - 120, "Ear L Sz")
    ear_l_scale_z.operation = 'MULTIPLY'
    ear_l_scale_z.inputs[0].default_value = 0.9

    ear_l_pos = add_node(tree, 'ShaderNodeCombineXYZ', COMBINE_X, EAR_L_Y + 60, "Ear L Pos")

    ear_l_xform = add_node(tree, 'GeometryNodeTransform', XFORM_X, EAR_L_Y, "Ear L Transform")

    ear_l_color = add_node(tree, 'GeometryNodeStoreNamedAttribute', MAT_X - 150, EAR_L_Y, "Ear L Color")
    ear_l_color.data_type = 'FLOAT_COLOR'
    ear_l_color.domain = 'POINT'
    ear_l_color.inputs['Name'].default_value = "Color"

    ear_l_mat = add_node(tree, 'GeometryNodeSetMaterial', MAT_X, EAR_L_Y, "Ear L Material")
    ear_l_mat.inputs['Material'].default_value = mats['ear']

    tree.links.new(group_in2.outputs['Ear Size'], ear_l_scale_x.inputs[1])
    tree.links.new(group_in2.outputs['Ear Size'], ear_l_scale_y.inputs[1])
    tree.links.new(group_in2.outputs['Ear Size'], ear_l_scale_z.inputs[1])
    tree.links.new(ear_l_scale_x.outputs[0], ear_l_scale.inputs['X'])
    tree.links.new(ear_l_scale_y.outputs[0], ear_l_scale.inputs['Y'])
    tree.links.new(ear_l_scale_z.outputs[0], ear_l_scale.inputs['Z'])
    tree.links.new(ears_spread_neg.outputs[0], ear_l_pos.inputs['X'])
    tree.links.new(ears_depth_y.outputs[0], ear_l_pos.inputs['Y'])
    tree.links.new(ears_height_z.outputs[0], ear_l_pos.inputs['Z'])
    tree.links.new(ear_l_sphere.outputs['Mesh'], ear_l_xform.inputs['Geometry'])
    tree.links.new(ear_l_pos.outputs['Vector'], ear_l_xform.inputs['Translation'])
    tree.links.new(ear_l_scale.outputs['Vector'], ear_l_xform.inputs['Scale'])
    tree.links.new(ear_l_xform.outputs['Geometry'], ear_l_color.inputs['Geometry'])
    tree.links.new(group_in2.outputs['Ear Color'], ear_l_color.inputs['Value'])
    tree.links.new(ear_l_color.outputs['Geometry'], ear_l_mat.inputs['Geometry'])

    # Right ear
    ear_r_sphere = add_node(tree, 'GeometryNodeMeshUVSphere', PRIM_X, EAR_R_Y, "Ear R Sphere")
    ear_r_sphere.inputs['Segments'].default_value = 12
    ear_r_sphere.inputs['Rings'].default_value = 6
    ear_r_sphere.inputs['Radius'].default_value = 0.18

    ear_r_scale = add_node(tree, 'ShaderNodeCombineXYZ', COMBINE_X, EAR_R_Y, "Ear R Scale")

    ear_r_scale_x = add_node(tree, 'ShaderNodeMath', MATH_X, EAR_R_Y, "Ear R Sx")
    ear_r_scale_x.operation = 'MULTIPLY'
    ear_r_scale_x.inputs[0].default_value = 0.7

    ear_r_scale_y = add_node(tree, 'ShaderNodeMath', MATH_X, EAR_R_Y - 60, "Ear R Sy")
    ear_r_scale_y.operation = 'MULTIPLY'
    ear_r_scale_y.inputs[0].default_value = 0.8

    ear_r_scale_z = add_node(tree, 'ShaderNodeMath', MATH_X, EAR_R_Y - 120, "Ear R Sz")
    ear_r_scale_z.operation = 'MULTIPLY'
    ear_r_scale_z.inputs[0].default_value = 0.9

    ear_r_pos = add_node(tree, 'ShaderNodeCombineXYZ', COMBINE_X, EAR_R_Y + 60, "Ear R Pos")

    ear_r_xform = add_node(tree, 'GeometryNodeTransform', XFORM_X, EAR_R_Y, "Ear R Transform")

    ear_r_color = add_node(tree, 'GeometryNodeStoreNamedAttribute', MAT_X - 150, EAR_R_Y, "Ear R Color")
    ear_r_color.data_type = 'FLOAT_COLOR'
    ear_r_color.domain = 'POINT'
    ear_r_color.inputs['Name'].default_value = "Color"

    ear_r_mat = add_node(tree, 'GeometryNodeSetMaterial', MAT_X, EAR_R_Y, "Ear R Material")
    ear_r_mat.inputs['Material'].default_value = mats['ear']

    tree.links.new(group_in2.outputs['Ear Size'], ear_r_scale_x.inputs[1])
    tree.links.new(group_in2.outputs['Ear Size'], ear_r_scale_y.inputs[1])
    tree.links.new(group_in2.outputs['Ear Size'], ear_r_scale_z.inputs[1])
    tree.links.new(ear_r_scale_x.outputs[0], ear_r_scale.inputs['X'])
    tree.links.new(ear_r_scale_y.outputs[0], ear_r_scale.inputs['Y'])
    tree.links.new(ear_r_scale_z.outputs[0], ear_r_scale.inputs['Z'])
    tree.links.new(ears_spread_x.outputs[0], ear_r_pos.inputs['X'])
    tree.links.new(ears_depth_y.outputs[0], ear_r_pos.inputs['Y'])
    tree.links.new(ears_height_z.outputs[0], ear_r_pos.inputs['Z'])
    tree.links.new(ear_r_sphere.outputs['Mesh'], ear_r_xform.inputs['Geometry'])
    tree.links.new(ear_r_pos.outputs['Vector'], ear_r_xform.inputs['Translation'])
    tree.links.new(ear_r_scale.outputs['Vector'], ear_r_xform.inputs['Scale'])
    tree.links.new(ear_r_xform.outputs['Geometry'], ear_r_color.inputs['Geometry'])
    tree.links.new(group_in2.outputs['Ear Color'], ear_r_color.inputs['Value'])
    tree.links.new(ear_r_color.outputs['Geometry'], ear_r_mat.inputs['Geometry'])

    # ------------------------------------------------------------------
    # EYEBROWS — squished ovals above each eye
    #
    # Positioned relative to Eyes Height so they follow the eyes.
    # Eyebrow Height slider adjusts the vertical offset above eyes.
    # Eventually brow ARKit shapes will tilt/raise them.
    # ------------------------------------------------------------------

    # Brow Z position: Eyes Height Z + 0.22 * Eyebrow Height
    brow_z_offset = add_node(tree, 'ShaderNodeMath', INPUT_X + 300, -700, "Brow Z Offset")
    brow_z_offset.operation = 'MULTIPLY'
    brow_z_offset.inputs[0].default_value = 0.22
    tree.links.new(group_in.outputs['Eyebrow Height'], brow_z_offset.inputs[1])

    brow_z = add_node(tree, 'ShaderNodeMath', INPUT_X + 500, -700, "Brow Z")
    brow_z.operation = 'ADD'
    tree.links.new(eyes_height_z.outputs[0], brow_z.inputs[0])
    tree.links.new(brow_z_offset.outputs[0], brow_z.inputs[1])

    # --- Left Eyebrow ---
    brow_l_sphere = add_node(tree, 'GeometryNodeMeshUVSphere', PRIM_X, BROW_L_Y, "Brow L Sphere")
    brow_l_sphere.inputs['Segments'].default_value = 12
    brow_l_sphere.inputs['Rings'].default_value = 6
    brow_l_sphere.inputs['Radius'].default_value = 0.14

    # Scale: wide and flat (squished oval)
    brow_l_sx = add_node(tree, 'ShaderNodeMath', MATH_X, BROW_L_Y, "Brow L Sx")
    brow_l_sx.operation = 'MULTIPLY'
    brow_l_sx.inputs[0].default_value = 1.8  # wide
    tree.links.new(group_in2.outputs['Eyebrow Size'], brow_l_sx.inputs[1])

    brow_l_sy = add_node(tree, 'ShaderNodeMath', MATH_X, BROW_L_Y - 60, "Brow L Sy")
    brow_l_sy.operation = 'MULTIPLY'
    brow_l_sy.inputs[0].default_value = 0.35  # thin front-to-back
    tree.links.new(group_in2.outputs['Eyebrow Size'], brow_l_sy.inputs[1])

    brow_l_sz = add_node(tree, 'ShaderNodeMath', MATH_X, BROW_L_Y - 120, "Brow L Sz")
    brow_l_sz.operation = 'MULTIPLY'
    brow_l_sz.inputs[0].default_value = 0.5  # thin vertically
    tree.links.new(group_in2.outputs['Eyebrow Size'], brow_l_sz.inputs[1])

    brow_l_scale = add_node(tree, 'ShaderNodeCombineXYZ', COMBINE_X, BROW_L_Y, "Brow L Scale")
    tree.links.new(brow_l_sx.outputs[0], brow_l_scale.inputs['X'])
    tree.links.new(brow_l_sy.outputs[0], brow_l_scale.inputs['Y'])
    tree.links.new(brow_l_sz.outputs[0], brow_l_scale.inputs['Z'])

    # Position: above left eye
    brow_l_pos_x = add_node(tree, 'ShaderNodeMath', MATH_X, BROW_L_Y + 60, "Brow L Pos X")
    brow_l_pos_x.operation = 'MULTIPLY'
    brow_l_pos_x.inputs[0].default_value = -0.32
    tree.links.new(group_in.outputs['Eye Spacing'], brow_l_pos_x.inputs[1])

    brow_l_pos_y = add_node(tree, 'ShaderNodeMath', MATH_X + 150, BROW_L_Y + 60, "Brow L Pos Y")
    brow_l_pos_y.operation = 'MULTIPLY'
    brow_l_pos_y.inputs[0].default_value = -0.48
    tree.links.new(group_in.outputs['Eyes Depth'], brow_l_pos_y.inputs[1])

    brow_l_pos = add_node(tree, 'ShaderNodeCombineXYZ', COMBINE_X, BROW_L_Y + 60, "Brow L Pos")
    tree.links.new(brow_l_pos_x.outputs[0], brow_l_pos.inputs['X'])
    tree.links.new(brow_l_pos_y.outputs[0], brow_l_pos.inputs['Y'])
    tree.links.new(brow_z.outputs[0], brow_l_pos.inputs['Z'])

    brow_l_xform = add_node(tree, 'GeometryNodeTransform', XFORM_X, BROW_L_Y, "Brow L Transform")

    brow_l_color = add_node(tree, 'GeometryNodeStoreNamedAttribute', MAT_X - 150, BROW_L_Y, "Brow L Color")
    brow_l_color.data_type = 'FLOAT_COLOR'
    brow_l_color.domain = 'POINT'
    brow_l_color.inputs['Name'].default_value = "Color"

    brow_l_mat = add_node(tree, 'GeometryNodeSetMaterial', MAT_X, BROW_L_Y, "Brow L Material")
    brow_l_mat.inputs['Material'].default_value = mats['brow']

    tree.links.new(brow_l_sphere.outputs['Mesh'], brow_l_xform.inputs['Geometry'])
    tree.links.new(brow_l_pos.outputs['Vector'], brow_l_xform.inputs['Translation'])
    tree.links.new(brow_l_scale.outputs['Vector'], brow_l_xform.inputs['Scale'])
    tree.links.new(brow_l_xform.outputs['Geometry'], brow_l_color.inputs['Geometry'])
    tree.links.new(group_in2.outputs['Eyebrow Color'], brow_l_color.inputs['Value'])
    tree.links.new(brow_l_color.outputs['Geometry'], brow_l_mat.inputs['Geometry'])

    # --- Right Eyebrow (mirror of left) ---
    brow_r_sphere = add_node(tree, 'GeometryNodeMeshUVSphere', PRIM_X, BROW_R_Y, "Brow R Sphere")
    brow_r_sphere.inputs['Segments'].default_value = 12
    brow_r_sphere.inputs['Rings'].default_value = 6
    brow_r_sphere.inputs['Radius'].default_value = 0.14

    brow_r_sx = add_node(tree, 'ShaderNodeMath', MATH_X, BROW_R_Y, "Brow R Sx")
    brow_r_sx.operation = 'MULTIPLY'
    brow_r_sx.inputs[0].default_value = 1.8
    tree.links.new(group_in2.outputs['Eyebrow Size'], brow_r_sx.inputs[1])

    brow_r_sy = add_node(tree, 'ShaderNodeMath', MATH_X, BROW_R_Y - 60, "Brow R Sy")
    brow_r_sy.operation = 'MULTIPLY'
    brow_r_sy.inputs[0].default_value = 0.35
    tree.links.new(group_in2.outputs['Eyebrow Size'], brow_r_sy.inputs[1])

    brow_r_sz = add_node(tree, 'ShaderNodeMath', MATH_X, BROW_R_Y - 120, "Brow R Sz")
    brow_r_sz.operation = 'MULTIPLY'
    brow_r_sz.inputs[0].default_value = 0.5
    tree.links.new(group_in2.outputs['Eyebrow Size'], brow_r_sz.inputs[1])

    brow_r_scale = add_node(tree, 'ShaderNodeCombineXYZ', COMBINE_X, BROW_R_Y, "Brow R Scale")
    tree.links.new(brow_r_sx.outputs[0], brow_r_scale.inputs['X'])
    tree.links.new(brow_r_sy.outputs[0], brow_r_scale.inputs['Y'])
    tree.links.new(brow_r_sz.outputs[0], brow_r_scale.inputs['Z'])

    brow_r_pos_x = add_node(tree, 'ShaderNodeMath', MATH_X, BROW_R_Y + 60, "Brow R Pos X")
    brow_r_pos_x.operation = 'MULTIPLY'
    brow_r_pos_x.inputs[0].default_value = 0.32  # mirrored
    tree.links.new(group_in2.outputs['Eye Spacing'], brow_r_pos_x.inputs[1])

    brow_r_pos_y = add_node(tree, 'ShaderNodeMath', MATH_X + 150, BROW_R_Y + 60, "Brow R Pos Y")
    brow_r_pos_y.operation = 'MULTIPLY'
    brow_r_pos_y.inputs[0].default_value = -0.48
    tree.links.new(group_in2.outputs['Eyes Depth'], brow_r_pos_y.inputs[1])

    brow_r_pos = add_node(tree, 'ShaderNodeCombineXYZ', COMBINE_X, BROW_R_Y + 60, "Brow R Pos")
    tree.links.new(brow_r_pos_x.outputs[0], brow_r_pos.inputs['X'])
    tree.links.new(brow_r_pos_y.outputs[0], brow_r_pos.inputs['Y'])
    tree.links.new(brow_z.outputs[0], brow_r_pos.inputs['Z'])

    brow_r_xform = add_node(tree, 'GeometryNodeTransform', XFORM_X, BROW_R_Y, "Brow R Transform")

    brow_r_color = add_node(tree, 'GeometryNodeStoreNamedAttribute', MAT_X - 150, BROW_R_Y, "Brow R Color")
    brow_r_color.data_type = 'FLOAT_COLOR'
    brow_r_color.domain = 'POINT'
    brow_r_color.inputs['Name'].default_value = "Color"

    brow_r_mat = add_node(tree, 'GeometryNodeSetMaterial', MAT_X, BROW_R_Y, "Brow R Material")
    brow_r_mat.inputs['Material'].default_value = mats['brow']

    tree.links.new(brow_r_sphere.outputs['Mesh'], brow_r_xform.inputs['Geometry'])
    tree.links.new(brow_r_pos.outputs['Vector'], brow_r_xform.inputs['Translation'])
    tree.links.new(brow_r_scale.outputs['Vector'], brow_r_xform.inputs['Scale'])
    tree.links.new(brow_r_xform.outputs['Geometry'], brow_r_color.inputs['Geometry'])
    tree.links.new(group_in2.outputs['Eyebrow Color'], brow_r_color.inputs['Value'])
    tree.links.new(brow_r_color.outputs['Geometry'], brow_r_mat.inputs['Geometry'])

    # ------------------------------------------------------------------
    # JOIN GEOMETRY — combine all parts
    # ------------------------------------------------------------------

    join = add_node(tree, 'GeometryNodeJoinGeometry', JOIN_X, -400, "Join All Parts")

    # Connect all parts to join (order = draw order, bottom connects first)
    tree.links.new(brow_r_mat.outputs['Geometry'], join.inputs['Geometry'])
    tree.links.new(brow_l_mat.outputs['Geometry'], join.inputs['Geometry'])
    tree.links.new(ear_r_mat.outputs['Geometry'], join.inputs['Geometry'])
    tree.links.new(ear_l_mat.outputs['Geometry'], join.inputs['Geometry'])
    tree.links.new(mouth_mat.outputs['Geometry'], join.inputs['Geometry'])
    tree.links.new(pupil_r_mat.outputs['Geometry'], join.inputs['Geometry'])
    tree.links.new(pupil_l_mat.outputs['Geometry'], join.inputs['Geometry'])
    tree.links.new(iris_r_mat.outputs['Geometry'], join.inputs['Geometry'])
    tree.links.new(iris_l_mat.outputs['Geometry'], join.inputs['Geometry'])
    tree.links.new(eye_r_mat.outputs['Geometry'], join.inputs['Geometry'])
    tree.links.new(eye_l_mat.outputs['Geometry'], join.inputs['Geometry'])
    tree.links.new(body_mat.outputs['Geometry'], join.inputs['Geometry'])

    # --- Group Output ---
    tree.links.new(join.outputs['Geometry'], group_out.inputs['Geometry'])

    return tree


# ===================================================================
# 4. ARMATURE (head bone for phone rotation)
# ===================================================================

def create_armature():
    """Create a simple armature with one 'head' bone."""
    bpy.ops.object.armature_add(location=(0, 0, 0))
    armature = bpy.context.active_object
    armature.name = "Blob_Armature"
    armature.data.name = "Blob_Armature"

    bpy.ops.object.mode_set(mode='EDIT')
    bone = armature.data.edit_bones[0]
    bone.name = "head"
    bone.head = (0, 0, 0.0)
    bone.tail = (0, 0, 1.8)
    bpy.ops.object.mode_set(mode='OBJECT')

    # CRITICAL: set pose bone to Euler rotation mode
    # The OSC receiver sends head rotation as Euler angles from the phone.
    # Blender defaults to Quaternion which ignores rotation_euler values.
    armature.pose.bones['head'].rotation_mode = 'XYZ'

    return armature


# ===================================================================
# 5. CREATE THE CHARACTER OBJECT WITH GEONODE MODIFIER
# ===================================================================

def create_character(tree, armature):
    """Create a mesh object and apply the geometry nodes modifier."""
    # Empty mesh — geonodes generates everything
    mesh = bpy.data.meshes.new("BlobPuppet")
    obj = bpy.data.objects.new("BlobPuppet", mesh)
    bpy.context.collection.objects.link(obj)

    # Add geometry nodes modifier
    mod = obj.modifiers.new("GeometryNodes", 'NODES')
    mod.node_group = tree

    # Parent to armature
    obj.parent = armature
    obj.parent_type = 'BONE'
    obj.parent_bone = 'head'
    # Offset so the character sits at origin when bone is at rest
    obj.matrix_parent_inverse = armature.pose.bones['head'].bone.matrix_local.inverted()

    return obj


# ===================================================================
# 6. DRIVERS — connect dummy mesh shape keys to geonode modifier
# ===================================================================

def setup_drivers(obj):
    """Add drivers from ARKitShapeKeys.Dummy to the geonode modifier inputs.

    The driver path format is: modifiers["GeometryNodes"]["Socket_X"]
    where Socket_X is the identifier from the node tree interface.
    """
    dummy = bpy.data.objects["ARKitShapeKeys.Dummy"]
    shape_keys = dummy.data.shape_keys
    tree = obj.modifiers["GeometryNodes"].node_group

    # Build a map: socket name -> socket identifier
    socket_map = {}
    for item in tree.interface.items_tree:
        if hasattr(item, 'in_out') and item.in_out == 'INPUT':
            socket_map[item.name] = item.identifier

    # Face tracking inputs to drive
    face_inputs = [
        'jawOpen', 'mouthSmileRight', 'mouthFunnel',
        'eyeBlinkLeft', 'eyeBlinkRight',
        'eyeWideLeft', 'eyeWideRight',
        'eyeLookInLeft', 'eyeLookInRight',
    ]

    for input_name in face_inputs:
        socket_id = socket_map.get(input_name)
        if not socket_id:
            print(f"  [!] Warning: no socket found for '{input_name}'")
            continue

        # The property path on the modifier
        data_path = f'modifiers["GeometryNodes"]["{socket_id}"]'

        driver = obj.driver_add(data_path)
        driver.driver.type = 'SCRIPTED'

        v = driver.driver.variables.new()
        v.name = 'var'
        v.type = 'SINGLE_PROP'
        v.targets[0].id_type = 'KEY'
        v.targets[0].id = shape_keys
        v.targets[0].data_path = f'key_blocks["{input_name}"].value'
        driver.driver.expression = 'var'

        print(f"  [+] Driver: {input_name} -> {socket_id}")


# ===================================================================
# 7. CAMERA + SCENE
# ===================================================================

def create_camera():
    """Create a camera framed on the character."""
    bpy.ops.object.camera_add(location=(0, -4.0, 1.0))
    cam = bpy.context.active_object
    cam.name = "Blob_Camera"
    cam.rotation_euler = (math.radians(82), 0, 0)
    bpy.context.scene.camera = cam
    cam.data.lens = 50
    return cam


def setup_scene():
    """Configure EEVEE, lighting, and background."""
    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_EEVEE'
    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1080
    scene.render.fps = 30

    world = bpy.data.worlds.get("World")
    if not world:
        world = bpy.data.worlds.new("World")
        scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value = (0.15, 0.2, 0.35, 1.0)
        bg.inputs["Strength"].default_value = 1.0

    bpy.ops.object.light_add(type='SUN', location=(2, -3, 5))
    light = bpy.context.active_object
    light.name = "Key_Light"
    light.data.energy = 3.0
    light.rotation_euler = (math.radians(45), math.radians(15), math.radians(-20))

    bpy.ops.object.light_add(type='AREA', location=(-2, -2, 3))
    fill = bpy.context.active_object
    fill.name = "Fill_Light"
    fill.data.energy = 50.0
    fill.data.size = 3.0
    fill.rotation_euler = (math.radians(60), 0, math.radians(30))


# ===================================================================
# MAIN
# ===================================================================

def main():
    print("\n=== Creating Blob Puppet Template V2 (Geometry Nodes) ===\n")

    clean_scene()
    mats = create_materials()
    print("  [+] Materials created")

    dummy = create_dummy_mesh()
    print("  [+] Dummy mesh with 13 ARKit shape keys")

    tree = build_geometry_nodes(mats)
    print("  [+] Geometry nodes tree built (GN_BlobPuppet)")

    armature = create_armature()
    print("  [+] Armature with 'head' bone")

    obj = create_character(tree, armature)
    print("  [+] Character object with geonode modifier")

    setup_drivers(obj)
    print("  [+] All face tracking drivers connected")

    cam = create_camera()
    setup_scene()
    print("  [+] Camera, lighting, and scene configured")

    # Select the character
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj

    print("\n=== Blob Puppet Template V2 Complete! ===")
    print("\nOpen the Geometry Nodes editor to see the full character graph.")
    print("Customization sliders are in the modifier panel:")
    print("  - Body Width / Body Height")
    print("  - Eye Size / Eye Spacing")
    print("  - Ear Size / Mouth Size")
    print("\nFace tracking (driven by ARKitShapeKeys.Dummy):")
    print("  - jawOpen, mouthSmileRight, mouthFunnel")
    print("  - eyeBlinkLeft/Right, eyeWideLeft/Right")
    print("  - eyeLookInLeft/Right")
    print("  - Head rotation → armature 'head' bone")


if __name__ == "__main__":
    main()
