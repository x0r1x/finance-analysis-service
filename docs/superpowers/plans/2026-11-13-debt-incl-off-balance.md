# Debt including off-balance obligations — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Compute the money stock `debt_incl_off_balance` as the sum of bound component rows, without stealing the existing `debt_outstanding` labels and without summing mixed balance-sheet totals.

**Architecture:** Five new stock concepts are bindable labels. The metric lists them in `numerator.plus` with `aggregate: sum` and no denominator. A new pure function sums every bound row of those concepts per period. `select_ratio` dispatches that function before any ratio division. Only the `corporate` model type marks the metric optional.

**Tech Stack:** Python 3.12, pytest, existing FAS catalogs (`configs/concepts`, `configs/glossary`, `configs/metrics`, `configs/model_types`). Tests: `uv run pytest`.

**Spec:** This plan is the spec. There is no separate design file. Global Constraints below are binding.

## Global Constraints

- Metric id is exactly `debt_incl_off_balance`.
- Component concept ids, in this order: `long_term_borrowings`, `short_term_borrowings`, `other_financial_debt`, `off_balance_third_party`, `off_balance_lease`.
- Do not retarget existing labels. `Займы и кредиты`, `Заемные средства`, and `Заёмные средства` stay on `debt_outstanding`.
- Do not add a denominator. Do not route this metric through `composed_ratio`.
- `aggregate: sum` is the only new metric key. Its result unit is `money`. IRR stays a ratio.
- Sum signed `normalized_value`. Do not take absolute values.
- Sum every row with status `bound` or `bound_with_warning` for that concept. Do not keep only `is_primary`.
- A component with no bound row contributes 0 and is listed in warning `component_absent`. If no component is bound at all, status is `missing_input` and `rows` is empty.
- A concept listed in `absent` is ignored unless the row `source` is `confirmed` or `profile` (same rule as `_primaries`).
- No automatic subtraction of account 009 against lines 1430/1540/1520/1550. The bound amount is already the figure to add.
- Applicability: `corporate` is `optional`. Every other model type, including `other`, is `not_applicable`.
- Do not edit `debt_outstanding`, `net_debt`, DSCR, LLCR, or PLCR formulas.
- Commit subjects are one imperative English line.
- Do not commit unrelated dirty files. This branch starts from `main` (`f6a5c28`).

---

### Task 1: Component concepts and labels

**Files:**
- Modify: `configs/concepts/core.yaml` (add five concepts next to `debt_outstanding`)
- Create: `configs/glossary/long_term_borrowings.yaml`
- Create: `configs/glossary/short_term_borrowings.yaml`
- Create: `configs/glossary/other_financial_debt.yaml`
- Create: `configs/glossary/off_balance_third_party.yaml`
- Create: `configs/glossary/off_balance_lease.yaml`
- Modify: `tests/unit/test_glossary_package.py` (`_IDS`)
- Create: `tests/unit/test_debt_incl_off_balance.py`

**Interfaces:**
- Consumes: nothing
- Produces: concept ids listed in Global Constraints, each `semantic_role: measure`, `dimension: money`, `temporal_nature: stock`, no `expected_sign`. Labels below. `package.resolve` returns those concepts.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_debt_incl_off_balance.py`:

```python
"""Долг с учетом забалансовых обязательств: метки слагаемых не занимают остаток долга."""

from __future__ import annotations

from finance_analysis.application.catalog import load_catalog


def test_component_labels_resolve_and_old_debt_labels_stay():
    package = load_catalog()
    assert package.resolve("Долгосрочные заемные средства").concept == "long_term_borrowings"
    assert package.resolve("Строка 1410").concept == "long_term_borrowings"
    assert package.resolve("Краткосрочные заемные средства").concept == "short_term_borrowings"
    assert package.resolve("Строка 1510").concept == "short_term_borrowings"
    assert package.resolve("Прочая финансовая задолженность").concept == "other_financial_debt"
    assert package.resolve("Забалансовые обязательства по обязательствам третьих лиц").concept == "off_balance_third_party"
    assert package.resolve("Забалансовые обязательства по договорам финансового лизинга").concept == "off_balance_lease"
    assert package.resolve("Займы и кредиты").concept == "debt_outstanding"
    assert package.resolve("Заемные средства").concept == "debt_outstanding"
    assert package.resolve("Заёмные средства").concept == "debt_outstanding"
    for concept_id in (
        "long_term_borrowings",
        "short_term_borrowings",
        "other_financial_debt",
        "off_balance_third_party",
        "off_balance_lease",
    ):
        concept = package.concepts[concept_id]
        assert concept.semantic_role == "measure"
        assert concept.dimension == "money"
        assert concept.temporal_nature == "stock"
