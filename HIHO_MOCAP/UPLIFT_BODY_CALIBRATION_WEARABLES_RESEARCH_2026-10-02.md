# WALK-IN CAPTURE RESEARCH: occlusion uplift, the body as the calibrator, and the smallest useful wearable

*2026-10-02, laptop. Blue-sky research, David's ask: three ideas to "go hard" on, with one goal: anyone can do this, in
any room, on the fly, and nothing here may raise the kit's price floor. READ-ONLY pass: nothing was run, installed or
posted. Three web research passes; every source below was opened unless it is marked UNVERIFIED. STATUS: research only.
No design, no code. Each part wants its own design doc before any code. Companion docs:
`GENERATIVE_INFILL_RESEARCH_2026-07-21.md` (what to do when NO camera sees a joint) and
`MULTI_ACTOR_RESEARCH_2026-09-19.md` (who is who across cameras). This doc sits between them.*

## The one-paragraph answer

All three ideas hold up, and they stack into one picture: you walk in, your body calibrates the cameras, a plain color
band says which performer you are, and when furniture or another performer hides a limb, the system bridges it and marks
that it did. The surprise is how much of this needs no trained model. A joint that only ONE camera still sees can be
recovered with geometry and the performer's own bone length. Camera positions can be solved from the skeleton joints the
kit already tracks. Published work supports both, at "good enough" accuracy rather than board accuracy. The trained
"uplift" model (2D skeleton in, 3D pose out) is the backup for harder occlusions, and the only version HIHO can ship is
one trained on the performer's own six-camera takes, because every ready-made one is trained on data HIHO cannot
license. Two earlier hunches are corrected by the evidence: gloves hurt hand tracking, and a printed tag on a wristband
is too small to read.

## Vocabulary

- **Uplift model (also "lifting" model):** a small neural network that takes ONE camera's flat 2D skeleton and guesses the
  3D pose. It infers depth; it does not measure it.
- **Triangulation:** what the kit does today. Two or more cameras see the same joint, and their sight lines cross at the
  joint's real position. That is measurement.
- **Intrinsics / extrinsics:** a camera's lens settings (fixed per camera model) / where the camera sits in the room
  (changes every setup).

## The occlusion ladder: sort every hidden joint by how many cameras still see it

| Cameras that see the joint | What happens | Measured or guessed |
|---|---|---|
| 2 or more | Triangulate, as today | Measured |
| Exactly 1 | **New tier.** Today the joint is lost. Recover it from that one sight line plus the known bone | Constrained (close to measured) |
| Exactly 1, several connected joints gone | Personal uplift model on that one camera's view | Guessed, anchored by the visible body |
| 0 | Gap fill from the July doc: short physics fill, then the personal motion model | Guessed |
| 0, with a motion sensor on the limb | The sensor carries the limb's direction through the gap | Measured by a second instrument |

Where the two cases land: **two dancers** block different cameras at different moments, so on a six-camera ring one
camera often still sees the limb. That is the one-camera tier, and it is where this doc adds something. **Legs under a
table** are usually hidden from every camera. That is the zero-camera tier: the July doc's job, or a low camera's.

### The one-camera tier without any model

One camera knows the DIRECTION to a hidden elbow but not the distance. The performer's upper-arm length, measured from
the shoulder the other cameras still see, supplies the distance. Picture a string of known length tied to the shoulder:
the elbow is where the string, pulled tight, meets the camera's sight line. There are usually two such points, near and
far; the previous frame says which.

- **The soft version already exists in the library under FreeMoCap's calibration.** Anipose's optimizer keeps a
  reprojection term for every camera that sees a point, even a single one, and holds the skeleton with limb-length and
  smoothness terms. Plain triangulation needs two cameras; this optimizer does not.
- **The hard geometric version was not found in any markerless tool.** Pose2Sim skips the joint and interpolates. OpenCap
  describes no single-view recovery. Structural Triangulation (ECCV 2022, Apache-2.0) uses known bone lengths but is
  silent below two views. The idea itself is old (Lee and Chen, 1985; UNVERIFIED, page blocked).
- **Nobody has measured this exact case:** one joint seen in 2D, the rest of the body already known in 3D. That is a gap
  HIHO could fill with its own takes.

### The uplift model, and why it has to be personal

