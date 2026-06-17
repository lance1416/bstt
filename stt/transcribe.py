from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from faster_whisper import WhisperModel

from stt import log

if TYPE_CHECKING:
    from stt.config import Settings


@dataclass
class Segment:
    start: float
    end: float
    text: str


def load_model(settings: "Settings") -> WhisperModel:
    m = settings.model
    device = m.resolved_device()
    compute_type = m.resolved_compute_type(device)
    log.get().info("Loading Whisper %s on %s (%s)", m.size, device, compute_type)
    return WhisperModel(m.size, device=device, compute_type=compute_type)


def transcribe_file(
    model: WhisperModel,
    file_path: str,
    settings: "Settings",
    on_segment: Callable[[float, float], None] | None = None,
) -> list[Segment]:
    m = settings.model
    segments_iter, info = model.transcribe(
        file_path,
        language=m.language,
        vad_filter=m.vad_filter,
        beam_size=m.beam_size,
    )
    result = []
    for s in segments_iter:
        result.append(Segment(start=s.start, end=s.end, text=s.text))
        if on_segment:
            on_segment(s.end, info.duration)
    return result


def is_cuda_oom(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(k in msg for k in ("cuda out of memory", "cublas_status_alloc_failed", "out of memory", "cudaerror"))
