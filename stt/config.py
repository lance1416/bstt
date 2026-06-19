from __future__ import annotations

import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path


@dataclass
class ModelSettings:
    size: str = "large-v3"
    device: str = "auto"
    compute_type: str = "auto"
    language: str = "yue"
    vad_filter: bool = True
    beam_size: int = 5

    def resolved_device(self) -> str:
        if self.device != "auto":
            return self.device
        import sys
        if sys.platform == "darwin":
            # CTranslate2 has no Metal backend; Apple Silicon runs whisper via
            # MLX on the GPU instead. CPU is still reachable by setting cpu.
            return "mps"
        try:
            import ctranslate2
            return "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
        except Exception:
            return "cpu"

    def resolved_compute_type(self, device: str) -> str:
        if self.compute_type != "auto":
            return self.compute_type
        return "float16" if device == "cuda" else "int8"


@dataclass
class PunctuationSettings:
    enabled: bool = True
    model: str = "ct-punc"


@dataclass
class Settings:
    model: ModelSettings = field(default_factory=ModelSettings)
    punctuation: PunctuationSettings = field(default_factory=PunctuationSettings)

    @classmethod
    def load(cls, path: str | Path) -> Settings:
        p = Path(path)
        if not p.exists():
            return cls()
        with open(p, "rb") as f:
            data = tomllib.load(f)
        return cls(
            model=ModelSettings(**data.get("model", {})),
            punctuation=PunctuationSettings(**data.get("punctuation", {})),
        )

    def with_overrides(self, **kwargs: object) -> Settings:
        """Return a new Settings with non-None kwargs applied to model fields."""
        overrides = {k: v for k, v in kwargs.items() if v is not None}
        return Settings(
            model=replace(self.model, **overrides) if overrides else self.model,
            punctuation=self.punctuation,
        )
