"""Цитирование строк LBO. Значение берётся из книги и не пересчитывается.

Как `payback`: отдельной формулы нет, строка не входит в матрицу коэффициентов
и не создаёт вопрос. Список пуст, пока основной тип не уверенный `lbo_ma`.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from finance_analysis.domain.metrics import _primaries

# Порядок — как в утверждении среза: сначала MOIC, затем стоимость на выходе.
CITED_CONCEPTS = ("moic", "exit_enterprise_value")


def cite_lbo_book_rows(
    *,
    source: str,
    primary: str | None,
    bindings: list[dict],
    facts: list[dict],
    absent: frozenset[str] = frozenset(),
) -> list[dict]:
    """Строки книги для уверенного `lbo_ma`. Нерешённый тип получает пустой список.

    Несколько чисел одной основной строки отдаются как есть и не складываются.
    Отсутствующая строка остаётся в списке со статусом `absent` и без вопроса.
    """

    if source == "unresolved" or primary != "lbo_ma":
        return []
    primaries = _primaries(bindings, absent)
    cited = []
    for concept in CITED_CONCEPTS:
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
    found = []
    for fact in facts:
        if fact.get("row_key") != row_key:
            continue
        text = _decimal_text(fact.get("normalized_value"))
        if text is None:
            continue
        found.append(text)
    return found


def _decimal_text(number) -> str | None:
    if number is None or isinstance(number, bool):
        return None
    try:
        return format(Decimal(str(number)), "f")
    except (InvalidOperation, ValueError):
        return None
