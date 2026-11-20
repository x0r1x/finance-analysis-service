# Financial Model Catalog

Фаза 3 дорожной карты метаслоя ([meta-layer-roadmap.md](meta-layer-roadmap.md)). Целевая модель — [meta-layer.md](meta-layer.md) (G1). Версия каталога входит в публичный [`SemanticModelVersion`](semantic-model-version.md).

Каталог делает **показатель** (indicator / metric) явной сущностью: не только YAML для кода расчёта, а запись с идентификатором, определением, структурой формулы, входами-понятиями, единицами, окном, вариантами по `model_types` и статусом.

Код: `finance_analysis.domain.financial_catalog`, загрузка `finance_analysis.application.financial_catalog`. Схема: `src/finance_analysis/domain/contracts/financial_model_catalog.json`. Чтение API: `GET /v1/metrics`, `GET /v1/metrics/{id}`.

## 1. Модель показателя

| Поле | Смысл | Обязательно |
|---|---|---|
| `id` | Публичный metric id (`dscr`, `icr`, …) | да |
| `definition` | Текстовое определение (из YAML или `null`) | нет |
| `inputs` | `{all_of, one_of}` — concept_id таксономии | да |
| `input_concepts` | Плоский список concept_id для поиска (`all_of ∪ one_of`) | да |
| `formula` | Декларативная структура формулы (числитель/знаменатель/ставка/base) | да |
| `unit` | Размерность **результата** (`ratio`, `money`, …) | да |
| `window` | `LTM` \| `period` \| `null` | нет |
| `variants` | Карта вариантов формулы (`pf`, `corporate_covenant`, `ocf_covenant`, …). Тип `corporate` сам выбирает только `corporate_covenant`. | да (может быть `{}`) |
| `model_types` | Применимость по типу: `{use, variant?}` | да |
| `status` | `active` \| `deprecated` | да (по умолчанию `active`) |
| `base` | Ссылка на базовый metric id, если формула наследует | нет |

Вариант повторяет: `id`, `definition`, `inputs`, `input_concepts`, `formula`, `unit`, `window`.

### `inputs`

```json
{ "all_of": ["cfads", "debt_service"], "one_of": ["ebitda", "ebit"] }
```

- `all_of` — все понятия необходимы;  
- `one_of` — достаточно одного из перечисленных;  
- `input_concepts` — удобный плоский список, **не** заменяет семантику `all_of`/`one_of`.

`row_fallbacks` не входят во входы формулы и не являются concept_id. `interest_paid` — понятие таксономии и кандидат `interest_order` для pf, ICR и `corporate_covenant`.

### `formula`

Декларативное описание экономического смысла, не исполняемый код:

```json
{
  "numerator": { "plus": ["ebitda"], "minus": ["cash_taxes", "capex"] },
  "denominator": { "plus": ["interest", "principal"], "minus": [] },
  "one_of": [],
  "rate": null,
  "base": null
}
```

| Поле | Смысл |
|---|---|
| `numerator.plus` / `minus` | Слагаемые числителя |
| `denominator.plus` / `minus` | Слагаемые знаменателя |
| `one_of` | Альтернативные числители (как у ICR: `ebitda` \| `ebit`) |
| `rate` | Ставка дисконтирования: одна строка или список приоритета (`[wacc, discount_rate]` у NPV; `discount_rate` у LLCR/PLCR) |
| `terminal` | Необязательная терминальная стоимость, одно понятие (`terminal_value` у NPV и IRR) |
| `compare_with` | Строка книги, с которой сверяется показатель (`project_fcf` у `fcf_identity`) |
| `add_back` | Добавка `{concept, tax_complement}`: чистые проценты × (1 − ставка). Только у названного варианта |
| `base` | Полное наследование формулы другого показателя (`adscr` → `dscr`) |

`base` — **самостоятельный** режим: рядом с ним нельзя указывать `numerator`, `denominator`, `rate`, `terminal`, `add_back` или `compare_with` (иначе ошибка загрузки). Объект `plus`/`minus` должен содержать хотя бы одно слагаемое суммарно — пустые `{}` / `{plus: []}` / `{minus: []}` отклоняются.

