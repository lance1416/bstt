import json
from pathlib import Path

import pytest

from stt import pipeline, writer
from stt.config import ModelSettings, PunctuationSettings, Settings
from stt.transcribe import Segment, segments_to_json


@pytest.fixture
def config_dir(tmp_path):
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "fillers.txt").write_text("嗯\n啊\n", encoding="utf-8")
    (cfg / "buddhist_terms.json").write_text(
        json.dumps({"浬槃": "涅槃"}, ensure_ascii=False), encoding="utf-8"
    )
    return cfg


def _settings_no_punc():
    return Settings(model=ModelSettings(), punctuation=PunctuationSettings(enabled=False))


def test_reprocess_applies_updated_terms(tmp_path, config_dir):
    db = str(tmp_path / "stt.db")
    out = str(tmp_path / "output")
    writer.init_transcript_db(db)
    raw = segments_to_json([Segment(0.0, 1.0, "嗯浬槃")])
    writer.write_transcript(db, "/hdd/a.mp3", "2017-10-18", raw, "OLD")

    pipeline.reprocess(db, out, str(config_dir), settings=_settings_no_punc())

    row = writer.get_transcript(db, "/hdd/a.mp3")
    assert row["text"] == "涅槃"          # 嗯 removed, 浬槃→涅槃
    assert row["raw_segments"] == raw      # raw untouched
    assert (Path(out) / "a.txt").read_text(encoding="utf-8") == "涅槃"


def test_reprocess_single_file_scope(tmp_path, config_dir):
    db = str(tmp_path / "stt.db")
    out = str(tmp_path / "output")
    writer.init_transcript_db(db)
    writer.write_transcript(
        db, "/hdd/a.mp3", "2017-10-18", segments_to_json([Segment(0, 1, "浬槃")]), "OLD_A"
    )
    writer.write_transcript(
        db, "/hdd/b.mp3", "2017-10-19", segments_to_json([Segment(0, 1, "浬槃")]), "OLD_B"
    )

    pipeline.reprocess(
        db, out, str(config_dir), settings=_settings_no_punc(), file_path="/hdd/a.mp3"
    )

    assert writer.get_transcript(db, "/hdd/a.mp3")["text"] == "涅槃"
    assert writer.get_transcript(db, "/hdd/b.mp3")["text"] == "OLD_B"  # untouched


def test_reprocess_skips_rows_without_raw(tmp_path, config_dir):
    db = str(tmp_path / "stt.db")
    out = str(tmp_path / "output")
    writer.init_transcript_db(db)
    writer.write_transcript(db, "/hdd/a.mp3", "2017-10-18", "", "OLD")  # no raw stored

    pipeline.reprocess(db, out, str(config_dir), settings=_settings_no_punc())

    assert writer.get_transcript(db, "/hdd/a.mp3")["text"] == "OLD"  # unchanged
