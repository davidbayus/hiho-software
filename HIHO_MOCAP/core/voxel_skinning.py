"""HIHO MOCAP — skin character meshes to a rig via the vendored voxel solver.

Exchange format (plain text, one file each way) and CLI contract are the
vendored solver's own — see external/voxel_skinning/README.md. This glue is
HIHO's, written fresh; the upstream GPL addon wrapper is not used.

The solver runs as a watched subprocess (same pattern as the FreeMoCap
runner): Blender ships no wheels and the binary is Blender-version-proof.
Falls back to Blender's Automatic Weights on any failure so the student
always leaves with a rigged character.
"""

import os
import platform
import subprocess
import tempfile
from typing import List, Tuple

import bpy

SOLVER_TIMEOUT_SECONDS = 600
# Solver knobs: voxel resolution, diffuse loops, sample rays, max influence
# bones, falloff, sharpness preset, detect-solidify. Upstream defaults except
# influence 8 -> 4: student rigs go to game engines / FBX where 4 is the norm.
SOLVER_ARGS = ("128", "5", "64", "4", "0.2", "3", "n")


def _binary_path() -> str:
    if platform.system() != "Darwin":
        return ""
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "external", "voxel_skinning", "vhd_mac_universal")


def _write_mesh_file(meshes: List[bpy.types.Object], path: str) -> int:
    total = 0
    with open(path, "w", encoding="utf-8") as f:
        f.write("# hiho mesh export\n")
        offset = 0
        for ob in meshes:
            for v in ob.data.vertices:
                co = ob.matrix_world @ v.co
                f.write(f"v,{co[0]},{co[1]},{co[2]}\n")
            for poly in ob.data.polygons:
                f.write("f" + "".join(
                    f",{offset + ob.data.loops[i].vertex_index}"
                    for i in poly.loop_indices) + "\n")
            offset += len(ob.data.vertices)
            total = offset
    return total


def _write_bone_file(rig: bpy.types.Object, path: str) -> int:
    count = 0
    with open(path, "w", encoding="utf-8") as f:
        f.write("# hiho bone export\n")
        for bone in rig.data.bones:
            if not bone.use_deform:
                continue
            h = rig.matrix_world @ bone.head_local
            t = rig.matrix_world @ bone.tail_local
            f.write(f"b,{bone.name.replace(',', ';')},{h[0]},{h[1]},{h[2]},"
                    f"{t[0]},{t[1]},{t[2]}\n")
            count += 1
    return count


def _apply_weight_file(meshes: List[bpy.types.Object], path: str) -> None:
    owner = []
    for ob in meshes:
        owner.extend((ob, i) for i in range(len(ob.data.vertices)))
    groups: List[str] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            tokens = line.strip().split(",")
            if tokens[0] == "b":
                name = tokens[1].replace(";", ",")
                groups.append(name)
                for ob in meshes:
                    existing = ob.vertex_groups.get(name)
                    if existing is not None:
                        ob.vertex_groups.remove(existing)
                    ob.vertex_groups.new(name=name)
            elif tokens[0] == "w":
                ob, vert_index = owner[int(tokens[1])]
                ob.vertex_groups[groups[int(tokens[2])]].add(
                    [vert_index], float(tokens[3]), 'REPLACE')


def _parent_meshes(meshes: List[bpy.types.Object], rig: bpy.types.Object,
                   parent_type: str) -> None:
    bpy.ops.object.select_all(action='DESELECT')
    for ob in meshes:
        ob.select_set(True)
    rig.select_set(True)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.parent_set(type=parent_type)


def skin_automatic(meshes: List[bpy.types.Object],
                   rig: bpy.types.Object) -> Tuple[bool, str]:
    """Blender's built-in Automatic Weights (bone heat). The fallback path."""
    try:
        _parent_meshes(meshes, rig, 'ARMATURE_AUTO')
    except RuntimeError as exc:
        return False, f"Automatic Weights failed: {exc}"
    return True, "Skinned with Blender Automatic Weights"


def skin_voxel(meshes: List[bpy.types.Object],
               rig: bpy.types.Object) -> Tuple[bool, str]:
    """Voxel heat diffuse skinning via the vendored solver binary."""
    binary = _binary_path()
    if not binary or not os.path.isfile(binary):
        return False, "Voxel solver binary not found for this platform"

    workdir = tempfile.mkdtemp(prefix="hiho_skin_")
    mesh_txt = os.path.join(workdir, "mesh.txt")
    bone_txt = os.path.join(workdir, "bone.txt")
    weight_txt = os.path.join(workdir, "weight.txt")

    vert_count = _write_mesh_file(meshes, mesh_txt)
    bone_count = _write_bone_file(rig, bone_txt)
    if vert_count == 0 or bone_count == 0:
        return False, f"Nothing to skin ({vert_count} vertices, {bone_count} bones)"

    try:
        os.chmod(binary, 0o755)
        result = subprocess.run(
            [binary, "mesh.txt", "bone.txt", "weight.txt", *SOLVER_ARGS],
            cwd=workdir, capture_output=True, text=True,
            timeout=SOLVER_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        return False, f"Voxel solver timed out after {SOLVER_TIMEOUT_SECONDS}s"
    except OSError as exc:
        return False, f"Voxel solver failed to launch: {exc}"
    if result.returncode != 0 or not os.path.isfile(weight_txt):
        tail = (result.stderr or result.stdout or "").strip()[-200:]
        return False, f"Voxel solver error (exit {result.returncode}): {tail}"

    _apply_weight_file(meshes, weight_txt)
    _parent_meshes(meshes, rig, 'ARMATURE')
    return True, f"Voxel-skinned {vert_count} vertices to {bone_count} bones"
