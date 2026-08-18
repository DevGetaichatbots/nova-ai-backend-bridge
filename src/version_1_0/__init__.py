"""Nova Insight Version 1.0 dashboard formatters, adapters, and diff engine."""

from .diffs import (
    ActivityDiff,
    FieldDiff,
    ValidationIssueVerifier,
    Verifier,
    diff_activities,
)
from .formatters import (
    format_health_v1_as_html,
    format_kemp_v1_as_html,
    format_kemp_predictive_v1_as_html,
    format_predictive_v1_as_html,
    localize_v1_html,
)

__all__ = [
    "ActivityDiff",
    "FieldDiff",
    "ValidationIssueVerifier",
    "Verifier",
    "diff_activities",
    "format_health_v1_as_html",
    "format_kemp_v1_as_html",
    "format_kemp_predictive_v1_as_html",
    "format_predictive_v1_as_html",
    "localize_v1_html",
]
