import numpy as np, cv2, tomllib, glob, sys, warnings; warnings.filterwarnings("ignore")
from aniposelib.cameras import CameraGroup
d = sys.argv[1]
toml = glob.glob(d+"/*camera_calibration.toml")[0]
raw = np.load(glob.glob(d+"/output_data/raw_data/charuco_2d*.npy")[0], allow_pickle=True)
p2 = np.array(raw.tolist(), dtype=float); n_c,n_f,n_p,_ = p2.shape
det = np.isfinite(p2[...,0]).all(axis=2); ncam = det.sum(axis=0)
print("cams", n_c, "| frames", n_f, "| det% per cam", (det.mean(axis=1)*100).round(0).tolist(), "| frames >=3 cams", int((ncam>=3).sum()), "| >=4", int((ncam>=4).sum()), "| >=5", int((ncam>=5).sum()), "| 6", int((ncam>=6).sum()))
print("floor-shot frames seen per cam:", [int(det[i][:300].sum()) for i in range(n_c)], "/300")
cg = CameraGroup.load(toml); flat = p2.reshape(n_c, n_f*n_p, 2)
p3 = cg.triangulate(flat, progress=False); e = np.linalg.norm(cg.reprojection_error(p3, flat, mean=False), axis=2)
seen = np.isfinite(flat[...,0]); use = seen.sum(axis=0) >= 3
per = [float(np.nanmedian(e[c][seen[c]&use])) for c in range(n_c)]; allv = e[:,use][seen[:,use]]
print("CROSS-CAMERA (anipose) median px per cam:", np.round(per,2).tolist(), "| overall median %.2f  mean %.2f" % (np.nanmedian(allv), np.nanmean(allv)))
co = det.astype(int) @ det.astype(int).T; print("co-visibility:"); print(co)
cal = tomllib.load(open(toml,"rb")); rows=[]
for k in [k for k in cal if k.startswith("cam_")]:
    R,_ = cv2.Rodrigues(np.array(cal[k]["rotation"],float)); t=np.array(cal[k]["translation"],float); C=-R.T@t/1000
    rows.append((np.degrees(np.arctan2(C[1],C[0]))%360, k, np.hypot(C[0],C[1]), C[2]))
print("ring:", [f"{k} az{az:.0f} {dd:.2f}m {h:.2f}m high" for az,k,dd,h in sorted(rows)])
