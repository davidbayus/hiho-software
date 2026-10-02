"""
QUADRE — 'Clean Up My Shape' operator.

One button. Takes a messy sculpt and gives back clean quads.
All presets run through QuadWild-BiMDF with density tuned per preset.

The heavy QuadWild stages run on a worker thread (they are pure ctypes
and never touch bpy) while a modal timer keeps the UI alive and shows
progress. Headless/script calls fall back to the old synchronous path.
See QUADRE_NOFREEZE_DESIGN_2026-07-06.md.
"""

import os
import math
import re
import threading
import time

import bpy
import bmesh
import mathutils
import numpy as np

from . import flow
from .lib import (
    Quadwild, QuadreException, EngineLoadError,
    flow_config_files, satsuma_config_files,
)
from .lib.data import create_default_QRParameters
from .util import bisect, exporter, importer


# ---------- defaults tuned for character work ----------

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

# Max input triangles before we auto-decimate.
# QRemeshify recommends < 100K. We enforce it so students
# don't wait forever on a 500K mesh.
MAX_INPUT_TRIS = 100_000

# Tri count the auto-decimate aims for — under MAX_INPUT_TRIS with
# headroom, since voxel remeshing overshoots on curvy shapes.
DECIMATE_TARGET_TRIS = 80_000


STAGE_LABELS = {
    1: "Step 1 of 3 — rebuilding the surface…",
    2: "Step 2 of 3 — tracing quad flow…",
    3: "Step 3 of 3 — building the final quads…",
}


class _Job:
    """Everything the worker thread needs — plain Python, no bpy.

    The worker only touches ctypes calls and file reads; all Blender
    data work happens on the main thread before (prep) and after
    (finish) this job runs.
    """

    def __init__(self, qw, target_faces, quad_count, obj_name,
                 original_location, sym_x, sym_y, n_parts, ref_co, ref_no):
        self.qw = qw
        # Positions + normals of the mesh handed to the engine — what the
        # flow map reads the shape's curvature from
        self.ref_co = ref_co
        self.ref_no = ref_no
        self.target_faces = target_faces   # what the engine aims for
        self.quad_count = quad_count       # what the student typed
        self.obj_name = obj_name
        self.original_location = original_location
        self.sym_x = sym_x
        self.sym_y = sym_y
        self.n_parts = n_parts

        self.stage = 0
        self.stage_started = time.monotonic()
        self.cancel_requested = False
        self.cancelled = False
        self.finished_ok = False
        self.error = None
        self.done = False

    def _enter_stage(self, n):
        self.stage = n
        self.stage_started = time.monotonic()

    def status_line(self):
        elapsed = int(time.monotonic() - self.stage_started)
        line = f"QUADRE: {STAGE_LABELS.get(self.stage, 'working…')} {elapsed}s"
        if self.cancel_requested:
            line += "  (stopping after this step)"
        return line

    def run(self):
        try:
            self._enter_stage(1)
            self.qw.remeshAndField(
                remesh=True, enableSharp=True, sharpAngle=SHARP_ANGLE
            )
            # The native stages can report success without writing their
            # result (seen upstream: xtrytofindme/QRemeshify a9afdf1,
            # 2026-08-11). Handing the next stage a missing file is a
            # hard-crash road, so check on disk between stages
            if not os.path.exists(self.qw.remeshed_path):
                self.error = "the engine could not rebuild the surface of this shape"
                return
            if self.cancel_requested:
                self.cancelled = True
                return

            # Swap in Quadre's own flow map. The engine's map is already on
            # disk, so any failure here just leaves that one in place
            try:
                flow.write_flow_field(
                    self.qw, self.ref_co, self.ref_no, self.target_faces
                )
            except Exception as e:
                print(f"QUADRE: kept the engine's own flow map ({e})")

            self._enter_stage(2)
            if not self.qw.trace() or not os.path.exists(self.qw.traced_path):
                self.error = "the engine could not trace quad flow on this shape"
                return
            if self.cancel_requested:
                self.cancelled = True
                return

            self._enter_stage(3)
            qr_params = create_default_QRParameters()
            lib_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
            qr_params.flow_config_filename = os.path.join(
                lib_dir, flow_config_files["SIMPLE"]
            ).encode()
            qr_params.satsuma_config_filename = os.path.join(
                lib_dir, satsuma_config_files["DEFAULT"]
            ).encode()

            remeshed_tris = _count_obj_faces(self.qw.remeshed_path)
            density = math.sqrt(QUADWILD_K * remeshed_tris / self.target_faces)
            density = min(max(density, 0.4), 12.0)

            self.qw.quadrangulate(qr_params, density, 0, True)

            # The native call can fail without raising — ground truth is
            # whether the result file actually appeared
            if not os.path.exists(self.qw.output_smoothed_path):
                self.error = "the engine finished without producing a result"
                return
            self.finished_ok = True

        except Exception as e:
            self.error = str(e)
        finally:
            self.done = True


