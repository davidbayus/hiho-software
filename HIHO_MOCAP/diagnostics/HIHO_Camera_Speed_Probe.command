#!/bin/zsh
# Double-click: measures each ring camera's real frame rate (alone, then all at once). Close Blender's camera windows first.
PY="/Users/davidbayus/miniforge3/envs/freemocap-env/bin/python"
"$PY" "/Users/davidbayus/Desktop/DR_BAYUS/SOFTWARE/HIHO_MOCAP/diagnostics/camera_speed_probe_2026-08-22.py" --out "$HOME/Desktop/HIHO_ALL/HIHO_CALIBRATIONS/camera_speed_probe_$(date +%Y-%m-%d_%H-%M).txt"
echo; read "?Press Enter to close..."
