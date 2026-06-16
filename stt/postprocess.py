import json
import re
from pathlib import Path

import opencc

_converter: opencc.OpenCC | None = None


def _get_converter() -> opencc.OpenCC:
    global _converter
    if _converter is None:
        _converter = opencc.OpenCC("t2s")
    return _converter


def load_fillers(fillers_path: str) -> list[str]:
    lines = Path(fillers_path).read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip()]


def load_terms(terms_path: str) -> dict[str, str]:
    return json.loads(Path(terms_path).read_text(encoding="utf-8"))


def remove_fillers(text: str, fillers: list[str]) -> str:
    for filler in fillers:
        text = re.sub(re.escape(filler), "", text)
    return re.sub(r" +", " ", text).strip()


def correct_terms(text: str, terms: dict[str, str]) -> str:
    for wrong, correct in terms.items():
        text = text.replace(wrong, correct)
    return text


def convert_to_simplified(text: str) -> str:
    return _get_converter().convert(text)


def postprocess(text: str, fillers_path: str, terms_path: str) -> str:
    fillers = load_fillers(fillers_path)
    terms = load_terms(terms_path)
    text = remove_fillers(text, fillers)
    text = correct_terms(text, terms)
    text = convert_to_simplified(text)
    return text
