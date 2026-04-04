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


def create_materials():
    """Create the color palette."""
    return {
        'body': make_material("Blob_Body", (1.0, 0.78, 0.65, 1.0)),
        'mouth': make_material("Blob_Mouth", (0.85, 0.35, 0.35, 1.0)),
        'eye_white': make_material("Blob_EyeWhite", (1.0, 1.0, 1.0, 1.0)),
        'iris': make_material("Blob_Iris", (0.2, 0.65, 0.7, 1.0)),
        'pupil': make_material("Blob_Pupil", (0.05, 0.05, 0.05, 1.0)),
        'ear': make_material("Blob_Ear", (1.0, 0.7, 0.55, 1.0)),
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
    23: 'mouthSmileRight',
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

    # --- Group Input & Output ---
    group_in = tree.nodes.new('NodeGroupInput')
    group_in.location = (INPUT_X, -400)

    group_out = tree.nodes.new('NodeGroupOutput')
    group_out.location = (OUT_X, -400)

    # We'll need a second Group Input for readability (Blender allows multiple)
    group_in2 = tree.nodes.new('NodeGroupInput')
    group_in2.location = (INPUT_X, -1400)

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

    body_mat = add_node(tree, 'GeometryNodeSetMaterial', MAT_X, BODY_Y, "Body Material")
    body_mat.inputs['Material'].default_value = mats['body']

    # Links: body
    tree.links.new(group_in.outputs['Body Width'], body_scale_w.inputs[0])
    tree.links.new(group_in.outputs['Body Height'], body_scale_h.inputs[0])
    tree.links.new(body_scale_w.outputs[0], body_combine.inputs['X'])
    tree.links.new(body_scale_h.outputs[0], body_combine.inputs['Z'])
    tree.links.new(body_sphere.outputs['Mesh'], body_xform.inputs['Geometry'])
    tree.links.new(body_combine.outputs['Vector'], body_xform.inputs['Scale'])
    tree.links.new(body_xform.outputs['Geometry'], body_mat.inputs['Geometry'])

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

    eye_l_pos = add_node(tree, 'ShaderNodeCombineXYZ', COMBINE_X, EYE_L_Y + 60, "L Eye Pos")
    eye_l_pos.inputs['Y'].default_value = -0.55
    eye_l_pos.inputs['Z'].default_value = 1.25

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

    eye_r_pos = add_node(tree, 'ShaderNodeCombineXYZ', COMBINE_X, EYE_R_Y + 60, "R Eye Pos")
    eye_r_pos.inputs['Y'].default_value = -0.55
    eye_r_pos.inputs['Z'].default_value = 1.25

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

    iris_l_pos = add_node(tree, 'ShaderNodeCombineXYZ', COMBINE_X, IRIS_L_Y, "Iris L Pos")
    iris_l_pos.inputs['Y'].default_value = -0.72
    iris_l_pos.inputs['Z'].default_value = 1.25

    iris_l_scale = add_node(tree, 'ShaderNodeCombineXYZ', COMBINE_X, IRIS_L_Y - 80, "Iris L Scale")

    iris_l_xform = add_node(tree, 'GeometryNodeTransform', XFORM_X, IRIS_L_Y, "Iris L Transform")

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
    tree.links.new(group_in.outputs['Eye Size'], iris_l_scale.inputs['X'])
    tree.links.new(group_in.outputs['Eye Size'], iris_l_scale.inputs['Y'])
    tree.links.new(iris_l_sz.outputs[0], iris_l_scale.inputs['Z'])

    tree.links.new(iris_l_sphere.outputs['Mesh'], iris_l_xform.inputs['Geometry'])
    tree.links.new(iris_l_pos.outputs['Vector'], iris_l_xform.inputs['Translation'])
    tree.links.new(iris_l_scale.outputs['Vector'], iris_l_xform.inputs['Scale'])
    tree.links.new(iris_l_xform.outputs['Geometry'], iris_l_mat.inputs['Geometry'])

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

    iris_r_pos = add_node(tree, 'ShaderNodeCombineXYZ', COMBINE_X, IRIS_R_Y, "Iris R Pos")
    iris_r_pos.inputs['Y'].default_value = -0.72
    iris_r_pos.inputs['Z'].default_value = 1.25

    iris_r_scale = add_node(tree, 'ShaderNodeCombineXYZ', COMBINE_X, IRIS_R_Y - 80, "Iris R Scale")

    iris_r_xform = add_node(tree, 'GeometryNodeTransform', XFORM_X, IRIS_R_Y, "Iris R Transform")

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
    tree.links.new(group_in2.outputs['Eye Size'], iris_r_scale.inputs['X'])
    tree.links.new(group_in2.outputs['Eye Size'], iris_r_scale.inputs['Y'])
    tree.links.new(iris_r_sz.outputs[0], iris_r_scale.inputs['Z'])

    tree.links.new(iris_r_sphere.outputs['Mesh'], iris_r_xform.inputs['Geometry'])
    tree.links.new(iris_r_pos.outputs['Vector'], iris_r_xform.inputs['Translation'])
    tree.links.new(iris_r_scale.outputs['Vector'], iris_r_xform.inputs['Scale'])
    tree.links.new(iris_r_xform.outputs['Geometry'], iris_r_mat.inputs['Geometry'])

    # ------------------------------------------------------------------
    # LEFT PUPIL — small dark sphere inside iris
    # ------------------------------------------------------------------

    pupil_l_sphere = add_node(tree, 'GeometryNodeMeshUVSphere', PRIM_X, PUPIL_L_Y, "Pupil L Sphere")
    pupil_l_sphere.inputs['Segments'].default_value = 8
    pupil_l_sphere.inputs['Rings'].default_value = 4
    pupil_l_sphere.inputs['Radius'].default_value = 0.06

    pupil_l_pos = add_node(tree, 'ShaderNodeCombineXYZ', COMBINE_X, PUPIL_L_Y, "Pupil L Pos")
    pupil_l_pos.inputs['Y'].default_value = -0.78
    pupil_l_pos.inputs['Z'].default_value = 1.25

    # Share the X position from iris
    pupil_l_xform = add_node(tree, 'GeometryNodeTransform', XFORM_X, PUPIL_L_Y, "Pupil L Transform")

    pupil_l_mat = add_node(tree, 'GeometryNodeSetMaterial', MAT_X, PUPIL_L_Y, "Pupil L Material")
    pupil_l_mat.inputs['Material'].default_value = mats['pupil']

    tree.links.new(iris_l_final_x.outputs[0], pupil_l_pos.inputs['X'])
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

    pupil_r_pos = add_node(tree, 'ShaderNodeCombineXYZ', COMBINE_X, PUPIL_R_Y, "Pupil R Pos")
    pupil_r_pos.inputs['Y'].default_value = -0.78
    pupil_r_pos.inputs['Z'].default_value = 1.25

    pupil_r_xform = add_node(tree, 'GeometryNodeTransform', XFORM_X, PUPIL_R_Y, "Pupil R Transform")

    pupil_r_mat = add_node(tree, 'GeometryNodeSetMaterial', MAT_X, PUPIL_R_Y, "Pupil R Material")
    pupil_r_mat.inputs['Material'].default_value = mats['pupil']

    tree.links.new(iris_r_final_x.outputs[0], pupil_r_pos.inputs['X'])
    tree.links.new(pupil_r_sphere.outputs['Mesh'], pupil_r_xform.inputs['Geometry'])
    tree.links.new(pupil_r_pos.outputs['Vector'], pupil_r_xform.inputs['Translation'])
    tree.links.new(pupil_r_xform.outputs['Geometry'], pupil_r_mat.inputs['Geometry'])

    # ------------------------------------------------------------------
    # MOUTH — driven by jawOpen, mouthSmileRight, mouthFunnel
    # ------------------------------------------------------------------

    mouth_sphere = add_node(tree, 'GeometryNodeMeshUVSphere', PRIM_X, MOUTH_Y, "Mouth Sphere")
    mouth_sphere.inputs['Segments'].default_value = 16
    mouth_sphere.inputs['Rings'].default_value = 8
    mouth_sphere.inputs['Radius'].default_value = 0.15

    # Mouth X scale: base 0.6 * MouthSize, + smile widens, - funnel narrows
    mouth_smile_w = add_node(tree, 'ShaderNodeMath', MATH_X - 400, MOUTH_Y, "Smile Width")
    mouth_smile_w.operation = 'MULTIPLY'
    mouth_smile_w.inputs[1].default_value = 0.5

    mouth_funnel_w = add_node(tree, 'ShaderNodeMath', MATH_X - 400, MOUTH_Y - 70, "Funnel Narrow")
    mouth_funnel_w.operation = 'MULTIPLY'
    mouth_funnel_w.inputs[1].default_value = -0.3

    mouth_w_add = add_node(tree, 'ShaderNodeMath', MATH_X - 200, MOUTH_Y, "Mouth W Sum")
    mouth_w_add.operation = 'ADD'

    mouth_w_base = add_node(tree, 'ShaderNodeMath', MATH_X, MOUTH_Y, "Mouth W Base")
    mouth_w_base.operation = 'ADD'
    mouth_w_base.inputs[0].default_value = 0.6

    mouth_w_size = add_node(tree, 'ShaderNodeMath', MATH_X + 150, MOUTH_Y, "Mouth W Final")
    mouth_w_size.operation = 'MULTIPLY'

    # Mouth Z scale: base 0.2 * MouthSize + jawOpen * 2.5
    mouth_jaw = add_node(tree, 'ShaderNodeMath', MATH_X - 200, MOUTH_Y - 140, "Jaw Scale")
    mouth_jaw.operation = 'MULTIPLY'
    mouth_jaw.inputs[1].default_value = 2.5

    mouth_z_base = add_node(tree, 'ShaderNodeMath', MATH_X, MOUTH_Y - 140, "Mouth Z Base")
    mouth_z_base.operation = 'ADD'
    mouth_z_base.inputs[0].default_value = 0.2

    mouth_z_size = add_node(tree, 'ShaderNodeMath', MATH_X + 150, MOUTH_Y - 140, "Mouth Z Final")
    mouth_z_size.operation = 'MULTIPLY'

    # Mouth Y depth scale with funnel (pucker pushes forward)
    mouth_funnel_y = add_node(tree, 'ShaderNodeMath', MATH_X, MOUTH_Y - 210, "Funnel Depth")
    mouth_funnel_y.operation = 'ADD'
    mouth_funnel_y.inputs[0].default_value = 0.15

    mouth_funnel_y_mul = add_node(tree, 'ShaderNodeMath', MATH_X - 200, MOUTH_Y - 210, "Funnel Y Mul")
    mouth_funnel_y_mul.operation = 'MULTIPLY'
    mouth_funnel_y_mul.inputs[1].default_value = 0.15

    mouth_scale = add_node(tree, 'ShaderNodeCombineXYZ', COMBINE_X, MOUTH_Y, "Mouth Scale")

    # Mouth position (drops slightly when jaw opens)
    mouth_drop = add_node(tree, 'ShaderNodeMath', MATH_X, MOUTH_Y - 280, "Jaw Drop")
    mouth_drop.operation = 'MULTIPLY'
    mouth_drop.inputs[1].default_value = -0.15

    mouth_pos_z = add_node(tree, 'ShaderNodeMath', MATH_X + 150, MOUTH_Y - 280, "Mouth Pos Z")
    mouth_pos_z.operation = 'ADD'
    mouth_pos_z.inputs[0].default_value = 0.5

    mouth_pos = add_node(tree, 'ShaderNodeCombineXYZ', COMBINE_X, MOUTH_Y - 200, "Mouth Pos")
    mouth_pos.inputs['X'].default_value = 0.0
    mouth_pos.inputs['Y'].default_value = -0.7

    mouth_xform = add_node(tree, 'GeometryNodeTransform', XFORM_X, MOUTH_Y, "Mouth Transform")

    mouth_mat = add_node(tree, 'GeometryNodeSetMaterial', MAT_X, MOUTH_Y, "Mouth Material")
    mouth_mat.inputs['Material'].default_value = mats['mouth']

    # Links: mouth
    tree.links.new(group_in2.outputs['mouthSmileRight'], mouth_smile_w.inputs[0])
    tree.links.new(group_in2.outputs['mouthFunnel'], mouth_funnel_w.inputs[0])
    tree.links.new(mouth_smile_w.outputs[0], mouth_w_add.inputs[0])
    tree.links.new(mouth_funnel_w.outputs[0], mouth_w_add.inputs[1])
    tree.links.new(mouth_w_add.outputs[0], mouth_w_base.inputs[1])
    tree.links.new(mouth_w_base.outputs[0], mouth_w_size.inputs[0])
    tree.links.new(group_in2.outputs['Mouth Size'], mouth_w_size.inputs[1])

    tree.links.new(group_in2.outputs['jawOpen'], mouth_jaw.inputs[0])
    tree.links.new(mouth_jaw.outputs[0], mouth_z_base.inputs[1])
    tree.links.new(mouth_z_base.outputs[0], mouth_z_size.inputs[0])
    tree.links.new(group_in2.outputs['Mouth Size'], mouth_z_size.inputs[1])

    tree.links.new(group_in2.outputs['mouthFunnel'], mouth_funnel_y_mul.inputs[0])
    tree.links.new(mouth_funnel_y_mul.outputs[0], mouth_funnel_y.inputs[1])

    tree.links.new(mouth_w_size.outputs[0], mouth_scale.inputs['X'])
    tree.links.new(mouth_funnel_y.outputs[0], mouth_scale.inputs['Y'])
    tree.links.new(mouth_z_size.outputs[0], mouth_scale.inputs['Z'])

    tree.links.new(group_in2.outputs['jawOpen'], mouth_drop.inputs[0])
    tree.links.new(mouth_drop.outputs[0], mouth_pos_z.inputs[1])
    tree.links.new(mouth_pos_z.outputs[0], mouth_pos.inputs['Z'])

    tree.links.new(mouth_sphere.outputs['Mesh'], mouth_xform.inputs['Geometry'])
    tree.links.new(mouth_pos.outputs['Vector'], mouth_xform.inputs['Translation'])
    tree.links.new(mouth_scale.outputs['Vector'], mouth_xform.inputs['Scale'])
    tree.links.new(mouth_xform.outputs['Geometry'], mouth_mat.inputs['Geometry'])

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

    ear_l_xform = add_node(tree, 'GeometryNodeTransform', XFORM_X, EAR_L_Y, "Ear L Transform")
    ear_l_xform.inputs['Translation'].default_value = (-0.85, -0.1, 1.3)

    ear_l_mat = add_node(tree, 'GeometryNodeSetMaterial', MAT_X, EAR_L_Y, "Ear L Material")
    ear_l_mat.inputs['Material'].default_value = mats['ear']

    tree.links.new(group_in2.outputs['Ear Size'], ear_l_scale_x.inputs[1])
    tree.links.new(group_in2.outputs['Ear Size'], ear_l_scale_y.inputs[1])
    tree.links.new(group_in2.outputs['Ear Size'], ear_l_scale_z.inputs[1])
    tree.links.new(ear_l_scale_x.outputs[0], ear_l_scale.inputs['X'])
    tree.links.new(ear_l_scale_y.outputs[0], ear_l_scale.inputs['Y'])
    tree.links.new(ear_l_scale_z.outputs[0], ear_l_scale.inputs['Z'])
    tree.links.new(ear_l_sphere.outputs['Mesh'], ear_l_xform.inputs['Geometry'])
    tree.links.new(ear_l_scale.outputs['Vector'], ear_l_xform.inputs['Scale'])
    tree.links.new(ear_l_xform.outputs['Geometry'], ear_l_mat.inputs['Geometry'])

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

    ear_r_xform = add_node(tree, 'GeometryNodeTransform', XFORM_X, EAR_R_Y, "Ear R Transform")
    ear_r_xform.inputs['Translation'].default_value = (0.85, -0.1, 1.3)

    ear_r_mat = add_node(tree, 'GeometryNodeSetMaterial', MAT_X, EAR_R_Y, "Ear R Material")
    ear_r_mat.inputs['Material'].default_value = mats['ear']

    tree.links.new(group_in2.outputs['Ear Size'], ear_r_scale_x.inputs[1])
    tree.links.new(group_in2.outputs['Ear Size'], ear_r_scale_y.inputs[1])
    tree.links.new(group_in2.outputs['Ear Size'], ear_r_scale_z.inputs[1])
    tree.links.new(ear_r_scale_x.outputs[0], ear_r_scale.inputs['X'])
    tree.links.new(ear_r_scale_y.outputs[0], ear_r_scale.inputs['Y'])
    tree.links.new(ear_r_scale_z.outputs[0], ear_r_scale.inputs['Z'])
    tree.links.new(ear_r_sphere.outputs['Mesh'], ear_r_xform.inputs['Geometry'])
    tree.links.new(ear_r_scale.outputs['Vector'], ear_r_xform.inputs['Scale'])
    tree.links.new(ear_r_xform.outputs['Geometry'], ear_r_mat.inputs['Geometry'])

    # ------------------------------------------------------------------
    # JOIN GEOMETRY — combine all parts
    # ------------------------------------------------------------------

    join = add_node(tree, 'GeometryNodeJoinGeometry', JOIN_X, -400, "Join All Parts")

    # Connect all parts to join (order = draw order, bottom connects first)
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
