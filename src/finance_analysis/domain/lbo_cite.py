"""Цитирование строк LBO. Значение берётся из ячейки и не пересчитывается.

Как `payback`: отдельной формулы нет, строка не входит в матрицу коэффициентов
и не создаёт вопрос. Список пуст, пока основной тип не уверенный `lbo_ma`.
Число цитаты — `value_dec`. `normalized_value` его не подменяет.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from finance_analysis.domain.metrics import _BOUND, HUMAN_SOURCES

# Порядок — как в утверждении среза: сначала MOIC, затем стоимость на выходе.
CITED_CONCEPTS = ("moic", "exit_enterprise_value")
# Пустая ячейка и ячейка «не применимо» цитатой не становятся. Нет статуса —
# наблюдение ещё можно цитировать, если `value_dec` разбирается.
_CITABLE_STATUS = frozenset({None, "cached", "zero_explicit"})
_AMBIGUOUS = "ambiguous"


def cite_lbo_book_rows(
    *,
    source: str,
    primary: str | None,
    bindings: list[dict],
    facts: list[dict],
    absent: frozenset[str] = frozenset(),
) -> list[dict]:
    """Строки книги для уверенного `lbo_ma`. Нерешённый тип получает пустой список.

    Несколько наблюдений одной строки отдаются как есть и не складываются.
    Отсутствующая строка остаётся в списке со статусом `absent` и без вопроса.
    Несколько основных привязок одного понятия не сводятся к последней строке.
    """

    if source == "unresolved" or primary != "lbo_ma":
        return []
    cited = []
    for concept in CITED_CONCEPTS:
        chosen = _one_primary(bindings, concept, absent)
        if chosen is _AMBIGUOUS:
            cited.append(
                {"concept": concept, "status": "ambiguous", "observations": []}
            )
            continue
        if chosen is None:
            cited.append({"concept": concept, "status": "absent", "observations": []})
            continue
        observations = _observations(facts, str(chosen.get("row_key") or ""))
        cited.append(
            {
                "concept": concept,
                "status": "cited" if observations else "absent",
                "row_key": chosen.get("row_key"),
                "observations": observations,
            }
        )
    return cited


def _one_primary(bindings: list[dict], concept: str, absent: frozenset[str]):
    """Одна основная строка понятия. Ноль строк — `None`, больше одной — неоднозначно.

    `metrics._primaries` при нескольких привязках молча оставляет последнюю.
    Для цитаты это была бы случайная строка, поэтому выбор здесь свой.
    """

    found: dict[str, dict] = {}
    for row in bindings:
        name = row.get("effective_concept")
        if not (
            row.get("is_primary") and row.get("status") in _BOUND and name == concept
        ):
            continue
        if concept in absent and row.get("source") not in HUMAN_SOURCES:
            continue
        found.setdefault(str(row.get("row_key") or ""), row)
    if not found:
        return None
    if len(found) > 1:
        return _AMBIGUOUS
    return next(iter(found.values()))


def _observations(facts: list[dict], row_key: str) -> list[dict]:
    found = []
    for fact in facts:
        if fact.get("row_key") != row_key or not _citable(fact):
            continue
        item: dict = {}
        if fact.get("cell_id") is not None:
            item["cell_id"] = str(fact["cell_id"])
        item["value"] = _decimal_text(fact.get("value_dec"))
        for field in ("normalized_value", "scale_factor"):
            if field not in fact or fact[field] is None:
                continue
            text = _decimal_text(fact[field])
            if text is not None:
                item[field] = text
        for field in ("axis_id", "period_id", "value_status"):
            if fact.get(field) is not None:
                item[field] = fact[field]
        if fact.get("period_index") is not None and not isinstance(
            fact.get("period_index"), bool
        ):
            item["period_index"] = fact["period_index"]
        found.append(item)
    return found


def _citable(fact: dict) -> bool:
    if fact.get("value_status") not in _CITABLE_STATUS:
        return False
    return _decimal_text(fact.get("value_dec")) is not None


def _decimal_text(number) -> str | None:
    if number is None or isinstance(number, bool):
        return None
    try:
        value = Decimal(str(number))
    except (InvalidOperation, ValueError):
        return None
    if not value.is_finite():
        return None
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text
