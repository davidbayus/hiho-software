# HIHO Mocap — Adoptable Innovations from Dennis Shtatnov's DIY System

**Date:** 2026-06-17
**Author:** David Bayus + Claude
**Status:** Brainstorm / Roadmap
**Source:** `made-by-dennis-mocap-research.md` (deep dive on Dennis's 16-camera marker-based system)

---

## What This Document Is

Dennis Shtatnov built a 16-camera, 240fps, sub-millimeter precision motion capture system from scratch — custom PCBs, custom software, the whole thing. His system is **marker-based** (retroreflective dots + infrared cameras), while HIHO is **markerless** (MediaPipe sees your body through regular webcams). We can't just swap in his system — the approaches are fundamentally different, and HIHO's classroom-friendly, no-markers-needed simplicity is a core strength we don't want to lose.

But Dennis solved several engineering problems that HIHO also faces: camera synchronization, USB bandwidth limits, cable length constraints, and processing bottlenecks. **This document pulls out the ideas we CAN adopt** and sorts them from "do it this summer" to "dream big."

Each idea includes: what it is in plain English, which HIHO pain point it addresses, rough cost, technical difficulty (1–5 scale), what needs to exist first, and what could go wrong.

**Difficulty scale:**
- **1** = David could set it up himself with existing documentation
- **2** = Needs some Python scripting or config work, Claude can help
- **3** = Real programming project, might take a week or two
- **4** = Significant engineering effort, might need outside expertise
- **5** = Research-level work, needs serious engineering or hardware design

---

## Current HIHO Pain Points (for reference)

These are the problems we're trying to solve. Each idea below tags which pain point(s) it addresses.

| # | Pain Point | What's Happening |
|---|---|---|
| **P1** | USB bandwidth ceiling | macOS UVC limits mean 4 cameras can't all run on one USB bus. Currently split across multiple USB-C ports. |
| **P2** | Frame rate jitter | Webcam frame delivery isn't perfectly timed. Timestamps drift, causing jitter in the final mocap. |
| **P3** | Hand tracking bottleneck | MediaPipe hand tracking is computationally expensive across all 4 feeds simultaneously. |
| **P4** | Cable length limits | Active USB 3.0 extensions max out at ~16ft, constraining camera placement. |
| **P5** | Frame count synchronization | Current workaround is frame-count-bounded recording, but true temporal sync would be better. |
| **P6** | FreeMoCap bugs | 22 documented bugs, many related to the GUI and pipeline assumptions (see `BUGS_AND_BACKLOG.md`). |

---

## TIER 1: THIS SUMMER

*Feasible with the existing 4× Logitech C922x cameras, MacBook, and Python/OpenCV. Software-only improvements or minor additions under $100. No new cameras, no new infrastructure.*

---

### 1.1 — Per-Frame Timestamp Recording + Post-Hoc Alignment

**What it is:** Right now, the Camera Manager records frames in a tight loop and relies on frame *counting* to keep cameras in sync (every camera records exactly N frames). This works, but it doesn't account for the fact that frame delivery from USB webcams isn't perfectly regular — one camera might deliver its 100th frame 50 milliseconds before another camera delivers its 100th frame. The fix: record a high-resolution timestamp (using Python's `time.perf_counter()` or `time.monotonic()`) alongside every single frame. Then, in post-processing, resample all cameras to a common timeline using interpolation. Frames that arrived early or late get time-shifted to where they should have been.

Dennis's system solves this with hardware (PTP gives nanosecond sync). We can't match that precision, but we can get from "best-effort frame counting" to "software-corrected millisecond-level alignment" — which is a meaningful improvement for 30fps capture.

**Why it helps:** Reduces frame-rate jitter in the final mocap data. **(P2, P5)**

**Rough cost:** $0 — pure software change.

**Difficulty:** 2 — Needs modifications to the Camera Manager's recording loop (add timestamp logging) and a post-processing script that resamples the data. The math is straightforward linear interpolation.

**Dependencies:** The Camera Manager (`core/camera_manager.py`) needs to exist and be working. It already records frames per-camera in separate threads, so adding timestamps is a small change to each thread's loop.

**Risks/unknowns:**
- Python's `time.perf_counter()` has microsecond resolution on macOS, which is more than enough for 30fps (33ms between frames). No risk there.
- The interpolation step happens after FreeMoCap processes the videos, so it would need to operate on the 3D landmark data (the `.npy` output), not on the raw video frames. This means understanding FreeMoCap's output format.
- Won't eliminate jitter entirely — if a camera drops a frame, interpolation can only estimate what happened. But it'll smooth out the common case of "frames arrived slightly out of phase."

---

### 1.2 — Multiprocess MediaPipe (Bypass the Python GIL)

**What it is:** Python has a thing called the GIL (Global Interpreter Lock) that prevents true parallel processing within a single program. Right now, when FreeMoCap runs MediaPipe on 4 camera feeds, it's effectively doing them one at a time even if your Mac has 8+ CPU cores sitting idle. The fix: run MediaPipe for each camera in its own *process* (not thread) using Python's `multiprocessing` module. Each process gets its own GIL, so all 4 cameras get processed genuinely in parallel.

Dennis's approach was to write everything in Rust (which has no GIL) and run processing on each camera's Raspberry Pi. We can't do that, but we can use Python's built-in multiprocessing to get 4× parallelism on the processing step.

**Why it helps:** Could cut MediaPipe processing time by up to 4× on a multi-core Mac. Directly addresses the hand tracking / pose estimation bottleneck. **(P3)**

**Rough cost:** $0 — software change to the processing pipeline.

**Difficulty:** 3 — This requires modifying how FreeMoCap invokes MediaPipe, or writing a wrapper that pre-processes videos in parallel before feeding results back to FreeMoCap's triangulation step. The tricky part is managing shared memory for the output data and making sure the results still feed correctly into the Anipose triangulation step.

**Dependencies:** Understanding FreeMoCap's `process_recording_headless()` internals well enough to know where to insert the parallelism. The headless processing flow is documented in `HEADLESS_FREEMOCAP_DESIGN_2026-06-01.md`.

**Risks/unknowns:**
- Memory usage: each MediaPipe process loads its own copy of the ML model into RAM. With 4 processes, that's 4× the model memory. On a MacBook with 16GB+ RAM this should be fine, but worth testing.
- Startup overhead: spawning processes is slower than spawning threads. For a 30-second recording this overhead is negligible; for a 5-second test clip it might matter.
- This might already be partially addressed by FreeMoCap's pipeline — need to check if they already parallelize. If they do, the win is smaller.

---

### 1.3 — Selective Hand Tracking (Only Process Hands Where You Need Them)

**What it is:** Instead of running full hand tracking on all 4 camera feeds, only run it on the 2 cameras that have the best view of the hands. Body pose estimation runs on all 4 cameras (it's faster), but hand tracking — the expensive part — only runs on cameras where the hands are most visible. You could determine "best view" either statically (the front-facing cameras) or dynamically (whichever cameras see the largest hand bounding box).

Dennis's system doesn't have this problem because marker detection is extremely cheap (just finding bright dots). But the *principle* — don't process data you don't need — is universal.

**Why it helps:** Cuts hand tracking compute by ~50% with minimal quality loss, since hand triangulation only needs 2 good views anyway. **(P3)**

**Rough cost:** $0 — software change.

**Difficulty:** 2 — If you do it statically (hard-code which 2 cameras track hands), it's straightforward. Dynamic selection based on hand visibility is harder (difficulty 3).

**Dependencies:** Needs to be implemented as a configuration option in the processing pipeline. Either a wrapper around FreeMoCap's MediaPipe invocation, or a pre-filtering step.

**Risks/unknowns:**
- If the performer turns around, the "best" cameras for hands change. Static selection breaks in this case.
- Triangulation quality for hands depends on having two cameras with good angular separation. If both selected cameras are on the same side, hand depth estimation suffers.
- FreeMoCap may not easily support per-camera tracking options — might need to patch their code.

---

### 1.4 — Lower-Resolution Hand Detection Pass

**What it is:** Run the initial hand *detection* (finding where hands are in the frame) at a lower resolution like 480×270, then crop the region around each detected hand and run the full landmark estimation on just that crop at full resolution. This is a two-pass approach: cheap detection, then expensive estimation only where needed.

This is inspired by how Dennis's system works conceptually — his cameras process tiny regions of interest (the bright blobs) rather than analyzing the entire image. We're applying the same "find the interesting part, then zoom in" logic to markerless tracking.

**Why it helps:** Detection is the screening step — most of each frame is background. Running it at 1/4 resolution is roughly 4× cheaper. Landmark estimation (the expensive part) runs on a small crop instead of the full frame. Net effect: faster hand tracking. **(P3)**

**Rough cost:** $0 — software change.

**Difficulty:** 3 — MediaPipe's API doesn't natively support this two-pass approach. You'd need to manually run the hand detector at low resolution, compute the crop coordinates, extract the crop from the full-res frame, and run the hand landmark model on the crop. This is doable with MediaPipe's individual model components but requires understanding their internal pipeline.

**Dependencies:** MediaPipe's hand detection and landmark models need to be invokable separately (they are, through the lower-level API).

**Risks/unknowns:**
- At very low detection resolution, small or distant hands might be missed entirely.
- The crop-and-estimate approach adds code complexity. If MediaPipe updates their API, this custom pipeline might break.
- Might not work cleanly with FreeMoCap's existing pipeline — could require a custom MediaPipe runner that replaces FreeMoCap's built-in one.

---

### 1.5 — Audio Sync Pulse (Poor Man's Hardware Trigger)

**What it is:** At the start of each recording, play a sharp audio tone (a click or beep) from a speaker. All cameras pick up the audio through their built-in microphones (the C922x has dual mics). In post-processing, detect the audio pulse in each camera's audio track and use it as a synchronization reference — like a digital clapperboard.

Dennis uses PTP + hardware triggers for nanosecond sync. We can't match that, but an audio pulse gives us a physical reference point that's better than software timestamps alone. The speed of sound introduces ~1ms of delay per foot of distance between speaker and camera, but at our scale (cameras within 10 feet of each other) that's under 10ms — well within one frame at 30fps.

**Why it helps:** Gives a physical synchronization reference that's independent of software timing. Can be combined with timestamp correction (1.1) for best results. **(P2, P5)**

**Rough cost:** $0 — use the laptop's built-in speaker. Or ~$10 for a small Bluetooth speaker placed centrally.

**Difficulty:** 2 — Playing the tone is trivial (Python `sounddevice` or just a system beep). Detecting it in the audio track requires a simple peak-detection algorithm. Aligning the video streams based on the audio reference is straightforward.

**Dependencies:** Cameras must record audio (C922x does by default, but the Camera Manager's `cv2.VideoWriter` setup needs to include audio. Currently it records video-only. Adding audio recording is a small addition).

**Risks/unknowns:**
- OpenCV's `VideoWriter` doesn't support audio natively. You'd need to use a different recording approach (like `ffmpeg` subprocess) or record audio separately and mux later.
- Noisy environments (classroom, event space) could make the sync pulse harder to detect. Solution: use a distinctive frequency (like 1kHz sine burst) and filter for it.
- Adds a small amount of complexity to the recording pipeline.

---

### 1.6 — Adopt Dennis's Documentation Standard

**What it is:** Dennis's GitHub documentation is exceptional — every component has datasheet references, every design decision is explained with alternatives listed and trade-offs discussed, and the whole project is navigable by someone who wasn't there when it was built. HIHO already has good documentation (this doc, `ARCHITECTURE.md`, `BUGS_AND_BACKLOG.md`), but we can level up by adding: component datasheets / spec sheets for every piece of hardware, a decision log (why we chose X over Y), and a "new contributor" guide.

**Why it helps:** Makes the project sustainable beyond David's involvement. Essential for K-12 deployment where other teachers will need to set up and troubleshoot the system. Also directly supports the dissertation's documentation requirements. **(General sustainability)**

**Rough cost:** $0 — just writing.

**Difficulty:** 1 — No code required. It's writing that David can do himself (with Claude's help).

**Dependencies:** None.

**Risks/unknowns:** The only risk is time investment. Documentation takes hours. But given that HIHO is both a tool and a dissertation project, the documentation IS part of the deliverable.

---

### 1.7 — Threading Optimization in Camera Manager

**What it is:** The current Camera Manager uses one thread per camera with a shared buffer protected by `threading.Lock`. This is correct but could be optimized. Improvements include: using `threading.Event` more aggressively to reduce lock contention, adding a `collections.deque` with a small fixed size (3-5 frames) instead of a single-frame buffer to absorb timing jitter, and using `cv2.VideoCapture.grab()` + `retrieve()` instead of `read()` to separate the timing-critical grab from the expensive decode.

Dennis's system avoids these issues entirely by using dedicated hardware per camera. But within the constraints of "4 USB cameras on one Mac," these threading optimizations are the equivalent of tuning the engine we've got.

**Why it helps:** Reduces frame delivery jitter and improves recording stability. The `grab()`/`retrieve()` split is especially valuable — `grab()` latches the frame from the USB buffer immediately (microseconds), while `retrieve()` does the JPEG decode (milliseconds). By grabbing from all cameras first and decoding second, you get tighter temporal alignment. **(P2, P5)**

**Rough cost:** $0 — software change to `camera_manager.py`.

**Difficulty:** 2 — Straightforward Python threading changes. The `grab()`/`retrieve()` pattern is well-documented in OpenCV.

**Dependencies:** Camera Manager exists and is working.

**Risks/unknowns:**
- The `grab()`/`retrieve()` pattern helps most when cameras are connected to different USB buses (which they are in HIHO's setup). If they share a bus, `grab()` calls still serialize at the USB level.
- Small deque buffer adds a frame or two of latency to the preview. Acceptable since preview is already at 10Hz.

---

## TIER 2: FALL SEMESTER

*Moderate hardware investment ($100–500) or significant software work. Testable with students during Fall 2026. Good candidates for student research projects at CADRE.*

---

### 2.1 — Test a Single PoE IP Camera Alongside USB Cameras

**What it is:** Buy one PoE IP camera (a regular surveillance camera, not a custom Dennis-style module) and integrate it as a 5th camera alongside the existing 4 USB webcams. This tests the core idea from Dennis's system — network-based camera connectivity — without replacing anything. The IP camera connects via Ethernet to the Mac (through a PoE switch or injector that provides power over the cable). You'd write a small RTSP or ONVIF client in Python to capture frames from it.

This is a proof-of-concept: does a network camera produce usable data for markerless mocap? Can it coexist with USB cameras in the same pipeline?

**Why it helps:** Tests the viability of PoE cameras for HIHO without commitment. If it works, it's the first step toward eliminating USB entirely. Also immediately adds a 5th camera angle, which improves triangulation. **(P1, P4 — testing the solution)**

**Rough cost:** $80–200 for a PoE IP camera (Reolink, Hikvision, Amcrest all make affordable PoE cameras with 1080p+). $30–50 for a PoE injector (single-port device that adds power to an Ethernet cable). Total: **$110–250**.

**Difficulty:** 3 — Writing the RTSP capture client is straightforward (OpenCV can open RTSP streams with `cv2.VideoCapture("rtsp://...")`). The harder part is synchronizing the IP camera's frames with the USB cameras' frames, since they're on completely different timing systems. You'd need the timestamp correction from Tier 1.1 to be working first.

**Dependencies:**
- Tier 1.1 (timestamp-based sync) should be in place, since the IP camera and USB cameras won't share any sync mechanism.
- A wired Ethernet connection to the Mac (USB-C Ethernet adapter if the Mac doesn't have a port).
- Camera Manager needs to support "generic" frame sources, not just OpenCV USB capture. The IP camera's RTSP stream can be opened with `cv2.VideoCapture()` using a URL instead of an index, so this might work with minimal changes.

**Risks/unknowns:**
- **Latency.** RTSP streams typically have 100–300ms of latency due to buffering. This is much worse than USB's near-zero latency. The frames will be "late" compared to USB cameras. Post-hoc timestamp alignment can correct for constant latency, but variable latency (network jitter) is harder.
- **Resolution/framerate mismatch.** IP cameras may default to different resolutions or framerates than the C922x webcams. Need to configure them to match.
- **Color/exposure differences.** Different camera sensors produce different color profiles. MediaPipe should handle this, but the 3D reconstruction might show artifacts where the IP camera's data joins the USB cameras' data.
- **Network setup.** Students need to configure an IP address for the camera. Not hard, but it's a new skill for most.

**Student project potential:** HIGH — this is a well-scoped semester project. "Integrate a PoE IP camera into HIHO Mocap and measure the impact on tracking quality."

---

### 2.2 — Visual Sync Signal (LED Flash + Software Detection)

**What it is:** Instead of an audio sync pulse (Tier 1.5), use a visual one: a bright LED flash visible to all cameras at the start of recording. In post-processing, detect the flash frame in each camera's video and use it as the sync reference. Think of it as a strobe-light clapperboard.

This is a simplified version of Dennis's approach — his IR LEDs strobe synchronized to the camera trigger. We can't trigger our cameras, but we can use a shared visual event as a synchronization anchor.

**Why it helps:** More reliable than audio in noisy environments. Works even if cameras don't record audio. Combined with timestamp correction, gives the best synchronization possible without hardware camera triggers. **(P2, P5)**

**Rough cost:** ~$10–30 for a small bright LED or flash unit that can be triggered from the computer (an Arduino with an LED, or even a USB-controlled LED strip). Or $0 if you use the laptop screen flash.

**Difficulty:** 2 — The LED trigger is simple. Flash detection in video is basic computer vision (find the frame with the biggest brightness spike). Alignment math is the same as the audio approach.

**Dependencies:** All cameras must have line-of-sight to the LED. In a surround capture setup (cameras on all sides), the LED needs to be centrally placed or omnidirectional.

**Risks/unknowns:**
- Rolling shutter on the C922x means the flash might not illuminate the entire frame uniformly — the top and bottom of the image are captured at slightly different times. This limits sync precision to about 1 frame (33ms at 30fps).
- A very bright flash could briefly blow out the exposure on nearby cameras, causing MediaPipe to lose tracking for a frame or two right at the start.

---

### 2.3 — Dedicated Hand Camera(s)

**What it is:** Add 1–2 small cameras positioned specifically to capture hand close-ups (pointed at the performer's hands from a close, angled position). These cameras ONLY feed hand tracking — they don't contribute to body pose estimation. The existing 4 cameras handle body tracking. This separates the "body problem" from the "hand problem."

Dennis's system uses 16 cameras in part to get enough angular coverage for finger-level detail. We can't afford 16 cameras, but adding 2 dedicated hand cameras is a targeted investment that addresses the single most expensive processing step.

**Why it helps:** Hand cameras can run at higher resolution (since they only see a small area), giving MediaPipe better input for hand tracking. The body cameras can skip hand tracking entirely, cutting their processing load. **(P3)**

**Rough cost:** $50–100 per camera. Budget options: Logitech C270 ($20), ELP USB cameras ($30–60), or another C922x ($90). Total for 2 cameras: **$40–200**.

**Difficulty:** 3 — The cameras themselves are plug-and-play. The challenge is in the software: the Camera Manager needs to support different "roles" for different cameras (body vs. hands), and the processing pipeline needs to merge hand data from the hand cameras with body data from the body cameras. This is non-trivial integration work.

**Dependencies:**
- Camera Manager supporting 6 cameras (USB bandwidth becomes a bigger issue — may need more USB-C ports or a powered hub on a dedicated bus).
- Processing pipeline that can merge landmarks from different camera subsets.
- Physical mounting for hand cameras (small tripods or clamps positioned near the performance area).

**Risks/unknowns:**
- **USB bandwidth with 6 cameras.** The MacBook might not handle 6 simultaneous USB video streams. This could force the PoE IP camera approach for the hand cameras specifically.
- **Calibration complexity.** All 6 cameras need to be calibrated together (same coordinate system). Adding cameras means the ChArUco board needs to be visible to all cameras simultaneously, which is harder with close-up hand cameras.
- **Occlusion.** Close-up hand cameras have a narrow field of view. If the performer moves their hands outside the hand cameras' view, you lose hand data entirely until they bring their hands back.

---

### 2.4 — GPU-Accelerated Pose Estimation on Apple Silicon

**What it is:** MediaPipe currently runs on CPU on macOS. Apple Silicon Macs (M1/M2/M3/M5) have powerful GPU and Neural Engine hardware that sits idle during processing. Explore running pose estimation on the GPU using either MediaPipe's GPU delegate, Apple's CoreML framework (by converting the MediaPipe model to CoreML format), or an alternative pose estimator that supports Metal (Apple's GPU API).

Dennis wrote custom Rust code that's 300× faster than OpenCV for his specific task. We can't rewrite MediaPipe, but we CAN try to run it on the right hardware.

**Why it helps:** Could provide 2–5× speedup in pose estimation, making real-time processing more feasible and reducing the time students wait after a capture. **(P3)**

**Rough cost:** $0 — the GPU hardware already exists in the Mac.

**Difficulty:** 4 — MediaPipe's macOS GPU support is experimental and poorly documented. Converting to CoreML requires understanding both model formats. Alternative pose estimators (like RTMPose via ONNX Runtime with CoreML backend) exist but haven't been tested with FreeMoCap.

**Dependencies:**
- Apple Silicon Mac (already have this).
- Understanding of CoreML model conversion pipeline (coremltools Python package).
- Willingness to potentially fork FreeMoCap's MediaPipe integration.

**Risks/unknowns:**
- **MediaPipe's GPU delegate on macOS is buggy.** Google's primary platform for MediaPipe GPU is Android. macOS support is second-class. Could waste significant time debugging.
- **CoreML conversion.** The MediaPipe hand model is a custom architecture that may not convert cleanly to CoreML. Missing operations or precision mismatches could produce wrong results.
- **Alternative pose estimators change the whole pipeline.** If you switch from MediaPipe to RTMPose, FreeMoCap's internals need modification. This is a deep fork.
- **Quality vs. speed tradeoff.** GPU-accelerated models sometimes sacrifice accuracy for speed. Need to verify that tracking quality doesn't degrade.

**Student project potential:** VERY HIGH — this is a great graduate research project. "Accelerating markerless motion capture on Apple Silicon using CoreML."

---

### 2.5 — Smarter Frame Dropping + Interpolation in the Pipeline

**What it is:** Instead of requiring exact frame-count parity (FreeMoCap's current constraint, documented in `BUGS_AND_BACKLOG.md` Bug #5), build a smarter sync layer that: (a) accepts variable frame counts per camera, (b) uses timestamp data to identify the closest matching frames across cameras, (c) interpolates 3D landmark positions when frames don't align perfectly. This is essentially building a proper temporal alignment engine — what professional mocap systems call "timecode-based synchronization in post."

Dennis doesn't need this because his hardware guarantees every camera fires at exactly the same instant. But for software-synced USB cameras, this kind of post-processing alignment is the practical path to clean data.

**Why it helps:** Removes the brittleness of frame-count-bounded recording. Allows for dropped frames without ruining a take. Produces smoother motion data. **(P2, P5, P6 — several FreeMoCap bugs relate to sync requirements)**

**Rough cost:** $0 — software.

**Difficulty:** 3 — The math (temporal interpolation of 3D points) is well-understood. The engineering challenge is integrating it into the pipeline — either as a post-processing step after FreeMoCap, or as a replacement for FreeMoCap's sync assumptions.

**Dependencies:**
- Tier 1.1 (per-frame timestamps) must be in place — interpolation requires knowing when each frame was captured.
- Understanding FreeMoCap's internal data format well enough to post-process it.

**Risks/unknowns:**
- Interpolation introduces smoothing. Very fast movements (hands, head turns) could be artificially dampened. Need to use appropriate interpolation (cubic spline, not linear) and validate against known motions.
- FreeMoCap might reject recordings that don't meet its frame-count requirements before we get a chance to post-process. May need to patch FreeMoCap to be more tolerant.

---

## TIER 3: NEXT YEAR

*Bigger architectural changes that need experimentation. Could be summer 2027 work or ongoing research projects.*

---

### 3.1 — Full Migration from USB Webcams to PoE IP Cameras

**What it is:** Replace all 4 (or more) USB webcams with PoE IP cameras. Every camera connects via a single Ethernet cable (which carries both data AND power) to a PoE network switch, which connects to the host computer. No USB involved at all. This is the core of Dennis's architecture adapted for markerless mocap.

**Why it helps:** Eliminates USB bandwidth ceiling entirely — each camera gets its own dedicated Ethernet connection with 100 Mbps+ bandwidth (vs. sharing a USB bus). Ethernet cables run up to 328 feet (vs. 16 feet for USB). Power comes over the same cable, so no separate power adapters or USB hubs. Scales to 8, 12, 16+ cameras by adding more switch ports. **(P1, P4 — completely solves both)**

**Rough cost:** $150–300 per camera × 4 = $600–1,200 for cameras. $80–200 for a managed PoE switch (8-port). $20–40 for a USB-C Ethernet adapter. Total: **$700–1,450**. Comparable to the current 4× C922x setup ($748) if you pick budget cameras.

**Difficulty:** 4 — The cameras themselves are standard products. The challenge is: (a) writing/adapting the Camera Manager to capture from RTSP/ONVIF streams instead of USB, (b) dealing with network latency and buffering, (c) achieving acceptable frame synchronization without hardware sync, and (d) verifying that MediaPipe works well on IP camera footage (different compression, color profile, etc.).

**Dependencies:**
- Successful Tier 2.1 proof-of-concept (single PoE camera tested).
- Timestamp-based sync (Tier 1.1) proven and working.
- Network infrastructure in the capture space (switch, cables, power).

**Risks/unknowns:**
- **Latency.** RTSP adds 100–500ms of latency. For live preview this is noticeable. For recorded processing (capture first, process later) it doesn't matter. But if you ever want real-time mocap (preview of your skeleton while performing), latency becomes a problem.
- **Camera selection.** Not all IP cameras produce footage that works well with MediaPipe. Need to test specific models. Look for cameras with: manual exposure control, configurable framerate, RTSP support, PoE 802.3af compliance, and ideally a global shutter.
- **Cost per camera.** Budget PoE cameras ($80–150) exist but tend to have aggressive compression (H.265) that may degrade tracking. Higher-quality cameras ($200–400) with less compression produce better data but cost more.
- **Cross-platform.** RTSP capture works on Mac, Windows, and Linux — no OS-specific issues. This is actually *better* than USB, where macOS has unique UVC limits.

---

### 3.2 — PTP (Precision Time Protocol) for Camera Synchronization

**What it is:** PTP is a networking standard (IEEE 1588) that synchronizes clocks across networked devices to nanosecond accuracy. Dennis uses it to ensure all 16 cameras fire at exactly the same instant. Some commercial IP cameras support PTP natively — if we migrate to PoE cameras (Tier 3.1), we could select PTP-capable models and get hardware-level synchronization without custom electronics.

**Why it helps:** True hardware sync between cameras. No more jitter, no more timestamp correction, no more frame-count workarounds. Every camera captures at exactly the same moment. This is the gold standard for multi-camera systems. **(P2, P5 — completely solves both)**

**Rough cost:** PTP-capable IP cameras cost $300–600 each (Basler, FLIR/Teledyne, Allied Vision are the main brands). A PTP-capable managed switch is $150–400. For 4 cameras: **$1,350–2,800**.

**Difficulty:** 4 — The cameras and switch do the hard work. Configuration involves setting up PTP master/slave relationships on the switch and enabling PTP on each camera. The tricky part is that PTP synchronizes *clocks*, not *triggers* — you still need to configure the cameras to capture at a synchronized rate, which usually means using the camera's trigger input or a software trigger timed to the PTP clock. Some cameras support "free-run with PTP timestamp" which is simpler.

**Dependencies:**
- Tier 3.1 (PoE camera migration) — PTP only works on networked cameras.
- A managed Ethernet switch that supports PTP (IEEE 1588v2). Consumer switches don't have this.
- Camera models that support PTP. This limits your options significantly.

**Risks/unknowns:**
- **Camera cost.** PTP-capable cameras are 2–4× more expensive than regular IP cameras. This pushes the system away from HIHO's "affordable for classrooms" goal.
- **PTP + markerless is untested.** PTP is standard in marker-based and industrial vision. Nobody (that we know of) is using PTP-synced cameras for MediaPipe-based markerless mocap. We'd be the first, which means unknown integration challenges.
- **Complexity.** PTP configuration requires understanding network timing protocols. It's not plug-and-play. One misconfigured device can throw off the whole system.

---

### 3.3 — Higher Framerate Capture (120fps+)

**What it is:** The C922x webcams capture at 30fps (or 60fps at 720p). Dennis's system runs at 240fps. Higher framerates mean more data points per second of motion, which means smoother animation and the ability to capture fast movements (hand gestures, dance moves, combat choreography) without blur or aliasing.

**Why it helps:** 30fps misses a lot of motion detail. At 120fps, you have 4× the temporal resolution — fast hand movements that are a blur at 30fps become trackable. The resulting animation is smoother and more nuanced. **(P2 — more frames means less interpolation needed, and the general quality ceiling rises)**

**Rough cost:** High-framerate cameras that work with MediaPipe: ELP USB cameras with 120fps modes ($50–80 each), PlayStation Eye cameras ($10 used, 120fps at 320×240 — too low-res), or industrial USB3 cameras ($200–500 each). For 4 cameras: **$200–2,000** depending on the path.

**Difficulty:** 3 — If you find cameras that work with OpenCV at 120fps, the Camera Manager just needs a framerate config change. The bigger challenge is processing: MediaPipe at 120fps means 4× the processing load, which makes the hand tracking bottleneck (P3) 4× worse. Dennis avoids this because his processing (blob detection) is trivially cheap. Markerless pose estimation is not.

**Dependencies:**
- Cameras capable of 120fps+ at 720p or higher resolution.
- Either GPU-accelerated MediaPipe (Tier 2.4) or selective processing (skip frames for tracking, interpolate).
- Higher storage bandwidth — 4 cameras at 120fps produces 4× more video data.

**Risks/unknowns:**
- **Processing bottleneck scales with framerate.** Going from 30fps to 120fps means MediaPipe needs to process 4× more frames. Without GPU acceleration or frame-skipping, processing a 30-second take could take 20+ minutes.
- **USB bandwidth at 120fps.** Streaming 4 cameras at 120fps over USB is almost certainly beyond what macOS UVC can handle on a single bus. This likely requires the PoE migration (Tier 3.1) first.
- **Diminishing returns for educational use.** For the "record a walk cycle" classroom exercise, 30fps is fine. 120fps matters for fast action capture (martial arts, dance, sports). Worth asking: does the educational use case need this?

---

### 3.4 — Edge Computing: Pi-Based Preprocessing Per Camera

**What it is:** Attach a Raspberry Pi (or similar small computer) to each camera. The Pi does some preprocessing — image resizing, background subtraction, even a lightweight pose detection pass — before sending the results to the host computer over the network. This distributes the computational load across multiple small computers instead of dumping everything on one Mac.

This is directly inspired by Dennis's architecture, where each Pi runs blob detection and only sends marker positions to the host. The difference: we'd need each Pi to run a lightweight version of MediaPipe or a faster alternative.

**Why it helps:** Offloads processing from the host Mac, enabling more cameras without overwhelming the host. Each Pi handles its own camera's data in parallel. **(P3 — distributes the bottleneck)**

**Rough cost:** $45–75 per Raspberry Pi 5 × 4 = $180–300 for Pis. Plus $50–100 for power supplies, cables, and cases. The cameras could be USB cameras plugged directly into their respective Pis. Total: **$230–400** on top of existing camera cost.

**Difficulty:** 5 — This is a significant systems engineering project. Each Pi needs to: (a) capture video from its camera, (b) run some form of pose preprocessing, (c) stream results to the host over the network. MediaPipe runs on Pi but SLOWLY — a Raspberry Pi 5 can manage maybe 5–10fps with MediaPipe, not 30fps. You'd likely need a lighter pose estimator (MoveNet, PoseNet, or a custom model optimized for Pi). The host then needs to merge preprocessed data from all Pis and run the triangulation step.

**Dependencies:**
- Network infrastructure (all Pis + host on same network).
- A lightweight pose estimator that runs at 30fps on a Pi (this may not exist yet for hands).
- Custom software for the Pi capture + stream pipeline.
- A redesigned host pipeline that accepts preprocessed data rather than raw video.

**Risks/unknowns:**
- **Pi processing speed.** MediaPipe on a Pi 5 is slow. This approach might not work until there's a model lightweight enough to run at full framerate on Pi hardware. Body-only (no hands) might be feasible; hands are the problem.
- **Complexity explosion.** Instead of managing 1 computer, you're managing 5 (1 host + 4 Pis). Each Pi is a little Linux computer that needs OS updates, network config, and custom software. This is exactly the maintenance burden Dennis's system has, which the research report flagged as a problem for classrooms.
- **Power.** 4 Pis need power. If using PoE cameras on the Pis, the Pi itself still needs a separate power source (unless you use a PoE hat for the Pi — these exist but add $20 per Pi).

---

### 3.5 — IR Illumination for Consistent Tracking

**What it is:** Add infrared lighting panels to the capture space. Near-infrared light (850nm) is invisible to humans but visible to most camera sensors. It provides consistent, shadow-free illumination regardless of the room's ambient lighting. Dennis's system uses intense IR LED strobes on each camera; a simpler version for HIHO would be standalone IR flood lights.

**Why it helps:** MediaPipe's tracking quality depends heavily on good, consistent lighting. In a classroom or studio with variable overhead lights, windows, shadows, and changing conditions, tracking can be unreliable. IR illumination provides a consistent light source that doesn't affect the room's visible appearance. **(General quality improvement)**

**Rough cost:** $30–80 for 2–4 IR flood lights (sold as security camera illuminators). Available on Amazon for $15–40 each.

**Difficulty:** 2 for the lights themselves. BUT: the C922x webcams have an IR-cut filter that blocks most infrared light. So IR illumination won't help with the *current* cameras — it only becomes useful when you switch to cameras that can see IR (or cameras where you can remove the IR filter).

**Dependencies:**
- Cameras without IR-cut filters, OR cameras with removable/switchable IR filters.
- This pairs naturally with the PoE camera migration (Tier 3.1) — many surveillance IP cameras have switchable IR filters (day/night mode).

**Risks/unknowns:**
- **IR-only illumination means grayscale images.** If the cameras switch to IR-only mode, MediaPipe receives grayscale footage. MediaPipe *does* work on grayscale, but it's trained primarily on color images. Accuracy may decrease.
- **Better approach: IR + visible combined.** Use IR illumination to boost overall light levels while keeping some visible light for color data. This gives MediaPipe the best of both worlds. But it requires cameras that pass both visible and IR light (no IR-cut filter), which changes the color balance of the image.
- **Safety.** IR LEDs at 850nm are invisible but can still damage eyes at close range if very powerful. Dennis's 160W peak LED strobes are safe because they pulse for microseconds. Continuous IR flood lights at lower power are safe, but check the specifications.

---

### 3.6 — Global Shutter Cameras

**What it is:** The C922x uses a rolling shutter sensor — it reads the image line by line from top to bottom. This takes about 30ms for a full frame. If the subject moves during that 30ms, the top of the image shows them in one position and the bottom shows them in a slightly different position. This causes wobble, warping, and artifacts — especially during fast movements. Global shutter cameras capture the entire image at once (all pixels exposed simultaneously), eliminating these artifacts.

Dennis's AR0234 sensor is global shutter, which is one reason his system captures clean data at 240fps. For markerless tracking at 30fps, rolling shutter artifacts are usually small. But they DO affect fast movements and contribute to jitter in the landmark positions.

**Why it helps:** Cleaner frame data for MediaPipe, especially during fast movements. Reduces a source of noise that currently contributes to jitter. **(P2)**

**Rough cost:** Global shutter USB cameras: $200–500 each (Basler dart, FLIR Blackfly, or Chinese industrial cameras on AliExpress for $80–150). Global shutter PoE cameras: similar range. For 4 cameras: **$320–2,000**.

**Difficulty:** 3 — The cameras are drop-in replacements if they support standard USB UVC or RTSP. No software changes needed for the basic swap. But selecting the right camera model (resolution, framerate, lens mount, driver compatibility) requires research and testing.

**Dependencies:** None strictly, but pairs well with the PoE migration (Tier 3.1).

**Risks/unknowns:**
- **Cost vs. benefit at 30fps.** Rolling shutter artifacts at 30fps and normal movement speeds are often smaller than MediaPipe's inherent tracking jitter. The improvement might be hard to measure. Global shutter pays off more at higher framerates (Tier 3.3).
- **Sensor quality.** Affordable global shutter sensors tend to have smaller pixels and worse low-light performance than rolling shutter sensors at the same price. The C922x actually has a pretty decent sensor for its price.

---

## TIER 4: LONG-TERM VISION

*If HIHO scales, money and time are available, and we're building for widespread deployment. Think 2028+.*

---

### 4.1 — Purpose-Built HIHO Camera Module

**What it is:** Design a custom camera module specifically optimized for HIHO's markerless mocap use case — inspired by Dennis's approach but built for RGB pose estimation instead of IR marker tracking. Think: a Raspberry Pi Compute Module + a good RGB sensor + a PoE carrier board + a 3D-printed enclosure. One unit does everything: capture, preprocess, timestamp, and stream. Plug in one Ethernet cable and it works.

**Why it helps:** Solves every hardware pain point simultaneously: USB bandwidth (gone — it's Ethernet), cable length (328 feet), synchronization (PTP built in), processing distribution (Pi does preprocessing), and form factor (purpose-built, small, mountable). **(P1, P2, P3, P4, P5 — all of them)**

**Rough cost per unit (DIY):** ~$150–200 (comparable to Dennis's per-camera cost). For 8 cameras: ~$1,200–1,600. This is roughly the same as buying 8 good webcams, but you get a much better-integrated system.

**Difficulty:** 5+ — This is a hardware product design project. Custom PCB design (Dennis used KiCad), firmware development, enclosure design, manufacturing (even small-batch PCB assembly). Dennis is a Google engineer with hardware experience and it took him months. For HIHO, this would likely need a partnership with an electrical engineering program.

**Dependencies:** All of the above tiers proven. A clear understanding of what specs the camera module needs (resolution, framerate, sensor type, processing capability). Dennis's open-source designs as a starting point.

**Risks/unknowns:**
- **Is it worth it vs. buying off-the-shelf PoE cameras?** If affordable PoE cameras with good specs become available (and they keep getting cheaper), a custom module may be over-engineering. The custom module wins on tight integration and cost-at-scale; off-the-shelf wins on availability and zero development time.
- **Scale justification.** Custom hardware only makes sense if HIHO is deployed in many classrooms. For one installation, buy cameras. For 50 installations, custom hardware starts to make sense.
- **Maintenance.** Custom hardware means custom maintenance. If a unit breaks, there's no warranty and no replacement off the shelf. Need to keep spare parts and documentation.

---

### 4.2 — Hybrid Marker + Markerless System

**What it is:** Use markerless tracking for body pose (MediaPipe through RGB cameras — HIHO's current strength) and add optional marker-based tracking for precision applications (hands, fingers, props, face). Two sets of cameras: the RGB cameras for body, and a few IR cameras (Dennis-style or commercial) for marker tracking of specific body parts.

**Why it helps:** Best of both worlds. Body capture stays easy (no markers needed — just stand in frame). But when a student needs precise finger tracking, facial capture, or prop tracking, they can add a few reflective markers and get sub-millimeter precision on those specific parts. **(P3 — offloads hand tracking to markers, which are computationally cheap to process)**

**Rough cost:** The markerless RGB system (already exists). Plus 2–4 IR cameras ($200–400 each for Dennis-style DIY, or $500+ for commercial). Plus reflective markers ($3–5 each, reusable). Plus IR illumination. Total addition: **$500–2,000**.

**Difficulty:** 5 — The cameras are the easy part. The hard part is fusing two different tracking systems into one coherent skeleton. The RGB cameras give MediaPipe-based 3D body pose. The IR cameras give marker-based 3D point positions. Merging these requires: shared calibration (both camera sets in the same coordinate system), a fusion algorithm that combines body landmarks with marker positions, and a pipeline that handles cases where one system has data and the other doesn't.

**Dependencies:** PoE infrastructure (Tier 3.1) for the IR cameras. Dennis's open-source IR processing code. A fusion pipeline (new research).

**Risks/unknowns:**
- **Complexity for students.** The whole point of HIHO is simplicity. Adding an optional marker-based layer adds complexity. Need to design the UX so that markers are truly optional — the system works fine without them, and adding them is a progressive enhancement.
- **Calibration hell.** Calibrating two different camera systems (RGB + IR) to the same coordinate frame is harder than calibrating either one alone. Different sensors see different things (the ChArUco board is visible to RGB cameras but may not be to IR cameras through a bandpass filter).
- **This is a research project.** Nobody has published a practical hybrid marker/markerless consumer system. This is novel enough to be a dissertation chapter on its own.

---

### 4.3 — Performance-Critical Components in Rust

**What it is:** Rewrite the most performance-critical parts of the pipeline in Rust (the language Dennis chose for his entire system). Candidates: the frame capture and timestamp layer, the image preprocessing pipeline, and the 3D triangulation math. Python orchestrates; Rust does the heavy lifting. This is called writing "native extensions" — Rust code that Python can call as if it were a library.

Dennis's custom blob detection is 300× faster than OpenCV. Even for different tasks (markerless preprocessing, triangulation), Rust's zero-overhead abstractions and lack of GIL mean significant speedups over Python.

**Why it helps:** Order-of-magnitude speedup on processing bottlenecks. Makes real-time (or near-real-time) processing feasible. **(P3)**

**Rough cost:** $0 in hardware. But Rust expertise is expensive in human time — either learning Rust or hiring someone who knows it.

**Difficulty:** 5 — Rust is a powerful language but has a steep learning curve. Writing Python-callable Rust extensions (using `PyO3` or `maturin`) adds another layer of complexity. The resulting code is fast and safe, but getting there requires serious engineering.

**Dependencies:** Clear profiling data showing WHERE the bottlenecks are (don't rewrite code that isn't the bottleneck). A Rust developer (or someone willing to learn).

**Risks/unknowns:**
- **Maintenance burden.** A mixed Python + Rust codebase requires contributors who know both languages. For an open-source education project, this limits who can contribute.
- **Might not be necessary.** If GPU-accelerated MediaPipe (Tier 2.4) or distributed processing (Tier 3.4) solve the speed problem, Rust rewrites are unnecessary optimization.
- **Cross-platform Rust builds.** Rust compiles to native code, so you need to build for macOS (ARM + x86), Windows, and Linux separately. CI/CD gets more complex.

---

### 4.4 — Full Distributed Processing Cluster

**What it is:** Instead of one host computer processing everything, use multiple computers working in parallel. Each computer handles a subset of cameras, and a coordinator merges the results. This could be 2–3 Mac Minis (or even student laptops) on a local network, each processing 2–4 camera feeds, with a central machine doing the final triangulation.

Dennis's system is already semi-distributed (each Pi preprocesses its own camera). This takes that idea further for the compute-heavy markerless pipeline.

**Why it helps:** Scales to arbitrarily many cameras without one computer becoming the bottleneck. 16 cameras across 4 computers = 4 cameras per computer, which is exactly what HIHO already handles on one machine. **(P3 — scales processing linearly with hardware)**

**Rough cost:** Depends on what computers you use. If students bring their own laptops: $0 for hardware, just need a network switch and software. If buying dedicated hardware: $600–2,000 for a couple Mac Minis. Network switch: $50–200.

**Difficulty:** 5 — Distributed systems are inherently complex. Clock synchronization across machines, network latency, failure handling (what if one machine crashes mid-capture?), and result merging all need to be solved. This is a research-grade systems engineering problem.

**Dependencies:** PoE camera infrastructure (Tier 3.1), network-based capture pipeline, a coordinator service that assigns cameras to processing nodes and merges results.

**Risks/unknowns:**
- **Overkill for 4 cameras.** Distributed processing makes sense at 8–16+ cameras. For 4 cameras, one decent computer handles it fine (after Tier 2 optimizations).
- **Student laptops are unreliable.** If the cluster includes student machines, any student closing their laptop kills part of the pipeline.
- **Debugging is hard.** When something goes wrong in a distributed system, the bug could be on any of the machines, in the network, or in the coordination logic. This is a known challenge in professional distributed systems.

---

### 4.5 — The Dream Rig (What It All Looks Like Together)

If everything in Tiers 1–4 were implemented and refined, HIHO's "dream system" would look like this:

**Hardware:**
- 8–12 custom HIHO camera modules (RGB, global shutter, PoE, PTP-synced, Pi Compute Module inside each one)
- All connected to a managed PoE+ switch with PTP support
- One host computer (Mac Mini or equivalent) connected to the switch
- Optional: 2–4 IR cameras for precision marker tracking when needed
- IR flood lights for consistent illumination
- Total system cost: ~$2,000–4,000

**Software:**
- Each camera module runs a lightweight pose pre-processor (optimized for its hardware)
- Cameras are PTP-synced to nanosecond accuracy
- Host receives preprocessed landmark data from all cameras
- Rust-accelerated triangulation produces 3D skeleton in near-real-time
- Blender PPParty addon shows live preview of the skeleton while performing
- One-click processing produces a baked animation on any puppet character
- All results save to a curated library that students contribute to

**Setup:**
- Plug in Ethernet cables, turn on the switch, launch Blender
- Wave a calibration board once
- Perform
- Done

**What this gets you:**
- 8–12 synchronized cameras capturing at 120fps+
- Hardware-level nanosecond sync (no jitter)
- Sub-centimeter body tracking, sub-millimeter with optional markers
- Cable runs up to 328 feet (auditorium-scale)
- Processing in seconds, not minutes
- Affordable enough for school deployment ($2,000–4,000 per installation)

**What Dennis proved:** This is technically achievable. His system does most of this today for marker-based tracking. The markerless version needs more compute per camera but the architecture is sound.

---

## Summary Table

| ID | Idea | Tier | Pain Points | Cost | Difficulty | Best For |
|---|---|---|---|---|---|---|
| 1.1 | Per-frame timestamps + alignment | 1 | P2, P5 | $0 | 2 | Immediate jitter reduction |
| 1.2 | Multiprocess MediaPipe | 1 | P3 | $0 | 3 | Faster processing |
| 1.3 | Selective hand tracking | 1 | P3 | $0 | 2 | Quick processing win |
| 1.4 | Low-res hand detection pass | 1 | P3 | $0 | 3 | Faster hand tracking |
| 1.5 | Audio sync pulse | 1 | P2, P5 | $0–10 | 2 | Better sync reference |
| 1.6 | Documentation standard | 1 | General | $0 | 1 | Project sustainability |
| 1.7 | Threading optimization | 1 | P2, P5 | $0 | 2 | Recording stability |
| 2.1 | PoE IP camera pilot | 2 | P1, P4 | $110–250 | 3 | Testing PoE viability |
| 2.2 | Visual sync signal | 2 | P2, P5 | $10–30 | 2 | Reliable sync in noisy rooms |
| 2.3 | Dedicated hand cameras | 2 | P3 | $40–200 | 3 | Better hand data |
| 2.4 | GPU-accelerated pose estimation | 2 | P3 | $0 | 4 | Faster processing on Apple Silicon |
| 2.5 | Smart frame dropping + interpolation | 2 | P2, P5, P6 | $0 | 3 | Robust sync pipeline |
| 3.1 | Full PoE camera migration | 3 | P1, P4 | $700–1,450 | 4 | Eliminates USB entirely |
| 3.2 | PTP camera synchronization | 3 | P2, P5 | $1,350–2,800 | 4 | Hardware-perfect sync |
| 3.3 | 120fps+ capture | 3 | P2 | $200–2,000 | 3 | Fast-motion quality |
| 3.4 | Pi-based edge preprocessing | 3 | P3 | $230–400 | 5 | Distributed processing |
| 3.5 | IR illumination | 3 | General | $30–80 | 2 | Consistent lighting |
| 3.6 | Global shutter cameras | 3 | P2 | $320–2,000 | 3 | Cleaner frame data |
| 4.1 | Custom HIHO camera module | 4 | All | $1,200–1,600 | 5+ | Purpose-built system |
| 4.2 | Hybrid marker + markerless | 4 | P3 | $500–2,000 | 5 | Best of both worlds |
| 4.3 | Rust processing pipeline | 4 | P3 | $0 | 5 | Order-of-magnitude speed |
| 4.4 | Distributed processing cluster | 4 | P3 | $0–2,000 | 5 | Scaling to 16+ cameras |

---

## Recommended Starting Sequence

If David wants to start making progress this summer, here's the order that gives the most impact for the least effort:

1. **1.1 + 1.7** (Per-frame timestamps + threading optimization) — These two changes to the Camera Manager are quick wins that directly improve recording quality. Do them together.

2. **1.3** (Selective hand tracking) — Static version (only track hands on front-facing cameras). Quick config change with immediate processing speed benefit.

3. **1.6** (Documentation standard) — Start adopting Dennis's documentation approach now. This pays dividends for everything that follows.

4. **1.5** (Audio sync pulse) — If timestamp correction alone isn't enough, add the audio pulse as a physical sync reference.

5. **1.2** (Multiprocess MediaPipe) — If processing time is still painful after selective hand tracking, add multiprocess parallelism.

6. **2.1** (PoE camera pilot) — This is the big Fall project. Buy one IP camera, test it, learn the technology. Everything in Tier 3 depends on this going well.

---

## Cross-References

- **Dennis's system deep dive:** `~/Desktop/DR_BAYUS/made-by-dennis-mocap-research.md`
- **HIHO architecture:** `ARCHITECTURE.md` (this folder)
- **Camera Manager design:** `CAMERA_MANAGER_DESIGN.md` (this folder)
- **Known bugs:** `BUGS_AND_BACKLOG.md` (this folder)
- **Dennis's GitHub (open-source designs):** https://github.com/dennisss/dacha/blob/master/pkg/vision/mocap/index.md
- **Dennis's prebuilt camera interest form:** https://docs.google.com/forms/d/e/1FAIpQLSfVKHNcx7DENkEgXrULLhKXdeeola4GosIWPKfqiPD5mJLqxQ/viewform
