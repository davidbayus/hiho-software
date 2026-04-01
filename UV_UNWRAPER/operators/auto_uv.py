"""
Auto UV Operators — Three Buttons for Three Shape Types

1. Character — symmetric biped/humanoid (teddy bear surgery)
2. Simple Shape — props, accessories, single objects (crack the walnut)
3. Thingamabob — multi-limbed, asymmetric, weird (the octopus)

Each button runs the same unwrap pipeline but uses a different
seam generation strategy. The kid picks the button that matches
their shape, clicks once, and they're ready to paint.
"""

import bpy
from ..core.seam_generator import (
    generate_seams_character,
    generate_seams_simple,
    generate_seams_thingamabob,
    apply_seams_to_mesh,
)


# ===========================================================================
#  BASE CLASS — shared unwrap/pack logic
# ===========================================================================

class _AutoUVBase(bpy.types.Operator):
    """Base class for all three auto-UV operators. Not registered directly."""

    bl_options = {'REGISTER', 'UNDO'}

    unwrap_method: bpy.props.EnumProperty(
        name="Method",
        description="Which unwrapping algorithm to use",
        items=[
            ('MINIMUM_STRETCH', "Best Quality (SLIM)",
             "Minimum Stretch — best distortion, requires Blender 4.3+"),
            ('ANGLE_BASED', "Standard (ABF)",
             "Angle Based Flattening — works on all Blender versions"),
            ('CONFORMAL', "Fast (Conformal)",
             "Conformal — fastest, may have more stretching"),
        ],
        default='ANGLE_BASED',
    )

    island_margin: bpy.props.FloatProperty(
        name="Island Spacing",
        description="Gap between UV islands (prevents color bleeding when painting)",
        default=0.01,
        min=0.0,
        max=0.1,
        step=1,
    )

    # Subclasses set this to their seam generation function
    _seam_generator = None
    _mode_name = "auto"

    @classmethod
    def poll(cls, context):
        """Only enable the button when a mesh object is selected."""
        obj = context.active_object
        return (
            obj is not None
            and obj.type == 'MESH'
            and context.mode in {'OBJECT', 'EDIT_MESH', 'SCULPT'}
        )

    def execute(self, context):
        """Run the full auto-UV pipeline."""
        obj = context.active_object
        original_mode = context.mode

        if original_mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        try:
            result = self._run_auto_uv(context, obj)
        except Exception as e:
            self.report({'ERROR'}, f"Auto UV failed: {str(e)}")
            self._restore_mode(original_mode)
            return {'CANCELLED'}

        self._restore_mode(original_mode)

        if result:
            self.report({'INFO'}, result)
            return {'FINISHED'}
        else:
            return {'CANCELLED'}

    def _run_auto_uv(self, context, obj):
        """The shared UV generation pipeline."""
        mesh = obj.data
        mesh.update()

        # --- Step 1: Generate seams using the mode-specific generator ---
        seam_edges = self._seam_generator(obj)
        num_seams = apply_seams_to_mesh(obj, seam_edges)
        seam_info = f"{num_seams} smart seams ({self._mode_name})"

        if num_seams == 0:
            self.report({'WARNING'}, "No seams could be generated — mesh may be too simple")
            return None

        # --- Step 2: Create UV map if needed ---
        if not mesh.uv_layers:
            mesh.uv_layers.new(name="AutoUV")
        mesh.uv_layers.active = (
            mesh.uv_layers["AutoUV"] if "AutoUV" in mesh.uv_layers
            else mesh.uv_layers[0]
        )

        # --- Step 3: Unwrap ---
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')

        method = self.unwrap_method
        try:
            bpy.ops.uv.unwrap(method=method, margin=self.island_margin)
        except TypeError:
            if method == 'MINIMUM_STRETCH':
                self.report({'WARNING'},
                    "SLIM not available in this Blender version, using ABF")
                bpy.ops.uv.unwrap(method='ANGLE_BASED', margin=self.island_margin)
            else:
                raise

        # --- Step 4: Average island scale + Pack ---
        try:
            bpy.ops.uv.average_islands_scale()
        except RuntimeError:
            pass

        bpy.ops.uv.pack_islands(margin=self.island_margin)

        bpy.ops.object.mode_set(mode='OBJECT')

        num_islands = self._count_uv_islands(mesh)
        return (
            f"Auto UV complete! {seam_info}, "
            f"{num_islands} UV island{'s' if num_islands != 1 else ''}"
        )

    def _count_uv_islands(self, mesh) -> int:
        """Count actual UV islands by walking UV connectivity."""
        if not mesh.uv_layers.active:
            return 0

        uv_layer = mesh.uv_layers.active.data
        num_loops = len(uv_layer)
        if num_loops == 0:
            return 0

        parent = list(range(num_loops))

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        for poly in mesh.polygons:
            loops = list(poly.loop_indices)
            for i in range(1, len(loops)):
                union(loops[0], loops[i])

        edge_loops = {}
        for poly in mesh.polygons:
            verts = list(poly.vertices)
            loops = list(poly.loop_indices)
            for i in range(len(verts)):
                edge_key = tuple(sorted((verts[i], verts[(i + 1) % len(verts)])))
                edge_loops.setdefault(edge_key, []).append(loops[i])

        seam_edges = set()
        for edge in mesh.edges:
            if edge.use_seam:
                seam_edges.add(tuple(sorted((edge.vertices[0], edge.vertices[1]))))

        for edge_key, loop_list in edge_loops.items():
            if edge_key not in seam_edges and len(loop_list) >= 2:
                for i in range(1, len(loop_list)):
                    union(loop_list[0], loop_list[i])

        islands = set()
        for i in range(num_loops):
            islands.add(find(i))

        return len(islands)

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


# ===========================================================================
#  THE THREE BUTTONS
# ===========================================================================

class KIDBLENDER_OT_auto_uv(_AutoUVBase):
    """Unwrap a symmetric character (biped/humanoid).
    Seams down the back and along inner limbs — like cutting open a stuffed animal."""

    bl_idname = "kidblender.auto_uv"
    bl_label = "Character"
    bl_description = (
        "Best for people, bipeds, and symmetric characters. "
        "Places seams down the back and inner limbs"
    )

    _seam_generator = staticmethod(generate_seams_character)
    _mode_name = "character"


class KIDBLENDER_OT_auto_uv_simple(_AutoUVBase):
    """Unwrap a simple shape (prop, accessory, single object).
    One seam line on the hidden side — like cracking open a walnut."""

    bl_idname = "kidblender.auto_uv_simple"
    bl_label = "Simple Shape"
    bl_description = (
        "Best for props, accessories, weapons, potions, hats, rocks. "
        "Places one seam on the back or bottom"
    )

    _seam_generator = staticmethod(generate_seams_simple)
    _mode_name = "simple"


class KIDBLENDER_OT_auto_uv_thingamabob(_AutoUVBase):
    """Unwrap a complex asymmetric shape (creature, blob, multi-limbed).
    Finds every appendage and seams each one — like unwrapping an octopus."""

    bl_idname = "kidblender.auto_uv_thingamabob"
    bl_label = "Thingamabob"
    bl_description = (
        "Best for creatures, monsters, asymmetric shapes, anything weird. "
        "Finds every appendage and seams it"
    )

    _seam_generator = staticmethod(generate_seams_thingamabob)
    _mode_name = "thingamabob"
