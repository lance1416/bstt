import json
import sqlite3

import pytest

from pathlib import Path

from stt import pipeline, queue
from stt.config import ModelSettings, PunctuationSettings, Settings

# Small, well-known public-domain clip (~11s of JFK speech, from whisper.cpp's
# samples) committed as a fixture so the test is offline and deterministic. The
# filename encodes a date so we can verify filename → date parsing.
SAMPLE_MP3 = Path(__file__).parent / "fixtures" / "2020-0101-jfk.mp3"
CONFIG_DIR = Path(__file__).parent.parent / "config"


@pytest.mark.skipif(not SAMPLE_MP3.exists(), reason="Sample MP3 fixture missing")
def test_full_pipeline(tmp_path):
    db_path = str(tmp_path / "stt.db")
    output_dir = str(tmp_path / "output")

    # Run with the smallest model and punctuation off so the test stays fast and
    # hermetic (no large model / no Chinese punctuation model download). This
    # exercises the transcribe → postprocess → write → queue path end to end;
    # the Chinese-specific cleanup passes are covered by the postprocess unit tests.
    # English clip + tiny model: 'yue' (Cantonese) isn't in the tiny tokenizer
    # (it was only added in large-v3), so set the language to match the audio.
    settings = Settings(
        model=ModelSettings(size="tiny", language="en"),
        punctuation=PunctuationSettings(enabled=False),
    )

    pipeline.run(
        input_dir=str(SAMPLE_MP3.parent),
        db_path=db_path,
        output_dir=output_dir,
        config_dir=str(CONFIG_DIR),
        settings=settings,
    )

    # txt produced with real content
    txt_file = Path(output_dir) / "2020-0101-jfk.txt"
    assert txt_file.exists(), "Expected .txt output file not created"
    text = txt_file.read_text(encoding="utf-8")
    assert len(text.strip()) > 20, "Transcript is suspiciously short"
    assert "country" in text.lower(), "Expected JFK clip to mention 'country'"

    # one transcript row, date parsed from the filename, raw segments persisted
    conn = sqlite3.connect(db_path)
    rows = conn.execute("SELECT date, raw_segments FROM transcripts").fetchall()
    conn.close()
    assert len(rows) == 1
    assert rows[0][0] == "2020-01-01"
    segs = json.loads(rows[0][1])
    assert isinstance(segs, list) and segs, "raw_segments should be a non-empty list"
    assert {"start", "end", "text"} <= segs[0].keys()

    # job queue shows done, no failures
    counts = queue.status_counts(db_path)
    assert counts.get("done", 0) == 1
    assert counts.get("failed", 0) == 0
