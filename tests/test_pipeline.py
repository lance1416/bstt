from stt import pipeline, queue, transcribe
from stt.config import ModelSettings, PunctuationSettings, Settings


def test_run_scopes_to_input_dir(tmp_path, monkeypatch):
    """run(dir_A) processes only A's files, even if B was enqueued first."""
    a = tmp_path / "A"
    a.mkdir()
    (a / "a.mp3").write_bytes(b"x")
    b = tmp_path / "B"
    b.mkdir()
    (b / "b.mp3").write_bytes(b"x")

    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "fillers.txt").write_text("", encoding="utf-8")
    (cfg / "buddhist_terms.json").write_text("{}", encoding="utf-8")

    db = str(tmp_path / "stt.db")
    out = str(tmp_path / "out")

    # Enqueue B first: a global queue would grab b.mp3 before a.mp3.
    queue.init_db(db)
    queue.scan_and_enqueue(str(b), db)

    monkeypatch.setattr(transcribe, "load_model", lambda settings: object())
    monkeypatch.setattr(
        transcribe,
        "transcribe_file",
        lambda model, path, settings, on_segment=None: [transcribe.Segment(0.0, 1.0, "hi")],
    )

    settings = Settings(
        model=ModelSettings(size="tiny", language="en"),
        punctuation=PunctuationSettings(enabled=False),
    )
    pipeline.run(input_dir=str(a), db_path=db, output_dir=out, config_dir=str(cfg), settings=settings)

    assert queue.status_counts(db, input_dir=str(a)).get("done") == 1
    assert queue.status_counts(db, input_dir=str(b)).get("pending") == 1
    assert queue.status_counts(db, input_dir=str(b)).get("done", 0) == 0
