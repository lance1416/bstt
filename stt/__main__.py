import argparse
import logging
import sys
import warnings
from pathlib import Path

# Suppress SyntaxWarnings from third-party packages (e.g. invalid escape sequences
# in funasr / faster-whisper compiled before Python 3.12 tightened the rules).
warnings.filterwarnings("ignore", category=SyntaxWarning)

from tqdm import tqdm
from tqdm.contrib.logging import logging_redirect_tqdm

from stt import log, pipeline, queue
from stt.config import Settings

DEFAULT_DB = "stt.db"
DEFAULT_OUTPUT = "output"
DEFAULT_CONFIG = "config"
DEFAULT_SETTINGS = "config/settings.toml"


def _cmd_run(args: argparse.Namespace) -> None:
    log.setup(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        log_file=args.log_file,
    )
    if args.force:
        n = queue.reset_all(args.db, args.input)
        log.get().info("--force: reset %d job(s) to pending", n)

    settings = Settings.load(args.settings).with_overrides(
        size=args.model_size,
        device=args.device,
        language=args.language,
        beam_size=args.beam_size,
    )
    log.get().info(
        "Settings — model: %s, device: %s, language: %s, beam_size: %d",
        settings.model.size,
        settings.model.device,
        settings.model.language,
        settings.model.beam_size,
    )

    job_bar = tqdm(
        total=None,
        desc="Queue",
        unit="file",
        position=0,
        leave=True,
        dynamic_ncols=True,
    )
    seg_bar = tqdm(
        total=None,
        desc="File ",
        unit="s",
        position=1,
        leave=False,
        dynamic_ncols=True,
    )

    def on_progress(event: pipeline.ProgressEvent) -> None:
        job_bar.total = event.total
        job_bar.n = event.done + event.failed
        job_bar.set_postfix(done=event.done, failed=event.failed or None)
        job_bar.refresh()
        seg_bar.reset(total=0)
        seg_bar.set_description("File ")

    def on_segment(event: pipeline.SegmentEvent) -> None:
        if seg_bar.total != event.total_seconds:
            seg_bar.reset(total=event.total_seconds)
            seg_bar.set_description(Path(event.file_path).stem[:20])
        seg_bar.n = event.current_seconds
        seg_bar.refresh()

    with logging_redirect_tqdm(loggers=[log.get()]):
        pipeline.run(
            input_dir=args.input,
            db_path=args.db,
            output_dir=args.output,
            config_dir=args.config,
            settings=settings,
            on_progress=on_progress,
            on_segment=on_segment,
        )

    seg_bar.close()
    job_bar.close()


def _cmd_status(args: argparse.Namespace) -> None:
    counts = queue.status_counts(args.db, args.input)
    if not counts:
        print("No jobs found. Run `uv run python -m stt run --input <dir>` first.")
        return
    total = sum(counts.values())
    done = counts.get("done", 0)
    print(f"Progress: {done}/{total} files ({done * 100 // total if total else 0}%)")
    for status, count in sorted(counts.items()):
        print(f"  {status}: {count}")
    failures = queue.failed_jobs(args.db, args.input)
    if failures:
        print(f"\nFailed files ({len(failures)}):")
        for job in failures:
            print(f"  {job['file_path']}\n    Error: {job['error']}")


def _cmd_retry(args: argparse.Namespace) -> None:
    n = queue.retry_failed(args.db, args.input)
    print(f"Reset {n} failed job(s) to pending.")


def _cmd_reprocess(args: argparse.Namespace) -> None:
    log.setup(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        log_file=args.log_file,
    )
    settings = Settings.load(args.settings)
    bar = tqdm(total=None, desc="Reprocess", unit="file", dynamic_ncols=True)

    def on_progress(event: pipeline.ProgressEvent) -> None:
        bar.total = event.total
        bar.n = event.done
        bar.refresh()

    with logging_redirect_tqdm(loggers=[log.get()]):
        pipeline.reprocess(
            db_path=args.db,
            output_dir=args.output,
            config_dir=args.config,
            settings=settings,
            file_path=args.file,
            on_progress=on_progress,
        )
    bar.close()


def main() -> None:
    if len(sys.argv) == 1:
        from stt.gui.app import launch
        launch()
        return

    parser = argparse.ArgumentParser(prog="stt", description="Cantonese Buddhist STT pipeline")
    parser.add_argument("--db", default=DEFAULT_DB, help="Path to SQLite database")
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="Transcribe MP3s in a directory")
    run_p.add_argument("--input", required=True, help="Directory of MP3 files")
    run_p.add_argument("--output", default=DEFAULT_OUTPUT, help="Output directory for .txt files")
    run_p.add_argument("--config", default=DEFAULT_CONFIG, help="Config directory")
    run_p.add_argument("--settings", default=DEFAULT_SETTINGS, metavar="PATH",
                       help=f"Settings TOML file (default: {DEFAULT_SETTINGS})")
    run_p.add_argument("--model-size", default=None, metavar="SIZE",
                       help="Override model size (e.g. large-v3, medium)")
    run_p.add_argument("--device", default=None, choices=["auto", "cuda", "cpu", "mps"],
                       help="Override inference device (mps = Apple Silicon via MLX)")
    run_p.add_argument("--language", default=None, metavar="LANG",
                       help="Override language code (e.g. yue, zh)")
    run_p.add_argument("--beam-size", default=None, type=int, metavar="N",
                       help="Override beam search width")
    run_p.add_argument("--force", action="store_true",
                       help="Re-process already-done files (resets queue before running)")
    run_p.add_argument("--log-file", default=None, metavar="PATH", help="Also write logs to this file")
    run_p.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                       help="Console log level (default: INFO)")
    run_p.set_defaults(func=_cmd_run)

    status_p = sub.add_parser("status", help="Show job queue status")
    status_p.add_argument("--input", default=None, metavar="DIR",
                          help="Scope to jobs under this directory (default: all)")
    status_p.set_defaults(func=_cmd_status)

    retry_p = sub.add_parser("retry-failed", help="Reset failed jobs to pending")
    retry_p.add_argument("--input", default=None, metavar="DIR",
                         help="Scope to jobs under this directory (default: all)")
    retry_p.set_defaults(func=_cmd_retry)

    reprocess_p = sub.add_parser(
        "reprocess",
        help="Re-run post-processing on stored transcriptions (no re-transcribe)",
    )
    reprocess_p.add_argument("--file", default=None, metavar="PATH",
                             help="Reprocess only this stored file path (default: all)")
    reprocess_p.add_argument("--output", default=DEFAULT_OUTPUT, help="Output directory for .txt files")
    reprocess_p.add_argument("--config", default=DEFAULT_CONFIG, help="Config directory")
    reprocess_p.add_argument("--settings", default=DEFAULT_SETTINGS, metavar="PATH",
                             help=f"Settings TOML file (default: {DEFAULT_SETTINGS})")
    reprocess_p.add_argument("--log-file", default=None, metavar="PATH", help="Also write logs to this file")
    reprocess_p.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                             help="Console log level (default: INFO)")
    reprocess_p.set_defaults(func=_cmd_reprocess)

    reset_p = sub.add_parser("reset-all", help="Reset all jobs to pending (re-process everything)")
    reset_p.add_argument("--input", default=None, metavar="DIR",
                         help="Scope to jobs under this directory (default: all)")
    reset_p.set_defaults(func=lambda a: print(f"Reset {queue.reset_all(a.db, a.input)} job(s) to pending."))

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
