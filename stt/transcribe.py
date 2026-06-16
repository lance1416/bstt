from dataclasses import dataclass
from typing import Callable

from faster_whisper import WhisperModel

from stt import log


@dataclass
class Segment:
    start: float
    end: float
    text: str


def load_model(device: str = "cuda") -> WhisperModel:
    log.get().info("Loading Whisper large-v3 on %s", device)
    compute_type = "float16" if device == "cuda" else "int8"
    return WhisperModel("large-v3", device=device, compute_type=compute_type)


def transcribe_file(
    model: WhisperModel,
    file_path: str,
    on_segment: Callable[[float, float], None] | None = None,
) -> list[Segment]:
    segments_iter, info = model.transcribe(file_path, language="yue", vad_filter=True)
    result = []
    for s in segments_iter:
        result.append(Segment(start=s.start, end=s.end, text=s.text))
        if on_segment:
            on_segment(s.end, info.duration)
    return result


def segments_to_text(segments: list[Segment]) -> str:
    return "\n".join(s.text.strip() for s in segments if s.text.strip())


def is_cuda_oom(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(k in msg for k in ("cuda out of memory", "cublas_status_alloc_failed", "out of memory", "cudaerror"))
