#!/bin/zsh
# usage: bench_run.sh <code> ...   every tool on each benchmark shape at Quad Count 5000
HERE=${0:A:h}
W=${AB_WORK:-$HERE/work}
QUADRE_SRC=${QUADRE_SRC:-${HERE:h}}            # folder that contains quadre/
OLD_SRC=${OLD_SRC:-$W/old038/CADRE_REMESHER}   # git archive of the 0.3.8 source, for the before column
B=${BLENDER:-/Applications/Blender.app/Contents/MacOS/Blender}
AR=${AUTOREMESHER:-"${HERE:h:h}/R&D/autoremesher/autoremesher.app/Contents/MacOS/autoremesher"}
Q=5000; O=$W/bench; mkdir -p $O
for code in "$@"; do
  sym=$(python3 -c "import json;print(json.load(open('$W/input/$code.json'))['sym'])")
  in=$W/input/$code.blend; ref=$W/input/${code}_ref_world.obj
  t0=$(date +%s)
  # light tools in the background: QuadriFlow + AutoRemesher on the 150K reference copy
  ( $HERE/tl.sh 300 $B -b --factory-startup --python $HERE/run_quadriflow.py -- $ref $O/${code}_quadriflow.obj $Q "$sym" > $O/_log_${code}_qf.txt 2>&1
    "$AR" --input $ref --output $O/${code}_autoremesher.obj --report $O/${code}_autoremesher.txt --target-quads $Q > $O/_log_${code}_ar.txt 2>&1
    got=$(grep -c "^f " $O/${code}_autoremesher.obj 2>/dev/null || echo 0)
    if [ "$got" -gt 0 ]; then
      t2=$(python3 -c "print(int($Q*$Q/$got))")
      "$AR" --input $ref --output $O/${code}_autoremesher.obj --report $O/${code}_autoremesher.txt --target-quads $t2 >> $O/_log_${code}_ar.txt 2>&1
    fi ) &
  $HERE/tl.sh 400 $B -b --python $HERE/run_exoside.py -- $in $O $code $Q:$sym > $O/_log_${code}_exo.txt 2>&1
  $HERE/tl.sh 300 $B -b --factory-startup --python $HERE/run_quadre.py -- $QUADRE_SRC $in $O ${code}_quadre043 $Q:$sym > $O/_log_${code}_q043.txt 2>&1
  $HERE/tl.sh 150 $B -b --factory-startup --python $HERE/run_quadre.py -- $OLD_SRC $in $O ${code}_quadre038 $Q:$sym > $O/_log_${code}_q038.txt 2>&1
  wait
  echo "== $code sym='$sym' $(( $(date +%s) - t0 ))s"
  grep -h -E "^AB (OK|FAIL|HANG)|Traceback|Warning: Your shape|QUADRE:" $O/_log_${code}_*.txt | sed -E 's| -> .*||' | cut -c1-150
  [ -f $O/${code}_autoremesher.txt ] && grep -E "Quads:|Non-quads:|Total time|Target quads" $O/${code}_autoremesher.txt | tr '\n' ' ' && echo
done
