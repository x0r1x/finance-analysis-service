"""Валюта строки только из книги (§5.8)."""

from __future__ import annotations

# Денежная мера — только явные единицы builder. price — деньги за единицу (EUR/MWh).
# Неизвестная единица и любой другой токен (rate, ratio, %, x, count, years, date)
# деньгами не считаются: валюту книги туда не додумываем.
_MONEY_UNITS = frozenset({"money", "price"})


def _named(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _unit(value: str | None) -> str | None:
    named = _named(value)
    return named.casefold() if named is not None else None


def monetary_fact(kind: str, unit: str | None) -> bool:
    """Fact-строка с явной денежной единицей. Пустая и неденежная мера — нет."""

    return kind == "fact" and _unit(unit) in _MONEY_UNITS


def resolve_currencies(
    rows: list[tuple[str, str | None, str | None]],
) -> list[tuple[str | None, str | None]]:
    """`(kind, hints.currency, unit)` → `(currency, currency_source)`.

    `hints` сохраняется как есть. Единственная валюта среди строк `kind: fact`
    переносится только на денежные fact-строки без своей валюты (`book_single`).
    Флаги, abstract, helper, ставки, проценты, коэффициенты и строки с неизвестной
    единицей без своей валюты остаются пустыми.
    """

    named = {_named(currency) for kind, currency, _unit_name in rows if kind == "fact"}
    named.discard(None)
    single = next(iter(named)) if len(named) == 1 else None
    resolved: list[tuple[str | None, str | None]] = []
    for kind, currency, unit in rows:
        own = _named(currency)
        if own is not None:
            resolved.append((own, "hints"))
        elif single is not None and monetary_fact(kind, unit):
            resolved.append((single, "book_single"))
        else:
            resolved.append((None, None))
    return resolved
