import re
from pathlib import Path

from stt.queue import conn_ctx


def init_transcript_db(db_path: str) -> None:
    with conn_ctx(db_path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS transcripts (
                id        INTEGER PRIMARY KEY,
                file_path TEXT NOT NULL,
                date      TEXT NOT NULL,
                text      TEXT NOT NULL
            )
        """)


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
            "SELECT id, file_path, date, text FROM transcripts WHERE text LIKE ? ORDER BY date",
            (f"%{query}%",),
        ).fetchall()
        return [dict(row) for row in rows]


def write_transcript(db_path: str, file_path: str, date: str, text: str) -> None:
    with conn_ctx(db_path) as conn:
        conn.execute(
            "INSERT INTO transcripts (file_path, date, text) VALUES (?, ?, ?)",
            (file_path, date, text),
        )


def get_transcript(db_path: str, file_path: str) -> dict | None:
    with conn_ctx(db_path) as conn:
        row = conn.execute(
            "SELECT id, file_path, date, text FROM transcripts"
            " WHERE file_path = ? ORDER BY id DESC LIMIT 1",
            (file_path,),
        ).fetchone()
        return dict(row) if row else None
