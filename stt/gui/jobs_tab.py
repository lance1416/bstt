from pathlib import Path

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QSortFilterProxyModel,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from stt import queue


class JobTableModel(QAbstractTableModel):
    _COLUMNS = ("Filename", "Status", "Completed", "Error")
    _BRUSHES: dict[str, QBrush] = {}

    @classmethod
    def _brushes(cls) -> dict[str, QBrush]:
        if not cls._BRUSHES:
            cls._BRUSHES = {
                "done": QBrush(QColor("#c8e6c9")),
                "failed": QBrush(QColor("#ffcdd2")),
                "pending": QBrush(QColor("#f5f5f5")),
                "in_progress": QBrush(QColor("#bbdefb")),
            }
        return cls._BRUSHES

    def __init__(self, db_path: str, parent=None) -> None:
        super().__init__(parent)
        self.db_path = db_path
        self._rows: list[dict] = []

    def refresh(self) -> None:
        self.beginResetModel()
        try:
            if Path(self.db_path).exists():
                self._rows = queue.list_jobs(self.db_path)
            else:
                self._rows = []
        except Exception:
            self._rows = []
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self._COLUMNS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self._COLUMNS[section]
        return None

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        col = index.column()
        if role == Qt.DisplayRole:
            if col == 0:
                return Path(row["file_path"]).name
            if col == 1:
                return row["status"]
            if col == 2:
                return row.get("completed_at") or row.get("started_at") or ""
            if col == 3:
                return row.get("error") or ""
        if role == Qt.BackgroundRole:
            return self._brushes().get(row["status"])
        return None

    def row_data(self, row_index: int) -> dict | None:
        if 0 <= row_index < len(self._rows):
            return self._rows[row_index]
        return None


class JobsTab(QWidget):
    view_transcript = Signal(str)  # emits file_path

    def __init__(self, db_path: str) -> None:
        super().__init__()
        self.db_path = db_path
        self._model = JobTableModel(db_path)

        self._proxy = QSortFilterProxyModel()
        self._proxy.setSourceModel(self._model)
        self._proxy.setFilterKeyColumn(0)
        self._proxy.setFilterCaseSensitivity(Qt.CaseInsensitive)

        # Auto-refresh timer (active during pipeline run)
        self._timer = QTimer(self)
        self._timer.setInterval(2000)
        self._timer.timeout.connect(self.refresh)

        # Filter
        filter_edit = QLineEdit()
        filter_edit.setPlaceholderText("Filter by filename…")
        filter_edit.textChanged.connect(self._proxy.setFilterFixedString)

        # Table
        self._table = QTableView()
        self._table.setModel(self._proxy)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.doubleClicked.connect(self._on_double_click)

        # Buttons
        retry_btn = QPushButton("Retry Failed")
        retry_btn.clicked.connect(self._retry_failed)
        reset_btn = QPushButton("Reset All")
        reset_btn.clicked.connect(self._reset_all)
        self._status_label = QLabel()
        btn_row = QHBoxLayout()
        btn_row.addWidget(retry_btn)
        btn_row.addWidget(reset_btn)
        btn_row.addStretch()
        btn_row.addWidget(self._status_label)

        layout = QVBoxLayout(self)
        layout.addWidget(filter_edit)
        layout.addWidget(self._table, 1)
        layout.addLayout(btn_row)

        self.refresh()

    def refresh(self) -> None:
        self._model.refresh()
        total = self._model.rowCount()
        if Path(self.db_path).exists():
            counts = queue.status_counts(self.db_path)
            done = counts.get("done", 0)
            failed = counts.get("failed", 0)
            self._status_label.setText(f"{done} done, {failed} failed / {total} total")
        else:
            self._status_label.setText("No database found. Run the pipeline first.")

    def start_auto_refresh(self) -> None:
        self._timer.start()

    def stop_auto_refresh(self) -> None:
        self._timer.stop()
        self.refresh()

    def _on_double_click(self, proxy_index: QModelIndex) -> None:
        source_index = self._proxy.mapToSource(proxy_index)
        row = self._model.row_data(source_index.row())
        if row and row["status"] == "done":
            self.view_transcript.emit(row["file_path"])

    def _retry_failed(self) -> None:
        n = queue.retry_failed(self.db_path)
        self.refresh()
        if n:
            QMessageBox.information(self, "Retry Failed", f"Reset {n} failed job(s) to pending.")

    def _reset_all(self) -> None:
        reply = QMessageBox.question(
            self,
            "Reset All",
            "Reset all jobs to pending? This clears done and failed status.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            queue.reset_all(self.db_path)
            self.refresh()
