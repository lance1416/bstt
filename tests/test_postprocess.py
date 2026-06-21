import json
import pytest
from stt import postprocess


@pytest.fixture
def config_dir(tmp_path):
    fillers = tmp_path / "fillers.txt"
    fillers.write_text("嗯\n啊\n哦\n", encoding="utf-8")
    terms = tmp_path / "buddhist_terms.json"
    terms.write_text(
        json.dumps({"浬槃": "涅槃", "般惹": "般若"}, ensure_ascii=False),
        encoding="utf-8",
    )
    return tmp_path


def test_load_fillers(config_dir):
    fillers = postprocess.load_fillers(str(config_dir / "fillers.txt"))
    assert "嗯" in fillers
    assert "啊" in fillers
    assert "" not in fillers


def test_remove_fillers_strips_tokens(config_dir):
    fillers = postprocess.load_fillers(str(config_dir / "fillers.txt"))
    result = postprocess.remove_fillers("嗯今天講嗯佛法啊", fillers)
    assert "嗯" not in result
    assert "啊" not in result
    assert "佛法" in result


def test_remove_fillers_collapses_spaces(config_dir):
    fillers = postprocess.load_fillers(str(config_dir / "fillers.txt"))
    result = postprocess.remove_fillers("a 嗯 b", fillers)
    assert "  " not in result


def test_load_terms(config_dir):
    terms = postprocess.load_terms(str(config_dir / "buddhist_terms.json"))
    assert terms["浬槃"] == "涅槃"


def test_correct_terms_replaces_wrong(config_dir):
    terms = postprocess.load_terms(str(config_dir / "buddhist_terms.json"))
    result = postprocess.correct_terms("浬槃之道般惹波羅蜜", terms)
    assert "涅槃" in result
    assert "浬槃" not in result
    assert "般若" in result
    assert "般惹" not in result


def test_convert_to_simplified():
    # 講 (Traditional) → 讲 (Simplified), 菩薩 → 菩萨
    assert postprocess.convert_to_simplified("講佛法") == "讲佛法"
    assert postprocess.convert_to_simplified("菩薩") == "菩萨"
    assert postprocess.convert_to_simplified("") == ""


def test_postprocess_segments_no_punc_model(config_dir):
    segments = ["嗯浬槃之講道", "般惹波羅蜜啊"]
    result = postprocess.postprocess_segments(
        segments,
        str(config_dir / "fillers.txt"),
        str(config_dir / "buddhist_terms.json"),
    )
    assert "嗯" not in result
    assert "啊" not in result
    assert "涅槃" in result
    assert "般若" in result
    assert "讲" in result      # T2S applied
    assert "講" not in result
    assert "\n" not in result  # segments concatenated without separator


def test_postprocess_segments_with_punc_model(config_dir):
    class FakePuncModel:
        def generate(self, input):
            # Receives the full concatenated text, not individual segments
            return [{"text": input + "。"}]

    segments = ["浬槃之道", "般惹波羅蜜"]
    result = postprocess.postprocess_segments(
        segments,
        str(config_dir / "fillers.txt"),
        str(config_dir / "buddhist_terms.json"),
        punc_model=FakePuncModel(),
    )
    assert "涅槃" in result
    assert "般若" in result
    assert "。" in result
    assert "\n" not in result
    # both segments appear in one combined string
    assert "涅槃之道" in result and "般若波罗蜜" in result


def test_postprocess_segments_empty_list(config_dir):
    result = postprocess.postprocess_segments(
        [],
        str(config_dir / "fillers.txt"),
        str(config_dir / "buddhist_terms.json"),
    )
    assert result == ""


def test_postprocess_segments_filters_blank(config_dir):
    segments = ["嗯", "", "  "]  # all become blank after filler removal
    result = postprocess.postprocess_segments(
        segments,
        str(config_dir / "fillers.txt"),
        str(config_dir / "buddhist_terms.json"),
    )
    assert result == ""
