"""Build the shippable addon zip — fixed include list, reproducible every time.

Run:  python3 build_zip.py
Output: SOFTWARE/hiho_mocap-<version>.zip  (version read from blender_manifest.toml)

Ships code only. Docs, research notes, vendor/, wheels/, mediapipe_models/, and
take/calibration data never enter the zip. Audit 2026-08-04 flagged the hand-made
zips (stray docs, stale STATUS.md self-misidentifying the install); this list is
the fix.
"""
from pathlib import Path
import re
import zipfile

HERE = Path(__file__).parent
OUT_DIR = HERE.parent

ROOT_FILES = [
    "__init__.py",
    "properties.py",
    "blender_manifest.toml",
    "HIHO_Record.command",
    "HIHO_Camera_Preview.command",
    "LICENSE",
]
PACKAGE_DIRS = ["core", "external", "operators", "panel", "ui", "diagnostics"]
SKIP_NAMES = {"__pycache__", ".DS_Store"}


def is_retired(p):
    """Retired modules stay on disk (never-delete policy) but never ship."""
    if p.suffix != ".py":
        return False
    with open(p, encoding="utf-8", errors="replace") as f:
        return f.readline().startswith("# RETIRED")


def main():
    manifest = (HERE / "blender_manifest.toml").read_text()
    version = re.search(r'^version = "([^"]+)"', manifest, re.M).group(1)
    out = OUT_DIR / f"hiho_mocap-{version}.zip"

    files = []
    for name in ROOT_FILES:
        p = HERE / name
        if p.is_file():
            files.append(p)
    for d in PACKAGE_DIRS:
        for p in sorted((HERE / d).rglob("*")):
            if p.is_file() and not p.suffix == ".pyc" \
                    and not (SKIP_NAMES & set(p.relative_to(HERE).parts)) \
                    and not is_retired(p):
                files.append(p)

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for p in files:
            z.write(p, p.relative_to(HERE))

    print(f"{out.name}: {len(files)} files, {out.stat().st_size // 1024} KB")
    for p in files:
        print(f"  {p.relative_to(HERE)}")


if __name__ == "__main__":
    main()
