"""Diagnostic 3: Find how to create a PAIRED simulation zone in 5.2.
Run in Text Editor (Alt+P). Results in 'SimZone_Results'.
"""
import bpy

out_name = "SimZone_Results"
if out_name in bpy.data.texts:
    bpy.data.texts.remove(bpy.data.texts[out_name])
txt = bpy.data.texts.new(out_name)

def log(msg):
    txt.write(msg + "\n")

log("=== SIMZONE DIAGNOSTIC 3 ===")
log(f"Blender: {bpy.app.version_string}\n")

# --- TEST 1: Check node tree for zone-related attributes ---
tree = bpy.data.node_groups.new("_Test_SimZone", 'GeometryNodeTree')
log("Node tree zone-related attrs:")
for attr in sorted(dir(tree)):
    if any(kw in attr.lower() for kw in ('zone', 'sim', 'repeat')):
        try:
            val = getattr(tree, attr)
            if not callable(val):
                log(f"  tree.{attr} = {val!r}")
            else:
                log(f"  tree.{attr}() = <callable>")
        except:
            log(f"  tree.{attr} = <error>")
bpy.data.node_groups.remove(tree)

# --- TEST 2: List all node.* operators with sim/zone ---
log("\nbpy.ops.node operators with 'sim' or 'zone':")
for attr in sorted(dir(bpy.ops.node)):
    if any(kw in attr.lower() for kw in ('sim', 'zone')):
        log(f"  bpy.ops.node.{attr}")

# --- TEST 3: Try the operator approach ---
log("\n--- Trying operator approach ---")

# Create a mesh with GN modifier so we have a context
mesh = bpy.data.meshes.new("_TestMesh")
obj = bpy.data.objects.new("_TestObj", mesh)
bpy.context.collection.objects.link(obj)
bpy.context.view_layer.objects.active = obj
obj.select_set(True)

tree = bpy.data.node_groups.new("_Test_SimZone", 'GeometryNodeTree')
mod = obj.modifiers.new("TestGN", 'NODES')
mod.node_group = tree

# Try to find a node editor area or use temp_override
found_area = None
for area in bpy.context.screen.areas:
    if area.type == 'NODE_EDITOR':
        found_area = area
        break

if found_area:
    log(f"Found NODE_EDITOR area, trying operator...")
    for region in found_area.regions:
        if region.type == 'WINDOW':
            try:
                with bpy.context.temp_override(
                        area=found_area, region=region,
                        space_data=found_area.spaces.active):
                    # Make sure the tree is active
                    found_area.spaces.active.node_tree = tree
                    bpy.ops.node.add_simulation_zone()
                log("Operator succeeded!")
                log(f"Nodes after operator ({len(tree.nodes)}):")
                for n in tree.nodes:
                    log(f"  name={n.name!r} type={n.type!r}")
                # Check pairing
                for n in tree.nodes:
                    if n.type == 'SIMULATION_INPUT':
                        log(f"  SimInput.paired_output = {n.paired_output!r}")
                    if n.type == 'SIMULATION_OUTPUT':
                        log(f"  SimOutput has state_items: len={len(n.state_items)}")
            except Exception as e:
                log(f"Operator failed: {e}")
            break
else:
    log("No NODE_EDITOR area found.")
    log("Please split your Blender window and make one area a")
    log("Geometry Nodes editor, then re-run this script.")

# Cleanup
bpy.data.objects.remove(obj, do_unlink=True)
bpy.data.meshes.remove(mesh)
bpy.data.node_groups.remove(tree)

log("\n=== DONE ===")
