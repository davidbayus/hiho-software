#!/bin/zsh
HERE=${0:A:h}
W=${AB_WORK:-$HERE/work}                       # inputs, outputs, renders live here (not in git)
QUADRE_SRC=${QUADRE_SRC:-${HERE:h}}            # folder that contains quadre/
B=${BLENDER:-/Applications/Blender.app/Contents/MacOS/Blender}
# usage: suite_op.sh <tag> [folder containing quadre/]   the REAL operator over the six-case suite
tag=$1; SRC=${2:-$QUADRE_SRC}; O=$W/op; mkdir -p $O
(
$B -b --factory-startup --python $HERE/run_quadre.py -- $SRC $W/input/chibi_sculpt_full.blend $O ${tag}_chibi 5000:X 1500:X 5000: > $O/_log_${tag}_1.txt 2>&1 &
$B -b --factory-startup --python $HERE/run_quadre.py -- $SRC $W/input/bucket.blend $O ${tag}_bucket 5000: > $O/_log_${tag}_2.txt 2>&1 &
$B -b --factory-startup --python $HERE/run_quadre.py -- $SRC $W/input/suzanne.blend $O ${tag}_suzanne 5000: 2000:X > $O/_log_${tag}_3.txt 2>&1 &
wait
)
grep -h -E "^AB|Traceback|Error|  File|QUADRE" $O/_log_${tag}_*.txt | cut -c1-150
{
REF=$W/input/chibi_ref_150k_world.obj $HERE/summ.sh $O/${tag}_chibi_q5000_symX.obj $O/${tag}_chibi_q1500_symX.obj $O/${tag}_chibi_q5000_symoff.obj
REF=$W/input/bucket_ref_world.obj $HERE/summ.sh $O/${tag}_bucket_q5000_symoff.obj | tail -n +2
REF=$W/input/suzanne_ref_world.obj $HERE/summ.sh $O/${tag}_suzanne_q5000_symoff.obj $O/${tag}_suzanne_q2000_symX.obj | tail -n +2
} | cut -c1-170 | python3 -c "
import sys
rows=[l.rstrip('\n') for l in sys.stdin if l.strip()]
print(rows[0]); vals=[]
for r in rows[1:]:
    print(r)
    try: vals.append([float(x) for x in r[44:].split()])
    except Exception: pass
if vals:
    n=len(vals); m=[sum(v[i] for v in vals)/n for i in range(len(vals[0]))]
    print(f\"{'MEAN ('+str(n)+')':44s}\"+''.join(f'{x:9.2f}' for x in m))
"
