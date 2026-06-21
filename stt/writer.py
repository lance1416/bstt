import re
from pathlib import Path

from stt.queue import conn_ctx


def init_transcript_db(db_path: str) -> None:
    with conn_ctx(db_path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS transcripts (
                id           INTEGER PRIMARY KEY,
                file_path    TEXT NOT NULL,
                date         TEXT NOT NULL,
                raw_segments TEXT,
                text         TEXT NOT NULL
            )
        """)
        cols = {row["name"] for row in conn.execute("PRAGMA table_info(transcripts)")}
        if "raw_segments" not in cols:
            conn.execute("ALTER TABLE transcripts ADD COLUMN raw_segments TEXT")
            # Dedupe legacy rows (one row per file): keep the newest id per file_path.
            conn.execute("""
                DELETE FROM transcripts
                WHERE id NOT IN (SELECT MAX(id) FROM transcripts GROUP BY file_path)
            """)
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_transcripts_file_path"
            " ON transcripts(file_path)"
        )


def parse_date(filename: str) -> str:
    # Match YYYY-MMDD pattern (e.g. 2017-1018)
    m = re.search(r"(\d{4})-(\d{2})(\d{2})", filename)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    # Match YYYY-MM-DD pattern
    m = re.search(r"(\d{4}-\d{2}-\d{2})", filename)
    if m:
        return m.group(1)
    return ""


def write_txt(text: str, source_path: str, output_dir: str) -> str:
    source = Path(source_path)
    out = Path(output_dir) / source.with_suffix(".txt").name
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    return str(out)


def search_transcripts(db_path: str, query: str) -> list[dict]:
    with conn_ctx(db_path) as conn:
        rows = conn.execute(
            "SELECT file_path, date, text FROM transcripts WHERE text LIKE ? ORDER BY date",
            (f"%{query}%",),
        ).fetchall()
        return [dict(row) for row in rows]


def write_transcript(
    db_path: str, file_path: str, date: str, raw_segments: str, text: str
) -> None:
    with conn_ctx(db_path) as conn:
        conn.execute(
            """
            INSERT INTO transcripts (file_path, date, raw_segments, text)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(file_path) DO UPDATE SET
                date=excluded.date,
                raw_segments=excluded.raw_segments,
                text=excluded.text
            """,
            (file_path, date, raw_segments, text),
        )


def list_transcriptions(db_path: str) -> list[dict]:
    with conn_ctx(db_path) as conn:
        rows = conn.execute(
            "SELECT file_path, date, raw_segments FROM transcripts ORDER BY date"
        ).fetchall()
        return [dict(row) for row in rows]


def get_transcript(db_path: str, file_path: str) -> dict | None:
    with conn_ctx(db_path) as conn:
        row = conn.execute(
            "SELECT id, file_path, date, raw_segments, text FROM transcripts"
            " WHERE file_path = ? LIMIT 1",
            (file_path,),
        ).fetchone()
        return dict(row) if row else None
