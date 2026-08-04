"""
Round A addendum — probe the 5.2 panel-nesting API.

Same prereq as the main diagnostic (PP_Marionette exists, has GN modifier).
Open in Blender Text Editor, click Run Script.
Results append to the 'PPParty_RoundA_Report' text block.
"""

import bpy

lines = []
def log(s=""):
    print(s)
    lines.append(s)

puppet = bpy.data.objects.get("PP_Marionette")
if not puppet:
    log("[Addendum] FAIL: No PP_Marionette.")
else:
    mod = next((m for m in puppet.modifiers if m.type == "NODES"), None)
    if not mod or not mod.node_group:
        log("[Addendum] FAIL: no GN modifier.")
    else:
        iface = mod.node_group.interface

        log("=" * 60)
        log("[A3c] Probing interface API for panel nesting alternatives.")

        interesting = [a for a in dir(iface)
                       if any(k in a.lower() for k in
                              ("move", "parent", "panel", "reparent"))]
        log(f"[A3c] Candidate methods/attrs on interface:")
        for a in sorted(interesting):
            log(f"    - {a}")

        log("\n[A3c] Attempting two-step nest: create + move_to_parent.")
        try:
            parent_panel = iface.new_panel("ROUND_A_ADDENDUM_PARENT")
            child_panel = iface.new_panel("ROUND_A_ADDENDUM_CHILD")
            try:
                # Standard 4.x+ signature: move_to_parent(item, new_parent, to_position=-1)
                iface.move_to_parent(child_panel, parent_panel)
                log("[A3c]   move_to_parent(child, parent) SUCCEEDED.")
                # verify by reading parent
                new_parent = getattr(child_panel, "parent", None)
                np_name = new_parent.name if new_parent else "<none>"
                log(f"[A3c]   child.parent.name now = '{np_name}'")
                if np_name == "ROUND_A_ADDENDUM_PARENT":
                    log("[A3c]   --> CONFIRMED: nested panels work via move_to_parent. "
                        "Round C unblocked.")
                else:
                    log("[A3c]   --> Call succeeded but parent not updated. Suspicious.")
            except Exception as e:
                log(f"[A3c]   move_to_parent failed: {type(e).__name__}: {e}")
                log("[A3c]   Checking alternative signatures...")
                try:
                    iface.move_to_parent(child_panel, parent_panel, 0)
                    log("[A3c]   3-arg version worked.")
                except Exception as e2:
                    log(f"[A3c]   3-arg version failed too: {e2}")

            # cleanup
            try:
                iface.remove(child_panel)
            except Exception:
                pass
            try:
                iface.remove(parent_panel)
            except Exception:
                pass
        except Exception as outer_e:
            log(f"[A3c] Outer setup failed: {outer_e}")

        log("=" * 60)
        log("[Addendum] Done. Re-copy PPParty_RoundA_Report.")

# Append to existing report text block
report_name = "PPParty_RoundA_Report"
if report_name in bpy.data.texts:
    existing = bpy.data.texts[report_name].as_string()
    bpy.data.texts[report_name].clear()
    bpy.data.texts[report_name].write(existing + "\n\n" + "\n".join(lines))
else:
    txt = bpy.data.texts.new(report_name)
    txt.write("\n".join(lines))

print(f"\n>>> Appended to {report_name} <<<")
