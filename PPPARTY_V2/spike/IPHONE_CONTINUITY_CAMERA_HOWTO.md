# iPhone Continuity Camera — How-To for the Dual-Cam Spike

Reference guide for using an iPhone as a second camera during `spike/dual_cam_test.py`. The point of using Continuity Camera is to get a high-quality second video source without buying hardware. The point of disabling effects is to make sure the noise comparison isn't polluted by Apple's ML post-processing (Center Stage panning, Studio Light relighting, etc.).

Cross-references:
- `spike/dual_cam_test.py` — the launcher this preflight prepares for
- `HANDOFF.md` — Day 8 evening section explains the strategic frame for the test

---

## Big Picture

You are NOT doing FreeMoCap-style multi-camera triangulation. The two cameras run independent MediaPipe pipelines. No Charuco board, no calibration. Two preview windows, eyeball-compare which has stiller hand landmarks.

iPhone effects to disable: **Center Stage, Portrait, Studio Light, Reactions.** All four add ML processing that confounds the noise comparison.

---

## Step 0 — Prerequisites

Both devices must meet these:

- **iPhone:** iOS 16 or later, signed in to your Apple ID
- **Mac:** macOS Ventura (13) or later, same Apple ID
- **Bluetooth and Wi-Fi ON on both** (Continuity uses these for handshake even via USB)
- **Two-Factor Auth enabled** on the Apple ID
- iPhone must be **unlocked** when you first connect (can re-lock once camera connection is live)

If any of those are off, the iPhone won't appear as a camera no matter what you do.

---

## Step 1 — Mount the iPhone physically

Camera stability matters more than you'd think. A wobbling phone produces noise that has nothing to do with MediaPipe or pixel density, and it'll pollute the comparison.

- **Bare-minimum mount:** lean it against books on the desk, rear camera facing you, screen down.
- **Better:** Apple's Continuity Camera magnetic mount (~$30), or any generic phone tripod mount.
- **Anchor it on something solid.** The whole experiment is "Cam 2 sees finger pixels with high density," and that thesis dies if the camera is shaking.

---

## Step 2 — Connect the iPhone

**Option A — wired (recommended):**
Plug iPhone into Mac via USB-C cable. Most reliable, also charges the phone.

**Option B — wireless:**
Have iPhone within ~30 feet of the Mac. Continuity will discover it automatically.

iPhone screen shows a small camera icon when it becomes the active camera — that's your confirmation.

---

## Step 3 — Wake the camera connection

The iPhone doesn't show up as an "available camera" to apps until something is actively using a camera. This trips people up.

**Easy way to wake it:** open Photo Booth (Applications → Photo Booth). It auto-grabs whatever camera comes up first.

Then check the camera dropdown:
- Photo Booth → **Camera menu** in the menu bar at the top of the screen
- You should see your iPhone listed (something like "David's iPhone Camera")
- Selecting it switches Photo Booth to iPhone view

If iPhone doesn't appear, see "Common Problems" at the end.

---

## Step 4 — Open Control Center to find Video Effects

The Video Effects tile only appears in Control Center while a camera is actively in use. So: Photo Booth is still running, showing iPhone view. Now:

1. Look at the **top-right corner of your menu bar**
2. Click the **Control Center icon** — two horizontal toggle switches stacked, right next to the clock/date
3. Control Center pops down with a grid of tiles (Wi-Fi, Bluetooth, AirDrop, Focus, etc.)
4. Look for a tile labeled **"Video Effects"** — it appears ONLY because Photo Booth is using a camera right now
5. Click that tile to expand its options

If you don't see "Video Effects":
- Verify the Photo Booth window is showing iPhone view, not built-in webcam
- Click the Photo Booth window once to activate it
- Some macOS versions show "Camera Effects" instead of "Video Effects"

---

## Step 5 — Disable the noise-confounding effects

Inside Video Effects, turn **OFF** these four:

| Effect | Why it must be off |
|---|---|
| **Center Stage** | Auto-pans/zooms to keep face centered. Will silently re-frame mid-test = different pixel density per frame = ruined comparison. |
| **Portrait** | Fakes background blur via depth-map ML. Smooths the background, can affect hand edges. |
| **Studio Light** | Relights face/scene using ML. Adds artificial smoothing. |
| **Reactions** | Triggers visual effects (heart-hands, fireworks, balloons) on gestures. Will literally explode confetti across the feed if you do anything hand-shaped. Catastrophic for a hand-tracking experiment. |

Leave **OFF** anything else (Desk View, etc.) — not relevant here.

**Mic Mode** options (Standard / Voice Isolation / Wide Spectrum) — don't care, no audio in this test.

---

## Step 6 — Verify the settings stuck

Settings should persist for the camera session. To verify before running the spike:

