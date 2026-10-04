# MULTI-ACTOR RESEARCH: RTMPose and two or more performers in one recording

*2026-09-19, laptop. Pie-in-the-sky research, David's ask: "do some pie in the sky reserach on RTMpose and being able to
track two or more actors in a mocap recording." READ-ONLY pass: nothing was run, installed or posted; the "today"
section is a reading of the FreeMoCap 2.0 alpha.23 source on disk, not an observation. STATUS: research only. No design,
no code. Build 1.5.x comes first; this wants its own design doc before any code.*

## The one-paragraph answer

Two-actor capture is feasible on the six-webcam ring, and closer than it looks. The 2D half is already native, because
RTMPose is "top-down": it finds a box around every person, then runs the pose model once per box. FreeMoCap's own tracker
library (skellytracker) also ships a working one-camera multi-person tracker that FreeMoCap does not call yet. The missing
piece is the cross-camera step: deciding which skeleton in camera A is the same human as which skeleton in camera B. For
two performers and six calibrated cameras that is small, well-understood geometry. It needs no GPU, no training data, and
no sync hardware beyond what triangulation already tolerates.

How far away (estimates):
- **Performers who stay apart:** a few weeks of eval-kit work.
- **Performers who cross:** a couple of months, part time.
- **Hugging and fighting:** unsolved everywhere. The best lab dataset needed more than 20 synchronized cameras plus masks.
- **Speed:** a second performer roughly doubles tracking time. A 30 second take goes from about 3 minutes to about 6,
  provided the person detector keeps running only occasionally.

## What happens today with two people in frame (from the source, not from a run)

1. **One box survives, chosen by highest confidence score.** Not the largest box, not the box nearest the previous one.
   `yolox_person_detector.py` lines 77 to 79 set `score_threshold = 0.7` and `max_detections = 1` (sort and cut at lines
   143 to 145 and 169 to 172). The stage then takes `bboxes[0]` (`detection_stage.py` line 132; batch path line 499).
2. **The detector runs rarely.** `redetect_interval = round(5.0 * video_fps)` (`mocap_task_config.py` line 165;
   `tracker_factory.py` line 120). At 60 fps the detector fires every 300 frames = 5 seconds. In between, the crop follows
   the previous frame's keypoints (`bbox_policy.py` lines 161 to 237), so it is sticky. An early re-detect fires when fewer
   than half the keypoints sit inside the box (`mocap_task_config.py` line 180; `bbox_policy.py` lines 39 to 52).
3. **So it can flip between people.** Every 5 second re-detect is a fresh "most confident person wins" lottery, and any
   failed box check triggers the same lottery early. During a crossing the one-person pose model sees two bodies in one
   crop and the box can drift onto the other performer. Nothing checks identity.
4. **Each camera decides alone.** One tracker per video (`video_node.py` lines 114, 115, 631); no code compares cameras.
   Camera A can follow performer 1 while camera D follows performer 2.
5. **Triangulation then blends two humans.** Outlier rejection may drop at most 2 cameras per point
   (`default_triangulation_values.py`; `outlier_rejection.py` lines 24 to 127). A 4-against-2 split gets rescued and the
   majority performer wins. A 3-against-3 split cannot be rescued: the skeleton lands between the bodies or teleports.
6. **CLASSROOM RISK WITH ONE PERFORMER: a bystander can steal a camera.** A classmate visible to one camera can win the
   confidence lottery. Worth a Stage 0 observation before the next student demo.

**Multi-person hooks already upstream** (skellytracker commit cb739aa, AGPL, arrived with the July 2026 alpha merge):
- `multi_person_tracker.py` line 24: a multi-person tracker for a SINGLE camera. Runs the detector every frame and the
  pose model once per box; assigns IDs by Hungarian matching on box overlap plus keypoint distance
  (`track_association.py` lines 126 to 171); defaults `max_age = 10`, `min_hits = 3` (`multi_person_config.py` 29 to 33).
