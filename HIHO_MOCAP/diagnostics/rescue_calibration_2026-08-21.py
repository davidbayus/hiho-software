"""Rescue a calibration solve from an already-tracked board take, WITHOUT re-reading
the videos (FreeMoCap 1.8.2's end-of-tracking video re-read fails transiently under
load: "missing file" / "all input arrays must have the same shape", seen twice on
2026-08-21). Feeds output_data/raw_data/charuco_2d*.npy into the same anipose
calibrate_rows() + charuco ground-plane path FreeMoCap uses. Optional --static-only
drops frames where the board is moving in any camera (the cameras are not frame-
synchronised, so moving frames disagree by 4-8 px; still frames agree to 0.2 px).

Run inside the freemocap env:
  python rescue_calibration_2026-08-21.py <take_folder> [--square-mm 200] [--static-only] [--suffix NAME]
Writes <take>/<take>_camera_calibration[<suffix>].toml + output_data/charuco_3d_xyz[<suffix>].npy
and GROUNDPLANE_STATUS[<suffix>].txt. Does NOT touch ~/freemocap_data.
"""
import argparse, glob, os, sys, warnings
import numpy as np, cv2
warnings.filterwarnings("ignore")

ap = argparse.ArgumentParser()
ap.add_argument("take"); ap.add_argument("--square-mm", type=float, default=200.0)
ap.add_argument("--static-only", action="store_true"); ap.add_argument("--motion-px", type=float, default=0.3)
ap.add_argument("--suffix", default="")
ap.add_argument("--skip-frames", type=int, default=0, help="exclude the first N frames (the floor shot) from the SOLVE; they still feed the ground-plane step")
a = ap.parse_args()
take = os.path.abspath(a.take); name = os.path.basename(take)

from freemocap.core_processes.capture_volume_calibration.anipose_camera_calibration import freemocap_anipose as fa
from freemocap.core_processes.capture_volume_calibration.anipose_camera_calibration.charuco_groundplane_utils import (
    find_good_frame, compute_basis_vectors_of_new_reference, skellyforge_data)
from freemocap.core_processes.capture_volume_calibration.charuco_stuff.charuco_board_definition import charuco_5x3

npy = glob.glob(take + "/output_data/raw_data/charuco_2d*.npy")[0]
p2 = np.array(np.load(npy, allow_pickle=True).tolist(), dtype=np.float64)   # (cams, frames, 8, 2)
n_c, n_f, n_p, _ = p2.shape
vids = sorted(glob.glob(take + "/Camera_*.mp4"))
assert len(vids) == n_c, f"{len(vids)} videos vs {n_c} cameras in the 2D data"
def _probe(path):
    cap = cv2.VideoCapture(path); w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)); h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)); cap.release()
    return w, h
W, H = _probe(vids[0])
if W == 0 or H == 0:   # transient OpenCV read failure (seen 2026-08-22): try the synchronized copy, then the recording info
    W, H = _probe(take + "/synchronized_videos/" + os.path.basename(vids[0]))
if W == 0 or H == 0:
    import json
    info = json.load(open(take + "/HIHO_RECORDING_INFO.json")); W, H = int(info["width"]), int(info["height"])
    print(f"WARNING: videos unreadable right now; frame size taken from HIHO_RECORDING_INFO.json ({W}x{H} before rotation)")
assert W > 0 and H > 0, "could not determine frame size"
# the tracker works on the rotated (portrait) frames; infer orientation from the data extent
if np.nanmax(p2[..., 0]) > W or np.nanmax(p2[..., 1]) > H:
    W, H = H, W
print(f"{name}: {n_c} cams x {n_f} frames, frame size {W}x{H}")

if a.static_only:
    mot = np.full((n_c, n_f), np.nan)
    mot[:, 1:] = np.nanmedian(np.linalg.norm(p2[:, 1:] - p2[:, :-1], axis=3), axis=2)
    moving = np.nan_to_num(mot, nan=0.0) > a.motion_px          # per camera per frame
    drop = moving.any(axis=0)                                   # any camera sees it moving -> drop the frame everywhere
    kept = (~drop).sum()
    p2 = p2.copy(); p2[:, drop] = np.nan
    print(f"static-only: dropped {int(drop.sum())} moving frames, kept {int(kept)}")

