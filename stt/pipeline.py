import threading
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable

from stt import log, postprocess, queue, transcribe, writer
from stt.config import Settings


@dataclass
class ProgressEvent:
    file_path: str
    status: str  # "done" | "failed"
    total: int
    done: int
    failed: int


@dataclass
class SegmentEvent:
    file_path: str
    current_seconds: float
    total_seconds: float


def run(
    input_dir: str,
    db_path: str,
    output_dir: str,
    config_dir: str,
    settings: Settings | None = None,
    stop_event: threading.Event | None = None,
    on_progress: Callable[[ProgressEvent], None] | None = None,
    on_segment: Callable[[SegmentEvent], None] | None = None,
) -> None:
    if settings is None:
        settings = Settings()

    logger = log.get()
    fillers_path = str(Path(config_dir) / "fillers.txt")
    terms_path = str(Path(config_dir) / "buddhist_terms.json")

    if not Path(fillers_path).exists():
        raise FileNotFoundError(f"Fillers config not found: {fillers_path}")
    if not Path(terms_path).exists():
        raise FileNotFoundError(f"Buddhist terms config not found: {terms_path}")

    Path(output_dir).mkdir(parents=True, exist_ok=True)

    queue.init_db(db_path)
    writer.init_transcript_db(db_path)
    new_jobs = queue.scan_and_enqueue(input_dir, db_path)
    queue.reset_stale(db_path)
    counts = queue.status_counts(db_path)
    total = sum(counts.values())
    pending = counts.get("pending", 0)
    logger.info("Queue: %d total jobs, %d pending, %d new", total, pending, new_jobs)

    model = transcribe.load_model(settings)

    while True:
        if stop_event and stop_event.is_set():
            logger.info("Pipeline stopped by request")
            break
        job = queue.next_pending(db_path)
        if job is None:
            break

        job_path = job["file_path"]
        logger.info("Transcribing: %s", Path(job_path).name)

        seg_cb: Callable[[float, float], None] | None = None
        if on_segment:
            def seg_cb(cur: float, tot: float, _path: str = job_path) -> None:
                on_segment(SegmentEvent(file_path=_path, current_seconds=cur, total_seconds=tot))

        job_status = "done"
        try:
            segs = transcribe.transcribe_file(model, job_path, settings, on_segment=seg_cb)
            raw_text = transcribe.segments_to_text(segs)
            clean_text = postprocess.postprocess(raw_text, fillers_path, terms_path)
            date = writer.parse_date(Path(job_path).name)
            writer.write_txt(clean_text, job_path, output_dir)
            writer.write_transcript(db_path, job_path, date, clean_text)
            queue.mark_done(db_path, job["id"])
            logger.info("Done: %s (%d segments)", Path(job_path).name, len(segs))
        except Exception as e:
            if transcribe.is_cuda_oom(e):
                logger.warning("CUDA OOM — switching to CPU for all remaining files")
                del model
                settings = Settings(model=replace(settings.model, device="cpu", compute_type="int8"))
                model = transcribe.load_model(settings)
                queue.reset_stale(db_path)
                continue
            job_status = "failed"
            logger.error("Failed %s: %s", Path(job_path).name, e)
            queue.mark_failed(db_path, job["id"], str(e))

        if on_progress:
            counts = queue.status_counts(db_path)
            on_progress(ProgressEvent(
                file_path=job_path,
                status=job_status,
                total=sum(counts.values()),
                done=counts.get("done", 0),
                failed=counts.get("failed", 0),
            ))

    counts = queue.status_counts(db_path)
    logger.info(
        "Pipeline finished — done: %d, failed: %d, pending: %d",
        counts.get("done", 0),
        counts.get("failed", 0),
        counts.get("pending", 0),
    )
