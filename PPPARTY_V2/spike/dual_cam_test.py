#!/usr/bin/env python3
"""Dual-camera mocap test launcher (BASEMENT experiment, 2026-04-30).

Spawns Pass 1 (body+hands) on Cam 1 AND Pass 2 (arms+hands) on Cam 2 at
the same time, on different UDP ports so they don't collide. Watch the
two preview windows side by side: each shows its own FPS readout.

This is a SPIKE — not part of the V2 build pipeline. Goal:
  1. Compute test — does M3 hold 30fps with 2 full senders running?
  2. Noise test — is Cam 2's hand data visibly cleaner than Cam 1's,
     especially when Cam 2 is positioned specifically for hands
     (lower, narrower FOV, table-mounted)?

Usage:
    python3 spike/dual_cam_test.py
    python3 spike/dual_cam_test.py --cam1 0 --cam2 1
    python3 spike/dual_cam_test.py --no-preview         # FPS in stdout only

Ctrl-C stops both senders cleanly.
"""
import argparse
import signal
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent  # PPPARTY_V2 root
SENDER_BODY = HERE / "mediapipe_sender.py"
SENDER_ARMSHANDS = HERE / "hand_sender.py"


def main():
    p = argparse.ArgumentParser(description="Dual-camera mocap spike")
    p.add_argument("--cam1", type=int, default=0,
                   help="Cam 1 index (body+hands sender). Default 0 = built-in.")
    p.add_argument("--cam2", type=int, default=1,
                   help="Cam 2 index (arms+hands sender). Default 1 = first USB cam.")
    p.add_argument("--port1", type=int, default=11111,
                   help="UDP port for Cam 1 sender.")
    p.add_argument("--port2", type=int, default=11113,
                   help="UDP port for Cam 2 sender. Default 11113 (NOT 11112) to "
                        "avoid colliding with hand_sender's normal port if a "
                        "receiver is also running.")
    p.add_argument("--no-preview", action="store_true",
                   help="Run both senders headless. FPS still printed to stdout.")
    args = p.parse_args()

    if not SENDER_BODY.exists():
        print(f"ERROR: {SENDER_BODY} not found.", file=sys.stderr)
        sys.exit(1)
    if not SENDER_ARMSHANDS.exists():
        print(f"ERROR: {SENDER_ARMSHANDS} not found.", file=sys.stderr)
        sys.exit(1)

    cmd_body = [sys.executable, str(SENDER_BODY),
                "--camera", str(args.cam1),
                "--port", str(args.port1)]
    cmd_arms = [sys.executable, str(SENDER_ARMSHANDS),
                "--camera", str(args.cam2),
                "--port", str(args.port2)]
    if args.no_preview:
        cmd_body.append("--no-preview")
        cmd_arms.append("--no-preview")

    print(f"Cam {args.cam1}: Pass 1 (body + hands)   → UDP 127.0.0.1:{args.port1}")
    print(f"Cam {args.cam2}: Pass 2 (arms + hands)   → UDP 127.0.0.1:{args.port2}")
    print(f"Ctrl-C to stop both.\n")

    p_body = subprocess.Popen(cmd_body)
    time.sleep(0.7)  # let Cam 1 grab the camera before Cam 2 tries
    p_arms = subprocess.Popen(cmd_arms)

    try:
        while True:
            time.sleep(1)
            if p_body.poll() is not None:
                print("Body sender exited.")
                break
            if p_arms.poll() is not None:
                print("Arms+hands sender exited.")
                break
    except KeyboardInterrupt:
        print("\nStopping both senders...")
    finally:
        for name, proc in (("body", p_body), ("arms+hands", p_arms)):
            if proc.poll() is None:
                proc.send_signal(signal.SIGINT)
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    print(f"{name} sender didn't stop cleanly — killing.")
                    proc.kill()


if __name__ == "__main__":
    main()
