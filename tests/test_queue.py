import pytest
from stt import queue


@pytest.fixture
def tmp_db(tmp_path):
    db = str(tmp_path / "test.db")
    queue.init_db(db)
    return db


@pytest.fixture
def tmp_input(tmp_path):
    d = tmp_path / "input"
    d.mkdir()
    (d / "lecture1.mp3").touch()
    (d / "lecture2.mp3").touch()
    return str(d)


def test_scan_enqueues_mp3s(tmp_db, tmp_input):
    count = queue.scan_and_enqueue(tmp_input, tmp_db)
    assert count == 2


def test_scan_is_idempotent(tmp_db, tmp_input):
    queue.scan_and_enqueue(tmp_input, tmp_db)
    count = queue.scan_and_enqueue(tmp_input, tmp_db)
    assert count == 0


def test_next_pending_returns_job(tmp_db, tmp_input):
    queue.scan_and_enqueue(tmp_input, tmp_db)
    job = queue.next_pending(tmp_db)
    assert job is not None
    assert "file_path" in job
    assert "id" in job


def test_next_pending_marks_in_progress(tmp_db, tmp_input):
    queue.scan_and_enqueue(tmp_input, tmp_db)
    queue.next_pending(tmp_db)
    counts = queue.status_counts(tmp_db)
    assert counts.get("in_progress", 0) == 1


def test_next_pending_returns_none_when_empty(tmp_db):
    result = queue.next_pending(tmp_db)
    assert result is None


def test_mark_done(tmp_db, tmp_input):
    queue.scan_and_enqueue(tmp_input, tmp_db)
    job = queue.next_pending(tmp_db)
    queue.mark_done(tmp_db, job["id"])
    counts = queue.status_counts(tmp_db)
    assert counts.get("done", 0) == 1


def test_mark_failed(tmp_db, tmp_input):
    queue.scan_and_enqueue(tmp_input, tmp_db)
    job = queue.next_pending(tmp_db)
    queue.mark_failed(tmp_db, job["id"], "some error")
    counts = queue.status_counts(tmp_db)
    assert counts.get("failed", 0) == 1


def test_reset_stale(tmp_db, tmp_input):
    queue.scan_and_enqueue(tmp_input, tmp_db)
    queue.next_pending(tmp_db)  # leaves one in_progress
    queue.reset_stale(tmp_db)
    counts = queue.status_counts(tmp_db)
    assert counts.get("in_progress", 0) == 0
    assert counts.get("pending", 0) == 2


def test_retry_failed(tmp_db, tmp_input):
    queue.scan_and_enqueue(tmp_input, tmp_db)
    job = queue.next_pending(tmp_db)
    queue.mark_failed(tmp_db, job["id"], "err")
    n = queue.retry_failed(tmp_db)
    assert n == 1
    counts = queue.status_counts(tmp_db)
    assert counts.get("pending", 0) == 2


def test_failed_jobs_lists_errors(tmp_db, tmp_input):
    queue.scan_and_enqueue(tmp_input, tmp_db)
    job = queue.next_pending(tmp_db)
    queue.mark_failed(tmp_db, job["id"], "decode error")
    failures = queue.failed_jobs(tmp_db)
    assert len(failures) == 1
    assert failures[0]["error"] == "decode error"


def test_list_jobs_returns_all(tmp_db, tmp_input):
    queue.scan_and_enqueue(tmp_input, tmp_db)
    jobs = queue.list_jobs(tmp_db)
    assert len(jobs) == 2
    assert all(j["status"] == "pending" for j in jobs)
    assert all("file_path" in j for j in jobs)


def test_list_jobs_reflects_status_changes(tmp_db, tmp_input):
    queue.scan_and_enqueue(tmp_input, tmp_db)
    job = queue.next_pending(tmp_db)
    queue.mark_done(tmp_db, job["id"])
    jobs = queue.list_jobs(tmp_db)
    statuses = {j["file_path"]: j["status"] for j in jobs}
    assert statuses[job["file_path"]] == "done"
