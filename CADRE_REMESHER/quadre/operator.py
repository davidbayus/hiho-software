"""
QUADRE — 'Clean Up My Shape' operator.

One button. Takes a messy sculpt and gives back clean quads.
All presets run through QuadWild-BiMDF with density tuned per preset.

The heavy QuadWild stages run on a worker thread (they are pure ctypes
and never touch bpy) while a modal timer keeps the UI alive and shows
progress. Headless/script calls fall back to the old synchronous path.
See QUADRE_NOFREEZE_DESIGN_2026-07-06.md.

The engine builds one quad layout per flow map, and the layout that
measures best is the one that gets finished and handed back. The engine
itself runs as separate child processes (child.py), so a hang or a crash
in it cannot take Blender down; if that is not possible on a computer,
the same steps run inside Blender as they used to.
See QUADRE_PHASE1_DESIGN_2026-10-03.md.
"""

import os
import math
import re
import shutil
import threading
import time

import bpy
import bmesh
import mathutils
import numpy as np

from . import child, flow, relax, score, stages
from .lib import Quadwild, EngineLoadError
from .stages import SHARP_ANGLE
from .util import bisect, exporter, importer


# ---------- defaults tuned for character work ----------

# Max input triangles before we auto-decimate.
# QRemeshify recommends < 100K. We enforce it so students
# don't wait forever on a 500K mesh.
MAX_INPUT_TRIS = 100_000

# Tri count the auto-decimate aims for — under MAX_INPUT_TRIS with
# headroom, since voxel remeshing overshoots on curvy shapes.
DECIMATE_TARGET_TRIS = 80_000

# A voxel-simplified copy with fewer triangles than this is scraps, not a
# shape (seen: 12 faces from a 287K-triangle open hand)
VOXEL_SCRAPS_TRIS = 2_000

# The finishing pass keeps separate pieces from snapping onto each other.
# Labelling the pieces of the original is plain Python, so it only runs
# when the original is small enough for that to be quick
PIECE_GUARD_MAX_FACES = 150_000


STAGE_LABELS = {
    1: "Step 1 of 3 — rebuilding the surface…",
    2: "Step 2 of 3 — building quad layouts…",
    3: "Step 3 of 3 — squaring up the best layout…",
}


