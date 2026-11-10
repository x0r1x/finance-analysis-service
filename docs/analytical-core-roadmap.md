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
| 2 | Корпус eval привязки (локально) | 5.2 | labels Packt/RVI/Ашан (+ рост); измеренные гейты |
| 3 | Виды находок аудита | 5.3 | `finding_kind` в Finding/API; маппинг правил |

---

## Фаза 0 — Документы (текущая)

**Состав:** этот файл; §5.7 design указывает на YAML как SSOT и способ снять матрицу; нормативная заметка `finding_kind` в §6.1 (без кода); уточнение `eval/README.md` про источники корпуса и разметку.

**Не-цели:** любой код продукта; смена формул метрик; новые типы моделей; хостинг приватных книг в cloud CI.

**Критерии приёмки:**

- [x] Дорожная карта фаз 0–3 с не-целями и критериями.
- [x] Снимок матрицы тип×метрика совпадает с `configs/model_types/*.yaml`.
- [x] Design §5.7 не держит устаревшую 6-колоночную таблицу как SSOT.
- [x] Design §6.1 фиксирует нормативный набор `finding_kind`.
- [x] `eval/README.md` описывает корпус, workflow разметки и что цели фазы 2b — допущения до labels.

---

## Снимок матрицы применимости (фаза 0)

Источник: `configs/model_types/*.yaml` на момент написания. Типов на диске **11** (+ `_common.yaml` с `compatible` и `default_use: not_applicable`). Ячейка без явного `use` у типа (кроме `other` с `"*": optional`) = `default_use`.

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

Cite-only типы (`lbo_ma`, `dcf_valuation`, `bank_leasing`): все метрики каталога `not_applicable`; смысл типа — цитаты понятий книги, не cover-ratios.

**Как снять актуальную матрицу** (после правок YAML):

```bash
PYTHONPATH=src python - <<'PY'
from finance_analysis.application.model_types import load_model_types
from finance_analysis.application.financial_catalog import load_financial_catalog

catalog = load_model_types()
fin = load_financial_catalog(model_types=catalog)
for metric_id, ind in sorted(fin.indicators.items()):
    cells = {
        type_id: ({"use": use.use} | ({"variant": use.variant} if use.variant else {}))
        for type_id, use in sorted(ind.model_types.items())
    }
    print(metric_id, cells)
PY
```

`fas check-config` загружает те же каталоги и падает на битом YAML; отдельного артефакта-снимка матрицы в фазе 0 ещё нет (фаза 1).

---

## Фаза 1 — Формальная матрица + целостность

**Зачем:** ячейки `(type, metric)` не должны молча опираться на `default_use` для уже известных метрик; design и CI не расходятся с каталогами.

**Состав:**

1. Правило `fas check-config` / CI: у каждого id из `configs/metrics/` явный `use` на каждом типе (запрет тихого `default_use` для известных метрик; `default_use` — только запас на новые метрики до backfill, либо снятие после заполнения).
2. Машинночитаемая матрица (снимок `configs/model_types/matrix.json` или assert dump == checked-in) по полному набору метрик.
3. Сохранить проверки достижимости входов обязательных метрик из `required_concepts` / таксономии.
4. Тесты cite-only типов: ячейки cover/NPV = `not_applicable`.

**Не-цели:** новые типы; новые формулы DSCR/ICR/…; смена порогов `FAS_MODEL_TYPE_*`.

**Критерии приёмки:**

- [ ] Каждая ячейка тип×метрика каталога явная в YAML или в утверждённом снимке.
- [ ] `fas check-config` ломается на пропущенной ячейке / битом variant.
- [ ] Снимок в docs (или генерация в CI) совпадает с YAML.

---

## Фаза 2 — Корпус eval привязки (приоритет; локально)

**Зачем:** цели фазы 2b в design / `eval/README.md` (top-1, ECE, false binds, NIL recall) сейчас **[допущения]** — в репозитории нет `eval/labels/*.json`.

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
6. Stretch: рост к 20–30 книгам из уже имеющегося корпуса/фикстур.

Cloud PR могут добавить helpers формата labels и CI skip без корпуса; **измерение и Ашан — локально**.

**Не-цели:** подмена mapping-eval снимком `eval/model_type/`; выкладывание приватных xlsx в cloud CI.

**Критерии приёмки:**

- [ ] Labels для Packt и RVI в `eval/labels/` (или явный local-only путь с инструкцией).
- [ ] Прогон `fas eval mapping` с записанными числами.
- [ ] В README / отчёте цели 2b помечены как измеренные или всё ещё допущения.

---

## Фаза 3 — Виды находок аудита (`finding_kind`)

**Зачем:** потребители сейчас смешивают ошибки, practice notes, нехватку данных и неоднозначность через один поток `Finding` + `needs_input` + статусы привязки.

**Нормативный набор** (design §6.1; код — в этой фазе):

`finding_kind ∈ {error, warning, methodology, insufficient_data, ambiguity}`

Ортогонален `severity` (`info|low|medium|high|critical`) и Panko `error_class` (`mechanical|logic|omission|quantitative|qualitative`). Три фазы правил аудита сохраняются.

**Маппинг (норматив → код):**

| kind | Ориентир |
|---|---|
| `error` | quantitative high/critical, mechanical/logic |
| `warning` | qualitative / low info без смены методологии |
| `methodology` | заметки определения/ковенанта/практики (`dscr_default_definition`, practice notes) |
| `insufficient_data` | выбранные пути `needs_input` / `missing_input` на поверхности аудита |
| `ambiguity` | неоднозначность привязки/вопроса (или связь с существующим question без дубля) |

**Состав:** поле на `Finding` (+ Parquet/API); фильтры `GET …/findings`; registry default по `error_class`+`severity`, override на правило; плагины — постепенно.

**Не-цели:** схлопывание трёх фаз аудита; смена open-world статусов привязки.

**Критерии приёмки:**

- [ ] Поле в схеме Finding и API; фильтр по kind.
- [ ] Документированный маппинг для правил трёх фаз (хотя бы default + явные override).
- [ ] Тесты: kind не подменяет severity/error_class.

---

## Вне скоупа

- Новые типы моделей и новые формулы коэффициентов.
- Смена enum open-world статусов строк (`bound` / `unknown` / `ambiguous` / …).
- Пересмотр метаслоя / DataMesh.
- Хостинг приватных книг (Ашан, K3) в cloud CI.

## Связь с трекером

Родитель: «Analytical core methodology roadmap». Дети: docs PR (фаза 0) → matrix integrity → eval corpus (local) → audit finding kinds.
