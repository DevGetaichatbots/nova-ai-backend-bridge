"""Source viewer & click-into-evidence models and renderers (TL-9.1, Brief §24).

Brief §24: Click an activity, inspect:
- Activity name
- Current ID
- Previous ID
- Status
- Deviation
- Match confidence / trust state
- Source verification block:
  - Old schedule page (or row reference for non-paginated sources)
  - New schedule page (or row reference for non-paginated sources)
  - Match method
  - Data status
- "View source" affordance opening the source document at the recorded page
  with the recorded bounding box highlighted (TL-1.2 geometry).

Do-not rules:
- Never fabricate a page number for CSV/MPP/XML/Excel sources. Show the row
  reference and explicitly note that the source is a non-paginated document.
- Do not expose source documents on the unauthenticated public-share route.
"""
from __future__ import annotations

import io
import json
import logging
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

from pydantic import BaseModel, Field

from src.trust.vocabulary import TrustState

logger = logging.getLogger(__name__)

_NON_PAGINATED_EXTENSIONS = (".csv", ".xlsx", ".xls", ".mpp", ".xml")
_NON_PAGINATED_METHODS = (
    "csv_cell",
    "excel_cell",
    "mpp_field",
    "mspdi_field",
    "csv",
    "excel",
    "mpp",
    "mspdi",
)


def is_non_paginated_source(
    filename: Optional[str] = None,
    extraction_method: Optional[str] = None,
) -> bool:
    """Check whether a document source is non-paginated (CSV, Excel, MPP, XML)."""
    if filename:
        fn_lower = filename.strip().lower()
        if any(fn_lower.endswith(ext) for ext in _NON_PAGINATED_EXTENSIONS):
            return True
    if extraction_method:
        meth_lower = extraction_method.strip().lower()
        if meth_lower in _NON_PAGINATED_METHODS:
            return True
    return False


class SourceScheduleRole(str, Enum):
    OLD = "old"
    NEW = "new"
    SINGLE = "single"


class SourceLocation(BaseModel):
    """Provenance location for an activity in a schedule source document."""

    schedule_role: str = "new"  # "old", "new", or "single"
    source_document: Optional[str] = None
    page_number: Optional[int] = Field(None, ge=1)
    bounding_box: Optional[List[float]] = None  # Polygon coords: [x1, y1, x2, y2, x3, y3, x4, y4]
    source_row: Optional[int] = None
    is_paginated: bool = True
    raw_value: Optional[str] = None
    extraction_method: Optional[str] = None

    def display_page_or_row(self, language: str = "en") -> str:
        """Display page number or row reference with honest non-paginated degradation."""
        is_da = str(language).lower().startswith("da")
        if not self.is_paginated or self.page_number is None:
            if self.source_row is not None:
                # 1-indexed display for end users
                row_disp = self.source_row + 1 if self.source_row >= 0 else self.source_row
                return (
                    f"Række {row_disp} (ikke-pagineret dokument)"
                    if is_da
                    else f"Row {row_disp} (non-paginated document)"
                )
            return (
                "Ikke-pagineret dokument"
                if is_da
                else "Non-paginated document"
            )
        return f"Side {self.page_number}" if is_da else f"Page {self.page_number}"


class ActivityDetail(BaseModel):
    """Brief §24 target interaction field set for an activity."""

    activity_name: str
    current_id: Optional[str] = None
    previous_id: Optional[str] = None
    status: str = "On schedule"
    deviation: Optional[str] = None
    match_method: str = "Exact Activity ID"
    match_trust: TrustState = TrustState.VERIFIED
    data_status: TrustState = TrustState.VERIFIED
    old_source: Optional[SourceLocation] = None
    new_source: Optional[SourceLocation] = None


