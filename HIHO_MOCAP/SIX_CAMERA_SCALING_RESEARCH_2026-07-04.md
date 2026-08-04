# Six-Camera Scaling + Studio Layout — Research (2026-07-04)

**Status:** RESEARCH ONLY — feeds design notes and a shopping list, no code yet.
**Trigger:** David (laptop, home, Jul 4): can dropping resolution while keeping
60fps get us to 6 cameras on the laptop? If not, what does it take to set up
the broken-screen MacBook Pro as a second capture node? End-state picture:
a 6-camera system, and a scheme to better optimize the studio space.
**Sources:** three parallel web-research passes (USB bandwidth + C922 formats;
headless-Mac capture node; 6-camera placement geometry). Confidence tags:
[OFFICIAL] docs, [SPEC] USB/UVC spec data, [PAPER] peer-reviewed,
[MAINTAINER] project devs, [ANECDOTE] forums/reviews, [INFERENCE] synthesis.
Builds on `FOUR_CAM_OPTIMIZATION_RESEARCH_2026-07-03.md` and the June
camera-scaling memory.

---

## 0. The headline (it's not what we expected)

**The resolution-drop idea is dead, but the goal survives anyway:**

1. **Dropping below 720p does NOT unlock 60fps.** The C922 offers 60fps in
   exactly ONE mode: 1280×720 MJPEG. Every lower resolution tops out at 30fps
   or less. There is no "lower res, same framerate" menu option to trade with.
   [ANECDOTE→SPEC: full v4l2 format dump of a C922n; corroborated by Logitech's
   own spec sheet listing only 1080p30 + 720p60, and motion-analysis forums.
   ~90% confidence — 2-minute hardware check at BASEMENT settles it, §5.]

2. **But 6 cameras at full 720p60 on the laptop alone is probably possible
   (~75%).** Verified on this exact machine (`ioreg`): the M4 MacBook Pro has
   **three independent USB controllers, one per Thunderbolt port**. Our own
   field data says two C922s at 720p60 fit on one controller (that's the
   working 2-on-hub pair at BASEMENT). Two cameras per port × three ports =
   **six cameras, no resolution drop, no second computer.**

3. **The headless MacBook stays in the plan as the fallback** (and the
   scaling path past 6) — full bootstrap recipe in §6.

So the order of operations is: prove the 2+2+2 topology with hardware we
mostly already own (§5), and only build the second capture node if the laptop
disappoints.

---

## 1. Why the resolution-drop path is closed

- C922 60fps is descriptor-level exclusive to 1280×720 MJPEG. Lower MJPEG
  modes (960×720, 864×480, 800×448, 640×480…) are 30fps-max. [see §0.1]
- Uncompressed (YUYV) 60fps exists only at postage-stamp sizes (~320×240 and
  below) and uncompressed modes make cameras reserve MORE bus bandwidth, not
  less — dead end twice over. [SPEC + ANECDOTE]
- Even if a sub-720p60 mode existed, it would fight the tracking scope:
  full-body + locomotion means the performer is far from the lens and small
  in frame; 720p is already the official "fine" floor (Jul 3 research), and
  fewer pixels on the body at distance directly costs MediaPipe accuracy.
- FreeMoCap requires all cameras at the SAME settings, so one weak camera
  mode would drag all six down. [OFFICIAL]

**Verdict: keep 720p60 everywhere and solve bandwidth with more USB lanes,
not fewer pixels.**

## 2. The USB math (done for you, laptop-verified where noted)

- Each USB 2.0 controller ("lane") carries 480 Mbps; a C922 at 720p60 MJPEG
  reserves roughly a third to a half of one lane. Field-verified: **2 per
  lane works** (BASEMENT hub pair), **4 on one lane fails** (install-day
  lesson). 3 on one lane: almost certainly fails — don't design for it.
- **This laptop (M4, Mac16,1) has 3 independent lanes** — one per
  Thunderbolt port. Verified live on this machine via `ioreg -p IOUSB`:
  three separate `AppleT8132USBXHCI` controllers. [MEASURED]
