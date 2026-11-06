# `SemanticModelVersion`

Фаза 2 дорожной карты метаслоя ([meta-layer-roadmap.md](meta-layer-roadmap.md)). Целевая модель — [meta-layer.md](meta-layer.md) (G4).

Публичный агрегат **`SemanticModelVersion`** (SMV) — один id согласованного набора семантических определений. Он стоит **рядом** с `derive_key`, не заменяет его и не входит в формулу `derive_key`.

Код: `finance_analysis.domain.semantic_model`. Манифест в object store: `semantic_models/{version}.json`, указатель `semantic_models/_head.json`.

## 1. Состав агрегата

| Компонент | Вход манифеста | Источник |
|---|---|---|
| taxonomy | `taxonomy.id` + `taxonomy.stamp` | `configs/concepts/` (`taxonomy` из `core.yaml` + отпечаток файлов) |
| glossary | `glossary` | релиз `glossary_version` (`g-…` / `none`) |
| metrics | `metrics` | отпечаток `configs/metrics/` |
| model_types | `model_types` | `ModelTypeCatalog.version` (уже sha канонического JSON) |
| units / dimensions | `dimensions.id` + `dimensions.stamp` | `configs/dimensions.yaml` |
| rules | `rules` | sha канонического `{code → version}` реестра аудита |
| schema | `schema` | `fas_schema_version` (`FAS_SCHEMA_VERSION`) |

```text
components = canonical{
  taxonomy: {id, stamp},
  glossary,
  metrics,
  model_types,
  dimensions: {id, stamp},
  rules,
  schema
}
SemanticModelVersion = sha256(canonical_json(components))[:16]
```

Одинаковые входы → одинаковый id. Отпечатки файлов нормализуют перевод строк к LF (как `derive_fingerprint`).

## 2. Отличие от `derive_key`

| | `SemanticModelVersion` | `derive_key` |
|---|---|---|
| Слой | Versioned Metadata Contract (публичный) | Bindings / Analytical (внутренний) |
| Вопрос | какая **семантика определений** действовала | какая **папка свёртки** книги |
| Входы | каталоги + релиз глоссария + схема | `state_seq`, глоссарий, таксономия, калибратор, embed/rerank/clm, профиль, `fas_derive_version`, model_types, `model_type_seq`, sheet_roles |
| Путь | `semantic_models/{version}.json` | `derived/{derive_key}/` |
| API | рядом с `derive_key` в книге / `versions` / `run` | без переименования и удаления |

SMV **не** включает журнал решений, модели эмбеддинга, профиль книги, калибратор и отпечаток кода свёртки — это зона `derive_key`.

## 3. Правила bump

Новый id появляется, когда меняется **любой** компонент §1:

- релиз / активация / откат глоссария → новый `glossary`;  
- правка `configs/concepts/`, `configs/metrics/`, `configs/model_types/`, `configs/dimensions.yaml` → новый stamp / `model_types`;  
- смена версий правил аудита (`Rule.version`) → новый `rules`;  
- MINOR/MAJOR `fas_schema_version` → новый `schema`.

Не бампают SMV сами по себе: запись в журнал книги, смена профиля, калибратора, embed-моделей, `sheet_roles_version`, `fas_derive_version`, `state_seq` — они бампают `derive_key`.

Запись манифеста: `put_if_absent` на `semantic_models/{version}.json`; указатель `_head.json` обновляется на активный id при публикации (релиз глоссария и смена пакетных входов при материализации книги).

## 4. Контракт манифеста и поля

**Манифест** `semantic_models/{version}.json`:

```json
{
  "version": "<16 hex>",
  "components": { "...": "§1" },
  "fas_version": "0.23.0",
  "created_at_utc": "…"
}
```

**Указатель** `semantic_models/_head.json`: `{ "active": "<version>", "updated_at_utc": "…" }`.

**Поля:**

| Место | Поле |
|---|---|
| `_head.json` книги | `versions.semantic_model` |
| ответ с данными книги | `semantic_model_version` рядом с `derive_key`; также в `versions.semantic_model` |
| `AnalysisResult.versions` | `semantic_model` рядом с `derive_key` |
| `run.parquet` | колонка `semantic_model_version` (схема `run@1.1`) |
| `FinancialFactProvenance` | `semantic_model_version` (больше не stub) |

`derive_key` не удаляется и не переименовывается.

## 5. Матрица: SMV vs только `derive_key`

| Артефакт | SMV | `derive_key` |
|---|---|---|
| Таксономия понятий (`configs/concepts/`) | да | да (через `taxonomy_version` + часть `fas_derive_version`) |
| Релиз глоссария | да | да (`glossary_version`) |
| Метрики (`configs/metrics/`) | да | нет (пока git-отпечаток в SMV; фаза 3 усилит каталог) |
| Типы моделей (`configs/model_types/`) | да | да (`model_types_version`) |
| Единицы / размерности (`dimensions.yaml`) | да | нет (косвенно через код/конфиг свёртки) |
| Правила аудита (`Rule.code`/`version`) | да | нет |
| `fas_schema_version` / схемы датасетов | да | нет |
| Журнал решений / `state_seq` | нет | да |
| Профиль книги | нет | да |
| Калибратор | нет | да |
| Embed / rerank / CLM | нет | да |
| `fas_derive_version` (PACKAGE/CONFIG свёртки) | нет | да |
| `sheet_roles_version` | нет | да |
| `model_type_seq` (журнал типа модели) | нет | да |

## 6. Не-цели фазы 2

OSI/Ossie export; слияние SMV и `derive_key` в один хеш; перенос метрик в object store (достаточно git-отпечатка в составе SMV); Iceberg/Hive.
