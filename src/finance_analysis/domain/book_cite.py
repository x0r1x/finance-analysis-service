"""Цитата строк книги для уверенного типа. Значение берётся из книги и не пересчитывается.

Как у строки срока окупаемости: отдельной формулы нет, строка не входит в матрицу
коэффициентов и не создаёт вопрос. Список пуст, пока основной тип не из среза.
`lbo_ma` сюда не входит.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from finance_analysis.domain.glossary import label_surface

# Пустое, ошибочное и отсутствующее значение не являются числом ячейки.
_NOT_A_NUMBER = frozenset({"empty", "not_applicable", "error", "missing"})
_BOUND = frozenset({"bound", "bound_with_warning"})
_HUMAN = frozenset({"confirmed", "profile"})

# Порядок понятий — как в утверждённых абзацах к решениям 37 и 38.
CITED_BY_TYPE = {
    "bank_leasing": ("lease_interest_income", "npl_share", "provision_coverage"),
    "dcf_valuation": ("wacc", "terminal_value", "enterprise_value", "equity_value"),
    "renewables_dpm": ("degradation", "energy_generation", "energy_tariff"),
    "real_estate_income": ("cap_rate", "noi", "vacancy"),
    "development_escrow": ("escrow_inflow", "escrow_disclosure", "effective_rate"),
}

# Полная подпись типа. Более короткая метка сюда не попадает и победителем не становится.
PREFERRED_LABEL = {
    "real_estate_income": {
        "noi": "Year 1 net operating income",
        "vacancy": "Year 1 vacancy",
    }
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
        status, row = _unique_row(concept, bindings, source, absent, primary)
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
    primary: str | None,
) -> tuple[str, dict | None]:
    """Одна основная строка. Несколько основных не схлопываются в последнюю.

    Предпочтительная подпись типа забирает свою строку целиком, даже если каскад
    оставил основной другой ряд. Без такой подписи выбор не делается.
    """

    preferred = _preferred_rows(concept, bindings, type_source, absent, primary)
    if preferred:
        if len(preferred) == 1:
            return "cited", preferred[0]
        return "ambiguous", None
    rows = [
        row
        for row in bindings
        if _citable(row, concept, type_source, absent, primary_only=True)
    ]
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


def _preferred_rows(
    concept: str,
    bindings: list[dict],
    type_source: str,
    absent: frozenset[str],
    primary: str | None,
) -> list[dict] | None:
    """Строки с полной предпочтительной подписью. `None` — правила для понятия нет.

    Человеческая основная строка это правило не перекрывает. Пустой список значит,
    что подпись в книге не встретилась и дальше работает обычный выбор одной строки.
    """

    text = PREFERRED_LABEL.get(primary or "", {}).get(concept)
    if not text:
        return None
    primaries = [
        row
        for row in bindings
        if _citable(row, concept, type_source, absent, primary_only=True)
    ]
    if any(row.get("source") in _HUMAN for row in primaries):
        return None
    wanted = label_surface(text)
    found: dict[str, dict] = {}
    for row in bindings:
        if not _citable(row, concept, type_source, absent, primary_only=False):
            continue
        label = row.get("matched_label_id")
        if not isinstance(label, str) or label_surface(label) != wanted:
            continue
        found.setdefault(str(row.get("row_key") or ""), row)
    return list(found.values())


def _citable(
    row: dict,
    concept: str,
    type_source: str,
    absent: frozenset[str],
    *,
    primary_only: bool,
) -> bool:
    if row.get("effective_concept") != concept:
        return False
    if primary_only and not row.get("is_primary"):
        return False
    status = row.get("status")
    allowed = _BOUND if primary_only else _BOUND | {"ambiguous"}
    if status not in allowed:
        return False
    if concept in absent and row.get("source") not in _HUMAN:
        return False
    return type_source not in _HUMAN or row.get("source") in _HUMAN


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
        normalized = _decimal_text(fact.get("normalized_value"))
        if normalized is not None:
            observed["normalized_value"] = normalized
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
        value = Decimal(str(number))
    except (InvalidOperation, ValueError):
        return None
    if not value.is_finite():
        return None
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text
