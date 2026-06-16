# STT Pipeline — GUI Design

**Date:** 2026-06-16
**Status:** Approved

---

## Overview

A PySide6 desktop GUI that wraps the existing `stt` backend library. The GUI lets a single local user start and monitor transcription runs, inspect job statuses, search completed transcripts, and edit configuration — without ever touching the CLI or config files by hand.

The backend (`pipeline.py`, `queue.py`, `writer.py`, `config.py`) is unchanged. The GUI is an additional consumer of the same public API already used by `__main__.py`.

---

## Framework

**PySide6** (Qt 6 for Python, LGPL)

- Native desktop look on Windows
- `QThread` + Qt signals map cleanly onto the existing `on_progress` / `on_segment` / `stop_event` callback pattern
- Rich built-in widgets: `QProgressBar`, `QTableView`, `QPlainTextEdit`, `QTabWidget`
- No additional server or browser process required

---

## Entry Point

`python -m stt` with **no subcommand** launches the GUI.
All existing CLI subcommands (`run`, `status`, `retry-failed`, `reset-all`) continue to work unchanged.

`__main__.py` dispatches on `len(sys.argv)`: no args → `gui.app.launch()`; otherwise → existing argparse path.

---

## Window Layout

Single `QMainWindow` with a `QTabWidget` containing four tabs: **Run**, **Jobs**, **Transcripts**, **Config**.

Window title: `STT Pipeline`. Minimum size: 900 × 600.

---

## Tab: Run

**Purpose:** Start and monitor a transcription run.

### Widgets

| Widget | Type | Behaviour |
|--------|------|-----------|
| Input folder | `QLineEdit` + `QPushButton` ("Browse") | Opens `QFileDialog.getExistingDirectory`; last-used path persisted via `QSettings` |
| Start button | `QPushButton` | Disabled while pipeline is running |
| Stop button | `QPushButton` | Enabled while running; sets `stop_event` |
| Queue progress bar | `QProgressBar` | Updated by `on_progress` signal; label shows `done / total files  N failed` |
| File progress bar | `QProgressBar` | Updated by `on_segment` signal; label shows filename + `seconds / total s` |
| Log area | `QPlainTextEdit` (read-only) | Receives log records via a `QtLoggingHandler`; auto-scrolls to bottom |

### Behaviour

1. User picks folder and clicks **Start**.
2. `PipelineWorker` (QThread) is created with the chosen folder, current `Settings`, and a fresh `threading.Event` as `stop_event`.
3. Worker runs `pipeline.run(...)` in its thread, emitting Qt signals on each `on_progress` / `on_segment` callback.
4. Main thread slots update the two progress bars and enable/disable buttons.
5. On **Stop**, `stop_event.set()` is called; the pipeline finishes the current file and exits cleanly.
6. On worker `finished` signal, buttons reset and Jobs tab refreshes.

---

## Tab: Jobs

**Purpose:** Inspect every file's status; trigger retries or full resets.

### Widgets

| Widget | Type | Behaviour |
|--------|------|-----------|
| Jobs table | `QTableView` + `JobTableModel(QAbstractTableModel)` | Columns: Filename, Status, Date, Error |
| Retry Failed button | `QPushButton` | Calls `queue.retry_failed(db)`; refreshes table |
| Reset All button | `QPushButton` | Confirms via `QMessageBox`, then calls `queue.reset_all(db)`; refreshes table |
| Filter box | `QLineEdit` | Client-side substring filter on filename |

### Table model

`JobTableModel` calls `queue.list_jobs(db)` on construction and on `refresh()`. Rows are coloured by status: green for `done`, red for `failed`, grey for `pending`, blue for `in_progress`. Clicking a row with status `done` switches to the Transcripts tab and loads that file's transcript.

Auto-refreshes every 2 seconds while the pipeline worker is active.

---

## Tab: Transcripts

**Purpose:** Search and read completed transcripts.

### Widgets

| Widget | Type | Behaviour |
|--------|------|-----------|
| Search box | `QLineEdit` | Enter or button press triggers search |
| Search button | `QPushButton` | Calls `writer.search_transcripts(db, query)` |
| Results table | `QTableView` + `SearchResultModel` | Columns: Date, Filename, Excerpt (first 80 chars of matching region) |
| Transcript viewer | `QPlainTextEdit` (read-only) | Full transcript of selected result; search term highlighted via `QTextEdit.find` |

### Behaviour

