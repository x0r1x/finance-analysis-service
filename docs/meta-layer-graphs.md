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
                              │                                              │
                              └── sem:rel (taxonomy)              excel:link ┘
                                                                   (graph_links)
```

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

Таксономические рёбра **не считают** и не подставляются во входы метрик (design §5.1). В трассировке метрики они справочны.

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

## 5. Путь трассировки

```text
metric_id → concept → binding_key → cell_id
```

Алгоритм (чистая функция `trace_metric` / HTTP ниже):

1. Взять показатель (и опционально `variant`) из Financial Model Catalog.  
2. Для каждого concept из `inputs.all_of ∪ inputs.one_of` построить шаг:  
   - ребро `metric:in:…`;  
   - найти **основную** привязку (`is_primary`, статус `bound` / `bound_with_warning`, `effective_concept` или `concept`);  
   - по `row_key` привязки (или join через `dim_row`) собрать `cell_id` из `fact_observation`;  
   - при наличии `graph_links` — перечислить `excel:link` инцидентные собранным ячейкам.  
3. Если основной привязки нет → `missing_trace = no_primary_binding`.  
4. Если основная привязка есть, а ячеек нет → `missing_trace = no_cell`.  
5. Тихий обрыв пути **запрещён**: либо есть `cell_ids`, либо явный `missing_trace`.

### Коды `missing_trace`

| Код | Смысл |
|---|---|
| `metric_unknown` | показателя нет в каталоге |
| `no_primary_binding` | нет основной bound-привязки для понятия |
| `no_cell` | основная привязка есть, но нет `fact_observation` по строке |

## 6. Проверка целостности

`check_metric_physical_trace` / `validate_metric_traces`:

- Для каждого входа метрики, у которого на книге есть **основная** привязка, в результате трассировки должен быть непустой `cell_ids` **либо** `missing_trace = no_cell`.  
- Нарушение — отсутствие и ячеек, и явной причины (инвариант сборщика следа).  
- Это не замена networkx-эвристик привязки и не полный lineage UI.

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

Если убрать `fact_observation` при той же привязке — тот же путь, но `cell_ids = []` и `missing_trace = no_cell`.

## 8. API (read-only)

| Метод | Ответ |
|---|---|
| `GET /v1/books/{job_id}/metrics/{metric_id}/trace` | трассировка показателя по текущей сборке `_head` |
| query `variant` | опциональный id варианта формулы |

Тело — объект контракта `MetricTrace` (см. JSON Schema): `metric_id`, `variant`, `build_key`, `steps[]` с полями concept / edge ids / binding / cells / `missing_trace` / опциональные `excel_links`.

Расчёт коэффициентов по-прежнему через analyses; маршрут только читает определения и проекцию книги.

## 9. Не-цели фазы 4

Замена networkx-эвристик привязки; полный lineage UI; запись третьего графа как дампа YAML в Parquet; Iceberg/Hive; графовая СУБД; схлопывание трёх графов в один store.
