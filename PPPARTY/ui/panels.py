# SPDX-License-Identifier: GPL-3.0-or-later
"""PPParty N-panel — marionette controls, connection, physics sliders.

V0.9.4: Material slots — full Blender material assignment for all body
        parts and head parts (replaces color pickers).
V0.9.0: Head Design — blob head customization sliders (eyes, mouth, nose,
        ears, eyebrows, lips) passed through from Green Room blob template.
V0.8.0: Added Make It Yours customization (Body Width, sizes, colors).
V0.5.0: Added Step Strength, Gesture Strength sliders.
Physics, body movement, and joint constraint sliders read from GN modifier.
"""

import bpy


class PPPARTY_PT_main_panel(bpy.types.Panel):
    """PPParty control panel in the 3D Viewport sidebar."""

    bl_label = "PPParty"
    bl_idname = "PPPARTY_PT_main_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "PPPARTY"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.ppparty

        # --- Create button ---
        layout.operator("ppparty.create_marionette",
                        icon='OUTLINER_OB_ARMATURE')

        puppet_name = settings.pp_active_puppet
        puppet = bpy.data.objects.get(puppet_name) if puppet_name else None

        if not puppet:
            layout.label(text="No marionette in scene.", icon='INFO')
            return

        mod = puppet.modifiers.get("PPParty_Physics")
        if not mod or not mod.node_group:
            return

        # --- Body Movement sliders ---
        layout.separator()
        box = layout.box()
        box.label(text="Body Movement", icon='CON_ROTLIKE')
        col = box.column(align=True)
        _draw_slider_group(col, mod, ["Lean Strength", "Extend Strength",
                                        "Lift Strength", "Step Strength",
                                        "Gesture Strength", "Momentum"])

        # --- Body Tracking blend ---
        layout.separator()
        box_bt = layout.box()
        box_bt.label(text="Body Tracking", icon='OUTLINER_OB_ARMATURE')
        col_bt = box_bt.column(align=True)
        _draw_slider_group(col_bt, mod, ["Body Tracking"])
        col_bt.scale_y = 0.8
        from .. import receiver
        if receiver.is_receiving and receiver.body_landmarks:
            col_bt.label(text="Body landmarks active",
                         icon='CHECKMARK')
        else:
            col_bt.label(text="0 = face heuristics, 1 = body tracking")
            col_bt.label(text="Auto-set to 1 when body detected")

        # --- Physics sliders ---
        layout.separator()
        box2 = layout.box()
        box2.label(text="Physics", icon='PHYSICS')
        col2 = box2.column(align=True)
        _draw_slider_group(col2, mod, ["Gravity", "Damping",
                                        "Ground Height",
                                        "Ground Friction",
                                        "Shoulder Float"])

        box3 = layout.box()
        box3.label(text="Proportions", icon='CON_SIZELIMIT')
        col3 = box3.column(align=True)
        _draw_slider_group(col3, mod, ["Arm Length", "Leg Length",
                                        "Upper Arm Ratio",
                                        "Upper Leg Ratio"])

        # --- Make It Yours (customization) ---
        layout.separator()
        box4 = layout.box()
        box4.label(text="Make It Yours", icon='BRUSH_DATA')
        col4 = box4.column(align=True)
        _draw_slider_group(col4, mod, ["Body Width"])
        col4.separator()
        col4.label(text="Hands:")
        _draw_slider_group(col4, mod, ["Hand Size", "Hand Width",
                                        "Hand Rotation", "Hand Tilt"])
        col4.separator()
        col4.label(text="Feet:")
        _draw_slider_group(col4, mod, ["Foot Size", "Foot Width",
                                        "Foot Depth", "Foot Rotation"])
        col4.separator()
        col4.label(text="Shoulders:")
        _draw_slider_group(col4, mod, ["Shoulder Width",
                                        "Shoulder Rotation"])
        col4.separator()
        col4.label(text="Cheeks:")
        _draw_slider_group(col4, mod, ["Cheek Size"])

        # --- Materials (body part material slots) ---
        layout.separator()
        box_c = layout.box()
        box_c.label(text="Materials", icon='MATERIAL')
        col_c = box_c.column(align=True)
        col_c.label(text="Body:")
        _draw_material_slots(col_c, mod, [
            "Body Part Material", "Hand Material", "Foot Material",
            "Joint Material", "Limb Material", "Cheek Material",
        ])
        col_c.separator()
        col_c.label(text="Head:")
        _draw_material_slots(col_c, mod, [
            "Head Material", "Eye Material", "Iris Material",
            "Pupil Material", "Mouth Material", "Lip Material",
            "Nose Material", "Ear Material", "Eyebrow Material",
        ])

        # --- Head Design (blob head customization passthrough) ---
        layout.separator()
        box5 = layout.box()
        box5.label(text="Head Design", icon='SCULPTMODE_HLT')

        col5 = box5.column(align=True)
        col5.label(text="Shape:")
        _draw_slider_group(col5, mod, ["Head Width", "Head Height",
                                        "Head Tilt"])
        col5.separator()
        col5.label(text="Eyes:")
        _draw_slider_group(col5, mod, ["Eye Size", "Eye Spacing",
                                        "Eyes Height", "Eyes Depth",
                                        "Eye Width", "Eye Rotation"])
        col5.separator()
        col5.label(text="Mouth:")
        _draw_slider_group(col5, mod, ["Mouth Size", "Mouth Height",
                                        "Mouth Depth"])
        col5.separator()
        col5.label(text="Nose:")
        _draw_slider_group(col5, mod, ["Nose Size", "Nose Height",
                                        "Nose Depth", "Nose Width",
                                        "Nose Rotation"])
        col5.separator()
        col5.label(text="Ears:")
        _draw_slider_group(col5, mod, ["Ear Size", "Ears Height",
                                        "Ears Spread", "Ears Depth",
                                        "Ear Width", "Ear Rotation"])
        col5.separator()
        col5.label(text="Eyebrows:")
        _draw_slider_group(col5, mod, ["Eyebrow Size", "Eyebrow Height",
                                        "Eyebrow Depth", "Eyebrow Spread",
                                        "Eyebrow Width",
                                        "Eyebrow Rotation"])
        col5.separator()
        col5.label(text="Lips:")
        _draw_slider_group(col5, mod, ["Lip Thickness"])

        # --- Studio Track (custom body parts) ---
        layout.separator()
        box6 = layout.box()
        box6.label(text="Studio Track", icon='SCULPTMODE_HLT')
        col6 = box6.column(align=True)
        col6.scale_y = 0.8
        col6.label(text="Drag custom meshes here:")
        _draw_object_slots(col6, mod, [
            "Custom Torso", "Custom Hand", "Custom Foot",
        ])

        # --- Reset ---
        layout.separator()
        layout.operator("ppparty.reset_physics", icon='FILE_REFRESH')


