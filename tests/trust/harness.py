"""
Trust-layer regression harness (TL-0.1 / TL-0.2 / TL-0.3).

Loads the synthetic fixture corpus and runs it through the deterministic
facts-producing paths the trust programme cares about, returning normalized,
diffable result dicts — never rendered HTML, never LLM prose (brief §36:
"snapshot the facts, not the HTML").

Offline only. Every fixture here is synthetic CSV/MSPDI text with a known
ground truth. Nothing in this module calls Azure OCR or an LLM — that is a
structural property, not a convention: run_health()/run_predictive() only
ever call ingestion.pipeline (extractor + heuristic recognizer + normalizer +
validator) and src.experimental.nusf_compare_engine, none of which make a
network call for the header shapes used in fixtures/. A fixture that
genuinely needs Azure OCR (e.g. a real scanned PDF) must set
"requires_azure": true in its ground_truth.json; load_fixtures() skips those
by default.

CLI:
    python -m tests.trust.harness baseline   # snapshot current output (TL-0.2)
    python -m tests.trust.harness compare    # diff against the baseline (TL-0.3 — not yet implemented)
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from ingestion.pipeline import IngestionPipeline, PipelineError
from ingestion.normalization.engine import to_nusf_chunks
from ingestion.models.nusf import NormalizedSchedule
from src.experimental.nusf_compare_engine import compare_nusf_chunks
from src.trust.claims import (
    UnsupportedClaimMetric,
    collect_unsupported_claims,
    compute_unsupported_claim_metric,
    verify_narrative,
)

logger = logging.getLogger(__name__)

_MISSING = object()  # sentinel: key absent from one side of a diff

FIXTURES_DIR = Path(__file__).parent / "fixtures"
BASELINES_DIR = Path(__file__).parent / "baselines"


@dataclass(frozen=True)
class Fixture:
    """One synthetic fixture: an old/new schedule pair (or a single file for
    fixtures that exercise ingestion in isolation), plus its ground truth."""

    id: str
    dir: Path
    kind: str  # "pair" | "single"
    reference_date: str
    ground_truth: dict[str, Any]
    requires_azure: bool = False

    @property
    def old_path(self) -> Optional[Path]:
        matches = sorted(self.dir.glob("old.*"))
        return matches[0] if matches else None

    @property
    def new_path(self) -> Optional[Path]:
        matches = sorted(self.dir.glob("new.*"))
        return matches[0] if matches else None


def load_fixtures(include_azure: bool = False) -> list[Fixture]:
    """Discover every fixture under fixtures/<id>/ground_truth.json.

    Returns fixtures sorted by directory name (stable, deterministic order).
    By default skips any fixture whose ground_truth declares
    ``"requires_azure": true`` — see module docstring.
    """
    fixtures: list[Fixture] = []
    for gt_path in sorted(FIXTURES_DIR.glob("*/ground_truth.json")):
        gt = json.loads(gt_path.read_text(encoding="utf-8"))
        requires_azure = bool(gt.get("requires_azure", False))
        if requires_azure and not include_azure:
            continue
        fixtures.append(
            Fixture(
                id=gt_path.parent.name,
                dir=gt_path.parent,
                kind=gt.get("kind", "pair"),
                reference_date=gt.get("reference_date", "Unknown"),
                ground_truth=gt,
                requires_azure=requires_azure,
            )
        )
    return fixtures


def _ingest(path: Path) -> tuple[Optional[NormalizedSchedule], list[dict], Optional[str]]:
    """Run a single file through the ingestion pipeline.

    Never raises. A ``PipelineError`` is an expected, first-class *result*
    for some fixtures (e.g. the empty/headers-only case) — not a harness
    failure — so it is returned as a string, not propagated.
    """
    pipeline = IngestionPipeline()
    try:
        schedule, _raw_chunks = pipeline.run(path)
    except PipelineError as exc:
        return None, [], str(exc)
    chunks = to_nusf_chunks(schedule) if schedule.activities else []
    return schedule, chunks, None


def _issue_summary(schedule: Optional[NormalizedSchedule]) -> Optional[dict[str, Any]]:
    if schedule is None:
        return None
    return {
        "activity_count": len(schedule.activities),
        "validation_passed": schedule.validation_passed,
        "issue_count": len(schedule.validation_issues),
        "issue_levels": sorted(i.level for i in schedule.validation_issues),
        "issue_rules": sorted({i.message.split(":")[0] for i in schedule.validation_issues}),
        # Activities normalization auto-corrected (e.g. swapped an inverted
        # start/finish pair) — tracked separately from validation_issues
        # because rule 101 checks *post*-swap state and can therefore never
        # see what this counts. See fixtures/07_data_quality_conflicts.
        "logic_warning_count": sum(1 for a in schedule.activities if a.has_logic_warning),
    }


def _strip_non_deterministic(comparison: dict[str, Any]) -> dict[str, Any]:
    """Drop keys that add snapshot noise without adding regression signal.

    compare_nusf_chunks() never emits LLM prose or UUIDs/timestamps, so
    nothing here is non-deterministic in the literal sense — but
    ``_activity_index`` duplicates progress_vs_expected/point_of_no_return
    at per-activity granularity, roughly doubling snapshot size for no
    additional regression-detection value the aggregate views don't already
    give (TL-0.2's "snapshot the facts, not the HTML" rationale).
    """
    return {k: v for k, v in comparison.items() if k != "_activity_index"}


def run_health(fixture: Fixture) -> dict[str, Any]:
    """Run a fixture through ingestion + the deterministic comparison engine
    (brief §4, §12-§15: the DETERMINISTIC DATA LAYER). No LLM involved.

    Returns a JSON-serializable dict of facts only: activity counts, per-side
    validation summaries, and — when both sides ingest successfully — the
    full deterministic comparison (matches, added/removed, KPI values,
    per-activity dates/progress/status) from compare_nusf_chunks().
    """
    old_schedule, old_chunks, old_error = (
        (None, [], None) if fixture.old_path is None else _ingest(fixture.old_path)
    )
    new_schedule, new_chunks, new_error = (
        (None, [], None) if fixture.new_path is None else _ingest(fixture.new_path)
    )

    result: dict[str, Any] = {
        "fixture_id": fixture.id,
        "old_pipeline_error": old_error,
        "new_pipeline_error": new_error,
        "old_schedule": _issue_summary(old_schedule),
        "new_schedule": _issue_summary(new_schedule),
        "comparison": None,
    }

    # No comparison to make: a single-file fixture, a side that failed to
    # ingest, or a side that produced zero activities. All are legitimate,
    # diffable outcomes on their own — forcing a comparison here would hide
    # them behind a crash instead of a fact.
    if fixture.kind != "pair" or old_error or new_error or not old_chunks or not new_chunks:
        return result

    comparison = compare_nusf_chunks(old_chunks, new_chunks, fixture.reference_date)
    result["comparison"] = _strip_non_deterministic(comparison)
    return result


def run_predictive(fixture: Fixture) -> dict[str, Any]:
    """Phase-0 placeholder predictive facts.

    There is currently no deterministic predictive fact layer in the
    pipeline: src/predictive_agent.py asks an LLM to invent the entire
    delayed-activity list, root causes, and priorities from a text context —
    exactly the anti-pattern Phase 5 (TL-5.1..TL-5.6) exists to remove
    (brief §4, §15). Calling that here would violate this harness's offline
    requirement (TL-0.1 "Do") and would not be reproducible for baseline
    snapshotting (TL-0.2 requires byte-identical output on a second run).

    Until TL-5.1 lands, this projects the same deterministic facts
    run_health() already computes into the shape a predictive-facts consumer
    needs: which activities are behind, how severely, and where. It is
    intentionally a read of run_health()'s own output, not a separate
    computation, so it cannot disagree with the health engine — and it gives
    Phase 5 a concrete baseline to diff its real deterministic engine
    against once one exists.
    """
    health = run_health(fixture)
    comparison = health.get("comparison")
    if comparison is None:
        return {"fixture_id": fixture.id, "predictive_facts": None}

    summary = comparison.get("executive_summary", {})
    ponr = comparison.get("point_of_no_return", [])
    behind = [
        item for item in comparison.get("progress_vs_expected", [])
        if item.get("status") == "behind"
    ]

    return {
        "fixture_id": fixture.id,
        "predictive_facts": {
            "delayed_count": summary.get("behind_schedule_count", 0),
            "critical_count": summary.get("critical_count", 0),
            "point_of_no_return_red_count": sum(
                1 for i in ponr if str(i.get("classification", "")).upper() == "RED"
            ),
            "point_of_no_return_yellow_count": sum(
                1 for i in ponr if str(i.get("classification", "")).upper() == "YELLOW"
            ),
            "delayed_areas": sorted(
                {
                    item.get("location", {}).get("area", "")
                    for item in behind
                    if item.get("location", {}).get("area")
                }
            ),
        },
    }


# --------------------------------------------------------------------------
# Baseline snapshotting (TL-0.2)
# --------------------------------------------------------------------------

def _fixture_snapshot(fixture: Fixture) -> dict[str, Any]:
    """The full, deterministic snapshot for one fixture: both facts-producing
    paths, keyed so a diff points straight at what changed."""
    return {
        "fixture_id": fixture.id,
        "health": run_health(fixture),
        "predictive": run_predictive(fixture),
    }


def write_baselines(fixtures: Optional[list[Fixture]] = None) -> list[Path]:
    """Run every offline fixture through both facts-producing paths and write
    one deterministic JSON snapshot per fixture to BASELINES_DIR.

    Snapshots are the facts, not the HTML (brief §36) — run_health()/
    run_predictive() already exclude timestamps, UUIDs, and LLM prose by
    construction (see their docstrings), so nothing further needs stripping
    here. Any baseline file left over from a fixture that no longer exists in
    fixtures/ is removed, so BASELINES_DIR always mirrors the corpus exactly
    and a renamed/deleted fixture can't leave a silently-stale reference file
    behind.

    Returns the list of baseline file paths written, sorted by fixture id
    (load_fixtures() already returns fixtures in that order).
    """
    if fixtures is None:
        fixtures = load_fixtures()

    BASELINES_DIR.mkdir(parents=True, exist_ok=True)

    expected_names = {f"{fixture.id}.json" for fixture in fixtures}
    for stale in sorted(BASELINES_DIR.glob("*.json")):
        if stale.name not in expected_names:
            logger.info(f"[baseline] removing stale baseline for missing fixture: {stale.name}")
            stale.unlink()

    written: list[Path] = []
    for fixture in fixtures:
        snapshot = _fixture_snapshot(fixture)
        path = BASELINES_DIR / f"{fixture.id}.json"
        # sort_keys + fixed indent + trailing newline: byte-identical output
        # across runs is the entire point (TL-0.2 acceptance criteria), and a
        # stable, minimal git diff is the entire point of committing these.
        text = json.dumps(snapshot, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        path.write_text(text, encoding="utf-8")
        written.append(path)
        logger.info(f"[baseline] wrote {path.relative_to(BASELINES_DIR.parent)}")

    return written


def _cli_baseline() -> int:
    written = write_baselines()
    print(f"Wrote {len(written)} baseline snapshot(s) to {BASELINES_DIR}")
    for path in written:
        print(f"  {path.name}")
    return 0


# --------------------------------------------------------------------------
# Regression comparison (TL-0.3)
# --------------------------------------------------------------------------
#
# Informational only — this reports differences, it does not fail a build
# over them (brief §36's gates become blocking in TL-9.6, not here). The one
# exception is a hard crash: a fixture that had a working baseline and now
# raises computing its current snapshot. Every fixture is synthetic (TL-0.1),
# so that can only mean a code regression, never bad input data — that is
# not a "regression to report", it is a broken harness, and it fails even in
# informational mode (see ComparisonReport.has_hard_failure).

def _list_diff_key(item: Any) -> str:
    """A stable, order-independent key for one element of a list being
    diffed. Prefers the activity-identity fields the comparison engine
    already emits (nusf_compare_engine._dashboard_meta); falls back to the
    item's own JSON so an unrecognized shape still diffs by content rather
    than by (brittle) position."""
    if isinstance(item, dict) and "activity" in item:
        return "|".join([
            str(item.get("activity", "")),
            str(item.get("start_date", "")),
            str(item.get("finish_date", "")),
            str(item.get("change_type", "")),
        ])
    return json.dumps(item, sort_keys=True, default=str)


def _normalize_for_diff(value: Any) -> Any:
    """Recursively turn every list into a dict keyed by _list_diff_key().

    Every list this harness snapshots is conceptually a set or a keyed
    collection (added activities, matched changes, progress rows) — nothing
    here depends on list *position* being meaningful. Diffing lists
    positionally would report a single inserted/removed element as N
    spurious "changed" entries (everything after it shifts index). Diffing
    them as dicts instead reports exactly the elements that were actually
    added, removed, or changed.
    """
    if isinstance(value, dict):
        return {k: _normalize_for_diff(v) for k, v in value.items()}
    if isinstance(value, list):
        if all(isinstance(v, str) for v in value):
            return {v: v for v in value}
        if all(isinstance(v, dict) for v in value):
            return {_list_diff_key(v): _normalize_for_diff(v) for v in value}
        return [_normalize_for_diff(v) for v in value]  # e.g. empty list, or a shape we don't expect
    return value


def _walk_diff(old: Any, new: Any, path: str = "") -> list[tuple[str, Any, Any]]:
    """Every leaf-level difference between two normalized (_normalize_for_diff)
    JSON-like structures, as (path, old_value, new_value)."""
    diffs: list[tuple[str, Any, Any]] = []
    if isinstance(old, dict) and isinstance(new, dict):
        for key in sorted(set(old) | set(new)):
            o = old.get(key, _MISSING)
            n = new.get(key, _MISSING)
            child_path = f"{path}.{key}" if path else key
            if o is _MISSING or n is _MISSING:
                diffs.append((child_path, o, n))
            else:
                diffs.extend(_walk_diff(o, n, child_path))
    elif old != new:
        diffs.append((path, old, new))
    return diffs


# Most-specific-prefix-first: "health.comparison.changed_activities" must be
# checked before the broader "health.comparison" catch-all, or every
# comparison sub-field would be miscategorized as a generic count change.
_CATEGORY_RULES: list[tuple[str, str]] = [
    ("health.old_pipeline_error", "new_failures"),
    ("health.new_pipeline_error", "new_failures"),
    ("health.old_schedule", "critical_field_extraction"),
    ("health.new_schedule", "critical_field_extraction"),
    ("health.comparison.changed_activities", "match_set"),
    ("health.comparison.false_matches", "false_match"),
    ("health.comparison", "count"),
    ("predictive", "count"),
]


def _categorize(path: str) -> str:
    """Bucket a diff path into one of brief §36's regression classes —
    critical-field extraction, false match (-> match_set), known calculation
    (-> count) — plus new_failures, per this task's Do §1."""
    if path == "health.comparison":
        # The comparison either appeared or vanished entirely (e.g. one side
        # started/stopped raising a PipelineError) — availability, not a KPI.
        return "new_failures"
    for prefix, category in _CATEGORY_RULES:
        if path == prefix or path.startswith(prefix + "."):
            return category
    return "other"


@dataclass(frozen=True)
class DiffLine:
    fixture_id: str
    category: str
    path: str
    old: Any
    new: Any


@dataclass(frozen=True)
class GradedLine:
    fixture_id: str
    field: str
    baseline_value: Any
    current_value: Any
    expected_value: Any
    verdict: str  # IMPROVED | NEUTRAL | REGRESSED | UNKNOWN


@dataclass(frozen=True)
class MatchMetrics:
    fixture_id: str
    match_precision: float
    false_match_rate: float
    unmatched_rate: float
    requires_verification_rate: float


def compute_fixture_metrics(fixture: Fixture, snapshot: dict[str, Any]) -> MatchMetrics:
    health = snapshot.get("health") or {}
    comparison = health.get("comparison") or {}
    exec_summary = comparison.get("executive_summary") or {}

    total_activities = exec_summary.get("selected_activities", 0)
    confirmed_matches = exec_summary.get("confirmed_matches_count", 0)
    requires_verification = exec_summary.get("requires_verification_count", 0)

    expected = fixture.ground_truth.get("expected", {})
    false_matches = expected.get("false_matches", 0)

    denom_matches = max(1, confirmed_matches + false_matches)
    denom_total = max(1, total_activities)

    precision = round((confirmed_matches - false_matches) / denom_matches, 4)
    false_match_rate = round(false_matches / denom_matches, 4)
    requires_verif_rate = round(requires_verification / denom_total, 4)
    unmatched = max(0, total_activities - confirmed_matches - requires_verification)
    unmatched_rate = round(unmatched / denom_total, 4)

    return MatchMetrics(
        fixture_id=fixture.id,
        match_precision=max(0.0, precision),
        false_match_rate=false_match_rate,
        unmatched_rate=unmatched_rate,
        requires_verification_rate=requires_verif_rate,
    )


@dataclass(frozen=True)
class FixtureResult:
    fixture_id: str
    status: str  # "unchanged" | "changed" | "new_baseline" | "crashed"
    crash_message: Optional[str] = None


# --------------------------------------------------------------------------
# Release gates (TL-9.6 / Brief §36, §39)
# --------------------------------------------------------------------------
GATE_CRITICAL_FIELD_EXTRACTION = "critical_field_extraction"
GATE_FALSE_MATCH = "false_match"
GATE_KNOWN_CALCULATION = "known_calculation"
GATE_UNSUPPORTED_CLAIMS = "unsupported_claims"

ALL_RELEASE_GATES = (
    GATE_CRITICAL_FIELD_EXTRACTION,
    GATE_FALSE_MATCH,
    GATE_KNOWN_CALCULATION,
    GATE_UNSUPPORTED_CLAIMS,
)

CRITICAL_EXTRACTION_FIELDS = {
    "old_activity_count",
    "new_activity_count",
    "old_logic_warning_count",
    "old_issue_rules",
    "old_validation_passed",
    "old_pipeline_raises",
    "old_pipeline_error_contains",
}

KNOWN_CALCULATION_FIELDS = {
    "changed_count",
    "behind_schedule_count",
    "ahead_of_schedule_count",
    "critical_count",
    "point_of_no_return_count",
    "project_health",
    "comparison_selected_activities",
    "comparison_progress_actual_pcts",
}

BASELINE_ADVERSARIAL_QUESTION_IDS = {
    "TL67-Q5-fabricated-number-contradicted",
    "TL67-Q6-fabricated-id-contradicted",
}
BASELINE_UNSUPPORTED_COUNT = 2


@dataclass(frozen=True)
class GateOverride:
    is_valid: bool
    adr_id: Optional[str] = None
    reason: Optional[str] = None
    error_message: Optional[str] = None


def validate_gate_override(
    adr_id: Optional[str] = None,
    reason: Optional[str] = None,
    decisions_path: Optional[Path] = None,
) -> GateOverride:
    """Validate that a gate override has an explicit justification recorded
    in DECISIONS.md per Brief §36.

    An override that is easy and unlogged is not a gate (Brief §36).
    Requires:
    1. A valid ADR identifier (e.g. 'ADR-050')
    2. A non-empty reason of at least 20 characters explaining the rationale
    3. The ADR must actually exist in DECISIONS.md
    """
    if not adr_id:
        adr_id = os.environ.get("NOVA_TRUST_GATE_OVERRIDE_ADR")
    if not reason:
        reason = os.environ.get("NOVA_TRUST_GATE_OVERRIDE_REASON")

    # Also support combined format in NOVA_TRUST_GATE_OVERRIDE: "ADR-NNN: reason..."
    combined = os.environ.get("NOVA_TRUST_GATE_OVERRIDE")
    if combined and (not adr_id or not reason):
        parts = combined.split(":", 1)
        if len(parts) == 2:
            adr_id = adr_id or parts[0].strip()
            reason = reason or parts[1].strip()

    if not adr_id and not reason:
        return GateOverride(
            is_valid=False,
            error_message="No override specified.",
        )

    if not adr_id:
        return GateOverride(
            is_valid=False,
            reason=reason,
            error_message="Override missing required ADR identifier (e.g. ADR-050).",
        )

    if not reason:
        return GateOverride(
            is_valid=False,
            adr_id=adr_id,
            error_message="Override missing required justification text.",
        )

    adr_match = re.match(r"^ADR-\d+$", adr_id.strip(), re.IGNORECASE)
    if not adr_match:
        return GateOverride(
            is_valid=False,
            adr_id=adr_id,
            reason=reason,
            error_message=f"Invalid ADR identifier format '{adr_id}'. Must be ADR-NNN.",
        )

    adr_clean = adr_id.strip().upper()
    reason_clean = reason.strip()

    if len(reason_clean) < 20:
        return GateOverride(
            is_valid=False,
            adr_id=adr_clean,
            reason=reason_clean,
            error_message=f"Override justification too short ({len(reason_clean)} chars). Minimum 20 characters required.",
        )

    # Locate DECISIONS.md
    if decisions_path is None:
        candidates = [
            Path(__file__).resolve().parents[4] / "changes" / "trust-layer" / "plan" / "DECISIONS.md",
            Path(__file__).resolve().parents[3] / "changes" / "trust-layer" / "plan" / "DECISIONS.md",
            Path.cwd() / "changes" / "trust-layer" / "plan" / "DECISIONS.md",
            Path.cwd().parent / "changes" / "trust-layer" / "plan" / "DECISIONS.md",
            Path.cwd().parents[1] / "changes" / "trust-layer" / "plan" / "DECISIONS.md",
        ]
        for c in candidates:
            if c.exists():
                decisions_path = c
                break

    if decisions_path is None or not decisions_path.exists():
        return GateOverride(
            is_valid=False,
            adr_id=adr_clean,
            reason=reason_clean,
            error_message="DECISIONS.md not found to verify ADR.",
        )

    content = decisions_path.read_text(encoding="utf-8")
    adr_pattern = rf"##\s+{re.escape(adr_clean)}\b"
    if not re.search(adr_pattern, content, re.IGNORECASE):
        return GateOverride(
            is_valid=False,
            adr_id=adr_clean,
            reason=reason_clean,
            error_message=f"Override rejected: {adr_clean} not found in {decisions_path}. An override must be recorded in DECISIONS.md before use.",
        )

    return GateOverride(
        is_valid=True,
        adr_id=adr_clean,
        reason=reason_clean,
    )


def _is_diff_improved(d: DiffLine, graded: list[GradedLine]) -> bool:
    for g in graded:
        if g.fixture_id == d.fixture_id and g.verdict == "IMPROVED":
            if g.field in d.path:
                return True
            if d.path == "health.old_schedule.activity_count" and g.field == "old_activity_count":
                return True
            if d.path == "health.new_schedule.activity_count" and g.field == "new_activity_count":
                return True
            if d.path == "health.old_schedule.logic_warning_count" and g.field == "old_logic_warning_count":
                return True
            if d.path == "health.old_schedule.validation_passed" and g.field == "old_validation_passed":
                return True
            if d.path.startswith("health.old_schedule.issue_rules") and g.field == "old_issue_rules":
                return True
            if "old_pipeline_error" in d.path and g.field in ("old_pipeline_raises", "old_pipeline_error_contains"):
                return True
    return False


@dataclass
class ComparisonReport:
    fixtures: list[FixtureResult]
    diffs: list[DiffLine]
    graded: list[GradedLine]
    metrics: Optional[list[MatchMetrics]] = None
    # TL-6.7 / brief §39: aggregate unsupported-factual-claim metric
    # across the standing test-question suite, plus the list of
    # offending claim texts so a non-zero rate can be inspected.
    unsupported_metric: Optional[UnsupportedClaimMetric] = None
    unsupported_offending: Optional[list[tuple[str, str]]] = None
    override_adr: Optional[str] = None
    override_reason: Optional[str] = None
    decisions_path: Optional[Path] = None

    def __post_init__(self):
        if self.metrics is None:
            self.metrics = []
        if self.unsupported_offending is None:
            self.unsupported_offending = []

    def gate_regressions(self) -> dict[str, list[str]]:
        """Evaluate the four release gates (Brief §36, §39, TL-9.6):
        1. critical_field_extraction: extraction cannot regress
        2. false_match: false matches cannot regress (target 0.0)
        3. known_calculation: calculations and KPIs cannot regress
        4. unsupported_claims: unsupported claims cannot exceed baseline
        """
        regressions: dict[str, list[str]] = {
            GATE_CRITICAL_FIELD_EXTRACTION: [],
            GATE_FALSE_MATCH: [],
            GATE_KNOWN_CALCULATION: [],
            GATE_UNSUPPORTED_CLAIMS: [],
        }

        def _add_regression(gate: str, msg: str):
            if msg not in regressions[gate]:
                regressions[gate].append(msg)

        # 1. Graded fields against ground truth
        for g in self.graded:
            if g.verdict == "REGRESSED":
                msg = f"{g.fixture_id}.{g.field} regressed (baseline={g.baseline_value!r} current={g.current_value!r} expected={g.expected_value!r})"
                if g.field in CRITICAL_EXTRACTION_FIELDS:
                    _add_regression(GATE_CRITICAL_FIELD_EXTRACTION, msg)
                elif g.field in ("added", "removed"):
                    _add_regression(GATE_FALSE_MATCH, msg)
                elif g.field in KNOWN_CALCULATION_FIELDS:
                    _add_regression(GATE_KNOWN_CALCULATION, msg)
                else:
                    _add_regression(GATE_KNOWN_CALCULATION, msg)

        # 2. Categorized diffs (for regressions not covered in ground truth)
        for d in self.diffs:
            if _is_diff_improved(d, self.graded):
                continue

            field_name = d.path.split(".")[-1]
            diff_msg = f"{d.fixture_id}: {d.path} ({d.old!r} -> {d.new!r})"

            if d.category in ("critical_field_extraction", "new_failures"):
                if not any(d.fixture_id in r and field_name in r for r in regressions[GATE_CRITICAL_FIELD_EXTRACTION]):
                    _add_regression(GATE_CRITICAL_FIELD_EXTRACTION, diff_msg)

            elif d.category in ("false_match", "match_set"):
                if not any(d.fixture_id in r and field_name in r for r in regressions[GATE_FALSE_MATCH]):
                    _add_regression(GATE_FALSE_MATCH, diff_msg)

            elif d.category == "count":
                if not any(d.fixture_id in r and field_name in r for r in regressions[GATE_KNOWN_CALCULATION]):
                    _add_regression(GATE_KNOWN_CALCULATION, diff_msg)

        # 3. Matching metrics: false match rate target is strictly 0.0 (Brief §37)
        for m in self.metrics:
            if m.false_match_rate > 0.0:
                msg = f"{m.fixture_id}: false match rate {m.false_match_rate:.2%} > 0.0% target"
                _add_regression(GATE_FALSE_MATCH, msg)

        # 4. Gate 4: Unsupported claim rate (Brief §39)
        if self.unsupported_metric is None:
            _add_regression(GATE_UNSUPPORTED_CLAIMS, "Unsupported claim suite did not produce metrics")
        else:
            if self.unsupported_metric.unsupported_count > BASELINE_UNSUPPORTED_COUNT:
                _add_regression(
                    GATE_UNSUPPORTED_CLAIMS,
                    f"Unsupported claim count ({self.unsupported_metric.unsupported_count}) exceeds baseline ({BASELINE_UNSUPPORTED_COUNT})",
                )
            for qid, claim_text in self.unsupported_offending:
                if qid not in BASELINE_ADVERSARIAL_QUESTION_IDS:
                    _add_regression(
                        GATE_UNSUPPORTED_CLAIMS,
                        f"Clean question [{qid}] produced unsupported claim: {claim_text!r}",
                    )
            offending_qids = {qid for qid, _ in self.unsupported_offending}
            for adv_qid in BASELINE_ADVERSARIAL_QUESTION_IDS:
                if adv_qid not in offending_qids:
                    _add_regression(
                        GATE_UNSUPPORTED_CLAIMS,
                        f"Adversarial fixture [{adv_qid}] was not detected as contradicted (verification net regressed)",
                    )

        return {k: v for k, v in regressions.items() if v}

    @property
    def has_gate_failures(self) -> bool:
        return bool(self.gate_regressions())

    @property
    def override(self) -> GateOverride:
        return validate_gate_override(
            adr_id=self.override_adr,
            reason=self.override_reason,
            decisions_path=self.decisions_path,
        )

    @property
    def has_hard_failure(self) -> bool:
        return any(f.status == "crashed" for f in self.fixtures)

    @property
    def exit_code(self) -> int:
        # TL-9.6 (Brief §36, §39): Release gates are now BLOCKING.
        # A hard failure (fixture crash) always fails the build and cannot be overridden.
        if self.has_hard_failure:
            return 1
        # Gate failures block the build unless a verified override is recorded in DECISIONS.md
        if self.has_gate_failures:
            if self.override.is_valid:
                return 0
            return 1
        return 0

    def render(self) -> str:
        lines: list[str] = []
        crashed = [f for f in self.fixtures if f.status == "crashed"]
        new_baseline = [f for f in self.fixtures if f.status == "new_baseline"]
        changed = [f for f in self.fixtures if f.status == "changed"]
        gate_failures = self.gate_regressions()

        if crashed:
            lines.append("CRASHED (hard failure -- fails even in informational mode):")
            for f in crashed:
                lines.append(f"  {f.fixture_id}: {f.crash_message}")
            lines.append("")

        if new_baseline:
            lines.append("NEW (no baseline yet -- run `baseline` to record one):")
            for f in new_baseline:
                lines.append(f"  {f.fixture_id}")
            lines.append("")

        if self.metrics:
            avg_prec = round(sum(m.match_precision for m in self.metrics) / len(self.metrics), 4)
            avg_fmr = round(sum(m.false_match_rate for m in self.metrics) / len(self.metrics), 4)
            avg_unm = round(sum(m.unmatched_rate for m in self.metrics) / len(self.metrics), 4)
            avg_req = round(sum(m.requires_verification_rate for m in self.metrics) / len(self.metrics), 4)
            lines.append("Precision-First Matching Metrics:")
            lines.append(f"  Precision: {avg_prec:.2%} | False Match Rate: {avg_fmr:.2%} | Unmatched: {avg_unm:.2%} | Verification Required: {avg_req:.2%}")
            lines.append("")

        # TL-6.7: brief §39 metric, its own line. Renders whether the
        # target is met and enumerates offending claims when not.
        if self.unsupported_metric is not None:
            lines.extend(render_unsupported_claim_metric(
                self.unsupported_metric, self.unsupported_offending,
            ))

        # TL-9.6 (Brief §36, §39): Blocking Release Gates banner
        if gate_failures:
            lines.append("=" * 80)
            if self.override.is_valid:
                lines.append("RELEASE GATE OVERRIDE ACTIVE (Brief §36)")
                lines.append(f"  Authorized ADR: {self.override.adr_id}")
                lines.append(f"  Reason: {self.override.reason}")
                lines.append("  Status in DECISIONS.md: VERIFIED")
                lines.append("  Overriding the following gate regression(s):")
                for gate, reasons in gate_failures.items():
                    lines.append(f"    [{gate}]:")
                    for r in reasons:
                        lines.append(f"      - {r}")
                lines.append("  Result: PROCEEDING (exit code 0)")
            else:
                lines.append("RELEASE GATES BLOCKED: Regressions detected (Brief §36, §39)")
                if self.override.error_message and self.override.error_message != "No override specified.":
                    lines.append(f"  Override check: {self.override.error_message}")
                lines.append("  The following gate(s) failed:")
                for gate, reasons in gate_failures.items():
                    lines.append(f"    [{gate}]:")
                    for r in reasons:
                        lines.append(f"      - {r}")
                lines.append("")
                lines.append("  To override, a justification must be recorded in DECISIONS.md and provided via:")
                lines.append("    NOVA_TRUST_GATE_OVERRIDE_ADR=\"ADR-NNN\"")
                lines.append("    NOVA_TRUST_GATE_OVERRIDE_REASON=\"Detailed justification text (min 20 chars)...\"")
            lines.append("=" * 80)
            lines.append("")

        if not changed and not crashed and not gate_failures:
            lines.append("no regressions")
            return "\n".join(lines).strip() + "\n"

        for category, label in (
            ("critical_field_extraction", "Critical-field extraction changes"),
            ("false_match", "False-match rate regressions"),
            ("match_set", "Match-set changes"),
            ("count", "Count / KPI changes"),
            ("new_failures", "New failures"),
            ("other", "Other changes"),
        ):
            entries = [d for d in self.diffs if d.category == category]
            if not entries:
                continue
            lines.append(f"{label}:")
            for d in entries:
                lines.append(f"  {d.fixture_id}: {d.path}: {d.old!r} -> {d.new!r}")
            lines.append("")

        if self.graded:
            lines.append("Graded against ground truth:")
            for g in self.graded:
                lines.append(
                    f"  {g.verdict:<10} {g.fixture_id}.{g.field}: "
                    f"baseline={g.baseline_value!r} current={g.current_value!r} "
                    f"expected={g.expected_value!r}"
                )
            lines.append("")

        return "\n".join(lines).strip() + "\n"


def _field_value_matches(field: str, value: Any, expected_value: Any) -> bool:
    """Compare a graded field's actual value to its ground-truth expectation.
    Almost always plain equality; a couple of fields in ground_truth.json are
    phrased as a predicate rather than a literal value to match (see
    fixture 08's "old_pipeline_error_contains", and unordered "added"/
    "removed" lists)."""
    if field == "old_pipeline_error_contains":
        return isinstance(value, str) and expected_value in value
    if field in ("added", "removed"):
        return sorted(value) == sorted(expected_value)
    return value == expected_value


_GRADED_FIELD_NAMES = (
    "old_activity_count", "new_activity_count", "old_logic_warning_count",
    "old_issue_rules", "old_validation_passed", "added", "removed",
    "changed_count", "behind_schedule_count", "ahead_of_schedule_count",
    "critical_count", "point_of_no_return_count", "project_health",
    "comparison_selected_activities", "comparison_progress_actual_pcts",
    "old_pipeline_raises", "old_pipeline_error_contains",
)


def _graded_fields(expected: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    """Extract exactly the fields ground_truth.json's "expected" block can
    name, from a {"health":..., "predictive":...} snapshot. Mirrors
    test_harness.py's assertions, but returns values instead of asserting
    them, so a baseline snapshot and a current snapshot can be graded
    against the same expectations and then compared to each other.
    Deliberately not shared code with test_harness.py: that file *asserts*
    one snapshot is correct; this *compares* two snapshots' correctness."""
    health = snapshot.get("health") or {}
    old_schedule = health.get("old_schedule") or {}
    new_schedule = health.get("new_schedule") or {}
    comparison = health.get("comparison")
    out: dict[str, Any] = {}

    for field in _GRADED_FIELD_NAMES:
        if field not in expected:
            continue
        if field == "old_activity_count":
            out[field] = old_schedule.get("activity_count", _MISSING)
        elif field == "new_activity_count":
            out[field] = new_schedule.get("activity_count", _MISSING)
        elif field == "old_logic_warning_count":
            out[field] = old_schedule.get("logic_warning_count", _MISSING)
        elif field == "old_issue_rules":
            out[field] = old_schedule.get("issue_rules", _MISSING)
        elif field == "old_validation_passed":
            out[field] = old_schedule.get("validation_passed", _MISSING)
        elif field == "old_pipeline_raises":
            out[field] = health.get("old_pipeline_error") is not None
        elif field == "old_pipeline_error_contains":
            out[field] = health.get("old_pipeline_error") or ""
        elif comparison is None:
            out[field] = _MISSING
        elif field == "added":
            out[field] = comparison["changed_activities"].get("added", [])
        elif field == "removed":
            out[field] = comparison["changed_activities"].get("removed", [])
        elif field == "changed_count":
            out[field] = len(comparison["changed_activities"].get("changes", []))
        elif field == "comparison_selected_activities":
            out[field] = comparison["executive_summary"].get("selected_activities", _MISSING)
        elif field == "comparison_progress_actual_pcts":
            out[field] = {
                item["activity"]: item["actual_pct"]
                for item in comparison.get("progress_vs_expected", [])
            }
        else:
            out[field] = comparison["executive_summary"].get(field, _MISSING)

    return out


def _grade(fixture: Fixture, baseline_snapshot: dict, current_snapshot: dict) -> list[GradedLine]:
    """Classify each changed, ground-truth-covered field as IMPROVED /
    REGRESSED / UNKNOWN (brief §36's classification requirement, Do §2).
    NEUTRAL is intentionally never emitted here — it is reserved for the
    additive-schema case (a *new* key appearing that ground truth doesn't
    yet cover, e.g. a future phase adding a provenance field), which shows
    up in the categorized diff, not the graded-fields comparison, and
    doesn't need a per-field verdict to be judged harmless."""
    expected = fixture.ground_truth.get("expected", {})
    baseline_actuals = _graded_fields(expected, baseline_snapshot)
    current_actuals = _graded_fields(expected, current_snapshot)

    graded: list[GradedLine] = []
    for field, expected_value in expected.items():
        if field not in baseline_actuals:
            continue  # not a graded field (e.g. free-text "notes")
        b_val, c_val = baseline_actuals[field], current_actuals[field]
        if b_val == c_val:
            continue  # unchanged for this field -- nothing to grade

        b_ok = b_val is not _MISSING and _field_value_matches(field, b_val, expected_value)
        c_ok = c_val is not _MISSING and _field_value_matches(field, c_val, expected_value)
        if b_ok and not c_ok:
            verdict = "REGRESSED"
        elif not b_ok and c_ok:
            verdict = "IMPROVED"
        else:
            # Either both still fail to match ground truth (changed to a
            # different wrong value -- no basis to call that better or
            # worse) or both happen to satisfy _field_value_matches despite
            # b_val != c_val (e.g. reordering under a predicate comparator).
            # Neither case can be graded from ground truth alone.
            verdict = "UNKNOWN"

        graded.append(GradedLine(fixture.id, field, b_val, c_val, expected_value, verdict))

    return graded


def compare_against_baseline(
    fixtures: Optional[list[Fixture]] = None,
    baselines_dir: Optional[Path] = None,
    snapshot_fn: Optional[Callable[[Fixture], dict[str, Any]]] = None,
    override_adr: Optional[str] = None,
    override_reason: Optional[str] = None,
    decisions_path: Optional[Path] = None,
) -> ComparisonReport:
    """Diff a freshly computed snapshot for every fixture against its
    committed baseline.

    Never raises for an ordinary regression — a fixture whose facts changed
    is reported, not failed. The one exception is a genuine crash; see the
    module-level comment above this section.

    `baselines_dir` / `snapshot_fn` are injectable so tests can exercise
    "deliberately broken" scenarios (TL-0.3 acceptance criteria) without
    touching the real committed baselines or requiring an actual code
    regression to demonstrate the reporting works.
    """
    if fixtures is None:
        fixtures = load_fixtures()
    baselines_dir = baselines_dir or BASELINES_DIR
    snapshot_fn = snapshot_fn or _fixture_snapshot

    results: list[FixtureResult] = []
    all_diffs: list[DiffLine] = []
    all_graded: list[GradedLine] = []
    all_metrics: list[MatchMetrics] = []

    for fixture in fixtures:
        baseline_path = baselines_dir / f"{fixture.id}.json"
        if not baseline_path.exists():
            results.append(FixtureResult(fixture.id, "new_baseline"))
            continue

        baseline_snapshot = json.loads(baseline_path.read_text(encoding="utf-8"))

        try:
            current_snapshot = snapshot_fn(fixture)
        except Exception as exc:  # noqa: BLE001 -- the crash itself is the signal
            results.append(FixtureResult(fixture.id, "crashed", f"{type(exc).__name__}: {exc}"))
            continue

        all_metrics.append(compute_fixture_metrics(fixture, current_snapshot))

        diffs = _walk_diff(
            _normalize_for_diff(baseline_snapshot),
            _normalize_for_diff(current_snapshot),
        )
        if not diffs:
            results.append(FixtureResult(fixture.id, "unchanged"))
            continue

        results.append(FixtureResult(fixture.id, "changed"))
        all_diffs.extend(
            DiffLine(fixture.id, _categorize(path), path, old, new)
            for path, old, new in diffs
        )
        all_graded.extend(_grade(fixture, baseline_snapshot, current_snapshot))

    # TL-6.7: brief §39 — run the standing test-question suite and
    # attach the unsupported-factual-claim rate to the report. Runs
    # unconditionally on every compare (a fixture crash does not
    # abort this — the metric is independent of fixture state).
    unsupported_metric, unsupported_offending = run_unsupported_claim_suite()

    return ComparisonReport(
        fixtures=results,
        diffs=all_diffs,
        graded=all_graded,
        metrics=all_metrics,
        unsupported_metric=unsupported_metric,
        unsupported_offending=unsupported_offending,
        override_adr=override_adr,
        override_reason=override_reason,
        decisions_path=decisions_path,
    )


def _cli_compare(
    override_adr: Optional[str] = None,
    override_reason: Optional[str] = None,
    decisions_path: Optional[Path] = None,
) -> int:
    report = compare_against_baseline(
        override_adr=override_adr,
        override_reason=override_reason,
        decisions_path=decisions_path,
    )
    print(report.render())
    return report.exit_code


# ============================================================================
# TL-6.7 — Standing test-question suite for unsupported-factual-claim rate
# ============================================================================
# Brief §39: *"Add a standing set of test questions run against known
# fixtures."* Each entry below is a (narrative, facts, language) triple
# that gets verified by `verify_narrative`; the resulting
# `CONTRADICTED` count is what feeds the brief §39 metric
# (`unsupported_count / total_claims`, target zero). The suite mixes
# clean baselines (zero unsupported), contradiction fixtures (a known
# false number the system must catch), and unverifiable fixtures
# (fact-store has nothing to check against) — so the metric exercises
# the full range of brief §39's failure modes.

_NARRATIVE_VERIFICATION_SUITE: list[dict[str, Any]] = [
    # Baseline 1: a known-good numeric claim — must verify clean.
    {
        "id": "TL67-Q1-delayed-count-clean",
        "narrative": "31 activities are delayed in the schedule.",
        "facts": {
            "insight_data": {"delayed_count": 31, "critical_count": 5},
            "delayed_activities": [],
            "summary_by_area": [],
            "schedule_overview": {"reference_date": "01-01-2026", "schedule_name": "T"},
        },
        "language": "en",
    },
    # Baseline 2: a known-good id reference — must verify clean.
    {
        "id": "TL67-Q2-id-reference-clean",
        "narrative": "Task ID T1 is delayed.",
        "facts": {
            "insight_data": {"delayed_count": 1, "critical_count": 1},
            "delayed_activities": [{"id": "T1", "days_overdue": 47}],
            "summary_by_area": [],
            "schedule_overview": {"reference_date": "01-01-2026", "schedule_name": "T"},
        },
        "language": "en",
    },
    # Baseline 3: a known-good date reference — must verify clean.
    {
        "id": "TL67-Q3-date-reference-clean",
        "narrative": "The reference date is 01-01-2026.",
        "facts": {
            "insight_data": {"delayed_count": 0},
            "delayed_activities": [],
            "summary_by_area": [],
            "schedule_overview": {"reference_date": "01-01-2026", "schedule_name": "T"},
        },
        "language": "en",
    },
    # Baseline 4: a known-good superlative — must verify clean (NK is the
    # unique top entry in the per-area breakdown).
    {
        "id": "TL67-Q4-superlative-clean",
        "narrative": "NK has the largest concentration of delay.",
        "facts": {
            "insight_data": {"delayed_count": 10},
            "delayed_activities": [],
            "summary_by_area": [
                {"area": "NK", "delayed_count": 8, "critical_count": 3},
                {"area": "AAA", "delayed_count": 2, "critical_count": 0},
            ],
            "schedule_overview": {"reference_date": "01-01-2026", "schedule_name": "T"},
        },
        "language": "en",
    },
    # Adversarial: a fabricated number that the fact store contradicts —
    # the headline brief §39 failure mode. This MUST register as
    # CONTRADICTED (the headline unsupported factual claim). The test
    # suite will deliberately fail if this changes.
    {
        "id": "TL67-Q5-fabricated-number-contradicted",
        "narrative": "47 activities are delayed in the schedule.",
        "facts": {
            "insight_data": {"delayed_count": 31, "critical_count": 5},
            "delayed_activities": [],
            "summary_by_area": [],
            "schedule_overview": {"reference_date": "01-01-2026", "schedule_name": "T"},
        },
        "language": "en",
    },
    # Adversarial: a fabricated id that the fact store contradicts.
    {
        "id": "TL67-Q6-fabricated-id-contradicted",
        "narrative": "Task ID T999 is delayed.",
        "facts": {
            "insight_data": {"delayed_count": 1, "critical_count": 1},
            "delayed_activities": [{"id": "T1", "days_overdue": 47}],
            "summary_by_area": [],
            "schedule_overview": {"reference_date": "01-01-2026", "schedule_name": "T"},
        },
        "language": "en",
    },
    # Adversarial: a wrong day count that the fact store contradicts.
    {
        "id": "TL67-Q7-fabricated-day-count-contradicted",
        "narrative": "T1 is delayed by 99 days.",
        "facts": {
            "insight_data": {"delayed_count": 1, "critical_count": 1, "most_overdue_days": 47},
            "delayed_activities": [{"id": "T1", "days_overdue": 47, "start_date": "01-01-2020", "end_date": "10-01-2020"}],
            "summary_by_area": [],
            "schedule_overview": {"reference_date": "01-01-2026", "schedule_name": "T"},
        },
        "language": "en",
    },
    # Brief §18's A142 pattern: a causal claim — must classify as
    # INFERENCE (always UNVERIFIABLE, never VERIFIED). Contributes to
    # the unverifiable count, not the unsupported count.
    {
        "id": "TL67-Q8-causal-a142",
        "narrative": "T1 is delayed because of a coordination issue.",
        "facts": {
            "insight_data": {"delayed_count": 1, "critical_count": 1},
            "delayed_activities": [{"id": "T1", "days_overdue": 47}],
            "summary_by_area": [],
            "schedule_overview": {"reference_date": "01-01-2026", "schedule_name": "T"},
        },
        "language": "en",
    },
    # Brief §20's headline hedged-prose case: a forecast that's
    # unverifiable but uses fact-grade language. The narrative itself
    # is unsupported (UNVERIFIABLE DATE_DURATION + overclaiming); the
    # brief §39 metric does not count UNVERIFIABLE as unsupported, but
    # the test asserts the hedger still rewrites the prose for §20.
    {
        "id": "TL67-Q9-forecast-with-overclaim",
        "narrative": "The project will definitely be delayed by 4-8 weeks.",
        "facts": {
            "insight_data": {"delayed_count": 5, "critical_count": 1},
            "delayed_activities": [],
            "summary_by_area": [],
            "schedule_overview": {"reference_date": "01-01-2026", "schedule_name": "T"},
        },
        "language": "en",
    },
]


def run_unsupported_claim_suite() -> tuple[UnsupportedClaimMetric, list[tuple[str, str]]]:
    """TL-6.7 / brief §39: run the standing test-question suite, aggregate
    the unsupported-factual-claim rate, and enumerate every offending
    claim for inspection.

    Returns `(metric, offending_claims)`:
      - `metric`: aggregate across the suite
      - `offending_claims`: list of `(question_id, claim_text)` pairs,
        one per CONTRADICTED claim — the headline brief §39 deliverable
        that any non-zero rate lists the specific unsupported claims.
    """
    from src.trust.claims import NarrativeVerificationResult
    results: list[NarrativeVerificationResult] = []
    question_ids: list[str] = []
    for entry in _NARRATIVE_VERIFICATION_SUITE:
        question_ids.append(entry["id"])
        results.append(verify_narrative(
            entry["narrative"],
            entry["facts"],
            language=entry.get("language", "en"),
        ))
    metric = compute_unsupported_claim_metric(results)
    offending = collect_unsupported_claims(results, question_ids)
    return metric, offending


def render_unsupported_claim_metric(
    metric: UnsupportedClaimMetric,
    offending: list[tuple[str, str]],
) -> list[str]:
    """TL-6.7 / AC4: render the metric as its own line(s) in the harness
    compare output. Brief §39: any non-zero rate must enumerate the
    offending claims for inspection."""
    lines: list[str] = []
    if metric.total_claims == 0:
        # Defensive: no claims extracted → metric is undefined. Report
        # it explicitly so a missing-test-questions case is visible.
        lines.append("Unsupported factual claims (TL-6.7 / brief §39): "
                     "no claims extracted across the suite")
        lines.append("")
        return lines

    target_met = metric.meets_target()
    lines.append(
        f"Unsupported factual claims (TL-6.7 / brief §39): "
        f"{metric.unsupported_count}/{metric.total_claims} "
        f"({metric.unsupported_rate:.2%}) — target met: {target_met}"
    )
    if metric.unsupported_count > 0:
        lines.append("  Offending claims:")
        for qid, text in offending:
            lines.append(f"    [{qid}] {text!r}")
    lines.append("")
    return lines


def main(argv: Optional[list[str]] = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print("usage: python -m tests.trust.harness {baseline|compare} [options]")
        return 2

    command = argv[0]
    if command == "baseline":
        return _cli_baseline()
    if command == "compare":
        import argparse
        parser = argparse.ArgumentParser(
            prog="python -m tests.trust.harness compare",
            description="Diff current output against committed baselines and enforce release gates (Brief §36, §39)",
        )
        parser.add_argument("--override-adr", help="ADR ID recorded in DECISIONS.md (e.g. ADR-050)")
        parser.add_argument("--override-reason", help="Detailed justification for the override (min 20 chars)")
        args, _ = parser.parse_known_args(argv[1:])
        return _cli_compare(
            override_adr=args.override_adr,
            override_reason=args.override_reason,
        )

    print(f"unknown command: {command}")
    print("usage: python -m tests.trust.harness {baseline|compare} [options]")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
