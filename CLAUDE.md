# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Speech-to-text pipeline specialized for **Cantonese Buddhist audio**. Transcribes MP3s
with Whisper, then runs a Chinese-text cleanup chain (filler removal → Buddhist-term
correction → Traditional→Simplified conversion → punctuation restoration). Output is one
`.txt` per file plus a searchable SQLite store. Ships both a CLI and a PySide6 GUI.

## Commands

Uses [`uv`](https://docs.astral.sh/uv/) for everything (Python >=3.11).

```bash
uv sync                        # install deps
uv run pytest                  # run all tests
uv run pytest tests/test_postprocess.py::test_correct_terms_replaces_wrong  # single test

# CLI (subcommands under `python -m stt`)
uv run python -m stt run --input <dir>   # transcribe all *.mp3 (recursive) in <dir>
uv run python -m stt status              # queue progress + failed files
uv run python -m stt retry-failed        # reset failed jobs to pending
uv run python -m stt reset-all           # reset every job to pending (re-process)
uv run python -m stt                     # NO args → launches the GUI

# Useful run overrides
uv run python -m stt run --input <dir> --device cpu --model-size medium --force
```

`run` flags override `config/settings.toml` at runtime: `--model-size`, `--device`
(`auto|cuda|cpu|mps`), `--language`, `--beam-size`, `--force` (reset queue first),
`--log-file`, `--log-level`. The end-to-end integration test runs a committed ~11s clip
(`tests/fixtures/2020-0101-jfk.mp3`) through the pipeline with the `tiny` model and
punctuation off; it needs `ffmpeg` on PATH (the Whisper backends shell out to it to decode
audio) and downloads the tiny model on first run.

## Architecture

The pipeline (`stt/pipeline.py:run`) is the spine — both CLI (`stt/__main__.py`) and GUI
(`stt/gui/worker.py`) call it with optional `on_progress`/`on_segment`/`stop_event` hooks.
Per file the flow is:

```
queue.scan_and_enqueue → transcribe.transcribe_file → postprocess.postprocess_segments
  → writer.write_txt + writer.write_transcript → queue.mark_done/mark_failed
```

**Queue (`stt/queue.py`)** — SQLite `jobs` table is the unit of work and the resume
mechanism. Files are enqueued by resolved path (`INSERT OR IGNORE`, so re-scans are
idempotent). `next_pending` uses `BEGIN IMMEDIATE` + flip to `in_progress` for atomic claim;
`reset_stale` reclaims `in_progress` rows left over from a crash on the next run. This is why
the pipeline is interruptible and restartable — never bypass the queue to "just process a file".

**Transcribe backends (`stt/transcribe.py`)** — a `Backend` Protocol with two impls chosen by
`ModelSettings.resolved_device()`:
- `FasterWhisperBackend` (CTranslate2) for CPU/CUDA — supports VAD + beam search, streams segments.
- `MlxWhisperBackend` for Apple Silicon GPU (`mps`) — CTranslate2 has **no Metal backend**, so
  macOS GPU goes through `mlx-whisper`. It is greedy-only (no VAD/beam) and returns all segments
  at once. MLX needs HF-Hub model repos (see `_MLX_REPOS` map), unlike faster-whisper's bare sizes.

On CUDA OOM (`is_cuda_oom`) the pipeline transparently reloads the model on CPU/int8 and
continues — don't add a hard failure path there.

**Postprocess (`stt/postprocess.py`)** — order matters and is deliberate: per-segment
(filler-strip → term-correct → OpenCC `t2s`), then **join**, then punctuate the *whole* text.
Punctuation runs on joined text so the model sees real sentence boundaries instead of Whisper's
time-based cuts. Config comes from `config/fillers.txt` (one token per line) and
`config/buddhist_terms.json` (`{wrong: correct}` map).

**Punctuation (`stt/punctuate.py`)** — optional, via FunASR `ct-punc`. Loading installs a
**torchaudio import stub** (`_TorchaudioFinder`) only when torchaudio is absent, so funasr can
walk its submodules without the dep; the stub is removed after load. Missing `funasr` degrades
gracefully (warns, disables punctuation) — keep it optional.

**Writer (`stt/writer.py`)** — writes the `.txt` and inserts into the `transcripts` SQLite table
(separate from `jobs`, same DB). `parse_date` extracts dates from filenames in `YYYY-MMDD` (e.g.
`2017-1018`) or `YYYY-MM-DD` form. `search_transcripts` powers GUI full-text-ish search via `LIKE`.

**GUI (`stt/gui/`)** — PySide6, four tabs wired in `main_window.py` (Run / Jobs / Transcripts /
Config — UI labels are in Chinese). `PipelineWorker` (`worker.py`) runs `pipeline.run` on a
`QThread`, bridging progress/segment/log via Qt signals and `QtLoggingHandler`; `stop()` sets the
`stop_event` the pipeline polls.

## Config & data

- `config/settings.toml` — model size/device/compute_type, `language` (`yue` Cantonese / `zh`
  Mandarin), VAD, beam size, punctuation toggle. Loaded by `Settings.load`; CLI flags override.
- Default DB `stt.db` (WAL mode), default output dir `output/`, default config dir `config/`.
- `Settings`, `ModelSettings`, `PunctuationSettings` are frozen-ish dataclasses; use
  `with_overrides(...)` (drops `None` values) rather than mutating.

## Platform notes (dependency resolution)

`pyproject.toml` routes torch carefully: CUDA wheels (`pytorch-cu132` index) are pulled **only
off-darwin**; macOS gets MPS-enabled torch from PyPI plus `mlx-whisper`. Editing torch/whisper
deps without preserving these platform markers will break resolution on one OS or the other.