| Model | Size | Code license | Trained on |
|---|---|---|---|
| Martinez 2017 "simple baseline" | 4 to 5 million parameters | MIT | Human3.6M |
| VideoPose3D | 8.5 to 17 million | CC BY-NC (code and weights) | Human3.6M, HumanEva |
| MotionBERT | 42.5 million | Apache-2.0 | AMASS, Human3.6M and others |
| MotionAGFormer | 2.2 to 19 million | Apache-2.0 | Human3.6M, MPI-INF-3DHP |
| PoseMamba (2025) | 0.9 to 6.7 million | Apache-2.0 | Human3.6M, MPI-INF-3DHP |

- **The license wall.** Human3.6M is "limited to academic use only" and may not be transferred. Every ready-made lifter
  above learned from it, whatever its code license says. Same conclusion as the July doc reached for motion models:
  **their designs are lessons; their weights do not go in an AGPL kit.**
- **The rig is the teacher.** Every clean six-camera take already contains the training pairs: each camera's flat
  skeleton, and the triangulated 3D answer. This is published: **LiftPose3D** trained a Martinez-style network on
  triangulated multi-camera poses, then lifted from one camera, and needed between a thousand and ten thousand poses.
  That was lab animals in fixed setups (GPL-3.0 code). A one-minute take at 60 fps holds 3,600 poses, each seen from six
  angles, so the amount is within reach on paper. **Nobody has published the number for one human performer.** Caution:
  neighboring frames are near-copies, so variety of movement matters more than minutes.
- **Training for occlusion makes its own data too.** Hide joints on purpose in clean takes and train the model to put
  them back. The whole-body benchmark does this; error rises by about a fifth when a quarter of the joints are hidden.
  MotionBERT takes per-joint confidence as an input, which is the right shape for us.
- **Body yes, fingers no.** On the 133-point whole-body benchmark, lifted hands are the worst part by far. Uplift is for
  arms and legs.
- **How good.** Generic lifters, guessing a whole skeleton with no other help, are off by a few centimetres per joint on
  their own benchmark and "generalize poorly" under occlusion. Our case is easier (calibrated camera, most of the body
  measured) but unmeasured.

### The catch that comes first: knowing which views to distrust

The 2D tracker never says "I can't see it." It guesses a hidden joint, and with two performers it can pin a hidden wrist
on the other body. Before any recovery tier can run, the kit has to decide which camera views of a joint are real. The
pieces exist or are planned: per-joint confidence, the reprojection outlier rejection already shipped, who-is-who from
the multi-actor doc, and per-performer masks for contact frames.

## The body as the calibrator

**Verdict: supported, at "good enough" accuracy, with scale as the weak link.**

The recipe HIHO would use: lens settings fixed in advance per camera model; the performer does the calibration dance;
the joints tracked across cameras do the board's job; a bundle adjustment (the same kind of solve the board uses) finds
where the cameras sit.

| Work | Setup | Result against a board or reference calibration |
|---|---|---|
| Puwein 2014 | Lens known, 4 to 6 cameras, 200 to 530 frames | Camera position within 7 mm to 58 mm, angle 0.3 to 1.0 degrees |
| Liu 2022 | One person, synced, 4 cameras at 720p, about a minute | Joint reprojection as good as the checkerboard's |
| Pätzold, Bultmann, Behnke 2022 | Lens known, software sync, 20 cameras, people walking 3 minutes | Within 5.3 cm and 0.39 degrees of a tag calibration |
| Kineo 2025 | Lens known, keypoints only | Within 1 cm and 0.20 degrees on a lab dataset; 12 cm when the lens is also estimated |

- **The honest cost,** from the Pätzold paper: checked against a printed tag grid, the body calibration was off by 5.0
  pixels where the tag calibration was off by 1.95. The reason is simple: "left shoulder" is not the same physical spot
  seen from the front and from the side. Papers fight this with confidence thresholds, torso joints, and thousands of
  frames.
- **Scale is the weak link.** Every method is scale-free or assumes a height. One paper measured that body-size scale
  alone leaves about 10 cm of camera error. The working fixes: one measured distance between two cameras (Caliscope), a
  stick of known length, the performer's measured height, or a few seconds of the board. For animation the stakes are
  lower than for science, since a rig retarget absorbs a uniform size error (reasoning, not a measurement).
