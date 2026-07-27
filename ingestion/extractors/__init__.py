try:
    from .registry import ExtractorRegistry
except Exception:  # pragma: no cover  — v1 init is best-effort; v2 modules must be importable
    ExtractorRegistry = None  # type: ignore[assignment]
try:
    from .base import BaseExtractor
except Exception:  # pragma: no cover
    BaseExtractor = None  # type: ignore[assignment]

# Auto-register concrete extractors. Best-effort; failures don't block v2.
try:
    import importlib
    for _name in ("csv", "excel", "pdf", "mpp", "mspdi"):
        try:
            importlib.import_module(f".{_name}", package=__name__)
        except Exception:
            pass
except Exception:
    pass

__all__ = ["ExtractorRegistry", "BaseExtractor"]
