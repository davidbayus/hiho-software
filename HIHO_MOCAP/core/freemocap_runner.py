# RETIRED (2026-06-09): not registered, not imported by the addon. The live
# capture path is operators/external_capture.py + external/record_take.py;
# processing is core/external_runner.py + external/. Kept on disk per the
# never-delete policy; excluded from shipped zips. Do not re-wire without
# reading AUDIT_2026-06-09.md (finding L1) — this code predates the headless
# pivot and bypasses the per-camera rotation system.
"""HIHO MOCAP — FreeMoCap pipeline wrapper for in-Blender processing.

Runs FreeMoCap's headless processing pipeline on a worker thread so Blender
stays responsive. Exposes progress + stage strings to the main thread via
simple shared state. No `bpy` imports per STAGE_3_DESIGN.md Decision 2.

HIHO MOCAP's Stage 1 recorder writes a flat layout:
    take_dir/
        Camera_0.mp4
        Camera_1.mp4
        Camera_2.mp4
        Camera_3.mp4

FreeMoCap expects:
    take_dir/
        synchronized_videos/
            Camera_0.mp4 ...
        <calibration TOML>
        output_data/   (created by the pipeline)

We reshape via symlinks (non-destructive) before processing.
"""

import logging
import multiprocessing
import queue
import shutil
import threading
from pathlib import Path
from typing import Optional


# Substring -> human label. Order = stage order. Used to drive the progress
# bar from FreeMoCap's logging_queue (per STEP_4_DEP_AUDIT.md, FMC emits one
# log line per stage start; no structured start/end events).
STAGES = (
    ("detecting", "Detecting 2D landmarks"),
    ("triangulat", "Triangulating 3D points"),
    ("filtering", "Filtering 3D data"),
    ("skeleton model", "Building skeleton"),
    ("center of mass", "Computing center of mass"),
    ("saving", "Saving output"),
)


class FreeMocapRunner:
    """Runs FreeMoCap's pipeline on a worker thread.

    Main thread reads progress_pct, current_stage, is_done, error, output_path
    via the property accessors. They are written from background threads but
    Python's GIL makes single-attribute reads/writes atomic — no locking needed
    for this access pattern.
    """

    def __init__(self, take_dir: str, calibration_toml_path: str):
        self.take_dir = Path(take_dir)
        self.calibration_toml_path = Path(calibration_toml_path)

        self._progress_pct = 0
        self._current_stage = "queued"
        self._is_done = False
        self._error: Optional[str] = None
        self._output_path: Optional[str] = None

        self._worker: Optional[threading.Thread] = None
        self._log_drain: Optional[threading.Thread] = None
        self._log_queue: Optional[multiprocessing.Queue] = None
        self._kill_event: Optional[multiprocessing.synchronize.Event] = None

    @property
    def progress_pct(self) -> int:
        return self._progress_pct

    @property
    def current_stage(self) -> str:
        return self._current_stage

    @property
    def is_done(self) -> bool:
        return self._is_done

    @property
    def error(self) -> Optional[str]:
        return self._error

    @property
    def output_path(self) -> Optional[str]:
        return self._output_path

    def start(self) -> None:
        if self._worker is not None:
            raise RuntimeError("FreeMocapRunner already started")

        self._log_queue = multiprocessing.Queue()
        self._kill_event = multiprocessing.Event()
        self._current_stage = "preparing"

        self._worker = threading.Thread(target=self._run, daemon=True)
        self._worker.start()

        self._log_drain = threading.Thread(target=self._drain_logs, daemon=True)
        self._log_drain.start()

    def stop(self) -> None:
        """Request cancellation. The pipeline polls kill_event between stages."""
        if self._kill_event is not None:
            self._kill_event.set()

    def _run(self) -> None:
        try:
            self._reshape_for_freemocap()
            self._current_stage = "starting pipeline"

            # Import inside the worker — a broken FreeMoCap install surfaces
            # as `runner.error`, not as an addon-enable crash.
            from freemocap.core_processes.process_motion_capture_videos.process_recording_folder import (
                process_recording_folder,
            )
            from freemocap.data_layer.recording_models.post_processing_parameter_models import (
                ProcessingParameterModel,
            )
            from freemocap.data_layer.recording_models.recording_info_model import RecordingInfoModel

            recording_info = RecordingInfoModel(recording_folder_path=str(self.take_dir))
            recording_info.calibration_toml_path = str(self.calibration_toml_path)

            params = ProcessingParameterModel(recording_info_model=recording_info)

            process_recording_folder(
                recording_processing_parameter_model=params,
                kill_event=self._kill_event,
                logging_queue=self._log_queue,
                use_tqdm=False,
            )

            self._output_path = recording_info.data_3d_npy_file_path
            self._progress_pct = 100
            self._current_stage = "done"
        except Exception as exc:
            self._error = f"{type(exc).__name__}: {exc}"
            self._current_stage = "error"
        finally:
            self._is_done = True

    def _reshape_for_freemocap(self) -> None:
        sync_dir = self.take_dir / "synchronized_videos"
        if sync_dir.exists():
            return
        sync_dir.mkdir()
        for mp4 in sorted(self.take_dir.glob("Camera_*.mp4")):
            link = sync_dir / mp4.name
            try:
                link.symlink_to(mp4)
            except OSError:
                shutil.copy2(mp4, link)

    def _drain_logs(self) -> None:
        if self._log_queue is None:
            return
        while not (self._is_done and self._log_queue.empty()):
            try:
                record = self._log_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                msg = record.getMessage() if isinstance(record, logging.LogRecord) else str(record)
            except Exception:
                msg = str(record)
            lower = msg.lower()
            for idx, (needle, label) in enumerate(STAGES):
                if needle in lower:
                    pct = int((idx + 1) / len(STAGES) * 100)
                    if pct > self._progress_pct:
                        self._progress_pct = pct
                    self._current_stage = label
                    break
