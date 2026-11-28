"""Знак, природа и исключение строки (§5.4). Фазу отсюда не ставим."""

from __future__ import annotations

from finance_analysis.domain.glossary import normalize_label

_EXCLUDED_KINDS = frozenset({"helper", "flag", "index"})
# Пустая ячейка, «не применимо» и отсутствие статуса — не число ряда.
_BLANK_STATUS = frozenset({None, "empty", "not_applicable"})


def exclusion(row: dict, *, empty_series: bool) -> tuple[bool, str | None]:
    if row.get("check_row"):
        return True, "check_row"
    if row.get("kind") in _EXCLUDED_KINDS:
        return True, row["kind"]
    if row.get("hidden") and not row.get("hidden_by_outline"):
        return True, "hidden"
    if empty_series:
        return True, "empty_series"
    return False, None


def infer_row(row: dict, flows: dict) -> dict:
    label = normalize_label(str(row.get("label") or ""))
    sign = _flow(label, flows)
    nature = "flow" if sign else None
    aggregation = "aggregate" if any(token in label for token in ("total", "итого", "всего")) else None
    return {"sign": sign, "nature": nature, "aggregation": aggregation, "source": "inferred"}


def _flow(label: str, flows: dict) -> str | None:
    for direction in ("outflow", "inflow"):
        for token in flows.get(direction) or ():
            if normalize_label(token) and normalize_label(token) in label:
                return direction
    return None


def facts_by_row(facts: list[dict] | None) -> dict[str | None, list[dict]] | None:
    """Факты по `row_key` за один проход. `None` — списка фактов нет."""

    if facts is None:
        return None
    grouped: dict[str | None, list[dict]] = {}
    for fact in facts:
        grouped.setdefault(fact.get("row_key"), []).append(fact)
    return grouped


def series_is_empty(row_key: str | None, by_row: dict[str | None, list[dict]] | None) -> bool:
    """Та же пустая серия, что `empty_series`, по уже сгруппированным фактам."""

    if by_row is None or row_key is None:
        return False
    return _own_is_empty(by_row.get(row_key) or [])


def empty_series(row_key: str, facts: list[dict] | None) -> bool:
    if facts is None or row_key is None:
        return False
    return _own_is_empty([fact for fact in facts if fact.get("row_key") == row_key])


def _own_is_empty(own: list[dict]) -> bool:
    if not own:
        return True
    return all(fact.get("value_status") in _BLANK_STATUS for fact in own)
