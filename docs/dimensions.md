# Units and dimensions (public contract)

Каталог: `configs/dimensions.yaml`. Код: `finance_analysis.domain.dimensions`. Версия каталога входит в [`SemanticModelVersion`](semantic-model-version.md) (`dimensions.id` + `dimensions.stamp`). Оси понятия и решение 42 — [design-v0.23.md](design-v0.23.md).

Это **публичный контракт единиц/размерностей**. Правила аудита `dimension_mismatch` и `pricing_basis_mismatch` уже живут в `plugins/rules/structure.py`; этот документ их не переписывает.

## 1. Что где лежит

| Слой | Что хранит |
|---|---|
| Понятие (`configs/concepts/`) | имя `dimension` из каталога; не конкретную валюту/МВт·ч |
| Каталог (`configs/dimensions.yaml`) | базовые и составные размерности, допустимые `units`, у ценовых — `pricing_basis` / у мощности — `billing_period` на единице |
| Строка / факт книги | конкретная единица (`RUB`, `MWh`, …) и `scale_factor` |

Совпадение физических показателей (одинаковые exponents) **не** доказывает экономическую совместимость: `currency_per_energy` и `currency_per_power_time` совпадают по степеням, но это разные цены (`pricing_basis`: `energy` vs `capacity`).

## 2. Каталог

Базовые: `money`, `power`, `duration`, `count`, `area`. Безразмерная: `ratio`. Составные: `energy` (power × duration), `currency_per_energy`, `currency_per_power_time`.

- `pricing_basis` ∈ `{energy, capacity}` — основа тарифа, не период отчёта книги.
- `billing_period` ∈ `{year, quarter, month, day}` — расчётный период платы за мощность на единице каталога.
- Валюта на ценовой единице (`currency`) — свойство единицы, не понятия.

Свёртка по времени следует из `temporal_nature` понятия (`sum` / `last` / `none`), явный `aggregation` — только исключение. Свёртка по объектам — отдельное `object_aggregation` (сейчас `weighted_average` с согласованным весом).

## 3. Enforcement (уже есть)

| Правило | Когда |
|---|---|
| `dimension_mismatch` | арифметика / формула смешивает несовместимые размерности |
| `pricing_basis_mismatch` | совпали показатели, но разошлись `pricing_basis`, `billing_period`, валюта или копирование без конверсии |

Клиент и DataMesh читают имена размерностей и единицы из каталога + факты книги; смену поведения правил этот контракт не обещает.
