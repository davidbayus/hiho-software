"""QUADRE — Bisect mesh for symmetry support."""

import bmesh


def bisect_on_axes(bm: bmesh.types.BMesh, xaxis: bool, yaxis: bool, zaxis: bool):
    """Bisect mesh on specified axes, removing negative-side geometry for mirroring."""

    if xaxis:
        bmesh.ops.bisect_plane(
            bm,
            geom=[v for v in bm.verts] + [e for e in bm.edges] + [f for f in bm.faces],
            dist=0.0001,
            plane_co=(0, 0, 0),
            plane_no=(1, 0, 0),
            use_snap_center=False,
            clear_outer=False,
            clear_inner=True,
        )

    if yaxis:
        bmesh.ops.bisect_plane(
            bm,
            geom=[v for v in bm.verts] + [e for e in bm.edges] + [f for f in bm.faces],
            dist=0.0001,
            plane_co=(0, 0, 0),
            plane_no=(0, 1, 0),
            use_snap_center=False,
            clear_outer=False,
            clear_inner=True,
        )

    if zaxis:
        bmesh.ops.bisect_plane(
            bm,
            geom=[v for v in bm.verts] + [e for e in bm.edges] + [f for f in bm.faces],
            dist=0.0001,
            plane_co=(0, 0, 0),
            plane_no=(0, 0, 1),
            use_snap_center=False,
            clear_outer=False,
            clear_inner=True,
        )
