try:
    from .ingestion import router
except Exception:  # pragma: no cover
    router = None  # type: ignore[assignment]

__all__ = ["router"]
