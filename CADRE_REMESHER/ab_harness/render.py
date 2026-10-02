"""Side-by-side wireframe renders with singularity markers (red = 3-pole, blue = 5-pole,
magenta = 6+). Runs headless with Workbench.

blender -b --factory-startup --python render.py -- <out_prefix> <px_per_slot> <views csv> <label>=<path.obj> ...
views: front,side,back,threeq,head,headside,top,feet
env: NO_WIRE=1 (surface only), HEAT=1 (colour by flow error), RENDER_BG=<linear grey>, NO_POLES=1
"""
import bpy, bmesh, os, sys, json, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ab_common import *
import numpy as np

a = args_after_dashes()
out_prefix, px = a[0], int(a[1])
views = a[2].split(',')
items = [x.split('=', 1) for x in a[3:]]

clear_scene()
scene = bpy.context.scene
scene.render.engine = 'BLENDER_WORKBENCH'
sh = scene.display.shading
sh.light = 'STUDIO'
sh.color_type = 'OBJECT'
sh.show_object_outline = False
sh.show_shadows = False
sh.show_cavity = False
scene.display.render_aa = '8'
scene.view_settings.view_transform = 'Standard'
if scene.world is None:
    scene.world = bpy.data.worlds.new('w')
scene.world.use_nodes = False
scene.world.color = (1, 1, 1)
if os.environ.get('RENDER_BG'):          # linear grey level, e.g. 0.0103 = slide background 1A1A1A
    g = float(os.environ['RENDER_BG']); scene.world.color = (g, g, g)
scene.render.film_transparent = False
scene.render.image_settings.file_format = 'PNG'

meshes = []
for label, path in items:
    verts, faces = read_obj(path)
    V_ = np.array(verts)
    if os.environ.get('NORMALIZE'):
        V_ = (V_ - 0.5 * (V_.min(0) + V_.max(0))) / float((V_.max(0) - V_.min(0)).max())
    meshes.append((label, V_, faces))
allv = np.concatenate([m[1] for m in meshes])
lo, hi = allv.min(0), allv.max(0)
center = 0.5 * (lo + hi)
half = 0.5 * (hi - lo)
rad_xy = float(np.linalg.norm(half[:2]))
hz = float(half[2])

ico_bm = bmesh.new()
bmesh.ops.create_icosphere(ico_bm, subdivisions=1, radius=1.0)
ico_v = np.array([v.co[:] for v in ico_bm.verts])
ico_f = [tuple(v.index for v in f.verts) for f in ico_bm.faces]
ico_bm.free()

COL = {3: (1.0, 0.15, 0.05, 1), 5: (0.05, 0.35, 1.0, 1), 6: (0.9, 0.0, 0.9, 1), 2: (1.0, 0.8, 0.0, 1)}
groups = []
for (label, V, faces), (_, path) in zip(meshes, items):
    Vc = V - center
    root = bpy.data.objects.new(label + '_root', None)
    scene.collection.objects.link(root)
    surf = obj_from_pydata(label + '_surf', Vc.tolist(), faces)
    surf.color = (0.82, 0.84, 0.88, 1)
    surf.parent = root
    for p in surf.data.polygons:
        p.use_smooth = False
    heat = os.environ.get('HEAT') and (os.path.exists(path + '.mis.npy') or os.path.exists(path + '.fcol.npy'))
    if heat:
        if os.path.exists(path + '.fcol.npy'):
            c3 = np.load(path + '.fcol.npy')
            cols = np.concatenate([c3, np.ones((len(c3), 1))], 1)
        else:
            mis = np.load(path + '.mis.npy')
            cols = np.empty((len(mis), 4))
            t = np.clip(mis / 25.0, 0, 1)
            cols[:, 0] = 0.15 + 0.85 * t; cols[:, 1] = 0.75 - 0.6 * t; cols[:, 2] = 0.95 - 0.9 * t; cols[:, 3] = 1
            cols[mis < 0] = (0.82, 0.82, 0.82, 1)
        ca = surf.data.color_attributes.new('Col', 'FLOAT_COLOR', 'CORNER')
        nper = np.array([len(f) for f in faces])
        ca.data.foreach_set('color', np.repeat(cols, nper, axis=0).ravel())
        sh.color_type = 'VERTEX'
    # edges + valence
    es = set()
    for f in faces:
        n = len(f)
        for k in range(n):
            x, y = f[k], f[(k + 1) % n]
            es.add((x, y) if x < y else (y, x))
    E = np.array(list(es))
    val = np.bincount(E.ravel(), minlength=len(V))
    emean = float(np.linalg.norm(V[E[:, 0]] - V[E[:, 1]], axis=1).mean())
    wire = obj_from_pydata(label + '_wire', Vc.tolist(), faces)
    if os.environ.get('NO_WIRE'):
        wire.hide_render = True
    wm = wire.modifiers.new('w', 'WIREFRAME')
    wm.thickness = max(0.0035 * 2 * hz, 0.05 * emean) * 0.55
    wm.use_replace = True
    wm.use_even_offset = False
    wire.color = (0.02, 0.02, 0.03, 1)
    if heat:
        cb = wire.data.color_attributes.new('Col', 'FLOAT_COLOR', 'CORNER')
        cb.data.foreach_set('color', np.tile([0.02, 0.02, 0.03, 1.0], len(cb.data)))
    wire.parent = root
    for cls, test in (() if os.environ.get('NO_POLES') else ((3, val == 3), (5, val == 5), (6, val >= 6), (2, val <= 2))):
        idx = np.nonzero(test)[0]
        if len(idx) == 0:
            continue
        r = 0.2 * emean
        mv, mf = [], []
        for j, i in enumerate(idx):
            base = len(mv)
            mv.extend((ico_v * r + Vc[i]).tolist())
            mf.extend([tuple(base + t for t in f) for f in ico_f])
        mk = obj_from_pydata(f'{label}_v{cls}', mv, mf)
        mk.color = COL[cls]
        if os.environ.get('HEAT'):
            cm = mk.data.color_attributes.new('Col', 'FLOAT_COLOR', 'CORNER')
            cm.data.foreach_set('color', np.tile(COL[cls], len(cm.data)))
        mk.parent = root
    groups.append(root)

