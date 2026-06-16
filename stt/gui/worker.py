import logging
import threading

from PySide6.QtCore import QThread, Signal

from stt import pipeline
from stt.config import Settings


class QtLoggingHandler(logging.Handler):
    def __init__(self, signal: Signal) -> None:
        super().__init__()
        self._signal = signal

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._signal.emit(self.format(record))
        except Exception:
            self.handleError(record)


class PipelineWorker(QThread):
    progress = Signal(pipeline.ProgressEvent)
    segment = Signal(pipeline.SegmentEvent)
    log_line = Signal(str)
    finished = Signal()
    error = Signal(str)

    def __init__(
        self,
        input_dir: str,
        db_path: str,
        output_dir: str,
        config_dir: str,
        settings: Settings,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.input_dir = input_dir
        self.db_path = db_path
        self.output_dir = output_dir
        self.config_dir = config_dir
        self.settings = settings
        self.stop_event = threading.Event()

    def run(self) -> None:
        from stt import log

        handler = QtLoggingHandler(self.log_line)
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)-8s] %(message)s", "%H:%M:%S")
        )
        logger = log.get()
        logger.addHandler(handler)
        try:
            pipeline.run(
                input_dir=self.input_dir,
                db_path=self.db_path,
                output_dir=self.output_dir,
                config_dir=self.config_dir,
                settings=self.settings,
                stop_event=self.stop_event,
                on_progress=lambda e: self.progress.emit(e),
                on_segment=lambda e: self.segment.emit(e),
            )
        except Exception as e:
            self.error.emit(str(e))
        finally:
            logger.removeHandler(handler)
            self.finished.emit()

    def stop(self) -> None:
        self.stop_event.set()
