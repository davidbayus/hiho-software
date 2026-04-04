"""OSC receiver for Live Link Face data.

Forked from FOSCAP 1.0.0 (GPL-3.0-or-later)
Original authors: Will Anderson, Francesco Siddi (Blender Foundation)

Receives ARKit face tracking data from the Live Link Face iOS app
over UDP and applies it to shape keys on a dummy mesh in Blender.
"""

import socket
import struct
import threading
import time

import bpy
import mathutils


# The 13 active ARKit shape keys used by puppet templates.
# Maps Live Link Face array index -> shape key name on the dummy mesh.
BLENDSHAPE_MAP = {
    2: 'eyeLookInRight',
    3: 'eyeLookInLeft',
    4: 'eyeLookOutRight',
    5: 'eyeLookOutLeft',
    19: 'mouthFunnel',
    20: 'mouthPucker',
    23: 'mouthSmileRight',
    27: 'mouthClose',
    37: 'jawOpen',
    41: 'eyeBlinkLeft',
    42: 'eyeBlinkRight',
    43: 'eyeWideLeft',
    44: 'eyeWideRight',
}

# Name of the hidden mesh that receives shape key data from the phone
DUMMY_MESH_NAME = "ARKitShapeKeys.Dummy"


def ensure_dummy_mesh():
    """Create the ARKitShapeKeys.Dummy mesh if it doesn't exist.

    This hidden mesh receives face tracking data from the phone.
    Its shape key values drive the puppet's geometry nodes inputs
    via scripted expressions.
    """
    if DUMMY_MESH_NAME in bpy.data.objects:
        return bpy.data.objects[DUMMY_MESH_NAME]

    mesh = bpy.data.meshes.new(DUMMY_MESH_NAME)
    obj = bpy.data.objects.new(DUMMY_MESH_NAME, mesh)
    bpy.context.collection.objects.link(obj)

    # Minimal geometry — single vertex
    mesh.from_pydata([(0, 0, 0)], [], [])

    # Basis shape key (required before adding others)
    obj.shape_key_add(name='Basis')

    # Add one shape key per active ARKit blend shape
    for name in sorted(set(BLENDSHAPE_MAP.values())):
        obj.shape_key_add(name=name)

    # Hide it — students never need to see this
    obj.hide_viewport = True
    obj.hide_render = True
    obj.hide_select = True

    return obj


def decode_live_link_face(raw_bytes):
    """Decode a binary Live Link Face UDP packet.

    The packet contains 61 floats: 52 ARKit blend shape weights,
    3 head rotation values, 3 left eye rotation values, and
    3 right eye rotation values.

    Returns a list of tuples, or None on failure.
    """
    try:
        name_length = struct.unpack('!i', raw_bytes[41:45])[0]
        name_end = 45 + name_length

        if len(raw_bytes) <= name_end + 16:
            return None

        _frame, _subframe, _fps, _denom, count = struct.unpack(
            "!if2ib", raw_bytes[name_end:name_end + 17]
        )

        if count != 61:
            return None

        data = struct.unpack("!61f", raw_bytes[name_end + 17:])
    except (struct.error, IndexError):
        return None

    result = []

    # Blend shape weights (indices 0-51)
    for i in range(52):
        if i in BLENDSHAPE_MAP:
            result.append(('shape', BLENDSHAPE_MAP[i], data[i]))

    # Head rotation (indices 52-54, axes swapped per FOSCAP)
    result.append(('head_rotation', [-data[53], -data[52], -data[54]]))

    return result


class OSCReceiver:
    """Threaded UDP receiver for Live Link Face data.

    Usage:
        receiver = OSCReceiver()
        receiver.start(port=11111)
        # ... face tracking data flows to dummy mesh shape keys ...
        receiver.stop()
    """

    def __init__(self):
        self._thread = None
        self._sock = None
        self._running = False
        self._port = 11111
        self._pending = {}
        self._latest = {}
        self._lock = threading.Lock()
        self._last_packet_time = 0.0
        self._last_redraw_time = 0.0
        self._target_armature = None
        self._target_bone = None

    @property
    def is_running(self):
        return self._running

    @property
    def is_receiving(self):
        """True if we got face data in the last 2 seconds."""
        return self._running and (time.time() - self._last_packet_time) < 2.0

    @property
    def port(self):
        return self._port

    def get_latest_values(self):
        """Snapshot of latest shape key values for UI display."""
        with self._lock:
            return dict(self._latest)

    def start(self, port=11111, target_armature=None, target_bone=None):
        """Start listening for face tracking data.

        Returns True if started successfully, False on error (e.g. port in use).
        """
        if self._running:
            return True

        self._port = port
        self._target_armature = target_armature
        self._target_bone = target_bone

        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            self._sock.bind(('0.0.0.0', port))
        except OSError:
            self._sock.close()
            self._sock = None
            return False

        self._running = True
        self._thread = threading.Thread(target=self._listen, daemon=True)
        self._thread.start()

        if not bpy.app.timers.is_registered(self._apply_updates):
            bpy.app.timers.register(self._apply_updates)

        return True

    def stop(self):
        """Stop listening and clean up."""
        self._running = False

        if self._sock:
            self._sock.close()
            self._sock = None

        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None

        with self._lock:
            self._pending.clear()
            self._latest.clear()

        if bpy.app.timers.is_registered(self._apply_updates):
            bpy.app.timers.unregister(self._apply_updates)

    def _listen(self):
        """Background thread: receive and decode UDP packets.

        Only keeps the latest value for each shape key and head rotation.
        Stale frames are discarded — we only care about the newest data.
        """
        while self._running:
            try:
                raw, _addr = self._sock.recvfrom(1024)
                if raw:
                    decoded = decode_live_link_face(raw)
                    if decoded:
                        self._last_packet_time = time.time()
                        with self._lock:
                            for entry in decoded:
                                if entry[0] == 'shape':
                                    # Overwrite — only latest value matters
                                    self._pending[entry[1]] = entry[2]
                                    self._latest[entry[1]] = entry[2]
                                elif entry[0] == 'head_rotation':
                                    self._pending['_head_rotation'] = entry[1]
            except OSError:
                break

    def _apply_updates(self):
        """Timer callback: push pending data to Blender objects (main thread).

        Only applies the latest value for each shape key — stale frames
        from the pending dict have already been overwritten by _listen().
        """
        if not self._running:
            return None  # Unregister timer

        dummy = bpy.data.objects.get(DUMMY_MESH_NAME)
        if not dummy or not dummy.data.shape_keys:
            return 0.01

        with self._lock:
            updates = dict(self._pending)
            self._pending.clear()

        if not updates:
            return 0.01

        key_blocks = dummy.data.shape_keys.key_blocks

        # Apply shape key values (each key appears once — latest value only)
        for name, value in updates.items():
            if name == '_head_rotation':
                continue
            kb = key_blocks.get(name)
            if kb:
                kb.value = value

        # Apply head rotation
        head_euler = updates.get('_head_rotation')
        if head_euler and self._target_armature and self._target_bone:
            arm = self._target_armature
            if arm.type == 'ARMATURE':
                bone = arm.pose.bones.get(self._target_bone)
                if bone:
                    bone.rotation_euler = mathutils.Euler(head_euler, 'XYZ')

        # Refresh viewport at ~30fps (was 0.5s — caused visible skipping)
        now = time.time()
        if now - self._last_redraw_time > 0.033:
            self._last_redraw_time = now
            for window in bpy.context.window_manager.windows:
                for area in window.screen.areas:
                    if area.type == 'VIEW_3D':
                        area.tag_redraw()

        return 0.01  # 10ms timer interval
