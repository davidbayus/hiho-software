"""Pick Your Puppet — browse and load puppet templates."""

import bpy
from bpy.props import EnumProperty

from ..core.template_loader import discover_templates, load_template, unload_template


def _get_template_items(self, context):
    """Build the enum list of available puppet templates."""
    templates = discover_templates()
    if not templates:
        return [('NONE', "No templates found", "")]

    items = []
    for i, t in enumerate(templates):
        items.append((t['path'], t['name'], f"Load {t['name']}", i))
    return items


class GREENROOM_OT_pick_puppet(bpy.types.Operator):
    """Pick a puppet character to perform with"""

    bl_idname = "greenroom.pick_puppet"
    bl_label = "Pick Your Puppet"
    bl_options = {'REGISTER', 'UNDO'}

    template: EnumProperty(
        name="Puppet",
        description="Choose a puppet template",
        items=_get_template_items,
    )

    def execute(self, context):
        if self.template == 'NONE':
            self.report({'WARNING'}, "No templates available")
            return {'CANCELLED'}

        # Unload current template if one is loaded
        settings = context.scene.greenroom
        if settings.gr_active_template:
            from .. import active_template_info
            if active_template_info:
                unload_template(active_template_info)

        # Load the selected template
        info = load_template(self.template)

        if not info.is_valid:
            self.report({'ERROR'}, f"Template problem: {info.errors[0]}")
            return {'CANCELLED'}

        # Store in addon state
        import green_room
        green_room.active_template_info = info
        settings.gr_active_template = info.puppet_object
        settings.gr_active_template_path = self.template

        # Report warnings
        for w in info.warnings:
            self.report({'WARNING'}, w)

        self.report({'INFO'}, f"Loaded {info.puppet_object}!")

        # Force viewport redraw
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()

        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=300)

    def draw(self, context):
        self.layout.prop(self, "template", text="")
