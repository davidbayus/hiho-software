"""
Edge Scorer — Curvature-Based Seam Visualization

Proof-of-concept tool that scores every edge by dihedral angle
(the angle between adjacent face normals) and marks high-scoring
edges as seams. This lets you visually compare against Substance
Painter's seam placement on the same mesh.

Sharp bends score high → good seam candidates (highlighted)
Flat areas score low → bad seam candidates (ignored)
"""

import bpy
import bmesh
import math
from typing import Dict


class PAWRAPPA_OT_edge_score(bpy.types.Operator):
    """Score every edge by curvature and mark sharp edges as seams.
    Use this to visualize where a curvature-based unwrapper would place seams."""

    bl_idname = "pawrappa.edge_score"
    bl_label = "Score Edges"
    bl_description = (
        "Highlights edges where the surface bends sharply. "
        "Compare these against Substance Painter's seam placement"
    )
    bl_options = {'REGISTER', 'UNDO'}

    threshold_degrees: bpy.props.FloatProperty(
        name="Sharpness Threshold (°)",
        description=(
            "Edges sharper than this angle get marked as seams. "
            "Lower = more seams, Higher = fewer seams"
        ),
        default=30.0,
        min=5.0,
        max=120.0,
        step=500,
    )

    concavity_boost: bpy.props.BoolProperty(
        name="Prefer Concave Edges",
        description=(
            "Concave edges (creases, armpits, crevices) are weighted higher "
            "than convex edges. Seams hide better in crevices"
        ),
        default=True,
    )

    @classmethod
    def poll(cls, context):
        """Only works on mesh objects."""
        obj = context.active_object
        return obj is not None and obj.type == 'MESH'

    def execute(self, context):
        """Score all edges and mark sharp ones as seams."""
        obj = context.active_object
        original_mode = context.mode

        if original_mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        try:
            result = self._score_edges(obj)
        except Exception as e:
            self.report({'ERROR'}, f"Edge scoring failed: {str(e)}")
            self._restore_mode(original_mode)
            return {'CANCELLED'}

        self._restore_mode(original_mode)
        self.report({'INFO'}, result)
        return {'FINISHED'}

    def _score_edges(self, obj) -> str:
        """Compute dihedral angles and mark seams."""
        mesh = obj.data

        # Build BMesh for access to calc_face_angle
        bm = bmesh.new()
        bm.from_mesh(mesh)
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()

        threshold_rad = math.radians(self.threshold_degrees)

        # Score every edge
        edge_scores: Dict[int, float] = {}
        total_edges = 0
        boundary_edges = 0
        scored_edges = 0

        for edge in bm.edges:
            total_edges += 1

            # Boundary edges (only one face) — always mark as seams
            if edge.is_boundary:
                edge_scores[edge.index] = math.pi
                boundary_edges += 1
                continue

            # Non-manifold edges (more than 2 faces) — skip
            if len(edge.link_faces) != 2:
                continue

            scored_edges += 1

            if self.concavity_boost:
                # Signed angle: positive = convex, negative = concave
                angle = edge.calc_face_angle_signed(0.0)
                abs_angle = abs(angle)

                # Concave edges get boosted (they're better seam locations)
                # Convex edges get their raw angle
                if angle < 0:
                    # Concave — boost by factor (seams hide in crevices)
                    edge_scores[edge.index] = abs_angle * 1.5
                else:
                    edge_scores[edge.index] = abs_angle
            else:
                # Unsigned — just the raw angle
                angle = edge.calc_face_angle(0.0)
                edge_scores[edge.index] = angle

        # Clear all existing seams
        for edge in mesh.edges:
            edge.use_seam = False

        # Mark edges above threshold as seams
        marked = 0
        for edge in mesh.edges:
            if edge.index in edge_scores:
                if edge_scores[edge.index] >= threshold_rad:
                    edge.use_seam = True
                    marked += 1

        # Stats for the report
        if scored_edges > 0:
            angles_deg = [math.degrees(edge_scores[i]) for i in edge_scores if i < len(mesh.edges)]
            if angles_deg:
                avg_angle = sum(angles_deg) / len(angles_deg)
                max_angle = max(angles_deg)
                min_angle = min(angles_deg)
            else:
                avg_angle = max_angle = min_angle = 0.0
        else:
            avg_angle = max_angle = min_angle = 0.0

        bm.free()

        return (
            f"Scored {scored_edges} edges — "
            f"{marked} marked as seams (>{self.threshold_degrees:.0f}°). "
            f"Range: {min_angle:.1f}°–{max_angle:.1f}°, "
            f"Avg: {avg_angle:.1f}°"
        )

    def _restore_mode(self, original_mode):
        """Try to restore the mode we were in before."""
        try:
            mode_map = {
                'EDIT_MESH': 'EDIT',
                'SCULPT': 'SCULPT',
                'OBJECT': 'OBJECT',
            }
            target = mode_map.get(original_mode, 'OBJECT')
            bpy.ops.object.mode_set(mode=target)
        except RuntimeError:
            pass
