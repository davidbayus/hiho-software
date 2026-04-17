# SPDX-License-Identifier: GPL-3.0-or-later
"""The Minkowski capsule — PPParty's one novel primitive.

Every body part (chest, hand, foot, shoulder, cheek, etc.) is built
from this capsule. Width=0 → sphere. Width>0 → pill shape along the
chosen axis.

The math is a Minkowski sum: imagine sweeping a sphere across the
surface of a box — the shape you trace out is our capsule. We build
this inside a reusable node group (PP_DynCapsule) so it can be
instantiated dozens of times in the marionette tree without
duplicating nodes.

Public entry point:
    add_dynamic_capsule(tree, x, y, label, radius, subdivs,
                        width_output, ext_factor, axis)

Internal:
    _ensure_capsule_group() — builds or retrieves PP_DynCapsule
"""

import bpy

from ._common import add_node, _frame_section


def add_dynamic_capsule(tree, x, y, label, radius=0.5, subdivs=6,
                        width_output=None, ext_factor=0.3, axis='Z'):
    """Add a dynamic Minkowski capsule via the PP_DynCapsule node group.

    Width=0 → sphere. Width>0 → pill shape along the specified axis.
    Returns the group node (geometry output = capsule mesh).
    """
    _axis_map = {'X': (1, 0, 0), 'Y': (0, 1, 0), 'Z': (0, 0, 1)}
    capsule_tree = _ensure_capsule_group()
    grp = add_node(tree, 'GeometryNodeGroup', x, y, label)
    grp.node_tree = capsule_tree
    grp.inputs['Radius'].default_value = radius
    grp.inputs['Ext Factor'].default_value = ext_factor
    grp.inputs['Subdivisions'].default_value = subdivs
    grp.inputs['Axis Mask'].default_value = _axis_map.get(axis, (0, 0, 1))
    if width_output is not None:
        tree.links.new(width_output, grp.inputs['Width'])
    return grp


