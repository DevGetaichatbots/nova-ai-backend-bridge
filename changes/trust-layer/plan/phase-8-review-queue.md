# Phase 8 — Review queue & corrections

**Goal.** Give humans a way to resolve what Nova refused to guess — and make sure they
never have to resolve the same thing twice.

**User-visible change.** Yes — a new review surface in both apps.

**Why this phase must exist.** Phase 3 deliberately increased the number of unresolved
items: Nova now says "requires verification" where it previously forced a match. That is
correct (brief §37: precision first), but without a resolution path it is just a worse
product. Brief §25 and §26 close the loop.

---

### TL-8.1 — Review queue data model + backend

**Brief:** §25 · **Blocked by:** TL-7.8 · **Blocks:** TL-8.2, TL-8.3

**Why.** Brief §25 specifies the shape: "31 items require review", categorised as
low-confidence IDs, uncertain matches, unreadable dates, conflicting values.

**Files.**
- create `rag-agent/backend/src/trust/review_queue.py`
- `rag-agent/backend/src/main.py` (endpoints)
- `kemp&lauritzen/backend/routes/schedule.py`
- `website/workspace/app/Nova-Insights-Backend/routes/schedule.py`

**Do.**
1. Define `ReviewItem`: category, affected activity/activities, the evidence Nova has,
   the candidate options, and the resolution state.
2. Categories per brief §25: low-confidence IDs, uncertain activity matches, unreadable
   dates, conflicting values. Source conflicts from `TL-4.5` feed in here.
3. Endpoints: list items for a session, resolve an item, reopen a resolution.
4. Persist per project/session, scoped to the tenant. Note the asymmetry: the Nova app
   has `company_id` multi-tenant scoping, Kemp does not — the queue must respect both.
5. Resolutions are additive records, never destructive edits to source data.

**Acceptance criteria.**
- [ ] All four brief §25 categories representable
- [ ] Items carry candidate options where a choice is required
- [ ] Endpoints exist in both Flask backends with correct auth and tenant scoping
- [ ] Resolutions never mutate extracted source values
- [ ] Read-only users cannot resolve items

**Verify.** `cd rag-agent/backend && pytest tests/trust/test_review_queue.py -q`

**Do not.** Do not let a resolution overwrite the extracted value. The original reading
and the human decision are separate facts, and both are needed for audit (Phase 9).

---

### TL-8.2 — Review queue UI

**Brief:** §25, §42 · **Blocked by:** TL-8.1

**Why.** Brief §25's example interaction: *"Nova found two possible matches for Activity
'Ventilation Level 2' — Option A / Option B / No match."*

**Files.**
- `kemp&lauritzen/app/src/components/` (new review component)
- `website/workspace/app/src/components/` (new review component)
- `kemp&lauritzen/app/src/services/`, `website/workspace/app/src/services/`

**Do.**
1. Surface the review count from the dashboard, linking into the queue.
2. For each item, show Nova's evidence — why it is uncertain — then the options.
   "No match" is always an explicit, first-class choice.
3. Show the consequence of resolving: which comparison results will change.
4. Brand and locale parity, same requirement as `TL-7.6`. Kemp is Danish-only.
5. Note the rendering constraint: dashboards render inside a sandboxed iframe
   (`sandbox="allow-scripts"`, no `allow-same-origin` on the Health path). The review UI
   must live in the parent app, not inside the iframe.

**Acceptance criteria.**
- [ ] Review count visible from the dashboard, links to the queue
- [ ] Each item shows evidence, options, and "No match"
- [ ] Consequence of resolution shown before confirming
- [ ] Both apps, both locales
- [ ] Review UI is outside the sandboxed iframe

**Verify.** Manual walkthrough of the brief §25 ventilation scenario in both apps.

**Do not.** Do not put the review UI inside the dashboard iframe — it cannot reach the
parent app's auth context there.

---

### TL-8.3 — Verified match mapping store

**Brief:** §26 · **Blocked by:** TL-8.1 · **Blocks:** TL-8.4

