# Pull the Chibi sculpt + David's own Exoside retopo out of the class blend
# into small standalone files the A/B harness can load fast.
import bpy, sys, os
S = sys.argv[sys.argv.index('--')+1]
sc = bpy.data.objects['Cube.001']; rt = bpy.data.objects['Retopo_Cube.001']
for o in (sc, rt):
    print("XFORM", o.name, tuple(o.location), tuple(o.rotation_euler), tuple(o.scale), o.parent)
    m = o.data
    xs = [v.co.x for v in m.vertices]
    print("  xrange", min(xs), max(xs), "attrs", [a.name for a in m.attributes][:12], "mats", len(m.materials))
# symmetry check on the retopo: fraction of verts with a mirror partner
import mathutils
kd = mathutils.kdtree.KDTree(len(rt.data.vertices))
for i,v in enumerate(rt.data.vertices): kd.insert(v.co, i)
kd.balance()
hit = sum(1 for v in rt.data.vertices if kd.find(mathutils.Vector((-v.co.x, v.co.y, v.co.z)))[2] < 1e-4)
print("RETOPO mirror-partner fraction", hit/len(rt.data.vertices))
# save standalone libraries
bpy.data.libraries.write(os.path.join(S, 'input/chibi_sculpt_full.blend'), {sc, sc.data})
bpy.data.libraries.write(os.path.join(S, 'input/chibi_david_exoside_retopo.blend'), {rt, rt.data})
print("WROTE")
