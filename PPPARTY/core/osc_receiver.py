"""Tracking data receiver for PPParty — MediaPipe + Live Link Face.

Receives face + body tracking data over UDP and applies it to
geometry node modifier inputs on the PP_Marionette object.

Supports two input formats (auto-detected per packet):
  1. MediaPipe MPPT packets (webcam sender script)
  2. Live Link Face packets (phone-based, backward compat with V0.9.6)

Forked from FOSCAP 1.0.0 (GPL-3.0-or-later)
Original authors: Will Anderson, Francesco Siddi (Blender Foundation)
"""

import socket
import struct
import threading
import time

import bpy
import mathutils


# ---------------------------------------------------------------------------
# MediaPipe MPPT packet format
# ---------------------------------------------------------------------------

# Magic header for MediaPipe PPParty Tracking packets
MPPT_MAGIC = b'MPPT'
MPPT_VERSION = 0x01
MPPT_FLAG_FACE = 0x01
MPPT_FLAG_BODY = 0x02

# MediaPipe blend shape names in alphabetical order (52 total).
# Index into this list matches the order MediaPipe outputs them.
MEDIAPIPE_BLEND_SHAPES = [
    "_neutral",          # 0  — not used
    "browDownLeft",      # 1
    "browDownRight",     # 2
    "browInnerUp",       # 3
    "browOuterUpLeft",   # 4
    "browOuterUpRight",  # 5
    "cheekPuff",         # 6
    "cheekSquintLeft",   # 7
    "cheekSquintRight",  # 8
    "eyeBlinkLeft",      # 9
    "eyeBlinkRight",     # 10
    "eyeLookDownLeft",   # 11
    "eyeLookDownRight",  # 12
    "eyeLookInLeft",     # 13
    "eyeLookInRight",    # 14
    "eyeLookOutLeft",    # 15
    "eyeLookOutRight",   # 16
    "eyeLookUpLeft",     # 17
    "eyeLookUpRight",    # 18
    "eyeSquintLeft",     # 19
    "eyeSquintRight",    # 20
    "eyeWideLeft",       # 21
    "eyeWideRight",      # 22
    "jawForward",        # 23
    "jawLeft",           # 24
    "jawOpen",           # 25
    "jawRight",          # 26
    "mouthClose",        # 27
    "mouthDimpleLeft",   # 28
    "mouthDimpleRight",  # 29
    "mouthFrownLeft",    # 30
    "mouthFrownRight",   # 31
    "mouthFunnel",       # 32
    "mouthLeft",         # 33
    "mouthLowerDownLeft",  # 34
    "mouthLowerDownRight", # 35
    "mouthPressLeft",    # 36
    "mouthPressRight",   # 37
    "mouthPucker",       # 38
    "mouthRight",        # 39
    "mouthRollLower",    # 40
    "mouthRollUpper",    # 41
    "mouthShrugLower",   # 42
    "mouthShrugUpper",   # 43
    "mouthSmileLeft",    # 44
    "mouthSmileRight",   # 45
    "mouthStretchLeft",  # 46
    "mouthStretchRight", # 47
    "mouthUpperUpLeft",  # 48
    "mouthUpperUpRight", # 49
    "noseSneerLeft",     # 50
    "noseSneerRight",    # 51
]

# MediaPipe pose landmark names (33 total)
POSE_LANDMARK_NAMES = [
    "nose", "left_eye_inner", "left_eye", "left_eye_outer",
    "right_eye_inner", "right_eye", "right_eye_outer",
    "left_ear", "right_ear", "mouth_left", "mouth_right",
    "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
    "left_wrist", "right_wrist", "left_pinky", "right_pinky",
    "left_index", "right_index", "left_thumb", "right_thumb",
    "left_hip", "right_hip", "left_knee", "right_knee",
    "left_ankle", "right_ankle", "left_heel", "right_heel",
    "left_foot_index", "right_foot_index",
]


# ---------------------------------------------------------------------------
# Live Link Face format (backward compat with phone pipeline)
# ---------------------------------------------------------------------------

