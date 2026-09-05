# Phase 2 — Never invent an ID

**Goal.** Make it structurally impossible for Nova to display an Activity ID it did
not read from a source document.

**User-visible change.** Yes — the ID column. Some activities will start showing
"Unable to verify" instead of a number. **This is the intended outcome**, and it is
the change most directly tied to the live Andreas/K&L conversation.

**The finding this phase exists to fix.** In
`ingestion/normalization/engine.py` (~L240–255):

```python
raw_source_id = _get_val(row, headers, effective_id_col)
if not raw_source_id:
    raw_source_id = f"{_stable_text(raw_name)} | {_stable_text(raw_location_path)}"
...
if not raw_source_id:
    raw_source_id = str(row_idx + 1)          # ← invents an ID from row position
```

`Activity.source_id` is a **required** `str`, which is what forces the invention.
That synthesized value then flows to the dashboard's visible ID column via
`nusf_compare_engine.py` (~L313):

```python
"id": row.get("_identity_label", "").strip() or row.get("source_id", "").strip()
```

So today a user can be shown `1`, `2`, `3` — or a `name | location` string — presented
exactly like a real Activity ID. Brief §10 calls this out as an absolute rule and
demands it be "impossible at architecture level, not merely discouraged in the prompt".

---

### TL-2.1 — Make `source_id` optional; delete the invention fallbacks

**Brief:** §9, §10 · **Blocked by:** TL-1.8 · **Blocks:** TL-2.2

**Why.** The type system is currently what forces the lie. Fix the type, and the
fallbacks have nowhere to go.

**Files.**
- `rag-agent/backend/ingestion/models/nusf.py` — `Activity.source_id`
- `rag-agent/backend/ingestion/normalization/engine.py` — ~L240–255

**Do.**
1. Change `source_id: str` → `source_id: Optional[str] = None`.
2. Delete both fallbacks: the `name | location` composite and the `str(row_idx + 1)`
   positional invention. When no ID column value is present, `source_id` stays `None`.
3. `internal_id` (the derived UUID) remains required — it is an internal handle and is
   never displayed as an Activity ID. Add a comment saying exactly that.
4. Fix every consumer that assumed `source_id` is a non-empty string. Expect fallout in
   `to_nusf_chunks`, `nusf_compare_engine`, and the relationship-resolution map
   (`source_id_to_internal`) — the relationship map should key on `internal_id`.

**Acceptance criteria.**
- [ ] `Activity.source_id` is `Optional[str]` defaulting to `None`
- [ ] Neither invention fallback exists anywhere in the codebase
- [ ] Ingesting a schedule with no ID column produces activities with `source_id is None`, not `"1"`
- [ ] Relationship resolution still works (keyed on `internal_id`)
- [ ] `harness compare` diffs are limited to ID fields and are explainable

**Verify.** `cd rag-agent/backend && pytest tests/trust/test_no_invented_ids.py tests/test_nusf_normalization.py -q`

**Do not.** Do not substitute `internal_id` (the UUID) into the display path. Swapping
one invented identifier for another prettier one fails the same rule.

---

### TL-2.2 — Split matching identity from source Activity ID

**Brief:** §9 · **Blocked by:** TL-2.1 · **Blocks:** TL-2.3, TL-2.5, TL-2.6

**Why.** Brief §9 is precise: *matching identity* and *source Activity ID* are not the
same thing, and conflating them is what produced the composite-ID fallback. Nova may
legitimately use `name + location` to decide two rows are the same activity — it may
never then present that composite as the activity's ID.

**Files.**
- `rag-agent/backend/ingestion/models/nusf.py`
- `rag-agent/backend/ingestion/normalization/engine.py`
- `rag-agent/backend/src/experimental/nusf_compare_engine.py` — identity resolution (~L179–232)

**Do.**
1. Establish two clearly separated concepts on `Activity`:
   - `source_id: Optional[str]` — verbatim from the document, display-safe, never synthesized
   - `match_key: str` — internal join key, may be composite, **never displayed**
2. `stable_key` already approximates `match_key`; rename/absorb it rather than adding a
   third concept, and record the mapping in `DECISIONS.md`.
3. Record `match_method` alongside: `verified_source_id`, `stable_key`,
   `name_location_composite`, `positional` — feeding `TL-3.1`'s levels.
4. In `nusf_compare_engine`, stop falling back to `source_id` for the display `id`
   when the identity was composite. Display `source_id` or nothing.

**Acceptance criteria.**
- [ ] `match_key` and `source_id` are separate fields with separate semantics
- [ ] A test asserts no composite `match_key` value ever appears in a display field
- [ ] `match_method` is recorded for every activity
- [ ] `_identity_label` (the existing human-readable "why matched" string) is preserved and mapped to `match_method`

**Verify.** `cd rag-agent/backend && pytest tests/trust/test_identity_separation.py -q`

**Do not.** Do not delete `_identity_label`. It is existing, genuinely useful provenance
about *why* two rows matched, and Phase 3 builds on it.

---

### TL-2.3 — Architectural guard: no synthesized ID can surface

**Brief:** §10, §34 · **Blocked by:** TL-2.2 · **Blocks:** TL-2.4

**Why.** Brief §10 requires this be impossible at architecture level, and §34 warns
that a system-prompt rule is not a safety mechanism. That means a test that fails the
build, not a convention.

**Files.**
- create `rag-agent/backend/tests/trust/test_no_invented_ids.py`

**Do.**
1. Write a test that, for every fixture, walks the **entire rendered output** (both
   dashboards, both brand variants) and asserts every displayed activity ID is either:
   - byte-identical to a value present in the source document, or
   - the canonical "unable to verify" marker from `TL-0.4`'s vocabulary.
2. Include an adversarial fixture with no ID column at all, and assert no numeric IDs
   appear anywhere in its output.