**Why.** Brief §26: *"Do not make him correct the same deterministic ambiguity every
upload if the relevant identity relationship remains valid."* Andreas resolving the same
ambiguity on every weekly upload would destroy trust faster than the original problem.

**Files.**
- `rag-agent/backend/src/trust/review_queue.py`
- create migration for `verified_match_mapping`

**Do.**
1. Store confirmed identity relationships scoped to the project: activity X in revision 1
   is activity Y in revision 2.
2. Version every mapping with the evidence it was based on and who confirmed it, when.
3. On subsequent comparisons, consult the store *before* falling back to ambiguity —
   a human-confirmed mapping is `L1`-equivalent confidence and should be labelled as
   human-verified, distinct from source-ID-verified.
4. Mappings are project-scoped, never global.

**Acceptance criteria.**
- [ ] Confirmed mappings persist and are reused on the next upload
- [ ] Each mapping records evidence, author, and timestamp
- [ ] Human-verified matches are distinguishable from source-verified ones
- [ ] Mappings do not leak across projects or tenants

**Verify.** `cd rag-agent/backend && pytest tests/trust/test_match_mapping.py -q`

**Do not.** Do not make human-confirmed mappings globally applicable. The same activity
name means different things on different projects.

---

### TL-8.4 — Corrections feed back into matching

**Brief:** §26 · **Blocked by:** TL-8.3 · **Blocks:** TL-8.5

**Why.** A stored mapping nobody consults is a database table, not a feature.

**Files.**
- `rag-agent/backend/src/experimental/nusf_compare_engine.py` — `_resolve_activity_matches`
- `rag-agent/backend/src/trust/matching.py`

**Do.**
1. Consult the mapping store during match resolution, before ambiguity detection.
2. A mapped pair resolves at human-verified confidence and skips the review queue.
3. Record in `MatchResult.method` that this came from a human decision — it must remain
   visible in "Why?" (`TL-7.5`) and in the audit log (`TL-9.2`).
4. A human mapping that contradicts strong source evidence (e.g. both sides now have
   different verified IDs) raises a conflict rather than silently winning — this is the
   invalidation trigger handled in `TL-8.5`.

**Acceptance criteria.**
- [ ] Mapped pairs skip the review queue on subsequent uploads
- [ ] Match method records human verification
- [ ] "Why?" shows that a human confirmed this match, and when
- [ ] Contradiction between mapping and strong source evidence raises a conflict

**Verify.** `cd rag-agent/backend && pytest tests/trust/test_correction_feedback.py -q`

**Do not.** Do not let a stored mapping silently override contradicting source evidence.
Brief §26's caveat — mappings must be invalidated when evidence changes materially — is
the whole safety condition on this feature.

---

### TL-8.5 — Mapping invalidation

**Brief:** §26 · **Blocked by:** TL-8.4 · **Blocks:** Phase 9

**Why.** Brief §26: *"mappings must be versioned and invalidated when underlying evidence
changes materially."* Without this, a correct decision from March silently corrupts
August's comparison after the activity has been split, renamed, or rescoped.

**Files.**
- `rag-agent/backend/src/trust/review_queue.py`
- `rag-agent/backend/src/trust/matching.py`

**Do.**
1. Define what "materially changed" means, concretely and testably. At minimum:
   the activity name changes beyond a similarity threshold; the location/area changes;
   a verified source ID appears on either side that contradicts the mapping; the activity
   is split into multiple activities.
2. On material change, invalidate the mapping and return the item to the review queue
   with an explanation of what changed.
3. Keep the invalidated mapping in history — never delete it (audit, Phase 9).
4. Show the user why a previously-resolved item has returned. An item silently
   reappearing reads as a bug.

**Acceptance criteria.**
- [ ] Material-change criteria defined, documented, and tested
- [ ] Invalidated mappings return to the queue with an explanation
- [ ] Invalidation history retained
- [ ] Fixture: resolve a match, materially change the activity, confirm invalidation

**Verify.** `cd rag-agent/backend && pytest tests/trust/test_mapping_invalidation.py -q`

**Do not.** Do not delete invalidated mappings. Do not re-surface an item without
explaining what changed.
