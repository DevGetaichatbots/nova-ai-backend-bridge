# EXT-1 — K&L Golden Dataset Request

**Status:** DRAFT — awaiting human send (see `PROGRESS.md` → External
dependencies → `EXT-1` for the current owner and target date)

**Source brief:** §35 (Testing — Build a Golden Dataset), §7 (OCR Confidence
Thresholds — "starting hypotheses, not final thresholds"), §10 (Never invent
an Activity ID), §12 (Match Confidence), §46 (Recommended User-Facing
Terminology)

**Trust-layer task:** TL-0.6 (see `plan/PROGRESS.md` for status)

---

## 1. What we are asking for

A **golden dataset** of 10–20 real K&L schedule pairs, expanded incrementally
toward hundreds of individual activities with manually established correct
answers. The dataset is used to:

- calibrate match-confidence thresholds (gates `TL-3.6` and `TL-4.7`),
- measure parsing regressions between releases (already covered by the
  synthetic harness in `TL-0.1`–`TL-0.3`, but synthetic fixtures cannot
  reproduce real-world edge cases),
- ground-truth the "never invent an Activity ID" rule in
  Phase 2 against actual ambiguous extractions, and
- validate the trust-engine propagation logic against real source-quality
  variation.

The dataset is the single calibration input for everything in
`changes/trust-layer/plan/phase-3-matching.md` and
`changes/trust-layer/plan/phase-4-trust-engine.md` that says "structural
placeholder thresholds".

## 2. Volume and scope

Brief §35 calls for **10–20 schedule pairs initially**, then **hundreds to
thousands of individual activities** with established ground truth. Per
activity:

| Field | Required | Notes |
|---|---|---|
| Correct Activity ID | yes | the ID K&L would recognise as authoritative (the column K&L's own planners trust) |
| Correct Activity name | yes | as it appears in K&L's system of record |
| Correct planned start | yes | ISO date |
| Correct planned finish | yes | ISO date |
| Correct actual start | when present | nullable |
| Correct actual finish | when present | nullable |
| Correct percent complete | yes | 0–100, no clamping |
| Correct match to prior revision | yes | per pair — which activity in the new schedule is the same logical activity |
| Correct status | yes | per the source schedule's own status vocabulary |
| Correct changes vs prior revision | yes | free text or structured list, per K&L's normal reporting practice |

Anything K&L would normally record that we do not list above is welcome —
more context is better than less for ground-truth work. The required list
above is the floor, not the ceiling.

## 3. Formats required

We currently support and must calibrate against:

- **Image PDF schedules** (Azure Document Intelligence output) — the
  primary input today; OCR confidence depends heavily on scan quality.
- **MS Project exports** — both `.mpp` (via MPXJ) and `.xml` (MSPDI).
  These are the ones where ID schemes change between revisions and where
  the "positional ID" trap shows up.
- **Detailtidsplan** — K&L's own format. If extraction logic for this
  format has gaps, the dataset is what surfaces them.
- **Plandisc / equivalent** — used by some K&L project teams.

Per pair, both the **old** and **new** revisions must be present. A pair
without a ground-truth match is not usable for match-confidence calibration.

## 4. Anonymisation and data handling

This is K&L project data and must be handled accordingly:

- **Project names, contractor names, client names, addresses** — must be
  replaced with stable pseudonyms (`Project A`, `Project B`, …) consistent
  across both revisions of a pair. Pseudonym mapping stays with K&L; Nova
  does not need it for calibration.
- **Activity names** — preferably left in place. They are the load-bearing
  signal for matching across revisions, and replacing them with synthetic
  text destroys the matching signal. If K&L requires activity-name
  redaction, that is workable but reduces the dataset's value for
  `TL-3.x` and should be flagged in the response.
- **Dates** — leave in place. Relative dates lose the cross-revision
  matching signal (the same activity in the old and new schedule is
  identified partly by date proximity).
- **Currency, quantities, internal cost codes** — redact if present; not
  used by Nova's current scope.
- **Transfer** — encrypted at rest, transferred over a K&L-approved
  channel. Nova-side storage follows the same rules as the rest of the
  K&L dataset ingestion path.

If K&L's standard anonymisation process has a different shape (e.g.
project names randomised, activity names kept), follow that — the goal is
"calibration data K&L is comfortable sharing", not "a specific
anonymisation recipe we prefer".

