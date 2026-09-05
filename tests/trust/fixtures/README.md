# Trust-layer fixture corpus

Synthetic (never real client data — see `../../../changes/trust-layer/plan/phase-0-safety-net.md`
TL-0.1 "Do not") old/new schedule pairs with a known-by-construction ground truth. This
corpus is the regression harness's substrate until `EXT-1` (real, anonymized K&L
schedule pairs) lands — see `PROGRESS.md`.

Every fixture directory contains:
- `old.<ext>` / `new.<ext>` — the two revisions (absent `new.*` for `kind: "single"`)
- `ground_truth.json` — `kind`, `reference_date`, `expected` (what `run_health()`
  must produce), and `notes` (why, and what gap in today's pipeline this fixture
  documents, if any)

Load them with `tests.trust.harness.load_fixtures()`. Run one through the
deterministic engine with `run_health(fixture)` / `run_predictive(fixture)`.

All fixtures are offline: CSV or hand-written MSPDI XML only, no scanned PDF, no
Azure OCR, no LLM call. None currently sets `requires_azure: true`.

| Fixture | Brief §§ | What it exercises |
|---|---|---|
| `01_clean_durable_ids` | §12, §15, §35 | The easy path: a durable `Entydigt Id` column, one behind/one ahead/one on-schedule activity, one add, one remove, all four change types (start/finish/duration/progress). Baseline control every later phase must keep passing. |
| `02_mspdi_positional_id` | §9, §10, §12, §35 | MS Project XML export. The display `ID` column is purely positional and renumbers on every pre-existing task when a new task is inserted. Proves matching already keys off name, not the renumbered ID — the exact ID problem in brief §9. |
| `03_duplicate_names_daek` | §12, §35 | Five/six identically-named activities at one location, non-durable ID. Exercises the grouped, greedy nearest-date matching path (`nusf_compare_engine._resolve_activity_matches`) that a naive 1:1 identity join would get wrong. |
| `04_id_changed_same_activity` | §11, §12 | Same name/location/trade, ID changes between revisions (schedule tool regenerates its "stable" ID on export). Match still succeeds — but the previous ID is not preserved anywhere in the output (documents the brief §11 gap, owned by `TL-2.5`). |
| `05_ambiguous_no_forced_match` | §13 | Brief's own ventilation example, verbatim: one old activity, three plausible-but-not-identical new candidates. Confirms today's baseline never force-matches — it reports one remove and three adds rather than guessing. |
| `06_zero_delayed` | §35 | Healthy schedule, nothing behind. Control fixture so a matching/status regression that starts manufacturing delays out of nothing has something to fail against. |
| `07_data_quality_conflicts` | §27, §7, §29 | Duplicate ID across two differently-named rows, 150% progress, inverted start/finish. Documents three real, currently-undetected gaps (duplicate ID silently drops an activity from comparison; >100% is silently clamped; Rule 101 can never fire because dates are pre-swapped) — this is the "before" snapshot `TL-0.5` and `TL-4.5` work against. |
| `08_empty_headers_only` | §35, §28 | Header row, zero data rows. `IngestionPipeline.run()` correctly raises rather than returning a fake empty-but-successful schedule. Single-file (`kind: "single"`), no `new.*`. |

## Adding a fixture

1. Create `fixtures/<id>/`, write `old.<ext>` (and `new.<ext>` unless `kind: "single"`).
2. Run it through the harness and read the real output — do not hand-compute expected
   numbers for anything touching date arithmetic or rounding; the engine's rounding
   behaviour is easy to get subtly wrong by hand and the point of `ground_truth.json`
   is to be trustworthy, not merely plausible.
3. Write `ground_truth.json`: `brief_ref`, `description`, `kind`, `format`,
   `reference_date`, `expected` (only the facts this fixture is actually meant to
   pin down — not full snapshot parity, that's what `TL-0.2`'s baseline is for),
   and `notes` (state plainly if the fixture is documenting a known gap rather than
   asserting correct behaviour).
4. Add a row to the table above.
