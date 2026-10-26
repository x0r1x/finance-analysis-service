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


def identity(data: LabelingInput) -> list[Vote]:
    """Строка по формуле и значениям равна сумме привязанных людьми слагаемых → голос за левую часть."""

    keys = _key_of(data)
    votes = []
    for left, parts in sorted(data.identities.items()):
        rows = [data.bound(part, sources=HUMAN) for part in parts]
        if not all(rows):
            continue
        for row_key in sorted(data.values):
            if row_key in rows or row_key not in keys:
                continue
            if not set(rows) <= data.precedents.get(row_key, set()):
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
    """Корпус open + in − out = close по строке, ссылающейся на principal → остаток долга (closing)."""

    principal = data.bound("principal", sources=HUMAN)
    if not principal:
        return []
    keys = _key_of(data)
    votes = []
    for row_key, refs in sorted(data.precedents.items()):
        if row_key == principal or principal not in refs or row_key not in refs or row_key not in keys:
            continue
        votes.append(Vote(keys[row_key], "debt_outstanding", "+", "lf.rollforward"))
    return votes


def sum_component(data: LabelingInput) -> list[Vote]:
    """Слагаемое итога, привязанного к debt_service → «компонент DS» (кандидат narrower, не синоним)."""

    ds = data.bound("debt_service")
    if not ds:
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
