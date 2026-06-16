from PySide6.QtWidgets import QMainWindow, QTabWidget

from stt.gui.config_tab import ConfigTab
from stt.gui.jobs_tab import JobsTab
from stt.gui.run_tab import RunTab
from stt.gui.transcripts_tab import TranscriptsTab


class MainWindow(QMainWindow):
    def __init__(
        self,
        db_path: str,
        output_dir: str,
        config_dir: str,
        settings_path: str,
    ) -> None:
        super().__init__()
        self.setWindowTitle("STT Pipeline")
        self.setMinimumSize(900, 600)

        self._run_tab = RunTab(db_path, output_dir, config_dir, settings_path)
        self._jobs_tab = JobsTab(db_path)
        self._transcripts_tab = TranscriptsTab(db_path)
        self._config_tab = ConfigTab(config_dir, settings_path)

        self._tabs = QTabWidget()
        self._tabs.addTab(self._run_tab, "Run")
        self._tabs.addTab(self._jobs_tab, "Jobs")
        self._tabs.addTab(self._transcripts_tab, "Transcripts")
        self._tabs.addTab(self._config_tab, "Config")
        self.setCentralWidget(self._tabs)

        # Cross-tab wiring
        self._run_tab.pipeline_started.connect(self._jobs_tab.start_auto_refresh)
        self._run_tab.pipeline_finished.connect(self._jobs_tab.stop_auto_refresh)
        self._jobs_tab.view_transcript.connect(self._on_view_transcript)

    def _on_view_transcript(self, file_path: str) -> None:
        self._tabs.setCurrentWidget(self._transcripts_tab)
        self._transcripts_tab.load_for_file(file_path)
