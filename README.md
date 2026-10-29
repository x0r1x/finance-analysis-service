# finance-analysis-service

[Русский](README.ru.md) · **English**

Analysis layer for a cash-flow model that [finance-context-builder](https://github.com/x0r1x/finance-context-builder) has already parsed. FAS does not read Excel and does not recalculate formulas. The input is the builder `job_id`. The output is the book head, the concept mapping, findings, and a report in `json` or `md`.

Guides: [overview](docs/en/overview.md), [API](docs/en/api.md), [glossary](docs/en/glossary.md), [analyses](docs/en/analyses.md), [architecture](docs/en/architecture.md).

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

Redis from Compose is `redis:8.6.7-alpine` on `127.0.0.1:6379`:

```bash
docker compose -f deploy/docker-compose.yml up -d redis
uv run fas-api
```

`fas-api` listens on `FAS_HOST` / `FAS_PORT`, default `0.0.0.0:8080`. Compose publishes that same host port. finance-context-builder also uses host port 8080, so change the FAS host port to run both.

Workers are separate processes. The queues in Compose are `fas:interactive`, `fas:glossary`, `fas:batch`, and `fas:maintenance`:

```bash
uv run fas-worker --queue fas:interactive
uv run fas-scheduler
```

Check:

```bash
curl -s http://127.0.0.1:8080/health/live
curl -s http://127.0.0.1:8080/health/ready
```

## CLI

- `uv run fas storage sync <source> <destination>` copies the object store. `--dry-run` and `--verify` are optional.
- `uv run fas glossary export` writes the glossary export.
- `uv run fas glossary shadow <version>` runs the shadow report for a release.
- `uv run fas calibrator train|activate|list` trains, activates, or lists a calibrator. `activate` and the version argument belong together.
- `uv run fas eval mapping` scores the labeled books. `--prune` drops concepts for a BLINKout run. Details are in [eval/README.md](eval/README.md).
- `uv run fas learn cluster|mine|compact` runs one learning step.
- `uv run fas ops requeue [entry_id]` requeues an operation entry.
