"""OSC receiver for Live Link Face data — PPParty edition.

Forked from FOSCAP 1.0.0 (GPL-3.0-or-later)
Original authors: Will Anderson, Francesco Siddi (Blender Foundation)
Ported from Green Room V0.7.0 for standalone PPParty use.

Receives ARKit face tracking data from the Live Link Face iOS app
over UDP and applies it to shape keys on a dummy mesh in Blender.
Head rotation also feeds an armature bone for body movement.
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
        # Bigger receive buffer for busy WiFi — prevents packet drops
        # when other phones/devices share the travel router network
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

        # Lazy-cache shape key blocks and pose bone (avoids per-frame lookups)
        if self._cached_key_blocks is None:
            dummy = bpy.data.objects.get(DUMMY_MESH_NAME)
            if not dummy or not dummy.data.shape_keys:
                return 0.01
            self._cached_key_blocks = dummy.data.shape_keys.key_blocks
            # Cache the pose bone too
            if self._target_armature and self._target_bone:
                arm = self._target_armature
                if arm.type == 'ARMATURE':
                    self._cached_bone = arm.pose.bones.get(self._target_bone)

        # Swap pending dict — O(1) instead of copying
        with self._lock:
            updates = self._pending
            self._pending = {}

        if not updates:
            return 0.01

        key_blocks = self._cached_key_blocks

        # Apply shape key values (each key appears once — latest value only)
        for name, value in updates.items():
            if name == '_head_rotation':
                continue
            kb = key_blocks.get(name)
            if kb:
                kb.value = value

        # Apply head rotation
        head_euler = updates.get('_head_rotation')
        if head_euler and self._cached_bone:
            self._cached_bone.rotation_euler = mathutils.Euler(head_euler, 'XYZ')

        # Push face tracking + head rotation directly to GN modifier
        # (bypasses Blender drivers — works on 5.2 where driver paths changed)
        self._push_to_puppet(updates)

        # Refresh viewport at ~30fps
        now = time.time()
        if now - self._last_redraw_time > 0.033:
            self._last_redraw_time = now
            for window in bpy.context.window_manager.windows:
                for area in window.screen.areas:
                    if area.type == 'VIEW_3D':
                        area.tag_redraw()

        return 0.01  # 10ms timer interval

    def _push_to_puppet(self, updates):
        """Push tracking data directly to PPParty GN modifier inputs.

        Blender 5.2 changed modifier properties from IDProperties to RNA.
        This method probes multiple access strategies on first call:
          1. RNA attributes (Blender 5.2+)
          2. IDProperty access (Blender 5.0)
          3. Interface default_value (last resort — changes the node group)
        After every write batch, calls update_tag() to force re-evaluation.
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
            self._iface_map = {}

            shape_names = set(BLENDSHAPE_MAP.values())
            for item in mod.node_group.interface.items_tree:
                if (hasattr(item, 'item_type')
                        and item.item_type == 'SOCKET'
                        and item.in_out == 'INPUT'
                        and item.socket_type == 'NodeSocketFloat'):
                    if item.name in shape_names:
                        self._face_socket_ids[item.name] = item.identifier
                        self._iface_map[item.name] = item
                    elif item.name.startswith('headRot'):
                        self._rot_socket_ids[item.name] = item.identifier
                        self._iface_map[item.name] = item

            # --- Probe: discover correct access method ---
            self._write_method = None
            probe_log = []

            # Collect ALL RNA float properties (no filter by name)
            rna_float_props = {}
            for prop in mod.rna_type.properties:
                if prop.type == 'FLOAT' and not prop.is_readonly:
                    rna_float_props[prop.identifier] = prop

            probe_log.append(f"RNA float props: {list(rna_float_props.keys())[:10]}")

            # Attempt RNA match: try mapping socket identifiers to RNA props
            if rna_float_props:
                self._rna_map = {}
                all_ids = {}
                all_ids.update(self._face_socket_ids)
                all_ids.update(self._rot_socket_ids)

                for iface_name, iface_id in all_ids.items():
                    # Try many naming variants
                    candidates = [
                        iface_id,                             # Socket_1
                        iface_id.lower(),                     # socket_1
                        iface_id.lower().replace('-', '_'),   # socket-1 → socket_1
                        iface_name,                           # jawOpen
                        iface_name.lower(),                   # jawopen
                        # snake_case of camelCase name
                        ''.join(
                            f'_{c.lower()}' if c.isupper() else c
                            for c in iface_name
                        ).lstrip('_'),                        # jaw_open
                    ]
                    for candidate in candidates:
                        if candidate in rna_float_props:
                            self._rna_map[iface_name] = candidate
                            break

                if self._rna_map:
                    self._write_method = 'rna'
                    probe_log.append(
                        f"Using RNA: {len(self._rna_map)} mapped")
                    for k, v in list(self._rna_map.items())[:3]:
                        probe_log.append(f"  {k} → mod.{v}")

            # Attempt IDProperty access (Blender 5.0 style)
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

            # Last resort: write directly to interface default_value
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
                probe_log.append("WARNING — no working access method!")

            # Write probe results to Text block (visible in Blender UI)
            self._write_probe_log(probe_log)

        mod = self._cached_puppet_mod
        if not self._write_method:
            return

        wrote_any = False

        # --- Push face tracking values ---
        for name, value in updates.items():
            if name == '_head_rotation':
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

        # --- Push head rotation ---
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

        # Force Blender to re-evaluate the modifier after writing values
        if wrote_any and self._cached_puppet_obj:
            self._cached_puppet_obj.update_tag()

    @staticmethod
    def _write_probe_log(lines):
        """Write probe diagnostic to Blender Text Editor block."""
        text_name = "PPParty_Probe"
        if text_name in bpy.data.texts:
            bpy.data.texts.remove(bpy.data.texts[text_name])
        text = bpy.data.texts.new(text_name)
        text.write("PPParty OSC Probe Results\n")
        text.write(f"Blender {bpy.app.version_string}\n\n")
        for line in lines:
            text.write(line + "\n")
