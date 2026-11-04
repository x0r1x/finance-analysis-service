"""ADSCR, min/avg DSCR, LLCR и PLCR (§5.7). Окна и NPV — Python `Decimal`.

Входы — только ячейки книги (§0 п. 2): ставка дисконтирования — привязанная
ячейка `discount_rate`, остаток — `debt_outstanding`. Неполные периоды FAS
не корректирует: окно ADSCR, которое не покрывается периодами книги целиком,
не считается (`not_computed`), а не досчитывается по долям.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, localcontext
from itertools import pairwise

from finance_analysis.domain.coverage import is_coverage_test_period
from finance_analysis.domain.metrics import (
    RATIO,
    _axes_of,
    _groups,
    _payment,
    _primaries,
    _sums,
    absent_concepts,
    aligned_keys,
    coverage_ratio,
    quantize_ratio,
)
from finance_analysis.domain.period_basis import keys_for_basis

# Длина периода по `grain` оси builder. Неизвестный grain — длина неизвестна.
GRAIN_MONTHS = {"year": 12, "model_year": 12, "half": 6, "half_year": 6, "quarter": 3, "month": 1}
WINDOW_MONTHS = 12
DAYS_IN_YEAR = Decimal(365)
LOAN_LIFE = ("llcr", "plcr")
WINDOWED = ("adscr",)
REDUCED = ("dscr_min", "dscr_avg")
BASES = ("period_end", "period_start")
_DSCR_FAMILY = ("dscr", "adscr", "dscr_min", "dscr_avg", "llcr", "plcr")
# Понятие → метрики каталога, которым оно нужно (`needed_by` вопроса, §5.10.5).
METRIC_INPUTS = {
    "cfads": _DSCR_FAMILY,
    "debt_service": _DSCR_FAMILY,
    "interest": ("icr",),
    "debt_outstanding": LOAN_LIFE,
    "discount_rate": LOAN_LIFE,
}
DIRECTIONS = ("lookback", "lookforward")
# `validation_range` понятия `discount_rate` в `configs/concepts/core.yaml`: доля, не проценты.
RATE_RANGE = (Decimal(0), Decimal("0.30"))


def add_months(day: date, months: int) -> date:
    """Тот же день через `months` месяцев; конец месяца остаётся концом."""

    month0 = day.month - 1 + months
    year, month = day.year + month0 // 12, month0 % 12 + 1
    last = _month_last(year, month)
    return date(year, month, min(day.day, last))


def _month_last(year: int, month: int) -> int:
    following = date(year + month // 12, month % 12 + 1, 1)
    return (following - timedelta(days=1)).day


def grain_months(grain: str | None) -> int | None:
    return GRAIN_MONTHS.get(str(grain or "").lower())


def _ctx(ctx) -> None:
    ctx.prec = 38
    ctx.rounding = "ROUND_HALF_EVEN"


def _dated(period: dict) -> bool:
    return period.get("period_start") is not None and period.get("period_end") is not None


def _as_date(value) -> date | None:
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _ordered(periods: list[dict], axis: str) -> list[dict]:
    found = [
        {**period, "period_start": _as_date(period.get("period_start")), "period_end": _as_date(period.get("period_end"))}
        for period in periods
        if period["axis_id"] == axis
    ]
    return sorted(found, key=lambda item: int(item.get("period_index") or 0))


def _result(metric: str, rows: list[dict], *, needs=None, warnings=None, status="succeeded") -> dict:
    return {"metric": metric, "rows": rows, "needs_input": needs or [], "warnings": warnings or [], "status": status}


def _row(metric: str, period: dict | None, value, status: str, reason: str | None, **extra) -> dict:
    return {
        "metric": metric,
        "axis_id": None if period is None else period["axis_id"],
        "period_id": None if period is None else period["period_id"],
        "period_key_base": None if period is None else period.get("period_key_base"),
        "period_marker": None if period is None else period.get("period_marker"),
        "value": value,
        "status": status,
        "reason": reason,
        **extra,
    }


def _ratio(num: Decimal, den: Decimal) -> Decimal:
    with localcontext() as ctx:
        _ctx(ctx)
        return quantize_ratio(num / den)


def _missing(metric: str, bindings: list[dict], needed: tuple[str, ...], absent: frozenset[str]) -> dict | None:
    """Первое недостающее или неоднозначное понятие → вопрос пакета (§5.10.5)."""

    primaries = _primaries(bindings, absent)
    ambiguous = [name for name, rows in _groups(bindings).items() if len(rows) > 1 and name in needed]
    if not ambiguous:
        ambiguous = [
            row.get("effective_concept")
            for row in bindings
            if row.get("status") == "ambiguous" and row.get("effective_concept") in needed
        ]
    if ambiguous:
        return _result(
            metric, [], needs=[{"kind": "concept", "reason": "ambiguous", "subject": ambiguous[0]}], status="needs_input"
        )
    marked = absent_concepts(bindings, absent)
    for name in needed:
        if name not in primaries:
            reason = "absent_in_book" if name in marked else "concept_unknown"
            return _result(
                metric, [], needs=[{"kind": "concept", "reason": reason, "subject": name}], status="missing_input"
            )
    return None


def adscr(
    *,
    facts: list[dict],
    bindings: list[dict],
    periods: list[dict],
    period_phase: dict,
    explicit_phases: bool,
    sign_convention: str = "outflow_negative",
    marker_class: str | None = None,
    direction: str = "lookback",
    absent: frozenset[str] = frozenset(),
) -> dict:
    """Сумма CFADS ÷ сумма обслуживания долга за 12 месяцев на каждом тестовом периоде.

    Отдаётся только при известном `grain` короче года (§5.7); пустой или
    годовой `grain` — `adscr_not_applicable`. Окно собирается из целых
    периодов книги по датам; окно, которое периоды покрывают не целиком,
    не считается.
    """

    dscr = coverage_ratio(
        metric="dscr",
        facts=facts,
        bindings=bindings,
        periods=periods,
        period_phase=period_phase,
        explicit_phases=explicit_phases,
        sign_convention=sign_convention,
        marker_class=marker_class,
        absent=absent,
    )
    if dscr["status"] != "succeeded":
        return {**dscr, "metric": "adscr"}
    primaries = _primaries(bindings, absent)
    aligned = aligned_keys(periods)
    cfads = _sums(facts, primaries["cfads"], aligned, periods)
    debt = _sums(facts, primaries["debt_service"], aligned, periods)
    rows: list[dict] = []
    warnings = list(dscr["warnings"])
    for axis in sorted(_axes_of(facts, primaries["debt_service"])):
        ordered = _ordered(periods, axis)
        months = grain_months(ordered[0].get("grain") if ordered else None)
        if months is None or months >= WINDOW_MONTHS:
            warnings.append({"code": "adscr_not_applicable", "params": {"axis_id": axis, "grain": ordered[0].get("grain")}})
            continue
        tested = {(row["axis_id"], row["period_id"]) for row in dscr["rows"] if row["status"] == "computed"}
        for period in ordered:
            if (axis, period["period_id"]) not in tested:
                continue
            if not _dated(period):
                rows.append(_row("adscr", period, None, "missing_input", "no_period_dates", direction=direction))
                continue
            window = _window(ordered, period, direction)
            if window is None:
                rows.append(_row("adscr", period, None, "not_computed", "partial_window", direction=direction))
                continue
            keys = [aligned.get((axis, item["period_id"]), (axis, item["period_id"])) for item in window]
            earned_keys = keys_for_basis(keys, primaries["cfads"])
            paid_keys = keys_for_basis(keys, primaries["debt_service"])
            if any(key not in cfads for key in earned_keys) or any(key not in debt for key in paid_keys):
                rows.append(_row("adscr", period, None, "missing_input", "no_binding", direction=direction))
                continue
            with localcontext() as ctx:
                _ctx(ctx)
                paid = sum((_payment(debt[key], sign_convention) for key in paid_keys), Decimal(0))
                earned = sum((cfads[key] for key in earned_keys), Decimal(0))
            if paid == 0:
                rows.append(_row("adscr", period, None, "no_debt_service", "zero_denominator", direction=direction))
                continue
            rows.append(
                _row(
                    "adscr",
                    period,
                    _ratio(earned, paid),
                    "computed",
                    None,
                    direction=direction,
                    window=[item["period_id"] for item in window],
                )
            )
    return _result("adscr", rows, warnings=warnings)


def _window(ordered: list[dict], period: dict, direction: str) -> list[dict] | None:
    if direction == "lookforward":
        start = period["period_start"]
        stop = add_months(start, WINDOW_MONTHS) - timedelta(days=1)
    else:
        stop = period["period_end"]
        start = add_months(stop + timedelta(days=1), -WINDOW_MONTHS)
    window = [item for item in ordered if _dated(item) and item["period_start"] >= start and item["period_end"] <= stop]
    if not window or window[0]["period_start"] != start or window[-1]["period_end"] != stop:
        return None
    for before, after in pairwise(window):
        if before["period_end"] + timedelta(days=1) != after["period_start"]:
            return None
    return window


def dscr_reductions(
    metric: str,
    *,
    facts: list[dict],
    bindings: list[dict],
    periods: list[dict],
    period_phase: dict,
    explicit_phases: bool,
    sign_convention: str = "outflow_negative",
    marker_class: str | None = None,
    absent: frozenset[str] = frozenset(),
) -> dict:
    """`dscr_min` — минимум по тестовым периодам; `dscr_avg` — двумя способами.

    Среднее отдаётся как среднее отношений (`mean_of_ratios`) и как отношение
    сумм (`ratio_of_sums`), с явным названием варианта (§5.7). Строка `ltm`
    в отношение сумм входит один раз, на последний тестовый период.
    """

    dscr = coverage_ratio(
        metric="dscr",
        facts=facts,
        bindings=bindings,
        periods=periods,
        period_phase=period_phase,
        explicit_phases=explicit_phases,
        sign_convention=sign_convention,
        marker_class=marker_class,
        absent=absent,
    )
    if dscr["status"] != "succeeded":
        return {**dscr, "metric": metric}
    primaries = _primaries(bindings, absent)
    aligned = aligned_keys(periods)
    cfads = _sums(facts, primaries["cfads"], aligned, periods)
    debt = _sums(facts, primaries["debt_service"], aligned, periods)
    by_axis: dict[str, list[dict]] = {}
    for row in dscr["rows"]:
        if row["status"] == "computed":
            by_axis.setdefault(row["axis_id"], []).append(row)
    rows = []
    for axis, computed in sorted(by_axis.items()):
        tested = [period["period_id"] for period in computed]
        if metric == "dscr_min":
            lowest = min(computed, key=lambda item: item["value"])
            rows.append({**lowest, "metric": metric, "over": tested})
            continue
        with localcontext() as ctx:
            _ctx(ctx)
            mean = quantize_ratio(sum((row["value"] for row in computed), Decimal(0)) / len(computed))
            keys = [aligned.get((axis, pid), (axis, pid)) for pid in tested]
            earned_keys = keys_for_basis(keys, primaries["cfads"])
            paid_keys = keys_for_basis(keys, primaries["debt_service"])
            paid = sum((_payment(debt[key], sign_convention) for key in paid_keys), Decimal(0))
            earned = sum((cfads[key] for key in earned_keys), Decimal(0))
        base = {"axis_id": axis, "period_id": None}
        rows.append(_row(metric, base, mean, "computed", None, variant="mean_of_ratios", over=tested))
        rows.append(_row(metric, base, _ratio(earned, paid), "computed", None, variant="ratio_of_sums", over=tested))
    return _result(metric, rows, warnings=dscr["warnings"])


def loan_life_ratio(
    metric: str,
    *,
    facts: list[dict],
    bindings: list[dict],
    periods: list[dict],
    period_phase: dict,
    explicit_phases: bool,
    sign_convention: str = "outflow_negative",
    marker_class: str | None = None,
    basis: str = "period_end",
    absent: frozenset[str] = frozenset(),
) -> dict:
    """LLCR и PLCR: NPV CFADS ÷ остаток долга на каждом тестовом периоде.

    `basis = period_end`: CFADS со следующего периода, остаток — привязанная
    строка в этом периоде (закрывающий), дата оценки — конец периода.
    `basis = period_start`: CFADS с текущего периода, привязанная строка
    читается как открывающий остаток, дата оценки — день до начала периода.
    LLCR обрезает CFADS последним периодом обслуживания долга и в нём не
    считается; PLCR берёт CFADS до конца шкалы. Дисконт — по фактическим
    долям периода (дни ÷ 365) с периодной ставкой, если строка ставки
    меняется по периодам; без дат — по длине `grain` с предупреждением.
    """

    needed = ("debt_service", "cfads", "debt_outstanding", "discount_rate")
    missing = _missing(metric, bindings, needed, absent)
    if missing is not None:
        return missing
    primaries = _primaries(bindings, absent)
    aligned = aligned_keys(periods)
    cfads = _sums(facts, primaries["cfads"], aligned, periods)
    debt = _sums(facts, primaries["debt_service"], aligned, periods)
    balance = _sums(facts, primaries["debt_outstanding"], aligned, periods)
    rate_by_key = _sums(facts, primaries["discount_rate"], aligned, periods)
    rates = sorted(set(rate_by_key.values()))
    warnings: list[dict] = []
    rows: list[dict] = []
    for axis in sorted(_axes_of(facts, primaries["debt_service"])):
        ordered = _ordered(periods, axis)
        keyed = [(period, aligned.get((axis, period["period_id"]), (axis, period["period_id"]))) for period in ordered]
        paying = [index for index, (_period, key) in enumerate(keyed) if _payment(debt.get(key, Decimal(0)), sign_convention) != 0]
        if not paying:
            continue
        final = paying[-1]
        fractions = _fractions([period for period, _key in keyed])
        if fractions is None:
            warnings.append({"code": "npv_period_dates_missing", "params": {"axis_id": axis}})
        elif any(not _dated(period) for period, _key in keyed):
            warnings.append({"code": "npv_by_grain", "params": {"axis_id": axis, "grain": ordered[0].get("grain")}})
        for index, (period, key) in enumerate(keyed):
            payment = _payment(debt.get(key, Decimal(0)), sign_convention)
            phase = period_phase.get((axis, period["period_id"]))
            if phase is None:
                phase = period_phase.get((axis, period.get("period_key_base") or period["period_id"]))
            marker = period.get("marker_class")
            if marker_class and marker and marker != marker_class:
                continue
            if not is_coverage_test_period(debt_service_nonzero=payment != 0, phase=phase, explicit_phases=explicit_phases):
                continue
            if metric == "llcr" and index == final:
                rows.append(_row(metric, period, None, "not_computed", "final_debt_service_period"))
                continue
            if fractions is None:
                rows.append(_row(metric, period, None, "missing_input", "no_period_dates"))
                continue
            owed = balance.get(key)
            if owed is None:
                rows.append(_row(metric, period, None, "missing_input", "no_binding"))
                continue
            if owed <= 0:
                reason = "zero_balance" if owed == 0 else "negative_balance"
                rows.append(_row(metric, period, None, "not_computed", reason))
                continue
            first = index + 1 if basis == "period_end" else index
            last = final if metric == "llcr" else len(keyed) - 1
            npv, used, error = _npv(keyed[first : last + 1], fractions[first : last + 1], cfads, rate_by_key, rates, key)
            if error:
                rows.append(_row(metric, period, None, "missing_input", error))
                continue
            if metric == "llcr":
                # §5.7: в числителе LLCR ещё DSRA без дисконта; понятия `dsra_balance` пока нет.
                warnings.append({"code": "dsra_not_included", "params": {"axis_id": axis, "period_id": period["period_id"]}})
            rows.append(
                _row(
                    metric,
                    period,
                    _ratio(npv, owed),
                    "computed",
                    None,
                    basis=basis,
                    window=[item["period_id"] for item, _key in keyed[first : last + 1]],
                    inputs={"npv_cfads": str(npv.quantize(Decimal("0.000001"))), "debt_outstanding": str(owed), "periods": used},
                )
            )
    return _result(metric, rows, warnings=warnings)


def _fractions(ordered: list[dict]) -> list[Decimal] | None:
    """Доля года каждого периода: по датам, иначе по `grain`; ни того ни другого — None."""

    found = []
    for period in ordered:
        if _dated(period):
            days = (period["period_end"] - period["period_start"]).days + 1
            found.append(Decimal(days) / DAYS_IN_YEAR)
            continue
        months = grain_months(period.get("grain"))
        if months is None:
            return None
        found.append(Decimal(months) / Decimal(12))
    return found


def _npv(window, fractions, cfads, rate_by_key, rates, valuation_key) -> tuple[Decimal, int, str | None]:
    """NPV CFADS окна на дату оценки; дисконт накапливается по периодам.

    Период окна без CFADS — `no_binding`, как у DSCR: ноль вместо факта не
    подставляется. Ставка вне `RATE_RANGE` — `rate_out_of_range`.
    """

    with localcontext() as ctx:
        _ctx(ctx)
        total = Decimal(0)
        factor = Decimal(1)
        used = 0
        for (period, key), fraction in zip(window, fractions, strict=True):
            rate = rate_by_key.get(key)
            if rate is None:
                rate = rate_by_key.get(valuation_key)
            if rate is None:
                if len(rates) != 1:
                    return Decimal(0), 0, "rate_not_at_period"
                rate = rates[0]
            if not RATE_RANGE[0] <= rate <= RATE_RANGE[1]:
                return Decimal(0), 0, "rate_out_of_range"
            factor = factor / (Decimal(1) + rate) ** fraction
            flow = cfads.get(key)
            if flow is None:
                return Decimal(0), 0, "no_binding"
            total += flow * factor
            used += 1
        return total, used, None


# Метрика → понятия, чьи ячейки цитируются за периоды окна строки (§5.7).
_CITED = {
    "dscr": ("cfads", "debt_service"),
    "adscr": ("cfads", "debt_service"),
    "dscr_min": ("cfads", "debt_service"),
    "dscr_avg": ("cfads", "debt_service"),
    "llcr": ("cfads",),
    "plcr": ("cfads",),
    "icr": ("interest",),
}


def ratio_cells(row: dict, facts: list[dict], bindings: list[dict], periods: list[dict], absent: frozenset[str]) -> list[dict]:
    """Факты книги, из которых посчитана строка коэффициента: окно строки и знаменатель LLCR/PLCR.

    Периоды окна — с оси обслуживания долга; факты других листов стыкуются по шкале.
    """

    if row.get("status") != "computed" or row.get("axis_id") is None:
        return []
    primaries = _primaries(bindings, absent)
    aligned = aligned_keys(periods)
    axis = row["axis_id"]
    own = row.get("window") or row.get("over") or [row["period_id"]]
    wanted = {aligned.get((axis, pid), (axis, pid)) for pid in own}
    cited = row.get("inputs") or _CITED.get(row["metric"], ())
    scoped = {name: wanted for name in cited if name in primaries}
    if row["metric"] in LOAN_LIFE and "debt_outstanding" in primaries:
        scoped["debt_outstanding"] = {aligned.get((axis, row["period_id"]), (axis, row["period_id"]))}
    by_row = {primaries[name]["row_key"]: keys for name, keys in scoped.items()}
    found = []
    for fact in facts:
        keys = by_row.get(fact.get("row_key"))
        if keys is None or not fact.get("cell_id"):
            continue
        place = (fact["axis_id"], fact["period_id"])
        if aligned.get(place, place) in keys:
            found.append(fact)
    return found


__all__ = [
    "BASES",
    "DIRECTIONS",
    "LOAN_LIFE",
    "METRIC_INPUTS",
    "RATIO",
    "REDUCED",
    "WINDOWED",
    "add_months",
    "adscr",
    "dscr_reductions",
    "grain_months",
    "loan_life_ratio",
    "ratio_cells",
]
