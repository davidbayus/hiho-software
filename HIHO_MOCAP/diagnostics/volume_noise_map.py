"""Noise-vs-position analysis for a perimeter take.
Where in the volume does tracking stay clean, and where does it fray?

Metrics per frame:
  - jitter: median across body joints of ||second difference|| of 3D position (mm).
    Second differencing kills smooth voluntary motion, keeps frame-to-frame noise.
  - reprojection error: mean across tracked points (px).
Position per frame: total-body center of mass (x, y), distance from ring center.
"""
import sys
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

rec = Path(sys.argv[1]).expanduser()
out_png = Path(sys.argv[2]).expanduser()

body = np.load(rec / "output_data" / "mediapipe_body_3d_xyz.npy")          # (F, 33, 3) mm
com = np.load(rec / "output_data" / "center_of_mass" /
              "mediapipe_total_body_center_of_mass_xyz.npy")               # (F, 3) mm
rpe = np.load(rec / "output_data" / "raw_data" /
              "mediapipe_3dData_numFrames_numTrackedPoints_reprojectionError.npy")  # (F, P)

FPS = 60.0
F = body.shape[0]
print(f"frames: {F} ({F/FPS:.1f}s)  joints: {body.shape[1]}")

# ring center from the 2026-07-17 calibration toml (mean of camera world x,y)
CENTER = np.array([-59.0, 180.0])

# --- jitter: second difference magnitude, median over joints, rolling median smooth
d2 = body[2:] - 2 * body[1:-1] + body[:-2]                 # (F-2, 33, 3)
mag = np.linalg.norm(d2, axis=2)                           # (F-2, 33)
frame_jitter = np.nanmedian(mag, axis=1)                   # (F-2,)
frame_jitter = np.concatenate([[np.nan], frame_jitter, [np.nan]])  # re-align to F

def rolling_median(x, w):
    half = w // 2
    out = np.full_like(x, np.nan)
    for i in range(len(x)):
        seg = x[max(0, i - half):i + half + 1]
        if np.any(np.isfinite(seg)):
            out[i] = np.nanmedian(seg)
    return out

jit_s = rolling_median(frame_jitter, 31)                   # ~0.5s window

# --- per-frame mean reprojection error
rpe_frame = np.nanmean(rpe, axis=1)
rpe_s = rolling_median(rpe_frame, 31)

# --- position
xy = com[:, :2]
r = np.linalg.norm(xy - CENTER, axis=1)                    # mm from ring center
vis = np.mean(np.all(np.isfinite(body), axis=2), axis=1)   # fraction of joints present

# --- baseline from opening still beat: lowest-motion 5s window in first 15s
com_speed = np.linalg.norm(np.diff(com[:, :2], axis=0), axis=1)
lim = min(int(15 * FPS), len(com_speed) - int(5 * FPS))
win = int(5 * FPS)
best = min(range(0, lim), key=lambda i: np.nansum(com_speed[i:i + win]))
base_jit = np.nanmedian(jit_s[best:best + win])
base_rpe = np.nanmedian(rpe_s[best:best + win])
base_r = np.nanmedian(r[best:best + win])
print(f"baseline (still, frames {best}-{best+win}, r={base_r:.0f}mm): "
      f"jitter {base_jit:.2f}mm  reproj {base_rpe:.2f}px")

# --- binned by radius
bins = np.arange(0, np.nanmax(r) + 250, 250)
print("\nradius(m)  median_jitter(mm)  xBase  reproj(px)  joints_vis%  time(s)")
rows = []
for lo, hi in zip(bins[:-1], bins[1:]):
    m = (r >= lo) & (r < hi) & np.isfinite(jit_s)
    if m.sum() < 30:
        continue
    mj, mr, mv = np.nanmedian(jit_s[m]), np.nanmedian(rpe_s[m]), np.nanmean(vis[m]) * 100
    rows.append((lo, hi, mj))
    print(f"{lo/1000:.2f}-{hi/1000:.2f}   {mj:8.2f}        {mj/base_jit:4.1f}x  "
          f"{mr:8.2f}     {mv:5.1f}      {m.sum()/FPS:5.1f}")

# clean radius: last bin whose median jitter <= 2x baseline
walk_base = np.nanmedian(jit_s[(r < 500) & np.isfinite(jit_s)])
print(f"central walking jitter (r<0.5m): {walk_base:.2f}mm")
clean = [hi for lo, hi, mj in rows if mj <= 2 * walk_base]
if clean:
    print(f"\nCLEAN RADIUS (jitter <= 2x central walking): ~{max(clean)/1000:.2f} m")
circ = plt.Circle((CENTER[0]/1000, CENTER[1]/1000), max(clean)/1000, fill=False, color="k", ls="--")

# --- figure
cams = np.array([[-364, -1335], [630, -1215], [-881, 1427],
                 [776, 1896], [-2398, 137], [1885, 170]])
fig, axes = plt.subplots(1, 2, figsize=(14, 6))
ax = axes[0]
ok = np.isfinite(jit_s)
sc = ax.scatter(xy[ok, 0] / 1000, xy[ok, 1] / 1000, c=np.clip(jit_s[ok], 0, 8.0),
                s=6, cmap="RdYlGn_r")
ax.scatter(cams[:, 0] / 1000, cams[:, 1] / 1000, marker="s", s=90, c="k", zorder=5)
for i, (cx, cy) in enumerate(cams / 1000):
    ax.annotate(f"cam{i}", (cx, cy), textcoords="offset points", xytext=(6, 6), fontsize=9)
ax.add_patch(circ) if clean else None
ax.set_title("Top-down: your path, colored by jitter\n(green = clean, red = turbulent)")
ax.set_xlabel("x (m)"); ax.set_ylabel("y (m)"); ax.set_aspect("equal")
plt.colorbar(sc, ax=ax, label="jitter (mm/frame², clipped)")

ax = axes[1]
ax.scatter(r[ok] / 1000, jit_s[ok], s=4, alpha=0.3)
if rows:
    ax.plot([(lo + hi) / 2000 for lo, hi, _ in rows], [mj for _, _, mj in rows],
            "r-o", lw=2, label="median per 25cm ring")
ax.axhline(2 * walk_base, color="orange", ls="--", label="2x central walking jitter")
ax.set_title("Jitter vs distance from ring center")
ax.set_xlabel("distance from center (m)"); ax.set_ylabel("jitter (mm/frame²)")
ax.set_ylim(0, np.nanpercentile(jit_s, 98) * 1.3)
ax.legend()
fig.tight_layout()
fig.savefig(out_png, dpi=110)
print(f"\nsaved: {out_png}")
