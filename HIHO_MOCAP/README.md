# HIHO MOCAP

Multi-camera markerless motion capture for Blender. The main project of [HIHO Software](../README.md).

A ring of ordinary webcams records a performer. FreeMoCap turns the videos into 3D motion in its own Python environment. This addon runs the whole path from inside Blender and delivers a baked animation on a rig, ready to retarget to a character.

## One take, start to finish

1. **Show Cameras**, pick your ring
2. **Record Calibration** with the printed board, then **Solve** and **Check** (the Quality and Floor badges report on the calibration and name the take they describe)
3. **Record Mocap**
4. Pick a **Tracker** (RTMPose by default), then **Process Mocap** (runs in the external environment, with a live log and a quality report)
5. **Spawn Rig**, then **Bake Animation** and **Save Out**

The full workflow panel (cameras, calibration, recording, processing, rig, bake and export, face) is always visible. Recording and calibration are the first thing every session does, so nothing hides them. The Studio panel sits alongside it with a few plain-language steps for working with a finished take: **Load Take**, **Play**, **Send to Character**.

## Design choices

- The **Tracker** menu picks how each camera finds the body: RTMPose (fast, the default) or MediaPipe (classic, slow). If the fast one is not installed, Process says so and stops; it never quietly switches
- The bake keeps every rotation continuous, so smoothing a take is safe
- Every take is filtered at its real frame rate
- Baking removes only this addon's constraints, so a character's own rigging survives
- A blank camera list refuses to guess instead of silently recording the wrong cameras
- Machine-level settings (the FreeMoCap environment, the HIHO data home folder) live in addon preferences and survive restarts
- A crash leaves a readable note

## Requirements

- Blender 5.2 LTS, the version students use. It also runs unchanged on Blender 5.3
- A separate Python environment with FreeMoCap, set once in addon preferences: FreeMoCap 2.0 (alpha) for the default RTMPose tracker, FreeMoCap 1.8.2 for the classic MediaPipe tracker. The setup scripts at the top of the repository (`HIHO_Setup_Mac.command`, `HIHO_Setup_PC.bat`) build the 1.8.2 environment
- Webcams (the house ring is six Logitech C922x on a 270 degree, three-height mount)

## Documentation

`STATUS.md` is the live state. `HIHO_MOCAP_WRAPPER_ARCHITECTURE.md` is the architecture. The dated design, audit, diagnosis, and research docs in this folder are the development history in prose.

## License

AGPL-3.0, like the FreeMoCap engine it drives.
