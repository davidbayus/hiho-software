"""
QUADRE — starting and watching the engine as a separate program.

Each engine step runs in a process of its own (engine_runner.py, started
with Blender's bundled Python). That buys three things the engine cannot
give from inside Blender:

  - a hang is stopped after TIME_LIMIT instead of freezing Blender;
  - a crash ends the child, not Blender;
  - Esc stops the work at once, and several layouts can run side by side.

No Blender calls here: this runs on the worker thread.
See QUADRE_PHASE1_DESIGN_2026-10-03.md.
"""

import os
import subprocess
import sys
import time

from .stages import EngineError


# A child still running after this many seconds is stuck. Honest runs take
# seconds (the slowest step on the eleven benchmark shapes: under 10 s on
# this laptop); the hangs this guards against never return at all
TIME_LIMIT = 300.0

RUNNER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine_runner.py")

# engine_runner.py's exit codes
EXIT_DONE = 0
EXIT_ENGINE_ERROR = 2
EXIT_TIME_LIMIT = 4


class Unavailable(Exception):
    """The engine could not be run as a separate program on this computer."""


class Stuck(Exception):
    """The engine ran past the time limit and was stopped."""


class Stopped(Exception):
    """The work was called off (Esc)."""


class _Child:
    def __init__(self, step, host_dir, time_limit):
        name, mesh_path = step[0], step[1]
        base = os.path.splitext(mesh_path)[0]
        self.ready_path = f"{base}.{name}.ready"
        self.error_path = self.ready_path + ".error"
        for stale in (self.ready_path, self.error_path):
            if os.path.exists(stale):
                os.remove(stale)
        env = dict(os.environ)
        env['QUADRE_HOST_DIR'] = host_dir
        # The child also stops itself, a little after this side would have
        # stopped it: an orphan cannot run on
        command = [
            sys.executable, "-I", RUNNER,
            str(time_limit + 10.0), self.ready_path, *[str(part) for part in step],
        ]
        self.log = open(f"{base}.{name}.log", "w")
        self.started = time.monotonic()
        try:
            self.process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL, stdout=self.log, stderr=subprocess.STDOUT,
                env=env,
                # Windows: no console window flashing up per step
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
            )
        except OSError:
            self.log.close()
            raise

    def stop(self):
        if self.process.poll() is None:
            self.process.kill()
        self.process.wait()
        self.log.close()

    def outcome(self, code):
        """None when the step finished; otherwise the exception that says why not."""
        self.log.close()
        if not os.path.exists(self.ready_path):
            return Unavailable(f"the engine did not start there (exit code {code})")
        if code == EXIT_DONE:
            return None
        if code == EXIT_TIME_LIMIT:
            return Stuck()
        if code == EXIT_ENGINE_ERROR and os.path.exists(self.error_path):
            with open(self.error_path) as f:
                return EngineError(f.read().strip())
        return EngineError("the engine stopped unexpectedly on this shape")


def run_steps(steps, host_dir, should_stop=None, on_done=None, time_limit=None):
    """Run engine steps as separate programs, several at once.

    steps: one (step name, mesh path, extra arguments...) per program.
    Returns one outcome per step: None when it finished, otherwise the
    exception that says why not (EngineError, Stuck, Unavailable).
    Raises Stopped, after stopping every child, when should_stop() says so.
    on_done() is called as each step ends, whatever its outcome.
    """
    if time_limit is None:
        time_limit = TIME_LIMIT
    # One core stays free so Blender itself keeps moving
    at_once = max(1, (os.cpu_count() or 2) - 1)
    waiting = list(enumerate(steps))
    running = {}
    outcomes = [None] * len(steps)

    def ended(index, outcome):
        outcomes[index] = outcome
        if on_done is not None:
            on_done()

    try:
        while waiting or running:
            while waiting and len(running) < at_once:
                index, step = waiting.pop(0)
                try:
                    running[index] = _Child(step, host_dir, time_limit)
                except OSError as e:
                    ended(index, Unavailable(str(e)))
            if should_stop is not None and should_stop():
                raise Stopped()
            for index, child in list(running.items()):
                code = child.process.poll()
                if code is not None:
                    del running[index]
                    ended(index, child.outcome(code))
                elif time.monotonic() - child.started > time_limit:
                    del running[index]
                    child.stop()
                    ended(index, Stuck())
            time.sleep(0.02)
    finally:
        for child in running.values():
            child.stop()
    return outcomes
