from __future__ import annotations


def load_model(model_name: str = "ct-punc"):
    from funasr import AutoModel
    return AutoModel(model=model_name, disable_update=True)


def apply(text: str, model) -> str:
    if not text.strip():
        return text
    result = model.generate(input=text)
    return result[0]["text"] if result else text
