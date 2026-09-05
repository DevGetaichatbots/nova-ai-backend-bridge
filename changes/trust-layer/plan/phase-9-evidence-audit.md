# Phase 9 — Evidence, audit & Trust Center

**Goal.** Let K&L audit Nova rather than trust it — and make the quality of the system
itself observable over time.

**User-visible change.** Yes — source viewer, and a Trust Center for admins.

**Brief §24 on why this is the strongest feature in the programme:**

> Now the user doesn't have to trust Nova blindly. They can audit Nova.
> That is extremely powerful.

This phase corresponds to the brief's **P2 — enterprise maturity**. It is last because
every piece of it consumes evidence produced by earlier phases; attempting it first would
have produced a viewer with nothing to show.

---

### TL-9.1 — Click-into-evidence / source viewer

**Brief:** §24 · **Blocked by:** TL-8.5 · **Requires:** TL-1.2 geometry

**Why.** Brief §24's target interaction: click an activity, see current ID, previous ID,
status, deviation, match method, and then jump to the source — page 14 of the old
schedule, page 16 of the new — with the relevant row highlighted.

**Files.**
- `rag-agent/backend/src/version_1_0/formatters.py` — activity detail
- `rag-agent/backend/src/main.py` — source-document endpoint
- both React apps

**Do.**
1. Activity detail panel showing the brief §24 field set, assembled from stored
   provenance: current ID, previous ID, status, deviation, match method and confidence.
2. Source verification block: old schedule page, new schedule page, match method, data
   status.
3. "View source" opens the source document at the recorded page with the recorded
   bounding box highlighted — this is what `TL-1.2`'s polygon capture was for.
4. Source documents are already persisted as bytes by the Flask layer (`file_data BYTEA`)
   for predictive analyses; confirm the equivalent exists for comparison uploads, and
   serve them with correct auth and tenant scoping.
5. Non-PDF sources have no page/geometry. Show the row reference instead and say the
   source is not a paginated document — do not fabricate a page number.

**Acceptance criteria.**
- [ ] Detail panel shows the full brief §24 field set
- [ ] "View source" opens the correct page with the correct region highlighted
- [ ] Works for both old and new schedules in a comparison
- [ ] Non-paginated sources degrade honestly to a row reference
- [ ] Source access is authenticated and tenant-scoped

**Verify.** `cd rag-agent/backend && pytest tests/trust/test_source_viewer.py -q` plus manual verification against a real PDF.

**Do not.** Do not fabricate a page number for CSV/MPP/XML sources. Do not expose source
documents on the unauthenticated public-share route.

---

### TL-9.2 — Audit log

**Brief:** §40 · **Blocked by:** TL-8.5 · **Blocks:** TL-9.3

**Why.** Brief §40's test: *"If K&L asks 'Why did Nova say this on 12 August?' you should
be able to reconstruct the answer."*

**Files.**
- create `rag-agent/backend/src/trust/audit.py`
- both Flask backends

**Do.**
1. Log the brief §40 chain: schedule uploaded → parser version → OCR provider/version →
   confidence results → matches generated → manual corrections → analysis version →
   agent answer → evidence used.
2. Append-only, immutable.
3. Retention and tenant scoping consistent with the rest of the system. Note the Nova app
   already imports `log_audit_event` in `schedule.py` without ever calling it — decide
   whether to adopt that existing facility or supersede it, and record it.
4. The audit log contains project data. Handle it under the same constraints as the
   schedules themselves.

**Acceptance criteria.**
- [ ] Every stage in the brief §40 chain logged
- [ ] Log is append-only
- [ ] A past analysis can be fully reconstructed from the log
- [ ] Relationship to the existing unused `log_audit_event` decided and recorded

**Verify.** `cd rag-agent/backend && pytest tests/trust/test_audit_log.py -q`

**Do not.** Do not log raw document contents into the audit trail. Reference them;
duplicating client project data multiplies the handling obligation.

---

### TL-9.3 — Version everything

**Brief:** §41 · **Blocked by:** TL-9.2 · **Blocks:** TL-9.4

**Why.** Brief §41: results will change over time, and without versions nobody can
explain why.

**Files.**
- `rag-agent/backend/src/trust/audit.py`
- `rag-agent/backend/ingestion/pipeline.py`
- `rag-agent/backend/src/predictive_agent.py`
- `rag-agent/backend/src/experimental/nusf_compare_engine.py`

**Do.**
1. Version and record: parser, matching algorithm, analysis engine, prompt, model,
   schedule revision, manual corrections.
2. Stamp versions into every analysis result and audit entry.
3. Prompt and model versions matter most — an Azure deployment change silently altering
   output is exactly the scenario this exists to catch.
4. Surface the analysis-engine version in the Trust Center (`TL-9.5`).