# The 13 active ARKit shape keys used by the phone-era pipeline.
# Maps Live Link Face array index -> shape key name on the dummy mesh.
BLENDSHAPE_MAP = {
    2: 'eyeLookInRight',
    3: 'eyeLookInLeft',
    4: 'eyeLookOutRight',
    5: 'eyeLookOutLeft',
    19: 'mouthFunnel',
    20: 'mouthPucker',
    21: 'mouthLeft',
    22: 'mouthRight',
    23: 'mouthSmileRight',
    25: 'mouthFrownLeft',
    26: 'mouthFrownRight',
    27: 'mouthClose',
    37: 'jawOpen',
    41: 'eyeBlinkLeft',
    42: 'eyeBlinkRight',
    43: 'eyeWideLeft',
    44: 'eyeWideRight',
}

# Name of the hidden mesh that receives shape key data
DUMMY_MESH_NAME = "ARKitShapeKeys.Dummy"


# ---------------------------------------------------------------------------
# Packet decoders
# ---------------------------------------------------------------------------

def decode_mediapipe(raw_bytes):
    """Decode a MediaPipe MPPT UDP packet.

    Packet format:
        4 bytes  — magic b'MPPT'
        1 byte   — version
        1 byte   — flags (bit 0: face, bit 1: body)
        If face:  52 floats (blend shapes) + 3 floats (head rotation)
        If body:  33 × 4 floats (x, y, z, visibility per landmark)

    Returns a list of tuples, or None on failure.
    """
    if len(raw_bytes) < 6:
        return None
    if raw_bytes[:4] != MPPT_MAGIC:
        return None

    version, flags = struct.unpack('BB', raw_bytes[4:6])
    if version != MPPT_VERSION:
        return None

    result = []
    offset = 6

    # Face data: 52 blend shapes + 3 head rotation = 55 floats
    if flags & MPPT_FLAG_FACE:
        face_size = 55 * 4  # 55 floats × 4 bytes
        if len(raw_bytes) < offset + face_size:
            return None
        data = struct.unpack('<55f', raw_bytes[offset:offset + face_size])
        offset += face_size

        # Blend shapes (first 52 floats)
        for i in range(52):
            name = MEDIAPIPE_BLEND_SHAPES[i]
            if name != "_neutral":
                result.append(('shape', name, data[i]))

        # Head rotation (floats 52-54: pitch, yaw, roll)
        result.append(('head_rotation', [data[52], data[53], data[54]]))

    # Body data: 33 landmarks × 4 floats + 3 body center floats = 135
    if flags & MPPT_FLAG_BODY:
        body_size = 135 * 4
        if len(raw_bytes) < offset + body_size:
            return None
        data = struct.unpack('<135f', raw_bytes[offset:offset + body_size])
        offset += body_size

        landmarks = {}
        for i in range(33):
            base = i * 4
            landmarks[i] = {
                'name': POSE_LANDMARK_NAMES[i],
                'x': data[base],
                'y': data[base + 1],
                'z': data[base + 2],
                'visibility': data[base + 3],
            }
        result.append(('body_landmarks', landmarks))

        # Body center: image-space hip midpoint (centered at 0,0)
        result.append(('body_center', (data[132], data[133], data[134])))

    return result if result else None


