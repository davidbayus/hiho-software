# SPDX-License-Identifier: GPL-3.0-or-later
"""The Minkowski capsule — PPParty's one novel primitive.

=============================================================================
The big idea
=============================================================================
Every body part of the puppet — chest, hand, foot, shoulder, cheek, ear,
eye, eyebrow — is a "capsule." A capsule is the shape you get if you take
a cylinder and cap each end with a hemisphere, like a pill or a Tic Tac.

We don't model eight different capsule meshes. We build ONE procedural
capsule whose shape is controlled by sliders: a Width slider, a Radius
slider, and an axis direction. When Width is 0, the capsule collapses to
a sphere. When Width is positive, the capsule stretches into a pill along
the chosen axis. One primitive, many body parts.

=============================================================================
Why it's a "Minkowski" capsule
=============================================================================
Imagine sweeping a sphere across the surface of a box. Everywhere the
sphere travels, it carves out a rounded envelope — the flat sides of the
box become flat faces, the edges become rounded cylinders, the corners
become rounded hemispheres. That envelope is called a Minkowski sum of a
box and a sphere. If you let the box shrink to a single point, the
envelope becomes a plain sphere. If the box is longer on one axis, you
get a pill.

Our code doesn't literally sweep anything. It does the algebraic
equivalent: for every vertex of a subdivided cube, it pushes the vertex
outward from an "inner skeleton" by exactly one radius. Vertices beside
the skeleton form the cylindrical midsection; vertices past the ends
form the hemispherical caps. Mathematically identical to the sphere
sweep, computationally cheap, and every body part gets it for free.

=============================================================================
Why a "node group" instead of inline nodes
=============================================================================
A node group in Blender is like a function in Python — a reusable
sub-tree you can drop into a bigger tree. Before this refactor, every
body part stamped out ~15 nodes of Minkowski math inline. With 8 dynamic
capsules in the puppet, that's ~120 redundant nodes, and every one of
them re-evaluates every time the puppet updates.

Now we build the Minkowski math ONCE inside a node group called
PP_DynCapsule. Every body part calls that group with its own Radius,
Width, and Axis Mask. Blender only evaluates the math once per call
instead of rebuilding it from scratch — and if we ever want to change
the capsule algorithm, there is exactly one place to edit.

Public entry point:
    add_dynamic_capsule(tree, x, y, label, radius, subdivs,
                        width_output, ext_factor, axis)

Internal:
    _ensure_capsule_group() — build PP_DynCapsule if it doesn't exist,
                              otherwise hand back the existing one
"""

import bpy

from ._common import add_node, _frame_section


