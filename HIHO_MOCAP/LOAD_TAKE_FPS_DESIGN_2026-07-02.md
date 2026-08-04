# Load Take Must Set the Scene Clock — Design Note (2026-07-02, evening)

**Status: DESIGN ONLY — code when David is back to test (one change at a time).**

**Problem (hit 4× today):** `operators/load_take.py` sets `last_processed_path` and spawns the rig but never touches `scene.render.fps` or the frame range. Blender defaults to 24fps; takes are now 60fps (were 30). Every take plays slow-motion until someone manually fixes the scene clock — the April PPParty "noise" gremlin (`project_noise_root_cause`), now guaranteed to hit every student on every take.

**Why it's not a one-liner:** the take's true fps isn't in the scene, and Blender's Python has no cv2 (wheel-less build) to probe the mp4s.

**Design:**
1. **Recorder writes a sidecar** — `record_take.py` drops `HIHO_RECORDING_INFO.json` (`fps`, `width`, `height`, `camera_ids`, `duration_sec`) in the take folder at record time. Zero-dependency, and it's the natural landing spot for the Tier 1.1 per-frame-timestamps work later (same file grows a `timestamps` companion).
2. **Load Take reads it** — if `HIHO_RECORDING_INFO.json` exists next to the videos: set `scene.render.fps`, `frame_start=1`, `frame_end=frame count of the loaded npy`, and report what it set ("Scene clock set to 60fps to match the take"). If absent (legacy takes): leave the scene alone but WARN loudly ("Old take — no recording info; set scene fps yourself, probably 30"). Never guess silently (audit theme).
3. Same sidecar read belongs in `process.py`'s post-process flow eventually; start with Load Take only (one change).

**Test plan (the user's path, per today's lesson):** record via the PANEL button → confirm sidecar exists with fps 60 → Load Take → scene fps becomes 60 and playback speed is right; then Load a pre-sidecar take → warning appears, scene untouched. Version: 1.4.16 candidate.