Пустые стороны и отсутствующие поля опускаются в JSON; `base`-only запись содержит только `{"base": "dscr"}`.

### `model_types`

Сохраняет связь тип модели → применимость **и** выбранный вариант формулы из `configs/model_types/*.yaml`:

```json
{
  "corporate": { "use": "optional", "variant": "corporate_covenant" },
  "project_finance": { "use": "required", "variant": "pf" },
  "investment_project": { "use": "not_applicable" }
}
```

`variant` присутствует только если он задан у типа для этого показателя.

### Источники

| Поле | Откуда |
|---|---|
| формула / входы / окно / base / rate | `configs/metrics/coverage.yaml` → `metrics` |
| `definition`, `status` | те же записи YAML (опциональные ключи; неверный тип → ошибка загрузки) |
| размерности входов | таксономия `configs/concepts/` + `configs/dimensions.yaml` |
| `unit` результата | вывод из формулы (частное → `ratio`; NPV-подобные → размерность числителя) |
| `model_types` + `variant` | `configs/model_types/*.yaml` → явные `metrics` (+ снимок `matrix.json`); `default_use` / `"*"` — только запас |
| `row_fallbacks` | тот же YAML; не входы формул и не concept_id. Список может быть пустым |

Связи таксономии (`composed_of` и др.) **не** считают и **не** подставляют формулу показателя.

## 2. Контракт каталога

Корень ответа / снимка:

```json
{
  "version": "<16 hex>",
  "stamp": "<отпечаток configs/metrics>",
  "indicators": { "<id>": { "...": "§1" } },
  "row_fallbacks": []
}
```

Инвариант: `version == sha256(canonical_json(indicators))[:16]`. Machine-readable схема — JSON Schema Draft 2020-12 по пути выше.

`build_financial_catalog` / `load_financial_catalog` **в production-пути** вызывают `validate_financial_catalog_integrity`: JSON Schema Draft 2020-12 по `as_dict()` плюс ссылочные инварианты (`id` = ключ, `input_concepts` = `all_of ∪ one_of`, `model_types.*.variant` ∈ `variants`, `base`/`formula.base` ∈ каталог). Ошибка блокирует старт сервиса и `fas check-config`, а не отдаётся клиенту как «почти корректный» ответ.

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
2. `row_fallbacks` нельзя указать как вход формулы. Имена `interest_order` — понятие `interest`, понятие `interest_paid` или row_fallback с canonical `interest`.  
3. Единицы слагаемых совместимы; частное безразмерно (кроме явных rate-метрик).  
4. Нет циклов `base`; ключи coverage/fallback известны.  
5. Некорректные типы `definition` / `status` / `window` в YAML — явная ошибка загрузки, без тихого default.  
6. `numerator` / `denominator` — только строка, список строк или непустой `plus`/`minus`; `base` — непустая строка; `rate` — непустая строка или список приоритета без повторов; `terminal` и `compare_with` — непустые строки; `add_back` — ровно `concept` и `tax_complement`. Вложенные `variants` запрещены; `base` без остальных полей формулы.  
7. Публичный снимок проходит JSON Schema, `version == hash(indicators)` и межполевые инварианты до публикации.

Тихий drift «concept vs metric input» и «формально валидная, но урезанная формула» запрещены: сервис с расхождением не стартует.

## 5. API чтения (опционально в фазе 3)

| Метод | Ответ |
|---|---|
| `GET /v1/metrics` | снимок каталога (`version`, `stamp`, `indicators`, `row_fallbacks`) |
| `GET /v1/metrics/{id}` | одна запись + `catalog_version` |

Маршруты только читают определения; расчёт коэффициентов по-прежнему через analyses.

## 6. Не-цели фазы 3

Переписывание всех правил аудита; автовывод формул из `composed_of`; отдельный сервис метрик; Iceberg/Hive; слияние трёх графов (фаза 4).
