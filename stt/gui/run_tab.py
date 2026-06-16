from pathlib import Path

from PySide6.QtCore import QSettings, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from stt.config import Settings
from stt.gui.worker import PipelineWorker


class RunTab(QWidget):
    pipeline_started = Signal()
    pipeline_finished = Signal()

    def __init__(
        self,
        db_path: str,
        output_dir: str,
        config_dir: str,
        settings_path: str,
    ) -> None:
        super().__init__()
        self.db_path = db_path
        self.output_dir = output_dir
        self.config_dir = config_dir
        self.settings_path = settings_path
        self._worker: PipelineWorker | None = None
        self._qsettings = QSettings("stt", "STTPipeline")

        # Folder picker
        self._folder_edit = QLineEdit()
        self._folder_edit.setPlaceholderText("Select input folder…")
        last_folder = self._qsettings.value("last_input_folder", "")
        if last_folder:
            self._folder_edit.setText(str(last_folder))
        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self._browse)
        folder_row = QHBoxLayout()
        folder_row.addWidget(QLabel("Input folder:"))
        folder_row.addWidget(self._folder_edit, 1)
        folder_row.addWidget(browse_btn)

        # Start / Stop
        self._start_btn = QPushButton("Start")
        self._stop_btn = QPushButton("Stop")
        self._stop_btn.setEnabled(False)
        self._start_btn.clicked.connect(self._start)
        self._stop_btn.clicked.connect(self._stop)
        btn_row = QHBoxLayout()
        btn_row.addWidget(self._start_btn)
        btn_row.addWidget(self._stop_btn)
        btn_row.addStretch()

        # Progress bars
        self._queue_bar = QProgressBar()
        self._queue_bar.setMaximum(0)
        self._queue_bar.setTextVisible(True)
        self._file_bar = QProgressBar()
        self._file_bar.setMaximum(0)
        self._file_bar.setTextVisible(True)

        # Log
        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)

        layout = QVBoxLayout(self)
        layout.addLayout(folder_row)
        layout.addLayout(btn_row)
        layout.addWidget(QLabel("Queue progress:"))
        layout.addWidget(self._queue_bar)
        layout.addWidget(QLabel("File progress:"))
        layout.addWidget(self._file_bar)
        layout.addWidget(QLabel("Log:"))
        layout.addWidget(self._log, 1)

    def _browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Select Input Folder", self._folder_edit.text()
        )
        if folder:
            self._folder_edit.setText(folder)
            self._qsettings.setValue("last_input_folder", folder)

    def _start(self) -> None:
        folder = self._folder_edit.text().strip()
        if not folder:
            QMessageBox.warning(self, "No folder", "Please select an input folder first.")
            return
        self._qsettings.setValue("last_input_folder", folder)
        settings = Settings.load(self.settings_path)
        self._worker = PipelineWorker(
            input_dir=folder,
            db_path=self.db_path,
            output_dir=self.output_dir,
            config_dir=self.config_dir,
            settings=settings,
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.segment.connect(self._on_segment)
        self._worker.log_line.connect(self._append_log)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._start_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self._log.clear()
        self._queue_bar.setMaximum(0)
        self._queue_bar.setValue(0)
        self._file_bar.setMaximum(0)
        self._file_bar.setValue(0)
        self._worker.start()
        self.pipeline_started.emit()

    def _stop(self) -> None:
        if self._worker:
            self._worker.stop()
        self._stop_btn.setEnabled(False)

    def _on_progress(self, event: object) -> None:
        from stt.pipeline import ProgressEvent

        e: ProgressEvent = event  # type: ignore[assignment]
        self._queue_bar.setMaximum(e.total)
        self._queue_bar.setValue(e.done + e.failed)
        self._queue_bar.setFormat(
            f"Queue: {e.done} done, {e.failed} failed / {e.total} total"
        )

    def _on_segment(self, event: object) -> None:
        from stt.pipeline import SegmentEvent

        e: SegmentEvent = event  # type: ignore[assignment]
        total = max(1, int(e.total_seconds))
        current = int(e.current_seconds)
        self._file_bar.setMaximum(total)
        self._file_bar.setValue(current)
        name = Path(e.file_path).stem[:30]
        self._file_bar.setFormat(f"{name}: {current}s / {total}s")

    def _append_log(self, line: str) -> None:
        self._log.appendPlainText(line)
        sb = self._log.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_finished(self) -> None:
        self._start_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._worker = None
        self.pipeline_finished.emit()

    def _on_error(self, msg: str) -> None:
        # worker always emits finished() after error() in its finally block,
        # so _on_finished handles button reset and pipeline_finished signal
        QMessageBox.critical(self, "Pipeline Error", msg)