def _count_obj_faces(obj_path):
    """Count 'f' lines in an OBJ file (QuadWild's intermediate output)."""
    count = 0
    with open(obj_path, 'r') as f:
        for line in f:
            if line.startswith('f '):
                count += 1
    return count


class QUADRE_OT_cleanup(bpy.types.Operator):
    """Clean up your shape — turns messy geometry into clean quads ready for UV, sculpting, and rigging"""
    bl_idname = "quadre.cleanup"
    bl_label = "Clean Up My Shape"
    bl_options = {'REGISTER', 'UNDO'}

    # The single running job, if any — read by the panel for its status line
    active_job = None

    _timer = None
    _thread = None

    @classmethod
    def poll(cls, context):
        if cls.active_job is not None:
            return False
        obj = context.active_object
        return obj is not None and obj.type == 'MESH' and context.mode == 'OBJECT'

    # ---------- entry points ----------

    def invoke(self, context, event):
        if context.window is None:
            return self.execute(context)

        job = self._prep(context)
        if job is None:
            return {'CANCELLED'}

        QUADRE_OT_cleanup.active_job = job
        self._thread = threading.Thread(target=job.run, daemon=True)
        self._thread.start()

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.25, window=context.window)
        wm.modal_handler_add(self)
        context.workspace.status_text_set(job.status_line())
        return {'RUNNING_MODAL'}

    def execute(self, context):
        # Synchronous path — scripts and --background get the same
        # blocking behavior as before
        job = self._prep(context)
        if job is None:
            return {'CANCELLED'}
        job.run()
        return self._finish(context, job)

    def modal(self, context, event):
        job = QUADRE_OT_cleanup.active_job

        if event.type == 'ESC' and event.value == 'PRESS':
            job.cancel_requested = True
            return {'RUNNING_MODAL'}

        if event.type != 'TIMER':
            # Let every other event through — the student keeps working
            return {'PASS_THROUGH'}

        if not job.done:
            context.workspace.status_text_set(job.status_line())
            self._tag_redraw(context)
            return {'RUNNING_MODAL'}

        self._thread.join()
        context.window_manager.event_timer_remove(self._timer)
        context.workspace.status_text_set(None)
        self._timer = None
        self._thread = None
        result = self._finish(context, job)
        self._tag_redraw(context)
        return result

    def _tag_redraw(self, context):
        for window in context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()

    # ---------- phase 1: prep (main thread, all bpy work) ----------

    def _prep(self, context):
        """Everything that touches Blender data, ending with the OBJ export.
        Returns a ready-to-run _Job, or None after reporting an error."""
        props = context.scene.kb_quadre
        obj = context.active_object

        # Honest interim answer to the native-crash risk: a rare engine
        # crash takes unsaved work with it, so nudge — never block
        if bpy.data.is_dirty:
            self.report({'INFO'}, "Tip: save your file first — just in case")

        if len(obj.data.polygons) == 0:
            self.report({'ERROR'}, "This shape has no faces — nothing to clean up")
            return None

        original_location = obj.location.copy()

        # Build temp file path
        mesh_filename = "".join(c if c not in "\\/:*?<>|" else "_" for c in obj.name).strip()
        mesh_filepath = os.path.join(bpy.app.tempdir, f"{mesh_filename}.obj")

        bm = None
        evaluated_obj = None
        temp_obj = None

        try:
            # Loads the native engine — on a fresh Mac install this is where
            # Gatekeeper says no, so it must fail with a friendly message
            # before any heavy mesh work starts
            qw = Quadwild(mesh_filepath)

            # Evaluate mesh with modifiers applied
            depsgraph = bpy.context.evaluated_depsgraph_get()
            evaluated_obj = obj.evaluated_get(depsgraph)
            mesh = evaluated_obj.to_mesh()

            # If the shape is too dense, simplify a temporary COPY —
            # the student's original mesh is never modified
            tri_count = sum(len(p.vertices) - 2 for p in mesh.polygons)
            simplified = tri_count > MAX_INPUT_TRIS
            if simplified:
                self.report({'INFO'}, f"Shape has {tri_count:,} triangles — simplifying a copy first...")
                temp_obj = self._make_decimated_copy(evaluated_obj, depsgraph)
                source_mesh = temp_obj.data
            else:
                source_mesh = mesh

            bm = bmesh.new()
            bm.from_mesh(source_mesh)

            # Preflight: stray edges/points confuse QuadWild — drop them
            # from our working copy, and note disconnected pieces so the
            # student knows why a result might look off
            self._remove_loose_geometry(bm)
            if len(bm.faces) == 0:
                self.report({'ERROR'}, "This shape has no solid surfaces — nothing to clean up")
                return None
            n_parts = self._count_connected_parts(bm)

            # Apply rotation and scale (but not location — we restore that later)
            if evaluated_obj.rotation_mode == 'QUATERNION':
                matrix = mathutils.Matrix.LocRotScale(
                    None, evaluated_obj.rotation_quaternion, evaluated_obj.scale
                )
            else:
                matrix = mathutils.Matrix.LocRotScale(
                    None, evaluated_obj.rotation_euler, evaluated_obj.scale
                )
            bmesh.ops.transform(bm, matrix=matrix, verts=bm.verts)

            # Symmetry — bisect on chosen axes so QuadWild produces
            # symmetrical quad flow, then mirror the result back
            sym_x = props.symmetry_x
            sym_y = props.symmetry_y
            if sym_x or sym_y:
                bisect.bisect_on_axes(bm, sym_x, sym_y, False)
                # A shape sitting entirely to one side of its center loses
                # everything here — exporting an empty mesh sends the native
                # engine down its hard-crash road
                if len(bm.faces) == 0:
                    self.report(
                        {'ERROR'},
                        "Symmetry removed everything — your shape sits to one "
                        "side of its center. Turn off Symmetry, or use Object "
                        "→ Set Origin → Origin to Geometry, then try again",
                    )
                    return None

            # Mark sharp edges from angle threshold, seams, material boundaries.
            # The angle test only runs on the student's own geometry: the
            # simplified copy is covered in short false creases, and the
            # engine bends the quad flow around every one of them (measured
            # 2026-10-02 on the Chibi sculpt: 112 poles with them, 48 without)
            face_set_layer = bm.faces.layers.int.get('.sculpt_face_set')
            bm.edges.ensure_lookup_table()
            for edge in bm.edges:
                is_sharp = (
                    not simplified
                    and math.degrees(edge.calc_face_angle(0)) > SHARP_ANGLE
                )
                is_material_boundary = (
                    len(edge.link_faces) > 1 and
                    edge.link_faces[0].material_index != edge.link_faces[1].material_index
                )
                is_face_set_boundary = (
                    face_set_layer is not None and
                    len(edge.link_faces) > 1 and
                    edge.link_faces[0][face_set_layer] != edge.link_faces[1][face_set_layer]
                )

                if is_sharp or edge.is_boundary or edge.seam or is_material_boundary or is_face_set_boundary:
                    edge.smooth = False

            # Triangulate for QuadWild
            bmesh.ops.triangulate(bm, faces=bm.faces, quad_method='SHORT_EDGE', ngon_method='BEAUTY')

            bm.normal_update()
            ref_co = np.array([v.co[:] for v in bm.verts])
            ref_no = np.array([v.normal[:] for v in bm.verts])

            # Export
            exporter.export_mesh(bm, mesh_filepath)
            exporter.export_sharp_features(bm, qw.sharp_path, SHARP_ANGLE)

            # The typed Quad Count is for the WHOLE shape. With symmetry on
            # the engine only ever sees one half (or quarter) and the mirror
            # step doubles the result afterwards, so the half must aim for
            # half the count (measured 2026-09-16: without this, X symmetry
            # delivered ~2.7× the typed number). The worker solves for the
            # density once the remeshed tri count exists
            sym_divisor = (2 if sym_x else 1) * (2 if sym_y else 1)
            target_faces = max(props.quad_count // sym_divisor, 1)

            return _Job(
                qw=qw,
                target_faces=target_faces,
                quad_count=props.quad_count,
                obj_name=obj.name,
                original_location=original_location,
                sym_x=sym_x,
                sym_y=sym_y,
                n_parts=n_parts,
                ref_co=ref_co,
                ref_no=ref_no,
            )

        except EngineLoadError as e:
            self.report({'ERROR'}, str(e))
            return None

        except Exception as e:
            self.report({'ERROR'}, f"Cleanup failed — this shape confused the engine. Try Blender's Voxel Remesh first, or check your shape for holes. ({e})")
            return None

        finally:
            if bm is not None:
                bm.free()
            if evaluated_obj is not None:
                evaluated_obj.to_mesh_clear()
            if temp_obj is not None:
                temp_mesh = temp_obj.data
                bpy.data.objects.remove(temp_obj)
                bpy.data.meshes.remove(temp_mesh)

    # ---------- phase 3: finish (main thread, all bpy work) ----------

    def _finish(self, context, job):
        QUADRE_OT_cleanup.active_job = None
        try:
            if job.cancelled:
                self.report({'INFO'}, "Cancelled — your shape is untouched")
                return {'CANCELLED'}

            if job.error is not None or not job.finished_ok:
                self.report(
                    {'ERROR'},
                    f"Cleanup failed — this shape confused the engine. Try Blender's Voxel Remesh first, or check your shape for holes. ({job.error})",
                )
                return {'CANCELLED'}

            obj = bpy.data.objects.get(job.obj_name)

            # Import the result
            final_mesh = importer.import_mesh(job.qw.output_smoothed_path)
            # Re-cleaning a result should yield X_clean.001 (Blender's own
            # numbering), never X_clean_clean
            m = re.match(r"^(.*_clean)(\.\d+)?$", job.obj_name)
            result_name = m.group(1) if m else f"{job.obj_name}_clean"
            final_obj = bpy.data.objects.new(result_name, final_mesh)
            context.collection.objects.link(final_obj)
            context.view_layer.objects.active = final_obj
            final_obj.select_set(True)
            final_obj.location = job.original_location

            # If symmetry was used, mirror the mesh geometry back to a
            # complete solid object — no modifiers left behind
            if job.sym_x or job.sym_y:
                self._mirror_geometry(final_obj, job.sym_x, job.sym_y)

            # Hide the original (it may have been deleted mid-run — that's fine)
            if obj is not None:
                obj.hide_set(True)
                obj.select_set(False)

            # The count is now a promise the student typed, so say how
            # close the engine landed — it aims for the number, never hits
            # it exactly, and sharp features can hold it above the target
            face_count = len(final_obj.data.polygons)
            summary = (
                f"Done! Clean shape has {face_count:,} faces "
                f"(you asked for {job.quad_count:,})"
            )
            if job.n_parts > 1:
                self.report(
                    {'WARNING'},
                    f"{summary}. Heads up: your shape was {job.n_parts} separate "
                    f"pieces — Quadre works best on one connected piece, so check "
                    f"the result where pieces meet",
                )
            else:
                self.report({'INFO'}, summary)
            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"Cleanup failed — this shape confused the engine. Try Blender's Voxel Remesh first, or check your shape for holes. ({e})")
            return {'CANCELLED'}

        finally:
            job.qw = None

    def _mirror_geometry(self, obj, x: bool, y: bool):
        """Mirror mesh geometry and merge — produces a solid complete mesh, no modifiers."""
        mirror = obj.modifiers.new("_quadre_mirror", 'MIRROR')
        mirror.use_axis[0] = x
        mirror.use_axis[1] = y
        mirror.use_clip = True
        mirror.merge_threshold = 0.001
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.modifier_apply(modifier=mirror.name)

    def _remove_loose_geometry(self, bm):
        """Remove wire edges and stray vertices from the working copy."""
        for edge in [e for e in bm.edges if e.is_wire]:
            bm.edges.remove(edge)
        for vert in [v for v in bm.verts if not v.link_faces]:
            bm.verts.remove(vert)

    def _count_connected_parts(self, bm):
        """Count disconnected pieces (islands) in the mesh."""
        bm.verts.index_update()
        seen = set()
        parts = 0
        for v in bm.verts:
            if v.index in seen:
                continue
            parts += 1
            stack = [v]
            while stack:
                cur = stack.pop()
                if cur.index in seen:
                    continue
                seen.add(cur.index)
                for e in cur.link_edges:
                    other = e.other_vert(cur)
                    if other.index not in seen:
                        stack.append(other)
        return parts

    def _make_decimated_copy(self, evaluated_obj, depsgraph):
        """Voxel-remesh a temporary copy of an oversized mesh down to the
        tri budget. Voxel size is computed from the mesh's actual surface
        area — a fixed size can EXPLODE the count on larger meshes."""
        temp_mesh = bpy.data.meshes.new_from_object(
            evaluated_obj, preserve_all_data_layers=False, depsgraph=depsgraph
        )
        temp_obj = bpy.data.objects.new("_quadre_decimate_tmp", temp_mesh)
        bpy.context.collection.objects.link(temp_obj)

        area = sum(p.area for p in temp_mesh.polygons)
        # Voxel remeshing yields roughly 2 triangles per voxel-sized
        # square of surface, so: voxel = sqrt(area * 2 / target_tris)
        voxel = math.sqrt(area * 2.0 / DECIMATE_TARGET_TRIS) if area > 0 else 0.02

        # Thin-wall check (THIN_WALL_RESEARCH_2026-07-06): a voxel bigger
        # than half the wall can't see the cavity between two walls and
        # silently fuses them (measured 34% volume loss). Characteristic
        # wall ≈ 2·volume/area — only meaningful on a closed mesh
        if area > 0:
            bm_check = bmesh.new()
            bm_check.from_mesh(temp_mesh)
            is_closed = all(not e.is_boundary for e in bm_check.edges)
            if is_closed:
                thickness = 2.0 * abs(bm_check.calc_volume(signed=True)) / area
                if voxel > thickness / 2.0:
                    self.report(
                        {'WARNING'},
                        "Your shape is very dense and has thin walls — the "
                        "automatic simplify step may crush the thin parts. If "
                        "the result looks melted or solid where it should be "
                        "hollow, simplify your sculpt yourself first (Remesh "
                        "at a small voxel size), then run Quadre again",
                    )
            bm_check.free()

        prev_active = bpy.context.view_layer.objects.active
        bpy.context.view_layer.objects.active = temp_obj
        try:
            for _ in range(3):
                mod = temp_obj.modifiers.new("_quadre_decimate", 'REMESH')
                mod.mode = 'VOXEL'
                mod.voxel_size = voxel
                bpy.ops.object.modifier_apply(modifier=mod.name)
                tris = sum(len(p.vertices) - 2 for p in temp_obj.data.polygons)
                if tris <= MAX_INPUT_TRIS:
                    break
                voxel *= 1.5
        finally:
            bpy.context.view_layer.objects.active = prev_active
        return temp_obj
