# Три графа метаслоя и трассировка

Фаза 4 дорожной карты метаслоя ([meta-layer-roadmap.md](meta-layer-roadmap.md)). Целевая модель — [meta-layer.md](meta-layer.md) (G2). Каталог показателей — [financial-model-catalog.md](financial-model-catalog.md). Провенанс факта — [financial-fact-provenance.md](financial-fact-provenance.md).

Код: `finance_analysis.domain.graphs`. Схема контракта рёбер: `src/finance_analysis/domain/contracts/meta_layer_graphs.json`. Чтение: `GET /v1/books/{job_id}/metrics/{metric_id}/trace`.

## 1. Три графа — разные жизненные циклы

| Граф | Узлы | Рёбра | Где живёт | Меняется с |
|---|---|---|---|---|
| **Физический Excel** | ячейки (`cell_id`) | формула → ссылка | `graph_links` (+ `dim_row.formula`) | `build_key` |
| **Семантический** | понятия, строки (`binding_key` / `row_key`) | привязка строки↔понятие; таксономия (`composed_of`, …) | `bindings`, `configs/concepts` | `derive_key` / релизы глоссария |
| **Формульный метрик** | показатель (`metric_id`), входы-понятия | показатель → concept (`all_of` / `one_of`) | Financial Model Catalog / `configs/metrics` | версия каталога в SMV |

Три графа **связываются идентификаторами узлов**, а не копированием рёбер друг в друга.

```text
metric ──(metric:in)──► concept ──(sem:bind)──► binding_key / row_key ──► cell_id
                                                              │
                                                   excel:link ┘  (graph_links, опц.)
```

Таксономия (`sem:rel:…`) — **отдельный** справочный механизм поверх `configs/concepts`; в ответ `MetricTrace` **не** входит (см. §5).

## 2. Запрет схлопывания

1. **Не** создавать одну Parquet/SQL-таблицу рёбер с общей семантикой (`edge_type` + `src` + `dst`), куда складываются Excel-ссылки, привязки и входы метрик.  
2. `graph_links` остаётся **только** физическим графом формул Excel.  
3. Семантические и формульные рёбра не материализуются как строки `graph_links` и не пишутся «третьим графом YAML» в Parquet «на всякий случай».  
4. Трассировка — **read-only view** (join по ключам), без графовой БД и без миграции схем §4.4 ради слияния графов.

Нарушение этого правила ломает потребителей: физический граф версионируется сборкой книги, семантический — свёрткой/глоссарием, формульный — релизом каталога метрик.

## 3. Типы узлов и рёбер

### 3.1 Физический Excel

| | Идентификатор |
|---|---|
| Узел | `cell_id` (как в `fact_observation.cell_id` / `graph_links.cell`) |
| Ребро | `excel:link:{digest16}` — digest = `sha1(model_id \| build_key \| cell \| ref_cell)[:16]` |

Поля источника ребра: строка `graph_links` (`cell`, `ref_cell`, `formula_class`, `truncated`, …). Стабильность — при тех же `model_id`/`build_key`/`cell`/`ref_cell`.

### 3.2 Семантический

| | Идентификатор |
|---|---|
| Узел-строка | `binding_key` (стабилен через пересборки); материализация — `row_key` |
| Узел-понятие | `concept` / `effective_concept` |
| Ребро привязки | `sem:bind:{digest16}` — digest = `sha1(model_id \| build_key \| binding_key)[:16]` |
| Ребро таксономии | `sem:rel:{type}:{source}->{target}` (`composed_of`, `broader_than`, `related_to`) |

Таксономические рёбра **не считают** и не подставляются во входы метрик (design §5.1). Формат id зарезервирован; **в `MetricTrace` они не сериализуются** — читать таксономию нужно отдельно (каталог понятий / glossary package).

### 3.3 Формульный метрик

| | Идентификатор |
|---|---|
| Узел-показатель | `metric_id` или `metric_id.variant` |
| Узел-вход | `concept` |
| Ребро входа | `metric:in:{metric_or_variant}:{role}:{concept}` где `role` ∈ `all_of` \| `one_of` |

Источник — запись каталога показателей (`inputs`), не `composed_of`.

## 4. Как `graph_links` соотносится с другими рёбрами

| Вопрос | Ответ |
|---|---|
| Является ли строка `graph_links` семантическим ребром? | **Нет.** Только Excel `cell → ref_cell`. |
| Является ли она ребром метрики? | **Нет.** Входы метрики — понятия каталога. |
| Как связать с привязкой? | `graph_links.row_key` / `cell` → `dim_row` → `binding_key` → `bindings.concept`. |
| Как связать с метрикой? | Только через понятие: metric → concept → binding → cell; опционально подтянуть `excel:link` для ячеек следа. |
| Можно ли `UNION` трёх наборов рёбер? | Только в эфемерном отчёте с **раздельными** пространствами id (`excel:` / `sem:` / `metric:`). Не как единый датасет §4.4. |

Machine-readable контракт id и ответа трассировки — JSON Schema по пути выше.

