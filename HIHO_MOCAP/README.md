# HIHO MOCAP

Multi-camera markerless motion capture for Blender. The canonical project of [HIHO Software](../README.md).

A ring of ordinary webcams records a performer. FreeMoCap turns the videos into 3D motion in its own Python environment. This addon runs the whole path from inside Blender and delivers a baked animation on a rig, ready to retarget to a character. No suit, no markers, no subscription.

## The artist path

1. **Show Cameras**, pick your ring
2. **Record Calibration** with the printed board, then **Solve** and **Check** (the quality badges tell the truth, and they name the take they describe)
3. **Record** a take
4. **Process Mocap** (runs in the external environment with a live log and an honest quality verdict)
5. **Load Take**, walk it with **Play**, **Bake**, **Send to Character**, **Save Out**

The full workflow panel (capture, calibration, processing, output, face) is always visible. Recording and calibration are the first thing every session does, so nothing hides them. The Studio panel sits alongside it with a few plain-language steps for working with a finished take.

## Design choices that matter

- The bake repairs its own rotation spelling, so smoothing a take is always safe
- Every take is filtered at its real frame rate
- Baking removes only this addon's constraints, so a character's own rigging survives
- A blank camera list refuses to guess instead of silently recording the wrong cameras
- Machine-level settings (the FreeMoCap environment, the HIHO data home folder) live in addon preferences and survive restarts
- Crashes leave a readable note instead of a shrug

## Requirements

- Blender 5.x (developed on 5.2 LTS)
- A separate Python environment with FreeMoCap 1.8.2 or newer, set once in addon preferences
- Webcams (the house ring is six Logitech C922x on a 270 degree, three-height mount)

## Where the real documentation lives

`STATUS.md` is the live state, updated every dev session. `HIHO_MOCAP_WRAPPER_ARCHITECTURE.md` is the architecture. The dated design, audit, diagnosis, and research docs in this folder are the development history in prose.

## License

AGPL-3.0, like the FreeMoCap engine it drives. Free and open source, forever.
