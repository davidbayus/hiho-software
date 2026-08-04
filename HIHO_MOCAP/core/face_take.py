"""Live Link Face take parsing + shape-key application.

Reads the CSV a Live Link Face take records on the phone (also the format
DeadFace writes on the 100%-open path — same seam, so the capture device can
swap later at zero downstream cost) and writes it as a shape-key action on a
face mesh. Format verified against a real v1.7.2 take on 2026-07-20
(FACE_CAPTURE_DESIGN_2026-07-20):

    Timecode, BlendshapeCount, <52 shapes>, <9 head/eye rotation channels>

Timecode is HH:MM:SS:FF.frac where FF.frac counts FRAMES at the capture
rate (confirmed to the digit against the take's nanosecond frame log).
Channels match by NAME, case-insensitive — the app's column order disagrees
with Apple's docs in places, and one app-era bug shipped garbled header
names, so a positional fallback against the observed v1.7.2 order exists
behind a loud warning. Head/eye rotations are parsed but not applied (the
body rig owns the head); the CSV path is stored on the action for a future
pass. No silent failure: everything skipped or assumed is reported.
"""

import csv
import json
import os
import re

import bpy

# The 61 channels in the exact column order of the verified v1.7.2 take.
# Used ONLY as the positional fallback when header names are unrecognizable.
LLF_COLUMN_ORDER = (
    "EyeBlinkLeft", "EyeLookDownLeft", "EyeLookInLeft", "EyeLookOutLeft",
    "EyeLookUpLeft", "EyeSquintLeft", "EyeWideLeft",
    "EyeBlinkRight", "EyeLookDownRight", "EyeLookInRight", "EyeLookOutRight",
    "EyeLookUpRight", "EyeSquintRight", "EyeWideRight",
    "JawForward", "JawRight", "JawLeft", "JawOpen",
    "MouthClose", "MouthFunnel", "MouthPucker", "MouthRight", "MouthLeft",
    "MouthSmileLeft", "MouthSmileRight", "MouthFrownLeft", "MouthFrownRight",
    "MouthDimpleLeft", "MouthDimpleRight", "MouthStretchLeft",
    "MouthStretchRight", "MouthRollLower", "MouthRollUpper",
    "MouthShrugLower", "MouthShrugUpper", "MouthPressLeft", "MouthPressRight",
    "MouthLowerDownLeft", "MouthLowerDownRight", "MouthUpperUpLeft",
    "MouthUpperUpRight",
    "BrowDownLeft", "BrowDownRight", "BrowInnerUp", "BrowOuterUpLeft",
    "BrowOuterUpRight",
    "CheekPuff", "CheekSquintLeft", "CheekSquintRight",
    "NoseSneerLeft", "NoseSneerRight", "TongueOut",
    "HeadYaw", "HeadPitch", "HeadRoll",
    "LeftEyeYaw", "LeftEyePitch", "LeftEyeRoll",
    "RightEyeYaw", "RightEyePitch", "RightEyeRoll",
)

_ROTATION_NAMES = {name.lower() for name in LLF_COLUMN_ORDER[52:]}
_KNOWN_NAMES = {name.lower() for name in LLF_COLUMN_ORDER}
_TIMECODE_RE = re.compile(r"^(\d+):(\d+):(\d+):(\d+)(?:\.(\d+))?$")


class FaceTakeError(ValueError):
    """Parse failure with a message written for the panel, not a log."""


def parse_llf_csv(path: str) -> dict:
    """Parse a Live Link Face CSV into channels + per-frame times/values.

    Returns dict with: shape_names (original spelling), times (seconds from
    take start), values (rows x shapes), fps, rotation_count, kind
    ('calibrated'/'raw'/'unknown'), warnings (list of strings).
    """
    warnings = []
    basename = os.path.basename(path)
    if basename.lower().endswith("_neutral.csv"):
        raise FaceTakeError(
            "That is the neutral-pose snapshot, not the performance. "
            "Pick the _cal.csv (best) or _raw.csv file from the take.")

    with open(path, newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.reader(handle))
    rows = [row for row in rows if row and any(cell.strip() for cell in row)]
    if len(rows) < 2:
        raise FaceTakeError("No animation rows in this file. "
                            "Pick the _cal.csv from a recorded take.")

    header = [cell.strip() for cell in rows[0]]
    if len(header) < 3 or header[0].lower() != "timecode":
        raise FaceTakeError(
            "Not a Live Link Face CSV (first column should be Timecode).")
    channel_names = header[2:]

    known = sum(1 for name in channel_names if name.lower() in _KNOWN_NAMES)
    if known < len(channel_names) // 2:
        if len(channel_names) == len(LLF_COLUMN_ORDER):
            warnings.append(
                f"Only {known} of {len(channel_names)} column names were "
                "recognizable - using the standard Live Link Face column "
                "order instead (known app bug). Eyeball the result.")
            channel_names = list(LLF_COLUMN_ORDER)
        else:
            raise FaceTakeError(
                f"Column names are unrecognizable and there are "
                f"{len(channel_names)} of them instead of "
                f"{len(LLF_COLUMN_ORDER)}, so the standard order can't be "
                "assumed. Is this really a Live Link Face CSV?")

    raw_frames = []
    skipped = 0
    for row in rows[1:]:
        match = _TIMECODE_RE.match(row[0].strip())
        if match is None or len(row) != len(header):
            skipped += 1
            continue
        h, m, s, ff = (int(match.group(i)) for i in range(1, 5))
        frac_text = match.group(5) or "0"
        frac = int(frac_text) / (10 ** len(frac_text))
        try:
            values = [float(cell) for cell in row[2:]]
        except ValueError:
            skipped += 1
            continue
        raw_frames.append((h * 3600 + m * 60 + s, ff + frac, values))

    if not raw_frames:
        if any(row[0].strip() == "NeutralPose" for row in rows[1:]):
            raise FaceTakeError(
                "That is the neutral-pose snapshot, not the performance. "
                "Pick the _cal.csv (best) or _raw.csv file from the take.")
        raise FaceTakeError("No readable animation rows in this file.")
    if skipped:
        warnings.append(f"Skipped {skipped} unreadable row(s).")

    fps = _resolve_fps(path, raw_frames, warnings)

    times = []
    day_offset = 0.0
    prev = None
    for whole_seconds, frames_part, _ in raw_frames:
        t = whole_seconds + frames_part / fps + day_offset
        if prev is not None and t < prev - 1.0:
            day_offset += 86400.0
            t += 86400.0
        prev = t
        times.append(t)
    start = times[0]
    times = [t - start for t in times]

    dropped_order = sum(1 for a, b in zip(times, times[1:]) if b <= a)
    if dropped_order:
        warnings.append(f"{dropped_order} out-of-order row(s) kept as-is.")

    shape_indices = [i for i, name in enumerate(channel_names)
                     if name.lower() not in _ROTATION_NAMES]
    shape_names = [channel_names[i] for i in shape_indices]
    values = [[frame[2][i] for i in shape_indices] for frame in raw_frames]

    kind = "unknown"
    if basename.lower().endswith("_cal.csv"):
        kind = "calibrated"
    elif basename.lower().endswith("_raw.csv"):
        kind = "raw"

    return {
        "shape_names": shape_names,
        "times": times,
        "values": values,
        "fps": fps,
        "rotation_count": len(channel_names) - len(shape_indices),
        "kind": kind,
        "warnings": warnings,
    }


