# K-12 Blender Addon — Claude Code Project

## What This Is
A Blender Python addon that transforms Blender into bespoke character-creation software for K-12 students. Built as a CADRE Lab collaboration at SJSU, led by David Bayus (Digital Media Art lecturer, 10+ years teaching 3D).

This is **local software** — not "Blender for kids" as a product, but Blender re-crafted for specific kids in specific classrooms with specific constraints.

## Project Lead
David Bayus is NOT a programmer. He's a visual artist and professor who teaches the 3D character pipeline this addon is based on. He'll describe what things should DO and how they should FEEL. You write the code. Ask clarifying questions when behavior is ambiguous — don't guess.

## Design Philosophy (Read This First)
- **Kid Pix is the north star.** A kid should be able to use this without an adult in the room. No dialog boxes. No modal interruptions. No dead ends.
- **One button per operation.** "Clean Up My Shape" not "Voxel Remesh → Quad Remesh → Apply Modifiers."
- **8-12 tools per workspace max.** Radical tool reduction. Constraint enables creativity.
- **Storytelling frames the experience.** Workspaces named for narrative stages ("Build Your World"), not technical operations ("Modeling").
- **Start with something, never nothing.** Pre-loaded scene, not empty viewport.

## The Pipeline This Addon Automates
David teaches an 8-phase character pipeline to college students. The addon compresses it for younger students:

| Phase | College (ART 102) | Addon (K-12) |
|-------|-------------------|--------------|
| 1. Blockout | Manual with primitives | Manual (the learning IS the doing) |
| 2. Voxel Remesh | Manual operator | One button: part of "Clean Up My Shape" |
| 3. Quad Remesh | Exoside Quad Remesher (PAID) | **Our custom free quad remesher** |
| 4. UV Unwrap | Manual seam marking + Unwrap | **Auto-UV on entering paint mode** |
| 5. Multires Sculpt & Bake | Manual multires + bake steps | Automated bake behind the scenes |
| 6. Texture Paint | Manual | Manual (the learning IS the doing) |
| 7. Rig | VHD Skinning + IK setup | Simplified rig presets / auto-rig |
| 8. Export | Manual format selection | One button: "Share My Creation" |

## Critical Technical Challenges
Two steps require building new tools (not just wrapping Blender operators):

### 1. Free Quad Remesher
- See `QUAD_REMESHER_RESEARCH_CONTEXT.md` for full landscape
- Starting point: Fork QRemeshify (based on QuadWild-BiMDF, SIGGRAPH 2021)
- Target: 2,000–5,000 quad faces from ~50K–200K tri input
- Must run on low-end hardware (8GB RAM, integrated GPU)
- Must be 100% free — no paid dependencies

### 2. Automatic UV Unwrapping for Characters
- See `UV_UNWRAP_RESEARCH_CONTEXT.md` for full landscape
- Use Blender's built-in SLIM (Minimum Stretch, available 4.3+) for parameterization
- Build heuristic seam placement: symmetry detection → center-back seam → limb protrusion detection → inner-surface seams
- Kid never sees the UV editor. UVs generate automatically when entering paint mode.

## Target Blender Version
- Blender 4.2+ minimum (matches QRemeshify compatibility)
- Blender 5.0+ preferred (multires baking improvements)

## Project Structure
```
addon/
├── __init__.py              # bl_info, register/unregister
├── operators/
│   ├── cleanup_shape.py     # "Clean Up My Shape" — voxel + quad remesh
│   ├── auto_uv.py           # Automatic UV unwrapping for characters
│   ├── auto_bake.py         # Automated multires normal map bake
│   ├── auto_rig.py          # Simplified rigging presets
│   └── share_creation.py    # One-click export (image/video/glTF)
├── ui/
│   ├── panels.py            # Custom UI panels per workspace
│   ├── workspaces.py        # Workspace definitions (Build → Paint → Move → Shoot → Share)
│   └── startup_scene.py     # Pre-loaded scene on addon activation
├── core/
│   ├── quad_remesh.py       # Quad remeshing engine (QRemeshify fork or custom)
│   ├── seam_generator.py    # Heuristic seam placement for auto-UV
│   ├── symmetry.py          # Mesh symmetry detection
│   └── protrusion.py        # Limb/appendage detection
├── assets/
│   ├── startup.blend         # Pre-loaded scene file
│   └── rig_presets/          # Biped, quadruped rig templates
└── tests/
    ├── test_quad_remesh.py
    ├── test_auto_uv.py
    └── test_seam_generator.py
```

## How to Test
```bash
# Run headless Blender test
blender --background --python tests/test_quad_remesh.py

# Install addon in Blender for manual UI testing
# Edit > Preferences > Add-ons > Install from Disk > select addon/ folder

# Run Python unit tests (logic only, no Blender dependency)
python -m pytest tests/ -v
```

## Code Style
- PEP 8
- Type hints where possible
- Every operator needs a docstring explaining what it does in plain English
- Blender class naming: `KIDBLENDER_OT_cleanup_shape`, `KIDBLENDER_PT_build_panel`
- Prefix all custom properties with `kb_` to avoid namespace collisions

## Dependencies Policy
- **ZERO paid dependencies.** This is non-negotiable.
- Blender's bundled Python + standard library = always OK
- numpy/scipy = OK (bundled with Blender)
- Compiled binaries from open-source projects (QuadWild-BiMDF) = OK if we bundle them
- Any pip-installable pure Python library = OK but document it
- Anything requiring user to install external software = NOT OK for the final addon

## Hardware Target
The addon must run on "Scrap in a Box" hardware — repurposed e-waste machines for low-income K-12 schools:
- ~8GB RAM
- Integrated GPU (no discrete graphics card)
- Linux or Windows
- No internet required after install

## Research Documents (Read These for Context)
- `QUAD_REMESHER_RESEARCH_CONTEXT.md` — Full competitive landscape, algorithms, build strategy for quad remesher
- `UV_UNWRAP_RESEARCH_CONTEXT.md` — Full competitive landscape, algorithms, build strategy for auto-UV
- `../Ed.D. Thesis Research Bot/Addon_Design_Brainstorm_2026-03-30.md` — Design philosophy, pedagogical theory, Kid Pix principles, workspace architecture (if accessible)

## What to Build First (Priority Order)
1. **Addon shell** — bl_info, register/unregister, empty operator stubs, basic panel
2. **"Clean Up My Shape" operator** — wrap QRemeshify or QuadWild-BiMDF with hardcoded defaults
3. **Auto-UV operator** — heuristic seam placement + SLIM unwrap + pack
4. **Paint mode integration** — auto-UV triggers when entering texture paint
5. **One-click bake** — automate the multires normal map bake steps
6. **UI polish** — custom panels, workspace setup, tool reduction
7. **Startup scene** — pre-loaded character/scene on addon activation
8. **Export** — "Share My Creation" one-click output

## Communication Style
David talks like an artist, not an engineer. When explaining what you've built or asking questions:
- Use plain language, not jargon
- Show what changed, not how the code works internally
- "This button now cleans up your mesh in one click" > "Implemented the voxel remesh operator with QuadWild-BiMDF subprocess call"
- If something fails, explain what the user would SEE, not what the stack trace says
