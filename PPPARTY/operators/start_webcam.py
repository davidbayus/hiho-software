"""Start Webcam — launches MediaPipe sender and tracking receiver."""

import os
import subprocess
import sys

import bpy


# Track the sender subprocess so we can kill it on disconnect
_sender_process = None


def _find_sender_script():
    """Locate mediapipe_sender.py relative to the addon."""
    addon_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(addon_dir, "mediapipe_sender.py")


def _find_system_python():
    """Find a system Python 3 that can run MediaPipe.

    Blender's bundled Python doesn't have mediapipe/opencv installed,
    so we need the system Python. Checks common locations.

    Search order:
      1. venv next to addon (development installs)
      2. ~/.ppparty/venv (user-level, works with zip-installed addon)
      3. System Python (python.org, Homebrew, macOS system)
    """
    candidates = []

    # venv next to addon (development install — addon run from source)
    addon_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    venv_python = os.path.join(addon_dir, "venv", "bin", "python3")
    candidates.append(venv_python)

    # User-level venv (works when addon is zip-installed into Blender)
    home_venv = os.path.join(os.path.expanduser("~"), ".ppparty",
                             "venv", "bin", "python3")
    candidates.append(home_venv)

    # Common system Python locations
    if sys.platform == "darwin":
        candidates += [
            "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12",
            "/Library/Frameworks/Python.framework/Versions/3.11/bin/python3.11",
            "/Library/Frameworks/Python.framework/Versions/3.10/bin/python3.10",
            "/usr/local/bin/python3.12",
            "/usr/local/bin/python3.11",
            "/usr/local/bin/python3",
            "/opt/homebrew/bin/python3",
            "/usr/bin/python3",
        ]
    elif sys.platform == "win32":
        candidates += [
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Python\Python312\python.exe"),
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Python\Python311\python.exe"),
            "python",
        ]
    else:  # linux
        candidates += [
            "/usr/bin/python3",
            "/usr/local/bin/python3",
        ]

    # Require execute permission — zip extraction strips the +x bit from
    # bundled venv pythons, leaving a non-executable file at a path that
    # `os.path.exists()` would happily return. Checking X_OK skips those
    # and falls through to a working system Python.
    for path in candidates:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path

    # Last resort: hope "python3" is on PATH
    return "python3"


class PPPARTY_OT_start_webcam(bpy.types.Operator):
    """Start face + body tracking from your webcam"""

    bl_idname = "ppparty.start_webcam"
    bl_label = "Start Webcam"

    def execute(self, context):
        global _sender_process
        from .. import receiver
        from ..core.osc_receiver import ensure_dummy_mesh

        if receiver.is_running:
            self.report({'WARNING'}, "Already tracking!")
            return {'CANCELLED'}

        # Verify sender script exists
        sender_script = _find_sender_script()
        if not os.path.isfile(sender_script):
            self.report({'ERROR'}, f"Cannot find mediapipe_sender.py")
            return {'CANCELLED'}

        # Make sure the dummy mesh exists
        ensure_dummy_mesh()

        settings = context.scene.ppparty
        port = settings.pp_port

        # Find the PPParty armature with a "head" bone
        target_armature = None
        target_bone = None
        for obj in context.scene.objects:
            if obj.type == 'ARMATURE' and obj.name.startswith('PP_'):
                for bone in obj.data.bones:
                    if bone.name == 'head':
                        target_armature = obj
                        target_bone = 'head'
                        break
                if target_armature:
                    break

        # Start the receiver first (binds the UDP port)
        if not receiver.start(port=port,
                              target_armature=target_armature,
                              target_bone=target_bone):
            self.report({'ERROR'}, f"Could not start -- port {port} in use")
            return {'CANCELLED'}

        # Mark source immediately so the panel shows webcam UI
        # (otherwise it shows "Waiting for phone" until first packet)
        receiver._source = 'mediapipe'

        # Launch the MediaPipe sender as a separate process
        python_path = _find_system_python()
        show_preview = settings.pp_show_preview
        cmd = [
            python_path, sender_script,
            "--port", str(port),
        ]
        if not show_preview:
            cmd.append("--no-preview")

        try:
            _sender_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.report({'INFO'},
                        f"Webcam tracking started (port {port})")
        except FileNotFoundError:
            receiver.stop()
            self.report({'ERROR'},
                        f"Python not found at {python_path}. "
                        "Install Python 3 with mediapipe and opencv-python.")
            return {'CANCELLED'}
        except Exception as e:
            receiver.stop()
            self.report({'ERROR'}, f"Could not start sender: {e}")
            return {'CANCELLED'}

        # Force panel redraw
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()

        return {'FINISHED'}


class PPPARTY_OT_stop_webcam(bpy.types.Operator):
    """Stop webcam tracking and kill the sender process"""

    bl_idname = "ppparty.stop_webcam"
    bl_label = "Stop Webcam"

    def execute(self, context):
        global _sender_process
        from .. import receiver

        killed = 0

        # Kill the sender subprocess we launched
        if _sender_process is not None:
            try:
                _sender_process.terminate()
                _sender_process.wait(timeout=3)
                killed += 1
            except Exception:
                try:
                    _sender_process.kill()
                    killed += 1
                except Exception:
                    pass
            _sender_process = None

        # Also kill any orphaned mediapipe_sender processes (e.g. from
        # a previous Blender session that didn't clean up).
        killed += _kill_orphaned_senders()

        # Stop the receiver
        receiver.stop()

        msg = "Webcam tracking stopped"
        if killed:
            msg += f" ({killed} process{'es' if killed > 1 else ''} killed)"
        self.report({'INFO'}, msg)

        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()

        return {'FINISHED'}


def _kill_orphaned_senders():
    """Find and kill any mediapipe_sender.py processes left over from
    a previous session.  Returns the number of processes killed."""
    import signal
    killed = 0
    try:
        # Get PIDs of any running mediapipe_sender.py
        result = subprocess.run(
            ["pgrep", "-f", "mediapipe_sender.py"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            for line in result.stdout.strip().splitlines():
                pid = int(line.strip())
                try:
                    os.kill(pid, signal.SIGTERM)
                    killed += 1
                except (ProcessLookupError, PermissionError):
                    pass
    except Exception:
        pass
    return killed