**Acceptance criteria.**
- [ ] All seven version dimensions recorded
- [ ] Versions stamped on results and audit entries
- [ ] A model or prompt change is visible in the audit trail
- [ ] Two analyses of the same input under different versions are distinguishable

**Verify.** `cd rag-agent/backend && pytest tests/trust/test_versioning.py -q`

**Do not.** Do not use a single global version number. Brief §41 lists seven independent
dimensions precisely because they change independently.

---

### TL-9.4 — Trust metrics KPIs

**Brief:** §38 · **Blocked by:** TL-9.3 · **Blocks:** TL-9.5, TL-9.6

**Why.** Brief §38 lists ten metrics that should become internal Nova quality KPIs.
Several already exist in the harness from Phases 3 and 6; this task makes them
continuous rather than test-time-only.

**Files.**
- `rag-agent/backend/src/trust/metrics.py`
- `rag-agent/backend/tests/trust/harness.py`

**Do.**
1. Instrument all ten brief §38 metrics: critical field verification rate, activity match
   precision, unmatched activity rate, manual review rate, OCR review rate, false match
   rate, conflict detection rate, agent unsupported claim rate, human correction rate,
   regression failure rate.
2. Compute them on real usage, not only fixtures.
3. Persist over time so trends are visible — brief §49's "confidence monitoring over time".
4. False match rate and unsupported claim rate get particular prominence (§37, §39).

**Acceptance criteria.**
- [ ] All ten metrics implemented
- [ ] Computed on real usage and persisted over time
- [ ] Trends queryable
- [ ] Metrics reconcile with the harness's fixture-time values

**Verify.** `cd rag-agent/backend && pytest tests/trust/test_metrics.py -q`

**Do not.** Do not blend these into one health score. Their diagnostic value is in being
separate — brief §30's argument applies to internal metrics too.

---

### TL-9.5 — Trust Center

**Brief:** §43 · **Blocked by:** TL-9.4

**Why.** Brief §43 positions this as a serious enterprise differentiator: a small admin
surface showing data verification, activity matching, items requiring review, unresolved
items, last validation date, and analysis engine version.

**Files.**
- both React apps (admin area)
- both Flask backends
- `rag-agent/backend/src/trust/metrics.py`

**Do.**
1. Build the brief §43 view for enterprise admins.
2. Include "View verification report" — an exportable summary.
3. Respect the tenancy difference: Nova is multi-tenant (`company_id`), Kemp is
   single-tenant with a simpler admin role. Both have an `/admin` area already.
4. Every percentage shown obeys brief §23 — defined denominator, no accuracy claims.

**Acceptance criteria.**
- [ ] Trust Center renders the brief §43 field set
- [ ] Verification report exportable
- [ ] Admin-only, correctly scoped in both apps
- [ ] Every percentage has a stated denominator
- [ ] Both brands, both locales

**Verify.** Manual admin walkthrough in both apps, plus
`cd rag-agent/backend && pytest tests/trust/test_trust_center.py -q`

**Do not.** Do not expose the Trust Center to non-admins, and do not surface cross-tenant
figures in the Nova app.

---

### TL-9.6 — Turn release gates from informational to blocking ✅ DONE

**Brief:** §36 · **Blocked by:** TL-9.4 · **Closes:** TL-0.3 · **Status:** DONE (2026-09-05) — see `PROGRESS.md`, ADR-050

**Why.** Brief §36 requires real release gates: *"A shiny new feature must not silently
reduce reliability."* Phase 0 shipped the harness in reporting mode; now the metrics are
real enough to enforce.

**Files.**
- `rag-agent/backend/tests/trust/harness.py`
- `rag-agent/backend/tests/trust/test_regression.py`
- CI config (`kemp&lauritzen/.github/workflows/trust-gates.yml`, `website/workspace/app/.github/workflows/trust-gates.yml`, `.github/workflows/trust-gates.yml`)

**Do.**
1. Flip the three gates brief §36 names to blocking:
   - critical-field extraction regression — **not allowed**
   - false-match regression — **not allowed**
   - known calculation regression — **not allowed**
2. Add unsupported-claim-rate regression as a fourth gate (brief §39's target is zero).
3. Wire into CI so a failing gate blocks the merge.
4. Define the override procedure: a gate can be overridden only with a recorded
   justification in `DECISIONS.md`. An override that is easy and unlogged is not a gate.

**Acceptance criteria.**
- [x] All four gates block on regression
- [x] Gates run in CI on every PR
- [x] A deliberately introduced regression blocks the build
- [x] Override requires a recorded `DECISIONS.md` justification
- [x] `TL-0.3` updated to `DONE` with a pointer to this task

**Verify.** Deliberate regressions block the build (`pytest tests/trust/test_regression.py -q` → 19 passed);
CI workflows configured in all repositories; `python -m tests.trust.harness compare` runs blocking release gates.

**Do not.** Do not add a skip flag. Do not allow an override without a written
justification — that is how gates decay into warnings, which is where this started.

