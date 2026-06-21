from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from stt import writer


class SearchResultModel(QAbstractTableModel):
    _COLUMNS = ("日期", "文件名", "摘要")

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._rows: list[dict] = []
        self._query: str = ""

    def set_results(self, rows: list[dict], query: str) -> None:
        self.beginResetModel()
        self._rows = rows
        self._query = query
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
        if not index.isValid() or role != Qt.DisplayRole:
            return None
        row = self._rows[index.row()]
        col = index.column()
        if col == 0:
            return row.get("date") or ""
        if col == 1:
            return Path(row["file_path"]).name
        if col == 2:
            return _excerpt(row["text"], self._query)
        return None

    def full_text(self, row_index: int) -> tuple[str, str] | None:
        """Returns (file_path, text) for the given row, or None if out of bounds."""
        if row_index < 0 or row_index >= len(self._rows):
            return None
        row = self._rows[row_index]
        return row["file_path"], row["text"]


def _excerpt(text: str, query: str, window: int = 80) -> str:
    pos = text.lower().find(query.lower()) if query else -1
    if pos == -1:
        return text[:window] + ("…" if len(text) > window else "")
    start = max(0, pos - 10)
    snippet = text[start : start + window]
    prefix = "…" if start > 0 else ""
    suffix = "…" if start + window < len(text) else ""
    return prefix + snippet + suffix


class TranscriptsTab(QWidget):
    reprocess_file_requested = Signal(str)

    def __init__(self, db_path: str) -> None:
        super().__init__()
        self.db_path = db_path
        self._model = SearchResultModel()
        self._current_query = ""
        self._current_file_path = ""

        # Search row
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("搜索转录内容…")
        self._search_edit.returnPressed.connect(self._search)
        search_btn = QPushButton("搜索")
        search_btn.clicked.connect(self._search)
        search_row = QHBoxLayout()
        search_row.addWidget(self._search_edit, 1)
        search_row.addWidget(search_btn)

        # Results table
        self._table = QTableView()
        self._table.setModel(self._model)
        self._table.setSelectionBehavior(QTableView.SelectRows)
        self._table.setEditTriggers(QTableView.NoEditTriggers)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.selectionModel().selectionChanged.connect(self._on_select)

        # Transcript viewer
        self._viewer = QPlainTextEdit()
        self._viewer.setReadOnly(True)
        self._reprocess_btn = QPushButton("重新处理此文件")
        self._reprocess_btn.clicked.connect(self._on_reprocess_clicked)

        # Layout: search + table on top, viewer on bottom
        results_widget = QWidget()
        results_layout = QVBoxLayout(results_widget)
        results_layout.setContentsMargins(0, 0, 0, 0)
        results_layout.addLayout(search_row)
        results_layout.addWidget(self._table)

        viewer_widget = QWidget()
        viewer_layout = QVBoxLayout(viewer_widget)
        viewer_layout.setContentsMargins(0, 0, 0, 0)
        viewer_layout.addWidget(self._viewer)
        viewer_layout.addWidget(self._reprocess_btn)

        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(results_widget)
        splitter.addWidget(viewer_widget)
        splitter.setSizes([300, 300])

        layout = QVBoxLayout(self)
        layout.addWidget(splitter)

    def _search(self) -> None:
        query = self._search_edit.text().strip()
        if not query:
            return
        self._current_query = query
        if not Path(self.db_path).exists():
            self._model.set_results([], query)
            self._viewer.setPlainText("未找到数据库，请先运行处理流程。")
            return
        try:
            rows = writer.search_transcripts(self.db_path, query)
        except Exception:
            rows = []
        self._model.set_results(rows, query)
        self._viewer.clear()

    def _on_select(self) -> None:
        indexes = self._table.selectionModel().selectedRows()
        if not indexes:
            return
        result = self._model.full_text(indexes[0].row())
        if result is None:
            return
        file_path, text = result
        self._current_file_path = file_path
        self._viewer.setPlainText(text)
        if self._current_query:
            self._highlight(self._current_query)

    def _highlight(self, query: str) -> None:
        fmt = QTextCharFormat()
        fmt.setBackground(QColor("#fff176"))
        self._viewer.moveCursor(QTextCursor.Start)
        while self._viewer.find(query):
            tc = self._viewer.textCursor()
            tc.mergeCharFormat(fmt)
        self._viewer.moveCursor(QTextCursor.Start)

    def load_for_file(self, file_path: str) -> None:
        self._current_file_path = file_path
        result = writer.get_transcript(self.db_path, file_path)
        self._search_edit.clear()
        self._model.set_results([], "")
        self._current_query = ""
        if result:
            self._viewer.setPlainText(result["text"])
        else:
            self._viewer.setPlainText("（未找到转录）")

    def _on_reprocess_clicked(self) -> None:
        if self._current_file_path:
            self.reprocess_file_requested.emit(self._current_file_path)
