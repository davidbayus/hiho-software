#!/bin/zsh
HERE=${0:A:h}
W=${AB_WORK:-$HERE/work}                       # inputs, outputs, renders live here (not in git)
QUADRE_SRC=${QUADRE_SRC:-${HERE:h}}            # folder that contains quadre/
B=${BLENDER:-/Applications/Blender.app/Contents/MacOS/Blender}
# usage: [REF=ref_world.obj] summ.sh <result.obj> ...   compact metric table
J=$W/exp/_summ_$$.json; mkdir -p $W/exp
$B -b --factory-startup --python $HERE/metrics.py -- ${REF:-$W/input/chibi_ref_150k_world.obj} $J "$@" 2>&1 | grep -E "FAIL|Traceback|Error"
python3 - $J <<'PY'
import json,sys
R=json.load(open(sys.argv[1]))
cols=[('faces','faces',0),('singular','poles',0),('curv_misalign_strong_mean_deg','flow°',1),('curv_misalign_strong_gt20_pct','flow>20%',1),('angle_dev_mean','ang°',1),('angle_bad_pct','angBad%',2),('warp_mean_deg','warp°',1),('aspect_mean','aspect',2),('edge_cv','edgeCV',2),('nbr_area_ratio_p95','nbrP95',2),('fid_fwd_mean_pm','fidV‰',2),('fid_rev_mean_pm','fidS‰',2),('fid_rev_max_pm','fidMax‰',1),('selfcross_faces_pct','xself%',1),('chord_len_max','chordMax',0)]
print(f"{'name':44s}"+"".join(f"{c[1]:>9s}" for c in cols))
for r in R:
    n=r['file'].replace('.obj','').replace('chibi_','')[:43]
    print(f"{n:44s}"+"".join(f"{r[c[0]]:9.{c[2]}f}" for c in cols))
PY
