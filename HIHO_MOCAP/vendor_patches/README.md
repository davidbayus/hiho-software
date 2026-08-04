# vendor_patches/

Compatibility patches we apply to the bundled `vendor/ajc27_freemocap_blender_addon/` and `vendor/freemocap/`.

## Why this exists

ajc27 and FreeMoCap upstream sometimes ship code that needs a small adjustment for HIHO MOCAP's pinned Blender 5.0 / Python 3.11.13 environment, or for our bundled-vendored layout. We carry those patches here rather than forking the upstream repos, so the vendored copies stay close to upstream and the diffs are visible.

## How to add a patch

1. Make the minimal edit directly in `vendor/<addon>/<file>` so the bundled copy works.
2. Drop a small `.md` next to this README, named `YYYY-MM-DD_<short-slug>.md`, with:
   - Which file was patched (path inside `vendor/`).
   - What the patch does (one paragraph, plain language).
   - Why upstream's version doesn't work for us (the failure mode, the error message, the version we tested against).
   - When/whether to upstream the fix (link to an upstream issue if filed).

## Existing patches

- `2026-05-xx_path_getters_local_appdata.md` — vendored FreeMoCap `path_getters.py` patch. See `MEMORY/project_hiho_mocap_vendored_freemocap_patch.md` for the recipe and rationale. (To be migrated into this directory from its current loose location during v1.2 scaffolding.)