- `examples/run_multiperson_on_video.py` is a ready example script. `data_store.py` lines 56 to 85 is a per-person saver.
- `precomputed_object_detector.py` accepts boxes supplied from outside (not registered for config use).

**Gaps in those hooks:** IDs are per camera, nothing is cross-view; saved arrays drop their frame numbers; a person
hidden longer than 10 frames (a sixth of a second at 60 fps) returns with a new ID; the crossing test keeps its boxes
non-overlapping (`tests/test_multi_person_tracker.py` lines 168 to 171); FreeMoCap 2.0a23 imports none of this.

Paths: skellytracker files sit under
`HIHO_ALL/RTMPOSE_EVAL/LOCAL.nosync/freemocap-2.0a23/.venv/lib/python3.12/site-packages/skellytracker/`
(`core/detectors/object_detectors/yolox/`, `core/tracker/`, `core/temporal_processing/`, `core/data_primitives/`,
`core/sessions/ort_session_utils.py`, `examples/`, `tests/`); FreeMoCap files under `.../freemocap-2.0a23/freemocap/`
(`core/tasks/mocap/mocap_task_config.py`, `core/tracking/tracker_factory.py`, `core/pipeline/posthoc/video_node.py`,
`core/tasks/triangulation/helpers/`).

## The options

| Approach | How it works | Needs | License | Maturity | Fit for the ring | HIHO effort |
|---|---|---|---|---|---|---|
| Upstream skellytracker MultiPersonTracker | Finds everyone in ONE camera's video, keeps per-camera IDs | CPU ok, no training | AGPL-3.0 | New, unused by FreeMoCap | Good foundation, half a solution | Small |
| Pose2Sim personAssociation (closest cousin) | Casts a 3D ray per keypoint per camera; two detections are the same person when their rays pass within 10 cm; a consistency solver (matchSVT) cleans the pairings; IDs over time from nearest 3D position (1.0 m max jump, 100 unseen frames) | CPU, no training, calibrated cameras, software sync by motion correlation | BSD-3 | Active, RTMPose via rtmlib | Good | Medium: borrow the math, skip the OpenSim toolchain |
| RapidPoseTriangulation (2025) | Pairs 2D poses across camera pairs, triangulates core joints, keeps pairs with low reprojection error, clusters in 3D, merges | CPU ok, no training; paper advises 5+ cameras | LGPL-3.0 | Research code, C++ and Docker | Good recipe, awkward code for student machines | Medium |
| Chen et al. 2020 cross-view tracking | Matches each new 2D skeleton to last frame's 3D tracks projected into that camera | CPU, no training | Code withheld | Idea only | Good idea | Medium |
| mvpose (Dong et al. 2019) | Appearance re-ID blended with epipolar distance, cycle consistency | GPU, assumes sync | Apache-2.0 | Dormant | Maybe | Large |
| 4D Association (2020) | One graph links limbs across views and time (OpenPose part fields) | C++ on Windows | None stated = all rights reserved | Dormant | Poor | n/a |
| VoxelPose, Faster VoxelPose, MvP | A neural net reads a 3D voxel grid of the room | GPU, trained per camera layout | MIT, MIT, Apache-2.0 | Research | Poor | Large |
| EasyMocap | YOLO, 2D pose, epipolar matching, 3D tracking, SMPL body fit | GPU, SMPL | Custom registration license + SMPL terms | Active | Poor (license) | n/a |
| SAM 2 or EdgeTAM masks, pipeline run twice (David's May idea) | Paint one performer out with the empty-room plate, run the one-person pipeline once per actor | Heavy compute, clicks, fixed cameras | Apache-2.0 | Mature models | Maybe for whole takes, good for contact frames | Small to medium |
| OpenCap | Keeps only the biggest person | n/a | n/a | n/a | Not applicable | n/a |

**Pose2Sim's limits:** association is per frame, no memory; two thresholds need tuning (too loose = wrong pairings, too
tight = lost people); when one person matches several in another view only the first match is kept; its sync step wants a
clear vertical movement and at least 5 seconds of footage.

