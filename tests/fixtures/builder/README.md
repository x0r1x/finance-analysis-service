# Фикстуры builder

Две реальные книги finance-context-builder (схема context `1.14.0`, граф `1.7.0`).
Каталог назван `job_id`. В тестах книга выбирается по алиасу (`tests/books.py`).

| Алиас | job_id | Файл-источник | Статус |
| --- | --- | --- | --- |
| `packt` | `2eca70a9acd0c7b1812adcb2e1a4aacc84092f52726d001a93b9564950e5dd5e` | `packt-project-finance.xlsx` | `succeeded`, предупреждений нет |
| `rvi` | `2f180b3eec3b8557908beafa659af75dd7c2e93dab02b176f3cab1d625ee7bac` | `rvi-project-finance.xlsx` | `succeeded`, есть предупреждение |

`packt` — модель проектного финансирования. Листы: Input Assumptions, TBA, Construction, Operation, Amortization, Debt, P&L, CFS, Balance Sheet, Ratios. 9 осей таймлайна по 40 периодов `Y1`…, 10 блоков (9 timeline и 1 params), 131 строка (97 fact). Граф: 2973 ссылки. Предупреждения `meta.warnings` пустые.

`rvi` — модель на одном листе `PF Model`. 1 ось, 5 блоков, 459 строк. Статус сборки `succeeded`, но `meta.warnings` сообщает о 20 формулах без кэшированного значения (например `PF Model!M536`). В `context.json` то же число лежит в `workbook.missing_cached_values`.

Общие файлы каждой книги:

- `meta.json` — статус, поколение, `content_sha256`, хэши стадий
- `owner.json` — владелец сборки
- `context.json`, `context.md`, `context.md.renderer`
- `graph.json`, `graph.md`
- `ir/graph_index.parquet`, `ir/graph_edges.parquet`

`graph.json` в `artifacts` называет ещё `ir/cells.parquet`, `ir/edges.parquet` и `ir/cell_edges.parquet`. В этом дампе их нет.

Согласованное чтение смотрит на `meta.json`: `status`, `generation`, `content_sha256`, `stages`. Отдельного `summary.json` и HTTP ETag `summary-2` в дампе нет.

## Локальные книги, которые не коммитятся

Крупные выгрузки кладутся вне git, например в `tests/fixtures/local-builder/` (каталог в `.gitignore`). Тест их подхватывает только если заданы обе переменные:

```
FAS_LOCAL_BUILDER_JOBS_DIR=/absolute/path/to/jobs
FAS_LOCAL_BUILDER_JOBS=<job_id>[,<job_id>...]
pytest tests/contract/test_local_builder_jobs.py
```

`FAS_LOCAL_BUILDER_JOBS_DIR` — каталог, внутри которого лежат папки `{job_id}/` в том же виде, что и книги выше. Без переменных тест пропускается.
