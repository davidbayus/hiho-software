#!/bin/zsh
# HIHO A/B: 60 fps vs 30 fps, same cameras, same session. Double-click at the BASEMENT.
# Question it answers: is 30 fps (the $25 Brio 101's ceiling) good enough for student movement?
# This is the panel's own recorder (external/record_take.py) with its --fps flag; nothing new is
# installed. Both takes land in HIHO_CAPTURES like any other take (the sidecar records the fps)
# plus an AB_NOTE.txt in each naming its twin. Process both the normal way afterwards.
# Same three moves in both takes: a walking loop, a jump, a fast arm swing.
set -u
PY="/Users/davidbayus/miniforge3/envs/freemocap-env/bin/python"
INSTALLED="$HOME/Library/Application Support/Blender/5.2/extensions/user_default/hiho_mocap/external/record_take.py"
SOURCE="$HOME/Desktop/DR_BAYUS/SOFTWARE/HIHO_MOCAP/external/record_take.py"
DATA_HOME="${HIHO_DATA_HOME:-$HOME/Desktop/HIHO_ALL}"
DURATION="${HIHO_AB_DURATION:-30}"    # seconds per take
COUNTDOWN="${HIHO_AB_COUNTDOWN:-5}"   # spoken countdown before each take

SCRIPT="$INSTALLED"; [[ -f "$SCRIPT" ]] || SCRIPT="$SOURCE"
if [[ ! -x "$PY" ]]; then echo "FreeMoCap env python not found: $PY"; read "?Enter to close..."; exit 1; fi
if [[ ! -f "$SCRIPT" ]]; then echo "record_take.py not found (installed addon or SOFTWARE copy)"; read "?Enter to close..."; exit 1; fi
mkdir -p "$DATA_HOME/HIHO_CAPTURES"

echo "HIHO 30 vs 60 fps A/B"
echo "  recorder : $SCRIPT"
echo "  takes to : $DATA_HOME/HIHO_CAPTURES"
echo "  each take: $DURATION s after a $COUNTDOWN s spoken countdown"
echo
echo "Close Blender's camera window first (Show Cameras / Record), if one is open."
echo "The picker opens next: right-click excludes a camera (the laptop's own), left-click rotates, Q when done."
read "?Press Enter to open the picker..."
CAMS=$("$PY" "$SCRIPT" --preview | tee /dev/stderr | grep '^HIHO_CAMERAS::' | tail -1 | sed 's/^HIHO_CAMERAS:://')
if [[ -z "$CAMS" ]]; then echo; echo "No cameras picked, nothing recorded."; read "?Enter to close..."; exit 1; fi
echo; echo "Recording cameras: $CAMS"

TAKE_PATH=""
record_take() {  # $1 = fps
  local fps=$1
  local stamp; stamp=$(date +%Y-%m-%d_%H-%M-%S)
  local out="$DATA_HOME/HIHO_CAPTURES/$stamp"
  echo; echo "=== TAKE at $fps fps: $DURATION s, countdown $COUNTDOWN s ==="
  read "?Get in position. Press Enter to start the $fps fps take..."
  "$PY" "$SCRIPT" --output "$out" --cameras "$CAMS" --countdown "$COUNTDOWN" \
        --duration "$DURATION" --show --fps "$fps"
  if [[ ! -d "$out" ]]; then echo "Take folder missing: $out (cancelled?)"; TAKE_PATH=""; return 1; fi
  echo "fps requested: $fps" > "$out/AB_NOTE.txt"
  TAKE_PATH="$out"
  echo "Saved: $out"
  [[ -f "$out/RECORDING_REPORT.txt" ]] && { echo "--- RECORDING_REPORT.txt ---"; cat "$out/RECORDING_REPORT.txt"; }
  return 0
}

record_take 60 || { read "?Enter to close..."; exit 1; }
TAKE60="$TAKE_PATH"
record_take 30 || { read "?Enter to close..."; exit 1; }
TAKE30="$TAKE_PATH"

echo "A/B twin: $TAKE30 (30 fps)" >> "$TAKE60/AB_NOTE.txt"
echo "A/B twin: $TAKE60 (60 fps)" >> "$TAKE30/AB_NOTE.txt"
echo
echo "DONE. Two takes, same cameras:"
echo "  60 fps: $TAKE60"
echo "  30 fps: $TAKE30"
echo
echo "Check the 30 fps report above: each camera should read about 30 fps. If it reads about 60,"
echo "the cameras ignored the request; tell Claude before processing."
echo "Next: Load Take + Process each one as usual, then compare shin wobble, foot contacts, and jitter"
echo "on the same three moves."
read "?Enter to close..."
