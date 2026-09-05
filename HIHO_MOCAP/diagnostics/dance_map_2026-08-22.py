"""Draw the calibration dance map (top view of the ring) from a solved calibration toml, with
cameras named by LETTER (the physical labels on the arms), not by software index.

Why: Camera_0..5 reshuffle with USB order, so "cam 3" means a different camera in different takes.
Letters are fixed identities taped on the camera bodies (David, applied 2026-09-05): one letter per camera,
A..F, no high/low suffix because heights change. They were assigned ONCE, by position around the ring
going CLOCKWISE from the open (camera-free) sector (verified against the tape 2026-09-05). The script
re-derives the same order from any later solve, which matches the tape as long as the cameras keep their
ORDER around the ring. If two cameras ever swap places, pass --letters "cam_0=C,cam_1=A,..." to override.
The map is always oriented with the open sector on the RIGHT, so it looks the same across takes
even though each solve's world frame follows wherever the floor board was laid.

Run inside the freemocap env:
  python dance_map_2026-08-22.py <take_folder_or_toml> [--out map.png] [--landmarks "name@deg,..."]
                                 [--letters "cam_0=C,..."] [--no-stops]
Prints the index -> letter translation table for the take (paste it into the handoff).
Landmarks are given as "label@bearing" separated by semicolons, where bearing is degrees counter-clockwise from the open
sector's centre line (the BASEMENT defaults below were read off the 08-21 map).
"""
import argparse, glob, os, tomllib
import numpy as np, cv2
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

BASEMENT_LANDMARKS = "DESK, CHAIR, PAINTING@60; COPIER + clothes rack@125; RED POSTER + silkscreen frames@215; white wall with WOODEN CABINET@300; POSTERS + DESKS@10"

ap = argparse.ArgumentParser()
ap.add_argument("take"); ap.add_argument("--out", default=None)
ap.add_argument("--landmarks", default=BASEMENT_LANDMARKS)
ap.add_argument("--letters", default=None, help='override, e.g. "cam_0=C,cam_1=A" (only when cameras changed ORDER around the ring)')
ap.add_argument("--no-stops", action="store_true", help="draw cameras + landmarks only, no numbered stops")
a = ap.parse_args()
toml_path = a.take if a.take.endswith(".toml") else glob.glob(os.path.join(a.take, "*_camera_calibration.toml"))[0]
take_name = os.path.basename(os.path.dirname(os.path.abspath(toml_path))) if not a.take.endswith(".toml") else os.path.basename(toml_path)
cal = tomllib.load(open(toml_path, "rb"))
keys = sorted([k for k in cal if k.startswith("cam_")], key=lambda k: int(k.split("_")[1]))

# camera centres + forward directions in the solve's world frame (metres)
C, F = [], []
for k in keys:
    R, _ = cv2.Rodrigues(np.array(cal[k]["rotation"], float)); t = np.array(cal[k]["translation"], float)
    C.append(-R.T @ t / 1000.0); F.append(R.T @ np.array([0, 0, 1.0]))
C, F = np.array(C), np.array(F)
n = len(C)

# sweet spot = point in the 1 m plane the cameras collectively aim at (least-squares yaw, grid search)
def yaw(c, f, p):
    to = p - c; f2 = f[:2] / np.linalg.norm(f[:2]); c2 = to[:2] / np.linalg.norm(to[:2])
    return np.degrees(np.arctan2(f2[0] * c2[1] - f2[1] * c2[0], f2 @ c2))
c0 = C.mean(axis=0); best = None
for dx in np.arange(-2, 2.01, 0.05):
    for dy in np.arange(-2, 2.01, 0.05):
        p = np.array([c0[0] + dx, c0[1] + dy, 1.0]); s = sum(yaw(C[i], F[i], p) ** 2 for i in range(n))
        if best is None or s < best[0]: best = (s, p)
spot = best[1]

# bearings around the sweet spot; open sector = largest gap; rotate so its centre line points RIGHT (0 deg)
bear = np.degrees(np.arctan2(C[:, 1] - spot[1], C[:, 0] - spot[0])) % 360
order = np.argsort(bear); b = bear[order]
gaps = np.diff(np.concatenate([b, [b[0] + 360]])); g = int(gaps.argmax()); open_centre = (b[g] + gaps[g] / 2) % 360
rel = (bear - open_centre) % 360                      # counter-clockwise from the open sector centre line
# letters: one per camera, walking CLOCKWISE from the open sector (A, B, C, ...). Flipped 2026-09-05:
# David's tape (applied that day) runs clockwise; the counter-clockwise rule gave six wrong letters.
seq = np.argsort((-rel) % 360); letters = {i: chr(ord("A") + k) for k, i in enumerate(seq)}
if a.letters:
    for item in a.letters.split(","):
        k, L = item.split("="); letters[keys.index(k.strip())] = L.strip()
