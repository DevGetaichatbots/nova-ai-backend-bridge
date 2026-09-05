# Phase 7 — User-facing trust surface

**Goal.** Make trust visible without making the dashboard unreadable.

**User-visible change.** Yes — this is the phase the client sees. Everything up to here
was foundation.

**The constraint that governs this phase** (brief §21): *"Do NOT turn Nova into a
Christmas tree with green/yellow/red icons everywhere. Confidence should be available
without overwhelming the user."*

Both dashboards, both brand variants, both languages. Kemp and Nova share
`src/version_1_0/formatters.py`, so most work is one change — but parity must be verified,
not assumed.

---

### TL-7.1 — Three-state badge component

**Brief:** §21, §46 · **Blocked by:** TL-6.4 · **Blocks:** TL-7.2, TL-7.3, TL-7.8

**Why.** Brief §21 specifies exactly three visible states with exact tooltips.

**Files.**
- `rag-agent/backend/src/version_1_0/formatters.py` — CSS + render helpers
- `rag-agent/backend/src/version_1_0/adapters.py`
- `rag-agent/backend/src/trust/vocabulary.py`

**Do.**
1. Build one badge renderer for the three states, with brief §21's tooltips verbatim:
   - **VERIFIED** (green) — "Verified against source schedule."
   - **REVIEW** (amber) — "Nova identified uncertainty in the source data or activity match. Review recommended."
   - **UNVERIFIED** (red/neutral) — "Nova could not reliably verify this value. It has not been used as confirmed data."
2. Show badges **only where they carry information**: default to showing `REVIEW` and
   `UNVERIFIED`, and suppress `VERIFIED` badges on rows where everything is verified.
   A wall of green badges is the Christmas tree §21 prohibits.
3. Badge colours must work in both palettes (`CSS` teal/blue and `CSS_KEMP` green).
   Amber and red must remain distinguishable against K&L green — check this explicitly,
   as the Kemp palette's green is close to the verified state colour.
4. Reuse the existing `ni-change-chip--*` chip pattern rather than inventing new markup.

**Acceptance criteria.**
- [ ] Exactly three states rendered, tooltips verbatim from brief §21
- [ ] Verified badges suppressed when a row is fully verified
- [ ] Badges legible and distinguishable in both palettes — visually confirmed
- [ ] Labels and tooltips resolve in EN and DA

**Verify.** `cd rag-agent/backend && pytest tests/trust/test_badges.py -q`

**Do not.** Do not badge every cell. Do not introduce a fourth state — source conflict
is a flag on top of a state, not a state.

---

### TL-7.2 — Project-level trust indicator

**Brief:** §22, §23 · **Blocked by:** TL-7.1 · **Blocks:** TL-7.5 · **Resolves Q-4**

**Why.** Brief §22 wants the top-of-dashboard summary that answers "can we trust this
dashboard?" before the PM has to ask. Brief §23 constrains how: any percentage must have
a precisely defined denominator, and "96% of activities passed Nova's verification rules"
is defensible where "Nova is 98.7% accurate" is not.

**Files.**
- `rag-agent/backend/src/version_1_0/formatters.py` — header region
- `rag-agent/backend/src/version_1_0/adapters.py`
- `rag-agent/backend/src/trust/engine.py`

**Do.**
1. Render the brief §22 shape: overall verified proportion, then the breakdown —
   N verified / N require review / N could not be reliably matched.
2. **Resolve `Q-4`** and record it: the exact denominator. Recommendation —
   "N of M activities passed Nova's verification rules", where M is total activities
   detected. Whatever is chosen, the definition must be visible to the user on hover.
3. Alongside it, surface the feature-specific confidences from `TL-4.4` — brief §30
   argues these are more useful than the single number.
4. Never use the word "accurate".

**Acceptance criteria.**
- [ ] Indicator renders the brief §22 breakdown
- [ ] Denominator defined, documented, and exposed to the user
- [ ] Feature-specific confidences displayed alongside
- [ ] `grep -ri "accurate" ` over rendered output returns nothing
- [ ] `Q-4` resolved in `DECISIONS.md`

**Verify.** `cd rag-agent/backend && pytest tests/trust/test_project_trust_indicator.py -q`

**Do not.** Do not publish a percentage whose denominator you cannot state in one
sentence. Do not equate confidence with accuracy (brief §23).

---

### TL-7.3 — Source / Calculation / Insight / Forecast distinction

**Brief:** §45 · **Blocked by:** TL-7.1 · **Blocks:** TL-7.4

**Why.** Brief §45: *"This alone could dramatically improve trust."* Users must not
confuse what the schedule says with what Nova calculated, inferred, or predicted.

