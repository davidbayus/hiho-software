"""Cross-camera score of a calibration toml against a take's 2D charuco data, split by frame type:
floor shot (first 5 s), raised-still (board not moving in any camera), moving. Usage: score_split.py <take> <toml> [motion_px]"""
import numpy as np, glob, sys, warnings; warnings.filterwarnings("ignore")
from aniposelib.cameras import CameraGroup
take, toml = sys.argv[1], sys.argv[2]; motion_px = float(sys.argv[3]) if len(sys.argv) > 3 else 0.3
p2 = np.array(np.load(glob.glob(take+"/output_data/raw_data/charuco_2d*.npy")[0], allow_pickle=True).tolist(), dtype=float)
n_c, n_f, n_p, _ = p2.shape
mot = np.full((n_c, n_f), np.nan); mot[:, 1:] = np.nanmedian(np.linalg.norm(p2[:, 1:]-p2[:, :-1], axis=3), axis=2)
moving = (np.nan_to_num(mot, nan=0.0) > motion_px).any(axis=0)
cat = np.full(n_f, "moving", dtype=object); cat[~moving] = "still"; cat[:300] = "floor"
cg = CameraGroup.load(toml); flat = p2.reshape(n_c, n_f*n_p, 2)
p3 = cg.triangulate(flat, progress=False); e = np.linalg.norm(cg.reprojection_error(p3, flat, mean=False), axis=2).reshape(n_c, n_f, n_p)
seen = np.isfinite(flat[..., 0]).reshape(n_c, n_f, n_p); use = seen.sum(axis=0) >= 3   # points seen by 3+ cams
print(f"{take.split('/')[-1]}  <-  {toml.split('/')[-1]}")
print(f"  frames: floor {int((cat=='floor').sum())}, raised-still {int((cat=='still').sum())}, moving {int((cat=='moving').sum())}")
for name in ["floor", "still", "moving"]:
    m = (cat == name)[None, :, None] & seen & use[None]
    per = [float(np.nanmedian(e[c][m[c]])) if m[c].any() else float('nan') for c in range(n_c)]
    allv = e[m]
    print(f"  {name:12s} median px per cam {np.round(per,2).tolist()}  overall median {np.nanmedian(allv):.2f}  mean {np.nanmean(allv):.2f}  (n={m.sum()})")
m = seen & use[None]; print(f"  ALL          overall median {np.nanmedian(e[m]):.2f}  mean {np.nanmean(e[m]):.2f}")
