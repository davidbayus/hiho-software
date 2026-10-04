"""
QUADRE — the engine's steps as plain functions.

Step 1 rebuilds the surface as clean triangles. After that comes one
"layout" per flow map: trace the quad flow, then build the quads. Each
layout works in a folder of its own, so several can exist side by side.

No Blender calls here, only the engine libraries and files on disk.
See QUADRE_PHASE1_DESIGN_2026-10-03.md.
"""

import math
import os
import shutil

from .lib import Quadwild, flow_config_files, satsuma_config_files
from .lib.data import create_default_QRParameters


# Sharp feature detection at 35 degrees — good for catching
# body part transitions (arm meets torso, neck meets head)
SHARP_ANGLE = 35.0

# The Quad Count field is an absolute TARGET face count. QuadWild's own
# density knob is relative to the input mesh's resolution, so a fixed
# setting used to give wildly different results on different meshes
# (bug report: bucket ballooned 43K → 160K faces). Instead we take the
# count the student typed and solve for the density that should hit it.

# Empirical: output faces ≈ K × remeshed_tris / density².
#   2026-07-06 (Blender 5.1.2, sphere/torus): K ≈ 0.42.
#   2026-09-16 (Blender 5.2.0 LTS, Suzanne at two densities + the
#   bug-report bucket, counts 1K–25K): K measured 0.45–0.53, so the
#   old value delivered ~20% more faces than the typed Quad Count.
#   Recalibrated to 0.50 (results now land within ~±10% of the ask).
# Sharp features set a floor (~650 faces on Suzanne, ~1,450 on a
# voxel-remeshed sculpt), so very low counts land above the ask.
QUADWILD_K = 0.50

# Further off the typed count than this, the engine gets one corrected retry
COUNT_TOLERANCE = 0.05


class EngineError(Exception):
    """The engine ran and could not do its job. str(error) is the reason in
    plain words, written to sit inside the operator's "Cleanup failed" message."""


def count_obj_faces(obj_path):
    """Count 'f' lines in an OBJ file (QuadWild's intermediate output)."""
    count = 0
    with open(obj_path, 'r') as f:
        for line in f:
            if line.startswith('f '):
                count += 1
    return count


def rebuild(qw):
    """Step 1: the engine's own clean triangle copy of the shape, with its
    crease list and its own flow map."""
    for stale in (qw.remeshed_path, qw.field_path):
        if os.path.exists(stale):
            os.remove(stale)
    qw.remeshAndField(remesh=True, enableSharp=True, sharpAngle=SHARP_ANGLE)
    # The native stages can report success without writing their result
    # (seen upstream: xtrytofindme/QRemeshify a9afdf1, 2026-08-11). Handing
    # the next stage a missing file is a hard-crash road, so check on disk
    if not os.path.exists(qw.remeshed_path):
        raise EngineError("the engine could not rebuild the surface of this shape")


def layout_folder(qw, index):
    """A folder of its own for one layout, holding the rebuilt surface and
    its crease list. Returns the engine handle for that folder; the caller
    puts a flow map at its field_path."""
    folder = f"{qw.mesh_path_without_ext}_layout_{index}"
    os.makedirs(folder, exist_ok=True)
    side = Quadwild(os.path.join(folder, os.path.basename(qw.mesh_path)))
    # Results are judged by whether their file appeared, so nothing may be
    # left over from an earlier run
    for stale in (side.field_path, side.traced_path, side.output_path, side.output_smoothed_path):
        if os.path.exists(stale):
            os.remove(stale)
    shutil.copyfile(qw.remeshed_path, side.remeshed_path)
    shutil.copyfile(qw.sharp_path, side.sharp_path)
    return side


def layout(qw, target_faces, should_stop=None):
    """Steps 2 and 3 for the flow map in qw's folder: trace the quad flow,
    build the quads, and build them once more if the count lands off.

    Returns the path of the result, or None when should_stop() said to stop
    between the two steps.
    """
    if not qw.trace() or not os.path.exists(qw.traced_path):
        raise EngineError("the engine could not trace quad flow on this shape")
    if should_stop is not None and should_stop():
        return None

    qr_params = create_default_QRParameters()
    lib_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
    qr_params.flow_config_filename = os.path.join(
        lib_dir, flow_config_files["SIMPLE"]
    ).encode()
    qr_params.satsuma_config_filename = os.path.join(
        lib_dir, satsuma_config_files["DEFAULT"]
    ).encode()

    remeshed_tris = count_obj_faces(qw.remeshed_path)
    density = math.sqrt(QUADWILD_K * remeshed_tris / target_faces)
    density = min(max(density, 0.4), 12.0)

    qw.quadrangulate(qr_params, density, 0, True)

    # The native call can fail without raising — ground truth is
    # whether the result file actually appeared
    result_path = qw.output_smoothed_path
    if not os.path.exists(result_path):
        raise EngineError("the engine finished without producing a result")

    # The density formula is an estimate. When the engine lands well
    # off the typed count, correct the density from what it actually
    # delivered and build the quads once more (this step is the
    # quick one), then keep whichever result is closer
    got = count_obj_faces(result_path)
    if (
        got > 0
        and abs(got / target_faces - 1.0) > COUNT_TOLERANCE
        and not (should_stop is not None and should_stop())
    ):
        retry_density = density * math.sqrt(got / target_faces)
        retry_density = min(max(retry_density, 0.4), 12.0)
        if abs(retry_density - density) > 1e-3:
            first_path = result_path + ".first"
            shutil.copyfile(result_path, first_path)
            qw.quadrangulate(qr_params, retry_density, 0, True)
            retry = (
                count_obj_faces(result_path)
                if os.path.exists(result_path) else 0
            )
            if retry == 0 or (
                abs(retry - target_faces) >= abs(got - target_faces)
            ):
                os.replace(first_path, result_path)
    return result_path
