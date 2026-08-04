"""
Face Clusterer — Curvature-Based Seam Generation via Face Clustering

Groups faces into clusters where all faces within a cluster point roughly
the same direction (similar normals). The boundaries between clusters
become seams. This is how Substance Painter's auto-unwrapper works.

The algorithm:
1. Score every edge by dihedral angle (how sharp the bend is)
2. Pick seed faces spread across the mesh (deterministic, not random)
3. Grow each seed into a "chart" by adding neighboring faces,
   preferring faces with low edge cost and similar normals
4. Repeat (Lloyd iteration) until stable
5. Boundaries between charts = seams

The merge threshold slider controls island count:
- Low threshold = many small islands (Smart UV style, good for hard-surface)
- High threshold = few large islands (SP style, good for characters)
"""

import bpy
import bmesh
import math
import heapq
from typing import Dict, List, Set, Tuple
from collections import deque


class PAWRAPPA_OT_face_cluster(bpy.types.Operator):
    """Group faces into clusters and mark boundaries as seams.
    One algorithm that works on any shape — characters, props, creatures, mechanical."""

    bl_idname = "pawrappa.face_cluster"
    bl_label = "Auto Seams"
    bl_description = (
        "Automatically places seams by grouping similar faces together. "
        "Adjust the merge slider: left = more islands, right = fewer islands"
    )
    bl_options = {'REGISTER', 'UNDO'}

    merge_threshold: bpy.props.FloatProperty(
        name="Merge Threshold",
        description=(
            "How aggressively to merge clusters. "
            "Low = many islands (detailed), High = few islands (simple)"
        ),
        default=0.5,
        min=0.05,
        max=0.95,
        step=5,
    )

    normal_weight: bpy.props.FloatProperty(
        name="Normal Sensitivity",
        description=(
            "How much face direction matters when grouping. "
            "Higher = clusters follow surface direction more strictly"
        ),
        default=1.0,
        min=0.1,
        max=3.0,
        step=10,
    )

    concavity_boost: bpy.props.BoolProperty(
        name="Prefer Concave Seams",
        description=(
            "Prefer placing seams in concave creases (armpits, crevices) "
            "where they're less visible"
        ),
        default=True,
    )

    back_bias: bpy.props.BoolProperty(
        name="Hide Seams on Back (+Y)",
        description=(
            "When two seam placements are equally good, prefer the one "
            "facing away from the camera (toward +Y)"
        ),
        default=True,
    )

    iterations: bpy.props.IntProperty(
        name="Refinement Passes",
        description="More passes = cleaner cluster boundaries (slower)",
        default=8,
        min=1,
        max=30,
    )

    @classmethod
    def poll(cls, context):
        """Only works on mesh objects."""
        obj = context.active_object
        return obj is not None and obj.type == 'MESH'

    def execute(self, context):
        """Run the full pipeline: cluster → seams → unwrap → pack."""
        obj = context.active_object
        mesh = obj.data
        original_mode = context.mode

        if original_mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        # --- Phase 1: Cluster faces and mark seams ---
        try:
            seam_result = self._cluster_and_seam(obj)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.report({'ERROR'}, f"Face clustering failed: {str(e)}")
            self._restore_mode(original_mode)
            return {'CANCELLED'}

        # --- Phase 2: Create UV map if needed ---
        if not mesh.uv_layers:
            mesh.uv_layers.new(name="AutoUV")
        if "AutoUV" in mesh.uv_layers:
            mesh.uv_layers.active = mesh.uv_layers["AutoUV"]

        # --- Phase 3: Unwrap using SLIM (best quality) ---
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')

        try:
            bpy.ops.uv.unwrap(method='MINIMUM_STRETCH', margin=0.01)
        except TypeError:
            # SLIM not available — fall back to ABF
            bpy.ops.uv.unwrap(method='ANGLE_BASED', margin=0.01)

        # --- Phase 4: Normalize island scale + pack ---
        try:
            bpy.ops.uv.average_islands_scale()
        except RuntimeError:
            pass

        bpy.ops.uv.pack_islands(margin=0.01)
        bpy.ops.object.mode_set(mode='OBJECT')

        self._restore_mode(original_mode)

        stretch = self._measure_uv_stretch(mesh)
        if stretch is None:
            verdict = ""
        elif stretch < 1.15:
            verdict = " — low stretching, good to paint!"
        elif stretch < 1.45:
            verdict = " — some stretching (usually fine for painting)"
        else:
            verdict = " — a lot of stretching, try the slider further LEFT (more pieces)"

        self.report({'INFO'}, seam_result + verdict)
        return {'FINISHED'}

    def _measure_uv_stretch(self, mesh):
        """Area-weighted mean UV distortion: 1.0 = perfect, higher = stretchier.
        Compares each face's share of UV space against its share of 3D surface."""
        if not mesh.uv_layers.active:
            return None
        uv = mesh.uv_layers.active.data

        areas3d = []
        areas2d = []
        for poly in mesh.polygons:
            pts = [uv[li].uv for li in poly.loop_indices]
            a2 = 0.0
            for i in range(1, len(pts) - 1):
                a, b, c = pts[0], pts[i], pts[i + 1]
                a2 += abs((b.x - a.x) * (c.y - a.y) - (c.x - a.x) * (b.y - a.y)) / 2
            areas2d.append(a2)
            areas3d.append(poly.area)

        total3 = sum(areas3d)
        total2 = sum(areas2d)
        if total3 < 1e-12 or total2 < 1e-12:
            return None

        weighted = 0.0
        for a3, a2 in zip(areas3d, areas2d):
            if a3 < 1e-12:
                continue
            r = (a2 / total2) / (a3 / total3)
            weighted += (max(r, 1.0 / r) if r > 1e-9 else 100.0) * (a3 / total3)
        return weighted

    def _cluster_and_seam(self, obj) -> str:
        """Full pipeline: score edges → cluster faces → extract seams."""
        mesh = obj.data

        bm = bmesh.new()
        bm.from_mesh(mesh)
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()
        bm.verts.ensure_lookup_table()

        num_faces = len(bm.faces)
        if num_faces < 2:
            bm.free()
            return "Mesh too simple to cluster"

        # --- Step 1: Score every edge ---
        edge_costs = self._compute_edge_costs(bm)

        # --- Step 2: Build face adjacency (the dual graph) ---
        face_adj, shared_edge = self._build_face_adjacency(bm)

        # --- Step 3: Determine number of initial clusters ---
        # More faces + lower merge threshold = more clusters
        # Scale: at threshold 0.05 → many clusters, at 0.95 → very few
        base_clusters = max(2, int(math.sqrt(num_faces)))
        num_clusters = max(2, int(base_clusters * (1.0 - self.merge_threshold)))
        num_clusters = min(num_clusters, num_faces)

        # --- Step 4: Pick seed faces (spread across mesh, deterministic) ---
        seeds = self._pick_seeds_deterministic(bm, num_clusters, face_adj)

        # --- Step 5: Cache face data ---
        face_normals = {}
        face_centers = {}
        for face in bm.faces:
            face_normals[face.index] = face.normal.copy()
            face_centers[face.index] = face.calc_center_median().copy()

        # --- Step 6: Lloyd iteration — grow clusters, recompute seeds ---
        labels = {}
        cluster_normals = None
        for iteration in range(self.iterations):
            labels = self._assign_faces_to_seeds(
                bm, seeds, face_adj, shared_edge, edge_costs,
                face_normals, num_faces, cluster_normals
            )

            # Recompute seeds (face nearest to cluster centroid) and each
            # cluster's average normal — comparing candidate faces against
            # the whole cluster's direction (not just the seed face's)
            # keeps charts flatter, which unwraps with less stretch
            seeds = self._recompute_seeds(labels, face_centers, bm)
            cluster_normals = self._compute_cluster_normals(labels, face_normals)

        # --- Step 7: Merge small clusters ---
        labels = self._merge_small_clusters(
            bm, labels, face_adj, shared_edge, edge_costs, min_faces=3
        )

        # --- Step 8: Extract seams from cluster boundaries ---
        seam_count = self._apply_seams_from_clusters(bm, mesh, labels)

        num_islands = len(set(labels.values()))
        bm.free()

        return (
            f"Auto seams: {num_islands} islands, "
            f"{seam_count} seam edges"
        )

    def _compute_edge_costs(self, bm) -> Dict[int, float]:
        """Score every edge: high cost = good seam candidate (hard to cross)."""
        edge_costs = {}

        for edge in bm.edges:
            if edge.is_boundary:
                edge_costs[edge.index] = 100.0
                continue

            if len(edge.link_faces) != 2:
                edge_costs[edge.index] = 0.0
                continue

            if self.concavity_boost:
                angle = edge.calc_face_angle_signed(0.0)
                abs_angle = abs(angle)
                if angle < 0:
                    cost = abs_angle * 1.5
                else:
                    cost = abs_angle
            else:
                cost = edge.calc_face_angle(0.0)

            # Back bias: cluster boundaries (seams) form along HIGH-cost
            # edges, so back-facing edges must cost MORE for seams to
            # prefer the back. Additive, because on smooth surfaces (the
            # very places a hidden seam matters) the dihedral cost is ~0
            # and a multiplier would have no effect.
            if self.back_bias:
                f1, f2 = edge.link_faces
                avg_normal_y = (f1.normal.y + f2.normal.y) / 2.0
                if avg_normal_y > 0:
                    cost += 0.2 * avg_normal_y

            edge_costs[edge.index] = cost

        return edge_costs

    def _build_face_adjacency(
        self, bm
    ) -> Tuple[Dict[int, List[int]], Dict[Tuple[int, int], int]]:
        """Build face neighbor lookup and track which edge connects each pair."""
        face_adj: Dict[int, List[int]] = {f.index: [] for f in bm.faces}
        shared_edge: Dict[Tuple[int, int], int] = {}

        for edge in bm.edges:
            if len(edge.link_faces) == 2:
                f1_idx = edge.link_faces[0].index
                f2_idx = edge.link_faces[1].index
                face_adj[f1_idx].append(f2_idx)
                face_adj[f2_idx].append(f1_idx)
                key = (min(f1_idx, f2_idx), max(f1_idx, f2_idx))
                shared_edge[key] = edge.index

        return face_adj, shared_edge

    def _pick_seeds_deterministic(
        self, bm, num_clusters: int, face_adj: Dict[int, List[int]]
    ) -> List[int]:
        """Pick seed faces spread across the mesh using farthest-point sampling.
        Deterministic: always starts from face 0."""
        num_faces = len(bm.faces)
        if num_clusters >= num_faces:
            return list(range(num_faces))

        # Start with face 0 (deterministic)
        seeds = [0]

        for _ in range(num_clusters - 1):
            dist = self._multi_bfs_distance(seeds, face_adj, num_faces)
            farthest = max(range(num_faces), key=lambda f: dist[f])
            seeds.append(farthest)

        return seeds

    def _multi_bfs_distance(
        self, sources: List[int], face_adj: Dict[int, List[int]], num_faces: int
    ) -> List[int]:
        """BFS distance from nearest source to every face."""
        dist = [-1] * num_faces
        queue = deque()

        for s in sources:
            dist[s] = 0
            queue.append(s)

        while queue:
            current = queue.popleft()
            for neighbor in face_adj.get(current, []):
                if dist[neighbor] == -1:
                    dist[neighbor] = dist[current] + 1
                    queue.append(neighbor)

        # Replace unreachable with 0
        for i in range(num_faces):
            if dist[i] == -1:
                dist[i] = 0

        return dist

    def _assign_faces_to_seeds(
        self,
        bm,
        seeds: List[int],
        face_adj: Dict[int, List[int]],
        shared_edge: Dict[Tuple[int, int], int],
        edge_costs: Dict[int, float],
        face_normals: Dict[int, any],
        num_faces: int,
        cluster_normals: Dict[int, any] = None,
    ) -> Dict[int, int]:
        """Assign every face to the nearest seed using a proper priority queue."""
        normal_w = self.normal_weight

        labels = {}
        cost_to = [float('inf')] * num_faces

        # Priority queue: (cost, tiebreaker, face_index, cluster_id)
        # Tiebreaker ensures deterministic ordering when costs are equal
        heap = []
        counter = 0

        for cluster_id, seed in enumerate(seeds):
            if seed < num_faces:
                cost_to[seed] = 0.0
                heapq.heappush(heap, (0.0, counter, seed, cluster_id))
                counter += 1

        visited = set()

        while heap:
            cost, _, face_idx, cluster_id = heapq.heappop(heap)

            if face_idx in visited:
                continue
            visited.add(face_idx)
            labels[face_idx] = cluster_id

            # Get the cluster's proxy normal — average of the whole cluster
            # from the previous Lloyd pass when available, else the seed face
            seed_normal = None
            if cluster_normals is not None:
                seed_normal = cluster_normals.get(cluster_id)
            if seed_normal is None:
                seed_idx = seeds[cluster_id] if cluster_id < len(seeds) else face_idx
                seed_normal = face_normals.get(seed_idx)
            if seed_normal is None:
                continue

            for neighbor_idx in face_adj.get(face_idx, []):
                if neighbor_idx in visited:
                    continue

                # Edge crossing cost
                pair_key = (
                    min(face_idx, neighbor_idx),
                    max(face_idx, neighbor_idx),
                )
                edge_idx = shared_edge.get(pair_key)
                edge_cost = edge_costs.get(edge_idx, 0.0) if edge_idx is not None else 0.0

                # Normal deviation cost
                neighbor_normal = face_normals.get(neighbor_idx)
                if neighbor_normal is not None:
                    dot = seed_normal.dot(neighbor_normal)
                    dot = max(-1.0, min(1.0, dot))
                    normal_cost = (1.0 - dot) * normal_w
                else:
                    normal_cost = 0.0

                # Sharp edges are expensive to cross → cluster boundaries
                crossing_penalty = edge_cost * 2.0
                total_cost = cost + crossing_penalty + normal_cost

                if total_cost < cost_to[neighbor_idx]:
                    cost_to[neighbor_idx] = total_cost
                    heapq.heappush(heap, (total_cost, counter, neighbor_idx, cluster_id))
                    counter += 1

        # Assign any unvisited faces to nearest cluster
        for face in bm.faces:
            if face.index not in labels:
                for n in face_adj.get(face.index, []):
                    if n in labels:
                        labels[face.index] = labels[n]
                        break
                else:
                    labels[face.index] = 0

        return labels

    def _recompute_seeds(
        self,
        labels: Dict[int, int],
        face_centers: Dict[int, any],
        bm,
    ) -> List[int]:
        """Find the face closest to each cluster's centroid."""
        from mathutils import Vector

        cluster_faces: Dict[int, List[int]] = {}
        for face_idx, cluster_id in labels.items():
            if cluster_id not in cluster_faces:
                cluster_faces[cluster_id] = []
            cluster_faces[cluster_id].append(face_idx)

        new_seeds = []
        for cid in sorted(cluster_faces.keys()):
            faces = cluster_faces[cid]
            if not faces:
                continue

            # Compute centroid
            centroid = Vector((0.0, 0.0, 0.0))
            for f in faces:
                centroid += face_centers[f]
            centroid /= len(faces)

            # Find face closest to centroid
            best_face = min(
                faces,
                key=lambda f: (face_centers[f] - centroid).length_squared,
            )
            new_seeds.append(best_face)

        return new_seeds

    def _compute_cluster_normals(
        self,
        labels: Dict[int, int],
        face_normals: Dict[int, any],
    ) -> Dict[int, any]:
        """Average normal per cluster, keyed to match the next pass's
        cluster ids (position in sorted cluster-id order, same ordering
        as _recompute_seeds)."""
        from mathutils import Vector

        sums: Dict[int, any] = {}
        for face_idx, cluster_id in labels.items():
            n = face_normals.get(face_idx)
            if n is None:
                continue
            if cluster_id not in sums:
                sums[cluster_id] = Vector((0.0, 0.0, 0.0))
            sums[cluster_id] += n

        result = {}
        for position, cid in enumerate(sorted(sums.keys())):
            avg = sums[cid]
            if avg.length > 1e-8:
                result[position] = avg.normalized()
        return result

    def _merge_small_clusters(
        self,
        bm,
        labels: Dict[int, int],
        face_adj: Dict[int, List[int]],
        shared_edge: Dict[Tuple[int, int], int],
        edge_costs: Dict[int, float],
        min_faces: int = 3,
    ) -> Dict[int, int]:
        """Merge clusters that are too small into their best neighbor."""
        changed = True
        max_passes = 50  # Safety limit
        passes = 0

        while changed and passes < max_passes:
            changed = False
            passes += 1

            # Count faces per cluster
            cluster_sizes: Dict[int, int] = {}
            for c in labels.values():
                cluster_sizes[c] = cluster_sizes.get(c, 0) + 1

            for cluster_id, size in list(cluster_sizes.items()):
                if size >= min_faces:
                    continue

                # Find all neighboring clusters and their boundary cost
                neighbor_costs: Dict[int, float] = {}
                cluster_faces = [f for f, c in labels.items() if c == cluster_id]

                for face_idx in cluster_faces:
                    for neighbor_idx in face_adj.get(face_idx, []):
                        neighbor_cluster = labels.get(neighbor_idx)
                        if neighbor_cluster is None or neighbor_cluster == cluster_id:
                            continue

                        pair_key = (
                            min(face_idx, neighbor_idx),
                            max(face_idx, neighbor_idx),
                        )
                        edge_idx = shared_edge.get(pair_key)
                        cost = edge_costs.get(edge_idx, 0.0) if edge_idx is not None else 0.0

                        if neighbor_cluster not in neighbor_costs:
                            neighbor_costs[neighbor_cluster] = 0.0
                        neighbor_costs[neighbor_cluster] += cost

                if not neighbor_costs:
                    continue

                # Merge into the neighbor with lowest boundary cost
                best_neighbor = min(neighbor_costs, key=neighbor_costs.get)
                for face_idx in cluster_faces:
                    labels[face_idx] = best_neighbor
                changed = True

        # Renumber contiguously
        unique = sorted(set(labels.values()))
        remap = {old: new for new, old in enumerate(unique)}
        return {f: remap[c] for f, c in labels.items()}

    def _apply_seams_from_clusters(
        self,
        bm,
        mesh,
        labels: Dict[int, int],
    ) -> int:
        """Mark edges between different clusters as seams."""
        # Clear all seams
        for edge in mesh.edges:
            edge.use_seam = False

        seam_count = 0

        for edge in bm.edges:
            if len(edge.link_faces) != 2:
                continue

            f1_idx = edge.link_faces[0].index
            f2_idx = edge.link_faces[1].index

            c1 = labels.get(f1_idx, -1)
            c2 = labels.get(f2_idx, -1)

            if c1 != c2:
                if edge.index < len(mesh.edges):
                    mesh.edges[edge.index].use_seam = True
                    seam_count += 1

        return seam_count

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