class _Job:
    """Everything the worker thread needs — plain Python, no bpy.

    The worker only touches ctypes calls and file reads; all Blender
    data work happens on the main thread before (prep) and after
    (finish) this job runs.
    """

    def __init__(self, qw, target_faces, quad_count, obj_name,
                 original_location, sym_x, sym_y, n_parts, ref_co, ref_no,
                 engine_matrix, host_dir):
        self.qw = qw
        # The engine runs as child processes until one fails to start;
        # from then on this job runs it inside Blender
        self.use_child = True
        self.host_dir = host_dir
        # Rotation + scale that took the original's own coordinates into
        # the engine's (location is left out and restored at the end)
        self.engine_matrix = engine_matrix
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

        # One layout per flow map; the best one's quads end up here
        self.layouts_total = 0
        self.layouts_done = 0
        self.result_path = None
        # What the finishing pass turns quads toward: Quadre's guide when
        # its maps could be drawn, otherwise the engine's map
        self.flow_path = qw.field_path

        self.stage = 0
        self.stage_started = time.monotonic()
        self.cancel_requested = False
        self.cancelled = False
        self.finished_ok = False
        self.error = None
        self.stuck = False
        self.done = False

    def _enter_stage(self, n):
        self.stage = n
        self.stage_started = time.monotonic()

    def status_line(self):
        elapsed = int(time.monotonic() - self.stage_started)
        line = f"QUADRE: {STAGE_LABELS.get(self.stage, 'working…')} {elapsed}s"
        if self.stage == 2 and self.layouts_total:
            line += f"  ({self.layouts_done} of {self.layouts_total} done)"
        if self.cancel_requested:
            line += "  (stopping…)" if self.use_child else "  (stopping after this step)"
        return line

    def _engine(self, steps, on_done=None):
        """Run engine steps; one outcome each (None = done, else the
        exception that says why not). Child processes side by side where
        that works, otherwise inside Blender one after another."""
        if self.use_child:
            outcomes = child.run_steps(
                steps, self.host_dir, lambda: self.cancel_requested, on_done
            )
            unavailable = [o for o in outcomes if isinstance(o, child.Unavailable)]
            if not unavailable:
                return outcomes
            print(f"QUADRE: running the engine inside Blender ({unavailable[0]})")
            self.use_child = False
            self.layouts_done = 0

        outcomes = []
        for step in steps:
            try:
                qw = Quadwild(step[1])
                if step[0] == 'rebuild':
                    stages.rebuild(qw)
                elif stages.layout(qw, step[2], lambda: self.cancel_requested) is None:
                    raise child.Stopped()
                outcomes.append(None)
            except child.Stopped:
                raise
            except Exception as e:
                outcomes.append(e)
            if on_done is not None:
                on_done()
        return outcomes

    def run(self):
        try:
            self._enter_stage(1)
            failure = self._engine([('rebuild', self.qw.mesh_path)])[0]
            if failure is not None:
                raise failure
            if not os.path.exists(self.qw.remeshed_path):
                raise stages.EngineError(
                    "the engine could not rebuild the surface of this shape"
                )
            if self.cancel_requested:
                raise child.Stopped()

            # One folder per layout: Quadre's own flow maps first, then the
            # map the engine wrote in step 1. If Quadre's maps cannot be
            # drawn, the engine's map alone still gives a result
            names = [name for name, _, _ in flow.MAPS]
            normals_at = None
            sides = []
            try:
                normals_at = flow.normal_lookup(self.ref_co, self.ref_no)
                sides = [stages.layout_folder(self.qw, k) for k in range(len(names))]
                guide_path = sides[0].field_path + ".guide"
                flow.write_flow_fields(
                    self.qw.remeshed_path, self.qw.sharp_path, normals_at,
                    self.target_faces, [side.field_path for side in sides],
                    guide_path,
                )
                self.flow_path = guide_path
            except Exception as e:
                print(f"QUADRE: used the engine's own flow map only ({e})")
                names, normals_at, sides = [], None, []
            engine_side = stages.layout_folder(self.qw, len(sides))
            shutil.copyfile(self.qw.field_path, engine_side.field_path)
            names.append('engine')
            sides.append(engine_side)

            self.layouts_total = len(sides)
            self._enter_stage(2)

            def one_done():
                self.layouts_done += 1

            outcomes = self._engine(
                [('layout', side.mesh_path, self.target_faces) for side in sides],
                one_done,
            )
            if self.cancel_requested:
                raise child.Stopped()

            # One layout failing is not the end: the others still count
            best = None
            failure = None
            notes = []
            for name, side, outcome in zip(names, sides, outcomes):
                result_path = side.output_smoothed_path
                if outcome is None and not os.path.exists(result_path):
                    outcome = stages.EngineError(
                        "the engine finished without producing a result"
                    )
                if outcome is not None:
                    failure = outcome
                    notes.append(f"{name} failed")
                    continue
                total = self._measure(result_path, normals_at)
                notes.append(f"{name} {total:.1f}")
                if best is None or total < best[0]:
                    best = (total, name, result_path)
            if best is None:
                raise failure
            print(f"QUADRE: layouts (loops + corners off, degrees): {', '.join(notes)}; kept {best[1]}")
            self.result_path = best[2]
            self.finished_ok = True

        except child.Stopped:
            self.cancelled = True
        except child.Stuck:
            self.stuck = True
            self.error = "the engine got stuck"
        except Exception as e:
            self.error = str(e)
        finally:
            self.done = True

    def _measure(self, result_path, normals_at):
        """Lower is better: loops off the form plus corners off square. A
        layout that cannot be measured still counts, in last place."""
        if normals_at is None:
            return 0.0
        try:
            measured = score.score_quads(result_path, normals_at)
        except Exception as e:
            print(f"QUADRE: could not measure a layout ({e})")
            measured = None
        if measured is None:
            return float('inf')
        return measured['flow'] + measured['corners']


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

        # The finishing pass pauses the window for a moment, so the status
        # line gets one redraw to say what is happening first
        if job.finished_ok and not job.cancelled and job.stage != 3:
            job._enter_stage(3)
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
                engine_matrix=matrix.to_4x4(),
                host_dir=os.path.dirname(bpy.app.binary_path),
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

            if job.stuck:
                self.report(
                    {'ERROR'},
                    "QUADRE's engine got stuck on this shape and was stopped. "
                    "Blender and your shape are fine. Flat sheets and "
                    "paper-thin shapes can do this: give the shape some "
                    "thickness (Solidify), or try Blender's Voxel Remesh first",
                )
                return {'CANCELLED'}

            if job.error is not None or not job.finished_ok:
                self.report(
                    {'ERROR'},
                    f"Cleanup failed — this shape confused the engine. Try Blender's Voxel Remesh first, or check your shape for holes. ({job.error})",
                )
                return {'CANCELLED'}

            obj = bpy.data.objects.get(job.obj_name)

            # Import the result
            final_mesh = importer.import_mesh(job.result_path)

            # Finishing pass: square the quads up and sit them on the
            # original. If the original is gone or anything goes wrong, the
            # engine's result stands as it is
            if obj is not None:
                try:
                    self._finish_quads(context, job, obj, final_mesh)
                except Exception as e:
                    print(f"QUADRE: skipped the finishing pass ({e})")
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

    def _finish_quads(self, context, job, obj, mesh):
        depsgraph = context.evaluated_depsgraph_get()
        original = obj.evaluated_get(depsgraph)
        to_engine = job.engine_matrix
        to_original = to_engine.inverted()
        normal_to_engine = to_original.to_3x3().transposed()
        facing = []   # +1 / -1 once known: does the engine wind its quads our way?

        # A shape made of separate pieces (Suzanne's eyeballs sit inside
        # her eye sockets): each piece of the result may only snap to the
        # piece of the original it came from, or neighbours swap surfaces
        source_piece = None
        result_piece = None
        piece_match = {}
        polygons = original.data.polygons
        if job.n_parts > 1 and len(polygons) <= PIECE_GUARD_MAX_FACES:
            source_piece = self._face_pieces(
                len(original.data.vertices), [p.vertices[:] for p in polygons]
            )
            faces = [p.vertices[:] for p in mesh.polygons]
            piece_of_face = self._face_pieces(len(mesh.vertices), faces)
            result_piece = {}
            for face, piece in zip(faces, piece_of_face):
                for v in face:
                    result_piece[v] = piece

        def snap(X, indices, normals, max_dist):
            hits = {}
            for i in indices:
                found, loc, nrm, face = original.closest_point_on_mesh(
                    to_original @ mathutils.Vector(X[i])
                )
                if not found:
                    continue
                point = to_engine @ loc
                # Too far to be the same piece of surface — leave it
                if (point - mathutils.Vector(X[i])).length > max_dist:
                    continue
                side = (normal_to_engine @ nrm).dot(mathutils.Vector(normals[i]))
                hits[i] = (point, side, face)
            if not hits:
                return
            if not facing:
                sides = sorted(h[1] for h in hits.values())
                facing.append(1.0 if sides[len(sides) // 2] >= 0 else -1.0)
                if source_piece is not None:
                    votes = {}
                    for i, (_, _, face) in hits.items():
                        tally = votes.setdefault(result_piece.get(i), {})
                        tally[source_piece[face]] = tally.get(source_piece[face], 0) + 1
                    for piece, tally in votes.items():
                        piece_match[piece] = max(tally, key=tally.get)
            for i, (point, side, face) in hits.items():
                # A surface facing the other way is the far side of a thin
                # wall, not the spot this vertex came from
                if side * facing[0] < 0:
                    continue
                if source_piece is not None and (
                    piece_match.get(result_piece.get(i)) != source_piece[face]
                ):
                    continue
                X[i] = point[:]

        # Without the crease and border lines the pass still runs, the way
        # it did before it knew about them
        try:
            lines = relax.load_lines(job.qw, job.sym_x, job.sym_y)
        except Exception as e:
            print(f"QUADRE: finishing pass ran without the crease lines ({e})")
            lines = None
        relax.finish_quads(
            mesh, snap, relax.load_flow(job.qw.remeshed_path, job.flow_path),
            job.sym_x, job.sym_y, lines,
        )

    def _face_pieces(self, n_verts, faces):
        """Connected-piece id for every face (union-find over shared vertices)."""
        parent = list(range(n_verts))

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        for face in faces:
            root = find(face[0])
            for v in face[1:]:
                other = find(v)
                if other != root:
                    parent[other] = root
        return [find(face[0]) for face in faces]

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
        """Simplify a temporary copy of an oversized mesh down to the tri
        budget. Watertight shapes are voxel-remeshed (fast); open shapes
        are collapse-decimated, because voxel remeshing turns an open shell
        into scraps."""
        temp_mesh = bpy.data.meshes.new_from_object(
            evaluated_obj, preserve_all_data_layers=False, depsgraph=depsgraph
        )
        temp_obj = bpy.data.objects.new("_quadre_decimate_tmp", temp_mesh)
        bpy.context.collection.objects.link(temp_obj)

        tris_before = sum(len(p.vertices) - 2 for p in temp_mesh.polygons)
        area = sum(p.area for p in temp_mesh.polygons)
        # Voxel remeshing yields roughly 2 triangles per voxel-sized
        # square of surface, so: voxel = sqrt(area * 2 / target_tris).
        # A fixed size can EXPLODE the count on larger meshes
        voxel = math.sqrt(area * 2.0 / DECIMATE_TARGET_TRIS) if area > 0 else 0.02

        # Thin-wall check (THIN_WALL_RESEARCH_2026-07-06): a voxel bigger
        # than half the wall can't see the cavity between two walls and
        # silently fuses them (measured 34% volume loss). Characteristic
        # wall ≈ 2·volume/area — only meaningful on a closed mesh
        is_closed = False
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
            voxel_ok = False
            if is_closed:
                for _ in range(3):
                    mod = temp_obj.modifiers.new("_quadre_decimate", 'REMESH')
                    mod.mode = 'VOXEL'
                    mod.voxel_size = voxel
                    bpy.ops.object.modifier_apply(modifier=mod.name)
                    tris = sum(len(p.vertices) - 2 for p in temp_obj.data.polygons)
                    if tris <= MAX_INPUT_TRIS:
                        break
                    voxel *= 1.5
                voxel_ok = tris >= VOXEL_SCRAPS_TRIS

            if not voxel_ok:
                # An open shape (a hand cut at the wrist, a head with no
                # neck cap) has no inside for the voxel grid to fill: it
                # came back as two 6-face scraps on the benchmark hand, and
                # the engine never returns from scraps (2026-10-02). Start
                # again from the real surface and collapse edges instead —
                # slower, but it keeps open borders where they are
                if is_closed:
                    scraps = temp_obj.data
                    temp_obj.data = bpy.data.meshes.new_from_object(
                        evaluated_obj, preserve_all_data_layers=False, depsgraph=depsgraph
                    )
                    bpy.data.meshes.remove(scraps)
                mod = temp_obj.modifiers.new("_quadre_decimate", 'DECIMATE')
                mod.decimate_type = 'COLLAPSE'
                mod.ratio = min(1.0, DECIMATE_TARGET_TRIS / max(tris_before, 1))
                mod.use_collapse_triangulate = True
                bpy.ops.object.modifier_apply(modifier=mod.name)
        finally:
            bpy.context.view_layer.objects.active = prev_active
        return temp_obj