**Files.**
- `rag-agent/backend/src/version_1_0/formatters.py`
- `rag-agent/backend/src/trust/vocabulary.py`

**Do.**
1. Give each `EvidenceClass` a consistent, quiet visual treatment — a label or a subtle
   ground, not four more colours competing with the trust badges.
2. Apply consistently across both dashboards:
   - **SOURCE DATA** — what the schedule says
   - **NOVA CALCULATION** — what Nova deterministically computed
   - **NOVA INSIGHT** — what Nova inferred
   - **NOVA FORECAST** — what Nova predicts
3. Use brief §46's approved terminology exactly. No "AI thinks".
4. Keep it legible against both palettes.

**Acceptance criteria.**
- [ ] All four classes visually distinguishable and consistently applied
- [ ] Terminology matches brief §46 exactly, EN and DA
- [ ] Treatment does not collide with trust badges
- [ ] Applied to both dashboards

**Verify.** `cd rag-agent/backend && pytest tests/trust/test_evidence_class_rendering.py -q`

**Do not.** Do not use four more traffic-light colours. Evidence class is orthogonal to
trust state; making them look alike will merge them in users' minds.

---

### TL-7.4 — Forecast never renders like observed fact

**Brief:** §31 · **Blocked by:** TL-7.3

**Why.** Brief §31: *"Never make a prediction visually indistinguishable from an observed
fact."* Predictive is where this matters most.

**Files.**
- `rag-agent/backend/src/version_1_0/formatters.py` — predictive render path
- `rag-agent/backend/src/version_1_0/adapters.py` — `adapt_predictive_dashboard`

**Do.**
1. Render every `NOVA_FORECAST` element with its required companions from brief §31:
   prediction, confidence band/category, evidence, key drivers.
2. `predictive_snapshot.what_will_happen` and `estimated_delay_impact` — the most
   prominent numbers on the report — must read unambiguously as forecasts.
3. The overdue-bucket chart is observed fact; any projected trend is forecast. If both
   ever appear in one chart, they must be visually separated.
4. Where forecast confidence is low, say so at the point of display, not in a footnote.

**Acceptance criteria.**
- [ ] Every forecast element shows confidence, evidence, and drivers
- [ ] The two headline snapshot fields render as forecasts
- [ ] Observed and forecast data are never visually merged
- [ ] Low-confidence forecasts are marked at the point of display

**Verify.** `cd rag-agent/backend && pytest tests/trust/test_forecast_rendering.py -q`

**Do not.** Do not show a forecast number in the same style as a measured KPI. That is
the specific failure §31 names.

---

### TL-7.5 — "Why?" explanations

**Brief:** §32 · **Blocked by:** TL-7.2

**Why.** Brief §32: every major recommendation should support a "Why?" that turns Nova
from magical into explainable. The engine already has the material — `TL-4.3` records the
weakest link, `TL-6.3` records supporting facts.

**Files.**
- `rag-agent/backend/src/version_1_0/formatters.py`
- `rag-agent/backend/src/trust/engine.py`

**Do.**
1. Add a "Why?" affordance on risk flags, priority actions, and the project trust
   indicator.
2. Content follows brief §32's worked example: the specific counts behind the flag, the
   confidence, and the evidence base ("22 verified schedule records").
3. Assemble it from recorded evidence — never generate the explanation with a model. A
   generated rationale for a deterministic decision is itself an unverified claim.
4. The V1 dashboard is a self-contained HTML document with embedded JS; implement
   disclosure client-side in that existing pattern, not as a server round-trip.

**Acceptance criteria.**
- [ ] "Why?" available on risk flags, priority actions, and the trust indicator
- [ ] Explanations assembled from recorded evidence, no LLM call
- [ ] Content matches brief §32's structure
- [ ] Works inside the sandboxed iframe both apps render into

**Verify.** `cd rag-agent/backend && pytest tests/trust/test_why_explanations.py -q`

**Do not.** Do not generate explanations with a model. Do not require a network call —
the dashboard must stay self-contained for PDF export and public share links.

---

### TL-7.6 — Brand and locale parity

**Brief:** §46 · **Blocked by:** TL-7.5 · **Related:** EXT-2

**Why.** Kemp is Danish-only with no language switcher; Nova is EN/DA with a per-report
language selector. A trust feature that only reads well in English fails the Kemp user
entirely — and Kemp is the client driving this brief.

**Files.**
- `rag-agent/backend/src/version_1_0/localization.py`
- `rag-agent/backend/src/version_1_0/formatters.py`
- `kemp&lauritzen/app/src/locales/da.json`
- `website/workspace/app/src/locales/{en,da}.json`

