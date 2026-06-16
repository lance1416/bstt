import json
import re
from pathlib import Path


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


def postprocess(text: str, fillers_path: str, terms_path: str) -> str:
    fillers = load_fillers(fillers_path)
    terms = load_terms(terms_path)
    text = remove_fillers(text, fillers)
    text = correct_terms(text, terms)
    return text
