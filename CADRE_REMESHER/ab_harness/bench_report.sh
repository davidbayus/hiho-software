#!/bin/zsh
# usage: bench_report.sh <outdir> <code> ...   metrics + labelled sheets + blind A/B sheets for finished benchmark runs
HERE=${0:A:h}
W=${AB_WORK:-$HERE/work}
B=${BLENDER:-/Applications/Blender.app/Contents/MacOS/Blender}
OUT=$1; shift; O=$W/bench; mkdir -p $OUT $W/renders
for code in "$@"; do
  sym=$(python3 -c "import json;print(json.load(open('$W/input/$code.json'))['sym'] or 'off')")
  ref=$W/input/${code}_ref_world.obj
  exo=$O/${code}_exoside_q5000_sym${sym}_ad50_ac1.obj; qn=$O/${code}_quadre043_q5000_sym${sym}.obj; qo=$O/${code}_quadre038_q5000_sym${sym}.obj
  ar=$O/${code}_autoremesher.obj; qf=$O/${code}_quadriflow.obj
  have=(); for f in $exo $qn $qo $ar $qf; do [ -s $f ] && have+=($f); done
  $B -b --factory-startup --python $HERE/metrics.py -- $ref $O/${code}_metrics.json $have 2>&1 | grep -E "FAIL|Traceback|Error"
  items=()
  [ -s $exo ] && items+=("Exoside 1.4=$exo"); [ -s $qn ] && items+=("Quadre 0.4.3=$qn"); [ -s $qo ] && items+=("Quadre 0.3.8=$qo")
  [ -s $ar ] && items+=("AutoRemesher 1.2=$ar"); [ -s $qf ] && items+=("QuadriFlow=$qf")
  $B -b --factory-startup --python $HERE/render.py -- $W/renders/lab_$code 520 threeq,back $items 2>&1 | grep -E "Error|Traceback"
  python3 $HERE/montage.py $W/renders/lab_$code $OUT/LABELED_$code.png "$code, Quad Count 5000, symmetry $sym" > /dev/null
  if [ -s $exo ] && [ -s $qn ]; then
    order=$(python3 -c "
import json,os,random
p='$OUT/BLIND_KEY.json'; k=json.load(open(p)) if os.path.exists(p) else {}
if '$code' not in k: k['$code']=random.choice([['exoside','quadre'],['quadre','exoside']]); json.dump(k,open(p,'w'),indent=1)
print(k['$code'][0])")
    if [ "$order" = "exoside" ]; then a=$exo; b=$qn; else a=$qn; b=$exo; fi
    NO_POLES=1 $B -b --factory-startup --python $HERE/render.py -- $W/renders/blind_$code 800 threeq,front,back "A=$a" "B=$b" 2>&1 | grep -E "Error|Traceback"
    python3 $HERE/montage.py $W/renders/blind_$code $OUT/BLIND_$code.png "$code: which mesh is better, A or B?" > /dev/null
  fi
  echo "reported $code (${#have} results)"
done
