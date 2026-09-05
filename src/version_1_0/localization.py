from __future__ import annotations


LABELS = {
    "en": {
        "brand": "Nova Insight",
        "health_title": "PROJECT HEALTH",
        "predictive_title": "PREDICTIVE",
        "subtitle": "What should I act on today?",
        "filters": "Filters",
        "all": "All",
        "all_items": "All",
        "now": "Now",
        "unassigned": "Unassigned",
        "building": "Building / Area",
        "phase": "Phase",
        "floor": "Floor",
        "trade": "Trade / Discipline",
        "task_type": "Task Type",
        "activities_analyzed": "Activities analyzed",
        "critical_activities": "Critical activities",
        "point_no_return": "Point of no return",
        "delayed_activities": "Delayed activities",
        "important_next": "Important next",
        "monitor": "Monitor",
        "highest_risk": "Highest risk",
        "graph_title_health": "Progress Over Time",
        "graph_title_predictive": "Schedule Risk Outlook",
        "graph_subtitle_health": "Planned vs actual progress from available schedule data",
        "graph_subtitle_predictive": "Actual progress and delay risk from available schedule data",
        "actual": "Actual",
        "planned": "Schedule",
        "forecast": "Forecast",
        "delay": "Delay",
        "today": "Today",
        "finish_late": "Finish late",
        "data_quality": "Data quality",
        "no_graph_data": "Not enough progress data to render a reliable curve.",
        "area_progress": "Current Extract",
        "area_progress_sub": "Ranked area / phase progress",
        "progress": "Progress",
        "behind_table": "Behind Schedule",
        "ahead_table": "Ahead of Schedule",
        "changed_table": "Changed Activities",
        "stage_table": "Current Stage Analysis",
        "critical_path_table": "Critical Path Activities",
        "kemp_details": "Advanced details",
        "kemp_toggle_label": "Show Full overview",
        "overview_label": "Overview",
        "overview_toggle_label": "Show Overview",
        "summary_notes": "Summary & Notes",
        "summary_notes_sub": "Report facts for export and handover",
        "analysis_generated": "Analysis generated",
        "old_schedule_date": "Old schedule date",
        "new_schedule_date": "New schedule date",
        "actions": "What Should You Do Now",
        "critical_now": "Critical Now",
        "all_delayed": "All Delayed Activities",
        "root_causes": "Root Causes",
        "id": "ID",
        "task_name": "Activity Name",
        "phase_col": "Phase",
        "actual_col": "Actual",
        "expected_col": "Expected",
        "deviation_col": "Deviation",
        "ahead_col": "Ahead",
        "start_col": "Start",
        "finish_col": "Finish",
        "duration_col": "Duration",
        "old_start_col": "Old start",
        "new_start_col": "New start",
        "old_finish_col": "Old finish",
        "new_finish_col": "New finish",
        "old_duration_col": "Old duration",
        "new_duration_col": "New duration",
        "change_col": "Change",
        "before_col": "Before",
        "after_col": "After",
        "float_col": "Float",
        "not_available": "N/A",
        "completed_activities": "Completed activities",
        "total_activities": "Total activities",
        "removed_activities": "Removed activities",
        "added_activities": "Added activities",
        "overall_progress": "Overall progress",
        "reporting_period": "Reporting period",
        "notes": "Notes",
        "risk_bucket_note": "Delay aging view based on delayed activities; this is not a progress-over-time curve.",
        "no_notes": "No additional notes.",
        "new_start": "New start",
        "new_finish": "New finish",
        "status_col": "Status",
        "days_overdue": "Days overdue",
        "priority": "Priority",
        "sort": "Sort",
        "none": "None",
        "change_compact": "Change",
        "changed_field_start": "Start",
        "changed_field_finish": "Finish",
        "changed_field_duration": "Duration",
        "changed_field_progress": "Progress",
        "changed_field_id": "ID",
        "changed_field_multiple": "Multiple",
        "sort_impact": "Impact",
        "sort_impact_desc": "Largest impact",
        "sort_impact_asc": "Smallest impact",
        "sort_id_asc": "ID (A-Z)",
        "sort_task_asc": "Activity name (A-Z)",
        "unable_to_verify_change": "Unable to verify change",
        "expand_row": "Expand row",
        "collapse_row": "Collapse row",
        "filter_by": "Filter",
        "sort_by": "Sort by",
        "chips_unit_days": "d",
        "chips_unit_pp": "pp",
        "day_singular": "day",
        "day_plural": "days",
        "change_earlier": "earlier",
        "change_later": "later",
        "change_longer": "longer",
        "change_shorter": "shorter",
        "change_pp_higher": "pp higher",
        "change_pp_lower": "pp lower",
        # --- Trust layer (TL-0.4). All keys prefixed `trust_` so a single
        # regex audit can find every trust-related string. Brief §21, §45,
        # §46 are the source of truth. ---
        # Trust state labels (user-facing, brief §46 wording)
        "trust_state_verified": "Verified",
        "trust_state_review": "Review Recommended",
        "trust_state_unverified": "Unable to Verify",
        # Trust state tooltips (brief §21 wording — verbatim)
        "trust_state_verified_tt": "Verified against source schedule.",
        "trust_state_review_tt": "Nova identified uncertainty in the source data or activity match. Review recommended.",
        "trust_state_unverified_tt": "Nova could not reliably verify this value. It has not been used as confirmed data.",
        # Source-conflict flag (brief §46; flag, not a fourth state)
        "trust_source_conflict": "Source Conflict",
        "trust_source_conflict_tt": "The source schedule contains inconsistent values for this item.",
        # Claim kinds (brief §19)
        "trust_claim_fact": "Fact",
        "trust_claim_derived_fact": "Derived Fact",
        "trust_claim_inference": "Inference",
        "trust_claim_unknown": "Unknown",
        "trust_claim_fact_tt": "Directly supported by source or calculation.",
        "trust_claim_derived_fact_tt": "Deterministically calculated from the data.",
        "trust_claim_inference_tt": "Evidence suggests this, but does not prove it.",
        "trust_claim_unknown_tt": "Insufficient evidence.",
        # Evidence classes (brief §45 / §46)
        "trust_evidence_source_data": "Source Data",
        "trust_evidence_nova_calculation": "Nova Calculation",
        "trust_evidence_nova_insight": "Nova Insight",
        "trust_evidence_nova_forecast": "Nova Forecast",
        "trust_evidence_source_data_tt": "What the schedule says.",
        "trust_evidence_nova_calculation_tt": "What Nova deterministically calculated.",
        "trust_evidence_nova_insight_tt": "What Nova inferred/interpreted.",
        "trust_evidence_nova_forecast_tt": "What Nova predicts.",
        # Evidence class labels (TL-7.3, brief §45/§46). Distinct from the
        # `trust_evidence_*_tt` tooltips above — these are the *visible
        # labels* the chip carries. Brief §46 terminology is exact and
        # load-bearing for trust: "Source data", "Nova calculation",
        # "Nova insight", "Nova forecast" — never "AI thinks" or similar.
        # The Danish block mirrors the same vocabulary (brief §46:
        # Kemp is Danish-only; the same load-bearing strings apply).
        "evidence_class_source_data": "Source data",
        "evidence_class_source_data_tt": "What the schedule says — verbatim from the source.",
        "evidence_class_nova_calculation": "Nova calculation",
        "evidence_class_nova_calculation_tt": "Deterministically computed by Nova from the source data.",
        "evidence_class_nova_insight": "Nova insight",
        "evidence_class_nova_insight_tt": "Nova's interpretation of the source data.",
        "evidence_class_nova_forecast": "Nova forecast",
        "evidence_class_nova_forecast_tt": "Nova's prediction about the future.",
        "evidence_class_legend": "Evidence source",
        # Project-level trust indicator (TL-7.2, brief §22/§23). Never the
        # word "accurate" anywhere in this block — brief §23 is explicit
        # that confidence and accuracy are not the same claim.
        "trust_project_heading": "Trust in this analysis",
        "trust_project_summary": "{verified} of {total} activities passed Nova's verification rules",
        "trust_breakdown_verified": "verified",
        "trust_breakdown_review": "require review",
        "trust_breakdown_unresolved": "could not be reliably matched",
        "trust_denominator_tt": "{total} is the total number of activities Nova examined in this comparison — the same count shown as \"Activities Analyzed\" above. Of those, {verified} passed Nova's verification rules cleanly, {review} were flagged for manual review, and {unresolved} could not be reliably matched between the two schedules.",
        "trust_denominator_tt_all_verified": "{total} is the total number of activities Nova examined in this comparison — the same count shown as \"Activities Analyzed\" above. All {verified} passed Nova's verification rules cleanly (no rows flagged for review, none unresolved).",
        "trust_denominator_tt_predictive": "{total} is the total number of activities in this schedule. Of the {delayed} flagged as delayed, {unresolved} could not be reliably confirmed from the source data and are excluded from this count.",
        "trust_feature_schedule_parsing": "Schedule Parsing",
        "trust_feature_activity_matching": "Activity Matching",
        "trust_feature_progress_comparison": "Progress Comparison",
        "trust_feature_critical_path": "Critical Path",
        "trust_feature_forecast": "Forecast",
        "trust_feature_not_available": "Not available",
        # --- Forecast surface (TL-7.4, brief §31). Forecast-specific labels
        # for the predictive snapshot card. Never the word "prediction" in a
        # KPI tile — these labels only appear inside `.ni-forecast-panel`.
        "forecast_outlook_heading": "Forecast Outlook",
        "forecast_what_will_happen": "What will happen",
        "forecast_delay_impact": "Estimated delay impact",
        "forecast_confidence_high": "High",
        "forecast_confidence_medium": "Medium",
        "forecast_confidence_low": "Low confidence \u2014 interpret with caution",
        "forecast_key_drivers": "Key delay drivers",
        "forecast_basis": "Nova confidence basis",
        "forecast_biggest_risk": "Biggest Risk",
        "forecast_will_block": "Will block",
        "forecast_prevent_action": "Prevent with",
        "forecast_no_delay_observed": "No delays observed \u2014 structural risk analysis",
        # TL-7.5 \u2014 "Why?" explanations (brief \u00a732). Assembled from
        # already-recorded deterministic facts (TL-5.2's root-cause/
        # downstream classification, TL-7.2's trust breakdown) \u2014 never
        # generated by a model.
        "why_button": "Why?",
        "why_root_cause": "This task is a root cause \u2014 its delay is not caused by another delayed task.",
        "why_downstream_of": "This is a downstream consequence of {id}, which is also delayed.",
        "why_days_overdue": "{days} days overdue.",
        "why_action_related": "Based on {count} related delayed activities identified in this schedule.",
        # TL-7.7 (brief §44): "Do not make dashboard transparent but PDF
        # reports absolute." A PDF cannot hover for a tooltip and is
        # often read without the page-one trust panel still in view —
        # this footer restates the one fact that matters when the
        # comparison was not fully clean, in plain print-readable text.
        "pdf_methodology_footer": "⚠ Based on partially verified activity matching.",
        # TL-9.1 — Click-into-evidence / source viewer (brief §24)
        "evidence_detail": "Activity Evidence",
        "evidence_current_id": "Current ID",
        "evidence_previous_id": "Previous ID",
        "evidence_deviation": "Deviation",
        "evidence_source_verification": "SOURCE VERIFICATION",
        "evidence_old_schedule": "Old Schedule",
        "evidence_new_schedule": "New Schedule",
        "evidence_match_method": "Match Method",
        "evidence_data_status": "Data Status",
        "evidence_view_source": "View source",
        "evidence_non_paginated": "Non-paginated document",
    },
    "da": {
        "brand": "Nova Insight",
        "health_title": "PROJEKTSUNDHED",
        "predictive_title": "PROGNOSE",
        "subtitle": "Hvad skal jeg handle på i dag?",
        "filters": "Filtre",
        "all": "Alle",
        "all_items": "Alle",
        "now": "Nu",
        "unassigned": "Ikke tildelt",
        "building": "Bygning / Område",
        "phase": "Fase / Etape",
        "floor": "Etage",
        "trade": "Fag / Disciplin",
        "task_type": "Opgavetype",
        "activities_analyzed": "Aktiviteter analyseret",
        "critical_activities": "Kritiske aktiviteter",
        "point_no_return": "Point of no return",
        "delayed_activities": "Forsinkede aktiviteter",
        "important_next": "Vigtig næste",
        "monitor": "Overvåg",
        "highest_risk": "Største risiko",
        "graph_title_health": "Fremdrift over tid",
        "graph_title_predictive": "Risiko og prognose",
        "graph_subtitle_health": "Planlagt vs faktisk fremdrift fra tilgængelige tidsplandata",
        "graph_subtitle_predictive": "Faktisk fremdrift og forsinkelsesrisiko fra tilgængelige tidsplandata",
        "actual": "Faktisk",
        "planned": "Plan",
        "forecast": "Prognose",
        "delay": "Forsinkelse",
        "today": "I dag",
        "finish_late": "Slutter sent",
        "data_quality": "Datakvalitet",
        "no_graph_data": "Ikke nok fremdriftsdata til at vise en pålidelig kurve.",
        "area_progress": "Aktuelt udtræk",
        "area_progress_sub": "Rangeret område / fase-fremdrift",
        "progress": "Fremdrift",
        "behind_table": "Bagud i planen",
        "ahead_table": "Foran planen",
        "changed_table": "Ændrede aktiviteter",
        "stage_table": "Analyse af stade d.d.",
        "critical_path_table": "Kritiske vej-aktiviteter",
        "kemp_details": "Avancerede detaljer",
        "kemp_toggle_label": "Vis Fuld oversigt",
        "overview_label": "Overblik",
        "overview_toggle_label": "Vis fuld oversigt",
        "summary_notes": "Opsummering & noter",
        "summary_notes_sub": "Rapportfakta til eksport og overlevering",
        "analysis_generated": "Analyse genereret",
        "old_schedule_date": "Gammel plan dato",
        "new_schedule_date": "Ny plan dato",
        "actions": "Hvad skal du gøre nu",
        "critical_now": "Kritisk nu",
        "all_delayed": "Alle forsinkede aktiviteter",
        "root_causes": "Rodårsager",
        "id": "ID",
        "task_name": "Emne / Opgavenavn",
        "phase_col": "Etape / fase",
        "actual_col": "Oplyst stade",
        "expected_col": "Stade planlagt",
        "deviation_col": "Afvigelse",
        "ahead_col": "Forspring",
        "start_col": "Startdato",
        "finish_col": "Slutdato",
        "duration_col": "Varighed",
        "old_start_col": "Gammel start",
        "new_start_col": "Ny start",
        "old_finish_col": "Gammel slut",
        "new_finish_col": "Ny slut",
        "old_duration_col": "Gammel varighed",
        "new_duration_col": "Ny varighed",
        "change_col": "Ændring",
        "before_col": "Før",
        "after_col": "Efter",
        "float_col": "Float",
        "not_available": "Ikke oplyst",
        "completed_activities": "Afsluttede aktiviteter",
        "total_activities": "Aktiviteter i alt",
        "removed_activities": "Fjernede aktiviteter",
        "added_activities": "Tilføjede aktiviteter",
        "overall_progress": "Samlet fremdrift",
        "reporting_period": "Rapporteringsperiode",
        "notes": "Noter",
        "risk_bucket_note": "Forsinkelsesalder baseret på forsinkede aktiviteter; dette er ikke en fremdriftskurve over tid.",
        "no_notes": "Ingen yderligere noter.",
        "new_start": "Ny startdato",
        "new_finish": "Ny slutdato",
        "status_col": "Status",
        "days_overdue": "Dage over",
        "priority": "Prioritet",
        "sort": "Sorter",
        "none": "Ingen",
        "change_compact": "Ændring",
        "changed_field_start": "Start",
        "changed_field_finish": "Slut",
        "changed_field_duration": "Varighed",
        "changed_field_progress": "Fremdrift",
        "changed_field_id": "ID",
        "changed_field_multiple": "Flere",
        "sort_impact": "Betydning",
        "sort_impact_desc": "Størst betydning",
        "sort_impact_asc": "Mindst betydning",
        "sort_id_asc": "ID (A-Å)",
        "sort_task_asc": "Aktivitetsnavn (A-Å)",
        "unable_to_verify_change": "Ændringen kan ikke verificeres",
        "expand_row": "Vis detaljer",
        "collapse_row": "Skjul detaljer",
        "filter_by": "Filtrér",
        "sort_by": "Sortér efter",
        "chips_unit_days": "d",
        "chips_unit_pp": "pp",
        "day_singular": "dag",
        "day_plural": "dage",
        "change_earlier": "tidligere",
        "change_later": "senere",
        "change_longer": "længere",
        "change_shorter": "kortere",
        "change_pp_higher": "pp højere",
        "change_pp_lower": "pp lavere",
        # --- Trust layer (TL-0.4). Initial DA translations pending K&L
        # sign-off (external dependency EXT-2 in PROGRESS.md). ---
        # Trust state labels
        "trust_state_verified": "Verificeret",
        "trust_state_review": "Kontrol anbefales",
        "trust_state_unverified": "Kan ikke verificeres",
        # Trust state tooltips
        "trust_state_verified_tt": "Verificeret mod kildetidsplanen.",
        "trust_state_review_tt": "Nova har identificeret usikkerhed i kildedata eller aktivitetsmatch. Kontrol anbefales.",
        "trust_state_unverified_tt": "Nova kunne ikke pålideligt verificere denne værdi. Den er ikke brugt som bekræftet data.",
        # Source-conflict flag
        "trust_source_conflict": "Datakonflikt",
        "trust_source_conflict_tt": "Kildetidsplanen indeholder modstridende værdier for dette punkt.",
        # Claim kinds
        "trust_claim_fact": "Faktum",
        "trust_claim_derived_fact": "Afledt faktum",
        "trust_claim_inference": "Inferens",
        "trust_claim_unknown": "Ukendt",
        "trust_claim_fact_tt": "Direkte understøttet af kilde eller beregning.",
        "trust_claim_derived_fact_tt": "Beregnet deterministisk ud fra data.",
        "trust_claim_inference_tt": "Evidens antyder dette, men beviser det ikke.",
        "trust_claim_unknown_tt": "Utilstrækkelig evidens.",
        # Evidence classes
        "trust_evidence_source_data": "Kildedata",
        "trust_evidence_nova_calculation": "Nova-beregning",
        "trust_evidence_nova_insight": "Nova-indsigt",
        "trust_evidence_nova_forecast": "Nova-prognose",
        "trust_evidence_source_data_tt": "Det tidsplanen viser.",
        "trust_evidence_nova_calculation_tt": "Det Nova har beregnet deterministisk.",
        "trust_evidence_nova_insight_tt": "Det Nova har udledt / fortolket.",
        "trust_evidence_nova_forecast_tt": "Det Nova forudsiger.",
        # Evidence class labels (TL-7.3, brief §45/§46). Mirror of the EN
        # block — same load-bearing terminology, never "AI tænker" or
        # similar. Brief §46: Kemp is Danish-only; the same vocabulary
        # applies on the Danish dashboard.
        "evidence_class_source_data": "Kildedata",
        "evidence_class_source_data_tt": "Det tidsplanen viser — ordret fra kilden.",
        "evidence_class_nova_calculation": "Nova-beregning",
        "evidence_class_nova_calculation_tt": "Beregnet deterministisk af Nova ud fra kildedata.",
        "evidence_class_nova_insight": "Nova-indsigt",
        "evidence_class_nova_insight_tt": "Novas fortolkning af kildedataene.",
        "evidence_class_nova_forecast": "Nova-prognose",
        "evidence_class_nova_forecast_tt": "Novas forudsigelse om fremtiden.",
        "evidence_class_legend": "Datakilde",
        # Project-level trust indicator (TL-7.2). Never "nøjagtig"/"præcision"
        # anywhere here — same reasoning as the English block: confidence is
        # not accuracy (brief §23).
        "trust_project_heading": "Tillid til denne analyse",
        "trust_project_summary": "{verified} af {total} aktiviteter bestod Novas verifikationsregler",
        "trust_breakdown_verified": "verificeret",
        "trust_breakdown_review": "kræver kontrol",
        "trust_breakdown_unresolved": "kunne ikke matches pålideligt",
        "trust_denominator_tt": "{total} er det samlede antal aktiviteter, Nova har gennemgået i denne sammenligning — samme antal som vises som \"Aktiviteter analyseret\" ovenfor. Heraf bestod {verified} Novas verifikation uden bemærkninger, {review} er markeret til manuel kontrol, og {unresolved} kunne ikke matches pålideligt mellem de to tidsplaner.",
        "trust_denominator_tt_all_verified": "{total} er det samlede antal aktiviteter, Nova har gennemgået i denne sammenligning — samme antal som vises som \"Aktiviteter analyseret\" ovenfor. Alle {verified} bestod Novas verifikation uden bemærkninger (ingen markeret til kontrol, ingen uafklarede).",
        "trust_denominator_tt_predictive": "{total} er det samlede antal aktiviteter i denne tidsplan. Af de {delayed} markeret som forsinkede kunne {unresolved} ikke bekræftes pålideligt ud fra kildedata og indgår ikke i dette tal.",
        "trust_feature_schedule_parsing": "Tidsplan-indlæsning",
        "trust_feature_activity_matching": "Aktivitetsmatch",
        "trust_feature_progress_comparison": "Fremdriftssammenligning",
        "trust_feature_critical_path": "Kritisk vej",
        "trust_feature_forecast": "Prognose",
        "trust_feature_not_available": "Ikke tilgængelig",
        # --- Forecast surface (TL-7.4, brief §31). DA mirror of the EN
        # block. Kemp is Danish-only; all forecast labels must be DA. ---
        "forecast_outlook_heading": "Prognose",
        "forecast_what_will_happen": "Hvad sker der",
        "forecast_delay_impact": "Estimeret forsinkelsespåvirkning",
        "forecast_confidence_high": "Høj",
        "forecast_confidence_medium": "Mellem",
        "forecast_confidence_low": "Lav konfidens \u2014 fortolk med forsigtighed",
        # (Bare `forecast_confidence` key removed from both EN and DA —
        # `_confidence_badge` reads only the per-level keys above. The
        # bare "Confidence" string is a Flask localizer source pattern,
        # `report_localization.py`; TL-7.6 pins its absence.)
        "forecast_key_drivers": "Vigtigste forsinkelsesdrivere",
        "forecast_basis": "Grundlag for Novas konfidens",
        "forecast_biggest_risk": "Største risiko",
        "forecast_will_block": "Vil blokere",
        "forecast_prevent_action": "Forebyg med",
        "forecast_no_delay_observed": "Ingen forsinkelser observeret \u2014 strukturel risikoanalyse",
        "why_button": "Hvorfor?",
        "why_root_cause": "Denne opgave er en grund\u00e5rsag \u2014 forsinkelsen skyldes ikke en anden forsinket opgave.",
        "why_downstream_of": "Dette er en efterf\u00f8lgende konsekvens af {id}, som ogs\u00e5 er forsinket.",
        "why_days_overdue": "{days} dage forsinket.",
        "why_action_related": "Baseret p\u00e5 {count} relaterede forsinkede aktiviteter identificeret i denne tidsplan.",
        "pdf_methodology_footer": "\u26a0 Baseret p\u00e5 delvist verificeret aktivitetsmatch.",
        # TL-9.1 — Click-into-evidence / source viewer (brief §24)
        "evidence_detail": "Aktivitetsbevis",
        "evidence_current_id": "Nuværende ID",
        "evidence_previous_id": "Tidligere ID",
        "evidence_deviation": "Afvigelse",
        "evidence_source_verification": "KILDEVERIFICERING",
        "evidence_old_schedule": "Gammel tidsplan",
        "evidence_new_schedule": "Ny tidsplan",
        "evidence_match_method": "Matchmetode",
        "evidence_data_status": "Datastatus",
        "evidence_view_source": "Se kildedokument",
        "evidence_non_paginated": "Ikke-pagineret dokument",
    },
}


