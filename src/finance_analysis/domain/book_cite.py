"""Цитата строк книги для уверенного типа. Значение берётся из книги и не пересчитывается.

Как у строки срока окупаемости: отдельной формулы нет, строка не входит в матрицу
коэффициентов и не создаёт вопрос. Список пуст, пока основной тип не из среза.
`lbo_ma` сюда не входит.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

# Пустое, ошибочное и отсутствующее значение не являются числом ячейки.
_NOT_A_NUMBER = frozenset({"empty", "not_applicable", "error", "missing"})
_BOUND = frozenset({"bound", "bound_with_warning"})
_HUMAN = frozenset({"confirmed", "profile"})

# Порядок понятий — как в утверждённых абзацах к решениям 37 и 38.
CITED_BY_TYPE = {
    "bank_leasing": ("lease_interest_income", "npl_share", "provision_coverage"),
    "dcf_valuation": ("wacc", "terminal_value", "enterprise_value", "equity_value"),
    "renewables_dpm": ("degradation", "energy_generation", "energy_tariff"),
    "real_estate_income": ("cap_rate",),
    "development_escrow": ("escrow_inflow", "escrow_disclosure", "effective_rate"),
}


def cite_type_book_rows(
    *,
    source: str,
    primary: str | None,
    bindings: list[dict],
    facts: list[dict],
    absent: frozenset[str] = frozenset(),
) -> list[dict]:
    """Строки книги для уверенного основного типа. Нерешённый тип получает пустой список.

    Несколько чисел одной основной строки отдаются отдельными наблюдениями и не складываются.
    Пропуск периода остаётся на своём месте. Отсутствующая строка — статус `absent`, без вопроса.
    """

    concepts = CITED_BY_TYPE.get(primary or "")
    if source == "unresolved" or concepts is None:
        return []
    cited = []
    for concept in concepts:
        status, row = _unique_row(concept, bindings, source, absent)
        if row is None:
            cited.append({"concept": concept, "status": status, "observations": []})
            continue
        cited.append(
            {
                "concept": concept,
                "status": "cited",
                "row_key": row.get("row_key"),
                "observations": _observations(facts, str(row.get("row_key") or "")),
            }
        )
    return cited


def _unique_row(
    concept: str,
    bindings: list[dict],
    type_source: str,
    absent: frozenset[str],
) -> tuple[str, dict | None]:
    """Одна основная строка. Несколько основных не схлопываются в последнюю."""

    rows = []
    for row in bindings:
        if row.get("effective_concept") != concept or not row.get("is_primary"):
            continue
        if row.get("status") not in _BOUND:
            continue
        if concept in absent and row.get("source") not in _HUMAN:
            continue
        if type_source in _HUMAN and row.get("source") not in _HUMAN:
            continue
        rows.append(row)
    keys = []
    for row in rows:
        key = row.get("row_key")
        if key not in keys:
            keys.append(key)
    if len(keys) == 1:
        return "cited", next(row for row in rows if row.get("row_key") == keys[0])
    if len(keys) > 1:
        return "ambiguous", None
    return "absent", None


def _observations(facts: list[dict], row_key: str) -> list[dict]:
    """Наблюдения строки: `period_index` внутри `axis_id`, пропуски не выкидываются."""

    chosen = [fact for fact in facts if fact.get("row_key") == row_key]
    ordered = sorted(enumerate(chosen), key=lambda item: _order(item[1], item[0]))
    return [_observation(fact) for _, fact in ordered]


def _order(fact: dict, position: int) -> tuple:
    axis = "" if fact.get("axis_id") is None else str(fact.get("axis_id"))
    return (axis, _period_index(fact), position)


def _period_index(fact: dict) -> int:
    index = fact.get("period_index")
    if index is None or index == "":
        return 10**9
    try:
        return int(index)
    except (TypeError, ValueError):
        return 10**9


def _observation(fact: dict) -> dict:
    observed = {
        "cell_id": fact.get("cell_id"),
        "axis_id": fact.get("axis_id"),
        "period_id": fact.get("period_id"),
        "period_index": fact.get("period_index"),
        "value": _sheet_value(fact),
        "value_status": fact.get("value_status"),
    }
    if fact.get("normalized_value") is not None:
        observed["normalized_value"] = _decimal_text(fact.get("normalized_value"))
    if fact.get("scale_factor") not in (None, ""):
        observed["scale_factor"] = fact.get("scale_factor")
    return observed


def _sheet_value(fact: dict) -> str | None:
    """Кэш ячейки. Нормализованная величина отсутствующий `value_dec` не подменяет."""

    if fact.get("value_status") in _NOT_A_NUMBER:
        return None
    return _decimal_text(fact.get("value_dec"))


def _decimal_text(number) -> str | None:
    if number is None or isinstance(number, bool):
        return None
    try:
        return format(Decimal(str(number)), "f")
    except (InvalidOperation, ValueError):
        return None
