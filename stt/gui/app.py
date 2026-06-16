import sys

from PySide6.QtWidgets import QApplication

from stt.gui.main_window import MainWindow

_DEFAULT_DB = "stt.db"
_DEFAULT_OUTPUT = "output"
_DEFAULT_CONFIG = "config"
_DEFAULT_SETTINGS = "config/settings.toml"


def launch() -> None:
    from stt import log
    log.setup()
    app = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow(
        db_path=_DEFAULT_DB,
        output_dir=_DEFAULT_OUTPUT,
        config_dir=_DEFAULT_CONFIG,
        settings_path=_DEFAULT_SETTINGS,
    )
    window.show()
    sys.exit(app.exec())
