# Settings

[Русский](../ru/settings.md)

FAS reads every name below from the environment and from `.env` in the working directory. An environment value wins over `.env`. A line that starts with `#` is ignored. `cp .env.example .env` applies only the lines that have no `#`.

`FAS_HOST_PORT` defaults to `8088` and `BUILDER_HOST_PORT` defaults to `8080`. Compose reads those two from the shell when it publishes ports. They are not fields of `Settings`. The API is published on `127.0.0.1:8088`. The builder is published on `127.0.0.1:8080`.

`appendonly yes`, `appendfsync everysec`, and `maxmemory-policy noeviction` are the command of the `redis` service in `deploy/docker-compose.override.yml`. They are not application variables.

## Process

| Name | Default | What the process does |
| --- | --- | --- |
| `FAS_REDIS_URL` | none | Required. Startup fails when it is empty, when Redis does not answer, or when the server is older than 8.6.5. The path is the logical database. FAS uses database `1`. |
| `FAS_DATA_DIR` | `./data` | Root directory when S3 is off. The store path is this directory plus `FAS_S3_PREFIX`. |
| `FAS_HOST` | `127.0.0.1` | Address `uvicorn` binds. Compose sets `0.0.0.0` inside the container and publishes only `127.0.0.1:8088`. |
| `FAS_PORT` | `8080` | Port `uvicorn` binds. |
| `BUILDER_BASE_URL` | empty | Base URL of the builder HTTP API. Empty makes every builder call fail at once with "BUILDER_BASE_URL не задан". Production Compose sets an empty string so a copied `.env` cannot point the container at itself. The local override sets `http://finance-context:8080`. |
| `FAS_EMBEDDED_WORKERS` | `false` | `true` starts four `fas-worker` processes and `fas-scheduler` as children of `fas-api`. `false` leaves the queues to processes you start. Compose sets `true`. A child exits when the pid that spawned it is no longer its parent, unless that parent is PID 1. |
| `FAS_IN_CONTAINER` | `false` | Compose sets `true`. A Redis host of `127.0.0.1`, `localhost`, or `::1` then fails startup. Leave it unset for `uv run fas-api`. |
| `FAS_EMBEDDED_RESTART_BACKOFF_SEC` | `1` | Seconds a supervisor waits before it starts a dead embedded child again. Must be greater than 0. |
| `FAS_ADMIN_TOKEN` | empty | Empty allows glossary release writes. Any other value requires the request header `x-admin-token` to match it. |
| `FAS_READ_ONLY` | `false` | `true` makes the object store refuse writes. The conditional-write self-test is skipped. |
| `FAS_EVAL_DIR` | `eval` | `fas eval` reads labels from `FAS_EVAL_DIR/labels`. |
| `LOCK_TTL_MS` | `60000` | Lifetime of a book lock and of the GC lock. Also the floor of the pending idempotency TTL. |
| `LOAD_SYNC_SEC` | `20` | How long `POST /v1/books/{job_id}:load` waits for the builder. The pending idempotency key lives at least this many seconds plus 30. |
| `ETAG_TTL` | `300` | Seconds a cached findings payload stays in Redis. |

## Storage

S3 is on only when `FAS_S3_BUCKET`, `FAS_S3_ACCESS_KEY`, and `FAS_S3_SECRET_KEY` are all set. Any smaller mix is a startup error. With an endpoint the Wren source is `minio_file`. Without an endpoint it is `s3_file`. With no S3 at all the source is the local directory.

| Name | Default | What the process does |
| --- | --- | --- |
| `FAS_S3_ENDPOINT` | empty | MinIO or S3-compatible URL. Set it and Wren uses `minio_file`. |
| `FAS_S3_BUCKET` | empty | Bucket name. One of the three fields that turn S3 on. |
| `FAS_S3_PREFIX` | `fas` | Key prefix in the bucket. On disk it is the directory under `FAS_DATA_DIR`. |
| `FAS_S3_ACCESS_KEY` | empty | Access key. One of the three fields that turn S3 on. |
| `FAS_S3_SECRET_KEY` | empty | Secret key. One of the three fields that turn S3 on. |
| `FAS_S3_REGION` | `us-east-1` | Region passed to Wren `s3_file`. `minio_file` does not receive it. The local Compose MinIO is `ap-northeast-1`, so that value has to be set for that server. |
| `FAS_S3_SSL` | follows the endpoint | Unset is `false` only for an `http://` endpoint. An empty endpoint, `https://`, or a host with no scheme stays `true`. An explicit `true` or `false` is kept. Wren `minio_file` uses it as `ssl_enabled`. |

