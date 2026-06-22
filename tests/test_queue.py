import pytest
from pathlib import Path
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


# --- per-directory scoping ---------------------------------------------------


@pytest.fixture
def two_dirs(tmp_path):
    a = tmp_path / "A"
    a.mkdir()
    (a / "a1.mp3").touch()
    (a / "a2.mp3").touch()
    b = tmp_path / "B"
    b.mkdir()
    (b / "b1.mp3").touch()
    return str(a), str(b)


def _enqueue_both(db, dirs):
    a, b = dirs
    queue.scan_and_enqueue(a, db)
    queue.scan_and_enqueue(b, db)


def test_next_pending_scoped_to_dir(tmp_db, two_dirs):
    a, b = two_dirs
    _enqueue_both(tmp_db, two_dirs)
    seen = []
    while (job := queue.next_pending(tmp_db, input_dir=a)) is not None:
        seen.append(job["file_path"])
        queue.mark_done(tmp_db, job["id"])
    assert len(seen) == 2
    assert all(str(Path(a).resolve()) in p for p in seen)
    # B's job was never claimed by the A-scoped loop and is still reachable for B
    jb = queue.next_pending(tmp_db, input_dir=b)
    assert jb is not None and "b1.mp3" in jb["file_path"]


def test_status_counts_scoped(tmp_db, two_dirs):
    a, b = two_dirs
    _enqueue_both(tmp_db, two_dirs)
    assert queue.status_counts(tmp_db, input_dir=a).get("pending") == 2
    assert queue.status_counts(tmp_db, input_dir=b).get("pending") == 1
    assert queue.status_counts(tmp_db).get("pending") == 3  # global


def test_list_jobs_scoped(tmp_db, two_dirs):
    a, b = two_dirs
    _enqueue_both(tmp_db, two_dirs)
    assert len(queue.list_jobs(tmp_db, input_dir=a)) == 2
    assert len(queue.list_jobs(tmp_db, input_dir=b)) == 1
    assert len(queue.list_jobs(tmp_db)) == 3


def test_failed_jobs_scoped(tmp_db, two_dirs):
    a, b = two_dirs
    _enqueue_both(tmp_db, two_dirs)
    jb = queue.next_pending(tmp_db, input_dir=b)
    queue.mark_failed(tmp_db, jb["id"], "err")
    assert queue.failed_jobs(tmp_db, input_dir=a) == []
    fb = queue.failed_jobs(tmp_db, input_dir=b)
    assert len(fb) == 1 and "b1.mp3" in fb[0]["file_path"]


def test_retry_failed_scoped(tmp_db, two_dirs):
    a, b = two_dirs
    _enqueue_both(tmp_db, two_dirs)
    ja = queue.next_pending(tmp_db, input_dir=a)
    queue.mark_failed(tmp_db, ja["id"], "e")
    jb = queue.next_pending(tmp_db, input_dir=b)
    queue.mark_failed(tmp_db, jb["id"], "e")
    assert queue.retry_failed(tmp_db, input_dir=a) == 1
    assert queue.status_counts(tmp_db, input_dir=b).get("failed") == 1  # B untouched


def test_reset_all_scoped(tmp_db, two_dirs):
    a, b = two_dirs
    _enqueue_both(tmp_db, two_dirs)
    ja = queue.next_pending(tmp_db, input_dir=a)
    queue.mark_done(tmp_db, ja["id"])
    queue.reset_all(tmp_db, input_dir=a)
    assert queue.status_counts(tmp_db, input_dir=a).get("pending") == 2
    assert queue.status_counts(tmp_db, input_dir=a).get("done", 0) == 0
    assert queue.status_counts(tmp_db, input_dir=b).get("pending") == 1  # B untouched


def test_reset_stale_scoped(tmp_db, two_dirs):
    a, b = two_dirs
    _enqueue_both(tmp_db, two_dirs)
    queue.next_pending(tmp_db, input_dir=a)  # one A in_progress
    queue.next_pending(tmp_db, input_dir=b)  # one B in_progress
    queue.reset_stale(tmp_db, input_dir=a)
    assert queue.status_counts(tmp_db, input_dir=a).get("in_progress", 0) == 0
    assert queue.status_counts(tmp_db, input_dir=b).get("in_progress", 0) == 1
