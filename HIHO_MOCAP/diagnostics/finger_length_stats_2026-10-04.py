import numpy as np, glob, os, sys
B={"thumb.carpal":(0,1),"thumb.01":(1,2),"thumb.02":(2,3),"thumb.03":(3,4)}
for k,(n,b) in enumerate([("index",5),("middle",9),("ring",13),("pinky",17)]):
    B[f"palm.0{k+1}"]=(0,b)
    for j in range(3): B[f"f_{n}.0{j+1}"]=(b+j,b+j+1)
root=os.path.expanduser("~/Desktop/HIHO_ALL/HIHO_CAPTURES")
takes=sys.argv[1:]
allrows=[]
for t in takes:
    d={}
    for side,s in (("R","right"),("L","left")):
        p=f"{root}/{t}/output_data/mediapipe_{s}_hand_3d_xyz.npy"
        a=np.load(p)
        for bone,(h,tl) in B.items():
            L=np.linalg.norm(a[:,tl]-a[:,h],axis=1); v=L[~np.isnan(L)]
            d[(bone,side)]=(np.median(v),np.percentile(v,90),np.percentile(v,99),v.max(),len(v))
    print(f"\n== {t}  (mm: p50/p90/max, R | L)")
    for bone in B:
        r=d[(bone,"R")];l=d[(bone,"L")]
        print(f"{bone:14s} R {r[0]:6.1f} {r[1]:7.1f} {r[3]:7.0f} | L {l[0]:6.1f} {l[1]:7.1f} {l[3]:7.0f}")
