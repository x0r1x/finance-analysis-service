# Analyses

[Русский](../ru/analyses.md)

`POST /v1/books/{job_id}/analyses` takes `type` of `audit`, `ratios`, `impact`, or `full`. Any other value is `400`. A non-null `include` is `400` (`поле include не принимается`). `include: null` is ignored.

`audit` and `ratios` wait inside the sync deadline (`SYNC_DEADLINE_MS`, and `LOAD_SYNC_SEC` on the HTTP call). `ratios` and `impact` also return `202` when the book has more periods than `SYNC_MAX_PERIODS`, or when `async` is true. `full` always returns `202` with an `op_id`. The run is a Taskiq job on `fas:interactive` (`stage: analysis.full`), so a `fas-worker` for that queue must be up — either a process you start, or children of `fas-api` when `FAS_EMBEDDED_WORKERS=true` (Compose sets this). Audit, ratios, and impact that return `202` still run in the API process.

Enqueue pins `build_key`, `state_seq`, `derive_key`, and `analysis_semantic_model` into `stage_args`. The worker builds the Target from that snapshot, not from the live book head. If the worker dies mid-`analysis.full`, the operation ends failed or cancelled under the existing runner rules. The client must POST a new `type: full`. There is no automatic safe resume (`analysis` is not in `_IDEMPOTENT`).

`render` is `json` or `md`. It selects the report format stored with the result. The default metrics for `full`, when `metrics` is omitted, are `dscr` only.

`total_debt` is the stock `borrowings_lt + borrowings_st + lease_liability` on one date (RSBU lines 1410 and 1510 plus the FSBU 25 / IFRS 16 lease liability). It is not a ratio. Ask for it by name in `metrics`. The profile fields are `debt_standard` (`ras`, `ifrs`, `gaap`; default `ras`) and `include_operating_lease_liability` (default true, US GAAP only). A missing lease source returns `not_computed` rather than borrowings alone. Corporate books treat it as optional; project finance does not use it.

## What each type does

`audit` runs the selected rules. Omit `rules` and every rule runs. An empty `rules` list runs none.

`ratios` requires a non-empty `metrics` list. The allowed names are the `metrics` array in `GET /v1/capabilities`. On a confident primary model type, `result_data.book_rows` cites book cells for the type slice (`cited` / `absent` / `ambiguous` + `observations`). Contract: `adapters/storage/schemas/book_rows.json` (`book_rows@1.0`).

`impact` traces one target. Pass `target` as a `cell_id`, a `row_key`, or a `concept`. `direction` is `precedents` or `dependents`. `depth` defaults when it is omitted.

`full` runs ratios, then audit, then impact when `target` is present.

`POST /v1/books/{job_id}:compare` is not an analysis type. It compares two builds, two saved scenarios, or two books (`other.job_id`). It does not emit a metric delta between cases.

## Report and findings

`GET /v1/books/{job_id}/analyses/{analysis_id}/report?format=json|md` renders the stored `result.json`. The same result is byte-identical on a second read. `GET` does not recompute and does not call a model.

`GET /v1/books/{job_id}/findings` reads the last audit on `build_key`, or on the current head when `build_key` is omitted. `rule`, `severity`, and `finding_kind` are comma-separated (`finding_kind` ∈ `error|warning|methodology|insufficient_data|ambiguity`). `concept` keeps findings whose row is bound to that concept. `page_size` defaults to 50.

`GET /v1/books/{job_id}/findings/{fingerprint}` explains one finding and traces its formula graph. `direction` defaults to `precedents`. A fingerprint from an older build needs that build's `build_key`, or the lookup uses the current head and returns `404`.

Rule codes, the ratio formulas, and the finding shape are in [design-v0.23.md](../design-v0.23.md) §6.
