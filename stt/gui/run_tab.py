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
from stt.pipeline import ProgressEvent, SegmentEvent


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
        self._folder_edit.setPlaceholderText("选择输入文件夹…")
        last_folder = self._qsettings.value("last_input_folder", "")
        if last_folder:
            self._folder_edit.setText(str(last_folder))
        browse_btn = QPushButton("浏览")
        browse_btn.clicked.connect(self._browse)
        folder_row = QHBoxLayout()
        folder_row.addWidget(QLabel("输入文件夹："))
        folder_row.addWidget(self._folder_edit, 1)
        folder_row.addWidget(browse_btn)

        # Start / Stop
        self._start_btn = QPushButton("开始")
        self._stop_btn = QPushButton("停止")
        self._stop_btn.setEnabled(False)
        self._start_btn.clicked.connect(self._start)
        self._stop_btn.clicked.connect(self._stop)
        btn_row = QHBoxLayout()
        btn_row.addWidget(self._start_btn)
        btn_row.addWidget(self._stop_btn)
        btn_row.addStretch()

        # Progress bars — start in static idle state (setMaximum(0) would animate)
        self._queue_bar = QProgressBar()
        self._queue_bar.setTextVisible(True)
        self._file_bar = QProgressBar()
        self._file_bar.setTextVisible(True)
        self._reset_progress_bars()

        # Log
        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)

        layout = QVBoxLayout(self)
        layout.addLayout(folder_row)
        layout.addLayout(btn_row)
        layout.addWidget(QLabel("队列进度："))
        layout.addWidget(self._queue_bar)
        layout.addWidget(QLabel("文件进度："))
        layout.addWidget(self._file_bar)
        layout.addWidget(QLabel("日志："))
        layout.addWidget(self._log, 1)

    def _browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "选择输入文件夹", self._folder_edit.text()
        )
        if folder:
            self._folder_edit.setText(folder)
            self._qsettings.setValue("last_input_folder", folder)

    def _start(self) -> None:
        folder = self._folder_edit.text().strip()
        if not folder:
            QMessageBox.warning(self, "未选择文件夹", "请先选择输入文件夹。")
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
        # Start determinate (no busy spinner): pipeline.run emits the queue total
        # immediately, and per-file/segment events drive the bars from there.
        for bar in (self._queue_bar, self._file_bar):
            bar.setRange(0, 1)
            bar.setValue(0)
            bar.setFormat("准备中…")
        self._worker.start()
        self.pipeline_started.emit()

    def _reset_progress_bars(self) -> None:
        for bar in (self._queue_bar, self._file_bar):
            bar.setRange(0, 1)
            bar.setValue(0)
            bar.setFormat("等待中…")

    def _stop(self) -> None:
        if self._worker:
            self._worker.stop()
        self._stop_btn.setEnabled(False)

    def _on_progress(self, e: ProgressEvent) -> None:
        # max(1, ...) keeps the bar determinate; setMaximum(0) would animate.
        self._queue_bar.setMaximum(max(1, e.total))
        self._queue_bar.setValue(e.done + e.failed)
        self._queue_bar.setFormat(
            f"队列：{e.done} 已完成，{e.failed} 失败 / {e.total} 总计"
        )
        # A file just finished (or the run is starting): the next file hasn't
        # streamed segments yet, so reset the file bar to a determinate idle
        # state rather than leaving the previous file's bar full.
        self._file_bar.setRange(0, 1)
        self._file_bar.setValue(0)
        self._file_bar.setFormat("准备中…")

    def _on_segment(self, e: SegmentEvent) -> None:
        total = max(1, int(e.total_seconds))
        current = int(e.current_seconds)
        self._file_bar.setMaximum(total)
        self._file_bar.setValue(current)
        name = Path(e.file_path).stem[:30]
        self._file_bar.setFormat(f"{name}：{current}秒 / {total}秒")

    def _append_log(self, line: str) -> None:
        self._log.appendPlainText(line)
        sb = self._log.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_finished(self) -> None:
        self._start_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._worker = None
        self._reset_progress_bars()
        self.pipeline_finished.emit()

    def _on_error(self, msg: str) -> None:
        # worker always emits finished() after error() in its finally block,
        # so _on_finished handles button reset and pipeline_finished signal
        QMessageBox.critical(self, "处理出错", msg)
