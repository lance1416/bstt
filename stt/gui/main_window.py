from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMainWindow, QMessageBox, QProgressDialog, QTabWidget

from stt.config import Settings
from stt.gui.config_tab import ConfigTab
from stt.gui.jobs_tab import JobsTab
from stt.gui.run_tab import RunTab
from stt.gui.transcripts_tab import TranscriptsTab
from stt.gui.worker import ReprocessWorker


class MainWindow(QMainWindow):
    def __init__(
        self,
        db_path: str,
        output_dir: str,
        config_dir: str,
        settings_path: str,
    ) -> None:
        super().__init__()
        self.setWindowTitle("语音转录系统")
        self.setMinimumSize(900, 600)

        self._run_tab = RunTab(db_path, output_dir, config_dir, settings_path)
        self._jobs_tab = JobsTab(db_path)
        self._transcripts_tab = TranscriptsTab(db_path)
        self._config_tab = ConfigTab(config_dir, settings_path)

        self._tabs = QTabWidget()
        self._tabs.addTab(self._run_tab, "运行")
        self._tabs.addTab(self._jobs_tab, "任务")
        self._tabs.addTab(self._transcripts_tab, "转录文本")
        self._tabs.addTab(self._config_tab, "设置")
        self.setCentralWidget(self._tabs)

        # Cross-tab wiring
        self._run_tab.pipeline_started.connect(self._jobs_tab.start_auto_refresh)
        self._run_tab.pipeline_finished.connect(self._jobs_tab.stop_auto_refresh)
        self._jobs_tab.view_transcript.connect(self._on_view_transcript)

        self._db_path = db_path
        self._output_dir = output_dir
        self._config_dir = config_dir
        self._settings_path = settings_path
        self._reprocess_worker = None

        self._config_tab.reprocess_all_requested.connect(self._on_reprocess_all)
        self._transcripts_tab.reprocess_file_requested.connect(self._on_reprocess_file)

    def _on_view_transcript(self, file_path: str) -> None:
        self._tabs.setCurrentWidget(self._transcripts_tab)
        self._transcripts_tab.load_for_file(file_path)

    def _on_reprocess_all(self) -> None:
        self._start_reprocess(None)

    def _on_reprocess_file(self, file_path: str) -> None:
        self._start_reprocess(file_path)

    def _start_reprocess(self, file_path) -> None:
        if self._reprocess_worker is not None:
            return
        settings = Settings.load(self._settings_path)
        worker = ReprocessWorker(
            self._db_path, self._output_dir, self._config_dir, settings, file_path
        )
        dialog = QProgressDialog("正在重新处理…", "取消", 0, 0, self)
        dialog.setWindowModality(Qt.WindowModal)
        dialog.setMinimumDuration(0)

        def on_progress(e) -> None:
            if e.total:
                dialog.setMaximum(e.total)
                dialog.setValue(e.done)

        def on_finished() -> None:
            dialog.close()
            self._reprocess_worker = None
            QMessageBox.information(self, "完成", "重新处理完成。")

        worker.progress.connect(on_progress)
        dialog.canceled.connect(worker.stop)
        worker.finished.connect(on_finished)
        worker.error.connect(lambda msg: QMessageBox.warning(self, "错误", msg))
        self._reprocess_worker = worker
        worker.start()
        dialog.show()
