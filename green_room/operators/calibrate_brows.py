"""Brow calibration tool — find which ARKit indices correspond to eyebrow movements.

FOSCAP's blend shape index mapping doesn't follow standard ARKit ordering,
so we can't guess which indices the brow shapes are at. This operator
listens for one packet and prints ALL active blend shape indices (value > 0.05)
to Blender's console (Window → Toggle System Console on Windows,
or check Terminal on Mac).

Usage:
    1. Connect your phone (face tracking must be active)
    2. Make a NEUTRAL face, click "Capture Neutral"
    3. RAISE your eyebrows high, click "Capture Brows Up"
    4. The operator prints which indices spiked — those are the brow shapes
"""

import socket
import struct

import bpy

from ..core.osc_receiver import decode_all_blendshapes


class GREENROOM_OT_calibrate_brows(bpy.types.Operator):
    """Capture one frame of face data and print all active blend shape indices."""

    bl_idname = "greenroom.calibrate_brows"
    bl_label = "Capture Face Snapshot"
    bl_description = "Print all active ARKit indices to console (for finding brow indices)"
    bl_options = {'REGISTER'}

    def execute(self, context):
        settings = context.scene.greenroom
        port = settings.gr_port

        # Quick one-shot UDP listen
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(2.0)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        try:
            sock.bind(('', port))
        except OSError as e:
            self.report({'ERROR'}, f"Can't bind port {port} — is face tracking already running? ({e})")
            sock.close()
            return {'CANCELLED'}

        try:
            raw, _addr = sock.recvfrom(1024)
        except socket.timeout:
            self.report({'ERROR'}, "No face data received — is the phone connected?")
            sock.close()
            return {'CANCELLED'}
        finally:
            sock.close()

        active = decode_all_blendshapes(raw)
        if active is None:
            self.report({'ERROR'}, "Failed to decode packet")
            return {'CANCELLED'}

        # Print to console
        print("\n" + "=" * 50)
        print("FACE SNAPSHOT — Active blend shapes (> 0.05):")
        print("=" * 50)
        for idx in sorted(active.keys()):
            label, value = active[idx]
            mapped = "  ← MAPPED" if label != f"UNKNOWN_{idx}" else "  ← ???"
            print(f"  [{idx:2d}] {value:.3f}  {label}{mapped}")
        print("=" * 50 + "\n")

        self.report({'INFO'}, f"Snapshot: {len(active)} active indices — check console")
        return {'FINISHED'}