3. Include a fixture whose activity *names* look like IDs (e.g. `A-142 Cable tray`) and
   assert the name is not harvested into the ID field.
4. Add a static check that the invention patterns cannot return:
   `grep` for `row_idx + 1` and composite-ID construction near `source_id` assignment.

**Acceptance criteria.**
- [ ] Test passes on all fixtures
- [ ] Reintroducing either fallback fails the test (verify by temporarily reverting)
- [ ] Test covers Health and Predictive, Kemp and Nova variants
- [ ] Test is in the default `pytest tests/` run, not opt-in

**Verify.** `cd rag-agent/backend && pytest tests/trust/test_no_invented_ids.py -q`

**Do not.** Do not weaken this test later to make an unrelated change pass. If it
fails, the pipeline is inventing an ID — that is the test working.

---

### TL-2.4 — Display contract for unverifiable IDs

**Brief:** §10, §21, §42 · **Blocked by:** TL-2.3

**Why.** Brief §10 specifies the display: `ID: Unable to verify`, or `ID: —` with an
appropriate status. §42 adds that this should feel reassuring, not broken.

**Files.**
- `rag-agent/backend/src/version_1_0/formatters.py` — `_render_table`, `_table_row`
- `rag-agent/backend/src/version_1_0/adapters.py` — `_activity_row`
- `rag-agent/backend/src/trust/vocabulary.py`

**Do.**
1. Render a missing `source_id` using the canonical vocabulary marker plus the
   `UNVERIFIED` state — not an empty cell, which reads as a rendering bug.
2. Tooltip comes from brief §21: "Nova could not reliably verify this value. It has not
   been used as confirmed data."
3. Apply to both dashboards and both brand variants. Kemp and Nova share the formatter,
   so this should be one change — confirm it renders in both.
4. Keep the activity's *name* prominent so the row is still identifiable to a human
   even without an ID.

**Acceptance criteria.**
- [ ] Missing IDs render the canonical marker, never an empty cell or a placeholder number
- [ ] Marker and tooltip resolve in both EN and DA
- [ ] Both brand variants render identically apart from palette
- [ ] Visual check: a table of mostly-unverifiable IDs still reads as a working report

**Verify.** `cd rag-agent/backend && pytest tests/trust/test_id_display.py -q`

**Do not.** Do not hide rows with unverifiable IDs. Excluding them silently loses data
the PM needs; the brief's position is to show and mark, not to suppress.

---

### TL-2.5 — Preserve previous and current ID; flag ID changes

**Brief:** §11 · **Blocked by:** TL-2.2

**Why.** Brief §11: when an activity's ID changes between revisions (A142 → A198) but
other evidence shows it is the same activity, the dashboard should retain both and flag
`⚠ ID changed`. "Do not silently replace one with the other."

**Files.**
- `rag-agent/backend/src/experimental/nusf_compare_engine.py` — match result construction
- `rag-agent/backend/src/version_1_0/adapters.py` — `_dashboard_meta` / row shaping
- `rag-agent/backend/src/version_1_0/formatters.py` — changed-activities table

**Do.**
1. On every matched pair, record `previous_source_id` and `current_source_id`.
2. Where both exist and differ, set an `id_changed` flag.
3. Surface it in the changed-activities table as an explicit change chip — the table
   already has a chip mechanism (`ni-change-chip--*`) and `diffs.py` already diffs an
   `id` field, so extend rather than invent.
4. An ID appearing or disappearing (one side `None`) is distinct from an ID *changing*.
   Encode all three cases separately.

**Acceptance criteria.**
- [ ] Matched pairs carry both IDs
- [ ] `id_changed` is set only when both IDs exist and differ
- [ ] The ID-change fixture from `TL-0.1` renders a visible change indicator
- [ ] Appeared / disappeared / changed are distinguishable in the output

**Verify.** `cd rag-agent/backend && pytest tests/trust/test_id_change_tracking.py -q`

**Do not.** Do not treat an ID change as automatic evidence of a different activity.
That decision belongs to match confidence (`TL-3.2`), and pre-empting it here would
inflate the added/removed counts.

---

### TL-2.6 — NUSF chunk format version bump

**Brief:** §41 · **Blocked by:** TL-2.2

**Why.** `to_nusf_chunks` writes a fixed 22-column CSV header prefixed
`"FORMAT: NUSF CSV — ..."`, and `parse_nusf_chunks` recognises it by that header.
Phase 2 adds fields; without a version marker, old and new chunks become
indistinguishable and the parser cannot know what it is reading.

**Files.**
- `rag-agent/backend/ingestion/normalization/engine.py` — `to_nusf_chunks` (~L482–563)
- `rag-agent/backend/src/experimental/nusf_compare_engine.py` — `parse_nusf_chunks`, `_is_nusf_header`

**Do.**
1. Add an explicit version token to the format header (e.g. `NUSF CSV v2`).
2. Make `parse_nusf_chunks` accept both v1 and v2, defaulting v2-only fields sensibly
   for v1 chunks so pre-existing sessions still compare (D3).
3. Add the new columns: `match_key`, `match_method`, and a provenance reference.
4. Assert round-trip stability: serialize → parse → serialize is idempotent.

**Acceptance criteria.**
- [ ] v1 chunks stored before this change still parse and compare successfully
- [ ] v2 chunks carry the new columns
- [ ] Round-trip is idempotent for both versions
- [ ] `_is_nusf_header` recognises both, and a test covers a v1/v2 mixed session

**Verify.** `cd rag-agent/backend && pytest tests/trust/test_nusf_format_versioning.py tests/test_nusf_compare_engine.py -q`

**Do not.** Do not break v1 parsing. Existing stored sessions are exactly the
backward-compatibility case D3 protects.
