#!/bin/zsh
STAMP=$(date "+%Y-%m-%d_%H-%M-%S")
OUT="$HOME/Desktop/HIHO_CAPTURES/$STAMP"
CAMS="${1:-0,1,2,3,4,5}"
DUR="${2:-60}"
echo "HIHO RECORD  —  cameras $CAMS, ${DUR}s  (the six-camera ring)"
echo "Override:  HIHO_Record.command \"0,2,4\" 30   (cameras, seconds)"
echo "-------------------------------------------------"
echo "A live window opens. You'll HEAR a countdown (get ready, 7..1, recording),"
echo "then it records $DUR seconds. Get into the capture volume now."
echo "ESC in the window stops early."
echo "Saving to: $OUT"
echo ""
if "/Users/davidbayus/miniforge3/envs/freemocap-env/bin/python" \
  "/Users/davidbayus/Desktop/DR_BAYUS/SOFTWARE/HIHO_MOCAP/external/record_take.py" \
  --output "$OUT" --cameras "$CAMS" --countdown 7 --show --duration "$DUR"; then
  echo "$OUT" > "$HOME/Desktop/HIHO_LAST_CAPTURE.txt"
  echo ""
  echo "Done. Saved to: $OUT"
  echo "Tell Claude it's done and it will process this take."
else
  echo ""
  echo "RECORDING FAILED — nothing was saved and the last-capture pointer was not touched."
  echo "Read the messages above for the reason (camera busy, wrong index, ...)."
fi
