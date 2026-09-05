# Nova Trust Layer — Implementation Plan

This directory turns `../brief.md` into an executable, trackable plan.

It is written to be followed by **either** a human developer **or** a coding agent
(Claude Code, OpenCode, Cursor, etc.) with no prior context on this conversation.
Everything an executor needs is in this directory plus the repo.

---

## Standing decisions

These were decided at plan time and are binding unless superseded in `DECISIONS.md`.

| # | Decision | Consequence |
|---|---|---|
| D1 | **Foundations first**, in the brief's own P0 order | Provenance and OCR-confidence capture land before identity/matching changes. Phases run strictly in order; do not jump ahead to the visible ID fix. |
| D2 | **Golden dataset is an external K&L dependency** | Engineering must never block on it. Phase 0 builds the harness against synthetic fixtures. Tasks that *calibrate thresholds* are explicitly gated on real data (`TL-0.6`) and marked `BLOCKED` until it arrives. |
| D3 | **Additive schema, regenerate on demand** | Every new field is optional/defaulted. Previously stored `dashboard_html` must keep rendering untouched. **No backfill job.** Trust surfaces appear only on newly generated reports. |

---

## The product rule this plan exists to enforce

> Nova must never pretend to know something it does not know.
> A missing answer is acceptable. An uncertain answer clearly marked as uncertain is acceptable.
> A confidently presented incorrect answer is not acceptable.

Two non-negotiables follow, and they override convenience at every task:

1. **The LLM is not the source of truth.** Anything computable in code is computed
   in code (brief §4, §15). If a task tempts you to "just ask the model", that is a
   signal the task is being done wrong.
2. **Prompt rules are the last layer, not the safety architecture** (brief §34).
   "Do not hallucinate" in a system prompt never counts as satisfying an acceptance
   criterion. Enforcement must be structural — types, validation, gating, tests.

---

## Where the work happens

| Area | Path |
|---|---|
| Analysis engine (FastAPI) | `rag-agent/backend/` |
| Ingestion pipeline | `rag-agent/backend/ingestion/` |
| Dashboard rendering | `rag-agent/backend/src/version_1_0/` |
| K&L app (Flask + React) | `kemp&lauritzen/` |
| Nova app (Flask + React) | `website/workspace/app/` |

Both client apps must reach parity at every user-visible phase. Kemp and Nova are a
branding skin over one pipeline — a trust feature built for one is a bug if it is
missing from the other.

---

## Execution protocol

Follow this loop. It is the same for a human and an agent.

1. **Read `PROGRESS.md`.** It is the single source of truth for state.
2. **Pick the next task**: the first `TODO` whose `Blocked by` column is empty or
   fully `DONE`, in the lowest-numbered open phase. Do not start a later phase while
   an earlier one has open tasks (D1), unless the task is explicitly marked
   `parallel-safe`.
3. **Open that phase file** (`phase-N-*.md`) and read the task in full, including
   its **Do not** section.
4. **Set the row to `IN_PROGRESS`** in `PROGRESS.md` before writing code.
5. **Implement**, touching only the files the task lists. If you must touch others,
   record why in `DECISIONS.md`.
6. **Run the task's `Verify` command.** A task is not done because the code looks
   right; it is done because the verification passes.
7. **Update `PROGRESS.md`**: status → `DONE`, fill the `Evidence` column with the
   commit SHA (or test-output path).
8. **Commit** with the task ID in the subject line, e.g.
   `TL-1.2: capture Azure per-cell OCR confidence and geometry`.
   Update `PROGRESS.md` in that same commit.

If you get blocked: set status `BLOCKED`, name the blocker in `Notes`, and move to
the next unblocked task. Never mark something `DONE` to keep moving.

If you disagree with a task's approach: append an entry to `DECISIONS.md` stating
the alternative and why, then proceed with the recorded decision. The plan is
allowed to change — silently diverging from it is not.

---

## Task IDs and status

IDs are stable and permanent: `TL-<phase>.<n>`. Never renumber. If a task is dropped,
mark it `SKIPPED` with a reason; do not reuse the ID.

| Status | Meaning |
|---|---|
| `TODO` | Not started |
| `IN_PROGRESS` | Actively being worked; at most a few at a time |
| `BLOCKED` | Cannot proceed; blocker named in Notes |
| `DONE` | Implemented **and** verification passed **and** evidence recorded |
| `SKIPPED` | Deliberately not doing; reason in Notes and `DECISIONS.md` |

---

## Definition of done — for the whole programme

Lifted from brief §50. The plan is complete when a K&L project manager can assume:

> If Nova presents something as VERIFIED, there is traceable evidence behind it.
> If Nova is uncertain, Nova tells me.

Concretely, all of the following hold:

- Nova knows which activities it can confidently identify, and which it cannot.
- Nova knows which activities it can confidently match across revisions.
- Ambiguous data is isolated rather than absorbed into results.
- Calculations are deterministic.
- Nova never invents a missing Activity ID — enforced structurally, proven by test.
- Nova never silently forces an uncertain match.
- Nova explains which results are verified and flags which are not.
- Nova can show the source behind important claims.
- Nova refuses to answer factual questions where evidence is insufficient.
- The agent cannot present unsupported factual claims as fact.

---

## Phase map

| Phase | Title | Theme | User-visible? |
|---|---|---|---|
| [0](phase-0-safety-net.md) | Safety net & vocabulary | Measure before changing; fix what lies | No |
| [1](phase-1-provenance.md) | Provenance & OCR confidence | Stop discarding evidence | No |
| [2](phase-2-identity.md) | Never invent an ID | The architectural rule | Yes (ID column) |
| [3](phase-3-matching.md) | Match confidence & no forced matching | Precision over coverage | Yes (review bucket) |
| [4](phase-4-trust-engine.md) | Trust Engine & propagation | Weakest-link confidence, gating | Partly |
| [5](phase-5-predictive-facts.md) | Deterministic facts for Predictive | Remove LLM from fact extraction | No |
| [6](phase-6-agent-contract.md) | Response contract & claim verification | No unsupported claims | Partly |
| [7](phase-7-trust-surface.md) | User-facing trust surface | Verified / Review / Unable to verify | Yes |
| [8](phase-8-review-queue.md) | Review queue & corrections | Human resolution that persists | Yes |
| [9](phase-9-evidence-audit.md) | Evidence, audit & Trust Center | Auditability, enterprise maturity | Yes |

Phases 0–6 correspond to the brief's **P0**, phases 7–8 to **P1**, phase 9 to **P2**.

---

## Running things

The engine lives in `rag-agent/backend` with a `.venv`:

```bash
cd rag-agent/backend
source .venv/bin/activate
pytest tests/ -q                      # existing suite — must stay green
pytest tests/trust/ -q                # trust-layer suite, created in Phase 0
python -m tests.trust.harness baseline # snapshot current behaviour
python -m tests.trust.harness compare  # diff against the baseline
```

Test files added by this plan live under `rag-agent/backend/tests/trust/`.
The existing suite in `tests/` is a mix of pytest modules and standalone scripts;
add new work as pytest modules only.
