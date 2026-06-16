import argparse
from pathlib import Path

from stt import pipeline, queue

DEFAULT_DB = "stt.db"
DEFAULT_OUTPUT = "output"
DEFAULT_CONFIG = "config"


def _cmd_run(args: argparse.Namespace) -> None:
    def on_progress(event: pipeline.ProgressEvent) -> None:
        name = Path(event.file_path).name
        print(f"[{event.done + event.failed}/{event.total}] {event.status.upper()}: {name}")

    pipeline.run(
        input_dir=args.input,
        db_path=args.db,
        output_dir=args.output,
        config_dir=args.config,
        on_progress=on_progress,
    )
    print("Pipeline complete.")


def _cmd_status(args: argparse.Namespace) -> None:
    counts = queue.status_counts(args.db)
    if not counts:
        print("No jobs found. Run `python -m stt run --input <dir>` first.")
        return
    for status, count in sorted(counts.items()):
        print(f"  {status}: {count}")
    failures = queue.failed_jobs(args.db)
    if failures:
        print("\nFailed files:")
        for job in failures:
            print(f"  {job['file_path']}\n    Error: {job['error']}")


def _cmd_retry(args: argparse.Namespace) -> None:
    n = queue.retry_failed(args.db)
    print(f"Reset {n} failed job(s) to pending.")


def main() -> None:
    parser = argparse.ArgumentParser(prog="stt", description="Cantonese Buddhist STT pipeline")
    parser.add_argument("--db", default=DEFAULT_DB, help="Path to SQLite database")
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="Transcribe MP3s in a directory")
    run_p.add_argument("--input", required=True, help="Directory of MP3 files")
    run_p.add_argument("--output", default=DEFAULT_OUTPUT, help="Output directory for .txt files")
    run_p.add_argument("--config", default=DEFAULT_CONFIG, help="Config directory")
    run_p.set_defaults(func=_cmd_run)

    status_p = sub.add_parser("status", help="Show job queue status")
    status_p.set_defaults(func=_cmd_status)

    retry_p = sub.add_parser("retry-failed", help="Reset failed jobs to pending")
    retry_p.set_defaults(func=_cmd_retry)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
