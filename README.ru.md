# finance-analysis-service

**Русский** · [English](README.md)

Аналитический слой cash-flow модели, которую уже разобрал [finance-context-builder](https://github.com/x0r1x/finance-context-builder). FAS не читает Excel и не пересчитывает формулы. На входе `job_id` билдера. На выходе голова книги, привязка понятий, находки и отчёт `json` или `md`.

Гайды: [обзор](docs/ru/overview.md), [API](docs/ru/api.md), [глоссарий](docs/ru/glossary.md), [анализы](docs/ru/analyses.md), [архитектура](docs/ru/architecture.md).

Спека — [docs/design-v0.23.md](docs/design-v0.23.md). Гайды её не заменяют.

## Вход

FAS грузит книгу, которую билдер уже опубликовал. `BUILDER_BASE_URL` указывает на этот сервис. `POST /v1/books/{job_id}:load` читает его HTTP API. Файл `.xlsx` сюда не загружается.

## Окружение

Нужны Python 3.12+ и [uv](https://docs.astral.sh/uv/).

```bash
brew install uv
uv python install 3.12
uv sync
cp .env.example .env
```

`uv sync` создаёт `.venv` и ставит версии из `uv.lock`. Команды ниже идут через `uv run`. `.env` в git не входит. `Settings` его читает.

Без `FAS_REDIS_URL` процесс не стартует. Redis старше 8.6.5 тоже не принимается. `FAS_DATA_DIR` по умолчанию `./data`. Пустые `EMBED_BASE_URL`, `RERANK_BASE_URL`, `CLM_BASE_URL` и `LLM_BASE_URL` оставляют серверы моделей выключенными. Поиск понятия по метке при этом работает.

## Локальный запуск

Redis из Compose — `redis:8.6.7-alpine` на `127.0.0.1:6379`:

```bash
docker compose -f deploy/docker-compose.yml up -d redis
uv run fas-api
```

`fas-api` слушает `FAS_HOST` / `FAS_PORT`, по умолчанию `0.0.0.0:8080`. Compose публикует тот же хостовый порт. finance-context-builder тоже занимает хостовый `8080`, поэтому для двух сервисов сразу смените хостовый порт FAS.

Воркеры — отдельные процессы. Очереди в Compose: `fas:interactive`, `fas:glossary`, `fas:batch`, `fas:maintenance`.

```bash
uv run fas-worker --queue fas:interactive
uv run fas-scheduler
```

Проверка:

```bash
curl -s http://127.0.0.1:8080/health/live
curl -s http://127.0.0.1:8080/health/ready
```

## CLI

- `uv run fas storage sync <source> <destination>` копирует object store. `--dry-run` и `--verify` необязательны.
- `uv run fas glossary export` пишет экспорт глоссария.
- `uv run fas glossary shadow <version>` строит shadow-отчёт релиза.
- `uv run fas calibrator train|activate|list` учит, включает или показывает калибратор. `activate` идёт вместе с аргументом версии.
- `uv run fas eval mapping` считает размеченные книги. `--prune` убирает понятия для прогона BLINKout. Подробности в [eval/README.md](eval/README.md).
- `uv run fas learn cluster|mine|compact` выполняет один шаг обучения.
- `uv run fas ops requeue [entry_id]` возвращает запись операции в очередь.
