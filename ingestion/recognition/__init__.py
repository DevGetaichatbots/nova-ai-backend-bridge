try:
    from .heuristics import HeuristicRecognizer
    from .ai_fallback import AIFallbackRecognizer
except Exception:  # pragma: no cover
    pass

__all__ = ["HeuristicRecognizer", "AIFallbackRecognizer"]
