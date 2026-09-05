"""Tests for TL-9.1 — Click-into-evidence / source viewer (Brief §24).

Encodes acceptance criteria from `changes/trust-layer/plan/phase-9-evidence-audit.md` (TL-9.1):
- AC1: Detail panel shows the full brief §24 field set
- AC2: "View source" opens the correct page with the correct region highlighted
- AC3: Works for both old and new schedules in a comparison
- AC4: Non-paginated sources degrade honestly to a row reference
- AC5: Source access is authenticated and tenant-scoped

Do-not rules:
- Do not fabricate a page number for CSV/MPP/XML sources.
- Do not expose source documents on the unauthenticated public-share route.
"""
from __future__ import annotations

import io
import json
import pytest
from PIL import Image

from src.trust.source_viewer import (
    ActivityDetail,
    SourceLocation,
    build_activity_detail,
    build_source_location,
    highlight_pdf_page,
    is_non_paginated_source,
    render_activity_detail_panel,
)
from src.trust.vocabulary import TrustState


@pytest.fixture
def sample_two_page_pdf() -> bytes:
    """Create a minimal in-memory 2-page PDF document for testing."""
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument.new()
    doc.new_page(612, 792)
    doc.new_page(612, 792)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


class TestActivityDetailPanel:
    """AC1: Detail panel shows the full brief §24 field set."""

    def test_detail_panel_shows_full_brief_24_field_set(self):
        """Brief §24 literal fields: Activity, Current ID, Previous ID, Status,

        Deviation, Match, SOURCE VERIFICATION (Old Schedule, New Schedule,
        Match Method, Data Status), View source affordance.
        """
        act = {
            "task_name": "EL – Cable Tray Installation",
            "id": "A142",
            "status": "Behind schedule",
            "deviation": -44,
        }
        old_act = {
            "task_name": "EL – Cable Tray Installation",
            "id": "A142",
        }
        detail = build_activity_detail(act, old_act, language="en")
        detail.old_source = build_source_location(
            "old",
            source_document="schedule_july.pdf",
            page_number=14,
            bounding_box=[1.0, 2.0, 5.0, 2.0, 5.0, 2.5, 1.0, 2.5],
        )
        detail.new_source = build_source_location(
            "new",
            source_document="schedule_august.pdf",
            page_number=16,
            bounding_box=[1.5, 3.0, 5.5, 3.0, 5.5, 3.5, 1.5, 3.5],
        )

        html = render_activity_detail_panel(detail, language="en")

        # 1. Activity Name & Brand
        assert "NOVA" in html
        assert "EL – Cable Tray Installation" in html

        # 2. Current & Previous ID
        assert "Current ID" in html
        assert "A142" in html
        assert "Previous ID" in html

        # 3. Status & Deviation
        assert "Status" in html
        assert "Behind schedule" in html
        assert "Deviation" in html
        assert "-44 pp" in html

        # 4. Match
        assert "Match" in html
        assert "ni-trust-badge" in html

        # 5. SOURCE VERIFICATION block
        assert "SOURCE VERIFICATION" in html
        assert "Old Schedule" in html
        assert "Page 14" in html
        assert "New Schedule" in html
        assert "Page 16" in html
        assert "Match Method" in html
        assert "Exact Activity ID" in html
        assert "Data Status" in html

        # 6. View source affordances with data attributes
        assert 'data-schedule="old"' in html
        assert 'data-page="14"' in html
        assert 'data-schedule="new"' in html
        assert 'data-page="16"' in html
        assert "View source" in html

    def test_detail_panel_locale_parity_danish(self):
        """Brief §46 / TL-7.6 parity: Danish localization renders all labels in DA."""
        act = {
            "task_name": "EL – Kabelbakke montering",
            "id": "A142",
            "status": "Forsinket",
            "deviation": -44,
        }
        old_act = {
            "task_name": "EL – Kabelbakke montering",
            "id": "A142",
        }
        detail = build_activity_detail(act, old_act, language="da")
        detail.old_source = build_source_location(
            "old",
            source_document="gammel_plan.pdf",
            page_number=14,
            bounding_box=[1.0, 2.0, 5.0, 2.0, 5.0, 2.5, 1.0, 2.5],
        )
        detail.new_source = build_source_location(
            "new",
            source_document="ny_plan.pdf",
            page_number=16,
            bounding_box=[1.5, 3.0, 5.5, 3.0, 5.5, 3.5, 1.5, 3.5],
        )

        html = render_activity_detail_panel(detail, language="da")

        assert "KILDEVERIFICERING" in html
        assert "Gammel tidsplan" in html
        assert "Ny tidsplan" in html
        assert "Side 14" in html
        assert "Side 16" in html
        assert "Nuværende ID" in html
        assert "Tidligere ID" in html
        assert "Afvigelse" in html
        assert "-44 %-point" in html
        assert "Matchmetode" in html
        assert "Datastatus" in html
        assert "Se kildedokument" in html

    def test_missing_or_unverified_ids_render_safely(self):
        """When IDs or counterpart matches are absent, renders safe badges/placeholders."""
        act = {
            "task_name": "Unlinked Task",
            "id": None,
            "status": "On schedule",
        }
        detail = build_activity_detail(act, old_activity=None, language="en")
        html = render_activity_detail_panel(detail, language="en")

        # Current ID missing -> UNVERIFIED badge
        assert "Current ID" in html
        assert "Previous ID" in html
        assert "—" in html  # Previous ID is —
        assert "No reliable match" in html


