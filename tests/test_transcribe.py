from stt.transcribe import Segment, segments_from_json, segments_to_json


def test_segments_json_round_trip():
    segs = [Segment(0.0, 1.5, "你好"), Segment(1.5, 3.0, "世界")]
    restored = segments_from_json(segments_to_json(segs))
    assert restored == segs


def test_segments_to_json_keeps_chinese_readable():
    out = segments_to_json([Segment(0.0, 1.0, "佛法")])
    assert "佛法" in out  # ensure_ascii=False


def test_segments_from_json_empty():
    assert segments_from_json("") == []
    assert segments_from_json("[]") == []
