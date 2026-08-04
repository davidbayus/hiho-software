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
MPPT_FLAG_HANDS = 0x04  # alpha.46: 3 endpoints per hand in body-anchored meters
MPPT_FLAG_PALM_BASIS = 0x08  # alpha.56: palm_x + palm_y unit vectors per hand

# Hand-tracking dropout / reacquisition timing (alpha.53 dropout delta).
# Receiver-side only — the GN graph cannot reason about packet arrival
# time, so the receiver computes a per-hand Live float each tick and
# pushes it as a modifier socket. The chain physics in physics.py reads
# this float and gates its tip-pull term, smoothly transitioning between
# TRACKED (Live=1, full pull toward MP fingertip) and RELEASED (Live=0,
# free Verlet dangle under gravity + goal pull). See
# NATIVE_PHYSICS_DESIGN_DELTA_DROPOUT.md §Delta 1.
_DROPOUT_HOLD_S = 0.20  # ignore dropouts shorter than this — swallows
                        # single-frame MP misses
_DROPOUT_TAU_S  = 0.20  # Live ramps 1→0 over this once hold expires
_REACQ_TAU_S    = 0.08  # Live ramps 0→1 over this on recovery
                        # (asymmetric: drop slow to cushion the user
                        # against MP flicker, recover fast to snap the
                        # tip back to where their finger actually is)

# Hand endpoint socket names (6 Vector sockets on the GN modifier).
# These are the 3 tracked endpoints per hand, body-anchored world space:
#   wrist, thumb tip, index-finger tip (per Option C design doc).
# L = performer's left hand → maps to puppet's right side (selfie flip),
# R = performer's right hand → puppet's left side.
HAND_ENDPOINT_NAMES = (
    'bt_wrist_l', 'bt_thumb_l', 'bt_index_l',
    'bt_wrist_r', 'bt_thumb_r', 'bt_index_r',
)