def build_source_location(
    schedule_role: str,
    provenance: Optional[Dict[str, Any]] = None,
    *,
    source_document: Optional[str] = None,
    source_row: Optional[int] = None,
    page_number: Optional[int] = None,
    bounding_box: Optional[List[float]] = None,
    extraction_method: Optional[str] = None,
    raw_value: Optional[str] = None,
) -> SourceLocation:
    """Build a SourceLocation object, strictly enforcing non-paginated degradation."""
    prov_dict = provenance or {}

    # Extract best candidate provenance field (preferring name or source_id)
    target_prov = None
    if isinstance(prov_dict, dict):
        for candidate_key in ("source_id", "name", "task_name", "activity", "planned_start"):
            if candidate_key in prov_dict and prov_dict[candidate_key]:
                target_prov = prov_dict[candidate_key]
                break
        if target_prov is None and prov_dict:
            target_prov = next(iter(prov_dict.values()))

    # Resolve values from target_prov if not explicitly overridden
    if target_prov:
        if hasattr(target_prov, "source_document") and source_document is None:
            source_document = getattr(target_prov, "source_document", None)
        elif isinstance(target_prov, dict) and source_document is None:
            source_document = target_prov.get("source_document")

        if hasattr(target_prov, "page_number") and page_number is None:
            page_number = getattr(target_prov, "page_number", None)
        elif isinstance(target_prov, dict) and page_number is None:
            page_number = target_prov.get("page_number")

        if hasattr(target_prov, "bounding_box") and bounding_box is None:
            bounding_box = getattr(target_prov, "bounding_box", None)
        elif isinstance(target_prov, dict) and bounding_box is None:
            bounding_box = target_prov.get("bounding_box")

        if hasattr(target_prov, "source_row") and source_row is None:
            source_row = getattr(target_prov, "source_row", None)
        elif isinstance(target_prov, dict) and source_row is None:
            source_row = target_prov.get("source_row")

        if hasattr(target_prov, "extraction_method") and extraction_method is None:
            extraction_method = getattr(target_prov, "extraction_method", None)
        elif isinstance(target_prov, dict) and extraction_method is None:
            extraction_method = target_prov.get("extraction_method")

        if hasattr(target_prov, "raw_value") and raw_value is None:
            raw_value = getattr(target_prov, "raw_value", None)
        elif isinstance(target_prov, dict) and raw_value is None:
            raw_value = target_prov.get("raw_value")

    # Enforce non-paginated degradation (TL-9.1 AC4, brief §24 Do-not rule)
    if is_non_paginated_source(source_document, extraction_method):
        return SourceLocation(
            schedule_role=schedule_role,
            source_document=source_document,
            page_number=None,  # NEVER fabricate page number
            bounding_box=None,
            source_row=source_row,
            is_paginated=False,
            raw_value=raw_value,
            extraction_method=extraction_method,
        )

    return SourceLocation(
        schedule_role=schedule_role,
        source_document=source_document,
        page_number=page_number,
        bounding_box=bounding_box,
        source_row=source_row,
        is_paginated=True if page_number is not None else False,
        raw_value=raw_value,
        extraction_method=extraction_method,
    )