class PPPARTY_PT_connect_panel(bpy.types.Panel):
    """Tracking connection panel — webcam or phone."""

    bl_label = "Connect"
    bl_idname = "PPPARTY_PT_connect_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "PPPARTY"
    bl_order = 1

    def draw(self, context):
        layout = self.layout
        settings = context.scene.ppparty

        from .. import receiver
        from ..core.phone_connect import get_local_ip

        if not receiver.is_running:
            # --- Disconnected ---
            layout.prop(settings, "pp_port")

            # Webcam (primary)
            layout.prop(settings, "pp_show_preview")
            layout.operator("ppparty.start_webcam", icon='CAMERA_DATA')

            # Phone (secondary / fallback)
            box_phone = layout.box()
            box_phone.label(text="Or use your phone:", icon='PHONE')
            box_phone.operator("ppparty.connect_phone", icon='PLAY')
            col = box_phone.column(align=True)
            col.scale_y = 0.8
            col.label(text="1. Same WiFi as computer")
            col.label(text="2. Open Live Link Face app")
            col.label(text="3. Enter IP shown after connect")

        elif not receiver.is_receiving:
            # --- Waiting for data ---
            source = receiver.source
            if source == 'mediapipe':
                layout.label(text="Starting webcam...", icon='SORTTIME')
            else:
                ip = get_local_ip() or "unknown"
                layout.label(text=f"Listening on {ip}:{receiver.port}",
                             icon='SORTTIME')
                layout.label(text="Waiting for phone...")

                box = layout.box()
                box.label(text="On your phone:", icon='PHONE')
                col = box.column(align=True)
                col.scale_y = 0.8
                col.label(text=f"1. Open Live Link Face")
                col.label(text=f"2. Set target IP to: {ip}")
                col.label(text=f"3. Set port to: {receiver.port}")
                col.label(text=f"4. Hit Stream")

            layout.separator()
            if source == 'mediapipe':
                layout.operator("ppparty.stop_webcam", icon='PAUSE')
            else:
                layout.operator("ppparty.disconnect_phone", icon='PAUSE')

        else:
            # --- Receiving tracking data ---
            source = receiver.source or 'unknown'
            if source == 'mediapipe':
                layout.label(text="Webcam tracking active!", icon='CHECKMARK')
                # Show body landmark status
                if receiver.body_landmarks:
                    layout.label(text="Face + Body detected",
                                 icon='OUTLINER_OB_ARMATURE')
                else:
                    layout.label(text="Face detected",
                                 icon='FACE_MAPS')
            else:
                layout.label(text="Phone tracking active!", icon='CHECKMARK')

            # Show live values
            values = receiver.get_latest_values()
            if values:
                box = layout.box()
                box.label(text="Live Data:", icon='FACE_MAPS')
                col = box.column(align=True)
                col.scale_y = 0.8
                for key in ('jawOpen', 'eyeBlinkLeft', 'eyeBlinkRight',
                            'mouthSmileRight'):
                    v = values.get(key, 0.0)
                    col.label(text=f"  {key}: {v:.2f}")

            layout.separator()
            if source == 'mediapipe':
                layout.operator("ppparty.stop_webcam", icon='PAUSE')
            else:
                layout.operator("ppparty.disconnect_phone", icon='PAUSE')