def _ensure_capsule_group():
    """Create or retrieve the PP_DynCapsule node group.

    Minkowski capsule: cube → clamp to inner box → offset → normalize
    × radius → add back. Width=0 → sphere, Width>0 → pill shape.
    Replaces ~15 inline nodes per body part.
    """
    existing = bpy.data.node_groups.get("PP_DynCapsule")
    if existing:
        return existing

    g = bpy.data.node_groups.new("PP_DynCapsule", 'GeometryNodeTree')
    g.interface.clear()

    s = g.interface.new_socket(
        "Width", in_out='INPUT', socket_type='NodeSocketFloat')
    s.default_value = 0.0
    s.min_value = 0.0
    s.max_value = 5.0
    s = g.interface.new_socket(
        "Ext Factor", in_out='INPUT', socket_type='NodeSocketFloat')
    s.default_value = 0.3
    s = g.interface.new_socket(
        "Radius", in_out='INPUT', socket_type='NodeSocketFloat')
    s.default_value = 0.5
    s = g.interface.new_socket(
        "Subdivisions", in_out='INPUT', socket_type='NodeSocketInt')
    s.default_value = 6
    s.min_value = 2
    s.max_value = 12
    s = g.interface.new_socket(
        "Axis Mask", in_out='INPUT', socket_type='NodeSocketVector')
    s.default_value = (0.0, 0.0, 1.0)
    g.interface.new_socket(
        "Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry')

    dx = 200
    gin = add_node(g, 'NodeGroupInput', 0, 0, "In")

    # --- Extension sizing ---
    diam_n = add_node(g, 'ShaderNodeMath', dx, 0, "Diam")
    diam_n.operation = 'MULTIPLY'
    g.links.new(gin.outputs['Radius'], diam_n.inputs[0])
    diam_n.inputs[1].default_value = 2.0

    ext_n = add_node(g, 'ShaderNodeMath', dx, -120, "Ext")
    ext_n.operation = 'MULTIPLY'
    g.links.new(gin.outputs['Width'], ext_n.inputs[0])
    g.links.new(gin.outputs['Ext Factor'], ext_n.inputs[1])

    ext_x2 = add_node(g, 'ShaderNodeMath', dx * 2, -120, "Ext*2")
    ext_x2.operation = 'MULTIPLY'
    g.links.new(ext_n.outputs[0], ext_x2.inputs[0])
    ext_x2.inputs[1].default_value = 2.0

    ext_vec = add_node(g, 'ShaderNodeVectorMath', dx * 3, -120, "ExtVec")
    ext_vec.operation = 'SCALE'
    g.links.new(gin.outputs['Axis Mask'], ext_vec.inputs[0])
    g.links.new(ext_x2.outputs[0], ext_vec.inputs['Scale'])

    base_sz = add_node(g, 'ShaderNodeCombineXYZ', dx * 3, 0, "BaseSz")
    g.links.new(diam_n.outputs[0], base_sz.inputs['X'])
    g.links.new(diam_n.outputs[0], base_sz.inputs['Y'])
    g.links.new(diam_n.outputs[0], base_sz.inputs['Z'])

    cube_sz = add_node(g, 'ShaderNodeVectorMath', dx * 4, 0, "CubeSz")
    cube_sz.operation = 'ADD'
    g.links.new(base_sz.outputs['Vector'], cube_sz.inputs[0])
    g.links.new(ext_vec.outputs['Vector'], cube_sz.inputs[1])

    _frame_section(g,
        "EXTENSION — Width slider stretches the cube along one axis"
        " to create the pill midsection",
        'strings', [diam_n, ext_n, ext_x2, ext_vec, base_sz, cube_sz])

    # --- Subdivided cube mesh ---
    cube = add_node(g, 'GeometryNodeMeshCube', dx * 5, 0, "Cube")
    g.links.new(cube_sz.outputs['Vector'], cube.inputs['Size'])
    g.links.new(gin.outputs['Subdivisions'], cube.inputs['Vertices X'])
    g.links.new(gin.outputs['Subdivisions'], cube.inputs['Vertices Y'])
    g.links.new(gin.outputs['Subdivisions'], cube.inputs['Vertices Z'])

    # --- Minkowski clamp + sphere projection ---
    pos_in = add_node(g, 'GeometryNodeInputPosition', dx * 5, -120, "Pos")

    cl_hi_v = add_node(g, 'ShaderNodeVectorMath', dx * 4, -220, "+Ext")
    cl_hi_v.operation = 'SCALE'
    g.links.new(gin.outputs['Axis Mask'], cl_hi_v.inputs[0])
    g.links.new(ext_n.outputs[0], cl_hi_v.inputs['Scale'])

    cl_lo_v = add_node(g, 'ShaderNodeVectorMath', dx * 4, -320, "-Ext")
    cl_lo_v.operation = 'SCALE'
    g.links.new(cl_hi_v.outputs['Vector'], cl_lo_v.inputs[0])
    cl_lo_v.inputs['Scale'].default_value = -1.0

    cl_hi = add_node(g, 'ShaderNodeVectorMath', dx * 6, -120, "ClHi")
    cl_hi.operation = 'MINIMUM'
    g.links.new(pos_in.outputs['Position'], cl_hi.inputs[0])
    g.links.new(cl_hi_v.outputs['Vector'], cl_hi.inputs[1])

    cl_lo = add_node(g, 'ShaderNodeVectorMath', dx * 7, -120, "ClLo")
    cl_lo.operation = 'MAXIMUM'
    g.links.new(cl_hi.outputs['Vector'], cl_lo.inputs[0])
    g.links.new(cl_lo_v.outputs['Vector'], cl_lo.inputs[1])

    offs = add_node(g, 'ShaderNodeVectorMath', dx * 8, -120, "Offs")
    offs.operation = 'SUBTRACT'
    g.links.new(pos_in.outputs['Position'], offs.inputs[0])
    g.links.new(cl_lo.outputs['Vector'], offs.inputs[1])

    nrm = add_node(g, 'ShaderNodeVectorMath', dx * 9, -120, "Norm")
    nrm.operation = 'NORMALIZE'
    g.links.new(offs.outputs['Vector'], nrm.inputs[0])

    cap = add_node(g, 'ShaderNodeVectorMath', dx * 10, -120, "xR")
    cap.operation = 'SCALE'
    g.links.new(nrm.outputs['Vector'], cap.inputs[0])
    g.links.new(gin.outputs['Radius'], cap.inputs['Scale'])

    final = add_node(g, 'ShaderNodeVectorMath', dx * 11, -120, "Final")
    final.operation = 'ADD'
    g.links.new(cl_lo.outputs['Vector'], final.inputs[0])
    g.links.new(cap.outputs['Vector'], final.inputs[1])

    _frame_section(g,
        "MINKOWSKI SUM — Clamp each vertex to the inner box, then"
        " project outward onto a sphere of the given radius",
        'body', [pos_in, cl_hi_v, cl_lo_v, cl_hi, cl_lo,
                 offs, nrm, cap, final])

    # --- Output ---
    set_pos = add_node(g, 'GeometryNodeSetPosition', dx * 12, 0, "SetPos")
    g.links.new(cube.outputs['Mesh'], set_pos.inputs['Geometry'])
    g.links.new(final.outputs['Vector'], set_pos.inputs['Position'])

    gout = add_node(g, 'NodeGroupOutput', dx * 13, 0, "Out")
    g.links.new(set_pos.outputs['Geometry'], gout.inputs['Geometry'])

    return g
