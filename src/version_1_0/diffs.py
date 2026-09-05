"""Per-activity structured diff for the Nova Insight V1 Changed Activities table.

Pure logic - no I/O, no LLM, no HTML. Consumed by adapters.adapt_health_dashboard
and rendered by formatters._render_table(variant="changed").

The :class:`Verifier` protocol is the seam where the future Confidence /
Verification Layer will plug in. Today the default
:class:`ValidationIssueVerifier` consults upstream ValidationIssue objects plus
missing-extraction signals to decide whether a field can be trusted.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


FIELD_KEYS: tuple[str, ...] = ("start", "finish", "duration", "progress", "id")


# Trust-layer backstop: a day-based delta this large almost certainly means an
# extraction/parsing/matching problem upstream rather than a genuine schedule
# change (see changes/17-08/revision-1.md item 1 - "verify the Duration
# values"). Rather than display an implausible number, we mark the field
# unable-to-verify so the UI shows "Unable to verify change" instead of a
# figure nobody can trust. 3650 days (~10 years) comfortably exceeds any real
# construction activity/date shift while still catching parsing blow-ups.
_MAX_PLAUSIBLE_DAY_DELTA = 3650


_DATE_FORMATS: tuple[str, ...] = (
    "%d-%m-%Y",
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%d.%m.%Y",
    "%m/%d/%Y",
)


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def _parse_date(value: Any) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


_DURATION_NUM_RE = re.compile(r"(-?\d+(?:[.,]\d+)?)")


def _parse_duration_days(value: Any, default: int = 0) -> int:
    """Parse a duration cell into a whole number of days.

    Duration text reaching this function may be a bare number from a PDF
    table (assumed to already be in days - the convention used everywhere
    else in Nova for an unsuffixed duration) or carry a unit suffix produced
    by the MPP/MSPDI extractors, e.g. "73.0d", "5.0w", "160.0h". A trailing
    unit is converted to days (8 working hours/day, 5 working days/week -
    matching ingestion.extractors.mpp._duration_to_days) so two durations in
    different units compare correctly instead of being compared as raw
    numbers.

    Root-cause fix (2026-08 revision, changes/17-08/revision-1.md item 1):
    the previous implementation stripped every non-digit character
    (including "." and ",") before parsing, which deleted the decimal point
    instead of rounding on it. A duration formatted upstream as "73.0d" (a
    legitimate 73-day value) was reduced to the digit string "730" and
    parsed as 730 - a 10x inflation. Two such values on either side of a
    diff compound into the multi-thousand-day deltas ("+10,056d") reported
    against Nova. The unit suffix was also silently discarded rather than
    converted, so a value genuinely in weeks or hours was miscompared
    against one in days.
    """
    if value is None:
        return default
    text = str(value).strip()
    if not text:
        return default
    normalized = text.replace(",", ".")
    m = _DURATION_NUM_RE.search(normalized)
    if not m:
        return default
    try:
        amount = float(m.group(1))
    except (ValueError, TypeError):
        return default
    unit = normalized[m.end():].strip().lower()
    if unit.startswith("w") or unit.startswith("u"):  # week / uge
        days = amount * 5.0
    elif unit.startswith("h") or unit.startswith("t"):  # hour / time
        days = amount / 8.0
    else:  # "d", "dage", trailing junk, or no suffix - already days
        days = amount
    return int(round(days))


def _parse_pct(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    text = str(value).replace("%", "").strip().replace(",", ".")
    if not text:
        return default
    try:
        return float(text)
    except ValueError:
        return default


def _normalize_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple, set)):
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _values_equal(a: Any, b: Any) -> bool:
    sa, sb = _normalize_str(a), _normalize_str(b)
    if not sa and not sb:
        return True
    return sa == sb


def _signed_int_from_delta(value: Any) -> int:
    if value is None:
        return 0
    text = str(value).strip()
    if not text:
        return 0
    m = re.match(r"([+-]?\d+(?:\.\d+)?)", text)
    if not m:
        return 0
    try:
        return int(round(float(m.group(1))))
    except (ValueError, TypeError):
        return 0


def _signed_pp_from_delta(value: Any) -> float:
    if value is None:
        return 0.0
    text = str(value).strip()
    if not text:
        return 0.0
    m = re.match(r"([+-]?\d+(?:\.\d+)?)", text)
    if not m:
        return 0.0
    try:
        return float(m.group(1))
    except (ValueError, TypeError):
        return 0.0


# ---------------------------------------------------------------------------
# change_type label fallback mapping
# ---------------------------------------------------------------------------


_CHANGE_TYPE_ALIASES: dict[str, str] = {
    "start": "start",
    "start date": "start",
    "startdate": "start",
    "finish": "finish",
    "finish date": "finish",
    "end date": "finish",
    "enddate": "finish",
    "finishdate": "finish",
    "duration": "duration",
    "progress": "progress",
    "progress %": "progress",
    "percent complete": "progress",
    "id": "id",
    "activity id": "id",
}


def _map_change_type(label: Any) -> str | None:
    if not isinstance(label, str):
        return None
    return _CHANGE_TYPE_ALIASES.get(_normalize_str(label).lower())


# ---------------------------------------------------------------------------
# Public dataclasses
# ---------------------------------------------------------------------------


@dataclass
class FieldDiff:
    """One field-level change on one activity.

    ``semantic`` is one of ``"delay" | "improved" | "worsened" | "neutral"``.
    Progress uses ``"worsened"`` (not ``"delay"``) per the V1 spec; downstream
    formatters collapse both to the same red badge.
    """

    field: str
    old: Any
    new: Any
    delta: str | None
    semantic: str
    verify: str  # "verified" | "unable_to_verify"


@dataclass
class ActivityDiff:
    activity_id: str
    activity_name: str
    phase: str
    area: str
    trade: str
    field_diffs: list[FieldDiff]
    changed_fields: list[str]
    impact_score: float
    verify: str  # "verified" | "unable_to_verify"


# ---------------------------------------------------------------------------
# Verifier protocol + default implementation (Confidence / Verification seam)
# ---------------------------------------------------------------------------


@runtime_checkable
class Verifier(Protocol):
    """Pluggable gate for the future Confidence / Verification Layer."""

    def verify_field(self, activity_id: str, field: str) -> bool: ...

    def verify_activity(self, activity_id: str) -> bool: ...


_SEVERITY_RANK: dict[str, int] = {
    "info": 0,
    "warn": 1,
    "warning": 1,
    "error": 2,
    "critical": 2,
}


def _severity_rank(severity: Any) -> int:
    if not severity:
        return 0
    return _SEVERITY_RANK.get(str(severity).strip().lower(), 0)


class ValidationIssueVerifier:
    """Default :class:`Verifier`.

    A field is considered UN-verified when any ValidationIssue with severity >=
    ``"warn"`` touches that field, or when the issue has no ``field`` attribute
    (activity-wide issue). A field with both OLD and NEW values empty / missing
    is also UN-verified regardless of the verifier.
    """

    def __init__(self, issues_by_activity: dict[str, list[Any]] | None = None) -> None:
        self._issues_by_activity: dict[str, list[Any]] = {
            str(k): list(v) for k, v in (issues_by_activity or {}).items()
        }

    def verify_field(self, activity_id: str, field: str) -> bool:
        for issue in self._issues_by_activity.get(str(activity_id), []):
            if _severity_rank(getattr(issue, "severity", None)) < 1:
                continue
            issue_field = getattr(issue, "field", None)
            if issue_field is None:
                return False
            if str(issue_field) == field:
                return False
        return True

    def verify_activity(self, activity_id: str) -> bool:
        issues = self._issues_by_activity.get(str(activity_id), [])
        if not issues:
            return True
        return all(_severity_rank(getattr(i, "severity", None)) < 1 for i in issues)


# ---------------------------------------------------------------------------
# Field-level diff builders
# ---------------------------------------------------------------------------


def _verify_one(
    verifier: Verifier | None,
    activity_id: str,
    field: str,
    old: Any,
    new: Any,
) -> str:
    if verifier is not None and not verifier.verify_field(activity_id, field):
        return "unable_to_verify"
    # newPhase.md: "If either OLD or NEW value cannot be reliably
    # extracted/verified, show 'Unable to verify change' rather than
    # guessing." Previously this only fired when BOTH sides were empty, so a
    # missing OLD/NEW value defaulted through the numeric parsers as 0 and
    # was displayed as a confident (and wrong) delta. Either side missing is
    # enough - we cannot compute a trustworthy delta from a value we never
    # extracted.
    if not _normalize_str(old) or not _normalize_str(new):
        return "unable_to_verify"
    return "verified"


def _diff_start(item: dict, verifier: Verifier | None, activity_id: str) -> FieldDiff | None:
    old_val = item.get("old_start")
    new_val = item.get("new_start")
    if _values_equal(old_val, new_val):
        return None
    old_d = _parse_date(old_val)
    new_d = _parse_date(new_val)
    verify = _verify_one(verifier, activity_id, "start", old_val, new_val)
    if old_d and new_d:
        days = (new_d - old_d).days
        if abs(days) > _MAX_PLAUSIBLE_DAY_DELTA:
            logger.warning(
                f"[version_1_0.diffs][_diff_start] implausible delta days={days} "
                f"activity={activity_id!r} old={old_val!r} new={new_val!r} - marking unable_to_verify"
            )
            return FieldDiff("start", old_val, new_val, None, "neutral", "unable_to_verify")
        delta = f"{days:+d}d"
        if days > 0:
            semantic = "delay"
        elif days < 0:
            semantic = "improved"
        else:
            semantic = "neutral"
    else:
        delta = None
        semantic = "neutral"
    return FieldDiff("start", old_val, new_val, delta, semantic, verify)


def _diff_finish(item: dict, verifier: Verifier | None, activity_id: str) -> FieldDiff | None:
    old_val = item.get("old_finish")
    new_val = item.get("new_finish")
    if _values_equal(old_val, new_val):
        return None
    old_d = _parse_date(old_val)
    new_d = _parse_date(new_val)
    verify = _verify_one(verifier, activity_id, "finish", old_val, new_val)
    if old_d and new_d:
        days = (new_d - old_d).days
        if abs(days) > _MAX_PLAUSIBLE_DAY_DELTA:
            logger.warning(
                f"[version_1_0.diffs][_diff_finish] implausible delta days={days} "
                f"activity={activity_id!r} old={old_val!r} new={new_val!r} - marking unable_to_verify"
            )
            return FieldDiff("finish", old_val, new_val, None, "neutral", "unable_to_verify")
        delta = f"{days:+d}d"
        if days > 0:
            semantic = "delay"
        elif days < 0:
            semantic = "improved"
        else:
            semantic = "neutral"
    else:
        delta = None
        semantic = "neutral"
    return FieldDiff("finish", old_val, new_val, delta, semantic, verify)


def _diff_duration(item: dict, verifier: Verifier | None, activity_id: str) -> FieldDiff | None:
    explicit_old = item.get("old_duration")
    explicit_new = item.get("new_duration")

    # Prefer deriving duration from (finish - start) when all four dates are
    # parseable. The explicit duration field upstream is often in a different
    # unit (hours/weeks) than the dates (days), and the date-derived duration
    # is unambiguous. (changes/17-08/revision-1.md item 1)
    old_start_d = _parse_date(item.get("old_start"))
    old_finish_d = _parse_date(item.get("old_finish"))
    new_start_d = _parse_date(item.get("new_start"))
    new_finish_d = _parse_date(item.get("new_finish"))
    if old_start_d and old_finish_d and new_start_d and new_finish_d:
        old_n = (old_finish_d - old_start_d).days
        new_n = (new_finish_d - new_start_d).days
        old_val: Any = f"{old_n}d"
        new_val: Any = f"{new_n}d"
        verify = "verified"
    else:
        # Dates missing - fall back to the explicit duration field, with the
        # unit-suffix helper (h/w -> days) the upstream may carry.
        old_n = _parse_duration_days(explicit_old)
        new_n = _parse_duration_days(explicit_new)
        old_val = explicit_old
        new_val = explicit_new
        verify = _verify_one(verifier, activity_id, "duration", explicit_old, explicit_new)

    if old_n == new_n and not _normalize_str(explicit_old) and not _normalize_str(explicit_new):
        return None
    if old_n == new_n and (
        old_start_d is None or new_start_d is None
    ):
        return None

    delta_days = new_n - old_n
    # Backstop: a single duration value above the plausible-day ceiling
    # (~10 years) almost always signals that upstream data is in hours /
    # minutes / weeks while the dashboard is reading it as days. The
    # delta-only check previously let these through (e.g. 5832 -> 9456
    # gives a 3624-day delta that looked superficially plausible). Treat
    # any individual absolute value above the ceiling as unable_to_verify.
    if (
        abs(old_n) > _MAX_PLAUSIBLE_DAY_DELTA
        or abs(new_n) > _MAX_PLAUSIBLE_DAY_DELTA
        or abs(delta_days) > _MAX_PLAUSIBLE_DAY_DELTA
    ):
        logger.warning(
            f"[version_1_0.diffs][_diff_duration] implausible magnitude "
            f"old_n={old_n} new_n={new_n} delta={delta_days} "
            f"activity={activity_id!r} old={explicit_old!r} new={explicit_new!r} - marking unable_to_verify"
        )
        return FieldDiff("duration", old_val, new_val, None, "neutral", "unable_to_verify")
    delta = f"{delta_days:+d}d"
    if delta_days > 0:
        semantic = "delay"
    elif delta_days < 0:
        semantic = "improved"
    else:
        semantic = "neutral"
    return FieldDiff("duration", old_val, new_val, delta, semantic, verify)


def _diff_progress(item: dict, verifier: Verifier | None, activity_id: str) -> FieldDiff | None:
    # Preferred: explicit fields. Fallback: change_type + old/new free text.
    old_val: Any = None
    new_val: Any = None
    if "old_progress" in item or "new_progress" in item:
        old_val = item.get("old_progress")
        new_val = item.get("new_progress")
    else:
        ct = _normalize_str(item.get("change_type")).lower()
        if "progress" in ct or "percent" in ct:
            old_val = item.get("old")
            new_val = item.get("new")
    if old_val is None and new_val is None:
        return None
    if _values_equal(old_val, new_val):
        return None
    old_n = _parse_pct(old_val)
    new_n = _parse_pct(new_val)
    if round(old_n, 1) == round(new_n, 1) and _normalize_str(old_val) == _normalize_str(new_val):
        return None
    delta_pp = round(new_n - old_n, 1)
    if abs(delta_pp) < 0.05:
        return None
    delta = f"{delta_pp:+g}pp"
    semantic = "worsened" if delta_pp < 0 else "improved"
    verify = _verify_one(verifier, activity_id, "progress", old_val, new_val)
    return FieldDiff("progress", old_val, new_val, delta, semantic, verify)


def _diff_id(item: dict, verifier: Verifier | None, activity_id: str) -> FieldDiff | None:
    # ID changes when the upstream data carries explicit old_id/new_id signals,
    # or when item['field'] / item['change_type'] specifies 'id' with old/new.
    old_val = item.get("old_id")
    new_val = item.get("new_id")
    if old_val is None and new_val is None:
        ct = _normalize_str(item.get("field") or item.get("change_type")).lower()
        if ct in ("id", "activity id"):
            old_val = item.get("old")
            new_val = item.get("new")
    if old_val is None and new_val is None:
        return None
    if _values_equal(old_val, new_val):
        return None
    verify = _verify_one(verifier, activity_id, "id", old_val, new_val)
    return FieldDiff("id", old_val, new_val, None, "neutral", verify)


_FIELD_DIFF_BUILDERS = {
    "start": _diff_start,
    "finish": _diff_finish,
    "duration": _diff_duration,
    "progress": _diff_progress,
    "id": _diff_id,
}


# ---------------------------------------------------------------------------
# Public entry
# ---------------------------------------------------------------------------


def _pick_first(*candidates: Any) -> Any:
    for value in candidates:
        if _normalize_str(value):
            return value
    return None


def diff_activities(
    change_items: list[dict],
    verifier: Verifier | None = None,
) -> list[ActivityDiff]:
    """Produce one :class:`ActivityDiff` per unique activity id.

    ``change_items`` is the raw list from
    ``data["changed_activities"]["changes"]`` upstream. Multiple items per id
    are merged (the first item carries metadata, subsequent items contribute
    missing ``old_*`` / ``new_*`` fields).

    Returns the list sorted by ``impact_score`` descending, ties broken by
    ``activity_id`` ascending for deterministic output.
    """
    if not change_items:
        return []

    grouped: dict[str, dict] = {}
    activity_meta: dict[str, dict] = {}

    for item in change_items:
        if not isinstance(item, dict):
            continue
        act_id = _normalize_str(
            item.get("id") or item.get("activity") or item.get("source_id")
        )
        if not act_id:
            continue
        if act_id not in activity_meta:
            activity_meta[act_id] = {
                "activity_id": act_id,
                "activity_name": _normalize_str(
                    item.get("activity") or item.get("task_name") or item.get("name")
                ),
                "phase": _normalize_str(item.get("phase")),
                "area": _normalize_str(
                    item.get("area") or item.get("location") or item.get("building")
                ),
                "trade": _normalize_str(
                    item.get("trade")
                    or item.get("resource")
                    or item.get("discipline")
                ),
            }
        existing = grouped.setdefault(act_id, {})
        for key in (
            "old_start",
            "new_start",
            "old_finish",
            "new_finish",
            "old_duration",
            "new_duration",
            "old_progress",
            "new_progress",
            "old_id",
            "new_id",
        ):
            if not _normalize_str(existing.get(key)) and _normalize_str(item.get(key)):
                existing[key] = item.get(key)
        if not existing.get("field") and item.get("field"):
            existing["field"] = item.get("field")
        if not existing.get("change_type") and item.get("change_type"):
            existing["change_type"] = item.get("change_type")
        # Carry through old/new free-text as a fallback for progress / id.
        if not existing.get("old") and item.get("old") is not None:
            existing["old"] = item.get("old")
        if not existing.get("new") and item.get("new") is not None:
            existing["new"] = item.get("new")

    results: list[ActivityDiff] = []
    for act_id, item in grouped.items():
        meta = activity_meta[act_id]
        field_diffs: list[FieldDiff] = []
        changed_fields: list[str] = []
        for key in FIELD_KEYS:
            builder = _FIELD_DIFF_BUILDERS[key]
            fd = builder(item, verifier, act_id)
            if fd is not None:
                field_diffs.append(fd)
                changed_fields.append(fd.field)

        # Fallback: if no per-field diff was produced but a change_type label
        # signals one, give the corresponding builder a chance to read free
        # text from change_items[old]/[new].
        if not field_diffs:
            mapped = _map_change_type(item.get("change_type"))
            if mapped and mapped in _FIELD_DIFF_BUILDERS:
                fd = _FIELD_DIFF_BUILDERS[mapped](item, verifier, act_id)
                if fd is not None:
                    field_diffs.append(fd)
                    changed_fields.append(fd.field)

        impact = 0.0
        for fd in field_diffs:
            if fd.field in ("start", "finish", "duration"):
                impact += abs(_signed_int_from_delta(fd.delta)) * (
                    0.5 if fd.field == "duration" else 1.0
                )
            elif fd.field == "progress":
                impact += abs(_signed_pp_from_delta(fd.delta)) * 0.25

        if field_diffs:
            activity_verify = (
                "verified"
                if all(fd.verify == "verified" for fd in field_diffs)
                else "unable_to_verify"
            )
        else:
            activity_verify = "verified"

        results.append(
            ActivityDiff(
                activity_id=meta["activity_id"],
                activity_name=meta["activity_name"],
                phase=meta["phase"],
                area=meta["area"],
                trade=meta["trade"],
                field_diffs=field_diffs,
                changed_fields=changed_fields,
                impact_score=round(impact, 2),
                verify=activity_verify,
            )
        )

    results.sort(key=lambda r: (-r.impact_score, r.activity_id))
    logger.info(
        f"[version_1_0.diffs][diff_activities] produced={len(results)} activities"
    )
    return results


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    items = [
        {
            "id": "A1",
            "activity": "Pour foundation slab",
            "old_start": "01-05-2026",
            "new_start": "13-05-2026",
            "old_finish": "20-05-2026",
            "new_finish": "07-06-2026",
            "old_duration": "20",
            "new_duration": "17",
            "change_type": "Progress",
            "old": "44",
            "new": "30",
            "phase": "Slab",
            "area": "Bldg A",
            "trade": "Concrete",
        },
        {
            "id": "A2",
            "activity": "Install ductwork",
            "old_finish": "10-06-2026",
            "new_finish": "12-06-2026",
            "old_duration": "5",
            "new_duration": "5",
            "phase": "MEP",
            "area": "Bldg A",
            "trade": "VENT",
        },
        {
            "id": "A3",
            "activity": "Electrical rough-in",
            "old_start": "01-07-2026",
            "new_start": "08-07-2026",
            "old_finish": "20-07-2026",
            "new_finish": "27-07-2026",
            "phase": "MEP",
            "area": "Bldg A",
            "trade": "EL",
        },
    ]

    class _Issue:
        def __init__(self, field: str, severity: str = "warn") -> None:
            self.field = field
            self.severity = severity

    verifier = ValidationIssueVerifier({"A2": [_Issue("start", "warn")]})
    out = diff_activities(items, verifier=verifier)
    for ad in out:
        print(
            f"\n{ad.activity_id} :: {ad.activity_name!r} "
            f"changed_fields={ad.changed_fields} impact={ad.impact_score} verify={ad.verify}"
        )
        for fd in ad.field_diffs:
            print(
                f"   - {fd.field}: {fd.old!r} -> {fd.new!r} "
                f"delta={fd.delta!r} semantic={fd.semantic} verify={fd.verify}"
            )