def build_activity_detail(
    activity: Dict[str, Any],
    old_activity: Optional[Dict[str, Any]] = None,
    match_result: Optional[Any] = None,
    *,
    new_provenance: Optional[Dict[str, Any]] = None,
    old_provenance: Optional[Dict[str, Any]] = None,
    language: str = "en",
) -> ActivityDetail:
    """Build the full Brief §24 detail model for an activity."""
    act_name = (
        activity.get("task_name")
        or activity.get("activity")
        or activity.get("name")
        or "Unnamed Activity"
    )

    current_id = activity.get("id") or activity.get("source_id") or None
    previous_id = (
        old_activity.get("id") or old_activity.get("source_id") if old_activity else None
    )

    status_val = str(activity.get("status") or activity.get("priority") or "On schedule")

    dev_val = activity.get("deviation")
    formatted_dev = None
    if dev_val is not None:
        try:
            fdev = float(dev_val)
            sign = "+" if fdev > 0 else ""
            is_da = str(language).lower().startswith("da")
            unit = "%-point" if is_da else "pp"
            formatted_dev = f"{sign}{fdev:.0f} {unit}"
        except (ValueError, TypeError):
            formatted_dev = str(dev_val)

    # Match method & trust
    if match_result:
        method = getattr(match_result, "method", "Matching algorithm")
        level = getattr(match_result, "level", None)
        level_str = getattr(level, "value", str(level)) if level else ""
        if "L1" in level_str or "EXACT" in level_str.upper():
            match_trust = TrustState.VERIFIED
        elif "L2" in level_str or "L3" in level_str or "PARTIAL" in level_str:
            match_trust = TrustState.REVIEW
        else:
            match_trust = TrustState.UNVERIFIED
    elif old_activity:
        method = str(activity.get("match_method") or "Exact Activity ID")
        match_trust = TrustState.VERIFIED
    else:
        is_da = str(language).lower().startswith("da")
        method = "Ingen pålidelig match" if is_da else "No reliable match"
        match_trust = TrustState.UNVERIFIED

    # Data status
    data_status = TrustState.VERIFIED
    if activity.get("has_logic_warning") or activity.get("requires_verification"):
        data_status = TrustState.REVIEW

    # Sources
    new_source = build_source_location(
        "new",
        new_provenance or activity.get("provenance"),
        source_document=activity.get("source_document") or activity.get("filename"),
        source_row=activity.get("source_row"),
        page_number=activity.get("page_number"),
        bounding_box=activity.get("bounding_box"),
        extraction_method=activity.get("extraction_method"),
    )

    old_source = None
    if old_activity:
        old_source = build_source_location(
            "old",
            old_provenance or old_activity.get("provenance"),
            source_document=old_activity.get("source_document") or old_activity.get("filename"),
            source_row=old_activity.get("source_row"),
            page_number=old_activity.get("page_number"),
            bounding_box=old_activity.get("bounding_box"),
            extraction_method=old_activity.get("extraction_method"),
        )

    return ActivityDetail(
        activity_name=act_name,
        current_id=current_id,
        previous_id=previous_id,
        status=status_val,
        deviation=formatted_dev,
        match_method=method,
        match_trust=match_trust,
        data_status=data_status,
        old_source=old_source,
        new_source=new_source,
    )


def _render_badge_html(state: TrustState, language: str, *, suppress_verified: bool = False) -> str:
    """Render a canonical trust badge pill for a given TrustState."""
    from src.version_1_0.formatters import _trust_badge
    return _trust_badge(state, language, suppress_verified=suppress_verified)


