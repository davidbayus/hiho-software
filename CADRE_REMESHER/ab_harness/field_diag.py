"""How well does a .rosy field follow the sculpt's curvature (same yardstick as metrics.py)?
blender -b --python field_diag.py -- <ref_world.obj> <h> <locx,locy,locz> <rem.obj> <rosy> [<rosy> ...]"""
import bpy, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ab_common import *
from metrics import Ref
from exp_field import read_tri_obj
from mathutils import Vector
a = args_after_dashes()
ref = Ref(a[0]); h = float(a[1]); loc = np.array([float(x) for x in a[2].split(',')])
V, F = read_tri_obj(a[3]); V = V + loc
P0, P1, P2 = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
N = np.cross(P1 - P0, P2 - P0); A = 0.5 * np.linalg.norm(N, axis=1); N /= (2 * A)[:, None]
C = (P0 + P1 + P2) / 3
rad = 0.35 * h
def nrm(Pts): return np.array([ref.smooth_normal(Vector(p), rad) for p in Pts])
for rp in a[4:]:
    L = open(rp).read().split('\n')[2:]
    D = np.array([[float(x) for x in l.split()] for l in L if l.strip()])
    D -= (D * N).sum(1)[:, None] * N; D /= np.linalg.norm(D, axis=1)[:, None]
    E2 = np.cross(N, D)
    dU = (nrm(C + 0.5 * h * D) - nrm(C - 0.5 * h * D)) / h
    dW = (nrm(C + 0.5 * h * E2) - nrm(C - 0.5 * h * E2)) / h
    S11 = (dU * D).sum(1); S22 = (dW * E2).sum(1); S12 = 0.5 * ((dU * E2).sum(1) + (dW * D).sum(1))
    th = 0.5 * np.degrees(np.arctan2(2 * S12, S11 - S22)); mis = np.abs(th) % 90; mis = np.minimum(mis, 90 - mis)
    aniso = np.sqrt((S11 - S22) ** 2 + 4 * S12 ** 2)
    strong = aniso * h > 0.15
    w = A * strong
    print(f"AB FIELD {os.path.basename(os.path.dirname(rp))}/{os.path.basename(rp)}: strong area {100*w.sum()/A.sum():.0f}%  misalign mean {(mis*w).sum()/w.sum():.1f} deg  >20deg {100*((mis>20)*w).sum()/w.sum():.0f}%")
