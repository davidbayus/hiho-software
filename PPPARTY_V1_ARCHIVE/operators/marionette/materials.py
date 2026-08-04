# SPDX-License-Identifier: GPL-3.0-or-later
"""Materials — the simplest passthrough pattern in PPParty.

=============================================================================
What "material" means here
=============================================================================
Every surface you see in a Blender render is painted by a material. In
PPParty every body part gets one solid-color material — the puppet looks
flat and graphic on purpose, like a Muppet or a Saturday-morning cartoon.
No texture maps, no painting, no UV unwrapping needed. A material here is
just a Principled BSDF shader with a Base Color and a Roughness.

=============================================================================
Why this file is a good place to start reading
=============================================================================
Every Group Input socket in the geonode tree is a "door" you can pass a
value through from the outside. Some sockets take a float (a slider), some
take a color, some take a vector. One kind of socket takes a Material.

Material sockets are the easiest example of that passthrough pattern:
    1. The body-parts code declares a Material socket named "Head Material."
    2. The operator creates a material object in Python.
    3. The operator writes the material into that socket once, at build time.
    4. Inside the node tree, a "Set Material" node reads the socket and
       paints the mesh.

That's the whole trick. Once you understand how this works for materials,
the same pattern applies to floats (sliders like "Body Width"), colors,
vectors, and even whole meshes (what Studio Track uses for Object Info
overrides). Materials first, because there's no math in the way.

=============================================================================
Public entry points
=============================================================================
    make_material(name, color)
        Build a single solid-color material. Reusable helper.

    create_body_materials()
        Returns a dict of the six body-part materials
        (body, hand, foot, joint, limb, cheek).

    create_blob_head_materials()
        Returns a dict of the nine blob-head materials
        (body, mouth, eye_white, iris, pupil, ear, brow, lip, nose).

Both dicts use short keys ('body', 'mouth', …) because the operator that
consumes them reads those keys into GN sockets by matching names. Keeping
the keys short keeps the assignment loop in the operator easy to read.
"""

import bpy


# ===========================================================================
# THE HELPER — one material, one call
# ===========================================================================
# Every material in PPParty is a solid color with a slightly-soft surface.
# Rather than copy-paste the same three lines nine times in
# create_blob_head_materials() and six times in create_body_materials(),
# we wrap that recipe in a small function. DRY ("don't repeat yourself")
# is the CS term — if you ever want to change the default roughness or
# add a shader effect, there is exactly ONE place to edit.

def make_material(name, color):
    """Create a simple solid-color Principled BSDF material.

    `color` is an RGBA tuple — four floats in the 0–1 range. The alpha
    channel is always 1.0 for PPParty (fully opaque); we keep it in the
    tuple so Blender's color picker can read the value directly.

    Roughness 0.8 gives the puppet a matte, felt-like surface. Fully
    smooth (0.0) looks plasticky; fully rough (1.0) looks chalky. 0.8
    splits the difference and reads well under the classroom-default
    lighting in EEVEE.
    """
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = 0.8
    return mat


# ===========================================================================
# BODY PART MATERIALS — the marionette (everything below the neck)
# ===========================================================================
# Six materials, six body-part categories. Each N-panel "Material" picker
# in the "Materials" section points at one of these. Students can swap
# any of them for a custom material they build in the Shader editor —
# these are just the defaults the addon ships with.

def create_body_materials():
    """Create materials for the marionette body parts."""
    return {
        'body':  make_material("PP_Body",  (0.85, 0.55, 0.35, 1.0)),
        'hand':  make_material("PP_Hand",  (0.95, 0.75, 0.55, 1.0)),
        'foot':  make_material("PP_Foot",  (0.6,  0.4,  0.25, 1.0)),
        'joint': make_material("PP_Joint", (0.5,  0.5,  0.5,  1.0)),
        'limb':  make_material("PP_Limb",  (0.25, 0.25, 0.25, 1.0)),
        'cheek': make_material("PP_Cheek", (1.0,  0.6,  0.55, 1.0)),
    }


# ===========================================================================
# BLOB HEAD MATERIALS — the face (absorbed from retired Green Room addon)
# ===========================================================================
# These color defaults came over unchanged from Green Room V0.7.0 so that
# blob heads built in the old addon still look right when loaded into
# PPParty. Students who want a monster, an animal, or a robot face just
# reassign these in the N-panel — the socket names stay the same, only
# the material linked into them changes.

def create_blob_head_materials():
    """Create materials for the blob head (matches Green Room defaults)."""
    return {
        'body':      make_material("PP_HeadSkin", (1.0,  0.78, 0.65, 1.0)),
        'mouth':     make_material("PP_Mouth",    (0.25, 0.12, 0.08, 1.0)),
        'eye_white': make_material("PP_EyeWhite", (1.0,  1.0,  1.0,  1.0)),
        'iris':      make_material("PP_Iris",     (0.2,  0.65, 0.7,  1.0)),
        'pupil':     make_material("PP_Pupil",    (0.05, 0.05, 0.05, 1.0)),
        'ear':       make_material("PP_Ear",      (1.0,  0.7,  0.55, 1.0)),
        'brow':      make_material("PP_Brow",     (0.18, 0.09, 0.05, 1.0)),
        'lip':       make_material("PP_Lip",      (0.85, 0.45, 0.45, 1.0)),
        'nose':      make_material("PP_Nose",     (1.0,  0.72, 0.58, 1.0)),
    }
