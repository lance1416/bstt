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
    segments, _ = model.transcribe(file_path, language="yue", vad_filter=True)
    return [Segment(start=s.start, end=s.end, text=s.text) for s in segments]


def segments_to_text(segments: list[Segment]) -> str:
    return "\n".join(s.text.strip() for s in segments if s.text.strip())


def is_cuda_oom(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(k in msg for k in ("cuda out of memory", "cublas_status_alloc_failed", "out of memory", "cudaerror"))
