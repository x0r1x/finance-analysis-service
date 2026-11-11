# Обзор

[English](../en/overview.md)

FAS — аналитический сервис поверх уже разобранной cash-flow книги. [finance-context-builder](https://github.com/x0r1x/finance-context-builder) владеет книгой: раскладка, кэш значений, формулы и граф формул. FAS владеет понятиями, привязкой строк, фазами периодов, знаками, единицами, правилами аудита, коэффициентами покрытия и отчётами.

## Вход и выход

`POST /v1/books/{job_id}:load` читает этот `job_id` из HTTP API билдера (`BUILDER_BASE_URL`). Проекция лежит в Parquet по пути `books/{job_id}/{build_key}/`. Решения человека — в нумерованном журнале.

Дальше чтение отдаёт голову книги, привязку, находки последнего аудита и отчёт из сохранённого результата. Повторный `GET` того же отчёта ничего не пересчитывает.

## Чего FAS не делает

FAS не парсит Excel, не пересчитывает формулы и сам модель не вызывает. `GET /v1/capabilities` — карточка для клиента. Клиент может отдать `tools[]` своей LLM. Этот вызов делает не FAS.

`capabilities.phase` — поставленная фаза. Код возвращает `"4"`. Форматы отчёта — `json` и `md`.

## Спека

То, что эта страница не расписывает, лежит в [design-v0.23.md](../design-v0.23.md), §0 и §1. Если спека и код расходятся, сервис делает то, что в коде.

Целевая модель метаслоя и фазы поставки — [meta-layer.md](../meta-layer.md), [meta-layer-roadmap.md](../meta-layer-roadmap.md). Контракт провенанса финансового факта (фаза 1) — [financial-fact-provenance.md](../financial-fact-provenance.md). Публичный `SemanticModelVersion` (фаза 2) — [semantic-model-version.md](../semantic-model-version.md). Financial Model Catalog (фаза 3) — [financial-model-catalog.md](../financial-model-catalog.md). Три графа и трассировка (фаза 4) — [meta-layer-graphs.md](../meta-layer-graphs.md). Published Parquet / DataMesh (фаза 5) — [published-parquet-contract.md](../published-parquet-contract.md). Единицы и размерности — [dimensions.md](../dimensions.md).
