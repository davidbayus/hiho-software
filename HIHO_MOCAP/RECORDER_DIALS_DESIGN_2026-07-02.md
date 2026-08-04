# Recorder Dials (resolution / framerate) — Design Note (2026-07-02)

**Context:** Day-2 BASEMENT findings: motion blur on all four C922s (long exposures in dim light) and David's call to raise the framerate. Recording format is hardcoded at 960×540 @ 30fps (`core/camera_manager.py` DEFAULT_RESOLUTION / DEFAULT_FPS). Field evidence (Pose2Sim accuracy studies, PRE_BASEMENT research §4): framerate beats resolution; target is 1280×720 @ 60 (the C922's fast native mode). Higher fps also forces shorter exposures → less blur, compounding with more room light.

**Change (one file, `external/record_take.py`):** add `--width`, `--height`, `--fps` arguments, defaults matching today's values (960/540/30), passed to `CameraManager(...)` in the recording path. `CameraManager` already accepts `resolution=` and `fps=` — this is pure wiring. Preview path stays at defaults (identity/rotation checking doesn't need format control). Panel UI fields deliberately NOT added yet — format is a test-day variable driven via .command helpers / terminal until the A/B settles a new default; then the panel gets a proper control (post-test design).

**Known constraints stated up front:**
- Calibration is resolution-specific. Any resolution change requires a NEW calibration recording at that resolution. (fps alone doesn't invalidate calibration, but takes and calibration should use one format for sanity.)
- 4× C922 at 720p60 MJPG may exceed USB delivery. The writer stamps the requested fps into the mp4 header regardless of delivery (audit M8), so the test must count actual frames vs wall-clock.

**Test plan (real path, per the 1.4.12 lesson):** short live recording on the actual 4-cam rig at 1280×720@60, then count frames per camera and compare against wall-clock; pass = ~fps×seconds frames on all four cameras and normal-speed playback. Version 1.4.13 → 1.4.14.
