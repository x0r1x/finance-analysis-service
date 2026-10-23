# Фикстуры builder

Две реальные книги finance-context-builder (схема context `1.14.0`, граф `1.7.0`).
Каталог назван `job_id`. В тестах книга выбирается по алиасу (`tests/books.py`).

| Алиас | job_id | Файл-источник | Статус |
| --- | --- | --- | --- |
| `packt` | `2eca70a9acd0c7b1812adcb2e1a4aacc84092f52726d001a93b9564950e5dd5e` | `packt-project-finance.xlsx` | `succeeded`, предупреждений нет |
| `rvi` | `2f180b3eec3b8557908beafa659af75dd7c2e93dab02b176f3cab1d625ee7bac` | `rvi-project-finance.xlsx` | `succeeded`, есть предупреждение |

`packt` — модель проектного финансирования. Листы: Input Assumptions, TBA, Construction, Operation, Amortization, Debt, P&L, CFS, Balance Sheet, Ratios. 9 осей таймлайна по 40 периодов `Y1`…, 10 блоков (9 timeline и 1 params), 131 строка (97 fact). Граф: 2973 ссылки. `warnings` пуст, `missing_cached_values` = 0.

`rvi` — модель на одном листе `PF Model`. 1 ось, 5 блоков, 459 строк. Сборка `succeeded`. В `warnings` одна строка про формулы без кэша, `missing_cached_values` = 20.

Общие файлы каждой книги:

- `meta.json`, `owner.json` — лежат в дампе, адаптер FAS их не читает
- `context.json`, `context.md`, `context.md.renderer`
- `graph.json`, `graph.md`
- `summary.json` — тело `GET /summary`
- `ir/graph_index.parquet`, `ir/graph_edges.parquet`

`graph.json` в `artifacts` называет ещё `ir/cells.parquet`, `ir/edges.parquet` и `ir/cell_edges.parquet`. В этом дампе их нет.

`summary.json` собран скриптом `build_summary.py` из `context.json`, `graph.json` и `meta.json` этой же фикстуры. Скрипт повторяет форму `SummaryDocument` (`summary-2`): `schema_version`, `warnings` из `context.warnings`, `missing_cached_values` и `iterate` из `workbook`, циклы как `{id, class, members}` с числом членов, подсказки как `{sheet, row, label}` без `cell_ids`. Четыре поля источника (`source_filename`, `content_sha256`, `status`, `stage`) берутся из `meta.json`, если файл есть, иначе из `context.meta`. Код builder скрипт не импортирует. Адаптер FAS по-прежнему не читает `meta.json`.

Фикстура отдаёт этот файл как HTTP `/summary` формы `summary-2`: strong ETag считается по байтам `context.json` и `graph.json`, `304` и `HEAD` без тела, пересборка — `409 report_not_ready`.

## Локальные книги, которые не коммитятся

Крупные выгрузки кладутся вне git, например в `tests/fixtures/local-builder/` (каталог в `.gitignore`). Тест их подхватывает только если заданы обе переменные:

```
FAS_LOCAL_BUILDER_JOBS_DIR=/absolute/path/to/jobs
FAS_LOCAL_BUILDER_JOBS=<job_id>[,<job_id>...]
pytest tests/contract/test_local_builder_jobs.py
```

`FAS_LOCAL_BUILDER_JOBS_DIR` — каталог, внутри которого лежат папки `{job_id}/` в том же виде, что и книги выше. Без переменных тест пропускается.