def render_activity_detail_panel(detail: ActivityDetail, language: str = "en") -> str:
    """Render HTML for the Brief §24 Activity Detail Panel & Source Verification Block."""
    is_da = str(language).lower().startswith("da")

    lbl_activity = "Aktivitet" if is_da else "Activity"
    lbl_current_id = "Nuværende ID" if is_da else "Current ID"
    lbl_prev_id = "Tidligere ID" if is_da else "Previous ID"
    lbl_status = "Status"
    lbl_deviation = "Afvigelse" if is_da else "Deviation"
    lbl_match = "Match"
    lbl_source_ver = "KILDEVERIFICERING" if is_da else "SOURCE VERIFICATION"
    lbl_old_schedule = "Gammel tidsplan" if is_da else "Old Schedule"
    lbl_new_schedule = "Ny tidsplan" if is_da else "New Schedule"
    lbl_match_method = "Matchmetode" if is_da else "Match Method"
    lbl_data_status = "Datastatus" if is_da else "Data Status"
    lbl_view_source = "Se kildedokument" if is_da else "View source"
    lbl_none = "—"

    # Current & previous ID display
    curr_id_disp = detail.current_id if detail.current_id else _render_badge_html(TrustState.UNVERIFIED, language)
    prev_id_disp = detail.previous_id if detail.previous_id else lbl_none

    # Status display
    status_disp = detail.status

    # Deviation display
    dev_disp = detail.deviation if detail.deviation else lbl_none

    # Match badge
    match_badge = _render_badge_html(detail.match_trust, language)
    data_badge = _render_badge_html(detail.data_status, language)

    # Old source block
    if detail.old_source:
        old_loc_text = detail.old_source.display_page_or_row(language)
        if detail.old_source.is_paginated and detail.old_source.page_number is not None:
            bbox_attr = json.dumps(detail.old_source.bounding_box or [])
            old_action = (
                f'<button type="button" class="ni-view-source-btn" data-schedule="old" '
                f'data-page="{detail.old_source.page_number}" data-bbox="{bbox_attr}" '
                f'onclick="niV1ViewSource(this)">{lbl_view_source}</button>'
            )
        else:
            old_action = f'<span class="ni-source-non-paginated-tag">{old_loc_text}</span>'
    else:
        old_loc_text = lbl_none
        old_action = ""

    # New source block
    if detail.new_source:
        new_loc_text = detail.new_source.display_page_or_row(language)
        if detail.new_source.is_paginated and detail.new_source.page_number is not None:
            bbox_attr = json.dumps(detail.new_source.bounding_box or [])
            new_action = (
                f'<button type="button" class="ni-view-source-btn" data-schedule="new" '
                f'data-page="{detail.new_source.page_number}" data-bbox="{bbox_attr}" '
                f'onclick="niV1ViewSource(this)">{lbl_view_source}</button>'
            )
        else:
            new_action = f'<span class="ni-source-non-paginated-tag">{new_loc_text}</span>'
    else:
        new_loc_text = lbl_none
        new_action = ""

    html = f"""
<div class="ni-activity-detail-card" role="region" aria-label="{lbl_activity} {detail.activity_name}">
  <div class="ni-activity-detail-header">
    <span class="ni-activity-brand">NOVA</span>
    <h4 class="ni-activity-detail-name">{detail.activity_name}</h4>
  </div>

  <div class="ni-activity-detail-grid">
    <div class="ni-activity-detail-item">
      <span class="ni-activity-detail-k">{lbl_current_id}</span>
      <span class="ni-activity-detail-v">{curr_id_disp}</span>
    </div>
    <div class="ni-activity-detail-item">
      <span class="ni-activity-detail-k">{lbl_prev_id}</span>
      <span class="ni-activity-detail-v">{prev_id_disp}</span>
    </div>
    <div class="ni-activity-detail-item">
      <span class="ni-activity-detail-k">{lbl_status}</span>
      <span class="ni-activity-detail-v">{status_disp}</span>
    </div>
    <div class="ni-activity-detail-item">
      <span class="ni-activity-detail-k">{lbl_deviation}</span>
      <span class="ni-activity-detail-v">{dev_disp}</span>
    </div>
    <div class="ni-activity-detail-item">
      <span class="ni-activity-detail-k">{lbl_match}</span>
      <span class="ni-activity-detail-v">{match_badge}</span>
    </div>
  </div>

  <div class="ni-source-verification">
    <div class="ni-source-verification-title">{lbl_source_ver}</div>
    <div class="ni-source-verification-grid">
      <div class="ni-source-row">
        <span class="ni-source-label">{lbl_old_schedule}</span>
        <span class="ni-source-value">{old_loc_text}</span>
        {old_action}
      </div>
      <div class="ni-source-row">
        <span class="ni-source-label">{lbl_new_schedule}</span>
        <span class="ni-source-value">{new_loc_text}</span>
        {new_action}
      </div>
      <div class="ni-source-row">
        <span class="ni-source-label">{lbl_match_method}</span>
        <span class="ni-source-value">{detail.match_method}</span>
      </div>
      <div class="ni-source-row">
        <span class="ni-source-label">{lbl_data_status}</span>
        <span class="ni-source-value">{data_badge}</span>
      </div>
    </div>
  </div>
</div>
"""
    return html.strip()