```

Add the same five ids to `_IDS` in `tests/unit/test_glossary_package.py`.

- [ ] **Step 2: Run the test and confirm it fails**

Run: `uv run pytest tests/unit/test_debt_incl_off_balance.py::test_component_labels_resolve_and_old_debt_labels_stay -q`

Expected: FAIL because the concepts are not in the catalog.

- [ ] **Step 3: Add concepts and glossary files**

In `configs/concepts/core.yaml`, immediately after the `debt_outstanding` block:

```yaml
  long_term_borrowings:
    semantic_role: measure
    dimension: money
    temporal_nature: stock
  short_term_borrowings:
    semantic_role: measure
    dimension: money
    temporal_nature: stock
  other_financial_debt:
    semantic_role: measure
    dimension: money
    temporal_nature: stock
  off_balance_third_party:
    semantic_role: measure
    dimension: money
    temporal_nature: stock
  off_balance_lease:
    semantic_role: measure
    dimension: money
    temporal_nature: stock
```

Glossary files. Pref languages are `ru` and `en`. No alt that duplicates `debt_outstanding`.

`configs/glossary/long_term_borrowings.yaml`:

```yaml
concept: long_term_borrowings
pref:
  en: "Long-term borrowings"
  ru: "Долгосрочные заемные средства"
alt:
  ru:
    - "Строка 1410"
definition:
  en: "RAS balance line 1410. A component of debt including off-balance obligations."
  ru: "Строка 1410 бухгалтерского баланса. Слагаемое долга с учетом забалансовых обязательств."
```

`configs/glossary/short_term_borrowings.yaml`:

```yaml
concept: short_term_borrowings
pref:
  en: "Short-term borrowings"
  ru: "Краткосрочные заемные средства"
alt:
  ru:
    - "Строка 1510"
definition:
  en: "RAS balance line 1510, including the current portion of long-term borrowings."
  ru: "Строка 1510 бухгалтерского баланса, включая текущую часть долгосрочных займов."
```

`configs/glossary/other_financial_debt.yaml`:

```yaml
concept: other_financial_debt
pref:
  en: "Other financial debt"
  ru: "Прочая финансовая задолженность"
definition:
  en: "Credit-like portion of lines 1450, 1520, 1550, and 1530 only when the note shows a borrowing. Not the line total."
  ru: "Кредитная доля строк 1450, 1520 и 1550. Строка 1530 входит только если расшифровка показывает заимствование. Итог смешанной строки не берется."
```

`configs/glossary/off_balance_third_party.yaml`:

```yaml
concept: off_balance_third_party
pref:
  en: "Off-balance third-party obligations"
  ru: "Забалансовые обязательства по обязательствам третьих лиц"
definition:
  en: "Unrecognized issued guarantees and sureties (account 009). Amounts already recognized on the balance sheet are not included again."
  ru: "Непризнанные выданные поручительства и гарантии (счет 009). Сумма, уже отраженная в пассиве, сюда не входит."
```

`configs/glossary/off_balance_lease.yaml`:

```yaml
concept: off_balance_lease
pref:
  en: "Off-balance finance lease obligations"
  ru: "Забалансовые обязательства по договорам финансового лизинга"