n = len(groups)
slot_w = 2.0 * rad_xy * 1.06
for i, root in enumerate(groups):
    root.location = ((i - (n - 1) / 2) * slot_w, 0, 0)

cam_data = bpy.data.cameras.new('cam')
cam_data.type = 'ORTHO'
cam = bpy.data.objects.new('cam', cam_data)
scene.collection.objects.link(cam)
scene.camera = cam
cam_data.clip_start = 0.01
cam_data.clip_end = 1000

# name: (yaw_deg, pitch_deg, z_lo_frac, z_hi_frac)  fractions of full height, 0 = feet, 1 = top
VIEWS = {
    'front': (0, 0, 0.0, 1.0), 'side': (90, 0, 0.0, 1.0), 'back': (180, 0, 0.0, 1.0),
    'threeq': (35, 12, 0.0, 1.0), 'threeqback': (145, 12, 0.0, 1.0),
    'head': (0, 0, 0.45, 1.0), 'headside': (90, 0, 0.45, 1.0), 'headq': (35, 10, 0.45, 1.0),
    'body': (0, 0, 0.0, 0.55), 'bodyq': (35, 10, 0.0, 0.55), 'bodyback': (180, 0, 0.0, 0.55),
    'top': (0, 80, 0.0, 1.0),
}
info = {'labels': [m[0] for m in meshes], 'views': {}}
for vname in views:
    yaw, pitch, z0, z1 = VIEWS[vname]
    for root in groups:
        root.rotation_euler = (math.radians(pitch), 0, math.radians(-yaw))
    zc = (-hz + (z0 + z1) * hz) if pitch == 0 else 0.0
    zspan = (z1 - z0) * 2 * hz * 1.06 if pitch == 0 else 2 * max(hz, rad_xy) * 1.06
    zoom = (z1 - z0) if pitch == 0 else 1.0
    width_world = n * slot_w
    if zoom < 0.99:
        # zoomed views: shrink slot so the crop fills the frame
        vis_w = min(slot_w, zspan * 1.15)
        for i, root in enumerate(groups):
            root.location = ((i - (n - 1) / 2) * vis_w, 0, 0)
        width_world = n * vis_w
    else:
        for i, root in enumerate(groups):
            root.location = ((i - (n - 1) / 2) * slot_w, 0, 0)
    cam.location = (0, -50, zc)
    cam.rotation_euler = (math.radians(90), 0, 0)
    scene.render.resolution_x = px * n
    scene.render.resolution_y = int(round(px * n * zspan / width_world))
    scene.render.resolution_percentage = 100
    cam_data.ortho_scale = max(width_world, zspan * scene.render.resolution_x / scene.render.resolution_y)
    path = f"{out_prefix}_{vname}.png"
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    info['views'][vname] = {'path': path, 'w': scene.render.resolution_x, 'h': scene.render.resolution_y}
    print("AB RENDER", path)
with open(out_prefix + '_info.json', 'w') as f:
    json.dump(info, f)
