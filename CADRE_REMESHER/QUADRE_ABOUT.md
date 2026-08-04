# QUADRE — Free Quad Remeshing for Everyone

## What Is QUADRE?

QUADRE is a free, open-source Blender addon that turns messy 3D shapes into clean, animation-ready quad meshes — with one button.

Select your sculpt. Hit "Clean Up My Shape." Done.

It was built for students learning the character creation pipeline, but it works for anyone who needs clean topology without paying for commercial tools.

## Why It Exists

### The Problem

The standard character creation pipeline in 3D looks like this:

**Blockout → Sculpt → Voxel Remesh → QUAD REMESH → UV Unwrap → Texture Paint → Rig → Animate**

Every step in that pipeline is free — except one. Quad remeshing (the step that turns messy triangle soup into clean, orderly quads) has been locked behind paid software. The industry standard, Exoside Quad Remesher, costs $60. Blender's built-in option (QuadriFlow) isn't reliable enough for character work.

For a university course or a professional studio, $60 isn't a barrier. But for a K-12 classroom? A community workshop? A kid on a hand-me-down laptop? That $60 is the difference between a complete pipeline and a broken one.

QUADRE closes that gap.

### The Zero-Cost Pipeline

With QUADRE, the full character pipeline is 100% free:

| Step | Tool | Cost |
|------|------|------|
| Modeling | Blender | Free |
| Sculpting | Blender | Free |
| Voxel Remesh | Blender (built-in) | Free |
| **Quad Remesh** | **QUADRE** | **Free** |
| UV Unwrap | Blender | Free |
| Texture Paint | Blender | Free |
| Rigging | Blender + Mixamo | Free |
| Animation | Blender + Mixamo | Free |

No subscriptions. No trial periods. No "free for non-commercial use" asterisks. Free means free.

## How It Works

### Under the Hood: QuadWild

QUADRE wraps **QuadWild-BiMDF**, a quad remeshing algorithm developed by academic researchers and published at SIGGRAPH 2021 — the most prestigious computer graphics conference in the world.

The paper: *"Reliable Feature-Line Driven Quad-Remeshing"* by Nico Pietroni et al.

Here's what that algorithm actually does, in plain English:

1. **Reads the shape of your mesh.** It detects sharp edges, creases, and surface curvature — the features that define what your shape IS.

2. **Computes a "cross field."** Imagine drawing a tiny + sign on every point of your surface, showing which direction the quads should flow. The algorithm figures out the best orientation for those + signs across the entire surface at once.

3. **Lays down a grid.** Using that cross field as a guide, it maps a 2D grid onto your 3D surface. Where the grid lines cross become vertices. The spaces between become quads.

4. **Cleans up.** It smooths the result, removes tiny degenerate faces, and produces a final mesh that's ready for the next step in the pipeline.

The "BiMDF" part refers to a specific math solver (Bi-directional Minimum Deviation Flow) that replaced an expensive commercial dependency in the original algorithm, making the whole thing free to use.

### What QUADRE Adds

QuadWild is a powerful engine, but it exposes 30+ parameters that require deep technical knowledge to tune. QUADRE wraps it with:

- **One button.** "Clean Up My Shape" — that's it.
- **One slider.** Detail level, from low poly to high detail.
- **Smart defaults.** Sharp feature detection, smoothing, and density tuned for character meshes.
- **Auto-decimation.** If your mesh is too dense (over 100K triangles), QUADRE simplifies it first so you're not waiting forever.
- **Symmetry support.** Toggle X or Y axis symmetry for characters.

A student doesn't need to know what a cross field is. They press the button, move the slider, and get clean quads.

## Copyleft and Why It Matters

### What Is Copyleft?

QUADRE is released under the **GPL-3.0 license** — the same license as Blender itself. This is a "copyleft" license, which means:

- **Anyone can use it.** For any purpose — personal, educational, commercial.
- **Anyone can modify it.** You can change the code, add features, fix bugs.
- **Anyone can share it.** You can give copies to students, colleagues, anyone.
- **Modifications must stay open.** If you improve QUADRE and distribute your version, your improvements must also be GPL-3.0. The freedom is preserved.

This is different from "freeware" (free to use but you can't see or change the code) and different from "open source" licenses like MIT (which allow someone to take the code, modify it, and sell it as closed-source software).

Copyleft means QUADRE can never be locked behind a paywall. Not by us, not by anyone.

### The Software Stack

Every piece of software that QUADRE depends on is free and open:

| Component | What It Does | License |
|-----------|-------------|---------|
| **Blender** | 3D creation suite | GPL-2+ |
| **QuadWild-BiMDF** | Quad remeshing algorithm | GPL-3.0 |
| **QRemeshify** | Blender integration of QuadWild | GPL-3.0 |
| **QUADRE** | One-button wrapper for students | GPL-3.0 |

GPL all the way down. No proprietary dependencies. No paid libraries hidden in the stack. If any of these projects disappeared tomorrow, anyone could pick up the source code and keep going.

### Why Not Just Use the Free Version of [Commercial Tool]?

Many commercial tools offer free tiers, educational discounts, or non-commercial licenses. These are generous, but they come with strings:

- **Educational licenses expire.** The student graduates, the license disappears, and the skills they built around that tool become inaccessible.
- **"Free for non-commercial" changes.** Companies get acquired, change pricing, or redefine "non-commercial." What's free today may not be free next year.
- **Dependency is the product.** Free tiers exist to create dependency. The goal is conversion to paid, not empowerment.

Copyleft software doesn't have these failure modes. It's free because of how it's licensed, not because of a business decision that could change.

## Who Built This

**QUADRE** was built by **David Bayus** at the **CADRE Lab, San Jose State University**, with engineering assistance from Claude (Anthropic's AI).

David is a Digital Media Art lecturer who teaches the character creation pipeline this tool supports. He is not a programmer — he's a visual artist and educator who designed the tool around how students actually work.

The project is part of a broader initiative to build **local software** — tools made with care for specific people in specific classrooms with specific constraints. Not "Blender for kids" as a product, but Blender re-crafted for kids who need it.

### Credits and Acknowledgments

- **QuadWild-BiMDF** — Nico Pietroni, Stefano Nuvoli, Thomas Alderighi, Paolo Cignoni, Marco Tarini (SIGGRAPH 2021)
- **QRemeshify** — ksami (GitHub: ksami/QRemeshify) — the Blender addon that first wrapped QuadWild
- **Blender Foundation** — for making the best 3D software in the world and keeping it free
- **CADRE Lab, SJSU** — for supporting this work
- **Claude (Anthropic)** — AI engineering assistance

## Technical Details

- **Blender version:** 4.2+
- **Platforms:** macOS (ARM), Windows (x64), Linux (x64)
- **License:** GPL-3.0-or-later
- **Size:** ~5.5 MB (includes pre-compiled QuadWild binaries)
- **Dependencies:** None beyond Blender itself
- **Internet required:** No

## Links

- QuadWild-BiMDF paper: *"Reliable Feature-Line Driven Quad-Remeshing"* (SIGGRAPH 2021, DOI: 10.1145/3450626.3459941)
- QuadWild-BiMDF source: github.com/cgg-bern/quadwild-bimdf
- QRemeshify: github.com/ksami/QRemeshify
- Blender: blender.org