definition:
  en: "Lease payments that FSBU 25 did not recognize as a lease liability. A recognized lease liability is not included again."
  ru: "Платежи по аренде и лизингу, которые ФСБУ 25 не признал обязательством. Признанное обязательство по аренде сюда не входит."
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/unit/test_debt_incl_off_balance.py tests/unit/test_glossary_package.py tests/unit/test_rsbu_labels.py -q`

Expected: PASS. If another test freezes the concept-id set, add the five ids there and re-run that test. Do not change metric ids.

- [ ] **Step 5: Commit**

```bash
git add configs/concepts/core.yaml configs/glossary/long_term_borrowings.yaml configs/glossary/short_term_borrowings.yaml configs/glossary/other_financial_debt.yaml configs/glossary/off_balance_third_party.yaml configs/glossary/off_balance_lease.yaml tests/unit/test_debt_incl_off_balance.py tests/unit/test_glossary_package.py
git commit -m "Add debt components for off-balance-adjusted debt"
```

---

### Task 2: Sum of bound component rows

**Files:**
- Create: `src/finance_analysis/domain/debt_incl_off_balance.py`
- Modify: `tests/unit/test_debt_incl_off_balance.py`

**Interfaces:**
- Consumes: concept id strings from Task 1. Does not load YAML.
- Produces: `debt_incl_off_balance(*, components: tuple[str, ...], facts: list[dict], bindings: list[dict], periods: list[dict], absent: frozenset[str] = frozenset()) -> dict`

Return shape:

```python
{
    "metric": "debt_incl_off_balance",
    "rows": [
        {
            "period_id": str,
            "axis_id": str,
            "value": str,  # Decimal as plain string
            "status": "computed",
            "components": {concept_id: str},
        }
    ],
    "needs_input": [],
    "warnings": [{"code": "component_absent", "params": {"concepts": [str]}}],
    "status": "succeeded",
}
```

When nothing is bound: `status` is `missing_input`, `rows` is `[]`, `needs_input` is `[{"kind": "concept", "reason": "concept_unknown", "subject": "debt_incl_off_balance"}]`, `warnings` is `[]`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_debt_incl_off_balance.py`:

```python
from decimal import Decimal

from finance_analysis.domain.debt_incl_off_balance import debt_incl_off_balance

_COMPONENTS = (
    "long_term_borrowings",
    "short_term_borrowings",
    "other_financial_debt",
    "off_balance_third_party",
    "off_balance_lease",
)


def _bind(concept: str, row: str, *, primary: bool = True) -> dict:
    return {
        "effective_concept": concept,
        "row_key": row,
        "is_primary": primary,
        "status": "bound",
        "source": "inferred",
    }


def _fact(row: str, period: str, value: str) -> dict:
    return {
        "row_key": row,
        "axis_id": "a",
        "period_id": period,
        "normalized_value": value,
    }


def _year(period: str = "Y1") -> dict:
    return {"axis_id": "a", "period_id": period, "period_index": 1, "grain": "year", "timeline_id": "t"}


def test_sum_adds_bound_rows_and_zeros_a_missing_component():
    got = debt_incl_off_balance(
        components=_COMPONENTS,
        facts=[
            _fact("lt", "Y1", "100"),
            _fact("st", "Y1", "40"),
            _fact("lease_note", "Y1", "10"),
            _fact("derivative", "Y1", "5"),
            _fact("off_lease", "Y1", "7"),
        ],
        bindings=[
            _bind("long_term_borrowings", "lt"),
            _bind("short_term_borrowings", "st"),
            _bind("other_financial_debt", "lease_note"),
            _bind("other_financial_debt", "derivative", primary=False),
            _bind("off_balance_lease", "off_lease"),
        ],
        periods=[_year()],
    )
    assert got["status"] == "succeeded"
    assert got["rows"][0]["value"] == "162"
    assert Decimal(got["rows"][0]["components"]["other_financial_debt"]) == Decimal("15")
    assert got["warnings"] == [
        {"code": "component_absent", "params": {"concepts": ["off_balance_third_party"]}}
    ]


def test_no_bound_component_is_missing_input():
    got = debt_incl_off_balance(
        components=_COMPONENTS,
        facts=[_fact("lt", "Y1", "100")],
        bindings=[],
        periods=[_year()],
    )
    assert got["status"] == "missing_input"
    assert got["rows"] == []
    assert got["needs_input"] == [
        {"kind": "concept", "reason": "concept_unknown", "subject": "debt_incl_off_balance"}
    ]


def test_negative_stock_is_not_flipped():
    got = debt_incl_off_balance(
        components=_COMPONENTS,
        facts=[_fact("lt", "Y1", "-20"), _fact("st", "Y1", "5")],
        bindings=[
            _bind("long_term_borrowings", "lt"),
            _bind("short_term_borrowings", "st"),
        ],
        periods=[_year()],
    )
    assert got["rows"][0]["value"] == "-15"
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `uv run pytest tests/unit/test_debt_incl_off_balance.py -q`

Expected: FAIL on import of `debt_incl_off_balance`.

- [ ] **Step 3: Implement the sum**

Create `src/finance_analysis/domain/debt_incl_off_balance.py`.

Rules the code must follow:

- Import `Decimal` and `InvalidOperation`.
- Bound statuses are `bound` and `bound_with_warning`.
- Skip a row whose concept is outside `components`.
- Skip a row whose concept is in `absent` when `source` is not `confirmed` or `profile`.
- Read `normalized_value` with `Decimal(str(value))`. Skip a fact that is not a decimal.
- Key a fact by `(axis_id, period_id)`.
- For each such key that appears on a bound row, sum the decimals of every bound row of each component. A component with bound rows but no decimal on that key contributes 0 for that key and is not a separate warning.
- `components` on the row maps only concepts that had a bound row, to `str(total)` of that concept.
- `value` is `str(grand_total)`.
- Warning `component_absent` lists component ids that have no bound row, in the order of the `components` argument. Omit the warning when the list is empty.
- Ignore `periods` for arithmetic. Keep the argument so callers pass the same bundle as other metrics.
- Do not import the catalog. Do not divide.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/unit/test_debt_incl_off_balance.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/finance_analysis/domain/debt_incl_off_balance.py tests/unit/test_debt_incl_off_balance.py
git commit -m "Sum bound rows into off-balance-adjusted debt"
```

