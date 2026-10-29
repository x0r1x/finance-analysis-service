# Architecture

[Русский](../ru/architecture.md)

The tree is the layering. `adapters` talks to HTTP, Redis, the object store, the builder, and the model servers. `application` is the use cases (`FasService`, analyses, the glossary, the mapping pipeline). `domain` holds the rules that do not know about I/O. Audit rules live in `plugins/rules`.

A request enters `adapters/api`. The route checks ids and maps errors, then calls the application service.

## Storage

One backend per process. Set `FAS_S3_BUCKET` and the process uses S3. Otherwise it uses the directory in `FAS_DATA_DIR`. There is no fallback from one to the other. `fas storage sync` copies between two URLs.

Book files are immutable Parquet under `books/{job_id}/{build_key}/`. Derived tables for one journal position live under `derived/{derive_key}/`. The book head points at the current `build_key`, `state_seq`, and `derive_key`.

## Redis and workers

Redis is required. It holds locks, the operation log, idempotency keys, and the Taskiq queues. The API process does not run those queues.

Compose starts one worker on each queue, plus the scheduler:

| Process | Command |
| --- | --- |
| interactive | `fas-worker --queue fas:interactive` |
| glossary | `fas-worker --queue fas:glossary` |
| batch | `fas-worker --queue fas:batch` |
| maintenance | `fas-worker --queue fas:maintenance` |
| scheduler | `fas-scheduler` |

The code registers scheduled work on two of those queues. `fas:batch` runs unmapped clustering, glossary mine, and recalibration. `fas:maintenance` runs compaction, GC of incomplete builds, and operation reconcile. A `fas.run` payload names its queue or lands on `fas:interactive`. Analysis work that returns `202`, including `full`, stays in the API process. See [analyses](analyses.md).

## Query engine

Wren is an in-process DuckDB engine over the book's Parquet. Compose does not run a Wren service. Series, slice, and expression go through it. DuckDB returns sums. Ratios are computed in Python `Decimal` after that.

Model servers are optional HTTP dependencies (`EMBED_BASE_URL`, `RERANK_BASE_URL`, `CLM_BASE_URL`, `LLM_BASE_URL`). With all four empty, mapping stays lexical.

The layer diagram, the on-disk layout, and the queue classes are in [design-v0.23.md](../design-v0.23.md) §8, §9, and §10.