band = lambda h: "high" if h >= 1.65 else ("low" if h < 1.1 else "mid")
col = {"high": "#1f77e0", "mid": "#e0a020", "low": "#22a55a"}

# ---- table ----
print(f"{take_name}: open sector {gaps[g]:.0f} deg wide; sweet spot {np.linalg.norm(spot[:2]):.2f} m from the floor-board origin")
print("index  letter   height  dist-from-spot  aim-off")
for i in seq:
    print(f"{keys[i]:6s} {letters[i]:8s} {C[i,2]:5.2f} m   {np.linalg.norm(spot - C[i]):4.2f} m        {abs(yaw(C[i], F[i], spot)):4.1f} deg")

# ---- drawing ----
fig, ax = plt.subplots(figsize=(15, 10)); ax.set_aspect("equal"); ax.axis("off")
Rr = 1.0  # drawing ring radius (normalised)
for i in range(n):
    th = np.radians(rel[i]); d = np.linalg.norm(spot[:2] - C[i, :2]); r = Rr * min(1.25, max(0.6, d / 1.8))
    x, y = r * np.cos(th), r * np.sin(th); hb = band(C[i, 2])
    ax.add_patch(plt.Circle((x, y), 0.1, color=col[hb], zorder=3))
    ax.text(x, y, letters[i], ha="center", va="center", color="white", fontsize=14, fontweight="bold", zorder=4)
    ax.text(x, y - 0.17, f"{C[i,2]:.1f} m high", ha="center", va="top", fontsize=9, color="#444")
# open sector wedge
ax.add_patch(matplotlib.patches.Wedge((0, 0), 1.35, -gaps[g] / 2, gaps[g] / 2, color="#eeeeee", zorder=0))
ax.text(0.85, 0, "no cameras\n(open side)", ha="center", va="center", color="#888", fontsize=11)
ax.add_patch(plt.Circle((0, 0), 1.35, fill=False, ls="--", color="#bbb", zorder=0))
ax.add_patch(plt.Rectangle((-0.26, -0.14), 0.52, 0.28, color="black", zorder=3)); ax.text(0, 0, "BOARD\nyou stand here", color="white", ha="center", va="center", fontsize=10, fontweight="bold", zorder=4)
# landmarks
for item in [s for s in a.landmarks.split(";") if "@" in s]:
    name, deg = item.rsplit("@", 1); th = np.radians(float(deg))
    ax.text(1.75 * np.cos(th), 1.75 * np.sin(th), name.strip(), ha="center", va="center", fontsize=11, fontweight="bold", color="#8b0000",
            bbox=dict(boxstyle="round", fc="white", ec="#8b0000"))
# stops: one per camera, pointing the board's face at it
if not a.no_stops:
    stops = [(np.radians(rel[i]), letters[i]) for i in seq]
    for k, (th, L) in enumerate(stops):
        ax.annotate("", xy=(0.45 * np.cos(th), 0.45 * np.sin(th)), xytext=(0.22 * np.cos(th), 0.22 * np.sin(th)), arrowprops=dict(arrowstyle="->", lw=1.5))
        ax.add_patch(plt.Circle((0.55 * np.cos(th), 0.55 * np.sin(th)), 0.06, color="yellow", ec="black", zorder=3))
        ax.text(0.55 * np.cos(th), 0.55 * np.sin(th), str(k + 1), ha="center", va="center", fontsize=10, fontweight="bold", zorder=4)
low2 = sorted(range(n), key=lambda i: C[i, 2])[:2]; low_names = " and ".join(sorted(letters[i] for i in low2))
ax.set_xlim(-2.4, 3.9); ax.set_ylim(-2.0, 2.0)
ax.text(2.45, 1.8, f"{take_name}\nring top view, from this solve", fontsize=14, fontweight="bold", va="top")
ax.text(2.45, 1.3, "Blue = high camera, orange = mid, green = low.\nLetters = the labels taped on the cameras.\nRed boxes = what you see on the walls.\n"
        f"Yellow stops: face the board at that camera.\n\nDANCE: floor shot, 5 s, laid close to the two\nlow cameras ({low_names}): once toward each.\n"
        "Then pick it up and walk the stops SLOWLY,\n60 s total. At every stop: nod the board\nup / level / down and swing it side to side.\nNever hold it still and face-on; tilting is\nwhat teaches the solver each lens.",
        fontsize=10.5, va="top", family="monospace")
out = a.out or os.path.join(os.path.dirname(os.path.abspath(toml_path)), f"DANCE_MAP_{take_name}.png")
fig.savefig(out, dpi=120, bbox_inches="tight"); print("wrote", out)