def decode_live_link_face(raw_bytes):
    """Decode a binary Live Link Face UDP packet (phone pipeline).

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


def decode_packet(raw_bytes):
    """Auto-detect packet format and decode.

    Checks for MPPT magic header first (MediaPipe), falls back to
    Live Link Face (phone pipeline).
    """
    if len(raw_bytes) >= 4 and raw_bytes[:4] == MPPT_MAGIC:
        return decode_mediapipe(raw_bytes)
    return decode_live_link_face(raw_bytes)


# ---------------------------------------------------------------------------
# Dummy mesh (backward compat — still used by phone pipeline)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Receiver
# ---------------------------------------------------------------------------

class TrackingReceiver:
    """Threaded UDP receiver for face + body tracking data.

    Auto-detects MediaPipe MPPT packets and Live Link Face packets.
    Pushes blend shape values + head rotation to the GN modifier
    on PP_Marionette. Body landmarks are stored for future use
    (wired to Verlet endpoints in alpha.2).

    Usage:
        receiver = TrackingReceiver()
        receiver.start(port=11111)
        # ... tracking data flows to puppet ...
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
        self._source = None  # 'mediapipe' or 'livelink' (set on first packet)
        # Cached references — avoid per-frame lookups
        self._cached_key_blocks = None
        self._cached_bone = None
        # Direct modifier push (bypasses drivers — works on Blender 5.2)
        self._cached_puppet_mod = None
        self._cached_puppet_obj = None  # for update_tag()
        self._face_socket_ids = None   # shape_key_name → socket identifier
        self._rot_socket_ids = None    # headRotX/Y/Z → socket identifier
        self._write_method = None      # 'rna', 'idprop', or 'default'
        self._rna_map = {}             # face/rot name → RNA property name
        self._iface_map = {}           # face/rot name → interface item (fallback)
        # Body tracking — deltas pushed to GN Vector sockets
        self._body_landmarks = None
        self._bt_socket_ids = None   # bt_*_delta → socket identifier
        self._bt_factor_id = None    # Body Tracking float → socket identifier

    @property
    def is_running(self):
        return self._running

    @property
    def is_receiving(self):
        """True if we got tracking data in the last 2 seconds."""
        return self._running and (time.time() - self._last_packet_time) < 2.0

    @property
    def port(self):
        return self._port

    @property
    def source(self):
        """'mediapipe', 'livelink', or None if no packets received yet."""
        return self._source

    @property
    def body_landmarks(self):
        """Latest body landmarks dict, or None. Keys are landmark indices."""
        return self._body_landmarks

    def get_latest_values(self):
        """Snapshot of latest shape key values for UI display."""
        with self._lock:
            return dict(self._latest)

    def start(self, port=11111, target_armature=None, target_bone=None):
        """Start listening for tracking data.

        Returns True if started successfully, False on error (e.g. port in use).
        """
        if self._running:
            return True

        self._port = port
        self._target_armature = target_armature
        self._target_bone = target_bone

        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 65536)
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

        self._cached_key_blocks = None
        self._cached_bone = None
        self._cached_puppet_mod = None
        self._cached_puppet_obj = None
        self._face_socket_ids = None
        self._rot_socket_ids = None
        self._write_method = None
        self._rna_map = {}
        self._iface_map = {}
        self._source = None
        self._body_landmarks = None
        self._bt_socket_ids = None
        self._bt_factor_id = None

        if bpy.app.timers.is_registered(self._apply_updates):
            bpy.app.timers.unregister(self._apply_updates)

    def _listen(self):
        """Background thread: receive and decode UDP packets.

        Auto-detects MediaPipe vs Live Link Face format per packet.
        Only keeps the latest value for each shape key and head rotation.
        """
        while self._running:
            try:
                raw, _addr = self._sock.recvfrom(2048)
                if raw:
                    decoded = decode_packet(raw)
                    if decoded:
                        self._last_packet_time = time.time()
                        # Detect source from first packet
                        if self._source is None:
                            if len(raw) >= 4 and raw[:4] == MPPT_MAGIC:
                                self._source = 'mediapipe'
                            else:
                                self._source = 'livelink'
                        with self._lock:
                            for entry in decoded:
                                if entry[0] == 'shape':
                                    self._pending[entry[1]] = entry[2]
                                    self._latest[entry[1]] = entry[2]
                                elif entry[0] == 'head_rotation':
                                    self._pending['_head_rotation'] = entry[1]
                                elif entry[0] == 'body_landmarks':
                                    self._pending['_body_landmarks'] = entry[1]
                                elif entry[0] == 'body_center':
                                    self._pending['_body_center'] = entry[1]
            except OSError:
                break

    def _apply_updates(self):
        """Timer callback: push pending data to Blender objects (main thread)."""
        if not self._running:
            return None  # Unregister timer

        # Lazy-cache shape key blocks and pose bone
        if self._cached_key_blocks is None:
            dummy = bpy.data.objects.get(DUMMY_MESH_NAME)
            if not dummy or not dummy.data.shape_keys:
                return 0.01
            self._cached_key_blocks = dummy.data.shape_keys.key_blocks
            if self._target_armature and self._target_bone:
                arm = self._target_armature
                if arm.type == 'ARMATURE':
                    self._cached_bone = arm.pose.bones.get(self._target_bone)

        # Swap pending dict — O(1)
        with self._lock:
            updates = self._pending
            self._pending = {}

        if not updates:
            return 0.01

        key_blocks = self._cached_key_blocks

        # Apply shape key values
        for name, value in updates.items():
            if name.startswith('_'):
                continue
            kb = key_blocks.get(name)
            if kb:
                kb.value = value

        # Apply head rotation to armature bone
        head_euler = updates.get('_head_rotation')
        if head_euler and self._cached_bone:
            self._cached_bone.rotation_euler = mathutils.Euler(head_euler, 'XYZ')

        # Store body landmarks for future use (alpha.2)
        body_lm = updates.get('_body_landmarks')
        if body_lm is not None:
            self._body_landmarks = body_lm

        # Push face tracking + head rotation to GN modifier
        self._push_to_puppet(updates)

        # Refresh viewport at ~30fps
        now = time.time()
        if now - self._last_redraw_time > 0.033:
            self._last_redraw_time = now
            for window in bpy.context.window_manager.windows:
                for area in window.screen.areas:
                    if area.type == 'VIEW_3D':
                        area.tag_redraw()

        return 0.01

    def _push_to_puppet(self, updates):
        """Push tracking data directly to PPParty GN modifier inputs.

        Probes multiple access strategies on first call:
          1. RNA attributes (Blender 5.2+)
          2. IDProperty access (Blender 5.0)
          3. Interface default_value (last resort)
        """
        # Lazy-discover the puppet modifier, build socket maps, probe API
        if self._cached_puppet_mod is None:
            puppet = bpy.data.objects.get("PP_Marionette")
            if not puppet:
                return
            mod = puppet.modifiers.get("PPParty_Physics")
            if not mod or not mod.node_group:
                return

            self._cached_puppet_mod = mod
            self._cached_puppet_obj = puppet
            self._face_socket_ids = {}
            self._rot_socket_ids = {}
            self._bt_socket_ids = {}
            self._bt_factor_id = None
            self._iface_map = {}

            # Gather ALL known face tracking shape names (union of both pipelines)
            shape_names = set(BLENDSHAPE_MAP.values())
            for name in MEDIAPIPE_BLEND_SHAPES:
                if name != "_neutral":
                    shape_names.add(name)

            for item in mod.node_group.interface.items_tree:
                if not (hasattr(item, 'item_type')
                        and item.item_type == 'SOCKET'
                        and item.in_out == 'INPUT'):
                    continue
                if item.socket_type == 'NodeSocketFloat':
                    if item.name in shape_names:
                        self._face_socket_ids[item.name] = item.identifier
                        self._iface_map[item.name] = item
                    elif item.name.startswith('headRot'):
                        self._rot_socket_ids[item.name] = item.identifier
                        self._iface_map[item.name] = item
                    elif item.name == 'Body Tracking':
                        self._bt_factor_id = item.identifier
                        self._iface_map['Body Tracking'] = item
                elif item.socket_type == 'NodeSocketVector':
                    if item.name.startswith('bt_'):
                        self._bt_socket_ids[item.name] = item.identifier
                        self._iface_map[item.name] = item

            # --- Probe: discover correct access method ---
            self._write_method = None
            probe_log = []

            rna_float_props = {}
            for prop in mod.rna_type.properties:
                if prop.type == 'FLOAT' and not prop.is_readonly:
                    rna_float_props[prop.identifier] = prop

            probe_log.append(f"RNA float props: {list(rna_float_props.keys())[:10]}")

            if rna_float_props:
                self._rna_map = {}
                all_ids = {}
                all_ids.update(self._face_socket_ids)
                all_ids.update(self._rot_socket_ids)
                if self._bt_factor_id:
                    all_ids['Body Tracking'] = self._bt_factor_id

                for iface_name, iface_id in all_ids.items():
                    candidates = [
                        iface_id,
                        iface_id.lower(),
                        iface_id.lower().replace('-', '_'),
                        iface_name,
                        iface_name.lower(),
                        ''.join(
                            f'_{c.lower()}' if c.isupper() else c
                            for c in iface_name
                        ).lstrip('_'),
                    ]
                    for candidate in candidates:
                        if candidate in rna_float_props:
                            self._rna_map[iface_name] = candidate
                            break

                if self._rna_map:
                    self._write_method = 'rna'
                    probe_log.append(f"Using RNA: {len(self._rna_map)} mapped")
                    for k, v in list(self._rna_map.items())[:3]:
                        probe_log.append(f"  {k} -> mod.{v}")

            if self._write_method is None and self._face_socket_ids:
                test_sid = next(iter(self._face_socket_ids.values()))
                try:
                    old_val = mod.get(test_sid, 0.0)
                    mod[test_sid] = old_val
                    puppet.update_tag()
                    self._write_method = 'idprop'
                    probe_log.append(f"Using IDProperty (sid={test_sid})")
                except Exception as e:
                    probe_log.append(f"IDProperty failed: {e}")

            if self._write_method is None and self._iface_map:
                try:
                    test_item = next(iter(self._iface_map.values()))
                    old_val = test_item.default_value
                    test_item.default_value = old_val
                    self._write_method = 'default'
                    probe_log.append("Using interface default_value (fallback)")
                except Exception as e:
                    probe_log.append(f"default_value failed: {e}")

            if self._write_method is None:
                probe_log.append("WARNING -- no working access method!")

            self._write_probe_log(probe_log)

        mod = self._cached_puppet_mod
        if not self._write_method:
            return

        wrote_any = False

        # Push face tracking values
        for name, value in updates.items():
            if name.startswith('_'):
                continue
            if self._write_method == 'rna':
                rna_name = self._rna_map.get(name)
                if rna_name:
                    try:
                        setattr(mod, rna_name, value)
                        wrote_any = True
                    except Exception:
                        pass
            elif self._write_method == 'idprop':
                sid = self._face_socket_ids.get(name)
                if sid:
                    try:
                        mod[sid] = value
                        wrote_any = True
                    except Exception:
                        pass
            elif self._write_method == 'default':
                iface = self._iface_map.get(name)
                if iface:
                    try:
                        iface.default_value = value
                        wrote_any = True
                    except Exception:
                        pass

        # Push head rotation
        head_euler = updates.get('_head_rotation')
        if head_euler:
            for i, rname in enumerate(['headRotX', 'headRotY', 'headRotZ']):
                if self._write_method == 'rna':
                    rna_name = self._rna_map.get(rname)
                    if rna_name:
                        try:
                            setattr(mod, rna_name, head_euler[i])
                            wrote_any = True
                        except Exception:
                            pass
                elif self._write_method == 'idprop':
                    sid = self._rot_socket_ids.get(rname)
                    if sid:
                        try:
                            mod[sid] = head_euler[i]
                            wrote_any = True
                        except Exception:
                            pass
                elif self._write_method == 'default':
                    iface = self._iface_map.get(rname)
                    if iface:
                        try:
                            iface.default_value = head_euler[i]
                            wrote_any = True
                        except Exception:
                            pass

        # Push body tracking deltas (when landmarks available)
        body_lm = updates.get('_body_landmarks')
        if body_lm and self._bt_socket_ids:
            bt_wrote = self._push_body_tracking(body_lm, mod)
            wrote_any = wrote_any or bt_wrote

        # Push body center position (image-space hip midpoint)
        body_ctr = updates.get('_body_center')
        if body_ctr and self._bt_socket_ids:
            sid = self._bt_socket_ids.get('bt_body_center')
            if sid:
                # Map image-space to puppet: x→x, y(up)→z, z(depth)→y
                puppet_center = [body_ctr[0], body_ctr[2], body_ctr[1]]
                try:
                    if self._write_method == 'idprop':
                        mod[sid] = puppet_center
                    elif self._write_method == 'rna':
                        rna = self._rna_map.get('bt_body_center')
                        if rna:
                            setattr(mod, rna, puppet_center)
                    else:
                        iface = self._iface_map.get('bt_body_center')
                        if iface:
                            iface.default_value = puppet_center
                    wrote_any = True
                except Exception:
                    pass

        if wrote_any and self._cached_puppet_obj:
            self._cached_puppet_obj.update_tag()

    # MediaPipe landmark indices
    _LM_L_SHOULDER = 11
    _LM_R_SHOULDER = 12
    _LM_L_ELBOW = 13
    _LM_R_ELBOW = 14
    _LM_L_WRIST = 15
    _LM_R_WRIST = 16
    _LM_L_HIP = 23
    _LM_R_HIP = 24
    _LM_L_ANKLE = 27
    _LM_R_ANKLE = 28

    # Scale MediaPipe meters → puppet units (tunable)
    _BT_SCALE = 1.5

    def _push_body_tracking(self, landmarks, mod):
        """Compute body-tracking deltas from MediaPipe pose landmarks.

        MediaPipe coordinate system (after horizontal flip in sender):
          x: subject's left → positive (mirrored: puppet's right)
          y: down → positive
          z: toward camera → positive

        Puppet coordinate system:
          x: right → positive
          z: up → positive
          y: forward → positive

        After flip, MediaPipe's left_* = puppet's right side.

        Deltas: wrist - shoulder (arms), ankle - hip (legs).
        These replace the face-heuristic deltas on attachment points.
        """
        def _lm_vec(idx):
            lm = landmarks.get(idx)
            if not lm:
                return None
            return (lm['x'], lm['y'], lm['z'])

        def _mp_to_puppet(dx, dy, dz):
            """Transform a MediaPipe delta to puppet space."""
            return (
                dx * self._BT_SCALE,       # x stays (flip handled)
                -dz * self._BT_SCALE,       # depth → puppet forward
                -dy * self._BT_SCALE,       # up (negate MP down)
            )

        def _delta(a_idx, b_idx):
            a = _lm_vec(a_idx)
            b = _lm_vec(b_idx)
            if not a or not b:
                return None
            return _mp_to_puppet(b[0] - a[0], b[1] - a[1], b[2] - a[2])

        # Puppet right = MP left (because of selfie flip)
        # Puppet left = MP right
        deltas = {
            'bt_shr_delta': _delta(self._LM_L_SHOULDER, self._LM_L_WRIST),
            'bt_shl_delta': _delta(self._LM_R_SHOULDER, self._LM_R_WRIST),
            'bt_hipr_delta': _delta(self._LM_L_HIP, self._LM_L_ANKLE),
            'bt_hipl_delta': _delta(self._LM_R_HIP, self._LM_R_ANKLE),
            # Elbow bend hints: shoulder→elbow direction for IK
            'bt_elbow_r_hint': _delta(self._LM_L_SHOULDER, self._LM_L_ELBOW),
            'bt_elbow_l_hint': _delta(self._LM_R_SHOULDER, self._LM_R_ELBOW),
        }

        wrote = False
        for name, vec in deltas.items():
            if vec is None:
                continue
            sid = self._bt_socket_ids.get(name)
            if not sid:
                continue
            try:
                if self._write_method == 'idprop':
                    mod[sid] = list(vec)
                    wrote = True
                elif self._write_method == 'default':
                    iface = self._iface_map.get(name)
                    if iface:
                        iface.default_value = vec
                        wrote = True
                else:
                    # RNA: try direct IDProperty as fallback for vectors
                    mod[sid] = list(vec)
                    wrote = True
            except Exception:
                pass

        # Enable body tracking blend (set factor to 1.0)
        if wrote:
            try:
                if self._write_method == 'rna':
                    rna_name = self._rna_map.get('Body Tracking')
                    if rna_name:
                        setattr(mod, rna_name, 1.0)
                elif self._write_method == 'idprop' and self._bt_factor_id:
                    mod[self._bt_factor_id] = 1.0
                elif self._write_method == 'default':
                    iface = self._iface_map.get('Body Tracking')
                    if iface:
                        iface.default_value = 1.0
            except Exception:
                pass

        return wrote

    @staticmethod
    def _write_probe_log(lines):
        """Write probe diagnostic to Blender Text Editor block."""
        text_name = "PPParty_Probe"
        if text_name in bpy.data.texts:
            bpy.data.texts.remove(bpy.data.texts[text_name])
        text = bpy.data.texts.new(text_name)
        text.write("PPParty Tracking Probe Results\n")
        text.write(f"Blender {bpy.app.version_string}\n\n")
        for line in lines:
            text.write(line + "\n")


# Backward compatibility alias — existing code imports OSCReceiver
OSCReceiver = TrackingReceiver
