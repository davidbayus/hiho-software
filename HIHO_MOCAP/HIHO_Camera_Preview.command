#!/bin/zsh
echo "HIHO camera preview"
echo "-------------------"
echo "A window will open showing every camera, each labeled cam 0, cam 1, ..."
echo "If macOS asks for camera permission, click Allow (then double-click this again)."
echo "Press Q or ESC in the preview window to close it."
echo ""
"/Users/davidbayus/miniforge3/envs/freemocap-env/bin/python" \
  "/Users/davidbayus/Desktop/DR_BAYUS/SOFTWARE/HIHO_MOCAP/external/record_take.py" --preview
echo ""
echo "Preview closed. You can close this Terminal window."
