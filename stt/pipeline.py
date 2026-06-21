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


def _load_punc_model(settings: Settings):
    if not settings.punctuation.enabled:
        return None
    logger = log.get()
    try:
        from stt import punctuate
        logger.info("Loading punctuation model: %s", settings.punctuation.model)
        return punctuate.load_model(settings.punctuation.model)
    except ImportError:
        logger.warning("funasr not installed — punctuation disabled. Install with: uv add funasr")
    except Exception as e:
        logger.warning("Punctuation model failed to load (%s) — disabled. %s", type(e).__name__, e)
    return None


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

    # Emit the queue total up front (before the slow model load) so progress
    # consumers can show a determinate bar instead of a busy spinner while the
    # first file is still being transcribed.
    if on_progress:
        on_progress(ProgressEvent(
            file_path="",
            status="",
            total=total,
            done=counts.get("done", 0),
            failed=counts.get("failed", 0),
        ))

    model = transcribe.load_model(settings)

    punc_model = _load_punc_model(settings)

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
            clean_text = postprocess.postprocess_segments(
                [s.text for s in segs], fillers_path, terms_path, punc_model=punc_model
            )
            date = writer.parse_date(Path(job_path).name)
            raw_json = transcribe.segments_to_json(segs)
            writer.write_txt(clean_text, job_path, output_dir)
            writer.write_transcript(db_path, job_path, date, raw_json, clean_text)
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


def reprocess(
    db_path: str,
    output_dir: str,
    config_dir: str,
    settings: Settings | None = None,
    file_path: str | None = None,
    stop_event: threading.Event | None = None,
    on_progress: Callable[[ProgressEvent], None] | None = None,
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
    writer.init_transcript_db(db_path)

    if file_path:
        row = writer.get_transcript(db_path, file_path)
        rows = [row] if row else []
    else:
        rows = writer.list_transcriptions(db_path)

    punc_model = _load_punc_model(settings)

    total = len(rows)
    done = 0
    for row in rows:
        if stop_event and stop_event.is_set():
            logger.info("Reprocess stopped by request")
            break
        fp = row["file_path"]
        raw = row.get("raw_segments")
        if not raw:
            logger.warning(
                "Skipping %s — no raw segments stored (re-transcribe needed)",
                Path(fp).name,
            )
            continue
        segs = transcribe.segments_from_json(raw)
        clean_text = postprocess.postprocess_segments(
            [s.text for s in segs], fillers_path, terms_path, punc_model=punc_model
        )
        writer.write_txt(clean_text, fp, output_dir)
        writer.write_transcript(db_path, fp, row["date"], raw, clean_text)
        done += 1
        logger.info("Reprocessed: %s", Path(fp).name)
        if on_progress:
            on_progress(ProgressEvent(
                file_path=fp, status="done", total=total, done=done, failed=0
            ))

    logger.info("Reprocess finished — %d processed", done)
