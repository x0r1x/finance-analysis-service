"""LF опираются на арифметику и граф, а не на лексическое совпадение той же метки (§5.11.1)."""

from __future__ import annotations

from decimal import Decimal

from finance_analysis.domain.signals import LabelingInput, Vote

HUMAN = frozenset({"confirmed", "profile"})
AGREE_SHARE = Decimal("0.8")
ABS_TOL = Decimal("0.005")
REL_TOL = Decimal("0.005")


def _close(left: Decimal, right: Decimal) -> bool:
    return abs(left - right) <= max(ABS_TOL, abs(right) * REL_TOL)


def _agree(pairs: list[tuple[Decimal, Decimal]]) -> bool:
    if len(pairs) < 2:
        return False
    hits = sum(1 for left, right in pairs if _close(left, right))
    return Decimal(hits) / Decimal(len(pairs)) >= AGREE_SHARE


def _key_of(data: LabelingInput) -> dict[str, str]:
    return {row["row_key"]: row["binding_key"] for row in data.rows}


def ratio_numerator(data: LabelingInput) -> list[Vote]:
    """Прецедент строки dscr, для которого row / debt_service ≈ dscr по ≥ 80 % тестовых периодов → cfads."""

    dscr = data.bound("dscr")
    ds = data.bound("debt_service")
    if not dscr or not ds:
        return []
    keys = _key_of(data)
    ratio = data.values.get(dscr, {})
    service = data.values.get(ds, {})
    votes = []
    for row_key in sorted(data.precedents.get(dscr, set()) - {ds, dscr}):
        series = data.values.get(row_key, {})
        pairs = []
        for period, value in series.items():
            denominator = service.get(period)
            target = ratio.get(period)
            if denominator in (None, Decimal(0)) or target is None:
                continue
            pairs.append((value / abs(denominator), abs(target)))
        if _agree(pairs) and row_key in keys:
            votes.append(Vote(keys[row_key], "cfads", "+", "lf.ratio_numerator"))
    return votes


def _identity_parts(data: LabelingInput) -> dict[str, tuple[str, ...]]:
    """Части lf.identity. Их задаёт связь, которой реестр разрешил сверку.

    Сейчас это composed_of. related_to и другая смысловая связь части не задаёт
    и понятие не подменяет. Список тождеств добавляет понятие без такой связи.
    Расхождение списка со связью не подменяет связь: голос читает связь.
    Сумма в метрику отсюда не попадает.
    """

    found = {}
    for concept in data.concepts.values():
        parts = concept.targets_for("reconciliation")
        if parts:
            found[concept.id] = parts
    for left, parts in data.identities.items():
        if left not in found:
            found[left] = tuple(parts)
    return found


def _row(data: LabelingInput, row_key: str) -> dict | None:
    for row in data.rows:
        if row.get("row_key") == row_key:
            return row
    return None


def _explicit_currency(row: dict) -> str | None:
    raw = row.get("currency")
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    return text.casefold() if text else None


def _unit_spec(data: LabelingInput, row: dict):
    token = row.get("unit")
    if not isinstance(token, str) or not token:
        return None
    return data.units.get(token)


def _known_currency(data: LabelingInput, row_key: str) -> str | None:
    """Валюта строки. Пустое поле берётся из денежной единицы каталога.

    Неизвестная единица валюту не получает. Явная валюта, которая не совпала
    с валютой единицы, тоже не считается известной: сверка воздерживается.
    """

    row = _row(data, row_key)
    if row is None:
        return None
    explicit = _explicit_currency(row)
    spec = _unit_spec(data, row)
    catalog = None
    if spec is not None and isinstance(spec.currency, str) and spec.currency.strip():
        catalog = spec.currency.strip().casefold()
    if explicit and catalog and explicit != catalog:
        return None
    return explicit or catalog


def _one_currency(data: LabelingInput, row_keys: list[str]) -> bool:
    """Итог и части в одной известной валюте. Иначе сверка воздерживается."""

    found = [_known_currency(data, key) for key in row_keys]
    if any(item is None for item in found):
        return False
    return len(set(found)) == 1


def _scales_match(data: LabelingInput, row_keys: list[str]) -> bool:
    """Разный масштаб каталога при одной валюте не даёт сверить числа как есть.

    Ряд LF — одно число. Это может быть уже базовая величина, а может быть
    число на листе. Второй раз умножать на scale нельзя, а равные числа
    в тысячах и в рублях — ложный «за». Сверка воздерживается.
    """

    found: list[int] = []
    for key in row_keys:
        row = _row(data, key)
        spec = _unit_spec(data, row or {})
        if spec is None:
            continue
        found.append(spec.scale)
    return len(set(found)) <= 1


