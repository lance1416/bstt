import logging
from dataclasses import dataclass

from faster_whisper import WhisperModel


@dataclass
class Segment:
    start: float
    end: float
    text: str


def load_model(device: str = "cuda") -> WhisperModel:
    compute_type = "float16" if device == "cuda" else "int8"
    return WhisperModel("large-v3", device=device, compute_type=compute_type)


def transcribe_file(model: WhisperModel, file_path: str) -> list[Segment]:
    try:
        segments, _ = model.transcribe(file_path, language="yue", vad_filter=True)
        return [Segment(start=s.start, end=s.end, text=s.text) for s in segments]
    except RuntimeError as e:
        if "CUDA" not in str(e):
            raise
        logging.warning("CUDA OOM for %s — retrying on CPU (this will be slow)", file_path)
        cpu_model = WhisperModel("large-v3", device="cpu", compute_type="int8")
        segments, _ = cpu_model.transcribe(file_path, language="yue", vad_filter=True)
        return [Segment(start=s.start, end=s.end, text=s.text) for s in segments]


def segments_to_text(segments: list[Segment]) -> str:
    return "\n".join(s.text.strip() for s in segments if s.text.strip())
