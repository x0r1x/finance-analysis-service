# Аналитическое ядро и методология: дорожная карта

Поэтапная доводка ядра из [design-v0.23.md](design-v0.23.md) §§5–6 после закрытия фаз 1–5 метаслоя ([meta-layer-roadmap.md](meta-layer-roadmap.md)). Метаслой упаковывает каталоги и контракты; эта карта — про **применимость тип×метрика**, **eval привязки** и **виды находок аудита**.

Нормативное поведение текущего кода — design §5–§6 и YAML. Если документ и код расходятся, сервис делает то, что в коде, пока соответствующая фаза не принята.

## Принципы

1. **docs → contracts → code** внутри каждой фазы (как у метаслоя).
2. **SSOT применимости** — `configs/model_types/*.yaml` (+ `default_use` в `_common.yaml`). Таблица в design и снимок ниже **выводятся** из YAML; править вручную вторую копию нельзя.
3. Eval привязки с реальными книгами (Packt / RVI / Ашан) — на **локальной** машине с корпусом builder; cloud-агенты не выдумывают приватные книги.
4. Три фазы аудита (§6.1) не схлопываются; `finding_kind` режет их поперек вместе с `severity` и `error_class`.

## Обзор фаз

| Фаза | Название | Закрывает | Поставка |
|---|---|---|---|
| 0 | Документы | — | эта дорожная карта; sync §5.7 / §6.1; `eval/README.md` |
| 1 | Формальная матрица тип×метрика | 5.1 | явные ячейки + check-config/CI против каталогов |
| 2 | Корпус eval привязки (локально) | 5.2 | **срез:** `eval/labels/{packt,rvi}.json` + `eval/mapping/report.md` (2 книги); Ашан local-only; до 20–30 ещё расти |
| 3 | Виды находок аудита | 5.3 | `finding_kind` в Finding/API; маппинг правил |

---

## Фаза 0 — Документы

**Состав:** этот файл; §5.7 design указывает на YAML как SSOT и способ снять матрицу; нормативная заметка `finding_kind` в §6.1 (без кода); уточнение `eval/README.md` про источники корпуса и разметку.

**Не-цели:** любой код продукта; смена формул метрик; новые типы моделей; хостинг приватных книг в cloud CI.

**Критерии приёмки:**

- [x] Дорожная карта фаз 0–3 с не-целями и критериями.
- [x] Снимок матрицы тип×метрика совпадает с `configs/model_types/*.yaml`.
- [x] Design §5.7 не держит устаревшую 6-колоночную таблицу как SSOT.
- [x] Design §6.1 фиксирует нормативный набор `finding_kind`.
- [x] `eval/README.md` описывает корпус, workflow разметки и что цели фазы 2b — допущения до labels.

---

## Снимок матрицы применимости (фаза 1, машинный снимок)

Источник: `configs/model_types/*.yaml` на момент написания. Типов на диске **11** (+ `_common.yaml` с `compatible` и `default_use: not_applicable`). С фазы 1 у каждого id из `configs/metrics/` на каждом типе есть **явный** `use`; `default_use` и `"*"` у `other` — только запас на ещё не перечисленные метрики. Машинный снимок фазы 1: `configs/model_types/matrix.json`.

Обозначения: **R** = `required`, **O** = `optional`, **—** = `not_applicable`. После `/` — `variant`, если задан.

| Метрика | `project_finance` | `corporate` | `development_escrow` | `ppp_concession` | `investment_project` | `renewables_dpm` | `real_estate_income` | `lbo_ma` | `dcf_valuation` | `bank_leasing` | `other` |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `dscr` | R/`pf` | O/`corporate_covenant` | O/`pf` | R/`pf` | — | O/`pf` | O/`pf` | — | — | — | O |
| `dscr_min` | R | — | — | R | — | O | O | — | — | — | O |
| `dscr_avg` | O | — | — | O | — | O | O | — | — | — | O |
| `adscr` | O | — | — | O | — | — | — | — | — | — | O |
| `llcr` | O | — | — | O | — | — | — | — | — | — | O |
| `plcr` | O | — | — | O | — | — | — | — | — | — | O |
| `icr` | O | R | — | O | — | — | — | — | — | — | O |
| `net_debt_ebitda` | — | O | — | — | — | — | — | — | — | — | O |
| `escrow_coverage` | — | — | R | — | — | — | — | — | — | — | O |
| `npv` | — | — | — | O | R | — | — | — | — | — | O |
| `irr` | — | — | — | O | R | — | — | — | — | — | O |

