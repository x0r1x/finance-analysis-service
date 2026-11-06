# Контракт `FinancialFactProvenance`

Фаза 1 дорожной карты метаслоя ([meta-layer-roadmap.md](meta-layer-roadmap.md)). Целевая модель — [meta-layer.md](meta-layer.md) (G3). Нормативные схемы датасетов — [design-v0.23.md](design-v0.23.md) §4.4 и `src/finance_analysis/adapters/storage/schemas/*.json`.

Логическая запись **не** является новым Parquet-датасетом и **не** копирует `value*` / `concept` в широкую таблицу фактов. Это стабильный контракт сборки (view) поверх существующих датасетов §4.4.

Код: `finance_analysis.domain.provenance.assemble_financial_fact_provenance`.

## 1. Правило join

```text
fact_observation
  ⨝ dim_row      ON (model_id, build_key, row_key)
  ⨝ bindings     ON (model_id, build_key, binding_key)
                    — binding_key берётся из dim_row;
                      при нескольких строках bindings с тем же ключом
                      предпочитается is_primary = true, иначе первая
  ⨝ dim_period   ON (model_id, build_key, axis_id, period_id)
  ⟕ row_semantics ON (model_id, build_key, binding_key)
                    — опционально; при нескольких — первая с тем же derive_key
```

Ключи join уже есть в схемах; **новые nullable колонки-ссылки не требуются**. Предпочтение — документировать join, а не расширять схемы (MINOR только если join иначе нестабилен — в фазе 1 не применяется).

Точка входа сборки — одна строка `fact_observation` (ячейка). Остальные датасеты — справочники по ключам выше.

## 2. Поля контракта и источники

| Поле контракта | Датасет §4.4 | Колонка-источник | Обязательно |
|---|---|---|---|
| `model_id` | `fact_observation` | `model_id` | да |
| `build_key` | `fact_observation` | `build_key` | да |
| `row_key` | `fact_observation` | `row_key` | да |
| `binding_key` | `dim_row` | `binding_key` | да |
| `cell_id` | `fact_observation` | `cell_id` | да |
| `axis_id` | `fact_observation` | `axis_id` | да |
| `axis_kind` | `fact_observation` | `axis_kind` | да |
| `period_id` | `fact_observation` | `period_id` | да |
| `value_raw` | `fact_observation` | `value_raw` | нет |
| `value` | `fact_observation` | `value` | нет |
| `value_dec` | `fact_observation` | `value_dec` | нет |
| `normalized_value` | `fact_observation` | `normalized_value` | нет |
| `value_status` | `fact_observation` | `value_status` | да |
| `sheet` | `dim_row` | `sheet` | да |
| `label` | `dim_row` | `label` | нет |
| `unit` | `dim_row` | `unit` | нет |
| `currency` | `dim_row` | `currency` | нет |
| `scale` | `dim_row` | `scale` | нет |
| `concept` | `bindings` | `concept` | нет (`NULL` при unknown) |
| `effective_concept` | `bindings` | `effective_concept` | нет |
| `binding_status` | `bindings` | `status` | да |
| `binding_source` | `bindings` | `source` | нет |
| `binding_confidence` | `bindings` | `confidence` | нет |
| `matched_label_id` | `bindings` | `matched_label_id` | нет |
| `is_primary` | `bindings` | `is_primary` | да |
| `glossary_version` | `bindings` | `glossary_version` | нет |
| `taxonomy_version` | `bindings` | `taxonomy_version` | нет |
| `decided_by` | `bindings` | `decided_by` | нет |
| `binding_stale` | `bindings` | `stale` | да |
| `state_seq` | `bindings` | `state_seq` | да |
| `derive_key` | `bindings` | `derive_key` | да |
| `period_index` | `dim_period` | `period_index` | да |
| `period_key_base` | `dim_period` | `period_key_base` | нет |
| `grain` | `dim_period` | `grain` | нет |
| `header_text` | `dim_period` | `header_text` | нет |
| `calendar_year` | `dim_period` | `calendar_year` | нет |
| `timeline_id` | `dim_period` | `timeline_id` | нет |
| `sign` | `row_semantics` | `sign` | нет (опц. join) |
| `nature` | `row_semantics` | `nature` | нет (опц. join) |
| `aggregation` | `row_semantics` | `aggregation` | нет (опц. join) |
| `excluded` | `row_semantics` | `excluded` | нет (опц. join) |
| `semantic_model_version` | *(вне §4.4)* | stub до фазы 2 | нет |

`semantic_model_version` — заглушка публичного `SemanticModelVersion` (фаза 2). Пока передаётся снаружи сборки или остаётся `null`; **не** подменяет `derive_key`.

## 3. Запрет дубля факта

1. Не создавать датасет, который хранит копии `value` / `value_dec` / `normalized_value` / `concept` «на всякий случай».  
2. Сборка — чистая функция над уже записанными строками §4.4; запись новой широкой таблицы чисел — вне рамок.  
3. Iceberg / Hive writers — вне рамок (см. дорожную карту).  
4. Поля из `bindings` и `fact_observation` читаются по join; контракт не меняет конвейер привязки.

## 4. Минимальный полный провенанс

Для приёмки фазы 1 собранная запись должна содержать:

- понятие (`concept` / `effective_concept`);  
- период (`axis_id`, `period_id`, плюс поля `dim_period` выше);  
- ячейку (`cell_id`) и статус/значение из `fact_observation`;  
- источник и версии привязки (`binding_source`, `glossary_version`, `taxonomy_version`);  
- `build_key`;  
- `derive_key`;  
- `semantic_model_version` (stub, может быть `null`).

## 5. Не-цели этого документа

UI; новый датасет значений; изменение схем Parquet; `SemanticModelVersion` как вычисляемый манифест (фаза 2); Iceberg/Hive.