- **Fixing the lens settings is what makes it work.** Kineo's own numbers: 1 cm with known lens settings, 12 cm without.
  HIHO's fixed-intrinsics idea (one stored lens profile per camera model) is the enabling piece.
- **What ships today.** Caliscope has an experimental markerless calibration (BSD-2, RTMPose, bundle adjustment; its docs
  say accuracy "has not been established"). Pose2Sim lists keypoint calibration as "coming soon." Anipose and EasyMocap
  are board only.
- **Upstream agrees in public.** FreeMoCap issue #764 ("Boardless Multi-Camera Calibration", 2026): the lead developer
  writes that after V2 he hopes to use spatial estimates from body tracks for a good-enough calibration, keeping the
  board for scientific accuracy. No shipped feature or numbers yet. **Ask about their design before building anything.**
- **The big "foundation" models are not the answer.** DUSt3R, MASt3R, VGGT and HSfM recover cameras from plain images,
  but they are non-commercial or mixed-license, need a large graphics card, and land metres off on human scenes where
  keypoint methods land centimetres off.
- **Not found anywhere:** a head-to-head of body calibration against a ChArUco board on 3 to 6 consumer webcams in a
  small room. HIHO has that comparison sitting on disk: every existing take already has a board calibration from the
  same session.

**The shape this suggests:** body for setup-and-go, board for precision, both honest about which one was used. The
calibration dance stops being a ritual around the board and becomes the calibration.

## The smallest useful wearable

Three jobs a wearable could do, cheapest first.

**1. Identity (who is who).** A colored pinnie, band or hat per performer.
- Color is cheap for a camera to read and kinder to student privacy than face or appearance models.
- Printed tags need size. On a 720p webcam at about 3 metres, a readable ArUco or AprilTag needs to be roughly 8 to
  12 cm across plus a white margin. A hat top or chest bib can carry that. **A wristband cannot.**
- No open mocap project was found doing either. Pose2Sim matches people by geometry alone. Sports tracking uses jersey
  color (UNVERIFIED, page blocked).

**2. Helping the weak spots (hands).** The evidence says no, with one exception.
- MIT's color glove (Wang and Popović, SIGGRAPH 2009) was a Lycra glove with 20 patches in 10 colors, about a dollar to
  make. It worked because the whole pipeline was built around that glove.
- Trackers trained on bare hands do worse on gloves: MediaPipe Hands found nothing at all on medical gloves in one
  study; a Meta study measured bare-hand trackers going from about 16 mm error to 19 to 74 mm on sensing gloves.
- No controlled test of RTMPose on gloves exists. So: **a glove only helps if the 2D tracker is trained on that glove,**
  which makes it part of the "train the seeing on your own data" idea, not a quick win.

**3. Carrying a limb through an occlusion (motion sensors).** The one wearable that adds real measurement.
- Use a sensor for the DIRECTION a limb points, never for its position. Position from a sensor alone drifts off by
  metres within a minute. Direction holds for many minutes on good chips. Combine it with the camera-known bone length
  and parent joint (inference from the sources; no paper gives a "seconds of carry" figure).
- A published fusion method works on camera keypoints plus sensor orientations with no restricted body model: Zhang et
  al., CVPR 2020, 4 cameras plus 8 sensors, 24.6 mm error against 29 mm for the previous best, MIT code.
- Cost: SlimeVR trackers are about $40 each retail (new orders ship January 2027) or roughly $80 to $100 for a DIY set of
  eight; the server software is MIT/Apache and exports to other programs. A phone in a pocket can stream its sensors
  over the local network with free apps (SensorServer and phyphox, both GPL-3.0; owoTrack, MIT).
- This stays optional. It is the only item in this doc that costs money.

## Small-data motion models (the "one minute of video" memory)

| Model | Learns from | What it does | Compute | License |
|---|---|---|---|---|
| GANimator (SIGGRAPH 2022) | One short clip | Variations, style transfer, crowds | Hours of training | BSD-2 |
| SinMDM | One clip | In-betweening, extending, crowds | About 1.5 hours on a graphics card | MIT |
| GenMM (SIGGRAPH 2023) | One or a few clips | Variations, partial-body completion, looping | No training; a fraction of a second on an M1 | Apache-2.0, has a Blender add-on |

- These prove that a model of one person's movement from very little data is real. **None of them cleans or repairs
  motion;** they make new variations.