**Типы без показателей покрытия из текущего каталога** (`lbo_ma`, `dcf_valuation`, `bank_leasing`): полноценные типы моделей (сигналы + `required_concepts`); относительно *текущего* каталога `configs/metrics/` все ячейки покрытия = `not_applicable`. Ценность сегодня — извлечение/цитирование понятий книги, не cover-ratios. Формулировка **не** запрещает будущие метрики для этих типов.

**Как снять актуальную матрицу** (после правок YAML) — форма, которую ждёт `validate_applicability_matrix()`:

```bash
fas dump-applicability          # пишет configs/model_types/matrix.json
fas dump-applicability --stdout # JSON в stdout
```

`fas check-config` / `load_model_types` с фазы 1 дополнительно сверяют dump применимости с `configs/model_types/matrix.json`.

---

## Фаза 1 — Формальная матрица + целостность

**Зачем:** ячейки `(type, metric)` не должны молча опираться на `default_use` для уже известных метрик; design и CI не расходятся с каталогами.

**Состав:**

1. Правило `fas check-config` / CI: у каждого id из `configs/metrics/` явный `use` на каждом типе (запрет тихого `default_use` для известных метрик; `default_use` — только запас на новые метрики до backfill, либо снятие после заполнения).
2. Машинночитаемая матрица (снимок `configs/model_types/matrix.json` или assert dump == checked-in) по полному набору метрик.
3. Сохранить проверки достижимости входов обязательных метрик из `required_concepts` / таксономии.
4. Тесты типов без показателей покрытия из текущего каталога (`lbo_ma`, `dcf_valuation`, `bank_leasing`): ячейки cover/NPV = `not_applicable`.

**Не-цели:** новые типы; новые формулы DSCR/ICR/…; смена порогов `FAS_MODEL_TYPE_*`.

**Критерии приёмки:**

- [x] Каждая ячейка тип×метрика каталога явная в YAML или в утверждённом снимке.
- [x] `fas check-config` ломается на пропущенной ячейке / битом variant.
- [x] Снимок `configs/model_types/matrix.json` совпадает с YAML (проверка в `load_model_types` / `fas check-config`).

---

## Фаза 2 — Корпус eval привязки (приоритет; локально)

**Зачем:** цели фазы 2b в design / `eval/README.md` (top-1, ECE, false binds, NIL recall) — **[допущения]** до корпуса 20–30 книг; стартовые labels Packt/RVI + измеренный срез уже в `eval/`, но гейты 2b не закрыты.

**Где:** self-hosted worker с checkout `~/projects/finance-analysis-service` и соседним builder `~/projects/finance-context-builder`.

**Источники книг:**

| Книга | Где брать | В git FAS |
|---|---|---|
| Packt | builder `resources/corpus/` (`packt-project-finance.xlsx`) | да: `tests/fixtures/builder/` + алиас `packt` в `tests/books.py` |
| RVI | то же (`rvi-project-finance.xlsx`) | да: фикстура + алиас `rvi` |
| Ашан | builder `resources/corpus/АШАН_модель*.xls(x)` (приватно, не в `corpus.lock.json`) | нет; labels — только локально при чувствительных путях |

**Состав:**

1. Инвентаризация корпуса; reuse fixture `job_id` где dumps уже есть.
2. `…:load` в локальный FAS (`FAS_IT_CORPUS` / sibling layout).
3. Авторство `eval/labels/{name}.json`: critical CFADS / `debt_service` / `interest` (+ NIL); предпочтительно стабильный `by_path`.
4. `fas eval mapping` (+ BLINKout `--prune` для ключевых понятий); коммит non-secret labels; Ашан — local-only при необходимости (как K3 / escrow: env + `.local.yaml`).
5. Зафиксировать измеренные метрики в отчёте `eval/`; только после этого цели 2b — evidence, не assumptions.
6. **Воспроизводимость отчёта (обязательные pins).** В каждом измеренном отчёте фиксировать: version схемы labels; SHA/version glossary (и taxonomy при отдельной версии); identity builder; FAS git SHA / mapping version; источник книги + `job_id`; точную командную строку `fas eval mapping` (+ `--prune` если был); version калибратора, если в отчёте есть ECE. **Дельты метрик без этого pin-набора недействительны** (несравнимы между прогонами).
7. Stretch: рост к 20–30 книгам из уже имеющегося корпуса/фикстур.