def add_dynamic_capsule(tree, x, y, label, radius=0.5, subdivs=6,
                        width_output=None, ext_factor=0.3, axis='Z'):
    """Drop a dynamic Minkowski capsule into `tree` at position (x, y).

    Width=0 gives a sphere. Width>0 gives a pill along `axis`.

    `width_output` is the Float socket of whatever slider or math node
    you want this capsule's Width to follow — often an N-panel slider
    like "Eye Width." If `width_output` is None, the capsule stays at
    default Width=0 (just a sphere).

    `ext_factor` is the per-part conversion ratio from Width-slider
    units to world-space extension. Eyes want less extension per slider
    tick than hands do, because eyes are smaller. Tuning this keeps
    different-sized body parts responding "the same way" to a shared
    Width slider.

    Returns the group node; its Geometry output is the capsule mesh.
    """
    # Axis letters map to unit vectors. A unit vector is just an arrow
    # of length 1 pointing along one axis — "turn ON this one
    # direction, leave the other two OFF."
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
    """Build the PP_DynCapsule node group, or hand back the existing one.

    The word "cache" comes up a lot in CS. Caching just means: if you
    have already done expensive work once, remember the result so you
    don't redo it. We check `bpy.data.node_groups` first — if
    PP_DynCapsule is already sitting in the blend file, we hand it
    back unchanged. Only the first call actually constructs the tree.
    """
    existing = bpy.data.node_groups.get("PP_DynCapsule")
    if existing:
        return existing

    g = bpy.data.node_groups.new("PP_DynCapsule", 'GeometryNodeTree')
    g.interface.clear()

    # -----------------------------------------------------------------
    # INTERFACE — the inputs and outputs of this node group.
    # -----------------------------------------------------------------
    # Think of these like the handles on the outside of the group:
    # sliders and sockets you plug things into from the parent tree.
    # Every socket needs a type (Float, Int, Vector, Geometry…) and
    # usually a default value and range.

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

    # -----------------------------------------------------------------
    # LAYOUT CONSTANT — node columns are 200 units apart on screen.
    # Purely visual, so the math chain reads left-to-right cleanly.
    # -----------------------------------------------------------------
    dx = 200
    gin = add_node(g, 'NodeGroupInput', 0, 0, "In")

    # -----------------------------------------------------------------
    # EXTENSION SIZING
    # -----------------------------------------------------------------
    # We are computing the size of the CUBE that the Minkowski math
    # will operate on. Base size is the diameter (= 2 × Radius) in
    # every direction. Then the Axis Mask adds extra length on exactly
    # one axis, to form the pill midsection.
    #
    # In words:
    #     cube_size = (2R, 2R, 2R) + 2 × axis_mask × Width × ExtFactor
    #
    # When Width is 0, the second term vanishes and we get a cube of
    # side 2R, which becomes a plain sphere of radius R after the
    # Minkowski clamp below.

    diam_n = add_node(g, 'ShaderNodeMath', dx, 0, "Diam")
    diam_n.operation = 'MULTIPLY'
    g.links.new(gin.outputs['Radius'], diam_n.inputs[0])
    diam_n.inputs[1].default_value = 2.0           # diameter = 2 × radius

    ext_n = add_node(g, 'ShaderNodeMath', dx, -120, "Ext")
    ext_n.operation = 'MULTIPLY'
    g.links.new(gin.outputs['Width'], ext_n.inputs[0])
    g.links.new(gin.outputs['Ext Factor'], ext_n.inputs[1])
    # ext_n now holds a world-space HALF extent along the chosen axis.

    ext_x2 = add_node(g, 'ShaderNodeMath', dx * 2, -120, "Ext*2")
    ext_x2.operation = 'MULTIPLY'
    g.links.new(ext_n.outputs[0], ext_x2.inputs[0])
    ext_x2.inputs[1].default_value = 2.0           # full extent = 2 × half

    # Multiply axis mask × full extent → a 3D vector that's nonzero only
    # on the stretched axis. On a Z-axis capsule this is (0, 0, extent).
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

    # -----------------------------------------------------------------
    # SUBDIVIDED CUBE MESH
    # -----------------------------------------------------------------
    # Blender's Mesh Cube primitive takes a 3D size AND a subdivision
    # count on each axis. More subdivisions means more vertices, which
    # means a smoother capsule after we project — at the cost of more
    # math per frame. 6 is a reasonable default for most body parts;
    # tiny parts like shoulders use 3 or 4 to save cycles.

    cube = add_node(g, 'GeometryNodeMeshCube', dx * 5, 0, "Cube")
    g.links.new(cube_sz.outputs['Vector'], cube.inputs['Size'])
    g.links.new(gin.outputs['Subdivisions'], cube.inputs['Vertices X'])
    g.links.new(gin.outputs['Subdivisions'], cube.inputs['Vertices Y'])
    g.links.new(gin.outputs['Subdivisions'], cube.inputs['Vertices Z'])

    # -----------------------------------------------------------------
    # MINKOWSKI CLAMP + SPHERE PROJECTION
    # -----------------------------------------------------------------
    # Imagine a "skeleton" inside the final capsule: just a single
    # point when Width=0, or a short line segment along the active
    # axis when Width>0. The outer surface of the capsule is defined
    # as: "every 3D point that sits exactly Radius away from the
    # nearest point on the skeleton."
    #
    # To turn the cube's vertices into that surface, we do this to
    # every vertex:
    #     1. CLAMP the vertex position into the skeleton's bounding
    #        box. That gives the nearest point ON the skeleton.
    #     2. SUBTRACT to get the offset vector from skeleton to vertex.
    #     3. NORMALIZE the offset so its length becomes 1 — we now
    #        have a pure direction pointing outward.
    #     4. SCALE that direction by Radius.
    #     5. ADD it back to the clamped point. That's the final
    #        vertex position on the capsule surface.
    #
    # When the skeleton is a point (Width=0), every vertex lands on a
    # sphere of radius R. When it's a line segment (Width>0), vertices
    # beside the segment form a cylinder of radius R; vertices past
    # the ends form the two hemispherical caps. Together: a pill.

    pos_in = add_node(g, 'GeometryNodeInputPosition', dx * 5, -120, "Pos")

    # Build the +Ext / −Ext endpoints of the inner skeleton. `ext_n`
    # is the half extent along one axis (zero on the others).
    cl_hi_v = add_node(g, 'ShaderNodeVectorMath', dx * 4, -220, "+Ext")
    cl_hi_v.operation = 'SCALE'
    g.links.new(gin.outputs['Axis Mask'], cl_hi_v.inputs[0])
    g.links.new(ext_n.outputs[0], cl_hi_v.inputs['Scale'])

    cl_lo_v = add_node(g, 'ShaderNodeVectorMath', dx * 4, -320, "-Ext")
    cl_lo_v.operation = 'SCALE'
    g.links.new(cl_hi_v.outputs['Vector'], cl_lo_v.inputs[0])
    cl_lo_v.inputs['Scale'].default_value = -1.0

    # Clamp = MIN(position, +Ext) then MAX(…, −Ext). Per-component, so
    # each X/Y/Z coordinate is clamped independently. The result is
    # the nearest point on the skeleton for this vertex.
    cl_hi = add_node(g, 'ShaderNodeVectorMath', dx * 6, -120, "ClHi")
    cl_hi.operation = 'MINIMUM'
    g.links.new(pos_in.outputs['Position'], cl_hi.inputs[0])
    g.links.new(cl_hi_v.outputs['Vector'], cl_hi.inputs[1])

    cl_lo = add_node(g, 'ShaderNodeVectorMath', dx * 7, -120, "ClLo")
    cl_lo.operation = 'MAXIMUM'
    g.links.new(cl_hi.outputs['Vector'], cl_lo.inputs[0])
    g.links.new(cl_lo_v.outputs['Vector'], cl_lo.inputs[1])

    # Direction outward from the skeleton to the original vertex.
    offs = add_node(g, 'ShaderNodeVectorMath', dx * 8, -120, "Offs")
    offs.operation = 'SUBTRACT'
    g.links.new(pos_in.outputs['Position'], offs.inputs[0])
    g.links.new(cl_lo.outputs['Vector'], offs.inputs[1])

    # Normalize → unit-length direction. Multiply by Radius → a vector
    # of exactly Radius length pointing outward.
    nrm = add_node(g, 'ShaderNodeVectorMath', dx * 9, -120, "Norm")
    nrm.operation = 'NORMALIZE'
    g.links.new(offs.outputs['Vector'], nrm.inputs[0])

    cap = add_node(g, 'ShaderNodeVectorMath', dx * 10, -120, "xR")
    cap.operation = 'SCALE'
    g.links.new(nrm.outputs['Vector'], cap.inputs[0])
    g.links.new(gin.outputs['Radius'], cap.inputs['Scale'])

    # Final position = skeleton point + outward cap vector.
    final = add_node(g, 'ShaderNodeVectorMath', dx * 11, -120, "Final")
    final.operation = 'ADD'
    g.links.new(cl_lo.outputs['Vector'], final.inputs[0])
    g.links.new(cap.outputs['Vector'], final.inputs[1])

    _frame_section(g,
        "MINKOWSKI SUM — Clamp each vertex to the inner box, then"
        " project outward onto a sphere of the given radius",
        'body', [pos_in, cl_hi_v, cl_lo_v, cl_hi, cl_lo,
                 offs, nrm, cap, final])

    # -----------------------------------------------------------------
    # OUTPUT — Set Position on the cube mesh, then hand it back.
    # -----------------------------------------------------------------
    # Set Position takes a geometry and a per-vertex vector field, and
    # moves every vertex to its corresponding field value. Here the
    # field is "the Minkowski-projected position we just computed."

    set_pos = add_node(g, 'GeometryNodeSetPosition', dx * 12, 0, "SetPos")
    g.links.new(cube.outputs['Mesh'], set_pos.inputs['Geometry'])
    g.links.new(final.outputs['Vector'], set_pos.inputs['Position'])

    gout = add_node(g, 'NodeGroupOutput', dx * 13, 0, "Out")
    g.links.new(set_pos.outputs['Geometry'], gout.inputs['Geometry'])

    return g
