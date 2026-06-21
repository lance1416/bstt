import argparse
import json
from pathlib import Path

from stt import writer
from stt.transcribe import Segment, segments_to_json


def test_cmd_reprocess_processes_stored(tmp_path):
    from stt.__main__ import _cmd_reprocess

    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "fillers.txt").write_text("嗯\n", encoding="utf-8")
    (cfg / "buddhist_terms.json").write_text(
        json.dumps({"浬槃": "涅槃"}, ensure_ascii=False), encoding="utf-8"
    )
    settings_path = tmp_path / "settings.toml"
    settings_path.write_text("[punctuation]\nenabled = false\n", encoding="utf-8")

    db = str(tmp_path / "stt.db")
    out = str(tmp_path / "output")
    writer.init_transcript_db(db)
    writer.write_transcript(
        db, "/hdd/a.mp3", "2017-10-18", segments_to_json([Segment(0, 1, "嗯浬槃")]), "OLD"
    )

    ns = argparse.Namespace(
        db=db, output=out, config=str(cfg), settings=str(settings_path),
        file=None, log_file=None, log_level="INFO",
    )
    _cmd_reprocess(ns)

    assert writer.get_transcript(db, "/hdd/a.mp3")["text"] == "涅槃"
    assert (Path(out) / "a.txt").exists()