Cloud PR могут добавить helpers формата labels и CI skip без корпуса; **измерение и Ашан — локально**.

**Не-цели:** подмена mapping-eval снимком `eval/model_type/`; выкладывание приватных xlsx в cloud CI.

**Критерии приёмки:**

- [x] Labels для Packt и RVI в `eval/labels/` (или явный local-only путь с инструкцией).
- [x] Прогон `fas eval mapping` с записанными числами (`eval/mapping/report.md`, срез 2 книг).
- [x] Отчёт eval содержит полный pin-набор (labels schema / glossary·taxonomy / builder / FAS SHA·mapping / book+job_id / cmdline / calibrator-если-ECE).
- [x] В README / отчёте цели 2b помечены как измеренные или всё ещё допущения; дельты без pins не считаются evidence.

---

## Фаза 3 — Виды находок аудита (`finding_kind`)

**Зачем:** потребители сейчас смешивают ошибки, practice notes, нехватку данных и неоднозначность через один поток `Finding` + `needs_input` + статусы привязки.

**Граница Finding.** Finding = правила аудита фаз 1–3 + явно промотированные `needs_input` / `missing_input`. Вне Finding (если не промотированы): открытые статусы привязки, Questions, статус периода метрики.

**Нормативный набор** (enum + смыслы — SSOT в design §6.1; код — в этой фазе):

`finding_kind ∈ {error, warning, methodology, insufficient_data, ambiguity}`

`finding_kind`, `severity` (`info|low|medium|high|critical`) и Panko `error_class` (`mechanical|logic|omission|quantitative|qualitative`) — **независимые оси**. У одной Finding — один kind. `finding_kind=warning` ≠ severity с именем warning (в шкале severity warning нет). Три фазы правил аудита сохраняются.

**Дефолтный маппинг** `error_class`+`severity` → kind (override на правило в registry допустим и **авторитетен** — зафиксировать до финализации кода фазы 3):

| kind | Ориентир |
|---|---|
| `error` | quantitative high/critical, mechanical/logic |
| `warning` | прочие non-error / non-methodology (qualitative/info без смены методологии); в т.ч. отсутствие **необязательного** входа / пропуск необязательной проверки |
| `methodology` | practice / definition / covenant-definition notes (`dscr_default_definition`, …); опциональные methodology-пропуски тоже сюда, не в `insufficient_data` |
| `insufficient_data` | (a) явно промотированные `needs_input` / `missing_input`; (b) `error_class=omission` **только** как пробел в данных: отсутствует **обязательный** вход / обязательная проверка для применимой метрики или правила. **Не каждый** omission → `insufficient_data` (дефолт может брать omission как кандидата; kind сужается по required vs optional; registry override авторитетен) |
| `ambiguity` | неоднозначность на Finding (иначе — статусы привязки / Questions без дубля) |

**Инвариант omission:** `default_finding_kind` намеренно даёт `insufficient_data` для `error_class=omission` (кандидат data-gap). Любое omission-правило, которое на деле methodology / optional practice, **обязано** задать `Rule.finding_kind` (или call-site override). Registry guard в тестах: у каждого omission-правила либо default `insufficient_data`, либо явный override.

**Состав:** additive nullable поле на `Finding` (+ Parquet/API, backward compatible); фильтры `GET …/findings`; registry default по `error_class`+`severity`, override на правило; плагины — постепенно.

**Не-цели:** схлопывание трёх фаз аудита; смена open-world статусов привязки; автопромоут всех `needs_input`/`missing_input` без явного списка.

**Критерии приёмки:**

- [x] Nullable поле в схеме Finding и API; фильтр по kind.
- [x] Документированный маппинг для правил трёх фаз (default + явные override; omission→`insufficient_data` только для required-gap; registry authoritative).
- [x] Тесты: kind не подменяет severity/error_class; `kind=warning` ≠ severity warning.

---

## Вне скоупа

- Новые типы моделей и новые формулы коэффициентов.
- Смена enum open-world статусов строк (`bound` / `unknown` / `ambiguous` / …).
- Пересмотр метаслоя / DataMesh.
- Хостинг приватных книг (Ашан, K3) в cloud CI.

## Связь с трекером

Родитель: «Analytical core methodology roadmap». Дети: docs PR (фаза 0) → matrix integrity → eval corpus (local) → audit finding kinds.