## Models

A stage is off until both its URL and its model name are set. An API key, when set, is sent as `Authorization: Bearer`. Embed and rerank retry `RETRY_MAX` times. CLM and LLM do not.

| Name | Default | What the process does |
| --- | --- | --- |
| `EMBED_BASE_URL` | empty | Embed server. The stage stays off while this or `EMBED_MODEL` is empty. Glossary lookup by label still works. |
| `EMBED_MODEL` | empty | Model name sent to the embed server. Also the model recorded on the example index when embed is on. |
| `EMBED_TIMEOUT_SEC` | `2` | Timeout of one embed call. |
| `EMBED_MAX_CONCURRENCY` | `16` | How many embed calls run at once. |
| `RERANK_BASE_URL` | empty | Rerank server. The stage stays off while this or `RERANK_MODEL` is empty. |
| `RERANK_MODEL` | empty | Model name sent to the rerank server. |
| `RERANK_DIALECT` | `cohere` | Request shape. `cohere` or `tei`. |
| `RERANK_TIMEOUT_SEC` | `3` | Timeout of one rerank call. |
| `RERANK_MAX_CONCURRENCY` | `8` | How many rerank calls run at once. |
| `CLM_BASE_URL` | empty | Choice server. The stage stays off while this or `CLM_MODEL` is empty. |
| `CLM_MODEL` | empty | Model name sent to the choice server. |
| `CLM_API_KEY` | empty | Bearer token for CLM. Omitted from the request when empty. |
| `CLM_TIMEOUT_SEC` | `10` | Timeout of one CLM call, and of the embed used to pick few-shot examples for a cluster. |
| `CLM_MAX_CONCURRENCY` | `4` | How many CLM calls run at once. |
| `CLM_MAX_CALLS_PER_BOOK` | `50` | Choice calls allowed for one book. `0` skips those calls even when the server is configured. |
| `LLM_BASE_URL` | empty | Completion server. The stage stays off while this or `LLM_MODEL` is empty. |
| `LLM_MODEL` | empty | Model name sent to the completion server. |
| `LLM_API_KEY` | empty | Bearer token for the LLM. Omitted from the request when empty. |
| `LLM_TIMEOUT_SEC` | `30` | Timeout of one completion, including the cluster draft. |
| `LLM_MAX_CONCURRENCY` | `4` | How many LLM calls run at once. |
| `CB_WINDOW_SEC` | `30` | Window in which model failures are counted. The builder client does not use this window. |
| `RETRY_BUDGET_PER_MIN` | `60` | Model retries the process will spend in one minute. |
| `MAPPING_DEADLINE_MS` | `60000` | Deadline passed into the mapping pipeline. |
| `RECALL_TOP_K` | `20` | How many concepts the embedding search keeps for one row. |
| `RERANK_TOP_K` | `5` | How many candidates remain after rerank. With no rerank server the pipeline keeps twice this many, ordered by recall score. |
| `QUESTION_MAX_CANDIDATES` | `5` | Candidates returned on one mapping question. |
| `KNN_K` | `5` | Nearest labeled examples attached to a row and to a cluster prompt. |
| `EXAMPLES_REFRESH_SEC` | `60` | The example index is not reloaded from storage more often than this. |

## Wren

The number of live engines is the smaller of `WREN_ENGINE_POOL` and `WREN_POOL_MEMORY_MB / WREN_DUCKDB_MEMORY_MB`, and at least 1. At that cap the oldest engine that nobody is using is closed.

