# HIHO MOCAP v2.0 — Home-Rolled Server Architecture: Research

**Status:** Skeleton. Open placeholder. To be filled in fall 2026 with SJSU CS students.
**Date created:** 2026-05-23
**Predecessor:** HIHO MOCAP v1.0 (bundled-FreeMoCap-in-Blender-addon, shipping summer 2026)
**Continues from:** [HIHO_MOCAP_v1_PLAN.md § Post-v1.0 roadmap](HIHO_MOCAP_v1_PLAN.md)

---

## Why this doc exists

Per the post-v1.0 roadmap in `HIHO_MOCAP_v1_PLAN.md`, HIHO MOCAP v2.0 refactors away from bundling FreeMoCap as Python wheels inside a Blender addon, toward talking to a separate server over HTTP/websocket. This decouples Blender's Python version from FreeMoCap's forever.

The trigger was discovering on 2026-05-23 that:
- Blender 5.1+ ships Python 3.13.
- FreeMoCap (+ 5 sub-deps + mediapipe 0.10.14) is hard-pinned to Python `<3.13` across 6 repos.
- No public roadmap entry for FreeMoCap supporting 3.13 (confirmed via GitHub issue/PR scan + the FreeMoCap v2 livestream of 2026-05-16).
- FreeMoCap v2 itself is moving to a bundled-Python-installer + HTTP-server architecture — so the "talk to a server" approach is correct strategic direction, not just defensive.

## The pragmatic fallback (READ THIS BEFORE THE RESEARCH)

**The ideal is option B with SJSU CS student labor** (per `HIHO_MOCAP_v1_PLAN.md`). The pragmatic FALLBACK is whichever of B or C gets HIHO students to art-making fastest and cheapest. Don't let perfect block real work. This skeleton exists to enable the ideal, not to mandate it.

## Research questions to answer (open — fill in fall 2026)

### About FreeMoCap's v2 server architecture
- [ ] What exact protocol does FreeMoCap v2 use? (HTTP REST? WebSocket? gRPC?)
- [ ] What does the server expose for camera capture, calibration, processing?
- [ ] Is the protocol stable enough to depend on?
- [ ] What's their license? (likely AGPL-3.0, inherited if we vendor)

### About what we'd build ourselves
- [ ] Camera capture: keep our existing skellycam-bypass code? Or replace?
- [ ] Tracker integration: Mathis-style stitched-MediaPipe (body + hands + face models)? RTMPose? Other?
- [ ] HTTP server framework: FastAPI? Flask? Something lighter?
- [ ] Blender-side client: pure HTTP polling? WebSocket? Bundled JS UI?

### About what we'd reuse from FreeMoCap
- [ ] Multi-camera calibration: keep their implementation?
- [ ] Triangulation: keep theirs (Anipose-based)?
- [ ] Aaron Cherian's tracker evaluation pipeline: useful as a benchmarking harness?

### About SJSU CS student integration
- [ ] What courses could route students to HIHO MOCAP v2 work? (Senior project? Independent study? CS 100W?)
- [ ] What's the supervision model — independent study? Volunteer? Paid (with what budget)?
- [ ] How do we keep the work HIHO-aligned (open source, pedagogy-first, no tech-bro urgency, see [pedagogy-first memory](../../MEMORY/feedback_pedagogy_first_not_ship_mentality.md))?

## Reading list (to compile)

- FreeMoCap source — `SOFTWARE/R&D/freemocap-main/`
- FreeMoCap v2 livestream 2026-05-16 (transcript captured this session — ask Claude to retrieve)
- Aaron Cherian's dissertation (tracker evaluation pipeline)
- Anipose / aniposelib source (triangulation reference)
- OpenCV stereo calibration documentation
- (more to add)

## Architecture sketches (to draw)

To be filled in during fall 2026.

## Open questions

- [ ] Should this become a new HIHO ecosystem tool with its own name, or stay HIHO MOCAP v2.0?
- [ ] Does this absorb Green Room (already-reactivated as standalone), or stay separate?
- [ ] What happens if FreeMoCap v2 ships before we finish research? Re-evaluate scope — possibly drop to option C (thin wrapper).
- [ ] How does this interact with Mathis exiting academia June 30 2026 (governance discontinuity on the FreeMoCap side)?

---

## Sources / cross-references

- [HIHO_MOCAP_v1_PLAN.md](HIHO_MOCAP_v1_PLAN.md) — v1.0 anchor
- [SESSION_HANDOFF_2026-05-23.md](../../SESSION_HANDOFF_2026-05-23.md) — origin context
- `MEMORY/project_hiho_mocap_blender_50_pin.md` — the constraint that motivated this
- `MEMORY/project_hiho_mocap_v2_homerolled_ideal.md` — strategy memory
- `MEMORY/feedback_research_doc_first_pattern.md` — research → design → clean-room (NOT reverse-engineering)
- `MEMORY/feedback_pedagogy_first_not_ship_mentality.md` — discipline frame
- `MEMORY/project_hiho_animation_club.md` — the maintainer body