def _scale_polygon_to_pixels(
    coords: List[float],
    img_w: int,
    img_h: int,
    page_w_pts: float,
    page_h_pts: float,
) -> List[Tuple[float, float]]:
    """Convert polygon coordinates (from Azure OCR inches/points/pixels) to image pixel space."""
    if len(coords) < 4:
        return []

    # If coords are 4 numbers: [x, y, w, h] or [x1, y1, x2, y2]
    if len(coords) == 4:
        x1, y1, x2, y2 = coords
        coords = [x1, y1, x2, y1, x2, y2, x1, y2]

    xs = coords[0::2]
    ys = coords[1::2]
    max_x = max(xs) if xs else 0
    max_y = max(ys) if ys else 0

    # Determine coordinate unit
    page_w_in = page_w_pts / 72.0 if page_w_pts > 0 else 8.5
    page_h_in = page_h_pts / 72.0 if page_h_pts > 0 else 11.0

    if max_x <= page_w_in * 1.5 and max_y <= page_h_in * 1.5:
        # Inches (standard Azure Document Intelligence)
        scale_x = img_w / page_w_in
        scale_y = img_h / page_h_in
    elif max_x <= 1.0 and max_y <= 1.0:
        # Normalized [0, 1]
        scale_x = img_w
        scale_y = img_h
    elif page_w_pts > 0 and page_h_pts > 0 and max_x <= page_w_pts * 1.5 and max_y <= page_h_pts * 1.5:
        # Points (PDF points, 72 dpi)
        scale_x = img_w / page_w_pts
        scale_y = img_h / page_h_pts
    else:
        # Already image pixel space or unknown
        scale_x = 1.0
        scale_y = 1.0

    points = []
    for x, y in zip(xs, ys):
        px = max(0.0, min(float(img_w), float(x * scale_x)))
        py = max(0.0, min(float(img_h), float(y * scale_y)))
        points.append((px, py))

    return points


def highlight_pdf_page(
    pdf_bytes: bytes,
    page_number: int,
    bounding_box: Optional[List[float]] = None,
    *,
    scale: float = 2.0,
) -> bytes:
    """Render a target page of a PDF document with an amber highlight overlay on bounding_box.

    Args:
        pdf_bytes: Raw bytes of the PDF document.
        page_number: 1-indexed page number.
        bounding_box: Optional list of polygon coordinates [x1, y1, x2, y2, x3, y3, x4, y4].
        scale: Resolution scale factor (default 2.0 = 144 DPI for sharp display).

    Returns:
        PNG image bytes of the rendered page with highlight.

    Raises:
        ValueError: If page_number < 1 or pdf_bytes is empty.
        IndexError: If page_number > number of pages in the PDF.
    """
    if not pdf_bytes:
        raise ValueError("pdf_bytes cannot be empty")
    if page_number < 1:
        raise ValueError(f"page_number must be >= 1, got {page_number}")

    import pypdfium2 as pdfium
    from PIL import Image, ImageDraw

    try:
        doc = pdfium.PdfDocument(pdf_bytes)
    except Exception as e:
        raise ValueError(f"Failed to parse PDF document: {e}") from e

    total_pages = len(doc)
    if page_number > total_pages:
        raise IndexError(
            f"Page {page_number} is out of range (document has {total_pages} page{'s' if total_pages != 1 else ''})"
        )

    page = doc[page_number - 1]
    page_w_pts, page_h_pts = page.get_size()

    # Render page to PIL image
    pil_image = page.render(scale=scale).to_pil()
    img_w, img_h = pil_image.size

    # Draw highlight overlay if bounding_box is provided
    if bounding_box and len(bounding_box) >= 4:
        points = _scale_polygon_to_pixels(bounding_box, img_w, img_h, page_w_pts, page_h_pts)
        if len(points) >= 3:
            overlay = Image.new("RGBA", (img_w, img_h), (255, 255, 255, 0))
            draw = ImageDraw.Draw(overlay)

            # Amber highlight (Brief §24: clear, high-visibility highlight)
            # Fill: RGBA (245, 158, 11, 90) -> translucent amber
            # Outline: RGBA (217, 119, 6, 255) -> solid dark amber border
            outline_width = max(2, int(2 * scale))
            draw.polygon(points, fill=(245, 158, 11, 90), outline=(217, 119, 6, 255), width=outline_width)

            if pil_image.mode != "RGBA":
                pil_image = pil_image.convert("RGBA")
            pil_image = Image.alpha_composite(pil_image, overlay).convert("RGB")

    output = io.BytesIO()
    pil_image.save(output, format="PNG")
    return output.getvalue()


__all__ = [
    "SourceScheduleRole",
    "SourceLocation",
    "ActivityDetail",
    "is_non_paginated_source",
    "build_source_location",
    "build_activity_detail",
    "render_activity_detail_panel",
    "highlight_pdf_page",
]