def identity(data: LabelingInput) -> list[Vote]:
    """Строка по формуле и значениям равна сумме привязанных людьми слагаемых → голос за левую часть.

    Голос только если у итога и всех частей одна известная валюта и один масштаб
    каталога. Валюта строки — явное поле, иначе валюта её денежной единицы.
    Разные валюты, расхождение явной валюты с единицей, разный масштаб и
    неизвестная валюта — воздержание, не голос «против».
    """

    keys = _key_of(data)
    votes = []
    for left, parts in sorted(_identity_parts(data).items()):
        rows = [data.bound(part, sources=HUMAN) for part in parts]
        if not all(rows):
            continue
        for row_key in sorted(data.values):
            if row_key in rows or row_key not in keys:
                continue
            if not set(rows) <= data.precedents.get(row_key, set()):
                continue
            watched = [row_key, *rows]
            if not _one_currency(data, watched) or not _scales_match(data, watched):
                continue
            series = data.values[row_key]
            pairs = []
            for period, value in series.items():
                items = [data.values.get(part, {}).get(period) for part in rows]
                if any(item is None for item in items) or value == 0:
                    continue
                pairs.append((abs(value), abs(sum(items, Decimal(0)))))
            if _agree(pairs):
                votes.append(Vote(keys[row_key], left, "+", "lf.identity"))
    return votes


def rollforward(data: LabelingInput) -> list[Vote]:
    """Корпус close[t] = close[t−1] + приток[t] − |principal[t]| по ≥ 80 % пар периодов → остаток долга.

    Притоки — прочие прецеденты строки. Если тождество не сходится по числам, LF воздерживается.
    """

    principal = data.bound("principal", sources=HUMAN)
    if not principal:
        return []
    keys = _key_of(data)
    repaid = data.values.get(principal, {})
    votes = []
    for row_key, refs in sorted(data.precedents.items()):
        if row_key == principal or principal not in refs or row_key not in refs or row_key not in keys:
            continue
        balance = data.values.get(row_key, {})
        others = sorted(refs - {row_key, principal})
        pairs = []
        for before, now in data.consecutive(balance):
            if now not in repaid or any(now not in data.values.get(other, {}) for other in others):
                continue
            inflow = sum((data.values[other][now] for other in others), Decimal(0))
            pairs.append((balance[now], balance[before] + inflow - abs(repaid[now])))
        if _agree(pairs):
            votes.append(Vote(keys[row_key], "debt_outstanding", "+", "lf.rollforward"))
    return votes


def sum_component(data: LabelingInput) -> list[Vote]:
    """Слагаемое итога, привязанного к debt_service → «компонент DS» (кандидат narrower, не синоним).

    Голос требует связь, которой реестр разрешил сверку. Сейчас это composed_of.
    Смысловая связь голос не открывает. Список целей ряд не отбирает и не суммирует:
    в голос попадают прецеденты строки итога.
    """

    ds = data.bound("debt_service")
    concept = data.concepts.get("debt_service")
    if not ds or concept is None or not concept.targets_for("reconciliation"):
        return []
    keys = _key_of(data)
    return [
        Vote(keys[row_key], "debt_service", "+", "lf.sum_component")
        for row_key in sorted(data.precedents.get(ds, set()))
        if row_key in keys and row_key != ds
    ]


def unit_sign(data: LabelingInput) -> list[Vote]:
    """Только «против»: единица или знак строки противоречат понятию привязки."""

    rows = {row["binding_key"]: row for row in data.rows}
    votes = []
    for key, binding in sorted(data.bindings.items()):
        concept = data.concepts.get(binding.get("effective_concept") or "")
        row = rows.get(key)
        if concept is None or row is None or binding.get("source") in HUMAN:
            continue
        unit = str(row.get("unit") or "").lower()
        money_vs_rate = concept.unit == "money" and unit in {"%", "percent", "rate", "ratio", "x"}
        rate_vs_money = concept.unit == "ratio" and unit in {"money", "price"}
        sign = row.get("sign")
        wrong_sign = concept.expected_sign in {"inflow", "outflow"} and sign in {"inflow", "outflow"} and sign != concept.expected_sign
        if money_vs_rate or rate_vs_money or wrong_sign:
            votes.append(Vote(key, concept.id, "-", "lf.unit_sign"))
    return votes


LABELING_FUNCTIONS = (ratio_numerator, identity, rollforward, sum_component, unit_sign)


def run_all(data: LabelingInput) -> list[Vote]:
    votes: list[Vote] = []
    for function in LABELING_FUNCTIONS:
        votes.extend(function(data))
    return votes
