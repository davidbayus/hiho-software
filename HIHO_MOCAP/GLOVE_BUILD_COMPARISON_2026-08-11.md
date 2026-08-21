# Glove build comparison — Mocap Fusion Gloves vs LucidGloves P4.1 (2026-08-11)

**Why this doc:** David sent a second DIY glove build for comparison against our
committed platform: "$150 wireless mocap gloves - DIY Tutorial - Arduino + SteamVR
trackers" (Animation Prep Studios / guiglass, 43:50, Aug 2021, ~30K views,
youtube.com/watch?v=PCBvUHJH8Gw). Repos: github.com/guiglass/Mocap_Fusion_Gloves and
github.com/guiglass/AnimationPrepStudio-ArduGlove. Our committed platform (settled
2026-07-06, RESEARCH_AGENDA section 2): **LucidGloves Prototype 4.1 tracking-only**,
build manual + costed shopping list in `GLOVE_BUILD_MANUAL_2026-07-06.pdf`.

Fun footnote: YouTube's own sidebar on the Mocap Fusion video recommends Lucas
VRTech's "$22 Virtual Reality Gloves" — the LucidGloves creator. These two builds are
the recognized rivals of the DIY glove world, so this is the right comparison to make.

## The two designs in one paragraph each

**Mocap Fusion Gloves (the video):** five commercial resistive flex sensors (SparkFun
SEN-08606, 4.5") sewn along the fingers of a knit glove, read by an Arduino Mega.
Three wiring options: Mega wired to the PC over USB; Mega on the glove transmitting
by nRF24 radio (~$20/pair of radios) to an Arduino Uno receiver; or two Arduinos per
glove to a central receiver. Absolute hand position comes from a **Vive tracker**
strapped to a 3D-printed hand mount, which requires SteamVR plus lighthouse base
stations. Output feeds their Mocap Fusion app (closed freeware VR mocap sandbox).
Arduino sketches and print files are public on GitHub; no license was visible in the
README (unverified).

**LucidGloves P4.1 (ours):** five rotary potentiometers, each turned by a string on a
badge-reel spring anchored at the fingertip, read by an Arduino (or ESP32 for
Bluetooth wireless). Finger curl only, no absolute position: by design, because in
HIHO the six-camera rig already solves wrist position, and the glove exists to
replace only the noisiest data (fingers). MIT licensed end to end (firmware,
hardware, driver), large community, extensive docs.

## Costs (Claude's math, per the standing rule)

**Mocap Fusion, one PAIR:**
- 10 flex sensors × $8.95 = **$89.50** (the dominant cost; ~$45 of sensors per glove)
- Arduino Mega $25–40, plus wireless option: Uno ~$15–25 + nRF24 pair ~$20
- Knit gloves ~$15, Dynaflex ~$10, wire/print/misc ~$10
- **Pair subtotal, no tracking: ~$160–200** (matches their own $150–200 estimate; the
  video title's "$150" is this number, for a pair, and assumes you already own the VR
  gear)
- Absolute tracking, which the design REQUIRES to be what it is: 2 Vive trackers
  ~$130 each = $260, plus 1–2 lighthouse base stations $150–300, plus a
  SteamVR-capable PC
- **Realistic all-in from zero VR gear: ~$570–760 per pair**

**LucidGloves P4.1, one PAIR (from our costed manual):**
- First glove including ALL tools: $135–195; second glove: $25–35
- **Pair all-in: ~$160–230**, absolute position free because the camera rig is
  already installed
- Marginal cost per ADDITIONAL pair once tools exist (club scaling): **~$50–70**,
  vs ~$420+ per additional Mocap Fusion pair (sensors + boards + trackers)

David's read ("a lil more expensive") is right, and the gap is bigger than the title
suggests: at club scale it is roughly **6 to 8 times** the per-pair marginal cost,
and the real dependency cost is hidden in the SteamVR requirement.

## Comparison against the research-agenda axes

| Axis | LucidGloves P4.1 | Mocap Fusion Gloves |
|---|---|---|
| Cost per student pair | ~$50–70 marginal | ~$420+ marginal |
| Absolute hand position | From our camera rig (fusion, planned) | Vive tracker + SteamVR base stations |
| Build complexity | More mechanical fiddle (reels, strings, prints) but designed as THE community beginner build | Simpler mechanics (sew sensors, solder), 43-minute assembly video |
| Durability in kid hands | Potentiometers effectively immortal; strings/springs replaceable for pennies | Resistive flex sensors are known to fatigue and crack at the bend crease with hard repeated flexing (general knowledge, verify before ever relying on it) |
| Openness | MIT end to end | Sketches public (license unverified), app closed freeware, SteamVR proprietary + online account |
| Offline / old machines | Yes | SteamVR wants a modern GPU and online setup |
| Zero paid dependencies rule | Passes | Fails (trackers, base stations, Steam account) |

## Verdict

**Stay on LucidGloves P4.1. No change to the learn-first plan** (David solders a pair
himself first, then it becomes a club build). The Mocap Fusion design chains the
glove to the SteamVR ecosystem, which breaks three HIHO rules at once: zero paid
dependencies, runs offline, runs on old machines.

## What the video is still worth (three things to keep)

1. **It validates our fusion architecture from an independent direction.** Their
   answer to "a glove cannot know where the hand IS" is a $130 tracker strapped to
   the wrist. Ours is the camera rig we already own. Same asymmetric-trust split
   (absolute-but-noisy position source + relative-but-smooth finger source), which is
   exactly the Thread A + camera fusion framing in RESEARCH_AGENDA section 2. Two
   independent builders landing on wrist-anchor-plus-finger-sensors is good evidence
   the architecture is sound.
2. **The nRF24 Arduino-to-Arduino radio link (~$20) is a clean untethering pattern**
   worth remembering for the deferred serial-to-CSV logger design. For us the ESP32
   Bluetooth path already in the LucidGloves ecosystem is the cleaner single-chip
   version of the same idea; nRF24 is the fallback if Bluetooth pairing ever proves
   flaky in a classroom.
3. **The assembly video itself is a good club-night visual reference** for sewing
   sensors into knit gloves and general glove-wiring craft, regardless of platform.
   Worth a rewatch when the club build actually starts.

*Written 2026-08-11 (laptop). Sources: video page + README of
guiglass/Mocap_Fusion_Gloves, read same day; LucidGloves numbers from
GLOVE_BUILD_MANUAL_2026-07-06.pdf.*
