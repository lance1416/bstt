import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Protocol, cast

from stt import log

if TYPE_CHECKING:
    from faster_whisper import WhisperModel

    from stt.config import Settings


@dataclass
class Segment:
    start: float
    end: float
    text: str


def segments_to_json(segs: list[Segment]) -> str:
    return json.dumps(
        [{"start": s.start, "end": s.end, "text": s.text} for s in segs],
        ensure_ascii=False,
    )


def segments_from_json(s: str) -> list[Segment]:
    data = json.loads(s) if s else []
    return [
        Segment(start=float(d["start"]), end=float(d["end"]), text=str(d["text"]))
        for d in data
    ]


SegmentCallback = Callable[[float, float], None]


class Backend(Protocol):
    """A loaded transcription model. Loaded once, reused across files."""

    def transcribe(
        self,
        file_path: str,
        settings: "Settings",
        on_segment: SegmentCallback | None = None,
    ) -> list[Segment]: ...


class FasterWhisperBackend:
    """CTranslate2-based whisper (CPU / CUDA)."""

    def __init__(self, model: "WhisperModel") -> None:
        self._model = model

    def transcribe(
        self,
        file_path: str,
        settings: "Settings",
        on_segment: SegmentCallback | None = None,
    ) -> list[Segment]:
        m = settings.model
        segments_iter, info = self._model.transcribe(
            file_path,
            language=m.language or None,
            vad_filter=m.vad_filter,
            beam_size=m.beam_size,
        )
        result = []
        for s in segments_iter:
            result.append(Segment(start=s.start, end=s.end, text=s.text))
            if on_segment:
                on_segment(s.end, info.duration)
        return result


# Whisper size -> mlx-community MLX-format repo. faster-whisper accepts bare
# sizes; MLX needs a converted model from the Hub.
_MLX_REPOS = {
    "tiny": "mlx-community/whisper-tiny-mlx",
    "base": "mlx-community/whisper-base-mlx",
    "small": "mlx-community/whisper-small-mlx",
    "medium": "mlx-community/whisper-medium-mlx",
    "large-v2": "mlx-community/whisper-large-v2-mlx",
    "large-v3": "mlx-community/whisper-large-v3-mlx",
    "large-v3-turbo": "mlx-community/whisper-large-v3-turbo",
}


def _mlx_repo(size: str) -> str:
    if "/" in size:  # already an explicit HF repo
        return size
    return _MLX_REPOS.get(size, f"mlx-community/whisper-{size}-mlx")


class MlxWhisperBackend:
    """MLX-based whisper for Apple Silicon GPU (Metal/MPS).

    mlx_whisper.transcribe runs the whole file in one blocking call and caches
    the loaded model internally (keyed by repo), so we only hold the repo id.
    """

    def __init__(self, repo: str) -> None:
        self._repo = repo

    def transcribe(
        self,
        file_path: str,
        settings: "Settings",
        on_segment: SegmentCallback | None = None,
    ) -> list[Segment]:
        import mlx_whisper

        m = settings.model
        # mlx_whisper has no VAD and no beam search (greedy/temperature only),
        # so vad_filter and beam_size from settings don't apply here.
        result = mlx_whisper.transcribe(
            file_path,
            path_or_hf_repo=self._repo,
            language=m.language or None,
        )
        raw = cast("list[dict[str, Any]]", result.get("segments", []))
        # No streaming hook: segments arrive all at once. Use the last segment's
        # end as the total so the progress callback fills correctly.
        total = float(raw[-1]["end"]) if raw else 0.0
        out = []
        for s in raw:
            end = float(s["end"])
            out.append(Segment(start=float(s["start"]), end=end, text=str(s["text"])))
            if on_segment:
                on_segment(end, total)
        return out


def load_model(settings: "Settings") -> Backend:
    m = settings.model
    device = m.resolved_device()
    if device == "mps":
        repo = _mlx_repo(m.size)
        log.get().info("Loading MLX Whisper %s on mps (%s)", m.size, repo)
        return MlxWhisperBackend(repo)

    from faster_whisper import WhisperModel

    compute_type = m.resolved_compute_type(device)
    log.get().info("Loading Whisper %s on %s (%s)", m.size, device, compute_type)
    return FasterWhisperBackend(WhisperModel(m.size, device=device, compute_type=compute_type))


def transcribe_file(
    model: Backend,
    file_path: str,
    settings: "Settings",
    on_segment: SegmentCallback | None = None,
) -> list[Segment]:
    return model.transcribe(file_path, settings, on_segment=on_segment)


def is_cuda_oom(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(k in msg for k in ("cuda out of memory", "cublas_status_alloc_failed", "out of memory", "cudaerror"))
