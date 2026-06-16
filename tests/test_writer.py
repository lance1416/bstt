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
    writer.write_transcript(tmp_db, "/hdd/lecture1.mp3", "2017-10-18", "佛法無邊")
    conn = sqlite3.connect(tmp_db)
    rows = conn.execute(
        "SELECT text FROM transcripts WHERE transcripts MATCH '佛法'"
    ).fetchall()
    conn.close()
    assert len(rows) == 1
    assert "佛法" in rows[0][0]


def test_write_transcript_fts_searchable(tmp_db):
    writer.write_transcript(tmp_db, "/hdd/lecture1.mp3", "2017-10-18", "般若波羅蜜多")
    writer.write_transcript(tmp_db, "/hdd/lecture2.mp3", "2017-10-19", "阿彌陀佛")
    conn = sqlite3.connect(tmp_db)
    rows = conn.execute(
        "SELECT file_path FROM transcripts WHERE transcripts MATCH '般若'"
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