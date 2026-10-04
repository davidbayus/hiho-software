"""
QUADRE — the engine, run as a small program of its own.

Blender starts this file with its bundled Python, one process per engine
step. If the engine hangs or crashes, this process is what stops — not
Blender. Nothing here imports bpy.

    python engine_runner.py <seconds> <ready file> rebuild <mesh.obj>
    python engine_runner.py <seconds> <ready file> layout <mesh.obj> <target faces>

The ready file is written once the engine libraries have loaded: without
it, Blender knows the engine never got going here and runs it inside
Blender instead. A failure the engine itself reports goes to
<ready file>.error as one plain line.

See child.py (the side that starts and watches this) and
QUADRE_PHASE1_DESIGN_2026-10-03.md.
"""

import importlib
import os
import sys
import threading
import time
import types

EXIT_DONE = 0
EXIT_ENGINE_ERROR = 2
EXIT_NO_ENGINE = 3
EXIT_TIME_LIMIT = 4
EXIT_ORPHANED = 5


def _watch(seconds, parent):
    """Stop this process when its time is up, or when Blender is gone.

    Runs on its own thread: the engine call blocks the main one, and
    os._exit is the only way out of a native call that never returns.
    """
    deadline = time.monotonic() + seconds
    while True:
        time.sleep(0.5)
        if time.monotonic() > deadline:
            os._exit(EXIT_TIME_LIMIT)
        # POSIX hands an orphan to another parent; Windows keeps the old
        # number, and there the deadline alone ends an orphan
        if os.name == 'posix' and os.getppid() != parent:
            os._exit(EXIT_ORPHANED)


def main(argv):
    seconds, ready_path, step, mesh_path = float(argv[0]), argv[1], argv[2], argv[3]
    threading.Thread(target=_watch, args=(seconds, os.getppid()), daemon=True).start()

    # Windows: the engine needs the C++ runtime, which Blender ships next
    # to its own program file rather than next to this Python
    host_dir = os.environ.get('QUADRE_HOST_DIR')
    if host_dir and hasattr(os, 'add_dll_directory'):
        for folder in (host_dir, os.path.join(host_dir, 'blender.crt')):
            if os.path.isdir(folder):
                os.add_dll_directory(folder)

    # The add-on's own package starts by importing bpy, which this Python
    # does not have. A stand-in package over the same folder lets the engine
    # modules (and their relative imports) load without it
    here = os.path.dirname(os.path.abspath(__file__))
    package = types.ModuleType('quadre_engine')
    package.__path__ = [here]
    sys.modules['quadre_engine'] = package
    stages = importlib.import_module('quadre_engine.stages')
    lib = importlib.import_module('quadre_engine.lib')

    try:
        qw = lib.Quadwild(mesh_path)
    except lib.EngineLoadError:
        return EXIT_NO_ENGINE
    with open(ready_path, 'w') as f:
        f.write('ready\n')

    try:
        if step == 'rebuild':
            stages.rebuild(qw)
        elif step == 'layout':
            stages.layout(qw, int(argv[4]))
        else:
            raise stages.EngineError(f"unknown engine step {step}")
    except Exception as e:
        with open(ready_path + '.error', 'w') as f:
            f.write(str(e).replace('\n', ' ') + '\n')
        return EXIT_ENGINE_ERROR
    return EXIT_DONE


if __name__ == '__main__':
    code = main(sys.argv[1:])
    # Straight out: nothing the engine left behind gets a chance to stall
    # or crash an ordinary interpreter shutdown. The engine's own printout
    # is flushed to the log first where that is simple
    sys.stdout.flush()
    if os.name == 'posix':
        try:
            import ctypes
            ctypes.CDLL(None).fflush(None)
        except Exception:
            pass
    os._exit(code)
