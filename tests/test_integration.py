import json
import sqlite3
import pytest
from pathlib import Path

from stt import pipeline, queue

SAMPLE_MP3 = Path(__file__).parent.parent / "data" / "2017-1018-zhz.mp3"
CONFIG_DIR = Path(__file__).parent.parent / "config"


@pytest.mark.skipif(not SAMPLE_MP3.exists(), reason="Sample MP3 not available")
def test_full_pipeline(tmp_path):
    db_path = str(tmp_path / "stt.db")
    output_dir = str(tmp_path / "output")

    pipeline.run(
        input_dir=str(SAMPLE_MP3.parent),
        db_path=db_path,
        output_dir=output_dir,
        config_dir=str(CONFIG_DIR),
    )

    # txt file produced with content
    txt_file = Path(output_dir) / "2017-1018-zhz.txt"
    assert txt_file.exists(), "Expected .txt output file not created"
    text = txt_file.read_text(encoding="utf-8")
    assert len(text) > 100, "Transcript is suspiciously short"

    # output is Simplified Chinese — 講 (Traditional) must not appear; 讲 (Simplified) should
    assert "講" not in text, "Traditional character 講 found — T2S conversion did not run"

    # database row inserted and searchable
    conn = sqlite3.connect(db_path)
    rows = conn.execute("SELECT text, date FROM transcripts").fetchall()
    conn.close()
    assert len(rows) == 1
    assert rows[0][1] == "2017-10-18"

    # no wrong Buddhist terms remain in output
    terms = json.loads((CONFIG_DIR / "buddhist_terms.json").read_text(encoding="utf-8"))
    for wrong in terms:
        assert wrong not in text, f"Wrong term '{wrong}' still present in transcript"

    # job queue shows done, no failures
    counts = queue.status_counts(db_path)
    assert counts.get("done", 0) == 1
    assert counts.get("failed", 0) == 0
