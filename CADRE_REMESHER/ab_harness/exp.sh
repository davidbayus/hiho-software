#!/bin/zsh
HERE=${0:A:h}
W=${AB_WORK:-$HERE/work}                       # inputs, outputs, renders live here (not in git)
QUADRE_SRC=${QUADRE_SRC:-${HERE:h}}            # folder that contains quadre/
B=${BLENDER:-/Applications/Blender.app/Contents/MacOS/Blender}
# usage: exp.sh <name> key=val ...   one run of the experiment pipeline (see exp_quadre.py)
name=$1; shift
$B -b --factory-startup --python $HERE/exp_quadre.py -- $QUADRE_SRC ${INPUT:-$W/input/chibi_sculpt_full.blend} $W/exp $name "$@" 2>&1 | grep -E "^AB|Traceback|Error|error:|  File " | grep -v "^AB minchain"