## 5. What we will and will not do with it

**Will:**
- Run match-confidence calibration (`TL-3.6`).
- Run trust-threshold calibration (`TL-4.7`).
- Add synthetic-failure scenarios for the false-positive metric
  (`TL-3.5`).
- Use it as the regression-test reference for every Nova release
  (post-`TL-9.6` when release gates flip from informational to blocking).

**Will not:**
- Use it as the *only* test fixture. Synthetic fixtures from `TL-0.1`
  continue to be the first-pass harness and are not replaced by real
  data. Real data calibrates; synthetic data exercises the harness.
- Use it for any other client or any non-K&L feature work without
  explicit re-permission.
- Persist it in Nova's main database. It lives in a calibration-only
  store with the same access controls as the source-data ingestion path.

## 6. Timeline expectations

Suggested sequencing (owner + K&L to confirm):

- **T+0** — request sent (see `PROGRESS.md` `EXT-1` row for the
  target date).
- **T+1 week** — K&L confirms scope and proposes a sample pair to
  validate the anonymisation pattern before producing the full set.
- **T+3 weeks** — first 2–3 schedule pairs delivered (mix of formats).
- **T+5 weeks** — remaining pairs delivered.
- **T+6 weeks** — `TL-3.6` and `TL-4.7` calibration starts.

The fallback if the request is unanswered or only partially fulfilled by
the time Phase 3 begins is already in motion and recorded in
`DECISIONS.md` ADR-001: ship structural-placeholder thresholds, label
them as such, and continue. The synthetic harness carries the
regression-test guarantee either way; only the *calibration* waits.

## 7. Fallback already in motion

Per ADR-001 and `TL-0.1`:

- `tests/trust/fixtures/` carries 8 synthetic fixtures that exercise
  every code path Phase 1–4 plan to change.
- `tests/trust/baselines/` is the byte-identical reference snapshot.
- `python -m tests.trust.harness compare` reports regressions
  informatively today and blocks releases after `TL-9.6`.

So: if `EXT-1` arrives late, the only thing delayed is *threshold
calibration*. The structural safety net (`TL-0.1`–`TL-0.5`) and the
match-confidence model (`TL-3.1`–`TL-3.5`) ship on schedule.

## 8. Send checklist

Before sending, confirm:

- [ ] Owner name populated in `PROGRESS.md` `EXT-1` row.
- [ ] Target date populated in `PROGRESS.md` `EXT-1` row.
- [ ] K&L primary contact confirmed (name + role).
- [ ] K&L data-handling / DPA constraints reviewed; this request attached
      to or referencing the right agreement.
- [ ] Anonymisation pattern approved by K&L (either their standard
      pattern, or the proposal in §4).
- [ ] Return channel agreed (encrypted upload, S3, internal file share,
      etc.) — not email attachments.
- [ ] `TL-3.6` and `TL-4.7` in `PROGRESS.md` set to `BLOCKED` referencing
      `EXT-1` (done as part of TL-0.6 close-out; verify before send).

## 9. Evidence

When the request is sent, record in `PROGRESS.md` `EXT-1` row:

- Date sent
- Recipient (org + role; no individual PII)
- Channel (e.g. "encrypted upload link")
- Reply-by date (K&L's own commitment, if any)

When the first batch arrives, link to the encrypted-store path here.

When calibration starts (`TL-3.6` / `TL-4.7`), link to the calibration
report.
