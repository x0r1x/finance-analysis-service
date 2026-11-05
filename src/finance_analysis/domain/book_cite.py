"""Цитата строк книги для уверенного типа. Значение берётся из книги и не пересчитывается.

Как у строки срока окупаемости: отдельной формулы нет, строка не входит в матрицу
коэффициентов и не создаёт вопрос. Список пуст, пока основной тип не из среза.
`lbo_ma` сюда не входит.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from finance_analysis.domain.metrics import _primaries

# Пустое, ошибочное и отсутствующее значение не являются числом ячейки.
_NOT_A_NUMBER = frozenset({"empty", "not_applicable", "error", "missing"})

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

    Несколько чисел одной основной строки отдаются как есть и не складываются.
    Отсутствующая строка остаётся в списке со статусом `absent` и без вопроса.
    """

    concepts = CITED_BY_TYPE.get(primary or "")
    if source == "unresolved" or concepts is None:
        return []
    primaries = _primaries(bindings, absent)
    cited = []
    for concept in concepts:
        row = primaries.get(concept)
        if row is None:
            cited.append({"concept": concept, "status": "absent", "values": []})
            continue
        values = _values(facts, str(row.get("row_key") or ""))
        cited.append(
            {
                "concept": concept,
                "status": "cited" if values else "absent",
                "row_key": row.get("row_key"),
                "values": values,
            }
        )
    return cited


def _values(facts: list[dict], row_key: str) -> list[str]:
    """Числа листа в порядке фактов. Берётся `value_dec`, не нормализованная величина."""

    found = []
    for fact in facts:
        if fact.get("row_key") != row_key:
            continue
        text = _sheet_value(fact)
        if text is None:
            continue
        found.append(text)
    return found


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