- Empty query returns nothing (does not dump all transcripts).
- Clicking a result row populates the transcript viewer and highlights all occurrences of the search term.
- Results are ordered by date ascending.

---

## Tab: Config

**Purpose:** Edit model settings and correction dictionaries without touching files by hand.

### Sections

#### Model settings

Loads from `Settings.load(config/settings.toml)`. Fields:

| Field | Widget |
|-------|--------|
| Model size | `QComboBox`: `tiny`, `base`, `small`, `medium`, `large-v2`, `large-v3` |
| Device | `QComboBox`: `auto`, `cuda`, `cpu` |
| Language | `QLineEdit` |
| Beam size | `QSpinBox` (1–10) |
| Punctuation enabled | `QCheckBox` |
| Punctuation model | `QLineEdit` (visible only when punctuation enabled) |

Save writes values back to `config/settings.toml` using `tomllib` for reading and manual TOML serialisation for writing (no third-party writer needed given the simple flat structure).

#### Filler words

`QListWidget` populated from `config/fillers.txt`. **Add** opens a `QInputDialog`; **Remove** deletes the selected item. Save writes the list back to `fillers.txt`.

#### Buddhist terms

`QTableWidget` (two columns: Wrong form, Correct form) populated from `config/buddhist_terms.json`. Cells are editable in place. **Add row** appends a blank row; **Remove row** deletes the selected row. Save serialises back to `buddhist_terms.json`.

**Save settings** button at the bottom writes all three sections in sequence: settings TOML first, then fillers, then terms. Each write is independent; a failure mid-sequence shows a `QMessageBox.warning` and leaves the remaining files unchanged.

---

## Threading Model

```
Main thread (Qt event loop)
    │
    ├── PipelineWorker(QThread)
    │       fields: input_dir, db_path, output_dir, config_dir, settings, stop_event
    │       calls:  pipeline.run(...)
    │       emits:  progress(ProgressEvent)   → updates queue bar + job count
    │               segment(SegmentEvent)     → updates file bar
    │               log_record(LogRecord)     → appended to log area
    │               finished()               → resets buttons, refreshes Jobs tab
    │               error(str)               → shows QMessageBox
    │
    └── QtLoggingHandler(logging.Handler)
            installed on the "stt" logger in addition to existing handlers
            emits a Qt signal → appended to QPlainTextEdit on main thread
```

No shared mutable state between threads. All widget updates happen exclusively on the main thread via signal/slot connections.

---

## File Layout

```
stt/
├── gui/
│   ├── __init__.py
│   ├── app.py               ← QApplication setup, launch()
│   ├── main_window.py       ← QMainWindow, QTabWidget, tab wiring
│   ├── run_tab.py           ← Run tab widget
│   ├── jobs_tab.py          ← Jobs tab + JobTableModel
│   ├── transcripts_tab.py   ← Transcripts tab + SearchResultModel
│   ├── config_tab.py        ← Config tab, TOML/JSON save logic
│   └── worker.py            ← PipelineWorker(QThread), QtLoggingHandler
└── __main__.py              ← dispatch: no args → GUI, args → CLI
```

---

## Dependencies

Add to `pyproject.toml`:

```toml
dependencies = [
    ...
    "PySide6",
]
```

No other new dependencies. `PySide6` bundles Qt 6 and is available as a wheel for Windows/Python 3.12.

---

## Error Handling

| Scenario | Behaviour |
|----------|-----------|
| Pipeline raises unexpected exception | Worker emits `error(str)`; main thread shows `QMessageBox.critical` |
| DB not found on Jobs/Transcripts tab | Table shows empty state message: "No database found. Run the pipeline first." |
| Config save fails (permissions) | `QMessageBox.warning` with the OS error message |
| Stop requested | Pipeline finishes current file, then exits; progress bars left at last state |

---

## Testing

GUI code is not unit-tested (widget interaction requires a display). The backend remains fully tested. Manual smoke test checklist:

- [ ] Launch GUI: window opens, all four tabs visible
- [ ] Run tab: browse to `data/`, click Start, observe both progress bars advancing, log lines appearing
- [ ] Stop mid-run: pipeline halts after current file; queue bar frozen; Start re-enables
- [ ] Jobs tab: rows show correct status colours; Retry Failed re-queues failed rows
- [ ] Transcripts tab: search "菩萨" returns results; clicking a row shows full transcript with term highlighted
- [ ] Config tab: change beam size, save, reopen — value persists; add a filler word, save, verify in `fillers.txt`