| Name | Default | What the process does |
| --- | --- | --- |
| `WREN_ENGINE_POOL` | `32` | Cap on engines in the process. |
| `WREN_POOL_MEMORY_MB` | `8192` | Memory budget that can lower the cap above. |
| `WREN_DUCKDB_MEMORY_MB` | `512` | `SET memory_limit` on each DuckDB connection. Must be greater than 0. |
| `WREN_DUCKDB_THREADS` | `2` | `SET threads` on each DuckDB connection. Must be greater than 0. |
| `WREN_ENGINE_QUEUE_MAX` | `8` | An engine for a book is reused while its waiter count is below this. |
| `WREN_HOT_QUEUE` | `3` | A second engine for the same book starts only when the first engine already has at least this many waiters. |
| `WREN_ENGINES_PER_BOOK` | `2` | Engines one book may hold. Past this, a full queue returns "очередь движка переполнена". |
| `WREN_THREADS` | `8` | Size of the thread pool that runs Wren calls. |
| `CPU_THREADS` | `8` | Size of the thread pool that runs CPU work in the service. |

## API and quotas

| Name | Default | What the process does |
| --- | --- | --- |
| `API_MAX_INFLIGHT` | `64` | Handlers running at once. One more returns 503 "реплика перегружена". |
| `SYNC_DEADLINE_MS` | `10000` | Deadline of a synchronous HTTP call. A smaller `x-fas-deadline-ms` can only shorten it. Impact and ratios also wait at most 80 percent of this, and of the caller's wait, before they return 202. |
| `SYNC_MAX_PERIODS` | `120` | Impact and ratios return 202 when the book has more periods than this. |
| `OPERATION_WAIT_MAX_MS` | `30000` | Upper bound of the `wait_ms` query on an operation. |
| `SSE_ENABLED` | `true` | `false` makes `GET /v1/operations/{id}/events` answer 404 "SSE выключен". |
| `SSE_HEARTBEAT_SEC` | `15` | Seconds between SSE comments while no event arrives. |
| `IDEMPOTENCY_TTL` | `86400` | Seconds a finished idempotency record stays in Redis. |
| `RATE_USER_RPS` | `10` | Requests per second for one `X-User-Id`. |
| `RATE_USER_BURST` | `20` | Burst allowed on that user quota. |
| `RATE_CLIENT_RPS` | `50` | Requests per second for one `X-Client-Id`. |
| `RATE_CLIENT_BURST` | `100` | Burst allowed on that client quota. |
| `RATE_ANON_RPS` | `50` | Shared requests per second when both the user and the client are anonymous. The burst paired with it is 20 and is not a setting. |
| `USER_MAX_INFLIGHT` | `8` | Concurrent requests stored for one user. Past this the call is "слишком много запросов пользователя". |
| `REDIS_MAX_CONNECTIONS` | `64` | Size of the shared `redis.asyncio` pool in one process. The Taskiq broker opens its own connection. |

A Redis error inside the rate-limit script allows the request through. A Redis error on the user-inflight counter does not: that call fails as Redis unavailable.

## Queue

`GC_CRON` runs incomplete-build GC on `fas:maintenance`. `UNMAPPED_CLUSTER_CRON` and `GLOSSARY_MINE_CRON` run on `fas:batch`. `COMPACT_CRON` runs learning compaction on `fas:maintenance`.

