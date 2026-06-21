import sqlite3
import pytest
from pathlib import Path
from stt import writer


@pytest.fixture
def tmp_db(tmp_path):
    db = str(tmp_path / "test.db")
    writer.init_transcript_db(db)
    return db


def test_write_txt_creates_file(tmp_path):
    output_dir = str(tmp_path / "output")
    writer.write_txt("佛法無邊", "/hdd/lectures/lecture1.mp3", output_dir)
    txt = Path(output_dir) / "lecture1.txt"
    assert txt.exists()
    assert txt.read_text(encoding="utf-8") == "佛法無邊"


def test_write_txt_creates_output_dir_if_missing(tmp_path):
    output_dir = str(tmp_path / "nested" / "output")
    writer.write_txt("text", "/some/file.mp3", output_dir)
    assert (Path(output_dir) / "file.txt").exists()


def test_write_transcript_inserts_row(tmp_db):
    writer.write_transcript(tmp_db, "/hdd/lecture1.mp3", "2017-10-18", "[]", "佛法無邊")
    conn = sqlite3.connect(tmp_db)
    rows = conn.execute(
        "SELECT text FROM transcripts WHERE text LIKE '%佛法%'"
    ).fetchall()
    conn.close()
    assert len(rows) == 1
    assert "佛法" in rows[0][0]


def test_write_transcript_searchable(tmp_db):
    writer.write_transcript(tmp_db, "/hdd/lecture1.mp3", "2017-10-18", "[]", "般若波羅蜜多")
    writer.write_transcript(tmp_db, "/hdd/lecture2.mp3", "2017-10-19", "[]", "阿彌陀佛")
    conn = sqlite3.connect(tmp_db)
    rows = conn.execute(
        "SELECT file_path FROM transcripts WHERE text LIKE '%般若%'"
    ).fetchall()
    conn.close()
    assert len(rows) == 1
    assert "lecture1" in rows[0][0]


def test_parse_date_yyyy_mmdd():
    assert writer.parse_date("2017-1018-zhz.mp3") == "2017-10-18"


def test_parse_date_yyyy_mm_dd():
    assert writer.parse_date("2020-03-05-lecture.mp3") == "2020-03-05"


def test_parse_date_unknown_returns_empty():
    assert writer.parse_date("unknown_lecture.mp3") == ""


def test_search_transcripts_finds_match(tmp_db):
    writer.write_transcript(tmp_db, "/hdd/a.mp3", "2017-10-18", "[]", "般若波羅蜜多心經")
    writer.write_transcript(tmp_db, "/hdd/b.mp3", "2017-10-19", "[]", "阿彌陀佛聖號")
    results = writer.search_transcripts(tmp_db, "般若")
    assert len(results) == 1
    assert "a.mp3" in results[0]["file_path"]


def test_search_transcripts_no_match(tmp_db):
    writer.write_transcript(tmp_db, "/hdd/a.mp3", "2017-10-18", "[]", "佛法無邊")
    results = writer.search_transcripts(tmp_db, "孔子")
    assert results == []


def test_search_transcripts_ordered_by_date(tmp_db):
    writer.write_transcript(tmp_db, "/hdd/b.mp3", "2017-10-19", "[]", "菩薩行")
    writer.write_transcript(tmp_db, "/hdd/a.mp3", "2017-10-18", "[]", "菩薩戒")
    results = writer.search_transcripts(tmp_db, "菩薩")
    assert results[0]["date"] == "2017-10-18"
    assert results[1]["date"] == "2017-10-19"


def test_write_transcript_upserts_one_row(tmp_db):
    writer.write_transcript(tmp_db, "/hdd/a.mp3", "2017-10-18", "[]", "first")
    writer.write_transcript(tmp_db, "/hdd/a.mp3", "2017-10-18", "[]", "second")
    conn = sqlite3.connect(tmp_db)
    rows = conn.execute(
        "SELECT text FROM transcripts WHERE file_path='/hdd/a.mp3'"
    ).fetchall()
    conn.close()
    assert len(rows) == 1
    assert rows[0][0] == "second"


def test_write_transcript_stores_raw(tmp_db):
    raw = '[{"start": 0.0, "end": 1.0, "text": "x"}]'
    writer.write_transcript(tmp_db, "/hdd/a.mp3", "2017-10-18", raw, "X")
    row = writer.get_transcript(tmp_db, "/hdd/a.mp3")
    assert row["raw_segments"] == raw


def test_list_transcriptions_ordered_by_date(tmp_db):
    writer.write_transcript(tmp_db, "/hdd/b.mp3", "2017-10-19", "[]", "B")
    writer.write_transcript(tmp_db, "/hdd/a.mp3", "2017-10-18", "[]", "A")
    rows = writer.list_transcriptions(tmp_db)
    assert [r["file_path"] for r in rows] == ["/hdd/a.mp3", "/hdd/b.mp3"]
    assert "raw_segments" in rows[0]


def test_init_migrates_old_schema(tmp_path):
    db = str(tmp_path / "old.db")
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE transcripts (id INTEGER PRIMARY KEY, file_path TEXT NOT NULL,"
        " date TEXT NOT NULL, text TEXT NOT NULL)"
    )
    conn.execute(
        "INSERT INTO transcripts (file_path, date, text) VALUES ('/hdd/a.mp3','2017-10-18','V1')"
    )
    conn.execute(
        "INSERT INTO transcripts (file_path, date, text) VALUES ('/hdd/a.mp3','2017-10-18','V2')"
    )
    conn.commit()
    conn.close()

    writer.init_transcript_db(db)  # migrate

    conn = sqlite3.connect(db)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(transcripts)")}
    rows = conn.execute(
        "SELECT text FROM transcripts WHERE file_path='/hdd/a.mp3'"
    ).fetchall()
    conn.close()
    assert "raw_segments" in cols
    assert len(rows) == 1 and rows[0][0] == "V2"  # deduped to newest id

    writer.write_transcript(db, "/hdd/a.mp3", "2017-10-18", "[]", "V3")
    assert writer.get_transcript(db, "/hdd/a.mp3")["text"] == "V3"  # unique index → upsert