1. Quit Photo Booth (Cmd-Q)
2. Run the spike: `python3 spike/dual_cam_test.py --cam1 1 --cam2 0`
3. Once both preview windows are up, **re-open Control Center while the spike is running** (the spike has a camera active, so the Video Effects tile should reappear)
4. Confirm Center Stage, Portrait, Studio Light, Reactions all still show **off**

If settings reset: on some macOS versions effects are per-app. Set them while the spike's preview windows are active instead of while Photo Booth is.

---

## Running the Spike

From `SOFTWARE/PPPARTY_V2/`:

```bash
# Default — assumes Cam 1 = body sender, Cam 2 = hands sender
python3 spike/dual_cam_test.py

# Most common iPhone-as-Cam-2 invocation:
# Continuity Camera typically grabs index 0, MBP built-in goes to index 1
python3 spike/dual_cam_test.py --cam1 1 --cam2 0

# Headless (FPS in stdout only, no preview windows)
python3 spike/dual_cam_test.py --no-preview
```

What you should see:
- Two terminal lines confirming the cam→port assignments
- Two OpenCV preview windows pop up (5–10s on first run while models download)
- Each window shows: camera feed, MediaPipe skeleton overlay, FPS counter

Ctrl-C to stop both senders cleanly.

---

## Camera Order Verification

macOS enumerates AVFoundation devices in an order that depends on connection time. Typical pattern:

- Continuity Camera connected first → it grabs **index 0**
- Built-in MBP webcam → pushed to **index 1**

But not guaranteed. Trust your eyes on the preview windows — if both windows show the wrong camera, swap `--cam1` and `--cam2` numbers.

**Quick way to check what's at each index:** open Photo Booth → New Movie Recording → click camera dropdown. The order Apple lists them is *probably* the index order.

---

## What to Watch For (BASEMENT test)

Three things to look for in the preview windows:

1. **Compute (yes/no):** Both windows holding 30 FPS? Or does one drop?
2. **Visual hand stability:** Hold hand still in front of both cams. Are Cam 2's MediaPipe dots noticeably stiller than Cam 1's?
3. **Independent failure modes:** Move hand toward face. Single-cam, hand-on-face is THE failure case. With Cam 2 from a different angle, does it still see the hand cleanly when Cam 1 has the occlusion? **This is the killer feature** — not just "less noise," but redundant coverage that handles the worst case.

---

## Decision Tree (from `HANDOFF.md`)

| What you see | What it means |
|---|---|
| 2× holds 30 FPS, Cam 2 visibly cleaner, handles occlusion | Asymmetric is a sure thing. Phase 7+ enhancement. Design hand-only sender variant + fusion pattern. |
| 2× drops below 30 FPS but compute might fit at 1.4× | Write hand-only sender variant first, retest. |
| Cam 2 hand quality NOT visibly better | Multi-cam thesis weakened. Pivot to other 1.b levers (heavier tip One Euro, palm-normal `side_ref`). |

---

## Common Problems

**iPhone doesn't appear in camera list:**
- iPhone locked? Unlock it.
- iPhone in Low Power Mode? Disable, it can suspend Continuity.
- Same Apple ID? Settings → Apple Account on iPhone, top-right Apple icon on Mac.
- Try toggling Bluetooth off/on on both devices.
- Last resort: restart both. Usually fixes it.

**iPhone connects but goes black after a few seconds:**
- iPhone Settings → General → AirPlay & Continuity → **Continuity Camera ON**.
- If wireless is flaky, plug in USB-C — wired is more stable.

**Frame rate is terrible:**
- Continuity Camera caps at 1080p30 by default — should be plenty.
- If FPS is sub-15, the bottleneck is MediaPipe + macOS, not the camera.
- Worth noting as a finding regardless.

**Cmd-Tab doesn't show the OpenCV preview windows:**
- Different window class. Use Mission Control (F3 or three-finger swipe up). Sometimes hidden behind Photo Booth.

**Two cameras crash macOS or one cam drops out:**
- USB bandwidth saturation. Try a powered USB hub, or split across USB-A and USB-C controllers.
- Lower resolution if needed (senders default to 640×480 already).

---

## Caveats to Remember

- **This is NOT on V2's critical path.** Main path is item 1.a (percentile tweak in `_apply_median_hand_scale`). Spike result feeds into the rotation-noise research doc (item 1.b), it doesn't replace it.
- **Today's test is the conservative case (2× compute).** `hand_sender.py` runs both Pose AND Hand. The true asymmetric 1.4× version (hand-only sender) doesn't exist yet — would be ~30 lines stripping Pose out of `hand_sender.py`. If 2× holds 30 FPS, 1.4× is a guaranteed win.
- **No camera calibration is required.** Each sender stays monocular. MediaPipe `hand_world_landmarks` is already in hand-local frame, so any future fusion (Cam 2 contributes finger joint angles, Cam 1 contributes wrist position) doesn't need to know where the cameras are in space relative to each other.
