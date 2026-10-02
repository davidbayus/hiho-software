"""Shared helpers for the Quadre vs Exoside A/B harness (runs inside Blender)."""
import bpy, bmesh, os, sys, json, math, time
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree


def args_after_dashes():
    return sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []


def read_obj(path):
    verts, faces = [], []
    with open(path) as f:
        for line in f:
            if line.startswith('v '):
                t = line.split()
                verts.append((float(t[1]), float(t[2]), float(t[3])))
            elif line.startswith('f '):
                faces.append(tuple(int(tok.split('/')[0]) - 1 for tok in line.split()[1:]))
    return verts, faces


def write_obj(path, verts, faces):
    with open(path, 'w') as f:
        for v in verts:
            f.write(f"v {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}\n")
        for fc in faces:
            f.write("f " + " ".join(str(i + 1) for i in fc) + "\n")


def obj_from_pydata(name, verts, faces):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def append_objects(blend):
    with bpy.data.libraries.load(blend) as (src, dst):
        dst.objects = list(src.objects)
    out = []
    for o in dst.objects:
        bpy.context.scene.collection.objects.link(o)
        out.append(o)
    return out


def world_verts_faces(obj):
    m = obj.data
    mw = obj.matrix_world
    co = np.empty(len(m.vertices) * 3, dtype=np.float64)
    m.vertices.foreach_get('co', co)
    co = co.reshape(-1, 3)
    M = np.array(mw)
    co = co @ M[:3, :3].T + M[:3, 3]
    faces = [tuple(p.vertices) for p in m.polygons]
    return co, faces


def clear_scene():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o)


def only_select(obj):
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    obj.hide_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