p2_all = p2.copy()            # full data for the ground-plane step
if a.skip_frames > 0:
    p2 = p2.copy(); p2[:, :a.skip_frames] = np.nan
    print(f"skip-frames: first {a.skip_frames} frames excluded from the solve")
names = [os.path.splitext(os.path.basename(v))[0] for v in vids]
cg = fa.CameraGroup.from_names(names)
for cam in cg.cameras: cam.set_size((W, H))
bdef = charuco_5x3()
board = fa.AniposeCharucoBoard(bdef.number_of_squares_width, bdef.number_of_squares_height,
                               square_length=a.square_mm, marker_length=a.square_mm * 0.8, marker_bits=4, dict_size=250)
cg.charuco_2d_data = p2
all_rows = []
for c in range(n_c):
    rows = []
    for f in range(n_f):
        filled = p2[c, f].astype(np.float32).reshape(n_p, 1, 2)
        mask = ~np.isnan(filled[:, :, 0]) & ~np.isnan(filled[:, :, 1])
        ids = np.where(mask)[0]
        if len(ids) == 0: continue
        rows.append({"framenum": (0, f), "corners": filled[ids], "ids": ids.reshape(-1, 1), "filled": filled})
    all_rows.append(rows); print(f"  {names[c]}: {len(rows)} frames with corners")
error, merged, frames = cg.calibrate_rows(all_rows, board, init_intrinsics=True, init_extrinsics=True, verbose=False)
print(f"bundle adjust done, anipose error {error:.3f}")

# ground plane, same as FreeMoCap.set_charuco_board_as_groundplane
flat = p2_all.reshape(n_c, -1, 2); p3 = cg.triangulate(flat, progress=False).reshape(n_f, n_p, 3)
p3i = skellyforge_data(raw_charuco_data=p3)
status = ""
try:
    idx = find_good_frame(charuco_data=p3i, number_of_squares_width=5, number_of_squares_height=3)
    fr = p3i[idx]; x_hat, y_hat, z_hat = compute_basis_vectors_of_new_reference(fr, number_of_squares_width=5, number_of_squares_height=3)
    origin = fr[0]; Rcw = np.column_stack([x_hat, y_hat, z_hat])
    tv = np.asarray(cg.get_translations(), dtype=np.float64); rv = np.asarray(cg.get_rotations(), dtype=np.float64)
    tv2 = np.zeros_like(tv); rv2 = np.zeros_like(rv)
    for i in range(len(tv)):
        R, _ = cv2.Rodrigues(rv[i])
        tv2[i] = (R @ origin.reshape(3)) + tv[i].reshape(3)
        rv2[i] = cv2.Rodrigues(R @ Rcw)[0].reshape(3)
    cg.set_rotations(rv2); cg.set_translations(tv2)
    heights = []
    for i in range(len(rv2)):
        R, _ = cv2.Rodrigues(rv2[i]); C = -R.T @ tv2[i]; heights.append(C[2] / 1000.0)
    status = "OK: origin and up-axis set from the board's opening floor position; cameras above floor at " + ", ".join(f"{h:.2f}m" for h in heights)
    cg.metadata["groundplane_calibration"] = True
except Exception as ex:
    status = f"SKIPPED ground plane: {type(ex).__name__}: {ex}"
print(status)
p3 = cg.triangulate(flat, progress=False).reshape(n_f, n_p, 3)
cg.metadata["charuco_square_size"] = a.square_mm; cg.metadata["charuco_board_object"] = str(bdef); cg.metadata["path_to_recorded_videos"] = take
cg.metadata["rescued_from_2d_npy"] = True; cg.metadata["static_only"] = bool(a.static_only)
out_toml = f"{take}/{name}_camera_calibration{a.suffix}.toml"; cg.dump(out_toml)
np.save(f"{take}/output_data/charuco_3d_xyz{a.suffix}.npy", skellyforge_data(raw_charuco_data=p3))
open(f"{take}/GROUNDPLANE_STATUS{a.suffix}.txt", "w").write(status)
print("wrote", out_toml)
