#!/bin/zsh
HERE=${0:A:h}
W=${AB_WORK:-$HERE/work}                       # inputs, outputs, renders live here (not in git)
QUADRE_SRC=${QUADRE_SRC:-${HERE:h}}            # folder that contains quadre/
B=${BLENDER:-/Applications/Blender.app/Contents/MacOS/Blender}
# usage: suite.sh <tag> key=val ...   an experiment recipe over the six-case suite
tag=$1; shift; mkdir -p $W/exp
(
INPUT=$W/input/chibi_sculpt_full.blend $HERE/exp.sh ${tag}_chibi5kX target=5000 sym=X "$@" > $W/exp/_log_${tag}_1.txt 2>&1 &
INPUT=$W/input/chibi_sculpt_full.blend $HERE/exp.sh ${tag}_chibi1500X target=1500 sym=X "$@" > $W/exp/_log_${tag}_2.txt 2>&1 &
INPUT=$W/input/chibi_sculpt_full.blend $HERE/exp.sh ${tag}_chibi5koff target=5000 sym= "$@" > $W/exp/_log_${tag}_3.txt 2>&1 &
INPUT=$W/input/bucket.blend $HERE/exp.sh ${tag}_bucket5k target=5000 sym= "$@" > $W/exp/_log_${tag}_4.txt 2>&1 &
INPUT=$W/input/suzanne.blend $HERE/exp.sh ${tag}_suzanne5k target=5000 sym= "$@" > $W/exp/_log_${tag}_5.txt 2>&1 &
INPUT=$W/input/suzanne.blend $HERE/exp.sh ${tag}_suzanne2kX target=2000 sym=X "$@" > $W/exp/_log_${tag}_6.txt 2>&1 &
wait
)
grep -h -E "FAIL|Traceback|Error" $W/exp/_log_${tag}_*.txt
{
REF=$W/input/chibi_ref_150k_world.obj $HERE/summ.sh $W/exp/${tag}_chibi5kX.obj $W/exp/${tag}_chibi1500X.obj $W/exp/${tag}_chibi5koff.obj
REF=$W/input/bucket_ref_world.obj $HERE/summ.sh $W/exp/${tag}_bucket5k.obj | tail -n +2
REF=$W/input/suzanne_ref_world.obj $HERE/summ.sh $W/exp/${tag}_suzanne5k.obj $W/exp/${tag}_suzanne2kX.obj | tail -n +2
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
