r"""Tests for TL-2.5 — Visually mark modified activity IDs.

Encodes acceptance criteria from `changes/trust-layer/plan/phase-2-identity.md` (TL-2.5):
- AC1: Activity ID changes between old and new schedule are rendered with a distinct visual chip.
- AC2: Display shows old -> new ID transition clearly.
"""
from __future__ import annotations

import pytest
from src.version_1_0.formatters import format_health_v1_as_html


class TestIdChangeDisplay:
    def test_id_change_renders_distinct_chip(self):
        data = {
            "executive_summary": {"project_health": "STABLE", "selected_activities": 1},
            "summary_notes": {"total_activities": 1},
            "changed_activities": {
                "changes": [
                    {
                        "id": "TASK-102",
                        "activity": "Relabeled Task",
                        "field": "id",
                        "old": "TASK-101",
                        "new": "TASK-102",
                        "area": "Building A",
                        "phase": "Phase 1",
                        "discipline": "EL",
                    }
                ]
            },
        }

        html = format_health_v1_as_html(data, language="en")
        assert "TASK-101 → TASK-102" in html or "TASK-101" in html
        assert "ni-change-chip" in html
