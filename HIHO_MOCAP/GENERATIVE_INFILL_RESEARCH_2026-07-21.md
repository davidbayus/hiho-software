# Generative Infill for Mocap Cleanup — Research Doc — 2026-07-21

**What this is.** The research pass (research → design → code) on David's 2026-07-21
question: when a take's noise crosses a threshold — or a body part is simply
hidden (legs behind a table) — can a generative system fill the gap, as "the
ultimate outlier rejection"? Prompted by the SIGGRAPH 2026 poster *SeatSwap*
(Meta Reality Labs, [DOI 10.1145/3799825.3818703](https://dl.acm.org/doi/10.1145/3799825.3818703)),
whose useful lesson is its recipe, not its task: **captured performance is
sacred (a stay-close penalty), physics fixes the violations (contact and
intersection constraints), learning plays only a supporting role.**

**David's directive (2026-07-21): pursue two tracks — physics-first
constraints, and personal-prior training.** This doc scopes both. No code and
no design doc yet; this is the research layer only.

---

## Verdict up front

1. **Rung 2 — constraint-based gap fill — is buildable now**, with zero new
   dependencies, zero third-party licenses, zero training data. It is the
   Cascadeur/SeatSwap idea reduced to what a classroom needs, and it is
   teachable in one sentence: *the computer connects the dots without breaking
   your bones.*
2. **Rung 3 — a personal prior trained on the performer's own takes — is a
   real research thread, not a daydream**, and HIHO is unusually well placed
   for it: because our pipeline lives in MediaPipe 33-landmark space (plain 3D
   joint positions), **the entire SMPL/AMASS licensing swamp that traps every
   off-the-shelf motion prior simply does not apply to us.** We train small,
   from scratch, on data we own.
3. **Bundling any existing pretrained motion prior is rejected** (license
   table below). Their architectures are lessons; their weights are other
   people's motion under other people's terms.

---

## What we already have (why this fits)

- **The trigger signal exists.** Per-joint reprojection error and the
  median-based quality scorer (1.4.26) already say, frame by frame and joint
  by joint, "trust this / don't trust this." Thresholding that produces
  exactly the mask David described. The volume map (1.4.29) shows *where* in
  the room trust decays. Nothing new to invent — the badge machinery becomes
  the mask machinery.
- **The skeleton truth exists.** `enforce_rigid_bodies` already measures every
  bone's median length per take. Those medians are the anatomy constraints a
  filler must respect.
- **The floor exists.** Calibration gives us the ground plane, so "feet don't
  go through the floor" is a constraint we get for free.
- **Offline is fine.** The deliverable is baked animation (capture-and-bake,
  never live), so a filler that takes seconds per take costs nothing real.
- **Surface discipline:** this operates on the **data surface** — the 3D
  landmark npy between triangulation and retarget, the same surface as outlier
  rejection and Butterworth. It is NOT One Euro (live smoothing) and NOT
  Goo/rig-side secondary motion. Keep the three surfaces separate as always.

## The ladder

**Rung 1 (built):** outlier rejection → Bake → Butterworth. Removes lies the
sensors told about things the cameras saw.

**Rung 2 (physics-first constraint fill — the build candidate):** for masked
spans, *solve* for the missing trajectory instead of guessing it:

- **Detect** — mask = frames × joints where confidence collapses (threshold on
  the existing per-joint signals; David turns one dial).
- **Solve** — least-squares optimization over the masked span with four terms,
  all in plain language:
  1. *Meet the edges* — position AND velocity must match the trusted frames on
     both sides of the gap (no pops, no direction snaps).
  2. *Bones keep their length* — the take's own enforced medians.
  3. *Move smoothly* — minimize acceleration change (minimum-jerk), the
     standard model of unhurried human motion.
  4. *Respect the floor* — no foot below the calibrated ground plane.
- **Mark** — every filled frame is flagged as reconstruction (see Provenance).

This is classical numerical optimization (numpy/scipy least squares, CPU,
milliseconds per gap) — the same family as Vicon/OptiTrack marker gap-filling,
[Pose2Sim](https://github.com/perfanalytics/pose2sim)'s
`interp_if_gap_smaller_than`, and OpenSim-world tools like
[MoCapTools](https://github.com/JonathanCamargo/MoCapTools). SeatSwap's
regularization-plus-constraints pattern is this, at Meta scale. Cascadeur's
AutoPhysics is its commercial cousin (closed source; we characterize it from
public docs only, clean-room as always).

**Honest limit:** constraint fills are trustworthy up to roughly 1–2 seconds.
They know anatomy and smoothness but not *habit* — a 10-second occlusion of
walking legs will come back mathematically clean and humanly dead. That
boundary is where rung 3 begins.

**Rung 3 (personal prior — the research frontier):** a small neural network
learns *this performer's* movement style from their own clean takes, then
completes masked spans conditioned on the trusted frames around them
(masked-completion training: hide spans of clean data, learn to restore them).

- **Architecture template:** [SmoothNet](https://github.com/cure-lab/SmoothNet)
  (Apache-2.0) proves the shape — a tiny *temporal-only* network on joint
  trajectories, CPU-capable inference, no body model. We copy the shape, not
  the weights, and train from scratch.
- **Data:** the opt-in local mocap library (per-clip licensing) is exactly the
  training corpus. David alone has 20+ takes on disk today; each student's
  library grows semester-long. **Overfitting to one person is the feature**,
  not the bug — your gaps filled by your habits.
- **The open research question is data efficiency:** how many minutes of one
  performer make a prior that beats rung 2? Nobody publishes this number for
  landmark-space personal training; measuring it is a genuine, dissertation-
  grade experiment (and a paper HIHO could actually write).
- **Evaluation protocol (cheap, honest):** take clean takes, mask spans we
  actually have truth for, fill them with rung 2 and rung 3, measure
  millimeter error + eyeball the motion. **Decision gate: the prior must beat
  the constraint fill by a visible margin to earn its complexity.** If it
  doesn't, rung 2 is the product and the prior stays research.

## License landscape (all verified 2026-07-21)

| Tool | Code license | The catch | Usable how |
|---|---|---|---|
| [HuMoR](https://github.com/davrempe/humor) | MIT | Requires SMPL+H body model (registration-gated MPI license) for ALL uses; trained on AMASS | Read the paper; never bundle |
| [RoHM](https://github.com/sanweiliti/RoHM) (Meta, CVPR 2024) | **CC-BY-NC** (code AND checkpoints) | Non-commercial clause + SMPL-X + AMASS; heavyweight diffusion | Reference only — closest published system to David's exact scenario (occlusion masks → filled motion) |
| [SmoothNet](https://github.com/cure-lab/SmoothNet) | **Apache-2.0** | Their checkpoints carry H36M/AIST++ dataset terms | **Architecture template — train our own weights on our own data** |
| [MDM](https://github.com/GuyTevet/motion-diffusion-model) | MIT (incl. weights per repo) | Trained on HumanML3D (AMASS-derived); GPU; text-conditioned overkill | Read for inpainting technique |
| AMASS dataset | Custom academic | Non-commercial only; no redistribution; explicitly restricts even *models trained on it* for commercial use | **Avoid entirely** |

The pattern: every off-the-shelf prior is (a) welded to the SMPL body-model
family and (b) soaked in AMASS terms. HIHO's landmark-space, own-data path
sidesteps both — and it is the only path coherent with free-forever AGPL
distribution AND with the program's politics (opt-in, local, your data never
leaves — the training-data policy already says this).

## Provenance marking (both rungs, non-negotiable)

Filled frames are reconstruction, not capture. Like a conservator's visible
repair on pottery:

- flag filled spans on the baked fcurves (custom prop) and tint them in the
  viewport;
- write an `INFILL_REPORT.txt` into the take folder (which joints, which
  seconds, which rung) — same honest-output pattern as PROCESS_QUALITY.txt;
- the threshold dial is literally a dial between *documentation* and
  *fabrication* — say so in the classroom. That sentence is also a
  dissertation paragraph waiting to happen.

## What we will NOT do

- Bundle CC-BY-NC or dataset-encumbered weights into an AGPL addon.
- Fit our captures to SMPL bodies just to borrow someone's prior.
- Mine Cascadeur's or anyone's proprietary code (public docs only).
- Send motion to any cloud. Everything here runs on the room's own machines.

## Threads from here (in order)

1. **After Wednesday's live checks:** `GAP_FILL_DESIGN` doc for rung 2
   (detect → solve → mark, panel wording, threshold dial, report format).
   Design first, then one-change builds, per the standing rules.
2. **Late summer experiment:** personal-prior hold-out test on David's own
   take library (the data-efficiency question). SmoothNet-shaped net,
   landmark space, CPU. Success gate as above.
3. **Adoptable-innovations candidate:** a landmark-space gap-filler slots
   cleanly into FreeMoCap's post-processing too — upstream conversation once
   rung 2 is real.
4. **Adjacent reading:** [OpenMoCap](https://github.com/qianchen214/OpenMoCap)
   (ACM MM 2025) for occlusion handling in marker-based systems; EasyMocap for
   multi-view practice.

## Sources

- SeatSwap poster (read in full 2026-07-21): https://dl.acm.org/doi/10.1145/3799825.3818703
- Repo licenses + READMEs fetched 2026-07-21: HuMoR, SmoothNet, RoHM, MDM (links above)
- AMASS license terms fetched 2026-07-21: https://amass.is.tue.mpg.de/license.html
- Pose2Sim gap interpolation: https://github.com/perfanalytics/pose2sim
- Memory anchor: `project_generative_infill_direction.md` (2026-07-21 discussion + this doc)