- Two closer relatives of what HIHO wants: a PCA gap fill that learns from the SAME recording, no training data, gaps up
  to 2 seconds within a few millimetres on walking (Gløersen and Federolf 2016; a candidate for the July doc's rung 2);
  and a small network fitted per recording to multi-camera keypoints (Cotton et al. 2023).
- **No paper was found** that trains on minutes of one person's motion and uses it to fill that person's gaps. The July
  doc's open question is still open, and still HIHO's to answer.

## Measured, constrained, guessed: say which, always

The July doc made provenance marking non-negotiable. This doc adds tiers to mark: **measured** (two or more cameras),
**constrained** (one camera plus the bone), **lifted** (uplift model), **infilled** (no camera), **sensor-carried**. One
color each on the baked curves and a line each in the take report. This is the classroom's measuring-versus-making-it-up
lesson made visible, and it is the condition under which a guessed tier is acceptable at all.

## Do not bundle

Pretrained lifting weights (Human3.6M terms); VideoPose3D and EpipolarPose (non-commercial); DUSt3R, MASt3R, VGGT's
original checkpoint (non-commercial); HSfM (depends on SMPL and DUSt3R); CasCalib (no license stated); IMUPoser
(research-only). Usable as code or as templates: Martinez baseline (MIT), LiftPose3D (GPL-3.0), Structural Triangulation
(Apache-2.0), Caliscope (BSD-2), Pose2Sim (BSD-3), Zhang 2020 fusion (MIT), GenMM (Apache-2.0), SlimeVR server
(MIT/Apache-2.0).

## A staged path (each step is a test on data we already have, cheapest first)

1. **What is the one-camera tier worth?** Take a clean six-camera take. For one joint, pretend five cameras went blind
   for a second. Recover it with the bone-and-sight-line geometry and with the Anipose-style soft solve. Compare with
   the real six-camera answer. No model, no new recording. Pass: closer to the truth than the July doc's gap fill on
   the same span.
2. **Body calibration against the board.** Run a keypoint calibration on an existing take and compare the camera
   positions and the resulting skeleton with that session's board calibration. Try each scale source. This is the
   head-to-head nobody has published.
3. **Glove and color, by eye.** Five minutes at the ring: bare hand against a plain glove, and two color bands in the
   two-person Stage 0 footage from the multi-actor doc. Observation only.
4. **Personal uplift model.** Train a small Martinez-style lifter on David's own takes, hide joints, test on a held-out
   take. Gate: it must beat step 1's geometry by a visible margin to earn its complexity, the same rule the July doc set
   for the motion model.
5. **A phone in a pocket.** One sensor, one occluded limb, one take. Last, because it adds hardware.

## Risks and honest unknowns

- Nothing was run. Every accuracy number here comes from someone else's cameras, rooms and bodies.
- The one-camera geometry has a near-or-far ambiguity and leans on the parent joint being right; errors pass down the
  limb. Untested.
- Software-only camera sync is the least-studied part of body calibration. Several methods require synced cameras; one
  works with software sync; some estimate the offset. No paper measures webcam sync jitter's effect.
- One performer in a phone-booth volume gives the solver little spread to work with. The papers say to cover the space
  and stretch the limbs; none studies a small volume.
- A personal uplift model knows the moves it was shown. A move the performer has never recorded gets a worse guess.
- Training any model, even a small one, is heavier than anything the kit does today. It likely belongs on the lab's
  strongest machine, not on a student's old laptop. Running a trained small lifter should be light (inference from
  model size, not tested).
- Student data: a personal model is the student's own data in another form. The opt-in, local-only policy covers it; a
  model file should travel and be deleted with its owner's takes.

## Sources

