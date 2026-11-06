# API

[Русский](../ru/api.md)

Routes below are the ones registered in `adapters/api`. A field-by-field body is not copied here. It lives in [design-v0.23.md](../design-v0.23.md) §3, and the live argument card is `GET /v1/capabilities`.

`X-User-Id` and `X-Client-Id` name the actor. FAS does not authenticate them. A `POST` carries `Idempotency-Key`. Work that does not finish inside the sync deadline returns `202` plus an operation. Poll `GET /v1/operations/{op_id}`, or read `GET /v1/operations/{op_id}/events` (`text/event-stream`) when `SSE_ENABLED` is on.

## Process

- `GET /health/live` — the process is up.
- `GET /health/ready` — Redis and storage answer.
- `GET /metrics` — Prometheus text.
- `GET /v1/capabilities` — `fas_version`, `phase` (`"4"`), storage, rules, metrics, concepts, renderers (`json`, `md`), problems, and `tools[]`.

Each tool has `name`, `description`, `method`, `path`, `parameters`, `in`, and `strict`. `parameters` is a JSON Schema. `in` says where each argument goes: `path`, `query`, or `body`. The client drops nulls, substitutes `job_id` from its own session into the path, and splits the remaining arguments by `in`. `evaluate_expression` is the only tool with `strict: false`. The sixteen names are `get_book`, `get_coverage`, `get_mapping`, `get_semantics`, `resolve_periods`, `get_series`, `get_slice`, `evaluate_expression`, `run_analysis`, `list_findings`, `explain_finding`, `compare`, `submit_decisions`, `get_report`, `get_operation`, `resolve_concept`.

## Book

`{job_id}` is the builder job.

- `POST /v1/books/{job_id}:load` — load the book from the builder.
- `GET /v1/books/{job_id}` — head, coverage summary, warnings.
- `GET /v1/books/{job_id}/builds` and `GET /v1/books/{job_id}/builds/{build_key}` — build history and one build.
- `GET /v1/books/{job_id}/mapping` — binding rows. Query: `status`, `concept`, `importance`, `q`. `counts` are taken before the filter.
- `GET /v1/books/{job_id}/semantics` — signs, phases, and the other semantic rows.
- `GET /v1/books/{job_id}/coverage` — concept coverage.
- `GET /v1/books/{job_id}/questions` — open questions for this book.
- `POST /v1/books/{job_id}/series` — values by period. One of `row_keys`, `binding_keys`, `concepts` must be non-empty.
- `POST /v1/books/{job_id}/slice` — a cube slice. The only time dimension is `period_start`.
- `POST /v1/books/{job_id}/expression` — an expression over row bindings.
- `POST /v1/books/{job_id}/periods:resolve` — periods for a phrase.
- `GET /v1/books/{job_id}/decisions` and `POST /v1/books/{job_id}/decisions` — read and append the journal.
- `POST /v1/books/{job_id}/mapping:infer` — rebuild the inferred mapping. Returns `202`.
- `GET /v1/books/{job_id}/metrics/{metric_id}/trace` — read-only metric → concept → binding → cell trace (meta-layer phase 4). Query: `variant`.

## Analyses

- `POST /v1/books/{job_id}/analyses` — `type` is `audit`, `ratios`, `impact`, or `full`. See [analyses](analyses.md).
- `GET /v1/books/{job_id}/analyses` and `GET /v1/books/{job_id}/analyses/{analysis_id}` — list and one stored analysis.
- `GET /v1/books/{job_id}/analyses/{analysis_id}/report?format=json|md` — render the stored result.
- `GET /v1/books/{job_id}/findings` — findings of the last audit. Query: `build_key`, `rule`, `severity`, `concept`, `page_size`, `page_token`.
- `GET /v1/books/{job_id}/findings/{fingerprint}` — one finding plus a trace. Query: `build_key`, `direction` (`precedents` or `dependents`), `depth`.
- `POST /v1/books/{job_id}:compare` — two builds, two scenarios, or two books.

## Operations

- `GET /v1/operations` — list. Query: `kind`, `job_id`, `status`.
- `GET /v1/operations/{op_id}` — one operation. `wait_ms` long-polls.
- `GET /v1/operations/{op_id}/events` — server-sent events for that path only.
- `POST /v1/operations/{op_id}:cancel` — cancel a queued or running operation.

## Glossary and profiles

Glossary routes are listed in [glossary](glossary.md). Profile routes:

- `GET /v1/profiles`
- `GET /v1/profiles/{profile}`
- `PUT /v1/profiles/{profile}`