---

### Task 3: Catalog, applicability, and analysis dispatch

**Files:**
- Modify: `configs/metrics/coverage.yaml` (append the metric)
- Modify: `src/finance_analysis/domain/model_type.py` (`MetricExpression.aggregate`)
- Modify: `src/finance_analysis/application/model_types.py` (`_expression`, `_composed`)
- Modify: `src/finance_analysis/domain/validation/catalog_integrity.py` (`_METRIC_KEYS`, reject a bad aggregate)
- Modify: `src/finance_analysis/domain/financial_catalog.py` (`result_unit`)
- Modify: `configs/model_types/corporate.yaml` and every other `configs/model_types/*.yaml` except `_common.yaml`
- Modify: `configs/model_types/matrix.json` via `uv run fas dump-applicability`
- Modify: `src/finance_analysis/domain/covenant.py` (`select_ratio`)
- Modify: `src/finance_analysis/application/analyses.py` (`RATIO_METRICS`)
- Modify: `tests/contract/test_api.py`
- Modify: `tests/contract/test_analyses.py`
- Modify: `tests/unit/test_model_type_slice5.py` (the literal `11`)
- Modify: `tests/unit/test_debt_incl_off_balance.py`

**Interfaces:**
- Consumes: `debt_incl_off_balance` from Task 2 and the five concept ids from Task 1.
- Produces: metric id `debt_incl_off_balance` in `load_metric_inputs()` and `RATIO_METRICS`, unit `money`, `corporate` use `optional`, `select_ratio("debt_incl_off_balance", ...)` returns the Task 2 result.

- [ ] **Step 1: Write the failing catalog test**

Append to `tests/unit/test_debt_incl_off_balance.py`:

```python
from finance_analysis.application.analyses import RATIO_METRICS
from finance_analysis.application.financial_catalog import load_financial_catalog
from finance_analysis.application.model_types import load_model_types
from finance_analysis.domain.covenant import select_ratio
from finance_analysis.domain.model_type import applicability


def test_metric_is_a_money_sum_optional_only_for_corporate():
    catalog = load_model_types()
    financial = load_financial_catalog()
    indicator = financial.get("debt_incl_off_balance")
    assert indicator is not None
    assert indicator.unit == "money"
    assert indicator.formula.numerator.plus == _COMPONENTS
    assert indicator.formula.denominator is None
    assert "debt_incl_off_balance" in RATIO_METRICS
    assert applicability(catalog, ("corporate",), "debt_incl_off_balance") == "optional"
    for type_id in catalog.types:
        if type_id == "corporate":
            continue
        assert applicability(catalog, (type_id,), "debt_incl_off_balance") == "not_applicable"
    got = select_ratio(
        "debt_incl_off_balance",
        None,
        {
            "facts": [_fact("lt", "Y1", "30"), _fact("st", "Y1", "2")],
            "bindings": [
                _bind("long_term_borrowings", "lt"),
                _bind("short_term_borrowings", "st"),
            ],
            "periods": [_year()],
            "absent": frozenset(),
            "sign_convention": "outflow_negative",
            "marker_class": None,
        },
        profile=None,
        profile_ref=None,
        composed=catalog.composed,
        concepts=frozenset(catalog.concepts),
        money=frozenset(),
    )
    assert got["status"] == "succeeded"
    assert got["rows"][0]["value"] == "32"
```