**Do.**
1. Every trust string has a reviewed Danish translation. Machine translation is not
   acceptable for terminology this load-bearing — this is `EXT-2`.
2. Verify every new label renders in `format_kemp_v1_as_html`,
   `format_health_v1_as_html`, `format_kemp_predictive_v1_as_html`, and
   `format_predictive_v1_as_html`.
3. Confirm no trust element is accidentally caught by the Kemp optional-item hiding
   mechanism (`_mark_optional_health_items` / `ni-kemp-hidden`) — trust indicators must
   never start collapsed behind the "Show Full overview" toggle.
4. Check the naive Flask-side string-replace localizers in `report_localization.py` do
   not corrupt the new strings.

**Acceptance criteria.**
- [ ] All trust strings have reviewed DA translations (`EXT-2` closed)
- [ ] All four formatter entry points render every trust element
- [ ] No trust element is hidden by the Kemp optional-item mechanism — asserted by test
- [ ] Flask-side localizers leave trust strings intact

**Verify.** `cd rag-agent/backend && pytest tests/trust/test_brand_locale_parity.py -q`

**Do not.** Do not ship English-only trust labels to Kemp. Do not let a trust indicator
default into the collapsed Kemp section.

---

### TL-7.7 — PDF export carries the same trust model

**Brief:** §44 · **Blocked by:** TL-7.6

**Why.** Brief §44: *"Do not make dashboard transparent but PDF reports absolute."*
PDFs are what get forwarded to people who never saw the dashboard.

**Files.**
- `rag-agent/backend/src/pdf_export.py`
- `rag-agent/backend/src/version_1_0/formatters.py` (print styles)

**Do.**
1. The live PDF path renders the displayed HTML through headless Chromium, so trust
   badges should carry automatically — **verify, do not assume**. Check that badge
   colours survive print-color-adjust and that tooltips (hover-only in PDF) have a
   visible print fallback.
2. Add the brief §44 methodology footer where results are partially verified:
   *"⚠ Based on partially verified activity matching."*
3. Include the project trust indicator on the PDF's first page.
4. Note: the Flask-side WeasyPrint/ReportLab PDF routes are unreachable from both UIs,
   and the ReportLab one is already non-functional against current V1 HTML. Do not
   invest in them here; record their status in `DECISIONS.md` and consider removal in
   Phase 9.

**Acceptance criteria.**
- [ ] Trust badges visible and correctly coloured in exported PDFs
- [ ] Hover-only information has a visible print fallback
- [ ] Partial-verification footer appears when applicable
- [ ] Trust indicator on page one
- [ ] Verified for both brands

**Verify.** `cd rag-agent/backend && pytest tests/trust/test_pdf_trust.py -q` plus manual inspection of one exported PDF per brand.

**Do not.** Do not rely on hover tooltips in a PDF.

---

### TL-7.8 — Reassuring uncertainty UX

**Brief:** §42 · **Blocked by:** TL-7.1

**Why.** Brief §42 contrasts a bare `ERROR` with a message that communicates *"Nova
protected you from a potentially incorrect result."* This is where the trust layer either
earns confidence or feels broken.

**Files.**
- `rag-agent/backend/src/version_1_0/formatters.py`
- `kemp&lauritzen/app/src/components/{ComparisonAnalysis,ScheduleAnalysis}.jsx`
- `website/workspace/app/src/components/{ComparisonAnalysis,ScheduleAnalysis}.jsx`

**Do.**
1. Replace error-shaped presentation of uncertainty with brief §42's pattern:
   "Review required" + what happened + what Nova did about it + the action link.
2. Render `BLOCK` gating (`TL-4.6`) as a protective decision, not a failure.
3. Both React apps must handle the new response states. Note the existing hazard: the
   Flask layer marks a run `'completed'` on HTTP 200 alone, so a gated or partial result
   must be represented explicitly in the payload rather than inferred from status codes.
4. Fix that status handling as part of this task — a `BLOCK` recorded as `'completed'`
   would surface as a blank report.

**Acceptance criteria.**
- [ ] Uncertainty states render as informative, not as errors
- [ ] `BLOCK` renders as a protective pause with an explanation
- [ ] Both apps handle gated/partial/no-answer states
- [ ] Flask status derivation accounts for gating outcomes, not just HTTP 200
- [ ] Screens reviewed against brief §42's wording

**Verify.** Manual review of each state in both apps, plus
`cd rag-agent/backend && pytest tests/trust/test_uncertainty_ux.py -q`

**Do not.** Do not show a raw exception or an empty dashboard. Every uncertainty state
must explain itself and offer a next step.
