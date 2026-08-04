# Made By Dennis — DIY Optical Motion Capture System
## Deep Dive Research Report for HIHO Mocap Comparison

*Researched June 17, 2026 — based on the video "Building Hollywood Motion Capture from Scratch"*

---

## The Short Version

Dennis Shtatnov built a **16-camera, professional-grade optical motion capture rig from scratch** — custom PCBs, custom software, the whole thing. Each camera costs under $200 to DIY and the system tracks retroreflective markers at 240fps with sub-0.5mm precision. It's genuinely impressive engineering, fully open-source, and got picked up by PC Gamer and Hackaday within days of posting.

**But here's the critical thing for HIHO:** This is a *marker-based* system. It tracks little reflective balls stuck to a person's body using infrared light. HIHO uses *markerless* tracking (MediaPipe sees your body directly through regular cameras). These are fundamentally different approaches that solve different problems, and switching between them has major implications for everything — cost, complexity, and especially classroom deployability.

---

## Who Is Dennis Shtatnov?

**Dennis Shtatnov** is a software engineer based in Sunnyvale, CA. His GitHub bio says "Engineer @ Google" and "Co-Founder @ Lemma" (Lemma is an interactive math education platform he co-created). He studied CS at Drexel University, did computer vision research there, and has a long history of ambitious hardware projects — dancing drone swarms that performed with Parsons Dance Company, custom 3D printers, robotic chalkboards, PX4 drone firmware contributions.

His YouTube channel **Made By Dennis** (@MadeByDennis) focuses on from-scratch builds of complex hardware/software systems. The motion capture video is his most high-profile project — it was published around June 8-10, 2026 and immediately got coverage from Hackaday and PC Gamer. His GitHub monorepo "dacha" (270 stars, written in Rust) contains the full mocap project alongside other libraries and tools.

This guy is not a hobbyist posting weekend projects. He's a professional software engineer with deep hardware chops who happens to love building things from first principles. The level of documentation in his GitHub is remarkable.

**Channel:** https://www.youtube.com/@MadeByDennis
**GitHub:** https://github.com/dennisss/dacha
**Mocap docs:** https://github.com/dennisss/dacha/blob/master/pkg/vision/mocap/index.md

---

## The Hardware: What's Actually In Each Camera

Each camera module is a self-contained unit with its own compute, networking, and lighting. Think of it less like a webcam and more like a tiny networked computer with a camera eye and a ring of invisible flashlights.

### The Sensor

**AR0234 monochrome sensor** — This is the eye of the camera.