def lang_code(language: str) -> str:
    return "da" if str(language).lower().startswith("da") else "en"


def t(language: str, key: str) -> str:
    code = lang_code(language)
    return LABELS.get(code, LABELS["en"]).get(key, LABELS["en"].get(key, key))


# ---------------------------------------------------------------------------
# Trust layer namespace helpers (TL-0.4)
#
# These resolve `TrustState` / `ClaimKind` / `EvidenceClass` `.value` strings
# to their label/tooltip keys under the `trust_*` prefix. Callers (notably
# `src.trust.vocabulary`) pass the raw `.value`, not the enum member, so
# these helpers stay decoupled from the enums themselves.
# ---------------------------------------------------------------------------

def t_state(state_value: str, lang: str, *, tooltip: bool = False) -> str:
    """Trust-state label or tooltip. `state_value` is the `.value` of
    `src.trust.vocabulary.TrustState` (e.g. "verified", "review",
    "unverified")."""
    suffix = "_tt" if tooltip else ""
    return t(lang, f"trust_state_{state_value}{suffix}")


def t_claim(kind_value: str, lang: str, *, tooltip: bool = False) -> str:
    """Claim-kind label or tooltip. `kind_value` is the `.value` of
    `src.trust.vocabulary.ClaimKind`."""
    suffix = "_tt" if tooltip else ""
    return t(lang, f"trust_claim_{kind_value}{suffix}")


def t_evidence(class_value: str, lang: str, *, tooltip: bool = False) -> str:
    """Evidence-class label or tooltip. `class_value` is the `.value` of
    `src.trust.vocabulary.EvidenceClass`."""
    suffix = "_tt" if tooltip else ""
    return t(lang, f"trust_evidence_{class_value}{suffix}")


def t_conflict(lang: str, *, tooltip: bool = False) -> str:
    """Source-conflict flag label or tooltip. The conflict flag has its own
    slot (it is *not* a `TrustState`)."""
    suffix = "_tt" if tooltip else ""
    return t(lang, f"trust_source_conflict{suffix}")