- **2 + 2 + 2 = 6 at 720p60.** The plan: one powered hub per port, two
  cameras per hub (or hub + direct pairs — same math, hubs just add reach
  and power stability).
- A USB *hub* never adds bandwidth (June memory, still true). A modern
  **Thunderbolt 4 dock also adds nothing** for webcams — USB 2.0 traffic is
  never tunneled; everything on that dock shares the port's one 480 Mbps
  link. [ANECDOTE, expert-grade — MacRumors "max two USB 2.0 webcams per
  TB4 port" thread matches our field data exactly.]
- **Older Thunderbolt 3 docks with their own internal USB controller (e.g.
  CalDigit TS3+) DO add a genuine new lane** (+2 more cameras each) — that's
  the "past 6 without a second computer" branch if ever needed. [ANECDOTE,
  expert-grade]
- Second machine remains the other honest way to add lanes (§6).

**Residual risks at 6 (why 75% and not 95%):** per-hub firmware quirks,
possible app-level limits handling 6 AVFoundation streams, and CPU load
writing six 60fps streams at once. None of these are USB physics; all are
answerable by the §5 tests. Processing time also rises ~50% per take
(6 videos instead of 4 through MediaPipe — offline, but classroom-relevant:
budget ~11–15 min/take vs today's 7–10).

## 3. Studio scheme — the 6-camera layout (the space-optimization piece)

Current known weaknesses (Jul 3 research): front-arc-only coverage, all four
lenses within ~9cm of the same height (~1.6m), all-high views weak for floor
work, drift-prone mounts in an old building.

The placement research (Pose2Sim, OpenCap, OptiTrack, FreeMoCap docs, and the
multi-view papers) converges on this shape for full-body + locomotion +
occasional two-performer work:

**Wrap ~270° around the volume — not a front arc, not a full even circle.**
- Pose2Sim: 6 cameras is exactly the recommended count for occlusion-heavy
  movement; their validated 7-cam rig covered 270°. [OFFICIAL/PAPER]
- Never place two cameras in a straight 180° line through the performer:
  opposed pairs both triangulate poorly (near-parallel rays) AND trigger
  MediaPipe left/right label swaps between front and back views — a
  documented FreeMoCap failure (issue #258: "inverted and translated"
  skeleton from opposing cameras). Offset would-be-opposed cameras by
  20–30° in azimuth and/or put them at different heights. [MAINTAINER+PAPER]
- The open ~90° at the back is where the backdrop goes.

**Three height bands — the floor-work fix.**
- 2 cameras HIGH (~2.0–2.2m, tilted down), 2 MID (~1.3–1.5m), 2 LOW
  (~0.7–0.9m, knee/waist). OptiTrack and Pose2Sim both explicitly endorse
  mixed elevations; low cameras are what buy leg/floor-contact quality, high
  cameras see over one performer to reach the second. Still NO true
  overhead/top-down (MediaPipe can't read prone-from-above). [OFFICIAL/PAPER]
- Good news: the articulating clamp mounts make this a re-clamping exercise,
  not a hardware purchase (Jul 3 note stands).

**A concrete starting layout** (azimuth 0° = front of volume; tune on site):

| Cam | Azimuth | Height | Role |
|-----|---------|--------|------|
| 1 | −60° | high (2.0–2.2m) | front-left high |
| 2 | −25° | mid (1.3–1.5m) | front-left mid (prime face/torso) |
| 3 | +25° | low (0.7–0.9m) | front-right low (legs/floor) |
| 4 | +75° | mid (1.4m) | right side profile |
| 5 | +130° | high (2.0–2.2m) | rear-right high |
| 6 | −120° | low (0.7–0.9m) | rear-left low |

Neighbor gaps land in/near the official 40–60° band; no pair is opposed in
both azimuth and height. Distances ~3.5–4m from volume center, all portrait
(sanctioned; standing bodies fill portrait frames better at close range) —
verify every camera keeps the full walk path head-to-toe in frame before
trusting it.

**Calibration with a surround rig — important relief:** the board does NOT
need to be seen by all six cameras at once. Our anipose calibration chains
pairwise overlaps and bundle-adjusts, so the ritual becomes: board flat on
the floor at the marked spot for the opening beat (groundplane), then a slow
continuous walk tracing each adjacent camera pair's shared seam, covering
floor-to-2m heights (low and high cameras need board frames in their zones
too). Every camera just needs shared board views with at least one neighbor.
[OFFICIAL FreeMoCap docs + anipose docs]

**Space fit-out (cheap, high-leverage):**
- Plain matte backdrop across the open rear + any busy warehouse sightlines
  (MediaPipe hates clutter; shared-studio reality). Mid-value neutral, matte.
- Gaff-tape on the floor: the calibrated volume footprint, the walk path,
  and the board's groundplane spot. Students stay inside the taped zone =
  stay inside the ≥3-camera-coverage region.
- Light: flood the volume with even, cross-firing soft light from high
  positions (short-exposure doctrine from Jul 3 needs LOTS of light);
  match color temperature; never let a fixture shine into a lens.
- Mount drift (the per-session-calibration reality): rigidity ranking is
  wall/column-bolted > scaffold clamp on added rigid truss/Unistrut >
  super clamp + SHORT arm on the stiffest pipe > long articulated arms.
  Keep arms short, lock every joint. Drift won't hit zero in that building —
  per-session calibration remains doctrine; rigidity just shrinks it.

**Two-performer note:** design for the 2-person worst case (this wrap + the
height diversity) and the 1-person case is covered for free. SAM2 masking
doesn't relax geometry — both bodies still need ≥2 clean views everywhere.

## 4. What to buy (and what NOT to)

- **2× Logitech C922x** (match the existing four — same formats, same
  calibration behavior, same uvcc controls).
- **1–2 additional powered USB hubs** (SABRENT HB-3A4C twin or similar;
  known-good model). Target topology: one hub per Thunderbolt port, 2 cams
  each. (Hub #2 alone unlocks the definitive 4-camera topology test, §5.)
- **2× more active USB extension + 2× SMALLRIG arms/clamps** to match the
  existing runs (cable length depends on the new low/rear positions).
- ~~Poster-size 5×3 Charuco board~~ **Already owned (David, 2026-07-04): two
  poster-size boards — one from the FreeMoCap store, one self-printed and
  mounted.** Nothing to buy or print. One setup task remains: measure the
  actual square edge (mm) of whichever board becomes the house standard and
  use the MEASURED value in calibration, not the nominal one (Jul 3 research
  §2c) — the two boards may differ, so pick one as canonical.
- **Do NOT buy:** a Thunderbolt 4 dock for this (adds zero webcam
  bandwidth), any non-powered hub, wide-angle clip-on lenses (distortion
  hurts tracking and complicates calibration).

## 5. Proof sequence (cheap → definitive, in order)

1. **$0, at BASEMENT, 2 min — C922 format ground truth.** One C922 plugged
   in, David's Terminal (camera permission lives there):
   `ffplay -f avfoundation -framerate 60 -video_size 800x448 -i "0"` —
   the error output lists every real mode+fps the camera offers. Confirms
   (or kills) the "no 60fps below 720p" finding on OUR cameras.
2. **~$25 — the topology proof with only the 4 cameras we own.** Second
   powered hub. 2 cams on hub A into port 1 + 2 cams on hub B into port 2,
   existing `HIHO_SPEED_TEST.command` unchanged (it already tests 4× 720p60).
   Clean pass = two lanes proven at 2-per-hub; the third lane is the same
   silicon, so 6 becomes near-certain before buying camera #5.
3. **The real thing.** New cameras arrive → 6-cam variant of the speed test
   (one-line change: `--cameras 0,1,2,3,4,5`; write it as
   `HIHO_SPEED_TEST_6CAM.command` when we're there) → then a fresh 6-camera
   calibration and a test take. Watch: enumeration order (indices WILL
   shuffle — the camera-picker UI prereq from June just got more urgent),
   laptop power brick on its own port… which no longer exists — power now
   shares a port with cameras. Check whether charging steals bandwidth
   (Jul 3 incident says it can); worst case, record on battery or introduce
   the one TB3-dock exception for power+cams.
4. **Only if 6-on-laptop fails → build the second node (§6).**

## 6. Plan B (and the past-6 path): the broken-screen MacBook as capture node

Fully researched, condensed to the decisions that matter:

- **It's viable, and the setup cost is one session with a borrowed
  monitor/TV.** Modern macOS cannot be bootstrapped blind: enabling Screen
  Sharing + SSH, auto-login, and the camera permission all need real GUI
  clicks once. In that single session: admin login → FileVault OFF →
  auto-login ON → Sharing: Remote Login + Screen Sharing ON → hostname
  `capture-node` → `sudo pmset -a sleep 0 displaysleep 1 disksleep 0` →
  install the Python env + recorder → **run the recorder once from
  Terminal.app and click Allow on the camera prompt** (permission sticks to
  Terminal.app — this is the make-or-break step) → test file on disk →
  done, unplug the monitor forever.
- **Day-to-day driving:** Screen Sharing from the main laptop (Finder →
  Network → capture-node). Recordings must be STARTED from a Terminal
  window inside Screen Sharing — SSH-launched processes are denied camera
  access by macOS (known OpenCV-on-Mac wall; SSH is fine for everything
  else). Leave the lid OPEN (dead screen shows nothing, avoids heat +
  sleep complications). Battery: check condition first; cap charge ~80%
  (AlDente free tier) since it lives plugged in.
- **Sync across two machines: the FLASH, not the clap.** Our OpenCV
  recorder writes silent video (OpenCV never records audio), so
  skelly_synchronize's audio method can't work cross-machine. Its
  brightness-flash method is official and fits: one bright flash visible
  to ALL cameras at take start (and one at the end to measure drift).
  Accuracy ≈ ±1 frame — at 60fps that's ~8ms, same tolerance the current
  rig already lives with. Do the clap too out of habit; the flash is the
  one that counts. (Per-frame timestamps in the recorder — already Tier 1
  on the adoptable-innovations list — become doubly valuable here.)
- **Getting takes off the node:** rsync-over-SSH one-liner in a
  double-clickable .command on the main laptop ("pull the node's takes"),
  run while packing up. No AirDrop, no fiddly SMB mounts.
- **Open items if we go here:** the spare's model/year + macOS version
  (determines Python/OpenCV support and adapter for the borrowed monitor),
  battery condition, and its own USB lane count (2 cameras is light duty —
  almost any MacBook manages 2).
- **Also the scaling story past 6:** every extra machine (or TB3-era dock
  with internal USB controller) adds lanes. 8 cameras = laptop's 6 + node's
  2, synced by the same flash. Nothing in the pipeline changes — FreeMoCap
  processes whatever synchronized folder we hand it.

## 7. How this feeds the pipeline (no surprises found)

- freemocap/anipose handle 6 cameras natively; outlier rejection (shipped
  1.4.17, default ON) is *specifically recommended for 4+ cameras* and gets
  more effective with 6 (more spare views to drop a bad one).
- `minimum_cameras_for_triangulation=3` stops being a floor-work compromise
  at 6 cams (a joint can lose three views and still triangulate).
- Recorder, sidecar, speed test, calibration, process, quality score: all
  already parameterized by camera list — no addon redesign required for 6.
  The two real software prereqs (both already queued): the camera-picker UI
  (enumeration instability × 6 is worse than × 4) and re-derived quality
  bands after the format/count change (recipe in the Jul 3 design note).

## 8. Suggested order of attack

1. Jul 7 sprint items stay first — nothing here blocks the student test,
   which runs on the proven 4-cam rig. (Eat vegetables before fun.)
2. §5.1 format check + §5.2 second-hub topology test (one BASEMENT visit,
   ~$25, definitive).
3. Buy list §4 → remount to the §3 layout in one deliberate session
   (this is also the height-diversity experiment from Jul 3 — same ladder
   time, one combined disruption) → fresh 6-cam calibration → A/B a floor
   -work take, 6-cam vs 4-cam config.
4. Camera-picker UI build lands before students touch the 6-cam rig.
5. Plan B node only on failure of §5, or later for 8.