| Name | Default | What the process does |
| --- | --- | --- |
| `GC_INCOMPLETE_AGE` | `1h` | Age after which GC deletes an incomplete build. A suffix `h`, `m`, or `s` is hours, minutes, or seconds. A bare number is seconds. |
| `GC_CRON` | `0 3 * * *` | When that GC is enqueued. |
| `RETRY_MAX` | `2` | Extra attempts after a failed builder call or a failed embed or rerank call. |
| `USER_MAX_QUEUED` | `20` | Tasks one user may already have waiting on one queue. |
| `TASKIQ_IDLE_TIMEOUT_MS` | `60000` | Idle time after which another worker may claim a task that was not acknowledged. |
| `TASKIQ_LEASE_REFRESH_SEC` | `15` | How often a worker extends the lease of a task it is still running. |
| `TASKIQ_RECLAIM_INTERVAL_SEC` | `10` | How often a worker looks for abandoned tasks. |
| `TASKIQ_RECLAIM_LOCK_SEC` | `30` | How long one worker holds the reclaim lock, and the broker's unacknowledged-lock timeout. |
| `TASKIQ_STREAM_MAXLEN` | `100000` | Approximate maximum length of a queue stream. |
| `OP_HEARTBEAT_SEC` | `15` | How often a running operation writes a heartbeat. A heartbeat younger than twice this is treated as fresh. |
| `OP_STALE_SEC` | `120` | Reconcile closes an operation that has no heartbeat this fresh. With no heartbeat at all, the operation must also be at least this old. |
| `TASK_RETRY_MAX` | `2` | Failures of one task before it is marked failed and moved to the dead-letter stream. The broker schedules one more attempt than this number. |
| `TASK_RETRY_BASE_SEC` | `5` | Base of the jittered delay before a task retry. |
| `TASK_RETRY_MAX_DELAY_SEC` | `300` | Cap on that delay. |
| `HEAVY_STAGE_TIMEOUT_SEC` | `1800` | An isolated heavy stage is killed after this many seconds. |
| `HEAVY_STAGE_KILL_GRACE_SEC` | `5` | Seconds that stage gets after the timeout signal. |
| `HEAVY_STAGE_MEMORY_MB` | `4096` | Memory cap of that stage. |
| `CB_FAILURES` | `5` | Failures that open the builder circuit and a model circuit. |
| `CB_OPEN_SEC` | `30` | Seconds those circuits stay open. |
| `SHUTDOWN_GRACE_SEC` | `25` | Seconds an embedded child is given to exit. |

## Glossary and learning

| Name | Default | What the process does |
| --- | --- | --- |
| `PROPOSE_MIN_BOOKS` | `3` | A cluster becomes a glossary proposal only when it spans this many books. A row marked critical skips this floor. |
| `UNMAPPED_CLUSTER_CRON` | `0 4 * * *` | When unmapped clustering is enqueued. |
| `UNMAPPED_MIN_CLUSTER` | `2` | `min_cluster_size` for HDBSCAN when row embeddings exist. Groups built from the label alone do not use it. |
| `GLOSSARY_MINE_CRON` | `30 4 * * *` | When glossary mining is enqueued. |
| `COMPACT_CRON` | `0 2 * * *` | When learning compaction is enqueued. |
| `GLOSSARY_AUTO_PROMOTE` | `false` | `true` lets mining write labels that already cleared the auto decision, and only while no canary is active. `false` leaves those rows as proposals. |
| `GLOSSARY_AUTO_MIN_BOOKS` | `3` | Books a mined label must appear in before it can be auto. |
| `GLOSSARY_AUTO_MIN_CONFIRMATIONS` | `2` | Confirmations that label must have. |
| `GLOSSARY_SHADOW_RECENT_BOOKS` | `50` | How many of the latest glossary jobs a shadow report includes. |
| `GLOSSARY_CANARY_SHARE` | `10` | Percent of books, from 0 to 100, that read a canary release. The release stores this share. A book is in the canary when `sha256(job_id) % 100` is below it. |
| `GLOSSARY_CANARY_HOURS` | `48` | Hours a canary waits before it may promote. |
| `GLOSSARY_CANARY_MIN_BOOKS` | `10` | Books that must be on the canary before that promotion. |
| `GLOSSARY_CANARY_MIN_ROWS` | `200` | Coverage rows those books must contain. |
| `GLOSSARY_CANARY_MAX_HOURS` | `168` | Hours after which a canary that stayed quiet can still promote. |
| `REMAP_BATCH_BOOKS` | `20` | Books one remap batch updates. |
| `REMAP_BOOKS_PER_MIN` | `60` | Pace of the rest of a remap. The pause between batches is `REMAP_BATCH_BOOKS / REMAP_BOOKS_PER_MIN` minutes. |
| `RECALIBRATE_EVERY` | `500` | New positive human confirmations or corrections required before the calibrator trains again. |
| `CALIBRATOR_MAX_RISK` | `0.02` | `max_risk` passed into that training. |
