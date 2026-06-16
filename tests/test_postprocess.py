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


def test_postprocess_applies_all_passes(config_dir):
    # 嗯/啊 removed, 浬槃→涅槃 corrected, 講→讲 converted to Simplified
    text = "嗯浬槃啊之講道"
    result = postprocess.postprocess(
        text,
        str(config_dir / "fillers.txt"),
        str(config_dir / "buddhist_terms.json"),
    )
    assert "嗯" not in result
    assert "啊" not in result
    assert "涅槃" in result
    assert "讲" in result   # Traditional 講 → Simplified 讲
    assert "講" not in result


def test_postprocess_empty_string(config_dir):
    result = postprocess.postprocess(
        "",
        str(config_dir / "fillers.txt"),
        str(config_dir / "buddhist_terms.json"),
    )
    assert result == ""
