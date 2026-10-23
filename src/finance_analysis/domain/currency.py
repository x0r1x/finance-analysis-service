"""Валюта строки только из книги (§5.8)."""

from __future__ import annotations


def _named(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def resolve_currencies(rows: list[tuple[str, str | None]]) -> list[tuple[str | None, str | None]]:
    """`(kind, hints.currency)` → `(currency, currency_source)`.

    Источник `hints` — валюта, которую builder уже положил в `hints.currency`.
    Если среди строк `kind: fact` названа ровно одна валюта, строки без валюты
    получают её с источником `book_single`. Несколько валют или ни одной —
    такая строка остаётся без валюты.
    """

    named = {_named(currency) for kind, currency in rows if kind == "fact"}
    named.discard(None)
    single = next(iter(named)) if len(named) == 1 else None
    resolved: list[tuple[str | None, str | None]] = []
    for _kind, currency in rows:
        own = _named(currency)
        if own is not None:
            resolved.append((own, "hints"))
        elif single is not None:
            resolved.append((single, "book_single"))
        else:
            resolved.append((None, None))
    return resolved