def _resolve_fps(path: str, raw_frames, warnings) -> float:
    """Capture rate: take.json sidecar when present, else the highest frame
    number seen in the timecodes (frames count 0..fps-1 within each second)."""
    observed = max(ff for _, ff, _ in raw_frames)
    guessed = float(int(observed) + 1)

    take_json = os.path.join(os.path.dirname(path), "take.json")
    if os.path.isfile(take_json):
        try:
            with open(take_json, encoding="utf-8") as handle:
                declared = float(json.load(handle)["videoTargetFrameRate"])
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            declared = None
        if declared:
            if abs(declared - guessed) > 1.0 and len(raw_frames) > declared:
                warnings.append(
                    f"take.json says {declared:.0f} fps but the timecodes "
                    f"look like {guessed:.0f} fps - using take.json.")
            return declared

    if guessed < 24.0:
        warnings.append(
            "Take too short to confirm its frame rate - assuming 60 fps.")
        return 60.0
    return guessed


def apply_face_take(target, parsed: dict, scene, take_label: str,
                    source_csv: str):
    """Write the parsed take as a shape-key action on target's mesh.

    Returns (matched_names, missing_names, last_frame). Idempotent per
    target: a previous HIHO face-take action on it is replaced, not stacked.
    """
    shape_keys = target.data.shape_keys
    if shape_keys is None:
        raise FaceTakeError(
            f"{target.name} has no sliders (shape keys). "
            "Click Spawn Test Face first, or pick a face mesh that has them.")

    by_lower = {key.name.lower(): key for key in shape_keys.key_blocks}
    matched = [(name, by_lower[name.lower()]) for name in parsed["shape_names"]
               if name.lower() in by_lower]
    missing = [name for name in parsed["shape_names"]
               if name.lower() not in by_lower]
    if not matched:
        raise FaceTakeError(
            f"None of the take's sliders exist on {target.name}. "
            "Click Spawn Test Face first, or pick a mesh with ARKit-named "
            "shape keys (eyeBlinkLeft, jawOpen, ...).")

    previous = None
    if (shape_keys.animation_data is not None
            and shape_keys.animation_data.action is not None):
        previous = shape_keys.animation_data.action

    action = bpy.data.actions.new(name=f"HIHO_FaceTake_{take_label}")
    shape_keys.animation_data_create()
    shape_keys.animation_data.action = action
    slot = action.slots.new(id_type='KEY', name=take_label)
    layer = action.layers.new("Layer")
    strip = layer.strips.new(type='KEYFRAME')
    channelbag = strip.channelbag(slot, ensure=True)
    shape_keys.animation_data.action_slot = slot

    if previous is not None and previous.users == 0 \
            and previous.name.startswith("HIHO_FaceTake_"):
        bpy.data.actions.remove(previous)

    scene_fps = scene.render.fps / scene.render.fps_base
    start_frame = float(scene.frame_start)
    frames = [start_frame + t * scene_fps for t in parsed["times"]]
    num = len(frames)

    name_to_column = {name: i for i, name in enumerate(parsed["shape_names"])}
    for source_name, key in matched:
        column = name_to_column[source_name]
        fcurve = channelbag.fcurves.new(
            data_path=f'key_blocks["{key.name}"].value')
        fcurve.keyframe_points.add(count=num)
        co = [0.0] * (2 * num)
        co[0::2] = frames
        co[1::2] = [row[column] for row in parsed["values"]]
        fcurve.keyframe_points.foreach_set("co", co)
        for point in fcurve.keyframe_points:
            point.interpolation = 'LINEAR'
        fcurve.update()

    action["hiho_source_csv"] = source_csv
    action["hiho_take_fps"] = parsed["fps"]

    last_frame = int(frames[-1]) + 1
    if scene.frame_end < last_frame:
        scene.frame_end = last_frame

    return [name for name, _ in matched], missing, last_frame