**Plain analogies.** Ray matching: every camera sighting is a laser line from that camera into the room; two sightings
are the same head only if their lines nearly touch. Hungarian matching: a seating-chart solver that finds the one-to-one
pairing with the smallest total cost. Cycle consistency: if A matches B and B matches C, then A must match C.

**2D cost (all estimates).** One RTMW-l crop costs 7.9 GFLOPs; one YOLOX-m pass costs 73.8, about nine crops' worth.
The M4 laptop measures about 50 frames per second across six cameras today (CoreML, one person, sparse detection). CoreML
must run batch size 1 (`ort_session_utils.py` lines 544 to 551), so each extra person is a full extra call: about 2x the
pose work. The expensive part is the DETECTOR: the upstream multi-person tracker runs YOLOX-m on every frame, about 11x
today's model work; our own 08-29 test with per-frame detection ran 2.5 fps. Detecting every 10th frame (as rtmlib does)
or using YOLOX-tiny (already listed in skellytracker) brings that to about 3x. No published Apple silicon RTMW benchmark
was found.

**Identity over time.** Per-camera 2D trackers (ByteTrack, OC-SORT, BoT-SORT: MIT; Roboflow trackers: Apache-2.0) give
IDs inside one view only and swap when boxes overlap. Tracking in 3D after association is sturdier: a crossing that
overlaps in camera A does not overlap in camera D, and two bodies never share 3D space. Cheap identity cues: bone lengths
as a fingerprint (weak per frame because segment lengths wobble 5 to 10 percent, fine as a median over a second, easy for
adult versus teen); costume color (kinder to student privacy than appearance models). What breaks: crossing = 3D tracking
survives; hug or fight = the 2D pose model mixes limbs, so expect dirty limbs rather than lost identity; exit and return =
new ID unless fingerprint, color, or "the one not currently tracked" restores it.

**The SAM 2 idea, fairly.** Its core move (turn one two-person take into two one-person takes, then run the trusted
pipeline twice) is where every option converges, and masks are what the contact research uses. What changed since May: the
pipeline now crops to a box, so when performers are apart a box per actor does the plate's job at almost no cost. Masks
earn their cost only in frames where the boxes overlap. Whole-take cost: a 30 second take is 10,800 frames across six
cameras plus 12 clicks; SAM 2 documents only A100 speeds; EdgeTAM claims 16 fps on an iPhone (if a MacBook matched that,
about 11 minutes of masking; unverified).

## A staged path for HIHO

**Stage 0. See today's failure (one afternoon, no code).** Shoot 30 seconds with two people on opposite halves of the
room, process as usual. In the six annotated videos, note which person each camera follows and whether any camera switches
at the 5 second marks. Pass or fail is not the point: this turns the code reading into an observation.

