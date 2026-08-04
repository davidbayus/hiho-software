"""
Round A diagnostic — paste into Blender 5.2 Text Editor and Run.

Prereq:
  1. Install PPPARTY_v1.0.0-alpha.14-refactor-blob-head.zip (Preferences → Install)
  2. Open a fresh .blend
  3. In the PPPARTY N-panel, press "Create Marionette"
  4. Select the "PP_Marionette" object in the outliner
  5. Open this file in Blender's Text Editor and click "Run Script"

After running, a new text block "PPParty_RoundA_Report" appears in the Text
Editor dropdown. Open it and copy the whole thing back to Claude.

This covers:
  A1  — did Create Marionette build Hand/Foot/Shoulder/Cheek sliders?
  A2  — does items_tree flatten nested panels on 5.2?
  A3  — does NodeTreeInterfaceSocket.hide_in_modifier exist on 5.2?
  A3b — do nested interface panels work on 5.2? (Round C prereq)
"""

import bpy

lines = []
def log(s=""):
    print(s)
    lines.append(s)

puppet = bpy.data.objects.get("PP_Marionette")
if not puppet:
    log("[Round A] FAIL: No 'PP_Marionette' object. Run Create Marionette first.")
else:
    mod = next((m for m in puppet.modifiers if m.type == "NODES"), None)
    if not mod or not mod.node_group:
        log("[Round A] FAIL: PP_Marionette has no GeometryNodes modifier.")
    else:
        tree = mod.node_group
        iface = tree.interface

        # ---- A2 — items_tree traversal scope ----
        items = list(iface.items_tree)
        log("=" * 60)
        log(f"[A2] items_tree length: {len(items)}")
        log("[A2] Item breakdown by type and parent:")
        panels_seen = {}
        sockets_under_panel = {}
        for it in items:
            kind = it.item_type  # 'PANEL' or 'SOCKET'
            parent = getattr(it, "parent", None)
            parent_name = parent.name if parent else "<root>"
            if kind == "PANEL":
                panels_seen[it.name] = parent_name
            else:
                sockets_under_panel.setdefault(parent_name, []).append(it.name)

        log(f"\n[A2] Panels seen ({len(panels_seen)}):")
        for p, parent in panels_seen.items():
            count = len(sockets_under_panel.get(p, []))
            nest_tag = f" (nested under '{parent}')" if parent != "<root>" else ""
            log(f"    - {p}: {count} sockets{nest_tag}")

        log(f"\n[A2] Root-level sockets: {len(sockets_under_panel.get('<root>', []))}")

        # ---- A1 — check specific sub-sections for sliders ----
        log("\n" + "=" * 60)
        log("[A1] Customization sub-section slider counts:")
        expected = {
            "Hands": ["Hand Size", "Hand Width", "Hand Rotation", "Hand Tilt"],
            "Feet": ["Foot Size", "Foot Width", "Foot Depth", "Foot Rotation"],
            "Shoulders": ["Shoulder Width", "Shoulder Rotation"],
            "Cheeks": ["Cheek Size", "Cheek Material", "Cheek Spacing",
                       "Cheek Height", "Cheek Depth", "Cheek Width", "Cheek Rotation"],
        }
        all_socket_names = {it.name for it in items if it.item_type == "SOCKET"}
        for group, names in expected.items():
            present = [n for n in names if n in all_socket_names]
            missing = [n for n in names if n not in all_socket_names]
            status = "OK" if not missing else "MISSING"
            log(f"    [{status}] {group}: {len(present)}/{len(names)} present"
                + (f"  missing={missing}" if missing else ""))

        # ---- A3 — hide_in_modifier attribute probe ----
        log("\n" + "=" * 60)
        sample_socket = next((it for it in items if it.item_type == "SOCKET"), None)
        if sample_socket is None:
            log("[A3] SKIP: no sockets to probe.")
        else:
            has_attr = hasattr(sample_socket, "hide_in_modifier")
            log(f"[A3] hasattr(socket, 'hide_in_modifier'): {has_attr}")
            if has_attr:
                log(f"[A3]   default value on '{sample_socket.name}': "
                    f"{sample_socket.hide_in_modifier}")
                log("[A3]   --> OK: Round B can use hide_in_modifier directly.")
            else:
                log("[A3]   --> Attribute missing on 5.2 — will need the "
                    "separate-collapsed-panel fallback described in handoff §5.1.")

        # ---- A3b — nested panel probe (Round C prereq) ----
        log("\n" + "=" * 60)
        try:
            test_parent = iface.new_panel("ROUND_A_TEST_PARENT")
            try:
                test_child = iface.new_panel("ROUND_A_TEST_CHILD", parent=test_parent)
                log("[A3b] new_panel(parent=...) works — "
                    "Round C can nest the blob head sub-panels.")
                iface.remove(test_child)
            except TypeError as e:
                log(f"[A3b] new_panel(parent=...) THREW TypeError: {e}")
                log("[A3b] Round C is BLOCKED — need different consolidation approach.")
            iface.remove(test_parent)
        except Exception as e:
            log(f"[A3b] Unexpected error creating test panel: {e}")

        log("\n" + "=" * 60)
        log("[Round A] Done. Open 'PPParty_RoundA_Report' text block and copy-paste back to Claude.")

# Write everything to a Blender text block so David can open it in the Text Editor
# without needing the System Console.
report_name = "PPParty_RoundA_Report"
if report_name in bpy.data.texts:
    bpy.data.texts[report_name].clear()
    txt = bpy.data.texts[report_name]
else:
    txt = bpy.data.texts.new(report_name)
txt.write("\n".join(lines))
print(f"\n>>> Report saved to text block: {report_name} <<<")
