"""Make It Yours — expose puppet customization sliders in the N-panel.

This doesn't use an operator with an F9 redo panel. Instead, the panel
draws sliders that directly modify the geometry nodes modifier inputs
on the active puppet. Changes are instant and visible in the viewport.

The customization inputs are whatever the template author put in the
"Customize" panel of their geonode tree — body width, eye size, colors, etc.
"""

import bpy


def draw_customize_sliders(layout, context):
    """Draw customization sliders for the active puppet template.

    Called from the main Green Room panel. Reads the customize inputs
    from the active template info and draws a prop for each one
    directly on the modifier.

    Args:
        layout: The panel layout to draw into
        context: Blender context
    """
    import green_room

    info = getattr(green_room, 'active_template_info', None)
    if not info or not info.customize_inputs:
        return

    puppet = bpy.data.objects.get(info.puppet_object)
    if not puppet:
        return

    mod = puppet.modifiers.get(info.modifier_name)
    if not mod:
        return

    box = layout.box()
    box.label(text="Make It Yours", icon='BRUSH_DATA')
    col = box.column(align=True)

    for name, sock_info in info.customize_inputs.items():
        # Skip non-geometry socket (the output)
        if sock_info.socket_type == 'NodeSocketGeometry':
            continue

        # Draw a slider for this input directly on the modifier
        try:
            col.prop(mod, f'["{sock_info.identifier}"]', text=name)
        except TypeError:
            # Socket type not drawable (e.g. geometry) — skip silently
            pass
