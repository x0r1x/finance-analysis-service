# finance-analysis-service

**Русский** · [English](README.md)

Аналитический слой cash-flow модели, которую уже разобрал [finance-context-builder](https://github.com/x0r1x/finance-context-builder). FAS не читает Excel и не пересчитывает формулы. На входе `job_id` билдера. На выходе голова книги, привязка понятий, находки и отчёт `json` или `md`.

Гайды: [обзор](docs/ru/overview.md), [API](docs/ru/api.md), [глоссарий](docs/ru/glossary.md), [анализы](docs/ru/analyses.md), [архитектура](docs/ru/architecture.md), [настройки](docs/ru/settings.md).

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

Локальный override сам поднимает `redis`, `minio`, `finance-analysis` и `finance-context`. Прод — только `deploy/docker-compose.yml`, Redis и MinIO он не запускает. Redis — `redis:8.6.7-alpine` на `127.0.0.1:6379`. База `1` — FAS, `0` — билдер, `2` — агент, `15` — pytest. В MinIO один бакет, `finance-context`, порты `127.0.0.1:9000` и `127.0.0.1:9001`. FAS пишет под префиксом `fas/`. Тома — `finance_redis-data` и `finance_minio-data`. Compose репозитория finance-context-builder рядом не поднимать: он публикует те же порты MinIO.

Прод, только приложение. Redis тогда берётся из `.env`. Этот адрес должен резолвиться внутри контейнера. `127.0.0.1` из примера — процесс на хосте, контейнер его отвергает:

```bash
docker compose -f deploy/docker-compose.yml up -d --build --wait
```

Локально:

```bash
docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.override.yml up -d --build --wait
```

API снаружи — `http://127.0.0.1:8088`. В контейнере процесс слушает `8080`. Та же локальная команда поднимает билдер как `finance-finance-context-1` из локального образа `deploy-finance-context:latest` и публикует его на `127.0.0.1:8080`. Образ собирается в репозитории finance-context-builder. `up --build` здесь его не пересобирает.

`uv run fas-api` на хосте слушает `127.0.0.1`. Порт берётся из `FAS_PORT` в `.env`. По умолчанию `8080`. Redis — `redis://127.0.0.1:6379/1`.

Остановка локального стека — та же пара `-f` и `down`. Тома при этом остаются. `--volumes` стирает книги и очереди. Книги для поздней проверки лежат в `../finance-context-builder/resources/corpus`.

Wren и DuckDB работают внутри образа FAS. LibreOffice — внутри образа билдера. Embed, rerank, LLM и CLM этот Compose не запускает. Пустые `*_BASE_URL` оставляют эти ступени выключенными. CLM подключается отдельно.

Контейнер запускает `fas-api`. При `FAS_EMBEDDED_WORKERS=true` этот процесс держит четыре очереди и планировщик: `fas:interactive`, `fas:glossary`, `fas:batch`, `fas:maintenance`. Когда переменная не задана, их запускают вручную:

```bash
uv run fas-worker --queue fas:interactive
uv run fas-scheduler
```

Проверка:

```bash
curl -s http://127.0.0.1:8088/health/live
curl -s http://127.0.0.1:8088/health/ready
```

## CLI

- `uv run fas storage sync <source> <destination>` копирует object store. `--dry-run` и `--verify` необязательны.
- `uv run fas glossary export` пишет экспорт глоссария.
- `uv run fas glossary shadow <version>` строит shadow-отчёт релиза.
- `uv run fas calibrator train|activate|list` учит, включает или показывает калибратор. `activate` идёт вместе с аргументом версии.
- `uv run fas eval mapping` считает размеченные книги. `--prune` убирает понятия для прогона BLINKout. Подробности в [eval/README.md](eval/README.md).
- `uv run fas learn cluster|mine|compact` выполняет один шаг обучения.
- `uv run fas ops requeue [entry_id]` возвращает запись операции в очередь.