## 5. Путь трассировки (граница реализации)

`GET …/metrics/{id}/trace` и `trace_metric` строят **только** путь входа метрики:

```text
metric_id → concept → binding_key → cell_id
```

Это **не** полный семантический lineage и **не** обход `composed_of` / `broader_than` / `related_to`.

Алгоритм:

1. Взять показатель (и опционально `variant`) из Financial Model Catalog.  
2. Для каждого concept из `inputs.all_of ∪ inputs.one_of` построить шаг:  
   - ребро `metric:in:…`;  
   - найти **основную** не-`stale` привязку (`is_primary`, статус `bound` / `bound_with_warning`); при нескольких — детерминированно минимальный `binding_key` + finding `ambiguous_primary_binding`;  
   - по `row_key` собрать все `cell_id` из `fact_observation` этой сборки;  
   - при наличии `graph_links` — перечислить `excel:link` инцидентные ячейкам.  
3. Если основной свежей привязки нет → `missing_trace = no_primary_binding` (или `stale_binding`, если есть только stale).  
4. Если основная привязка есть, а ячеек нет → `missing_trace = no_cell`.  
5. Тихий обрыв пути **запрещён**: либо есть `cell_ids`, либо явный `missing_trace`.

### Коды `missing_trace`

| Код | Смысл |
|---|---|
| `metric_unknown` | показателя нет в каталоге |
| `no_primary_binding` | нет основной bound-привязки для понятия |
| `stale_binding` | есть только устаревшая (`stale`) основная привязка |
| `no_cell` | датасет фактов **есть**, основная привязка есть, но нет ячеек по строке |
| `fact_dataset_unavailable` | нет `fact_observation` в сборке (доменная метка; HTTP — см. ниже) |
| `dim_row_unavailable` | нет `dim_row` в сборке (доменная метка; HTTP — см. ниже) |

**Важно:** отсутствие обязательного датасета ≠ `no_cell`. HTTP-слой при отсутствии `dim_row` / `fact_observation` отвечает `412 precondition_failed` («трассировка недоступна…»), а не подменяет ответ пустым списком фактов. Отсутствие опционального `graph_links` → `physical_lineage_complete: false` (связи формул не проверялись).

### Ответ API

Полное тело (валидируется JSON Schema перед возвратом): `metric_id`, `variant`, `build_key`, `model_id`, `catalog_version`, `missing_trace`, `steps[]`, `integrity[]`, `physical_lineage_complete`.

`integrity[]` — findings по исходным данным и инварианту DTO (`ambiguous_primary_binding`, `primary_binding_without_trace_or_reason`, …).

## 6. Проверка целостности

`check_metric_physical_trace` / `validate_metric_traces`:

- Для каждого входа с основной привязкой: непустой `cell_ids` **либо** явный `missing_trace`.  
- Несколько primary на одно понятие → finding `ambiguous_primary_binding` (выбор детерминирован).  
- Инвариант DTO отдельно тестируется на «сломанном» объекте; сценарии исходных данных — на недоступных датасетах, stale, ambiguous, нескольких периодах.

## 7. Пример на одной книге (golden)

Минимальная книга (как в тестах фазы 1/4): метрика `icr`, понятие `ebitda`, основная привязка, одна ячейка.

| Шаг | Значение |
|---|---|
| `metric_id` | `icr` |
| concept (вход `one_of`) | `ebitda` |
| `metric:in` | `metric:in:icr:one_of:ebitda` |
| `binding_key` | `bk_ebitda_primary` |
| `sem:bind` | `sem:bind:{digest(model,build,bk_ebitda_primary)}` |
| `row_key` | `P&L\|12\|blk1` |
| `cell_id` | `P&L!D12` |
| `missing_trace` | `null` |

Если датасет `fact_observation` **есть**, но строк по `row_key` нет — `cell_ids = []` и `missing_trace = no_cell`. Если датасета нет в манифесте — HTTP `412`, не `no_cell`.

## 8. API (read-only)

| Метод | Ответ |
|---|---|
| `GET /v1/books/{job_id}/metrics/{metric_id}/trace` | трассировка входа показателя по текущей сборке `_head` |
| query `variant` | опциональный id варианта формулы |

Расчёт коэффициентов по-прежнему через analyses; маршрут только читает определения и проекцию книги.

## 9. Ограничения текущей реализации

1. **Полное чтение Parquet.** Сервис загружает `fact_observation` / `graph_links` через `_dataset_rows` целиком, затем в памяти оставляет строки нужных `row_key` / `cell_id`. Фильтрация на уровне reader / индекс по `row_key` — отдельная задача; графовая БД не вводится.  
2. **Таксономия вне ответа.** `sem:rel` — формат id, не поле `MetricTrace`.  
3. Нет полного lineage UI и нет записи третьего графа в Parquet.

## 10. Не-цели фазы 4

Замена networkx-эвристик привязки; полный lineage UI; запись третьего графа как дампа YAML в Parquet; Iceberg/Hive; графовая СУБД; схлопывание трёх графов в один store.