`load_financial_catalog` may have a different import path. Open `src/finance_analysis/application/financial_catalog.py` and call the public loader that `GET /v1/metrics` uses. If the function name differs, use that name. The assertions stay.

- [ ] **Step 2: Run the test and confirm it fails**

Run: `uv run pytest tests/unit/test_debt_incl_off_balance.py::test_metric_is_a_money_sum_optional_only_for_corporate -q`

Expected: FAIL because the metric is absent.

- [ ] **Step 3: Register the metric and dispatch it**

Append to `metrics:` in `configs/metrics/coverage.yaml`:

```yaml
  debt_incl_off_balance:
    aggregate: sum
    numerator: {plus: [long_term_borrowings, short_term_borrowings, other_financial_debt, off_balance_third_party, off_balance_lease]}
    window: period
    definition: "Долг = строки 1410 и 1510 + кредитная доля строк 1450, 1520 и 1550 + непризнанные выданные обеспечения за третьих лиц + аренда, не признанная обязательством по ФСБУ 25. Строка 1530 входит только при заимствовании. Одно обязательство не прибавляется дважды."
```

`MetricExpression` gains `aggregate: str | None = None` as the last field with that default.

`_expression` reads `aggregate`. Allowed value is only `sum`. Any other value raises `ModelTypeInvalid`. Pass it into `MetricExpression`.

`_composed`: when `aggregate` is `sum`, require a dict numerator, require `window` of `period` or `LTM`, reject a `denominator` key, and return `Composed(numerator_side, Side((), ()), window)`.

`_METRIC_KEYS` includes `aggregate`. In `validate_catalog_integrity` path that walks metric bodies, reject `aggregate` other than `sum` with `CatalogIntegrityError`. A `sum` metric with a `denominator` key is also an error.

`result_unit`: if the resolved expression has `aggregate == "sum"` and a non-empty numerator and an empty denominator, return `_dim` of the first numerator term. Leave the later `num and not den → ratio` branch in place for IRR.

In every model-type file except `_common.yaml`, add an explicit cell:

- `configs/model_types/corporate.yaml`: `debt_incl_off_balance: {use: optional}`
- all others, including `other.yaml`: `debt_incl_off_balance: {use: not_applicable}`

Run `uv run fas dump-applicability` so `configs/model_types/matrix.json` matches.

`RATIO_METRICS` in `analyses.py`: append `"debt_incl_off_balance"` after `"irr"`.

`select_ratio`: before the `npv`/`irr` branch, when `metric == "debt_incl_off_balance"`:

```python
formula = composed.get(metric)
plus = formula.numerator.plus if formula is not None else ()
return debt_incl_off_balance(
    components=plus,
    facts=common["facts"],
    bindings=common["bindings"],
    periods=common["periods"],
    absent=common["absent"],
)
```

Update the hardcoded metric lists in `tests/contract/test_api.py` and `tests/contract/test_analyses.py` to append `"debt_incl_off_balance"` after `"irr"`.

In `tests/unit/test_model_type_slice5.py`, change `assert len(RATIO_METRICS) == 11` to `== 12`.

- [ ] **Step 4: Run the tests**

Run:

```bash
uv run pytest tests/unit/test_debt_incl_off_balance.py tests/unit/test_applicability_matrix.py tests/unit/test_financial_model_catalog.py tests/unit/test_model_type_slice5.py tests/unit/test_catalog_integrity.py tests/contract/test_api.py tests/contract/test_analyses.py -q
```

Expected: PASS. Fix only failures caused by the new metric id or the new `aggregate` field. Do not change unrelated metrics.

- [ ] **Step 5: Commit**

```bash
git add configs/metrics/coverage.yaml configs/model_types src/finance_analysis/domain/model_type.py src/finance_analysis/application/model_types.py src/finance_analysis/domain/validation/catalog_integrity.py src/finance_analysis/domain/financial_catalog.py src/finance_analysis/domain/covenant.py src/finance_analysis/application/analyses.py tests/contract/test_api.py tests/contract/test_analyses.py tests/unit/test_model_type_slice5.py tests/unit/test_debt_incl_off_balance.py
git commit -m "Publish off-balance-adjusted debt as a corporate metric"
```
