# Quadre A/B harness

Headless side-by-side testing of Quadre against Exoside Quad Remesher, built 2026-10-02.
Findings and design: `../QUADRE_FLOW_QUALITY_DESIGN_2026-10-02.md`.

Everything writes under `work/` next to these scripts (ignored by git), or `$AB_WORK` if set.
Blender is `/Applications/Blender.app` unless `$BLENDER` is set. Scripts are zsh + Blender's Python;
`montage.py` needs system `python3` with Pillow.

## Set up the inputs once

```
B=/Applications/Blender.app/Contents/MacOS/Blender
mkdir -p work/input work/out work/renders
$B -b <CHIBI_LOWPOLY_BASE.blend> --python prep_input.py -- work     # sculpt + the class retopo
$B -b --python prep_ref.py -- work                                  # 150K reference surface
$B -b "../BUG_REPORTS/ORGANIC TEST2.blend" --python prep_more.py -- work   # bucket + Suzanne
```

## Run

| Script | What it does |
|---|---|
| `suite_op.sh <tag> [src]` | The real operator over the six-case suite, one table with a MEAN row |
| `suite.sh <tag> key=val ...` | An experiment recipe (`exp_quadre.py`) over the same suite |
| `exp.sh <name> key=val ...` | One experiment run |
| `summ.sh <obj> ...` | Metric table for any result OBJs (`REF=` picks the reference) |
| `run_exoside.py` | Exoside 1.4 the way its Blender bridge drives it (needs a licensed install) |
| `run_quadre.py` | Quadre's operator from source |
| `render.py` + `montage.py` | Same-camera wireframe renders with poles marked, stacked into a sheet |
| `gui_test.py` | Student's path: install the zip in a sandboxed Blender window and press the button |
| `field_diag.py`, `worst.py` | How well a flow map follows curvature; where a result strays furthest |

`HEAT=1` on `render.py` colours quads by how far they sit off the form (needs the `.mis.npy`
files `metrics.py` writes next to each OBJ).

`exp_quadre.py` with its defaults reproduces the **0.3.8** operator; `exp_field.py` and
`exp_post.py` are the prototypes that became `quadre/flow.py` and `quadre/relax.py`.

## Reading the table

`poles` irregular vertices · `flow°` loops off the form (0 best, 22.5 random) · `ang°` corner
error · `angBad%` corners over 45 degrees off · `warp°` quad twist · `nbrP95` neighbour size jump ·
`fidV‰` vertices off the sculpt · `fidS‰` sculpt detail lost · `fidMax‰` worst spot.

The engine's patch layout shifts with tiny input changes, so single-case differences under about
one degree of `flow°` are noise. Read the MEAN row.
