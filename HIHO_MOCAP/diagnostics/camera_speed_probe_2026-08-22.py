"""Per-camera REAL frame-rate probe for the HIHO ring (2026-08-22).

Why: the frame-count recorder waits for every camera to deliver N frames, so a camera running at
25 fps makes a 60 s take last 150 s and its footage is out of time with the others. This probe opens
each camera exactly the way the recorder does (MJPG, 1280x720, 60 fps requested) and measures how many
frames it actually delivers in a fixed wall-clock window, first each camera ALONE, then ALL AT ONCE.
  alone slow + together slow  -> that camera: dark view (auto-exposure caps fps), camera, or cable
  alone fine  + together slow  -> the hub/port it shares (bandwidth or power)
Also prints mean brightness (0-255) of the frames: C922s drop to ~30 fps in dim light.

Usage (freemocap env, from Terminal so camera permission is granted):
  python camera_speed_probe_2026-08-22.py [--cameras 0,1,2,3,4,5] [--seconds 4] [--out result.txt]
"""
import argparse, sys, time, threading
import cv2, numpy as np

ap = argparse.ArgumentParser()
ap.add_argument("--cameras", default="0,1,2,3,4,5")
ap.add_argument("--seconds", type=float, default=4.0)
ap.add_argument("--out", default=None)
a = ap.parse_args()
cams = [int(x) for x in a.cameras.split(",") if x.strip() != ""]
lines = []
def say(s=""):
    print(s, flush=True); lines.append(s)

def open_cam(i):
    cap = cv2.VideoCapture(i, cv2.CAP_AVFOUNDATION)
    if not cap.isOpened():
        return None
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    cap.set(cv2.CAP_PROP_FPS, 60)
    for _ in range(10):
        cap.read()
    return cap

def measure(cap, seconds):
    n = 0; bright = []; t0 = time.perf_counter()
    while time.perf_counter() - t0 < seconds:
        ok, f = cap.read()
        if ok:
            n += 1
            if n % 15 == 0:
                bright.append(float(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY).mean()))
    dt = time.perf_counter() - t0
    return n / dt, (float(np.mean(bright)) if bright else float("nan"))

def verdict(fps):
    if fps >= 50: return "OK 60"
    if fps >= 24: return "SLOW ~30 (dim light / hub?)"
    return "BAD"

say(f"HIHO camera speed probe  cameras={cams}  window={a.seconds}s each")
say("")
say("PASS 1 - each camera ALONE")
alone = {}
for i in cams:
    cap = open_cam(i)
    if cap is None:
        say(f"  cam {i}: could not open"); alone[i] = (0.0, float('nan')); continue
    w, h = int(cap.get(3)), int(cap.get(4))
    fps, br = measure(cap, a.seconds); cap.release()
    alone[i] = (fps, br)
    say(f"  cam {i}: {fps:5.1f} fps  brightness {br:5.1f}  {w}x{h}  -> {verdict(fps)}")

say("")
say("PASS 2 - ALL cameras at once (the recording condition)")
caps = {}
for i in cams:
    c = open_cam(i)
    if c is not None: caps[i] = c
res = {}
def worker(i, cap):
    res[i] = measure(cap, a.seconds)
ths = [threading.Thread(target=worker, args=(i, c)) for i, c in caps.items()]
for t in ths: t.start()
for t in ths: t.join()
for c in caps.values(): c.release()
for i in cams:
    if i not in res:
        say(f"  cam {i}: could not open"); continue
    fps, br = res[i]
    say(f"  cam {i}: {fps:5.1f} fps  brightness {br:5.1f}  -> {verdict(fps)}")

say("")
say("READING")
for i in cams:
    fa = alone.get(i, (0, 0))[0]; ft = res.get(i, (0, 0))[0]
    if fa >= 50 and ft >= 50: continue
    if fa < 50 and ft < 50:
        say(f"  cam {i}: slow even alone -> look at the camera itself: dim view (brightness {alone[i][1]:.0f}), the camera, or its cable")
    elif fa >= 50 and ft < 50:
        say(f"  cam {i}: fine alone, slow with the others -> the hub/port it shares")
say("done")
if a.out:
    open(a.out, "w").write("\n".join(lines) + "\n")
