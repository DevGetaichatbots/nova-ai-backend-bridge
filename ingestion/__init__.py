try:
    from .pipeline import IngestionPipeline
except Exception:  # pragma: no cover  — v1 init is best-effort; v2 modules must be importable
    IngestionPipeline = None  # type: ignore[assignment]

__all__ = ["IngestionPipeline"]
