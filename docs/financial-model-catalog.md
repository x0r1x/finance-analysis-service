# Financial Model Catalog

Фаза 3 дорожной карты метаслоя ([meta-layer-roadmap.md](meta-layer-roadmap.md)). Целевая модель — [meta-layer.md](meta-layer.md) (G1). Версия каталога входит в публичный [`SemanticModelVersion`](semantic-model-version.md).

Каталог делает **показатель** (indicator / metric) явной сущностью: не только YAML для кода расчёта, а запись с идентификатором, определением, входами-понятиями, единицами, окном, вариантами по `model_types` и статусом.

Код: `finance_analysis.domain.financial_catalog`, загрузка `finance_analysis.application.financial_catalog`. Схема: `src/finance_analysis/domain/contracts/financial_model_catalog.json`. Чтение API: `GET /v1/metrics`, `GET /v1/metrics/{id}`.

## 1. Модель показателя

| Поле | Смысл | Обязательно |
|---|---|---|
| `id` | Публичный metric id (`dscr`, `icr`, …) | да |
| `definition` | Текстовое определение (из YAML или `null`) | нет |
| `inputs` | Входы-понятия (`concept_id` таксономии) | да |
| `unit` | Размерность **результата** (`ratio`, `money`, …) | да |
| `window` | `LTM` \| `period` \| `null` | нет |
| `variants` | Карта вариантов формулы (`pf`, `corporate_covenant`, …) | да (может быть `{}`) |
| `model_types` | Применимость по типу: `required` / `optional` / `not_applicable` | да |
| `status` | `active` \| `deprecated` | да (по умолчанию `active`) |
| `base` | Ссылка на базовый metric id, если формула наследует | нет |

Вариант повторяет подмножество полей: `id`, `definition`, `inputs`, `unit`, `window`.

### Источники

| Поле | Откуда |
|---|---|
| формула / входы / окно / base / rate | `configs/metrics/coverage.yaml` → `metrics` |
| `definition`, `status` | те же записи YAML (опциональные ключи) |
| размерности входов | таксономия `configs/concepts/` + `configs/dimensions.yaml` |
| `unit` результата | вывод из формулы (частное → `ratio`; NPV-подобные → размерность числителя) |
| `model_types` | `configs/model_types/*.yaml` → `metrics` / `default_use` |
| `row_fallbacks` | тот же YAML; **не** входы формул и **не** concept_id (решение 40) |

Связи таксономии (`composed_of` и др.) **не** считают и **не** подставляют формулу показателя.

## 2. Контракт каталога

Корень ответа / снимка:

```json
{
  "version": "<16 hex>",
  "stamp": "<отпечаток configs/metrics>",
  "indicators": { "<id>": { "...": "§1" } },
  "row_fallbacks": ["interest_paid"]
}
```

Инвариант: `version == sha256(canonical_json(indicators))[:16]`. Machine-readable схема — JSON Schema по пути выше.

## 3. Версия в `SemanticModelVersion`

Компонент `metrics` манифеста SMV (фаза 3):

```json
"metrics": { "version": "<catalog version>", "stamp": "<file stamp configs/metrics>" }
```

- `version` — отпечаток **содержимого** каталога показателей (записи Indicator).  
- `stamp` — отпечаток файлов `configs/metrics/` (как в фазе 2).  

Смена любого из них бампает публичный `SemanticModelVersion`. Старый манифест с `metrics` как строкой stamp больше не валиден для новых записей (`validate_manifest`).

## 4. Целостность и CI

`validate_catalog_integrity` / `fas check-config` / `load_model_types`:

1. Входы метрик и вариантов ⊆ понятия таксономии.  
2. `row_fallbacks` **нельзя** указать как вход формулы (только в `interest_order`).  
3. Единицы слагаемых совместимы; частное безразмерно (кроме явных rate-метрик).  
4. Нет циклов `base`; ключи coverage/fallback известны.

Тихий drift «concept vs metric input» запрещён: сервис с расхождением не стартует.

## 5. API чтения (опционально в фазе 3)

| Метод | Ответ |
|---|---|
| `GET /v1/metrics` | снимок каталога (`version`, `stamp`, `indicators`, `row_fallbacks`) |
| `GET /v1/metrics/{id}` | одна запись + `catalog_version` |

Маршруты только читают определения; расчёт коэффициентов по-прежнему через analyses.

## 6. Не-цели фазы 3

Переписывание всех правил аудита; автовывод формул из `composed_of`; отдельный сервис метрик; Iceberg/Hive; слияние трёх графов (фаза 4).
