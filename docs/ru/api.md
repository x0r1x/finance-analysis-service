# API

[English](../en/api.md)

Ниже маршруты, которые зарегистрированы в `adapters/api`. Поля тел сюда не скопированы. Они в [design-v0.23.md](../design-v0.23.md) §3, а живая карточка аргументов — `GET /v1/capabilities`.

`X-User-Id` и `X-Client-Id` называют актора. FAS их не проверяет. `POST` несёт `Idempotency-Key`. Работа, которая не уложилась в синхронный дедлайн, возвращает `202` и операцию. Дальше `GET /v1/operations/{op_id}` или, при включённом `SSE_ENABLED`, `GET /v1/operations/{op_id}/events` (`text/event-stream`).

Публичный контракт единиц/размерностей: [dimensions.md](../dimensions.md) (`configs/dimensions.yaml`; правила аудита `dimension_mismatch` / `pricing_basis_mismatch` уже действуют). Цитаты строк типа в `result_data.book_rows`: JSON Schema `src/finance_analysis/adapters/storage/schemas/book_rows.json` (`book_rows@1.0`).

## Процесс

- `GET /health/live` — процесс жив.
- `GET /health/ready` — Redis и хранилище отвечают.
- `GET /metrics` — текст Prometheus.
- `GET /v1/capabilities` — `fas_version`, `phase` (`"4"`), хранилище, правила, метрики, понятия, renderers (`json`, `md`), problems и `tools[]`.

У каждого tool есть `name`, `description`, `method`, `path`, `parameters`, `in` и `strict`. `parameters` — JSON Schema. `in` говорит, куда класть аргумент: `path`, `query` или `body`. Клиент выкидывает null, подставляет `job_id` из своей сессии в путь и раскладывает остальные аргументы по `in`. Только у `evaluate_expression` поле `strict: false`. Шестнадцать имён: `get_book`, `get_coverage`, `get_mapping`, `get_semantics`, `resolve_periods`, `get_series`, `get_slice`, `evaluate_expression`, `run_analysis`, `list_findings`, `explain_finding`, `compare`, `submit_decisions`, `get_report`, `get_operation`, `resolve_concept`.

## Книга

`{job_id}` — задача билдера.

- `POST /v1/books/{job_id}:load` — загрузить книгу из билдера.
- `GET /v1/books/{job_id}` — голова, сводка покрытия, предупреждения.
- `GET /v1/books/{job_id}/builds` и `GET /v1/books/{job_id}/builds/{build_key}` — история сборок и одна сборка.
- `GET /v1/books/{job_id}/mapping` — строки привязки. Query: `status`, `concept`, `importance`, `q`. `counts` считаются до фильтра.
- `GET /v1/books/{job_id}/semantics` — знаки, фазы и остальные семантические строки.
- `GET /v1/books/{job_id}/coverage` — покрытие понятиями.
- `GET /v1/books/{job_id}/questions` — открытые вопросы этой книги.
- `POST /v1/books/{job_id}/series` — значения по периодам. Хотя бы один из `row_keys`, `binding_keys`, `concepts` непустой.
- `POST /v1/books/{job_id}/slice` — срез куба. Единственное измерение времени — `period_start`.
- `POST /v1/books/{job_id}/expression` — выражение по привязкам строк.
- `POST /v1/books/{job_id}/periods:resolve` — периоды по фразе.
- `GET /v1/books/{job_id}/decisions` и `POST /v1/books/{job_id}/decisions` — чтение и запись журнала.
- `POST /v1/books/{job_id}/mapping:infer` — пересчитать inferred-привязку. Ответ `202`.
- `GET /v1/books/{job_id}/metrics/{metric_id}/trace` — read-only трассировка входа metric → concept → binding → cell (фаза 4). Query: `variant`. Нет `dim_row` / `fact_observation` → `412`; нет `graph_links` → `physical_lineage_complete: false`.

## Анализы

- `POST /v1/books/{job_id}/analyses` — `type` равен `audit`, `ratios`, `impact` или `full`. См. [анализы](analyses.md).
- `GET /v1/books/{job_id}/analyses` и `GET /v1/books/{job_id}/analyses/{analysis_id}` — список и один сохранённый анализ.
- `GET /v1/books/{job_id}/analyses/{analysis_id}/report?format=json|md` — отдать сохранённый результат.
- `GET /v1/books/{job_id}/findings` — находки последнего аудита. Query: `build_key`, `rule`, `severity`, `finding_kind`, `concept`, `page_size`, `page_token`.
- `GET /v1/books/{job_id}/findings/{fingerprint}` — одна находка и трасса. Query: `build_key`, `direction` (`precedents` или `dependents`), `depth`.
- `POST /v1/books/{job_id}:compare` — две сборки, два сценария или две книги.

## Операции

- `GET /v1/operations` — список. Query: `kind`, `job_id`, `status`.
- `GET /v1/operations/{op_id}` — одна операция. `wait_ms` ждёт завершения.
- `GET /v1/operations/{op_id}/events` — поток событий только на этом пути.
- `POST /v1/operations/{op_id}:cancel` — отменить операцию в `queued` или `running`.

## Глоссарий и профили

Маршруты глоссария перечислены в [глоссарии](glossary.md). Профили:

- `GET /v1/profiles`
- `GET /v1/profiles/{profile}`
- `PUT /v1/profiles/{profile}`