class PPPARTY_PT_debug_panel(bpy.types.Panel):
    """Debug tools — inspect modifier properties for Blender 5.2."""

    bl_label = "Debug"
    bl_idname = "PPPARTY_PT_debug_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "PPPARTY"
    bl_order = 2
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        layout.operator("ppparty.debug_modifier", icon='VIEWZOOM')
        layout.label(text="Results → Text Editor", icon='TEXT')
        layout.label(text="(open 'PPParty_Debug')")


class PPPARTY_PT_instructions_panel(bpy.types.Panel):
    """Usage instructions."""

    bl_label = "How to Use"
    bl_idname = "PPPARTY_PT_instructions_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "PPPARTY"
    bl_order = 3
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        box = layout.box()
        col = box.column(align=True)
        col.scale_y = 0.8
        col.label(text="1. Click 'Create Marionette'")
        col.label(text="2. Press Play on the timeline")
        col.label(text="3. Click 'Start Webcam'")
        col.label(text="4. Tilt head left/right = walk")
        col.label(text="5. Lean back = arms extend")
        col.label(text="6. Push mouth left/right = step")
        col.label(text="7. Smile = hands up, frown = down")
        col.label(text="8. Face expressions drive the head")
        col.label(text="")
        col.label(text="Tune sliders in Body Movement")
        col.label(text="to adjust responsiveness.")


# ===================================================================
# HELPERS
# ===================================================================

def _draw_slider_group(col, mod, names):
    """Draw GN modifier sliders for the given socket names."""
    for item in mod.node_group.interface.items_tree:
        if (hasattr(item, 'item_type')
                and item.item_type == 'SOCKET'
                and item.in_out == 'INPUT'
                and item.name in names):
            prop_path = f'["{item.identifier}"]'
            col.prop(mod, prop_path, text=item.name)


def _draw_material_slots(col, mod, names):
    """Draw material picker dropdowns for GN modifier Material sockets."""
    for item in mod.node_group.interface.items_tree:
        if (hasattr(item, 'item_type')
                and item.item_type == 'SOCKET'
                and item.in_out == 'INPUT'
                and item.socket_type == 'NodeSocketMaterial'
                and item.name in names):
            prop_path = f'["{item.identifier}"]'
            col.prop(mod, prop_path, text=item.name)


def _draw_object_slots(col, mod, names):
    """Draw Object picker dropdowns for GN modifier Object sockets."""
    for item in mod.node_group.interface.items_tree:
        if (hasattr(item, 'item_type')
                and item.item_type == 'SOCKET'
                and item.in_out == 'INPUT'
                and item.socket_type == 'NodeSocketObject'
                and item.name in names):
            prop_path = f'["{item.identifier}"]'
            col.prop(mod, prop_path, text=item.name)
