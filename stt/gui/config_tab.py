import json
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from stt.config import Settings


def _to_toml(settings: Settings) -> str:
    m = settings.model
    p = settings.punctuation
    return "\n".join(
        [
            "[model]",
            f'size = "{m.size}"',
            f'device = "{m.device}"',
            f'compute_type = "{m.compute_type}"',
            f'language = "{m.language}"',
            f'vad_filter = {"true" if m.vad_filter else "false"}',
            f"beam_size = {m.beam_size}",
            "",
            "[punctuation]",
            f'enabled = {"true" if p.enabled else "false"}',
            f'model = "{p.model}"',
            "",
        ]
    )


class ConfigTab(QWidget):
    reprocess_all_requested = Signal()

    def __init__(self, config_dir: str, settings_path: str) -> None:
        super().__init__()
        self.config_dir = config_dir
        self.settings_path = settings_path
        self._fillers_path = str(Path(config_dir) / "fillers.txt")
        self._terms_path = str(Path(config_dir) / "buddhist_terms.json")

        settings = Settings.load(settings_path)

        # --- Model settings group ---
        model_group = QGroupBox("模型设置")
        form = QFormLayout(model_group)

        self._size_combo = QComboBox()
        self._size_combo.addItems(["tiny", "base", "small", "medium", "large-v2", "large-v3"])
        self._size_combo.setCurrentText(settings.model.size)
        form.addRow("模型大小：", self._size_combo)

        self._device_combo = QComboBox()
        self._device_combo.addItems(["auto", "cuda", "cpu", "mps"])
        self._device_combo.setCurrentText(settings.model.device)
        form.addRow("运算设备：", self._device_combo)

        self._language_edit = QLineEdit(settings.model.language)
        form.addRow("语言：", self._language_edit)

        self._beam_spin = QSpinBox()
        self._beam_spin.setRange(1, 10)
        self._beam_spin.setValue(settings.model.beam_size)
        form.addRow("束宽：", self._beam_spin)

        self._punc_check = QCheckBox("启用标点")
        self._punc_check.setChecked(settings.punctuation.enabled)
        form.addRow("标点：", self._punc_check)

        self._punc_model_edit = QLineEdit(settings.punctuation.model)
        self._punc_model_edit.setVisible(settings.punctuation.enabled)
        self._punc_check.toggled.connect(self._punc_model_edit.setVisible)
        form.addRow("标点模型：", self._punc_model_edit)

        # --- Fillers group ---
        fillers_group = QGroupBox("语气词")
        fillers_layout = QVBoxLayout(fillers_group)
        self._fillers_list = QListWidget()
        self._fillers_list.setMinimumHeight(120)
        self._load_fillers()
        add_filler_btn = QPushButton("添加")
        add_filler_btn.clicked.connect(self._add_filler)
        remove_filler_btn = QPushButton("删除")
        remove_filler_btn.clicked.connect(self._remove_filler)
        filler_btn_row = QHBoxLayout()
        filler_btn_row.addWidget(add_filler_btn)
        filler_btn_row.addWidget(remove_filler_btn)
        filler_btn_row.addStretch()
        fillers_layout.addWidget(self._fillers_list)
        fillers_layout.addLayout(filler_btn_row)

        # --- Terms group ---
        terms_group = QGroupBox("佛教术语纠正")
        terms_layout = QVBoxLayout(terms_group)
        self._terms_table = QTableWidget(0, 2)
        self._terms_table.setHorizontalHeaderLabels(["错误形式", "正确形式"])
        self._terms_table.setMinimumHeight(120)
        self._terms_table.horizontalHeader().setStretchLastSection(True)
        self._load_terms()
        add_term_btn = QPushButton("添加行")
        add_term_btn.clicked.connect(self._add_term_row)
        remove_term_btn = QPushButton("删除行")
        remove_term_btn.clicked.connect(self._remove_term_row)
        term_btn_row = QHBoxLayout()
        term_btn_row.addWidget(add_term_btn)
        term_btn_row.addWidget(remove_term_btn)
        term_btn_row.addStretch()
        terms_layout.addWidget(self._terms_table)
        terms_layout.addLayout(term_btn_row)

        # --- Save button ---
        save_btn = QPushButton("保存设置")
        save_btn.clicked.connect(self._save)

        reprocess_btn = QPushButton("重新处理全部转录")
        reprocess_btn.clicked.connect(self._on_reprocess_clicked)

        # Scroll area for all content
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.addWidget(model_group)
        content_layout.addWidget(fillers_group)
        content_layout.addWidget(terms_group)
        content_layout.addWidget(save_btn)
        content_layout.addWidget(reprocess_btn)
        content_layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidget(content)
        scroll.setWidgetResizable(True)

        layout = QVBoxLayout(self)
        layout.addWidget(scroll)

    def _load_fillers(self) -> None:
        self._fillers_list.clear()
        p = Path(self._fillers_path)
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    self._fillers_list.addItem(line.strip())

    def _load_terms(self) -> None:
        self._terms_table.setRowCount(0)
        p = Path(self._terms_path)
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            for wrong, correct in data.items():
                row = self._terms_table.rowCount()
                self._terms_table.insertRow(row)
                self._terms_table.setItem(row, 0, QTableWidgetItem(wrong))
                self._terms_table.setItem(row, 1, QTableWidgetItem(correct))

    def _add_filler(self) -> None:
        text, ok = QInputDialog.getText(self, "添加语气词", "语气词：")
        if ok and text.strip():
            self._fillers_list.addItem(text.strip())

    def _remove_filler(self) -> None:
        for item in self._fillers_list.selectedItems():
            self._fillers_list.takeItem(self._fillers_list.row(item))

    def _add_term_row(self) -> None:
        row = self._terms_table.rowCount()
        self._terms_table.insertRow(row)
        self._terms_table.setItem(row, 0, QTableWidgetItem(""))
        self._terms_table.setItem(row, 1, QTableWidgetItem(""))

    def _remove_term_row(self) -> None:
        rows = sorted(
            {i.row() for i in self._terms_table.selectedIndexes()}, reverse=True
        )
        for row in rows:
            self._terms_table.removeRow(row)

    def _save(self) -> None:
        saves = [
            (self._save_settings, "settings TOML"),
            (self._save_fillers, "fillers.txt"),
            (self._save_terms, "buddhist_terms.json"),
        ]
        failed = []
        for fn, label in saves:
            try:
                fn()
            except OSError as e:
                failed.append(f"{label}: {e}")
        if failed:
            QMessageBox.warning(self, "保存失败", "\n".join(failed))
        else:
            QMessageBox.information(self, "已保存", "设置保存成功。")

    def _save_settings(self) -> None:
        existing = Settings.load(self.settings_path)
        new_model = replace(
            existing.model,
            size=self._size_combo.currentText(),
            device=self._device_combo.currentText(),
            language=self._language_edit.text().strip() or "yue",
            beam_size=self._beam_spin.value(),
        )
        new_punc = replace(
            existing.punctuation,
            enabled=self._punc_check.isChecked(),
            model=self._punc_model_edit.text().strip() or "ct-punc",
        )
        Path(self.settings_path).write_text(
            _to_toml(Settings(model=new_model, punctuation=new_punc)), encoding="utf-8"
        )

    def _save_fillers(self) -> None:
        lines = [
            self._fillers_list.item(i).text()
            for i in range(self._fillers_list.count())
        ]
        Path(self._fillers_path).write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _save_terms(self) -> None:
        data: dict[str, str] = {}
        for row in range(self._terms_table.rowCount()):
            wrong_item = self._terms_table.item(row, 0)
            correct_item = self._terms_table.item(row, 1)
            wrong = wrong_item.text().strip() if wrong_item else ""
            correct = correct_item.text().strip() if correct_item else ""
            if wrong and correct:
                data[wrong] = correct
        Path(self._terms_path).write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def _on_reprocess_clicked(self) -> None:
        reply = QMessageBox.question(
            self, "重新处理", "将对所有已转录文件重新运行后处理。是否继续？"
        )
        if reply == QMessageBox.Yes:
            self.reprocess_all_requested.emit()
