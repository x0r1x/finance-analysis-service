# Анализы

[English](../en/analyses.md)

`POST /v1/books/{job_id}/analyses` принимает `type` `audit`, `ratios`, `impact` или `full`. Другое значение — `400`. Непустой `include` — `400` (`поле include не принимается`). `include: null` игнорируется.

`audit` и `ratios` ждут в пределах синхронного дедлайна (`SYNC_DEADLINE_MS` и `LOAD_SYNC_SEC` у HTTP-вызова). `ratios` и `impact` также возвращают `202`, если в книге периодов больше, чем `SYNC_MAX_PERIODS`, или если `async` равен true. `full` всегда возвращает `202`. Работа идёт в процессе API, тем же способом, что и аудит. Это не отдельная задача очереди. Если процесс убит, прогон умирает вместе с ним.

`render` — `json` или `md`. Он выбирает формат отчёта, который сохраняется вместе с результатом. Метрики `full` по умолчанию, когда ключ `metrics` не передан, — только `dscr`.

## Что делает каждый type

`audit` гоняет выбранные правила. Нет ключа `rules` — гоняются все. Пустой список `rules` не гоняет ни одного.

`ratios` требует непустой список `metrics`. Допустимые имена — массив `metrics` в `GET /v1/capabilities`.

`impact` строит трассу одной цели. `target` — это `cell_id`, `row_key` или `concept`. `direction` — `precedents` или `dependents`. Пропущенный `depth` берёт значение по умолчанию.

`full` считает коэффициенты, затем аудит, затем impact, если передан `target`.

`POST /v1/books/{job_id}:compare` — не тип анализа. Он сравнивает две сборки, два сохранённых сценария или две книги (`other.job_id`). Разницу метрик между случаями не считает.

## Отчёт и находки

`GET /v1/books/{job_id}/analyses/{analysis_id}/report?format=json|md` рисует сохранённый `result.json`. Повторное чтение того же результата побайтно совпадает. `GET` не пересчитывает и модель не вызывает.

`GET /v1/books/{job_id}/findings` читает последний аудит сборки `build_key` или текущей головы, если `build_key` не передан. `rule`, `severity` и `finding_kind` задаются через запятую (`finding_kind` ∈ `error|warning|methodology|insufficient_data|ambiguity`). `concept` оставляет находки строк, привязанных к этому понятию. `page_size` по умолчанию 50.

`GET /v1/books/{job_id}/findings/{fingerprint}` поясняет одну находку и трассирует её граф формул. `direction` по умолчанию `precedents`. Отпечаток со старой сборки требует `build_key` этой сборки, иначе поиск идёт по текущей голове и возвращает `404`.

Коды правил, формулы коэффициентов и форма находки — в [design-v0.23.md](../design-v0.23.md) §6.
