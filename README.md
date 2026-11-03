# finance-analysis-service

[Русский](README.ru.md) · **English**

Analysis layer for a cash-flow model that [finance-context-builder](https://github.com/x0r1x/finance-context-builder) has already parsed. FAS does not read Excel and does not recalculate formulas. The input is the builder `job_id`. The output is the book head, the concept mapping, findings, and a report in `json` or `md`.

Guides: [overview](docs/en/overview.md), [API](docs/en/api.md), [glossary](docs/en/glossary.md), [analyses](docs/en/analyses.md), [architecture](docs/en/architecture.md), [settings](docs/en/settings.md).

The spec is [docs/design-v0.23.md](docs/design-v0.23.md). These guides do not replace it.

## Input

FAS loads a book that the builder has already published. Set `BUILDER_BASE_URL` to that service. `POST /v1/books/{job_id}:load` reads the builder HTTP API. An `.xlsx` upload is not accepted here.

## Environment setup

Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
brew install uv
uv python install 3.12
uv sync
cp .env.example .env
```

`uv sync` creates `.venv` and installs the versions pinned in `uv.lock`. Commands below use `uv run`. `.env` is gitignored. `Settings` reads it.

The process refuses to start without `FAS_REDIS_URL`, and it refuses a Redis older than 8.6.5. `FAS_DATA_DIR` defaults to `./data`. Leave `EMBED_BASE_URL`, `RERANK_BASE_URL`, `CLM_BASE_URL`, and `LLM_BASE_URL` empty to keep the model servers off. Glossary lookup by label still works.

## Local run

The local override starts `redis`, `minio`, `finance-analysis`, and `finance-context`. Production uses only `deploy/docker-compose.yml` and does not start Redis or MinIO. Redis is `redis:8.6.7-alpine` on `127.0.0.1:6379`, database `1` for FAS (`0` builder, `2` agent, `15` pytest). MinIO has one bucket, `finance-context`, on `127.0.0.1:9000` and `127.0.0.1:9001`. FAS writes under the prefix `fas/`. Volumes are `finance_redis-data` and `finance_minio-data`. Do not start the finance-context-builder Compose while this stack is up. That file publishes the same MinIO ports.

Production, the app only. Redis then comes from `.env`:

```bash
docker compose -f deploy/docker-compose.yml up -d --build --wait
```

Local:

```bash
docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.override.yml up -d --build --wait
```

The API is published on `http://127.0.0.1:8088`. Inside the container it still listens on `8080`. The same local command starts the builder as `finance-finance-context-1` from the local image `deploy-finance-context:latest` and publishes it on `127.0.0.1:8080`. That image is built in the finance-context-builder repo. `up --build` here does not rebuild it.

`uv run fas-api` on the host listens on `127.0.0.1`. The port comes from `FAS_PORT` in `.env`. The default is `8080`. Redis is `redis://127.0.0.1:6379/1`.

Stop the local stack with the same two `-f` files and `down`. That keeps the volumes. Add `--volumes` only when you mean to erase books and queues. Workbooks for a later check come from `../finance-context-builder/resources/corpus`.

Wren and DuckDB run inside the FAS image. LibreOffice runs inside the builder image. Embed, rerank, LLM, and CLM are not started here. Leave their `*_BASE_URL` empty and those stages stay off. CLM is connected separately.

The container runs `fas-api`. With `FAS_EMBEDDED_WORKERS=true`, that process keeps the four queues and the scheduler as its own children: `fas:interactive`, `fas:glossary`, `fas:batch`, and `fas:maintenance`. When the variable is unset, run them yourself:

```bash
uv run fas-worker --queue fas:interactive
uv run fas-scheduler
```

Check:

```bash
curl -s http://127.0.0.1:8088/health/live
curl -s http://127.0.0.1:8088/health/ready
```

## CLI

- `uv run fas storage sync <source> <destination>` copies the object store. `--dry-run` and `--verify` are optional.
- `uv run fas glossary export` writes the glossary export.
- `uv run fas glossary shadow <version>` runs the shadow report for a release.
- `uv run fas calibrator train|activate|list` trains, activates, or lists a calibrator. `activate` and the version argument belong together.
- `uv run fas eval mapping` scores the labeled books. `--prune` drops concepts for a BLINKout run. Details are in [eval/README.md](eval/README.md).
- `uv run fas learn cluster|mine|compact` runs one learning step.
- `uv run fas ops requeue [entry_id]` requeues an operation entry.