**Stage 1. Never crossing (a few weeks, eval kit only, research doc first).** Run the upstream multi-person tracker per
camera. Label the tracks once per take by brute force: with 2 people and 6 cameras there are only 32 possible labelings;
try them all, keep the one with the lowest reprojection error (Pose2Sim's single-person trick, widened). Feed each actor's
2D data to the unchanged triangulator, filter, shim and loader. Test: mirrored slow movement, 30 seconds. Pass: two rigs,
zero label swaps, hands on the right bodies, jitter within about 20 percent of a solo take from the same session.

**Stage 2. Crossing (a couple of months, part time).** For each frame, project last frame's two 3D skeletons into every
camera; pair detections to them with the seating-chart solver using SLOW joints only (hips, shoulders, neck); gate at
10 cm; fall back to ray matching when a track is lost. Why slow joints: one frame of timing skew at 60 fps is 16.7 ms; a
brisk walker's torso moves about 2.5 cm in that time, a fast hand about 8 cm, against the 10 cm gate. Test: swap sides 5
times at a walk, then once at a jog, with one tall and one short performer so a swap shows up as a sudden leg-length jump.
Pass: A is still A after every swap, no hip gap longer than 10 frames.

**Stage 3. Contact (open research).** Handshake, hug, slow stage fight. Masks (EdgeTAM or SAM 2) only on frames where the
two boxes overlap; mark the dirty limb spans and hand them to the planned gap fill. Pass: identity never swaps, limb
dropouts under 1 second. A documented fail is publishable too.

**Stage 4. Two rigs in Blender.** Each actor lands as an ordinary one-person recording folder with the same four files the
shim writes today, so the loader and bake run unchanged, once per actor. A sidecar ties both folders to one take, one
calibration, one clock. Both rigs must share ONE floor and origin alignment: aligned separately, the performers lose their
true spacing and handshakes will not meet. Stable A and B labels come from a start ritual (A begins on the mark nearest
camera A, no props), with a one-click fix in the panel and the bone fingerprint as checks.

## Upstream status (public pages only)

FreeMoCap's FAQ says multi-person tracking is being worked on, no date. Issue #597 has been open since May 2024 with no
description. A community PR for two-performer support (#873) was opened and closed unmerged by its own author within a
day in August 2026. So: ask about their design before building anything. (Questions for the 09-25 meeting are kept with
the meeting prep notes, outside this repo.)

## Risks and honest unknowns

- Nothing was run. The "today" section is code reading at alpha.23; alpha.24 (09-16) was not diffed; its notes do not
  mention multi-person.
- Speeds are estimates from FLOP counts plus two of our own measurements. FLOPs are not CoreML latency.
- Unsynchronized cameras are untested for association. Torso joints should tolerate one frame of skew; fast limbs in a
  fight will reject more cameras.
- Contact is unsolved everywhere. Plan for cleanup, not prevention.
- The ceiling ring probably helps (steep views overlap two people less). Reasoning, not a measurement.
- Old classroom machines face double an already long CPU wait.
- Do not bundle EasyMocap, 4D Association, or anything tied to SMPL. Everything recommended here is Apache-2.0, MIT, BSD-3,
  LGPL-3.0 or AGPL.
- Minors: two-performer takes double the footage of students. The same opt-in, local-only policy applies.

## Sources

FreeMoCap: docs.freemocap.org FAQ; github.com/freemocap/freemocap issues #597, #34, PR #873, milestones, releases;
docs.freemocap.org tracking-integration architecture page; github.com/freemocap/skellytracker (history of
`skellytracker/core/tracker/multi_person_tracker.py`).
Pose2Sim: github.com/perfanalytics/pose2sim (`Pose2Sim/personAssociation.py`, `Demo_MultiPerson/Config.toml`).
RTMPose and detection: arxiv.org/abs/2303.07399; github.com/open-mmlab/mmpose (projects/rtmpose); github.com/Tau-J/rtmlib;
github.com/Megvii-BaseDetection/YOLOX.
Cross-view methods: arxiv.org/abs/2503.21692 and gitlab.com/Percipiote/RapidPoseTriangulation; arxiv.org/abs/2003.03972
and github.com/longcw/crossview_3d_pose_tracking; github.com/zju3dv/mvpose; github.com/zhangyux15/4d_association;
github.com/microsoft/voxelpose-pytorch; github.com/AlvinYH/Faster-VoxelPose; github.com/openxrlab/xrmocap;
chingswy.github.io/easymocap-public-doc (multi-person page); github.com/zju3dv/EasyMocap LICENSE.
Close contact datasets: arxiv.org/abs/2410.20294 (Harmony4D); arxiv.org/abs/2506.13040 (MAMMA).
Trackers and masks: github.com/FoundationVision/ByteTrack; github.com/noahcao/OC_SORT; github.com/NirAharon/BoT-SORT;
github.com/roboflow/trackers; github.com/facebookresearch/sam2; github.com/facebookresearch/EdgeTAM.
OpenCap: simtk.org forum thread t=17752; mobilize.stanford.edu OpenCap Q&A (2022).

Related HIHO notes: `SUPERVISION_RESEARCH.md`, memory `project_two_person_sam2_preprocessing`,
`project_supervision_bytetrack`, `project_hiho_research_agenda_2026_27`.