# Palm-basis socket names (alpha.56). 2 unit vectors per hand defining
# the in-palm orientation. The third basis vector palm_z is reconstructed
# GN-side via cross(palm_x, palm_y) — saves 2 sockets per hand on the
# modifier interface and one round of orthogonalization. Receiver maps
# performer-side L/R onto puppet-side R/L (same selfie-flip mirror as
# the wrist/thumb/index unpacker — see decode_mediapipe).
PALM_BASIS_NAMES = (
    'palm_x_l', 'palm_y_l',
    'palm_x_r', 'palm_y_r',
)

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
        1 byte   — flags (bit 0: face, bit 1: body, bit 2: hands [alpha.46])
        If face:  52 floats (blend shapes) + 3 floats (head rotation)
        If body:  33 × 4 floats (x, y, z, visibility) + 3 body-center floats
        If hands: 1 presence byte (bit 0 L, bit 1 R)
                  + 9 floats per present hand
                    (wrist_xyz, thumb_tip_xyz, index_tip_xyz)

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

    # Hand endpoints: body-anchored world coords (meters, same frame as
    # pose_world_landmarks). Up to 2 hands, each with wrist + thumb_tip +
    # index_tip. Missing hands are omitted from the entries dict so the
    # push side can distinguish "not present" from "present at origin".
    #
    # alpha.55: mirror packet labels onto puppet sides — performer's
    # anatomical-Left hand drives puppet R-side sockets, and vice versa.
    # Matches the shoulder/hip delta swap below in `_compute_body_deltas`
    # (see "Puppet right = MP left" comment around line ~1108). Without
    # this swap, the puppet's tracked finger reaches on the OPPOSITE
    # side from the performer.
    if flags & MPPT_FLAG_HANDS:
        if len(raw_bytes) < offset + 1:
            return None
        presence = raw_bytes[offset]
        offset += 1
        entries = {}
        for label, bit in (('l', 0x01), ('r', 0x02)):
            if not (presence & bit):
                continue
            hand_size = 9 * 4  # 9 floats × 4 bytes
            if len(raw_bytes) < offset + hand_size:
                return None
            hd = struct.unpack('<9f',
                               raw_bytes[offset:offset + hand_size])
            offset += hand_size
            puppet_side = 'r' if label == 'l' else 'l'
            entries[f'bt_wrist_{puppet_side}'] = (hd[0], hd[1], hd[2])
            entries[f'bt_thumb_{puppet_side}'] = (hd[3], hd[4], hd[5])
            entries[f'bt_index_{puppet_side}'] = (hd[6], hd[7], hd[8])
        if entries:
            result.append(('hand_endpoints', entries))

    # Palm basis (alpha.56). Own flag bit + own presence byte —
    # NOT a per-hand block size bump under FLAG_HAS_HANDS, because that
    # would corrupt alpha.45–.55 receivers which expect 9 floats per
    # hand. Old receivers ignore the unknown flag and the trailing
    # bytes; alpha.56+ receivers decode 6 floats per hand here. Same
    # selfie-flip L/R swap as the hand-endpoint unpacker above.
    if flags & MPPT_FLAG_PALM_BASIS:
        if len(raw_bytes) < offset + 1:
            return None
        p_presence = raw_bytes[offset]
        offset += 1
        palm_entries = {}
        for label, bit in (('l', 0x01), ('r', 0x02)):
            if not (p_presence & bit):
                continue
            section_size = 6 * 4
            if len(raw_bytes) < offset + section_size:
                return None
            pd = struct.unpack('<6f',
                               raw_bytes[offset:offset + section_size])
            offset += section_size
            puppet_side = 'r' if label == 'l' else 'l'
            palm_entries[f'palm_x_{puppet_side}'] = (pd[0], pd[1], pd[2])
            palm_entries[f'palm_y_{puppet_side}'] = (pd[3], pd[4], pd[5])
        if palm_entries:
            result.append(('palm_basis', palm_entries))

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
        self._vis_socket_ids = None  # vis_arm_l etc → socket identifier
        self._ext_socket_ids = None  # bt_arm_*_ext → socket identifier
        # Delta cache (alpha.43): skip modifier writes when value hasn't
        # changed. Blender invalidates the dep graph on every write — even
        # a write of the same value — so a still face was dirtying the
        # graph 30×/sec with identical numbers.
        self._last_written = {}
        # Dep-graph invalidation gate (alpha.44): _push_to_puppet sets this
        # flag instead of calling update_tag() directly. The timer coalesces
        # all writes within a ~33ms window into one update_tag() call on
        # the 30 FPS redraw tick — one graph invalidation per frame, not
        # one per write.
        self._dep_graph_dirty = False
        # Per-hand presence tracking (alpha.53 dropout delta). Initialized
        # to "live" so a freshly-started receiver before any packets arrive
        # behaves identically to alpha.50 — Live = 1.0 means full tip pull,
        # tracked-tip socket sees raw_mp value (which is (0,0,0) pre-
        # tracking → falls through hands.py rest-pose fallback). Once
        # packets start arriving, the timer drives the asymmetric ramp:
        # last_seen → updated each batch, live → ramped toward 1.0/0.0,
        # held_pos → captures last fully-tracked value as the lerp source
        # during recovery. See NATIVE_PHYSICS_DESIGN_DELTA_DROPOUT.md.
        self._hand_last_seen = {'l': time.monotonic(), 'r': time.monotonic()}
        self._hand_live      = {'l': 1.0, 'r': 1.0}
        # Per-socket last-tracked snapshot for the recovery lerp. Hand
        # endpoints (alpha.53) + palm basis (alpha.56) share one dict
        # because they share the per-hand Live ramp — when the hand is
        # released, BOTH the tip positions AND the palm orientation
        # freeze at their last-tracked values.
        self._hand_held_pos  = {
            'bt_thumb_l': None, 'bt_index_l': None,
            'bt_thumb_r': None, 'bt_index_r': None,
            'bt_wrist_l': None, 'bt_wrist_r': None,
            'palm_x_l': None, 'palm_y_l': None,
            'palm_x_r': None, 'palm_y_r': None,
        }
        self._live_socket_ids = None  # 'Hand L/R Live' → socket identifier
        self._palm_socket_ids = None  # 'palm_x/y_l/r' → socket identifier
        self._last_live_tick = 0.0    # monotonic clock of last tick — for
                                      # asymmetric ramp dt computation

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
        self._vis_socket_ids = None
        self._ext_socket_ids = None
        self._last_written.clear()
        self._dep_graph_dirty = False
        # Reset dropout-delta state so a subsequent start() is fresh
        # (alpha.53). Discovery rebuilds _live_socket_ids and (alpha.56)
        # _palm_socket_ids; the timer + Live + held_pos dicts are re-
        # initialized to "live" defaults so the held-position lerp
        # behaves as if the receiver had just booted.
        self._live_socket_ids = None
        self._palm_socket_ids = None
        self._hand_last_seen = {'l': time.monotonic(), 'r': time.monotonic()}
        self._hand_live      = {'l': 1.0, 'r': 1.0}
        for k in self._hand_held_pos:
            self._hand_held_pos[k] = None
        self._last_live_tick = 0.0

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
                                elif entry[0] == 'hand_endpoints':
                                    self._pending['_hand_endpoints'] = entry[1]
                                elif entry[0] == 'palm_basis':
                                    self._pending['_palm_basis'] = entry[1]
            except OSError:
                break

    def _apply_updates(self):
        """Timer callback: push pending data to Blender objects (main thread)."""
        if not self._running:
            return None  # Unregister timer

        # Lazy-cache the pose bone for head rotation.
        # The phone-era dummy-mesh shape-key cache was removed in alpha.42 —
        # nothing downstream reads those shape keys anymore (face values go
        # straight to the GN modifier via _push_to_puppet).
        if self._cached_bone is None and self._target_armature and self._target_bone:
            arm = self._target_armature
            if arm.type == 'ARMATURE':
                self._cached_bone = arm.pose.bones.get(self._target_bone)

        # Swap pending dict — O(1)
        with self._lock:
            updates = self._pending
            self._pending = {}

        # Tick hand presence/Live every tick (alpha.53). Runs even when
        # no packets arrived this batch, because the dropout transition
        # is precisely "no packets for HOLD_S" → Live needs to ramp down
        # whether or not we're seeing data. The early return that lived
        # here pre-alpha.53 would have frozen Live at its last value
        # whenever the sender went silent, defeating the whole point.
        # Cost when truly idle: ~10µs of dict.get() + arithmetic.
        self._tick_hand_state(updates)

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

        # Coalesce dep-graph invalidation + viewport refresh at ~30fps.
        # Before alpha.44, update_tag() fired on every write from the 100Hz
        # timer — up to 3× per redraw frame. Gating both to the same 33ms
        # window means the GN tree re-evaluates once per visible frame.
        now = time.time()
        if now - self._last_redraw_time > 0.033:
            self._last_redraw_time = now
            if self._dep_graph_dirty and self._cached_puppet_obj:
                self._cached_puppet_obj.update_tag()
                self._dep_graph_dirty = False
            for window in bpy.context.window_manager.windows:
                for area in window.screen.areas:
                    if area.type == 'VIEW_3D':
                        area.tag_redraw()

        return 0.01

    def _value_changed(self, key, value, eps=1e-4):
        """Return True if value differs from cached; update cache on change.

        Handles both float scalars and 3-component vectors (tuple/list).
        Blender dirties the dep graph on every modifier write, so skipping
        same-value writes is the biggest single FPS win on a still subject.
        """
        last = self._last_written.get(key)
        if last is None:
            if isinstance(value, (tuple, list)):
                self._last_written[key] = tuple(value)
            else:
                self._last_written[key] = value
            return True
        if isinstance(value, (tuple, list)):
            for i, v in enumerate(value):
                if abs(v - last[i]) > eps:
                    self._last_written[key] = tuple(value)
                    return True
            return False
        if abs(value - last) > eps:
            self._last_written[key] = value
            return True
        return False

    def _tick_hand_state(self, updates):
        """Update per-hand presence timer + Live float every tick.

        Alpha.53 dropout delta. Refreshes _hand_last_seen from any hand
        packets in this batch, then ramps _hand_live toward 1.0 (recently
        seen) or 0.0 (timed out) using asymmetric tau constants. Drives
        the receiver-side lerp in _push_to_puppet AND the Live floats
        the chain physics reads in PP_ChainVerletSegment.

        Called every push tick from _apply_updates regardless of packet
        arrival — the dropout transition fires precisely when packets
        STOP arriving, so we can't gate this on "did we get data."

        See NATIVE_PHYSICS_DESIGN_DELTA_DROPOUT.md §Delta 1.
        """
        now = time.monotonic()

        # Refresh last-seen from any hand-endpoint packets in this batch.
        # We update on any of the 6 hand sockets (wrist/thumb/index per
        # side) — they're all sent together when MP detects the hand.
        hand_ep = updates.get('_hand_endpoints') if updates else None
        if hand_ep:
            for name in hand_ep:
                if name.endswith('_l'):
                    self._hand_last_seen['l'] = now
                elif name.endswith('_r'):
                    self._hand_last_seen['r'] = now

        # Ramp Live per side. Tick interval is variable (timer fires at
        # ~100Hz but Blender doesn't guarantee jitter-free intervals); we
        # measure the actual dt rather than assuming 0.01s.
        if self._last_live_tick == 0.0:
            dt_tick = 0.01  # bootstrap — assume one nominal tick
        else:
            dt_tick = now - self._last_live_tick
        self._last_live_tick = now

        for side in ('l', 'r'):
            dt_since = now - self._hand_last_seen[side]
            target = 1.0 if dt_since < _DROPOUT_HOLD_S else 0.0
            cur = self._hand_live[side]
            tau = _REACQ_TAU_S if target > cur else _DROPOUT_TAU_S
            step = dt_tick / max(tau, 1e-6)
            if target > cur:
                cur = min(cur + step, target)
            elif target < cur:
                cur = max(cur - step, target)
            self._hand_live[side] = cur

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
            self._vis_socket_ids = {}
            self._ext_socket_ids = {}
            self._live_socket_ids = {}  # alpha.53 dropout delta
            self._palm_socket_ids = {}  # alpha.56 palm basis
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
                    elif item.name in ('Hand L Live', 'Hand R Live'):
                        # alpha.53 dropout delta — receiver-driven Live
                        # float per hand, gates tip-pull in chain physics.
                        self._live_socket_ids[item.name] = item.identifier
                        self._iface_map[item.name] = item
                    elif item.name.startswith('vis_'):
                        self._vis_socket_ids[item.name] = item.identifier
                        self._iface_map[item.name] = item
                    elif (item.name.startswith('bt_')
                          and item.name.endswith('_ext')):
                        self._ext_socket_ids[item.name] = item.identifier
                        self._iface_map[item.name] = item
                elif item.socket_type == 'NodeSocketVector':
                    if item.name.startswith('bt_'):
                        self._bt_socket_ids[item.name] = item.identifier
                        self._iface_map[item.name] = item
                    elif item.name in PALM_BASIS_NAMES:
                        # alpha.56 — explicit branch (small static set,
                        # mirrors how 'Hand L/R Live' was added in alpha.53).
                        self._palm_socket_ids[item.name] = item.identifier
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
            if not self._value_changed(name, value):
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
                if not self._value_changed(rname, head_euler[i]):
                    continue
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
                if self._value_changed('bt_body_center', puppet_center):
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

        # Push hand endpoints (alpha.46). Incoming values are in pose_world
        # space (MP metric, Y-down, Z-toward-camera). Same _mp_to_puppet
        # transform used for body tracking — see _push_body_tracking for the
        # axis rationale. Applied to absolute positions here rather than
        # deltas because hand endpoints come pre-anchored to pose_world[15/16].
        #
        # Alpha.53 dropout delta: each tracked-tip write is now lerped via
        # the receiver-side `_hand_held_pos` cache. Live = 1.0 → capture
        # raw as held, write raw. Live < 1.0 → write lerp(held, raw, Live)
        # so the chain physics sees a smoothly-drifting target during
        # REACQUIRING instead of a snap from "frozen at last position" to
        # "30 cm offset." See NATIVE_PHYSICS_DESIGN_DELTA_DROPOUT.md.
        hand_ep = updates.get('_hand_endpoints')
        if hand_ep and self._bt_socket_ids:
            for name, pos in hand_ep.items():
                if name not in HAND_ENDPOINT_NAMES:
                    continue
                sid = self._bt_socket_ids.get(name)
                if not sid:
                    continue
                # MP (x,y,z) → puppet (x * scale, z * scale, -y * scale)
                puppet_pos = [
                    pos[0] * self._BT_SCALE,
                    pos[2] * self._BT_SCALE,
                    -pos[1] * self._BT_SCALE,
                ]
                # Receiver-side recovery lerp (alpha.53). When Live ≥ 1
                # we pass through and capture; when ramping, lerp from
                # last fully-tracked value toward raw.
                side = 'l' if name.endswith('_l') else 'r'
                live = self._hand_live[side]
                held = self._hand_held_pos.get(name)
                if live >= 0.999:
                    self._hand_held_pos[name] = list(puppet_pos)
                    out_pos = puppet_pos
                elif held is None:
                    # First-ever packet for this socket — nothing to
                    # lerp from. Pass through and let the next tick
                    # capture it once Live is fully back at 1.0.
                    out_pos = puppet_pos
                else:
                    out_pos = [held[i] + (puppet_pos[i] - held[i]) * live
                               for i in range(3)]
                if not self._value_changed(name, out_pos):
                    continue
                try:
                    if self._write_method == 'idprop':
                        mod[sid] = out_pos
                    elif self._write_method == 'default':
                        iface = self._iface_map.get(name)
                        if iface:
                            iface.default_value = out_pos
                    else:
                        mod[sid] = out_pos
                    wrote_any = True
                except Exception:
                    pass

        # Push palm basis (alpha.56). Same MP→puppet axis remap as
        # bt_ vectors but WITHOUT _BT_SCALE — basis vectors define
        # orientation, not displacement, so scaling them would distort
        # the rotation. Re-uses the per-hand Live ramp from
        # _tick_hand_state: when the hand drops, the palm orientation
        # freezes at last-tracked (held cache); on reacquire it lerps
        # smoothly back to fresh tracked over REACQ_TAU_S. Per-component
        # lerp briefly produces a non-unit basis during reacquisition;
        # invisible at the GN rotation step (alpha.57).
        palm_ep = updates.get('_palm_basis')
        if palm_ep and self._palm_socket_ids:
            for name, vec in palm_ep.items():
                if name not in PALM_BASIS_NAMES:
                    continue
                sid = self._palm_socket_ids.get(name)
                if not sid:
                    continue
                # MP (x,y,z) → puppet (x, z, -y). No scale factor.
                puppet_vec = [vec[0], vec[2], -vec[1]]
                side = 'l' if name.endswith('_l') else 'r'
                live = self._hand_live[side]
                held = self._hand_held_pos.get(name)
                if live >= 0.999:
                    self._hand_held_pos[name] = list(puppet_vec)
                    out_vec = puppet_vec
                elif held is None:
                    out_vec = puppet_vec
                else:
                    out_vec = [held[i] + (puppet_vec[i] - held[i]) * live
                               for i in range(3)]
                if not self._value_changed(name, out_vec):
                    continue
                try:
                    if self._write_method == 'idprop':
                        mod[sid] = out_vec
                    elif self._write_method == 'default':
                        iface = self._iface_map.get(name)
                        if iface:
                            iface.default_value = out_vec
                    else:
                        mod[sid] = out_vec
                    wrote_any = True
                except Exception:
                    pass

        # Push Live floats (alpha.53). Runs every tick; _value_changed
        # skips redundant writes when Live is steady at 1.0 or 0.0.
        # Sockets only exist on alpha.52+ marionettes; older builds
        # have an empty _live_socket_ids dict and this loop is a no-op.
        if self._live_socket_ids:
            for side in ('l', 'r'):
                name = f'Hand {side.upper()} Live'
                sid = self._live_socket_ids.get(name)
                if not sid:
                    continue
                live = self._hand_live[side]
                if not self._value_changed(name, live, eps=1e-3):
                    continue
                try:
                    if self._write_method == 'idprop':
                        mod[sid] = live
                    elif self._write_method == 'default':
                        iface = self._iface_map.get(name)
                        if iface:
                            iface.default_value = live
                    else:
                        mod[sid] = live
                    wrote_any = True
                except Exception:
                    pass

        if wrote_any:
            self._dep_graph_dirty = True

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

    # Scale MediaPipe meters → puppet units (tunable).
    # Bumped 1.5 → 2.5 in alpha.5: larger deltas overcome Verlet damping
    # so hands feel lighter and more responsive to body movement.
    _BT_SCALE = 2.5

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
            """Transform a MediaPipe delta to puppet space.

            MediaPipe world landmarks: X right, Y down, Z toward camera (negative = closer).
            Blender puppet space: X right, Y forward (negative = toward camera), Z up.
            """
            return (
                dx * self._BT_SCALE,       # lateral: same direction
                dz * self._BT_SCALE,       # depth: MP -Z (closer) → puppet -Y (toward cam)
                -dy * self._BT_SCALE,      # vertical: negate (MP Y down → puppet Z up)
            )

        def _delta(a_idx, b_idx):
            a = _lm_vec(a_idx)
            b = _lm_vec(b_idx)
            if not a or not b:
                return None
            return _mp_to_puppet(b[0] - a[0], b[1] - a[1], b[2] - a[2])

        def _bend_hint(sh_idx, el_idx, wr_idx):
            """Perpendicular offset of elbow from shoulder-hand line.

            Returns a direction vector in puppet space pointing from the
            shoulder-hand line toward the elbow — the true bend direction.
            Falls back to (0, -1, 0) puppet space when degenerate.
            """
            s = _lm_vec(sh_idx)
            e = _lm_vec(el_idx)
            h = _lm_vec(wr_idx)
            if not s or not e or not h:
                return None
            # Direction shoulder→hand in MP space
            dx, dy, dz = h[0]-s[0], h[1]-s[1], h[2]-s[2]
            dd = dx*dx + dy*dy + dz*dz
            if dd < 1e-8:
                return _mp_to_puppet(0.0, 0.0, -1.0)
            # Project elbow onto shoulder-hand line
            t = ((e[0]-s[0])*dx + (e[1]-s[1])*dy + (e[2]-s[2])*dz) / dd
            px, py, pz = s[0]+t*dx, s[1]+t*dy, s[2]+t*dz
            # Perpendicular offset: elbow - projection
            bx, by, bz = e[0]-px, e[1]-py, e[2]-pz
            bl = (bx*bx + by*by + bz*bz) ** 0.5
            if bl < 1e-6:
                return _mp_to_puppet(0.0, 0.0, -1.0)
            # Negate: bend hint points TOWARD elbow, but PP_TwoBoneIK's
            # double cross product convention expects the OPPOSITE direction
            return _mp_to_puppet(-bx/bl, -by/bl, -bz/bl)

        # Puppet right = MP left (because of selfie flip)
        # Puppet left = MP right
        deltas = {
            'bt_shr_delta': _delta(self._LM_L_SHOULDER, self._LM_L_WRIST),
            'bt_shl_delta': _delta(self._LM_R_SHOULDER, self._LM_R_WRIST),
            'bt_hipr_delta': _delta(self._LM_L_HIP, self._LM_L_ANKLE),
            'bt_hipl_delta': _delta(self._LM_R_HIP, self._LM_R_ANKLE),
            # Elbow bend hints: perpendicular offset from shoulder-hand line
            'bt_elbow_r_hint': _bend_hint(self._LM_L_SHOULDER,
                                          self._LM_L_ELBOW,
                                          self._LM_L_WRIST),
            'bt_elbow_l_hint': _bend_hint(self._LM_R_SHOULDER,
                                          self._LM_R_ELBOW,
                                          self._LM_R_WRIST),
        }

        wrote = False
        for name, vec in deltas.items():
            if vec is None:
                continue
            sid = self._bt_socket_ids.get(name)
            if not sid:
                continue
            if not self._value_changed(name, vec):
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

        # --- Arm extension ratios (how bent the arm is) ---
        # Ratio of straight-line shoulder→wrist distance to total arm
        # length (upper + lower segments). 0 = fully folded, 1 = straight.
        # Used in GN to scale hand position to puppet's Arm Length,
        # so IK can compute proper elbow bend regardless of proportions.
        def _arm_extension(sh_idx, el_idx, wr_idx):
            s = _lm_vec(sh_idx)
            e = _lm_vec(el_idx)
            w = _lm_vec(wr_idx)
            if not s or not e or not w:
                return None
            upper = sum((a - b) ** 2 for a, b in zip(e, s)) ** 0.5
            lower = sum((a - b) ** 2 for a, b in zip(w, e)) ** 0.5
            total = upper + lower
            if total < 1e-6:
                return 1.0
            reach = sum((a - b) ** 2 for a, b in zip(w, s)) ** 0.5
            return min(1.0, reach / total)

        # Puppet left = MP right (selfie flip)
        ext_ratios = {
            'bt_arm_l_ext': _arm_extension(self._LM_R_SHOULDER,
                                           self._LM_R_ELBOW,
                                           self._LM_R_WRIST),
            'bt_arm_r_ext': _arm_extension(self._LM_L_SHOULDER,
                                           self._LM_L_ELBOW,
                                           self._LM_L_WRIST),
        }

        if self._ext_socket_ids:
            for name, ratio in ext_ratios.items():
                if ratio is None:
                    continue
                sid = self._ext_socket_ids.get(name)
                if not sid:
                    continue
                if not self._value_changed(name, ratio):
                    continue
                try:
                    if self._write_method == 'idprop':
                        mod[sid] = ratio
                    elif self._write_method == 'default':
                        iface = self._iface_map.get(name)
                        if iface:
                            iface.default_value = ratio
                    else:
                        mod[sid] = ratio
                    wrote = True
                except Exception:
                    pass

        # --- Per-limb visibility from landmark confidence scores ---
        # When a limb drops off camera, its visibility → 0, blending that
        # limb back to face heuristics (idle pose). Ramp: <0.3→0, >0.7→1.
        def _limb_vis(idx_a, idx_b):
            a = landmarks.get(idx_a)
            b = landmarks.get(idx_b)
            if not a or not b:
                return 0.0
            raw = min(a.get('visibility', 0), b.get('visibility', 0))
            return max(0.0, min(1.0, (raw - 0.3) / 0.4))

        # Puppet left = MP right (selfie flip), puppet right = MP left
        vis_scores = {
            'vis_arm_l': _limb_vis(self._LM_R_SHOULDER, self._LM_R_WRIST),
            'vis_arm_r': _limb_vis(self._LM_L_SHOULDER, self._LM_L_WRIST),
            'vis_leg_l': _limb_vis(self._LM_R_HIP, self._LM_R_ANKLE),
            'vis_leg_r': _limb_vis(self._LM_L_HIP, self._LM_L_ANKLE),
        }

        if self._vis_socket_ids:
            for name, score in vis_scores.items():
                sid = self._vis_socket_ids.get(name)
                if not sid:
                    continue
                if not self._value_changed(name, score):
                    continue
                try:
                    if self._write_method == 'idprop':
                        mod[sid] = score
                    elif self._write_method == 'default':
                        iface = self._iface_map.get(name)
                        if iface:
                            iface.default_value = score
                    else:
                        mod[sid] = score
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