- Resolution: 1920 × 1200 at 120fps (that's more pixels than 1080p)
- With 2×2 binning (grouping pixels together for speed): 960 × 600 at 237fps
- Global shutter — captures the entire frame at once, no motion blur or rolling shutter wobble
- Monochrome — no color filter. Since they're only looking for bright IR dots (the markers), color information is wasted. Monochrome means every pixel gets the full light signal, making the markers show up more clearly
- 3.0μm pixel size on a 1/2.6" sensor format

Dennis chose monochrome specifically because pre-made monochrome camera boards are either unavailable or wildly overpriced, which led him to design his own PCB.

### The Lens

Cheap **M12 surveillance camera lenses** (the kind used in security cameras) — specifically a 4.35mm focal length lens with a built-in 850nm infrared bandpass filter. The lens + sensor combo costs about **$40 total** from AliExpress. The bandpass filter is key: it blocks visible light and only lets through near-infrared, so the camera basically can't see anything except the IR light bouncing off the reflective markers.

### The Compute Module

Each camera has its own **Raspberry Pi Compute Module 5** (or CM4) riding on a custom carrier board. The cheapest CM5 option (no WiFi, 2GB RAM, 16GB eMMC) runs about **$45**. The Pi handles:

- Receiving raw camera frames
- Running connected-components analysis to find bright blobs (the markers) in each frame
- Timestamping everything with nanosecond-level precision via PTP (Precision Time Protocol)
- Streaming the extracted marker positions to the host computer over Ethernet

### The Custom PCBs

Dennis designed **three custom circuit boards** because nothing off-the-shelf did what he needed at a reasonable price:

1. **Compute Carrier Board** — Hosts the CM5, provides PoE power extraction, has the camera connector, includes an STM32 microcontroller for trigger synchronization, an accelerometer for vibration monitoring, and RGB status LEDs

2. **LED Ring Board** — A ring of 12 near-IR LEDs (ams-OSRAM SFH 4715AS) around the lens. These pulse at **160 watts peak** — but only during the tiny fraction of a second when the camera is actually taking a frame, so average power stays within PoE limits. The LEDs flood the scene with invisible 850nm infrared light that bounces back off the retroreflective markers

3. **Camera Board** — Custom PCB for the AR0234 sensor with a 4-lane MIPI interface and external trigger input

All PCB designs (KiCad files), 3D-printable enclosure parts, and CNC heatsink designs are on GitHub.

### Synchronization

This is where it gets clever. All 16 cameras need to fire at exactly the same instant (within ~50 nanoseconds of each other). Here's how:

- Every camera connects via **PoE Ethernet** to a network switch
- The Raspberry Pi's Ethernet chip supports **PTP (Precision Time Protocol)** — a networking standard that synchronizes clocks across devices to nanosecond accuracy
- The Pi generates a **Pulse Per Second (PPS)** signal from its PTP-synced clock
- An **STM32 microcontroller** on the carrier board takes that PPS signal and divides it into the actual camera trigger frequency (120Hz or 240Hz), with precisely timed LED strobe pulses offset to ensure the LEDs are fully on before each frame captures

### The Network Architecture

- Each camera → PoE Ethernet cable → **PoE network switch** → Host computer
- No USB anywhere in the system
- Power AND data over a single Ethernet cable per camera
- Standard Cat5e/Cat6 cables, which can run **up to 100 meters** (328 feet)
- A managed PoE+ switch handles power delivery (up to 25.5W per port)

### Estimated Cost Per Camera (DIY)

| Component | Approximate Cost |
|---|---|
| AR0234 sensor + M12 IR lens | ~$40 |
| Raspberry Pi CM5 (cheapest) | ~$45 |
| Custom PCBs (3 boards, small qty) | ~$25-30 |
| PoE components, buck converter, MCU | ~$30-40 |
| LED driver + 12 IR LEDs | ~$20-25 |
| Capacitors, resistors, connectors | ~$10-15 |
| 3D printed enclosure + heatsink | ~$10-15 |
| Fasteners, cables, misc | ~$5-10 |
| **Total per camera** | **~$185-220** |

Dennis mentions **under $200** in the video. Prebuilt units (he's gauging demand via a Google Form) would be **~$300 each** with tariffs factored in.

**For a 16-camera system:** ~$3,000-3,500 in camera hardware + $100-300 for a PoE switch + host computer.

---

## The Software Pipeline

### On Each Camera (Raspberry Pi)

Dennis wrote custom image processing software in **Rust** (not Python, not C++). Each Pi:

1. Captures a raw monochrome frame from the AR0234
2. Runs a custom **connected-components algorithm** to find bright blobs in the image — these are the markers
3. For each blob, calculates the centroid (center point) with sub-pixel accuracy
4. Packages up the blob positions with a precise timestamp
5. Streams this data to the host computer over Ethernet

He claims this custom pipeline is **300× faster than OpenCV** for this specific task. That's plausible because OpenCV is a general-purpose library and his code is hyper-optimized for one thing: finding bright dots in a mostly-dark image.

### On the Host Computer

The host computer receives marker positions from all 16 cameras and:

1. **Camera calibration** — Knows exactly where each camera is in 3D space (position + orientation), figured out through a calibration process
2. **Triangulation** — When multiple cameras see the same marker, their 2D positions can be combined to calculate the marker's 3D position in space. This is the same math used in surveying and GPS
3. **Marker identification** — Figuring out which blob in Camera 1 corresponds to which blob in Camera 7 (this is one of the harder problems)
4. **Skeletal fitting** — Mapping the 3D marker positions onto a body model or rigid body

### What It Does NOT Do

- **No AI/ML pose estimation** — This doesn't use MediaPipe, OpenPose, or any neural network. It's pure geometric triangulation of physical markers
- **No markerless tracking** — You must attach retroreflective markers to whatever you're tracking
- **No built-in skeletal rigging** — It gives you precise 3D point clouds. Getting from there to a Blender skeleton requires additional software

---

## The Markers

Retroreflective spheres (think tiny disco balls for infrared light). Standard sizes:

- 9mm for finger tracking
- 14mm for body points
- 19mm+ for large rigid bodies (like props or drones)

You can buy them from OptiTrack (~$3-5 each) or make them yourself with retroreflective paint (glass microsphere + metallic base coat). Dennis documents both approaches.

Active markers (battery-powered IR LEDs attached to the subject) are also supported for longer-range tracking.

---

## How This Compares to HIHO's Current System

This is where it gets real. Let me lay it out honestly.

### The Fundamental Difference: Markers vs. Markerless

| | HIHO Mocap (Current) | Made By Dennis System |
|---|---|---|
| **Approach** | Markerless (MediaPipe) | Marker-based (retroreflective) |
| **What you track** | Human body detected by AI | Reflective dots you stick on things |
| **Setup per session** | Point cameras, go | Stick 30+ markers on the performer |
| **Can track non-humans** | Limited (MediaPipe is human-specific) | Anything with markers (objects, robots, animals) |
| **Precision** | ~1-2cm typical | <0.5mm claimed |
| **Frame rate** | 30fps (limited by webcams) | 120-240fps |

**This is not an upgrade — it's a completely different system.** HIHO uses AI that "sees" a human body in regular camera footage. Dennis's system sees invisible dots in infrared footage and does geometry to find them in 3D space.

### Hardware Comparison

| | HIHO | Made By Dennis |
|---|---|---|
| **Cameras** | 4× Logitech C922x | 16× custom IR cameras |
| **Camera cost** | $187 each ($748 total) | ~$200 each (~$3,200 for 16) |
| **Connection** | USB 2.0/3.0 | PoE Ethernet |
| **Max cable run** | ~16ft (USB active extension) | 328ft (standard Ethernet) |
| **Power** | USB from computer | PoE from network switch |
| **Bandwidth** | Shared USB bus (macOS ceiling problem) | Dedicated Ethernet per camera |
| **Sync method** | Software timestamp | Hardware PTP (<50ns error) |
| **Host computer** | MacBook | Needs a host computer (any OS with Ethernet) |

### Does It Solve HIHO's Pain Points?

**USB bandwidth ceiling on macOS?** YES — completely eliminated. Each camera has its own Ethernet connection. No USB bus sharing at all. This is the single biggest architectural win. You could run 16 cameras off one computer without any bandwidth issues.

**USB cable length limitations?** YES — Ethernet cables run 100 meters (328 feet) vs USB's ~5 meters (16 feet with active extensions). You could mount cameras across a gym or auditorium.

**FreeMoCap bugs?** NOT DIRECTLY — This system has its own software pipeline and wouldn't use FreeMoCap at all. You'd be trading FreeMoCap's 22 bugs for a brand-new, less-tested codebase with its own unknowns.

**Per-camera cost?** HIGHER — about the same per camera ($187 vs ~$200), but you need 16 cameras instead of 4. Total system cost goes from ~$750 to ~$3,200-4,800.

**Deployable in schools?** THIS IS THE DEAL-BREAKER — see below.

### The Classroom Reality Check

Here's where I need to be honest about trade-offs:

**For HIHO's mission (K-12 and college deployment), this system has serious problems:**

1. **Cost.** A 16-camera marker-based system costs 4-6× what HIHO costs. For a single research installation this is fine. For deployment across classrooms, it's prohibitive.

2. **Marker hassle.** Every capture session requires someone to carefully stick 30+ retroreflective markers on the performer's body in specific positions. In a college class, this eats 15-20 minutes of class time. In a K-12 setting with younger students, it's even harder. HIHO's markerless approach — point cameras, stand in frame, go — is dramatically simpler for classroom use.

3. **Technical complexity.** Each camera is a Raspberry Pi running custom Linux. The setup involves flashing custom OS images, configuring PTP networking, running Rust binaries, and managing a distributed cluster. Dennis's documentation is excellent, but this is orders of magnitude more complex than "plug in 4 webcams and run a Python script."

4. **Soldering and PCB assembly.** The DIY build requires surface-mount soldering (tiny components on custom PCBs). Even the prebuilt option ($300/camera) doesn't exist yet — Dennis is still gauging demand.

5. **Maintenance.** 16 Raspberry Pis + custom electronics = 16× the things that can break. A burned-out LED, a corrupted SD card, a loose connector — any of these takes a camera offline.

6. **Different software ecosystem.** Dennis's pipeline is written in Rust and uses his own custom cluster management system. It doesn't output to FreeMoCap, Anipose, or the ajc27 Blender addon. Getting data into Blender would require building new integration.

---

## What IS Worth Stealing

Even though the full system doesn't fit HIHO's needs, some of Dennis's ideas are genuinely useful:

### 1. PoE Architecture for Future Camera Rigs

If HIHO ever outgrows USB webcams, the PoE Ethernet approach is the right next step. You could potentially use PoE-powered IP cameras (commercially available, not custom-built) with a markerless pipeline. This solves the USB bandwidth ceiling and cable length problems without requiring custom hardware.

### 2. Hardware Synchronization via PTP

HIHO's current software-based timestamp synchronization has inherent jitter. PTP gives you nanosecond-accurate sync. Some commercial IP cameras support PTP natively — this could be explored without building custom hardware.

### 3. The 300× Faster Blob Detection Code

If HIHO ever needs to process camera feeds faster, Dennis's connected-components implementation (open-source in Rust) could be adapted for markerless preprocessing. The algorithmic approach — finding bright regions in dark images efficiently — is relevant beyond marker tracking.

### 4. The Documentation Standard

Dennis's GitHub documentation is a model for how an open-source hardware/software project should be documented. Every component has a datasheet reference, every design decision is explained, alternatives are listed with trade-offs. HIHO could learn from this approach for its own documentation.

---

## Could You Hybrid It?

One thought experiment: what if you used Dennis's camera hardware but ran markerless pose estimation on the host computer instead of marker tracking?

**Probably not practical.** Dennis's cameras are monochrome with IR bandpass filters — they literally cannot see visible light. They're purpose-built for seeing IR markers in a dark scene. Running MediaPipe or any markerless pose estimation requires regular RGB cameras that can see the human body in normal lighting.

You'd have to:
- Swap the lens for one without the IR bandpass filter
- Use a color sensor instead of monochrome
- Handle much higher data rates (full images vs. just blob positions)
- The whole "160W IR LED ring" becomes useless

At that point you've basically built a very expensive network of Raspberry Pi cameras, which might actually be interesting — but it's a different project entirely.

---

## Bottom Line

### For HIHO Specifically

**Don't switch to this system.** The marker-based approach is a mismatch for HIHO's core mission of accessible, easy-to-deploy mocap in educational settings. The cost is 4-6× higher, the setup per session is dramatically slower, and the technical complexity is orders of magnitude greater.

**Do watch this space.** Dennis is solving real problems (sync, bandwidth, cable runs) that HIHO will eventually face at scale. If PoE IP cameras with markerless tracking become viable, the architectural patterns Dennis demonstrates — PoE networking, PTP sync, distributed processing — will be relevant.

**The interest form for prebuilt cameras** is worth filling out just to stay connected: it shows there's a market forming around affordable DIY mocap hardware. Even if you don't buy his cameras, being in that community keeps you plugged into what people are building.

### For David Personally (as an Artist)

If you ever want a precision mocap system for your own art practice — motion-capture-driven animation, interactive installations, performance work — this is *incredible* bang for the buck compared to commercial systems. An OptiTrack system with similar specs costs $30,000+. Dennis's system costs ~$4,000-5,000 fully built and gives you sub-millimeter tracking at 240fps.

But that's a personal studio tool, not a classroom deployment tool. Different animals.

---

## Key Links

- **Video:** https://www.youtube.com/watch?v=kYVqL_DqBis
- **GitHub (full project):** https://github.com/dennisss/dacha/blob/master/pkg/vision/mocap/index.md
- **PCB designs, 3D print files, software:** all in the GitHub monorepo
- **Prebuilt camera interest form:** https://docs.google.com/forms/d/e/1FAIpQLSfVKHNcx7DENkEgXrULLhKXdeeola4GosIWPKfqiPD5mJLqxQ/viewform
- **Dennis's YouTube:** https://www.youtube.com/@MadeByDennis
- **Dennis's GitHub profile:** https://github.com/dennisss
- **Dennis's personal site:** https://dennis.page
- **Hackaday coverage:** https://hackaday.com/2026/06/10/process-4-billion-pixels-per-second-from-16-diy-cameras-for-the-best-v-tubing-rig-ever/
- **PC Gamer coverage:** https://www.pcgamer.com/hardware/streaming/this-diy-motion-capture-rig-features-16-cameras-made-from-scratch-and-is-doing-nothing-to-assuage-my-vtubing-delusions-of-grandeur/
