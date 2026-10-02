#!/bin/zsh
# usage: tl.sh <seconds> cmd...   run with a hard time limit (Blender ignores SIGALRM, so poll and kill)
lim=$1; shift
"$@" & pid=$!
( i=0; while kill -0 $pid 2>/dev/null; do sleep 1; i=$((i+1)); if [ $i -ge $lim ]; then echo "AB HANG killed after ${lim}s"; kill -9 $pid 2>/dev/null; break; fi; done ) &
wait $pid 2>/dev/null
