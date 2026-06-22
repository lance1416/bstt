import multiprocessing as mp
from queue import Empty

from PySide6.QtCore import QThread, Signal

from stt import procrun


class _ProcessWorker(QThread):
    """Run a pipeline entry point in a child process and re-emit its events.

    The pipeline cannot run directly on this QThread: on macOS, MLX/Metal GPU
    work crashes (SIGILL) when the Qt event loop is live on the main thread.
    Running it in a separate process (no Qt loop) avoids that. This thread just
    drains the child's event queue and re-emits the same Qt signals, so the rest
    of the GUI is unchanged. Subclasses supply the child target + kwargs.
    """

    progress = Signal(object)  # pipeline.ProgressEvent
    segment = Signal(object)  # pipeline.SegmentEvent
    log_line = Signal(str)
    finished = Signal()
    error = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        # "spawn" (not fork): a fresh interpreter with no inherited Qt/Metal state.
        self._ctx = mp.get_context("spawn")
        self._stop_event = self._ctx.Event()
        self._proc = None
        self._stopping = False

    def _target(self):
        """Return ``(callable, kwargs)`` to run in the child process."""
        raise NotImplementedError

    def run(self) -> None:
        func, kwargs = self._target()
        queue = self._ctx.Queue()
        proc = self._ctx.Process(
            target=func, args=(queue, self._stop_event, kwargs), daemon=True
        )
        self._proc = proc
        proc.start()
        terminal = False  # saw an explicit "done"/"error" from the child
        try:
            while True:
                try:
                    kind, payload = queue.get(timeout=0.2)
                except Empty:
                    if not proc.is_alive():
                        break
                    continue
                if kind == "progress":
                    self.progress.emit(payload)
                elif kind == "segment":
                    self.segment.emit(payload)
                elif kind == "log":
                    self.log_line.emit(payload)
                elif kind == "error":
                    terminal = True
                    self.error.emit(payload)
                elif kind == "done":
                    terminal = True
                    break
        finally:
            proc.join()
            # A user-requested stop terminates the child (nonzero exit) — that's
            # expected, not a crash, so only report unexpected exits.
            if not terminal and not self._stopping and proc.exitcode not in (0, None):
                self.error.emit(f"处理进程异常退出（代码 {proc.exitcode}）")
            self.finished.emit()

    def stop(self) -> None:
        # Stop promptly even mid-file: mlx_whisper.transcribe is one blocking call
        # that never checks stop_event, so set the flag (graceful, between files)
        # AND terminate the child (handles a long in-progress file).
        self._stopping = True
        self._stop_event.set()
        proc = self._proc
        if proc is not None and proc.is_alive():
            proc.terminate()


class PipelineWorker(_ProcessWorker):
    def __init__(
        self,
        input_dir: str,
        db_path: str,
        output_dir: str,
        config_dir: str,
        settings,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._kwargs = dict(
            input_dir=input_dir,
            db_path=db_path,
            output_dir=output_dir,
            config_dir=config_dir,
            settings=settings,
        )

    def _target(self):
        return procrun.run_pipeline, self._kwargs


class ReprocessWorker(_ProcessWorker):
    def __init__(
        self,
        db_path: str,
        output_dir: str,
        config_dir: str,
        settings,
        file_path: str | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._kwargs = dict(
            db_path=db_path,
            output_dir=output_dir,
            config_dir=config_dir,
            settings=settings,
            file_path=file_path,
        )

    def _target(self):
        return procrun.run_reprocess, self._kwargs