Occlusion and lifting
- Martinez et al. 2017: https://arxiv.org/pdf/1705.03098 and https://github.com/una-dinosauria/3d-pose-baseline
- VideoPose3D: https://arxiv.org/pdf/1811.11742 (license: https://raw.githubusercontent.com/facebookresearch/VideoPose3D/main/LICENSE)
- MotionBERT: https://github.com/Walter0807/MotionBERT and https://arxiv.org/pdf/2210.06551
- MotionAGFormer: https://github.com/TaatiTeam/MotionAGFormer ; PoseMamba: https://github.com/nankingjing/PoseMamba
- Human3.6M license: http://vision.imar.ro/human3.6m/eula.php
- H3WB whole-body benchmark: https://github.com/wholebody3d/wholebody3d
- Occlusion robustness: https://arxiv.org/abs/2312.06797 ; LInKs: https://arxiv.org/abs/2309.07243
- LiftPose3D: https://pmc.ncbi.nlm.nih.gov/articles/PMC7611544/ and https://github.com/NeLy-EPFL/LiftPose3D
- EpipolarPose: https://arxiv.org/abs/1903.02330 ; TriPose: https://arxiv.org/abs/2105.06599 ; Pavlakos 2017: https://arxiv.org/abs/1704.04793
- Anipose: https://www.biorxiv.org/content/10.1101/2020.05.26.117325v1.full and https://raw.githubusercontent.com/lambdaloop/aniposelib/master/aniposelib/cameras.py
- Structural Triangulation: https://github.com/chzh9311/structural-triangulation
- Pose2Sim: https://github.com/perfanalytics/pose2sim ; OpenCap: https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1011462

Body calibration
- Puwein 2014: https://lucaballan.altervista.org/pdfs/ACCV14.pdf
- Takahashi 2018: https://openaccess.thecvf.com/content_cvpr_2018_workshops/w34/html/Takahashi_Human_Pose_As_CVPR_2018_paper.html
- Liu 2022: https://ietresearch.onlinelibrary.wiley.com/doi/full/10.1049/cvi2.12130
- Xu 2021: https://ar5iv.labs.arxiv.org/html/2104.08568 ; CasCalib: https://arxiv.org/html/2405.06845v1
- Pätzold, Bultmann, Behnke 2022: https://arxiv.org/abs/2209.07393 and https://github.com/AIS-Bonn/ExtrCamCalib_PersonKeypoints
- Lee, Nishino, Nobuhara 2025: https://arxiv.org/html/2502.12546 ; Kineo 2025: https://arxiv.org/abs/2510.24464 (code link dead on 2026-10-02)
- Caliscope markerless calibration: https://mprib.github.io/caliscope/markerless_calibration/
- DUSt3R: https://github.com/naver/dust3r ; MASt3R: https://github.com/naver/mast3r ; VGGT: https://github.com/facebookresearch/vggt ; HSfM: https://github.com/hongsukchoi/HSfM_RELEASE
- FreeMoCap issue #764: https://github.com/freemocap/freemocap/issues/764

Wearables and sensors
- Color glove: https://people.csail.mit.edu/rywang/handtracking/s09-hand-tracking.pdf and https://news.mit.edu/2010/gesture-computing-0520
- Gloves and learned trackers: https://pmc.ncbi.nlm.nih.gov/articles/PMC11435464/ and https://arxiv.org/pdf/2602.05159
- ArUco detector defaults: https://raw.githubusercontent.com/opencv/opencv/4.x/modules/objdetect/include/opencv2/objdetect/aruco_detector.hpp
- AprilTag pixel floor (forum): https://www.chiefdelphi.com/t/pixels-for-apriltag-detection/424609
- Tag sizes at 3 metres are our own estimate: 1280x720, about 70 degrees across, tag facing the camera, no motion blur.
- Video Inertial Poser: https://virtualhumans.mpi-inf.mpg.de/papers/vonmarcardECCV18/vonmarcardECCV18.pdf
- Zhang et al. 2020: https://arxiv.org/pdf/2003.11163 and https://github.com/CHUNYUWANG/imu-human-pose-pytorch
- SlimeVR: https://www.crowdsupply.com/slimevr/slimevr-butterfly-trackers , https://docs.slimevr.dev/diy/components-guide.html , https://github.com/SlimeVR/SlimeVR-Server
- Phone sensors: https://github.com/umer0586/SensorServer , https://github.com/phyphox/phyphox-android , https://github.com/abb128/owoTrackVRSyncMobile
- Sensor drift: https://www.cl.cam.ac.uk/techreports/UCAM-CL-TR-696.html and https://docs.slimevr.dev/diy/imu-comparison.html

Small-data motion models
- GANimator: https://arxiv.org/abs/2205.02625 ; SinMDM: https://arxiv.org/html/2302.05905 ; GenMM: https://arxiv.org/html/2306.00378 and https://github.com/wyysf-98/GenMM
- Gløersen and Federolf 2016: https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0152616
- Cotton et al. 2023: https://arxiv.org/pdf/2303.02413
