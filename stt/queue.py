import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path


def _scope(input_dir: str | None) -> tuple[str, list]:
    """Return a ``(sql_fragment, params)`` that restricts to files under input_dir.

    Jobs store resolved absolute paths, so a job belongs to a directory when its
    ``file_path`` is under ``resolve(input_dir) + os.sep``. ``None`` → no filter.
    """
    if input_dir is None:
        return "", []
    base = str(Path(input_dir).resolve())
    if not base.endswith(os.sep):
        base += os.sep
    # Escape LIKE wildcards (\ first, so we don't re-escape our own escapes).
    pattern = base.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    return " AND file_path LIKE ? ESCAPE '\\'", [pattern]


@contextmanager
def conn_ctx(db_path: str):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(db_path: str) -> None:
    with conn_ctx(db_path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id          INTEGER PRIMARY KEY,
                file_path   TEXT UNIQUE NOT NULL,
                status      TEXT NOT NULL DEFAULT 'pending',
                started_at  TEXT,
                completed_at TEXT,
                error       TEXT
            )
        """)


def scan_and_enqueue(input_dir: str, db_path: str) -> int:
    paths = sorted(Path(input_dir).rglob("*.mp3"))
    with conn_ctx(db_path) as conn:
        new_count = 0
        for path in paths:
            cur = conn.execute(
                "INSERT OR IGNORE INTO jobs (file_path) VALUES (?)",
                (str(path.resolve()),),
            )
            new_count += cur.rowcount
        return new_count


def reset_stale(db_path: str, input_dir: str | None = None) -> None:
    clause, params = _scope(input_dir)
    with conn_ctx(db_path) as conn:
        conn.execute(
            "UPDATE jobs SET status='pending', started_at=NULL WHERE status='in_progress'"
            + clause,
            params,
        )


def next_pending(db_path: str, input_dir: str | None = None) -> dict | None:
    clause, params = _scope(input_dir)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT id, file_path FROM jobs WHERE status='pending'"
            + clause
            + " ORDER BY id LIMIT 1",
            params,
        ).fetchone()
        if row is None:
            conn.rollback()
            return None
        conn.execute(
            "UPDATE jobs SET status='in_progress', started_at=datetime('now') WHERE id=?",
            (row["id"],),
        )
        conn.commit()
        return {"id": row["id"], "file_path": row["file_path"]}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def mark_done(db_path: str, job_id: int) -> None:
    with conn_ctx(db_path) as conn:
        conn.execute(
            "UPDATE jobs SET status='done', completed_at=datetime('now') WHERE id=?",
            (job_id,),
        )


def mark_failed(db_path: str, job_id: int, error: str) -> None:
    with conn_ctx(db_path) as conn:
        conn.execute(
            "UPDATE jobs SET status='failed', completed_at=datetime('now'), error=? WHERE id=?",
            (error, job_id),
        )


def retry_failed(db_path: str, input_dir: str | None = None) -> int:
    clause, params = _scope(input_dir)
    with conn_ctx(db_path) as conn:
        cur = conn.execute(
            "UPDATE jobs SET status='pending', error=NULL WHERE status='failed'" + clause,
            params,
        )
        return cur.rowcount


def reset_all(db_path: str, input_dir: str | None = None) -> int:
    clause, params = _scope(input_dir)
    with conn_ctx(db_path) as conn:
        cur = conn.execute(
            "UPDATE jobs SET status='pending', started_at=NULL, completed_at=NULL,"
            " error=NULL WHERE 1=1" + clause,
            params,
        )
        return cur.rowcount


def status_counts(db_path: str, input_dir: str | None = None) -> dict[str, int]:
    clause, params = _scope(input_dir)
    with conn_ctx(db_path) as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) as count FROM jobs WHERE 1=1" + clause + " GROUP BY status",
            params,
        ).fetchall()
        return {row["status"]: row["count"] for row in rows}


def failed_jobs(db_path: str, input_dir: str | None = None) -> list[dict]:
    clause, params = _scope(input_dir)
    with conn_ctx(db_path) as conn:
        rows = conn.execute(
            "SELECT file_path, error FROM jobs WHERE status='failed'" + clause,
            params,
        ).fetchall()
        return [{"file_path": row["file_path"], "error": row["error"]} for row in rows]


def list_jobs(db_path: str, input_dir: str | None = None) -> list[dict]:
    clause, params = _scope(input_dir)
    with conn_ctx(db_path) as conn:
        rows = conn.execute(
            "SELECT id, file_path, status, started_at, completed_at, error FROM jobs"
            " WHERE 1=1" + clause + " ORDER BY id",
            params,
        ).fetchall()
        return [dict(row) for row in rows]
