import numpy as np, os, sys
B={"thumb.carpal":(0,1),"thumb.01":(1,2),"thumb.02":(2,3),"thumb.03":(3,4)}
for k,(n,b) in enumerate([("index",5),("middle",9),("ring",13),("pinky",17)]):
    B[f"palm.0{k+1}"]=(0,b)
    for j in range(3): B[f"f_{n}.0{j+1}"]=(b+j,b+j+1)
# anatomical ceiling as a fraction of forearm (elbow->wrist); generous (adult hand ~ 0.75 forearm)
CAP={"thumb.carpal":0.22,"thumb.01":0.22,"thumb.02":0.18,"thumb.03":0.16,"palm":0.45,
     ".01":0.22,".02":0.15,".03":0.13}
def cap(b):
    for k in ("thumb.carpal","thumb.01","thumb.02","thumb.03"):
        if b==k: return CAP[k]
    if b.startswith("palm"): return CAP["palm"]
    return CAP[b[-3:]]
root=os.path.expanduser("~/Desktop/HIHO_ALL/HIHO_CAPTURES")
for t in sys.argv[1:]:
    body=np.load(f"{root}/{t}/output_data/mediapipe_body_3d_xyz.npy")
    fa=np.nanmedian(np.r_[np.linalg.norm(body[:,15]-body[:,13],axis=1),np.linalg.norm(body[:,16]-body[:,14],axis=1)])
    print(f"\n== {t}  forearm median {fa:.0f} mm   [old target L/R -> new target L/R, share of frames under cap R/L]")
    H={s:np.load(f"{root}/{t}/output_data/mediapipe_{n}_hand_3d_xyz.npy") for s,n in (("R","right"),("L","left"))}
    for b,(h,tl) in B.items():
        c=cap(b)*fa; out=[];new={}
        for s in "RL":
            L=np.linalg.norm(H[s][:,tl]-H[s][:,h],axis=1); v=L[~np.isnan(L)]
            ok=v[v<=c]; share=len(ok)/max(len(v),1)
            new[s]=(np.percentile(ok,90) if len(ok)>=0.25*len(v) and len(ok)>0 else None, share, np.percentile(v,90))
        oldavg=(new["R"][2]+new["L"][2])/2
        r,l=new["R"][0],new["L"][0]
        if r and l and max(r,l)/min(r,l)<=1.5: fin=f"{(r+l)/2:5.1f} both (avg)"
        else:
            good=[(new[s][1],new[s][0],s) for s in "RL" if new[s][0]]
            fin = f"{max(good)[1]:5.1f} both (from {max(good)[2]})" if good else "median fallback"
        print(f"{b:13s} cap {c:5.0f}  old {oldavg:6.1f}  -> {fin:22s}  under-cap R {new['R'][1]:.0%} L {new['L'][1]:.0%}")
