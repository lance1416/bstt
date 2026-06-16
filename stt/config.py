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
class Settings:
    model: ModelSettings = field(default_factory=ModelSettings)

    @classmethod
    def load(cls, path: str | Path) -> Settings:
        p = Path(path)
        if not p.exists():
            return cls()
        with open(p, "rb") as f:
            data = tomllib.load(f)
        model_data = data.get("model", {})
        return cls(model=ModelSettings(**model_data))

    def with_overrides(self, **kwargs: object) -> Settings:
        """Return a new Settings with non-None kwargs applied to model fields."""
        overrides = {k: v for k, v in kwargs.items() if v is not None}
        return Settings(model=replace(self.model, **overrides)) if overrides else self
