from __future__ import annotations
import importlib.abc
import importlib.machinery
import sys
import types


class _StubModule(types.ModuleType):
    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.__dict__.update(
            __file__=None,
            __path__=[],
            __package__=name.split(".")[0],
            __spec__=None,
            __loader__=None,
        )

    def __getattr__(self, name: str) -> "_StubModule":
        # Dunder attributes that don't exist should raise AttributeError so that
        # Python introspection (hasattr, functools.unwrap, etc.) works correctly.
        # Without this, functools.unwrap follows __wrapped__ → stub → __wrapped__
        # forever and raises "ValueError: wrapper loop when unwrapping".
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        full = f"{self.__name__}.{name}"
        if full not in sys.modules:
            sub = _StubModule(full)
            sys.modules[full] = sub
        return sys.modules[full]  # type: ignore[return-value]

    def __call__(self, *args, **kwargs):
        return self


class _TorchaudioFinder(importlib.abc.MetaPathFinder):
    """Intercepts all torchaudio.* imports and returns stub modules.

    Installed only when torchaudio is absent. Removed after funasr loads
    so it doesn't interfere with anything else.
    """

    class _Loader(importlib.abc.Loader):
        def create_module(self, spec: importlib.machinery.ModuleSpec):
            if spec.name not in sys.modules:
                sys.modules[spec.name] = _StubModule(spec.name)
            return sys.modules[spec.name]

        def exec_module(self, module: types.ModuleType) -> None:
            pass

    def find_spec(self, fullname: str, path, target=None):
        if fullname == "torchaudio" or fullname.startswith("torchaudio."):
            return importlib.machinery.ModuleSpec(fullname, self._Loader())
        return None


def _install_torchaudio_stub() -> bool:
    """Return True if a stub was installed (torchaudio was absent)."""
    try:
        import torchaudio  # noqa: F401
        return False
    except ImportError:
        finder = _TorchaudioFinder()
        sys.meta_path.insert(0, finder)
        sys.modules["torchaudio"] = _StubModule("torchaudio")
        return True


def load_model(model_name: str = "ct-punc"):
    stubbed = _install_torchaudio_stub()
    import torch  # noqa: F401  must be fully initialised before funasr walks its submodules
    try:
        from funasr import AutoModel
        return AutoModel(model=model_name, disable_update=True)
    finally:
        if stubbed:
            sys.meta_path[:] = [f for f in sys.meta_path if not isinstance(f, _TorchaudioFinder)]


def apply(text: str, model) -> str:
    if not text.strip():
        return text
    result = model.generate(input=text)
    return result[0]["text"] if result else text
