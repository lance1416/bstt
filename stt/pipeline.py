import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from stt import postprocess, queue, transcribe, writer


@dataclass
class ProgressEvent:
    file_path: str
    status: str  # "done" | "failed"
    total: int
    done: int
    failed: int


def run(
    input_dir: str,
    db_path: str,
    output_dir: str,
    config_dir: str,
    on_progress: Callable[[ProgressEvent], None] | None = None,
) -> None:
    fillers_path = str(Path(config_dir) / "fillers.txt")
    terms_path = str(Path(config_dir) / "buddhist_terms.json")

    if not Path(fillers_path).exists():
        raise FileNotFoundError(f"Fillers config not found: {fillers_path}")
    if not Path(terms_path).exists():
        raise FileNotFoundError(f"Buddhist terms config not found: {terms_path}")

    Path(output_dir).mkdir(parents=True, exist_ok=True)

    queue.init_db(db_path)
    writer.init_transcript_db(db_path)
    queue.scan_and_enqueue(input_dir, db_path)
    queue.reset_stale(db_path)

    model = transcribe.load_model()

    while True:
        job = queue.next_pending(db_path)
        if job is None:
            break

        job_status = "done"
        try:
            segments = transcribe.transcribe_file(model, job["file_path"])
            raw_text = transcribe.segments_to_text(segments)
            clean_text = postprocess.postprocess(raw_text, fillers_path, terms_path)
            date = writer.parse_date(Path(job["file_path"]).name)
            writer.write_txt(clean_text, job["file_path"], output_dir)
            writer.write_transcript(db_path, job["file_path"], date, clean_text)
            queue.mark_done(db_path, job["id"])
        except Exception as e:
            job_status = "failed"
            logging.error("Failed %s: %s", job["file_path"], e)
            queue.mark_failed(db_path, job["id"], str(e))

        if on_progress:
            counts = queue.status_counts(db_path)
            on_progress(ProgressEvent(
                file_path=job["file_path"],
                status=job_status,
                total=sum(counts.values()),
                done=counts.get("done", 0),
                failed=counts.get("failed", 0),
            ))
