import sqlite3
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def _conn(db_path: str):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(db_path: str) -> None:
    with _conn(db_path) as conn:
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
    with _conn(db_path) as conn:
        new_count = 0
        for path in paths:
            cur = conn.execute(
                "INSERT OR IGNORE INTO jobs (file_path) VALUES (?)",
                (str(path.resolve()),),
            )
            new_count += cur.rowcount
        return new_count


def reset_stale(db_path: str) -> None:
    with _conn(db_path) as conn:
        conn.execute(
            "UPDATE jobs SET status='pending', started_at=NULL WHERE status='in_progress'"
        )


def next_pending(db_path: str) -> dict | None:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT id, file_path FROM jobs WHERE status='pending' ORDER BY id LIMIT 1"
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
    with _conn(db_path) as conn:
        conn.execute(
            "UPDATE jobs SET status='done', completed_at=datetime('now') WHERE id=?",
            (job_id,),
        )


def mark_failed(db_path: str, job_id: int, error: str) -> None:
    with _conn(db_path) as conn:
        conn.execute(
            "UPDATE jobs SET status='failed', completed_at=datetime('now'), error=? WHERE id=?",
            (error, job_id),
        )


def retry_failed(db_path: str) -> int:
    with _conn(db_path) as conn:
        cur = conn.execute(
            "UPDATE jobs SET status='pending', error=NULL WHERE status='failed'"
        )
        return cur.rowcount


def status_counts(db_path: str) -> dict[str, int]:
    with _conn(db_path) as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) as count FROM jobs GROUP BY status"
        ).fetchall()
        return {row["status"]: row["count"] for row in rows}


def failed_jobs(db_path: str) -> list[dict]:
    with _conn(db_path) as conn:
        rows = conn.execute(
            "SELECT file_path, error FROM jobs WHERE status='failed'"
        ).fetchall()
        return [{"file_path": row["file_path"], "error": row["error"]} for row in rows]


def list_jobs(db_path: str) -> list[dict]:
    with _conn(db_path) as conn:
        rows = conn.execute(
            "SELECT id, file_path, status, started_at, completed_at, error FROM jobs ORDER BY id"
        ).fetchall()
        return [dict(row) for row in rows]
