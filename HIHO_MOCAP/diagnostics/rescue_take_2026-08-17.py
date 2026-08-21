"""One-off rescue for take 2026-08-17_14-01-15: the 2D tracking finished and
saved valid data, but FreeMoCap's end-of-tracking validity check hit a
transient video-read hiccup (three videos momentarily read 0 frames) and
aborted before triangulation. This driver re-runs the pipeline with
run_image_tracking=False so it LOADS the saved 2D npy and continues from
triangulation onward. Parameter setup and sentinel/quality behavior are
reused from the addon's own external/process_take.py so the result is
indistinguishable from a normal panel-run process.

Runs inside freemocap-env. No addon code is modified.
"""
import sys
from pathlib import Path

sys.path.insert(0, "/Users/davidbayus/Desktop/DR_BAYUS/SOFTWARE/HIHO_MOCAP/external")
import process_take as pt

RECORDING = Path(
    "/Users/davidbayus/Desktop/HIHO_ALL/HIHO_CAPTURES/HIHO_CAPTURES/2026-08-17_14-01-15"
)
CALIBRATION = Path(
    "/Users/davidbayus/freemocap_data/calibrations/2026-08-17_13-47-14_camera_calibration.toml"
)


def main() -> int:
    assert RECORDING.is_dir(), f"missing recording: {RECORDING}"
    assert CALIBRATION.is_file(), f"missing calibration: {CALIBRATION}"

    pt._clear_sentinels(RECORDING)
    pt._emit(pt.INFO, "rescue: importing freemocap")

    from freemocap.core_processes.process_motion_capture_videos.process_recording_folder import (
        process_recording_folder,
    )
    from freemocap.data_layer.recording_models.post_processing_parameter_models import (
        ProcessingParameterModel,
    )
    from freemocap.data_layer.recording_models.recording_info_model import (
        RecordingInfoModel,
    )

    info = RecordingInfoModel(recording_folder_path=str(RECORDING))
    info.calibration_toml_path = str(CALIBRATION)
    params = ProcessingParameterModel(recording_info_model=info)

    # Mirror process_take.py's defaults: outlier rejection on, 60 fps clocks.
    params.anipose_triangulate_3d_parameters_model.use_triangulate_outlier_rejection = True
    params.post_processing_parameters_model.framerate = 60.0
    params.post_processing_parameters_model.butterworth_filter_parameters.sampling_rate = 60.0

    # The rescue: load the saved (validated-good) 2D data instead of re-tracking.
    params.tracking_parameters_model.run_image_tracking = False
    npy = info.data_2d_npy_file_path
    assert Path(npy).is_file(), f"2D npy not where freemocap expects it: {npy}"
    pt._emit(pt.INFO, f"rescue: loading 2D data from {npy}")

    try:
        process_recording_folder(
            recording_processing_parameter_model=params,
            use_tqdm=False,
        )
    except Exception as exc:  # same contract as process_take.py
        msg = f"process failed: {type(exc).__name__}: {exc}"
        pt._emit(pt.ERROR, msg)
        pt._write_sentinel(RECORDING, pt.ERROR_FILE, msg)
        return 4

    out = RECORDING / "output_data"
    required = {
        "body": out / "mediapipe_body_3d_xyz.npy",
        "right hand": out / "mediapipe_right_hand_3d_xyz.npy",
        "left hand": out / "mediapipe_left_hand_3d_xyz.npy",
        "reprojection error": out / "raw_data" / "mediapipe_3dData_numFrames_numTrackedPoints_reprojectionError.npy",
    }
    missing = [label for label, p in required.items() if not p.is_file()]
    if missing:
        msg = f"finished but the output is incomplete (missing: {', '.join(missing)}) in {out}"
        pt._emit(pt.ERROR, msg)
        pt._write_sentinel(RECORDING, pt.ERROR_FILE, msg)
        return 5

    quality = pt._score_quality(required["reprojection error"])
    pt._write_sentinel(RECORDING, pt.QUALITY_FILE, quality)
    pt._emit(pt.INFO, quality.splitlines()[0])

    body = required["body"]
    pt._write_sentinel(RECORDING, pt.DONE_FILE, str(body))
    pt._emit(pt.DONE, str(body))
    return 0


if __name__ == "__main__":
    sys.exit(main())