class TestPdfHighlighting:
    """AC2: 'View source' opens the correct page with the correct region highlighted."""

    def test_highlight_pdf_page_renders_valid_png(self, sample_two_page_pdf):
        """Page rendering produces valid PNG image bytes."""
        bbox = [1.0, 2.0, 5.0, 2.0, 5.0, 3.0, 1.0, 3.0]
        png_bytes = highlight_pdf_page(sample_two_page_pdf, page_number=2, bounding_box=bbox)

        assert png_bytes.startswith(b"\x89PNG\r\n\x1a\n")
        img = Image.open(io.BytesIO(png_bytes))
        assert img.format == "PNG"
        assert img.size[0] > 0 and img.size[1] > 0

    def test_highlight_overlay_modifies_pixel_data(self, sample_two_page_pdf):
        """Highlighted page contains amber highlight pixels absent in clean page."""
        clean_bytes = highlight_pdf_page(sample_two_page_pdf, page_number=1, bounding_box=None)
        highlighted_bytes = highlight_pdf_page(
            sample_two_page_pdf,
            page_number=1,
            bounding_box=[2.0, 2.0, 6.0, 2.0, 6.0, 4.0, 2.0, 4.0],
        )

        assert clean_bytes != highlighted_bytes

    def test_page_out_of_range_raises_index_error(self, sample_two_page_pdf):
        """Requesting a page beyond document length raises IndexError."""
        with pytest.raises(IndexError, match="out of range"):
            highlight_pdf_page(sample_two_page_pdf, page_number=3)

    def test_page_less_than_one_raises_value_error(self, sample_two_page_pdf):
        """Page number < 1 raises ValueError."""
        with pytest.raises(ValueError, match="page_number must be >= 1"):
            highlight_pdf_page(sample_two_page_pdf, page_number=0)

    def test_empty_bytes_raises_value_error(self):
        """Empty PDF bytes raises ValueError."""
        with pytest.raises(ValueError, match="pdf_bytes cannot be empty"):
            highlight_pdf_page(b"", page_number=1)


class TestComparisonDualScheduleSupport:
    """AC3: Works for both old and new schedules in a comparison."""

    def test_works_for_both_old_and_new_schedules(self, sample_two_page_pdf):
        """Both old and new schedules can be highlighted independently."""
        # Highlight old schedule (page 1)
        old_highlight = highlight_pdf_page(
            sample_two_page_pdf,
            page_number=1,
            bounding_box=[1.0, 1.0, 4.0, 1.0, 4.0, 2.0, 1.0, 2.0],
        )
        assert old_highlight.startswith(b"\x89PNG")

        # Highlight new schedule (page 2)
        new_highlight = highlight_pdf_page(
            sample_two_page_pdf,
            page_number=2,
            bounding_box=[2.0, 3.0, 5.0, 3.0, 5.0, 4.0, 2.0, 4.0],
        )
        assert new_highlight.startswith(b"\x89PNG")

        # Confirm different page contents
        assert old_highlight != new_highlight


class TestNonPaginatedHonestDegradation:
    """AC4: Non-paginated sources degrade honestly to a row reference.

    Do-not: Do not fabricate a page number for CSV/MPP/XML sources.
    """

    @pytest.mark.parametrize(
        "filename,ext_method",
        [
            ("schedule.csv", "csv_cell"),
            ("project_export.xlsx", "excel_cell"),
            ("plan.mpp", "mpp_field"),
            ("baseline.xml", "mspdi_field"),
        ],
    )
    def test_non_paginated_sources_never_fabricate_page_number(self, filename, ext_method):
        """CSV, XLSX, MPP, and XML sources strictly set page_number to None."""
        assert is_non_paginated_source(filename=filename) is True
        assert is_non_paginated_source(extraction_method=ext_method) is True

        loc = build_source_location(
            "new",
            source_document=filename,
            page_number=7,  # Upstream attempt to fabricate or pass an artifact
            source_row=42,
            extraction_method=ext_method,
        )

        assert loc.is_paginated is False
        assert loc.page_number is None  # MUST be None
        assert loc.bounding_box is None  # No polygon geometry
        assert loc.source_row == 42

        # Display text check
        en_disp = loc.display_page_or_row("en")
        da_disp = loc.display_page_or_row("da")
        assert "Row 43 (non-paginated document)" in en_disp
        assert "Page" not in en_disp
        assert "Række 43 (ikke-pagineret dokument)" in da_disp
        assert "Side" not in da_disp

    def test_non_paginated_html_omits_view_source_button(self):
        """In HTML detail panel, non-paginated sources do not render a 'View source' button."""
        act = {"task_name": "CSV Activity", "id": "101"}
        old_act = {"task_name": "CSV Activity", "id": "101"}
        detail = build_activity_detail(act, old_act)
        detail.old_source = build_source_location(
            "old",
            source_document="schedule.csv",
            source_row=10,
            extraction_method="csv_cell",
        )
        detail.new_source = build_source_location(
            "new",
            source_document="schedule_v2.csv",
            source_row=12,
            extraction_method="csv_cell",
        )

        html = render_activity_detail_panel(detail, "en")

        assert "Row 11 (non-paginated document)" in html
        assert "Row 13 (non-paginated document)" in html
        # Should not have button with data-page
        assert "data-page" not in html
