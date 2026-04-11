# SPDX-License-Identifier: GPL-3.0-or-later
"""PPParty — Debug Modifier Properties.

Diagnostic tool for Blender 5.2 modifier API changes.
Writes results to a Text Editor block so David can see what's happening
without needing a terminal window.
"""

import bpy


class PPPARTY_OT_debug_modifier(bpy.types.Operator):
    """Inspect PPParty modifier properties and test write methods"""

    bl_idname = "ppparty.debug_modifier"
    bl_label = "Debug Modifier"
    bl_options = {'REGISTER'}

    def execute(self, context):
        puppet = bpy.data.objects.get("PP_Marionette")
        if not puppet:
            self.report({'ERROR'}, "No PP_Marionette in scene")
            return {'CANCELLED'}

        mod = puppet.modifiers.get("PPParty_Physics")
        if not mod or not mod.node_group:
            self.report({'ERROR'}, "No PPParty_Physics modifier with node group")
            return {'CANCELLED'}

        lines = []
        lines.append("=== PPParty Modifier Debug ===")
        lines.append(f"Blender: {bpy.app.version_string}")
        lines.append(f"Modifier: {mod.name} (type={mod.type})")
        lines.append(f"Node group: {mod.node_group.name}")

        # --- 1. ALL RNA properties on the modifier (no filtering) ---
        lines.append("")
        lines.append("--- ALL RNA Properties (mod.rna_type.properties) ---")
        float_rna_props = []
        for prop in mod.rna_type.properties:
            ptype = getattr(prop, 'type', '?')
            psub = getattr(prop, 'subtype', '?')
            lines.append(f"  {prop.identifier}  type={ptype}  sub={psub}")
            if ptype == 'FLOAT':
                float_rna_props.append(prop.identifier)

        lines.append(f"  >> {len(float_rna_props)} FLOAT properties found")
        if float_rna_props:
            lines.append(f"  >> Float prop names: {float_rna_props[:20]}")

        # --- 2. IDProperty keys ---
        lines.append("")
        lines.append("--- IDProperty Keys (mod.keys()) ---")
        try:
            keys = list(mod.keys())
            if keys:
                for k in keys[:30]:
                    try:
                        v = mod[k]
                        lines.append(f"  '{k}' = {v}")
                    except Exception as e:
                        lines.append(f"  '{k}' = ERROR: {e}")
            else:
                lines.append("  (empty — no IDProperty keys)")
        except Exception as e:
            lines.append(f"  Error accessing keys: {e}")

        # --- 3. Node group interface sockets ---
        lines.append("")
        lines.append("--- Node Group Interface (input sockets) ---")
        float_sockets = []
        for item in mod.node_group.interface.items_tree:
            if (hasattr(item, 'item_type')
                    and item.item_type == 'SOCKET'
                    and item.in_out == 'INPUT'):
                stype = getattr(item, 'socket_type', '?')
                sid = item.identifier
                lines.append(f"  '{item.name}'  id={sid}  type={stype}")
                if stype == 'NodeSocketFloat':
                    float_sockets.append((item.name, sid))

        # --- 4. dir(mod) scan for unknown attributes ---
        lines.append("")
        lines.append("--- dir(mod) unique attrs (not in base type) ---")
        base_attrs = set(dir(bpy.types.Modifier))
        mod_attrs = set(dir(mod))
        unique = sorted(mod_attrs - base_attrs)
        # Filter out private/dunder
        unique = [a for a in unique if not a.startswith('__')]
        lines.append(f"  {unique[:50]}")

        # --- 5. Access tests for first 3 float sockets ---
        lines.append("")
        lines.append("--- ACCESS TESTS (first 3 float sockets) ---")
        for name, sid in float_sockets[:3]:
            lines.append(f"")
            lines.append(f"  Socket: '{name}' (id={sid})")

            # Test A: IDProperty read
            try:
                v = mod[sid]
                lines.append(f"    mod['{sid}'] READ = {v}  ✓")
            except Exception as e:
                lines.append(f"    mod['{sid}'] READ = FAIL: {e}")

            # Test B: getattr with exact identifier
            try:
                v = getattr(mod, sid)
                lines.append(f"    getattr(mod, '{sid}') = {v}  ✓")
            except Exception as e:
                lines.append(f"    getattr(mod, '{sid}') = FAIL: {e}")

            # Test C: getattr with lowercase
            sid_lower = sid.lower()
            try:
                v = getattr(mod, sid_lower)
                lines.append(f"    getattr(mod, '{sid_lower}') = {v}  ✓")
            except Exception as e:
                lines.append(f"    getattr(mod, '{sid_lower}') = FAIL: {e}")

            # Test D: getattr with lowercase + underscore
            sid_snake = sid.lower().replace('-', '_')
            if sid_snake != sid_lower:
                try:
                    v = getattr(mod, sid_snake)
                    lines.append(f"    getattr(mod, '{sid_snake}') = {v}  ✓")
                except Exception as e:
                    lines.append(f"    getattr(mod, '{sid_snake}') = FAIL: {e}")

        # --- 6. Write test: try setting jawOpen to 0.75 ---
        lines.append("")
        lines.append("--- WRITE TESTS (jawOpen → 0.75) ---")
        jaw_sid = None
        jaw_iface = None
        for item in mod.node_group.interface.items_tree:
            if (hasattr(item, 'item_type') and item.item_type == 'SOCKET'
                    and item.in_out == 'INPUT' and item.name == 'jawOpen'):
                jaw_sid = item.identifier
                jaw_iface = item
                break

        if jaw_sid:
            # Method 1: IDProperty write + update_tag
            try:
                mod[jaw_sid] = 0.75
                puppet.update_tag()
                readback = mod[jaw_sid]
                lines.append(f"  mod['{jaw_sid}'] = 0.75 + update_tag()")
                lines.append(f"    readback: {readback}")
            except Exception as e:
                lines.append(f"  IDProp write: FAIL — {e}")

            # Method 2: setattr + update_tag
            for attr_name in [jaw_sid, jaw_sid.lower(),
                              jaw_sid.lower().replace('-', '_')]:
                try:
                    setattr(mod, attr_name, 0.75)
                    puppet.update_tag()
                    readback = getattr(mod, attr_name)
                    lines.append(f"  setattr(mod, '{attr_name}', 0.75)")
                    lines.append(f"    readback: {readback}  ✓ WORKS")
                    break
                except Exception as e:
                    lines.append(f"  setattr '{attr_name}': FAIL — {e}")

            # Method 3: interface default_value
            if jaw_iface:
                try:
                    old_val = jaw_iface.default_value
                    jaw_iface.default_value = 0.75
                    puppet.update_tag()
                    lines.append(f"  interface default_value = 0.75  ✓")
                    lines.append(f"    (was {old_val})")
                    # Reset it
                    jaw_iface.default_value = old_val
                except Exception as e:
                    lines.append(f"  interface default_value: FAIL — {e}")

            # Method 4: path_resolve test
            lines.append("")
            lines.append("  -- path_resolve tests --")
            paths_to_try = [
                f'["{jaw_sid}"]',
                jaw_sid.lower(),
                f'node_group.interface.items_tree["{jaw_sid}"].default_value',
            ]
            for path in paths_to_try:
                try:
                    resolved = mod.path_resolve(path)
                    lines.append(f"    path_resolve('{path}') = {resolved}  ✓")
                except Exception as e:
                    lines.append(f"    path_resolve('{path}') = FAIL")

        else:
            lines.append("  No jawOpen socket found on interface!")

        # --- 7. Check if puppet responds after write ---
        lines.append("")
        lines.append("--- RESULT ---")
        lines.append("If jawOpen 0.75 worked, the puppet's mouth should be open.")
        lines.append("Check the viewport — did the mouth move?")
        lines.append("")
        lines.append("COPY EVERYTHING ABOVE if mouth did NOT move.")

        # Write to text block
        text_name = "PPParty_Debug"
        if text_name in bpy.data.texts:
            bpy.data.texts.remove(bpy.data.texts[text_name])
        text_block = bpy.data.texts.new(text_name)
        text_block.write('\n'.join(lines))

        # Switch a text editor to show it (if one exists)
        for area in context.screen.areas:
            if area.type == 'TEXT_EDITOR':
                area.spaces.active.text = text_block
                break

        self.report({'INFO'},
                    "Debug written to Text Editor → 'PPParty_Debug'")
        return {'FINISHED'}
