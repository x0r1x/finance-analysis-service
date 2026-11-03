# Архитектура

[English](../en/architecture.md)

Дерево каталогов и есть слои. `adapters` говорит с HTTP, Redis, object store, билдером и серверами моделей. `application` — сценарии (`FasService`, анализы, глоссарий, конвейер привязки). `domain` держит правила, которым не нужен ввод-вывод. Правила аудита лежат в `plugins/rules`.

Запрос входит в `adapters/api`. Маршрут проверяет идентификаторы и отображает ошибки, затем вызывает сервис приложения.

## Хранилище

Один бэкенд на процесс. Задан `FAS_S3_BUCKET` — процесс пишет в S3. Иначе он пишет в каталог `FAS_DATA_DIR`. Перехода с одного на другой нет. `fas storage sync` копирует между двумя URL.

Файлы книги — неизменяемый Parquet в `books/{job_id}/{build_key}/`. Производные таблицы одной позиции журнала лежат в `derived/{derive_key}/`. Голова книги указывает текущие `build_key`, `state_seq` и `derive_key`.

## Redis и воркеры

Redis обязателен. В нём блокировки, журнал операций, ключи идемпотентности и очереди Taskiq. Процесс API эти очереди не исполняет.

Эти пять процессов — дети `fas-api` в контейнере `finance-analysis`:

| Процесс | Команда |
| --- | --- |
| interactive | `fas-worker --queue fas:interactive` |
| glossary | `fas-worker --queue fas:glossary` |
| batch | `fas-worker --queue fas:batch` |
| maintenance | `fas-worker --queue fas:maintenance` |
| scheduler | `fas-scheduler` |

Код регистрирует расписание на двух из этих очередей. `fas:batch` считает кластеры непривязанных строк, разбор глоссария и перекалибровку. `fas:maintenance` уплотняет примеры, убирает недописанные сборки и сверяет операции. Полезная нагрузка `fas.run` называет свою очередь или попадает в `fas:interactive`. Анализ, который отвечает `202`, включая `full`, остаётся в процессе API. См. [анализы](analyses.md).

## Движок запросов

Wren — внутрипроцессный DuckDB поверх Parquet книги. В Compose отдельного сервиса Wren нет. Series, slice и expression идут через него. DuckDB возвращает суммы. Коэффициенты после этого считает Python `Decimal`.

Серверы моделей — необязательные HTTP-зависимости (`EMBED_BASE_URL`, `RERANK_BASE_URL`, `CLM_BASE_URL`, `LLM_BASE_URL`). Если все четыре пустые, привязка остаётся лексической.

Схема слоёв, раскладка на диске и классы очередей — в [design-v0.23.md](../design-v0.23.md) §8, §9 и §10.
