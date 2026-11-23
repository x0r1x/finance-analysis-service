"""Коэффициенты покрытия (§5.7). Частное, окна и NPV считает Decimal, не DuckDB.

Периоды строк разных осей сопоставляются через `timeline_id` + `period_index`
(§5.7, инвариант основной строки): CFADS на листе CFS и обслуживание долга на
листе Debt одной шкалы — один период. Строка результата лежит на оси
знаменателя.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, localcontext
from types import MappingProxyType
from typing import Any

from finance_analysis.domain.binding_resolution import declared_concept
from finance_analysis.domain.calculation_evidence import (
    BasisSide,
    CalculationOutcome,
    EvidenceBook,
    FactObservation,
    FactUse,
    PeriodResult,
    TransformationStep,
)
from finance_analysis.domain.mapping import marked_line_code
from finance_analysis.domain.metric_contract import BoundInputs, implements
from finance_analysis.domain.model_type import sheet_name_key
from finance_analysis.domain.period_basis import _year_of, basis_of, restate_series

MONEY = Decimal("0.000001")
RATIO = Decimal("0.0000000001")
# То же двенадцатимесячное окно, что у чистого долга к EBITDA. Привязка строки не меняется.
PARTIAL_DENOMINATOR = (
    "Окно знаменателя неполное: нет двенадцати месяцев подряд до конца периода числителя. "
    "Коэффициент не рассчитан."
)
SCALE_UNCONFIRMED = "Масштаб числителя и знаменателя не подтверждён. Коэффициент не рассчитан."
SCALE_ASSUMED = (
    "Масштаб одной стороны не подтверждён. Принято, что обе стороны выражены в единицах книги, "
    "и коэффициент рассчитан по числам на листе."
)
INTEREST_BASIS_FALLBACK = "В знаменателе взяты уплаченные проценты: строки начисленных процентов нет."
MIXED_BASIS = "Способ показа числителя и знаменателя различается. Коэффициент не рассчитан."
LEASE_OVERLAP = (
    "Строка процентов не подтверждает, что процентов по лизингу в ней нет. "
    "Добавка лизинга дала бы двойной счёт. Коэффициент не рассчитан."
)
NEGATIVE_LEASE_INTEREST = (
    "Основной долг в составе лизингового платежа больше самого платежа. Коэффициент не рассчитан."
)
OPERATING_LEASE_NUMERATOR = (
    "Расход по операционной аренде входит в операционную прибыль. "
    "Числитель EBITDA на лизинговый платёж не увеличен."
)
_BOUND = frozenset({"bound", "bound_with_warning"})
# Источники привязки от человека: только они отменяют `concept.absent` (§5.10.5).
HUMAN_SOURCES = frozenset({"confirmed", "profile"})


def quantize_ratio(value: Decimal) -> Decimal:
    with localcontext() as ctx:
        ctx.prec = 38
        ctx.rounding = "ROUND_HALF_EVEN"
        return value.quantize(RATIO)


def interest_choice(
    primaries: dict,
    order: tuple[str, ...] | list[str],
    *,
    row_fallbacks: dict | None = None,
) -> tuple[str | None, dict | None]:
    """Первое имя `interest_order`, у которого есть основная строка в primaries.

    Lookup — по id из порядка (concept или row_fallback id). Поля
    `binding_key` / `matching.rule` у fallback декларативны и сюда не входят.
    Предупреждение — когда выбраны уплаченные проценты, а строки начисления нет.
    """

    fallbacks = row_fallbacks or {}
    for name in order:
        if name not in primaries:
            continue
        canonical = None
        warn = False
        if name in fallbacks:
            canonical = getattr(fallbacks[name], "canonical", None)
            warn = canonical not in primaries
        elif name == "interest_paid":
            canonical = "interest"
            warn = "interest" not in primaries
        if warn:
            return name, {
                "code": "interest_basis_fallback",
                "params": {
                    "concept": name,
                    "canonical": canonical,
                    "fallback": name,
                    "message": INTEREST_BASIS_FALLBACK,
                },
            }
        return name, None
    return None, None


# shortcut: имена листов Outputs скопированы из sheet_roles.yaml. У привязки нет колонки листа: имя берётся из sheet, иначе из первого сегмента row_key. Поднять, когда привязка хранит лист.
_OUTPUT_SHEETS = frozenset({"outputs", "output", "итоги", "сводка"})
_PAID_INTEREST_CODE = "4123"


def confirm_paid_interest(
    primaries: dict, bindings: list[dict], absent: frozenset[str] = frozenset()
) -> dict | None:
    """Единственная строка interest с кодом 4123 занимает пустой ключ interest_paid.

    Основную interest не заменяет. Уже занятый interest_paid не переписывает.
    Ноль или несколько таких строк ничего не добавляют. Лист Outputs не доказательство.
    """

    if "interest_paid" in primaries:
        return None
    paid = [row for row in bindings if paid_interest_row(row, absent)]
    if len(paid) != 1:
        return None
    injected = {**paid[0], "effective_concept": "interest_paid", "is_primary": True}
    primaries["interest_paid"] = injected
    return injected


def paid_interest_row(row: dict, absent: frozenset[str]) -> bool:
    """Строка interest с явной подписью 4123. Основную interest эта функция не меняет."""

    if declared_concept(row) != "interest" or row.get("status") not in _BOUND:
        return False
    if "interest" in absent and row.get("source") not in HUMAN_SOURCES:
        return False
    if _output_sheet(row):
        return False
    return _stated_digits(row) == _PAID_INTEREST_CODE


def _output_sheet(row: dict) -> bool:
    sheet = row.get("sheet")
    if not isinstance(sheet, str) or not sheet.strip():
        key = row.get("row_key")
        sheet = key.split("|", 1)[0] if isinstance(key, str) and "|" in key else ""
    return bool(sheet) and sheet_name_key(str(sheet)) in _OUTPUT_SHEETS


def _stated_digits(row: dict) -> str | None:
    raw = row.get("line_code")
    if not isinstance(raw, str) or not raw:
        evidence = row.get("evidence")
        if not isinstance(evidence, dict):
            packed = row.get("evidence_json")
            if isinstance(packed, str) and packed:
                try:
                    evidence = json.loads(packed)
                except json.JSONDecodeError:
                    evidence = None
        raw = evidence.get("line_code") if isinstance(evidence, dict) else None
    code = marked_line_code(raw)
    if code is None or not code.startswith("стр. "):
        return None
    digits = code.removeprefix("стр. ")
    return digits if digits.isdigit() else None


_EBITDA_DEFINITION = frozenset({"book", "ras", "ifrs", "gaap"})
_RAS_UNPUBLISHED = (
    "Коэффициент не посчитан: выбрана EBITDA (РСБУ), а она ещё не собрана. "
    "Нужны прибыль от продаж и амортизация за тот же период. "
    "Прочие доходы и расходы входят только после удаления курсовых разниц, резервов, "
    "продажи и переоценки имущества, штрафов и других статей не обычной работы. "
    "Строка EBITDA из модели сюда не подставляется."
)
_IFRS_UNPUBLISHED = (
    "Коэффициент не посчитан: выбрана EBITDA (МСФО), а она ещё не собрана. "
    "Нужны операционная прибыль и амортизация за тот же период. "
    "Продажу активов, переоценку, курсовые разницы и участие в других организациях убирают "
    "только если они внутри этой операционной прибыли и человек их отметил. "
    "Строка EBITDA из модели сюда не подставляется."
)


def ebitda_definition_error(value) -> str | None:
    """None — значение можно сохранить. Чисел и свободной формулы нет."""

    if isinstance(value, str) and value in _EBITDA_DEFINITION:
        return None
    return "ebitda_definition: book, ras, ifrs или gaap"


def ebitda_definition(profile: dict | None) -> str:
    """Пустая пометка равна book. Чужое значение не читается как книжная строка."""

    raw = (profile or {}).get("ebitda_definition")
    if raw in (None, ""):
        return "book"
    if isinstance(raw, str) and raw in _EBITDA_DEFINITION:
        return raw
    return "invalid"


def methodology_block(
    profile: dict | None,
    bindings: list[dict],
    *,
    metric: str,
    names: tuple[str, ...] | None = None,
) -> dict | None:
    """Книжная EBITDA остаётся у пометки book. Остальные пометки эту строку не подставляют.

    EBITDA по отчётности считает только профиль icr.bank. Для прочих коэффициентов
    методика расчёта не выпускается.
    """

    kind = ebitda_definition(profile)
    if kind == "book":
        return None
    if names is not None and "ebitda" not in names and "ebit" not in names:
        return None
    # Одна фраза на ICR, чистый долг к EBITDA и корпоративный DSCR. Найденные строки её не меняют.
    del bindings
    message = _methodology_message(kind)
    return {
        "metric": metric,
        "rows": [],
        "needs_input": [],
        "missing_inputs": [],
        "warnings": [{"code": "ebitda_methodology_unpublished", "params": {"message": message}}],
        "status": "not_computed",
        "message": message,
    }


_GAAP_UNPUBLISHED = (
    "Коэффициент не посчитан: выбрана отчётность GAAP, а отдельная методика расчёта EBITDA ещё не утверждена. "
    "Методика МСФО сюда не подставляется."
)


def _methodology_message(kind: str) -> str:
    if kind == "ras":
        return _RAS_UNPUBLISHED
    if kind == "ifrs":
        return _IFRS_UNPUBLISHED
    if kind == "gaap":
        return _GAAP_UNPUBLISHED
    return "Пометка определения: book, ras, ifrs или gaap."


# Запасной знаменатель DSCR читает interest, interest_paid и principal, хотя каталог называет только cfads и debt_service.
DSCR_INPUTS = ("cfads", "debt_service", "interest", "interest_paid", "principal")
# EBITDA выше EBIT. Порядок объявления one_of этот выбор не меняет.
_NUMERATOR_RANK = ("ebitda", "ebit")


def choose_one_of(members: tuple[str, ...] | list[str], present: set[str]) -> str:
    """Член one_of, который берёт расчёт.

    Оба числителя ICR — EBITDA. Один доступный — он. Ни одного — EBITDA, если она
    в списке, иначе единственное имя. Порядок YAML сюда не входит.
    """

    pool = set(members)
    for name in _NUMERATOR_RANK:
        if name in pool and name in present:
            return name
    available = sorted(name for name in pool if name in present)
    if available:
        return available[0]
    for name in _NUMERATOR_RANK:
        if name in pool:
            return name
    return min(pool)


def dscr_denominator_plan(
    primaries: dict,
    interest_order: dict | None,
    row_fallbacks: dict | None = None,
) -> tuple[tuple[str, ...], str, tuple[str, str] | None, tuple[dict, ...]]:
    """Входы DSCR: понятия, имя знаменателя, части запаса, предупреждения.

    Нет debt_service и нет CFADS — ждём только CFADS. CFADS есть, тела нет —
    ждём CFADS и тело. Всё есть — CFADS, выбранные проценты и тело.
    """

    order = interest_order or {}
    if "debt_service" in primaries or not order.get("pf"):
        return ("cfads", "debt_service"), "debt_service", None, ()
    chosen, warning = interest_choice(primaries, order["pf"], row_fallbacks=row_fallbacks)
    if "cfads" not in primaries:
        return ("cfads",), "debt_service", None, ()
    if chosen is None:
        return ("cfads", "debt_service"), "debt_service", None, ()
    if "principal" not in primaries:
        return ("cfads", "principal"), "principal", None, ()
    warnings = (warning,) if warning else ()
    return ("cfads", chosen, "principal"), chosen, (chosen, "principal"), warnings
ICR_INPUTS = ("ebitda", "ebit", "interest", "interest_paid")
ICR_EBIT_INPUTS = ("ebit", "interest", "interest_paid")
_COVERAGE_INPUTS = {"dscr": DSCR_INPUTS, "icr": ICR_INPUTS, "icr_ebit": ICR_EBIT_INPUTS}


def _plan_rows(plan: Any, bindings: list[dict]) -> dict:
    from finance_analysis.domain.resolved_plan import bound_rows

    return bound_rows(plan, bindings)


def _plan_roles(metric: str, plan: Any) -> tuple[tuple[str, str] | None, tuple[str, ...], str, str]:
    pf = next((item for item in plan.fallbacks if item.replaced == "debt_service"), None)
    if metric == "dscr":
        if pf is not None:
            return (pf.chosen, "principal"), ("cfads", pf.chosen, "principal"), pf.chosen, "cfads"
        return None, ("cfads", "debt_service"), "debt_service", "cfads"
    one = [item.concept for item in plan.inputs if item.role == "one_of"]
    numerator = one[0] if one else ("ebit" if metric == "icr_ebit" else "ebitda")
    denominator = next((item.concept for item in plan.inputs if item.concept != numerator), "interest")
    return None, (denominator,), denominator, numerator


def _coverage_from_plan(metric: str, plan: Any, bindings: list[dict]) -> dict | None:
    if plan.status == "resolved":
        return None
    del bindings
    warnings = [item.as_dict() for item in plan.warnings]
    needs = [item.as_dict() for item in plan.needs_input]
    return {
        "metric": metric,
        "rows": [],
        "needs_input": needs,
        "missing_inputs": [item.subject for item in plan.needs_input],
        "warnings": warnings,
        "status": "needs_input" if plan.status == "needs_input" else "missing_input",
    }


_TRACE_METRICS = {"dscr", "icr", "icr_ebit"}


def _registered_version(metric: str, formula: str) -> str:
    """Версия берётся из ``@implements``. Второй карты здесь нет."""

    from finance_analysis.domain.metric_contract import REGISTRY

    return REGISTRY[(metric, formula)].implementation_version


def _step(steps: list, operation: str, refs, output, **parameters) -> None:
    steps.append(
        TransformationStep(
            step_id=len(steps) + 1,
            operation=operation,
            input_refs=tuple(refs),
            output_value=output,
            parameters=MappingProxyType(parameters),
        )
    )


def _finish(book: EvidenceBook | None, result: dict) -> CalculationOutcome:
    if book is None:
        return CalculationOutcome(result, None)
    return _seal(book, result)


def _remember(
    book: EvidenceBook | None,
    period: dict,
    status: str,
    reason: str | None,
    steps,
    value=None,
    numerator=None,
    denominator=None,
    window_periods=(),
    window_missing=(),
    missing_concepts=(),
) -> None:
    if book is None:
        return
    book.periods.append(
        PeriodResult(
            axis_id=period.get("axis_id"),
            period_id=period.get("period_id"),
            status=status,
            reason=reason,
            value=value,
            numerator=numerator,
            denominator=denominator,
            steps=tuple(steps),
            window_periods=tuple(window_periods),
            window_missing=tuple(window_missing),
            missing_concepts=tuple(missing_concepts),
        )
    )


def _seal(book: EvidenceBook, result: dict) -> CalculationOutcome:
    if book.metric not in _TRACE_METRICS:
        return CalculationOutcome(result, None)
    status = result.get("status")
    if status in {"scale_unconfirmed", "basis_mismatch", "input_absent"}:
        execution = "refused"
    elif status in {"needs_input", "missing_input", "not_computed"}:
        execution = "not_run"
    else:
        execution = "succeeded"
    if not book.periods:
        for row in result.get("rows") or []:
            book.periods.append(
                PeriodResult(
                    axis_id=row.get("axis_id"),
                    period_id=row.get("period_id"),
                    status=str(row.get("status")),
                    reason=row.get("reason"),
                    value=row.get("value"),
                    numerator=None,
                    denominator=None,
                    steps=(),
                )
            )
    return CalculationOutcome(result, book.freeze(execution, _registered_version(book.metric, book.metric)))


def _note(book: EvidenceBook | None, concept: str | None, key) -> dict | None:
    if book is None or concept is None:
        return None
    for item in book.notes or []:
        if item.get("concept") == concept and item.get("key") == key:
            return item
    return None


def _exclusion(book: EvidenceBook | None, key) -> dict | None:
    if book is None:
        return None
    for item in book.notes or []:
        if item.get("key") == key and item.get("reason") == "previous_ytd_missing":
            return item
    return None


def _uses(book: EvidenceBook | None, concept: str | None, key, aligned: dict) -> tuple:
    if book is None or concept is None:
        return ()
    found = []
    for item in book.observations or []:
        if item.concept != concept:
            continue
        own = (item.axis_id, item.period_id)
        if aligned.get(own, own) == key:
            found.append(item)
    return tuple(found)


def _restate_step(steps: list, note: dict, refs=None) -> None:
    cells = tuple(note["current_cells"]) + tuple(note["previous_cells"])
    cited = tuple(refs) if refs else tuple(f"cell:{cell}" for cell in cells)
    _step(
        steps,
        "period_restatement",
        cited,
        note["difference"],
        current_cells=note["current_cells"],
        previous_cells=note["previous_cells"],
        current_raw=note["current_raw"],
        previous_raw=note["previous_raw"],
        current_effective=note["current_effective"],
        previous_effective=note["previous_effective"],
        difference=note["difference"],
        year=note["year"],
        reset_rule=note["reset_rule"],
        reason=note["reason"],
    )


def _scale_steps(steps: list, uses) -> None:
    for item in uses:
        if item.effective_value == item.raw_value:
            continue
        ref = f"cell:{item.cell_id}" if item.cell_id else f"fact:{item.axis_id}:{item.period_id}"
        _step(
            steps,
            "scale_normalization",
            (ref,),
            item.effective_value,
            field=item.field,
            raw=item.raw_value,
        )


def _fact_ref(item) -> str:
    return f"cell:{item.cell_id}" if item.cell_id else f"fact:{item.axis_id}:{item.period_id}"


def _direct_inputs(steps, start: int, uses, source: tuple[str, ...]) -> tuple[str, ...]:
    """Шаг масштаба заменяет свою ячейку. Ячейка без шага остаётся входом."""

    changed = [_fact_ref(item) for item in uses if item.effective_value != item.raw_value]
    produced = tuple(f"step:{item.step_id}" for item in steps[start:])
    if len(produced) != len(changed):
        return produced or source
    changed_set = set(changed)
    return produced + tuple(ref for ref in source if ref not in changed_set)


def _scale_index(steps) -> dict[str, str]:
    found = {}
    for item in steps:
        if item.operation != "scale_normalization" or not item.input_refs:
            continue
        found.setdefault(item.input_refs[0], f"step:{item.step_id}")
    return found


def _rewrite(refs, scale_of: dict[str, str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(scale_of.get(ref, ref) for ref in refs))


def _scale_missing(steps, observations) -> None:
    known = _scale_index(steps)
    pending = tuple(
        item for item in observations if item.effective_value != item.raw_value and _fact_ref(item) not in known
    )
    _scale_steps(steps, pending)


def _cell_observations(book, concept, cells) -> tuple:
    if book is None or concept is None or not cells:
        return ()
    wanted = {str(cell) for cell in cells}
    found = []
    seen = set()
    for item in book.observations or []:
        if item.concept != concept or item.cell_id not in wanted or item.considered is not None:
            continue
        ref = _fact_ref(item)
        if ref in seen:
            continue
        seen.add(ref)
        found.append(item)
    return tuple(found)


def _part_terminal(steps, book, concept, key, aligned, *, before=None, after=None, rule=None) -> tuple[str, ...]:
    """Узел части: последний шаг, если значение изменилось, иначе исходные ссылки.

    Масштаб прошлого периода — свой узел в этом же графе. Чужой ``step_id`` не цитируется.
    """

    uses = _uses(book, concept, key, aligned)
    source = _origin_refs(book, concept, key)
    known = _scale_index(steps)
    pending = tuple(item for item in uses if item.effective_value != item.raw_value and _fact_ref(item) not in known)
    start = len(steps)
    _scale_steps(steps, pending)
    direct = _rewrite(_direct_inputs(steps, start, pending, source), _scale_index(steps))
    note = _note(book, concept, key)
    if note is not None and note.get("reason") is None:
        _scale_missing(steps, _cell_observations(book, concept, note.get("previous_cells")))
        previous = tuple(f"cell:{cell}" for cell in note.get("previous_cells") or ())
        cited = _rewrite((*direct, *previous), _scale_index(steps))
        _restate_step(steps, note, cited or direct)
        direct = (f"step:{steps[-1].step_id}",)
    if before is not None and after is not None and before != after:
        _step(
            steps,
            "sign_conversion",
            direct,
            after,
            before=before,
            after=after,
            rule=rule,
        )
        direct = (f"step:{steps[-1].step_id}",)
    return direct


def _bound_rows(primaries, names) -> dict:
    """Строки, которые формула имеет право прочитать. Чужое имя пропускается."""

    from finance_analysis.domain.metric_contract import UndeclaredInput

    found = {}
    for name in names:
        if not isinstance(name, str):
            continue
        try:
            if name in primaries:
                found[name] = primaries[name]
        except UndeclaredInput:
            continue
    return found


def _consider(book, facts, named: dict, periods, check: str) -> None:
    """Факты, которые отказ прочитал до ряда. Использованием это не становится."""

    if book is None or not named:
        return
    if check == "basis":
        for concept, binding in named.items():
            basis, source = basis_of(binding)
            book.basis_sides.append(BasisSide(concept, basis, source))
    policy = _scale_policy(facts, list(named.values()))
    aligned = aligned_keys(periods) if periods else {}
    for concept, binding in named.items():
        _sums(
            facts,
            binding,
            aligned,
            None,
            book=book,
            concept=concept,
            scale_policy=policy,
            considered=check,
        )


def _adopt_side(book, period, aligned, names, keys, operand: str) -> None:
    if book is None or not names:
        return
    chosen = set(keys)
    roles = {name: operand for name in names}
    slots = tuple((operand, name, chosen) for name in names)
    _adopt(book, period, aligned, slots, _cell_roles(book, roles, chosen))


def _skipped_restatement(steps, book, note, aligned) -> None:
    """Пересчёт пропущенного периода цитирует масштаб, если значение уже умножено."""

    concept = note.get("concept")
    _scale_missing(steps, _uses(book, concept, note.get("key"), aligned))
    _scale_missing(steps, _cell_observations(book, concept, note.get("previous_cells")))
    current = tuple(f"cell:{cell}" for cell in note.get("current_cells") or ())
    previous = tuple(f"cell:{cell}" for cell in note.get("previous_cells") or ())
    cited = _rewrite((*current, *previous), _scale_index(steps))
    _restate_step(steps, note, cited or None)


def _denominator_names(denominator_name, fallback_parts) -> tuple[str, ...]:
    if fallback_parts is None:
        return (denominator_name,)
    return (fallback_parts[0], "principal")


@implements("dscr", "dscr", implementation_version="dscr@1", inputs=DSCR_INPUTS)
@implements("icr", "icr", implementation_version="icr@1", inputs=ICR_INPUTS)
@implements("icr_ebit", "icr_ebit", implementation_version="icr_ebit@1", inputs=ICR_EBIT_INPUTS)
def coverage_ratio(
    *,
    metric: str,
    facts: list[dict],
    bindings: list[dict],
    periods: list[dict],
    period_phase: dict[tuple[str, str], str | None],
    explicit_phases: bool,
    sign_convention: str = "outflow_negative",
    marker_class: str | None = None,
    absent: frozenset[str] = frozenset(),
    interest_order: dict | None = None,
    row_fallbacks: dict | None = None,
    profile: dict | None = None,
    declared: tuple[str, ...] | None = None,
    plan: Any | None = None,
) -> dict:
    """`absent` — понятия с записью `concept.absent` в журнале книги (§5.10.5).

    Такое понятие не берётся из автоматической привязки, только из явного
    `concept.set` человека, который отменяет отметку. Словарь — это ``result``
    одного прохода. План этого прохода читают ``_plan_rows`` и
    ``_coverage_from_plan``.
    """

    return calculate_coverage(
        evidence=False,
        metric=metric,
        facts=facts,
        bindings=bindings,
        periods=periods,
        period_phase=period_phase,
        explicit_phases=explicit_phases,
        sign_convention=sign_convention,
        marker_class=marker_class,
        absent=absent,
        interest_order=interest_order,
        row_fallbacks=row_fallbacks,
        profile=profile,
        declared=declared,
        plan=plan,
    ).result


def calculate_coverage(
    *,
    metric: str,
    facts: list[dict],
    bindings: list[dict],
    periods: list[dict],
    period_phase: dict[tuple[str, str], str | None],
    explicit_phases: bool,
    sign_convention: str = "outflow_negative",
    marker_class: str | None = None,
    absent: frozenset[str] = frozenset(),
    interest_order: dict | None = None,
    row_fallbacks: dict | None = None,
    profile: dict | None = None,
    declared: tuple[str, ...] | None = None,
    plan: Any | None = None,
    evidence: bool = True,
) -> CalculationOutcome:
    """Единственный проход. ``result`` — прежнее тело ``coverage_ratio``.

    ``evidence=False`` не собирает книгу улики. Число от этого не меняется.
    """

    from finance_analysis.domain.coverage import is_coverage_test_period

    book = None
    if evidence:
        book = EvidenceBook(
            metric=metric,
            sign_convention=sign_convention,
            marker_class=marker_class,
            explicit_phases=explicit_phases,
            plan_content_sha256=getattr(plan, "content_sha256", None) if plan is not None else None,
        )
    if metric in {"icr", "icr_ebit"}:
        blocked = methodology_block(profile, bindings, metric=metric)
        if blocked:
            return _finish(book, blocked)
    if plan is not None:
        early = _coverage_from_plan(metric, plan, bindings)
        if early is not None:
            return _finish(book, early)
        primaries = _plan_rows(plan, bindings)
        warnings = [item.as_dict() for item in plan.warnings]
        fallback_parts, needed, denominator_name, numerator_name = _plan_roles(metric, plan)
        missing = [name for name in (*needed, numerator_name) if name not in primaries]
        ambiguous = []
    else:
        primaries = _primaries(bindings, absent)
        confirm_paid_interest(primaries, bindings, absent)
        guarded = declared if declared is not None else _COVERAGE_INPUTS.get(metric)
        if guarded:
            primaries = BoundInputs(guarded, primaries)
        order = interest_order or {}
        warnings = []
        fallback_parts = None
        if metric == "dscr":
            needed, denominator_name, fallback_parts, plan_warnings = dscr_denominator_plan(
                primaries, order, row_fallbacks
            )
            warnings.extend(plan_warnings)
        elif metric in {"icr", "icr_ebit"}:
            slot = "icr_ebit" if metric == "icr_ebit" else "icr"
            chosen, warning = interest_choice(
                primaries, order.get(slot, ("interest",)), row_fallbacks=row_fallbacks
            )
            needed = (chosen or "interest",)
            denominator_name = chosen or "interest"
            if warning:
                warnings.append(warning)
        else:
            return _finish(
                book,
                {"metric": metric, "rows": [], "needs_input": [], "warnings": [], "status": "missing_input"},
            )
        missing = [name for name in needed if name not in primaries]
        numerator_name = None
        if metric == "icr_ebit":
            numerator_name = choose_one_of(("ebit",), {name for name in ("ebit",) if name in primaries})
            if numerator_name not in primaries:
                missing.append(numerator_name)
        elif metric == "icr":
            present = {name for name in ("ebitda", "ebit") if name in primaries}
            numerator_name = choose_one_of(("ebitda", "ebit"), present)
            if numerator_name == "ebitda" and "ebit" in present:
                warnings.append({"code": "icr_numerator", "params": {"concept": "ebitda"}})
            elif numerator_name not in present:
                missing.append(numerator_name)
        else:
            numerator_name = "cfads"
        watched = set(needed) | {"ebitda", "ebit"}
        ambiguous = [name for name, rows in _groups(bindings).items() if len(rows) > 1 and name in watched]
        if not ambiguous:
            ambiguous = [
                declared_concept(row)
                for row in bindings
                if row.get("status") == "ambiguous" and declared_concept(row) in watched
            ]
    if ambiguous:
        if book is not None:
            _consider(book, facts, _bound_rows(primaries, watched), periods, "input")
        return _finish(
            book,
            {
                "metric": metric,
                "rows": [],
                "needs_input": [{"kind": "concept", "reason": "ambiguous", "subject": ambiguous[0]}],
                "missing_inputs": missing or [ambiguous[0]],
                "warnings": warnings,
                "status": "needs_input",
            },
        )
    if missing:
        subject = missing[0]
        reason = "absent_in_book" if subject in absent_concepts(bindings, absent) else "concept_unknown"
        if book is not None:
            _consider(book, facts, _bound_rows(primaries, (*needed, numerator_name)), periods, "input")
        return _finish(
            book,
            {
                "metric": metric,
                "rows": [],
                "needs_input": [{"kind": "concept", "reason": reason, "subject": subject}],
                "missing_inputs": list(missing),
                "warnings": warnings,
                "status": "missing_input",
            },
        )
    numerator_basis = _flow_basis(primaries[numerator_name])
    denominator_basis = _flow_basis(primaries[denominator_name])
    named = {numerator_name: primaries[numerator_name], denominator_name: primaries[denominator_name]}
    if fallback_parts is not None:
        named["principal"] = primaries["principal"]
    if unconfirmed_scale(facts, list(named.values())):
        components, scales = _scale_bundle(facts, named)
        _consider(book, facts, named, periods, "scale")
        return _finish(
            book,
            _explained(
                metric,
                periods,
                "scale_unconfirmed",
                SCALE_UNCONFIRMED,
                warnings,
                home=_home_period(facts, primaries[numerator_name], periods),
                components=components,
                scales=scales,
            ),
        )
    if fallback_parts is not None and _flow_basis(primaries["principal"]) != denominator_basis:
        _consider(book, facts, named, periods, "basis")
        return _finish(book, _explained(metric, periods, "basis_mismatch", MIXED_BASIS, warnings))
    if numerator_basis != denominator_basis and not (numerator_basis == "ltm" and denominator_basis == "period"):
        message = MIXED_BASIS
        if metric in {"icr", "icr_ebit"}:
            message = _basis_message(numerator_name, primaries[numerator_name], primaries[denominator_name]) or MIXED_BASIS
        _consider(book, facts, named, periods, "basis")
        return _finish(book, _explained(metric, periods, "basis_mismatch", message, warnings))
    sheet = _assume_sheet_units(facts, list(named.values()), warnings)
    scale_policy = "sheet" if sheet else _scale_policy(facts, list(named.values()))
    if book is not None:
        book.sheet = sheet
    if numerator_basis == "ltm" and denominator_basis == "period":
        extra = []
        if fallback_parts is not None:
            extra.append(primaries["principal"])
        return _finish(
            book,
            _ltm_numerator(
                metric,
                facts,
                primaries[numerator_name],
                primaries[denominator_name],
                periods,
                warnings,
                sign_convention,
                period_phase=period_phase,
                explicit_phases=explicit_phases,
                marker_class=marker_class,
                sheet=sheet,
                extra_denominators=extra,
                book=book,
                numerator_name=numerator_name,
                denominator_name=denominator_name,
                scale_policy=scale_policy,
            ),
        )
    aligned = aligned_keys(periods)
    numerator = _sums(
        facts,
        primaries[numerator_name],
        aligned,
        periods,
        sheet=sheet,
        book=book,
        concept=numerator_name,
        scale_policy=scale_policy,
    )
    if fallback_parts is None:
        denominator = _sums(
            facts,
            primaries[denominator_name],
            aligned,
            periods,
            sheet=sheet,
            book=book,
            concept=denominator_name,
            scale_policy=scale_policy,
        )
        home = _axes_of(facts, primaries[denominator_name])
    else:
        paid = _sums(
            facts,
            primaries[fallback_parts[0]],
            aligned,
            periods,
            sheet=sheet,
            book=book,
            concept=fallback_parts[0],
            scale_policy=scale_policy,
        )
        repaid = _sums(
            facts,
            primaries["principal"],
            aligned,
            periods,
            sheet=sheet,
            book=book,
            concept="principal",
            scale_policy=scale_policy,
        )
        # Платёж считается по каждой части отдельно и только потом складывается.
        # Сумма до знака уменьшает знаменатель, если у частей разные знаки.
        denominator = {}
        for key in paid.keys() & repaid.keys():
            left = _payment(paid[key], sign_convention)
            right = _payment(repaid[key], sign_convention)
            denominator[key] = left + right
            if book is not None:
                book.fallback[key] = {
                    "parts": (
                        {"concept": fallback_parts[0], "before": paid[key], "after": left},
                        {"concept": "principal", "before": repaid[key], "after": right},
                    ),
                    "assembled": left + right,
                }
        home = _axes_of(facts, primaries[fallback_parts[0]]) | _axes_of(facts, primaries["principal"])
    if metric in {"icr", "icr_ebit"} and _numerator_misses_axis(numerator, denominator, periods, aligned, home):
        raw = _sums(facts, primaries[numerator_name], aligned, None, sheet=sheet)
        if not _numerator_misses_axis(raw, denominator, periods, aligned, home):
            message = (
                "Нарастающий итог числителя ICR не удалось перевести в значение за период. "
                "Коэффициент не рассчитан."
            )
        else:
            message = "Числитель ICR не содержит значений на оси процентов. Коэффициент не рассчитан."
        return _finish(book, _explained(metric, periods, "input_absent", message, warnings))
    rows = []
    for period in periods:
        axis, period_id = period["axis_id"], period["period_id"]
        if axis not in home:
            _remember(book, period, "skipped", "axis_not_home", ())
            continue
        key = aligned.get((axis, period_id), (axis, period_id))
        excluded = _exclusion(book, key)
        # shortcut: период без числителя или знаменателя пропускается, ноль вместо факта не подставляется
        if key not in denominator or key not in numerator:
            if excluded is not None:
                steps = []
                _skipped_restatement(steps, book, excluded, aligned)
                concept = excluded.get("concept")
                operand = "numerator" if concept == numerator_name else "denominator"
                cells = tuple(excluded.get("current_cells") or ()) + tuple(excluded.get("previous_cells") or ())
                _adopt(book, period, aligned, (), {(concept, cell): operand for cell in cells})
                _remember(book, period, "skipped", "previous_ytd_missing", steps)
            else:
                _remember(book, period, "skipped", "missing_side", ())
            continue
        den = denominator[key]
        payment = _payment(den, sign_convention)
        phase = period_phase.get((axis, period_id))
        if phase is None:
            phase = period_phase.get((axis, period.get("period_key_base") or period_id))
        marker = period.get("marker_class")
        if marker_class and marker and marker != marker_class:
            _remember(book, period, "skipped", "marker_mismatch", ())
            continue
        if metric == "dscr" and not is_coverage_test_period(
            debt_service_nonzero=payment != 0,
            phase=phase,
            explicit_phases=explicit_phases,
        ):
            # Ноль — использование знаменателя. Ненулевой платёж, который фаза исключила, — роль eligibility.
            _adopt_side(
                book,
                period,
                aligned,
                _denominator_names(denominator_name, fallback_parts),
                {key},
                "denominator" if payment == 0 else "eligibility",
            )
            _remember(book, period, "skipped", "not_coverage_test_period", ())
            continue
        steps = []
        if book is not None:
            steps = _period_steps(
                book,
                key=key,
                aligned=aligned,
                denominator_name=denominator_name,
                den=den,
                payment=payment,
                sign_convention=sign_convention,
            )
        if payment == 0:
            _adopt_side(book, period, aligned, _denominator_names(denominator_name, fallback_parts), {key}, "denominator")
            rows.append(_row(metric, period, None, "no_debt_service" if metric == "dscr" else "missing_input", "zero_denominator"))
            _remember(book, period, "no_debt_service" if metric == "dscr" else "missing_input", "zero_denominator", steps, denominator=payment)
            continue
        num = numerator[key]
        with localcontext() as ctx:
            ctx.prec = 38
            ctx.rounding = "ROUND_HALF_EVEN"
            raw_ratio = num / payment
            value = quantize_ratio(raw_ratio)
        if book is not None:
            den_terminal = (f"step:{steps[-1].step_id}",) if steps else _origin_refs(book, denominator_name, key)
            start = len(steps)
            _numerator_steps(steps, book, numerator_name, key, aligned, num)
            num_terminal = (f"step:{steps[-1].step_id}",) if len(steps) > start else _origin_refs(book, numerator_name, key)
            _step(
                steps,
                "division",
                tuple(dict.fromkeys((*num_terminal, *den_terminal))),
                raw_ratio,
                numerator=num,
                denominator=payment,
            )
            if value != raw_ratio:
                _step(
                    steps,
                    "quantization",
                    (f"step:{steps[-1].step_id}",),
                    value,
                    precision=38,
                    quantum=RATIO,
                    rounding="ROUND_HALF_EVEN",
                )
            roles = {numerator_name: "numerator"}
            slots = [("numerator", numerator_name, {key})]
            if fallback_parts is None:
                roles[denominator_name] = "denominator"
                slots.append(("denominator", denominator_name, {key}))
            else:
                roles[fallback_parts[0]] = "denominator"
                roles["principal"] = "denominator"
                slots.append(("denominator", fallback_parts[0], {key}))
                slots.append(("denominator", "principal", {key}))
            _adopt(book, period, aligned, tuple(slots), _cell_roles(book, roles, {key}))
        built = _row(metric, period, value, "computed", None)
        built["components"] = {
            numerator_name: _component_cells(facts, primaries[numerator_name], [period]),
            denominator_name: _component_cells(facts, primaries[denominator_name], [period]),
        }
        if fallback_parts is not None:
            built["components"]["principal"] = _component_cells(facts, primaries["principal"], [period])
        rows.append(built)
        _remember(book, period, "computed", None, steps, value=value, numerator=num, denominator=payment)
    return _finish(book, {"metric": metric, "rows": rows, "needs_input": [], "warnings": warnings, "status": "succeeded"})


def _period_steps(book, *, key, aligned, denominator_name, den, payment, sign_convention):
    steps: list = []
    info = None if book is None else (book.fallback or {}).get(key)
    if info is not None:
        terminals: list[str] = []
        for part in info["parts"]:
            terminals.extend(
                _part_terminal(
                    steps,
                    book,
                    part["concept"],
                    key,
                    aligned,
                    before=part["before"],
                    after=part["after"],
                    rule=sign_convention,
                )
            )
        _step(steps, "denominator_assembly", tuple(terminals), info["assembled"])
        if payment != info["assembled"]:
            _step(
                steps,
                "sign_conversion",
                (f"step:{steps[-1].step_id}",),
                payment,
                before=info["assembled"],
                after=payment,
                rule=sign_convention,
            )
        return steps
    direct = _part_terminal(steps, book, denominator_name, key, aligned)
    if len(direct) != 1:
        _step(steps, "aggregation", direct, den, side="denominator")
        direct = (f"step:{steps[-1].step_id}",)
    if payment != den:
        _step(
            steps,
            "sign_conversion",
            direct,
            payment,
            before=den,
            after=payment,
            rule=sign_convention,
        )
    return steps


def _origin_refs(book, concept, key) -> tuple[str, ...]:
    if book is None or concept is None:
        return ()
    origin = (book.origins or {}).get(concept, {}).get(key) or {}
    return tuple(origin.get("refs") or ())


def _numerator_steps(steps, book, concept, key, aligned, value) -> None:
    direct = _part_terminal(steps, book, concept, key, aligned)
    if len(direct) > 1:
        _step(steps, "numerator_assembly", direct, value, side="numerator")


def _cell_roles(book, roles: dict[str, str], keys) -> dict[tuple[str, str], str]:
    found: dict[tuple[str, str], str] = {}
    if book is None:
        return found
    for concept, operand in roles.items():
        for key in keys:
            note = _note(book, concept, key)
            if note is None:
                continue
            cells = tuple(note.get("current_cells") or ()) + tuple(note.get("previous_cells") or ())
            for cell in cells:
                found[(concept, cell)] = operand
    return found


def _adopt(book, period, aligned, slots, extra_cells) -> None:
    if book is None:
        return
    result_axis = period.get("axis_id")
    result_period = period.get("period_id")
    taken = set()
    for obs in book.observations or []:
        own = (obs.axis_id, obs.period_id)
        key = aligned.get(own, own)
        operand = extra_cells.get((obs.concept, obs.cell_id))
        if operand is None:
            for role, concept, keys in slots:
                if obs.concept == concept and key in keys:
                    operand = role
                    break
        if operand is None:
            continue
        identity = (obs.cell_id, obs.concept, obs.axis_id, obs.period_id, result_period, operand)
        if identity in taken:
            continue
        taken.add(identity)
        book.fact_uses.append(
            FactUse(
                concept=obs.concept,
                cell_id=obs.cell_id,
                axis_id=obs.axis_id,
                period_id=obs.period_id,
                timeline_id=obs.timeline_id,
                period_index=obs.period_index,
                field=obs.field,
                sheet=obs.sheet,
                raw_value=obs.raw_value,
                effective_value=obs.effective_value,
                scale_factor=obs.scale_factor,
                scale_policy=obs.scale_policy,
                scale_applied=obs.scale_applied,
                normalization_source=obs.normalization_source,
                result_axis_id=None if result_axis is None else str(result_axis),
                result_period_id=None if result_period is None else str(result_period),
                operand=operand,
            )
        )


def _scale_mark(fact: dict, *, sheet: bool, policy: str) -> tuple[Decimal | None, str, bool, str]:
    """Решение о масштабе факта. Пустой шаг из него не пишется."""

    scale = _scale(fact.get("scale_factor"))
    if scale is None or policy == "plain":
        return None, "plain", False, "unset"
    if sheet or policy == "sheet":
        return scale, "sheet", False, "sheet"
    raw_dec = _decimal(fact.get("value_dec"))
    raw_val = _decimal(fact.get("value"))
    norm = _decimal(fact.get("normalized_value"))
    sheet_raw = raw_dec if raw_dec is not None else raw_val
    if scale == 1:
        return scale, "apply", True, "unit"
    if sheet_raw is not None and norm is not None and _close(norm, sheet_raw * scale):
        return scale, "apply", True, "normalized_value"
    if sheet_raw is not None and (norm is None or norm == sheet_raw):
        return scale, "apply", True, "multiplied"
    return scale, "apply", True, "normalized_value"


def _window_gap(ordered, period) -> tuple[tuple[str, ...], tuple[str, ...]]:
    from finance_analysis.domain.cover_metrics import WINDOW_MONTHS, add_months

    end = period.get("period_end")
    if not isinstance(end, date):
        return (), ()
    start = add_months(end + timedelta(days=1), -WINDOW_MONTHS)
    found = [
        item
        for item in ordered
        if item.get("period_start") and item.get("period_end") and item["period_start"] >= start and item["period_end"] <= end
    ]
    missing = []
    cursor = start
    for item in found:
        if item["period_start"] != cursor:
            missing.append(cursor.isoformat())
        cursor = item["period_end"] + timedelta(days=1)
    if cursor <= end:
        missing.append(cursor.isoformat())
    return tuple(item["period_id"] for item in found), tuple(missing)


@implements("dscr", "dscr.pf", implementation_version="dscr.pf@1", inputs=DSCR_INPUTS)
def dscr_pf(
    *,
    facts: list[dict],
    bindings: list[dict],
    periods: list[dict],
    period_phase: dict[tuple[str, str], str | None],
    explicit_phases: bool,
    sign_convention: str = "outflow_negative",
    marker_class: str | None = None,
    absent: frozenset[str] = frozenset(),
    interest_order: dict | None = None,
    row_fallbacks: dict | None = None,
    profile: dict | None = None,
    plan: Any | None = None,
) -> dict:
    """Проектный DSCR. Те же числа, что coverage_ratio для metric=dscr. Книгу улики не собирает."""

    if plan is not None:
        from finance_analysis.domain.resolved_plan import bindings_for_plan

        bindings = list(bindings_for_plan(bindings, plan))
    return calculate_dscr_pf(
        facts=facts,
        bindings=bindings,
        periods=periods,
        period_phase=period_phase,
        explicit_phases=explicit_phases,
        sign_convention=sign_convention,
        marker_class=marker_class,
        absent=absent,
        interest_order=interest_order,
        row_fallbacks=row_fallbacks,
        profile=profile,
        plan=plan,
        evidence=False,
    ).result


def calculate_dscr_pf(
    *,
    facts: list[dict],
    bindings: list[dict],
    periods: list[dict],
    period_phase: dict[tuple[str, str], str | None],
    explicit_phases: bool,
    sign_convention: str = "outflow_negative",
    marker_class: str | None = None,
    absent: frozenset[str] = frozenset(),
    interest_order: dict | None = None,
    row_fallbacks: dict | None = None,
    profile: dict | None = None,
    plan: Any | None = None,
    evidence: bool = True,
) -> CalculationOutcome:
    """Тот же проход, что у DSCR, с идентичностью ``dscr.pf@1`` на улике."""

    from dataclasses import replace

    if plan is not None:
        from finance_analysis.domain.resolved_plan import bindings_for_plan

        bindings = list(bindings_for_plan(bindings, plan))
    outcome = calculate_coverage(
        metric="dscr",
        facts=facts,
        bindings=bindings,
        periods=periods,
        period_phase=period_phase,
        explicit_phases=explicit_phases,
        sign_convention=sign_convention,
        marker_class=marker_class,
        absent=absent,
        interest_order=interest_order,
        row_fallbacks=row_fallbacks,
        profile=profile,
        declared=DSCR_INPUTS,
        plan=plan,
        evidence=evidence,
    )
    if outcome.evidence is None:
        return outcome
    return CalculationOutcome(
        outcome.result,
        replace(
            outcome.evidence,
            metric="dscr.pf",
            implementation=_registered_version("dscr", "dscr.pf"),
        ),
    )


ICR_LEASE_INPUTS = ("ebitda", "interest", "lease_interest", "lease_payment", "lease_principal")


@implements("icr_lease", "icr_lease", implementation_version="icr_lease@1", inputs=ICR_LEASE_INPUTS)
def lease_interest_coverage(
    *,
    facts: list[dict],
    bindings: list[dict],
    periods: list[dict],
    sign_convention: str = "outflow_negative",
    marker_class: str | None = None,
    absent: frozenset[str] = frozenset(),
    annual: bool = False,
    plan: Any | None = None,
) -> dict:
    """EBITDA / (|проценты| + проценты в составе лизингового платежа).

    `annual` складывает уже переведённые в период потоки календарного года.
    Без него каждая точка знаменателя — свой коэффициент, в зерне строки.
    Прямая строка `lease_interest` и пара «платёж − долг» вместе не считаются.
    """

    if plan is not None:
        from finance_analysis.domain.resolved_plan import bindings_for_plan

        bindings = list(bindings_for_plan(bindings, plan))
    metric = "icr_lease"
    primaries = BoundInputs(ICR_LEASE_INPUTS, _primaries(bindings, absent))
    warnings: list[dict] = []
    if "ebitda" not in primaries or "interest" not in primaries:
        subject = "ebitda" if "ebitda" not in primaries else "interest"
        return _lease_gap(metric, subject, [subject], bindings, absent, warnings, missing_input=True)
    watched = {"ebitda", "interest", "lease_interest", "lease_payment", "lease_principal"}
    ambiguous = [name for name, rows in _groups(bindings).items() if len(rows) > 1 and name in watched]
    if ambiguous:
        return _lease_ask(metric, "ambiguous", ambiguous[0], [ambiguous[0]], warnings)
    mode = _lease_mode(primaries, bindings, absent)
    if mode == "ambiguous":
        return _lease_ask(metric, "ambiguous", "lease_interest", ["lease_interest"], warnings)
    if mode == "none":
        return _lease_gap(
            metric, "lease_payment", ["lease_payment", "lease_principal"], bindings, absent, warnings
        )
    if mode == "half":
        subject = "lease_principal" if "lease_payment" in primaries else "lease_payment"
        return _lease_gap(metric, subject, [subject], bindings, absent, warnings)
    named = {"ebitda": primaries["ebitda"], "interest": primaries["interest"]}
    if mode == "direct":
        named["lease_interest"] = primaries["lease_interest"]
    elif mode == "pair":
        named["lease_payment"] = primaries["lease_payment"]
        named["lease_principal"] = primaries["lease_principal"]
    if unconfirmed_scale(facts, list(named.values())):
        components, scales = _scale_bundle(facts, named)
        return _explained(
            metric,
            periods,
            "scale_unconfirmed",
            SCALE_UNCONFIRMED,
            warnings,
            home=_home_period(facts, primaries["ebitda"], periods),
            components=components,
            scales=scales,
        )
    bases = {name: _flow_basis(row) for name, row in named.items()}
    denominator_bases = {basis for name, basis in bases.items() if name != "ebitda"}
    allowed_ltm = bases["ebitda"] == "ltm" and denominator_bases == {"period"}
    if len(set(bases.values())) > 1 and not allowed_ltm:
        return _explained(metric, periods, "basis_mismatch", MIXED_BASIS, warnings)
    if not allowed_ltm and _grain_conflict(facts, named, periods):
        return _explained(metric, periods, "basis_mismatch", MIXED_BASIS, warnings)
    sheet = _assume_sheet_units(facts, list(named.values()), warnings)
    aligned = aligned_keys(periods)
    series = {name: _sums(facts, row, aligned, periods, sheet=sheet) for name, row in named.items()}
    home = _axes_of(facts, primaries["interest"])
    points = _lease_points(periods, home, aligned, series, mode, sign_convention, marker_class)
    if any(addend is not None and addend < 0 for _period, _key, addend in points):
        return _lease_stop(metric, periods, "not_computed", "negative_lease_interest", NEGATIVE_LEASE_INTEREST, warnings)
    if any(addend is not None and addend > 0 for _period, _key, addend in points) and not _excludes_lease(
        primaries["interest"]
    ):
        asked = _lease_ask(metric, "lease_interest_overlap", "interest", ["interest"], warnings)
        asked["message"] = LEASE_OVERLAP
        asked["warnings"] = [
            *warnings,
            {"code": "lease_interest_overlap", "params": {"message": LEASE_OVERLAP}},
        ]
        return asked
    if _lease_in_opex(named):
        warnings.append({"code": "operating_lease_numerator", "params": {"message": OPERATING_LEASE_NUMERATOR}})
    if allowed_ltm:
        rows, computed = _lease_ltm_rows(
            metric, periods, series, home, facts, primaries, aligned, mode, sign_convention, marker_class
        )
        status = "succeeded" if computed else "partial_window"
        result = {"metric": metric, "rows": rows, "needs_input": [], "warnings": warnings, "status": status}
        if not computed:
            result["message"] = PARTIAL_DENOMINATOR
        return result
    if annual:
        rows = _lease_annual_rows(metric, points, series, sign_convention, facts, primaries, mode)
    else:
        rows = _lease_period_rows(metric, points, series, sign_convention, facts, primaries, mode)
    if any(row["status"] == "computed" for row in rows):
        status = "succeeded"
    elif any(row.get("reason") == "partial_window" for row in rows):
        status = "not_computed"
    else:
        status = "missing_input"
    return {"metric": metric, "rows": rows, "needs_input": [], "warnings": warnings, "status": status}


def _lease_mode(primaries: dict, bindings: list[dict], absent: frozenset[str]) -> str:
    direct = "lease_interest" in primaries
    pay = "lease_payment" in primaries
    principal = "lease_principal" in primaries
    if direct and (pay or principal):
        return "ambiguous"
    if direct:
        return "direct"
    if pay and principal:
        return "pair"
    gone = absent_concepts(bindings, absent)
    if "lease_payment" in gone and "lease_principal" in gone:
        return "zero"
    if pay or principal:
        return "half"
    return "none"


def _lease_ask(metric: str, reason: str, subject: str, missing: list[str], warnings: list[dict]) -> dict:
    return {
        "metric": metric,
        "rows": [],
        "needs_input": [{"kind": "concept", "reason": reason, "subject": subject}],
        "missing_inputs": missing,
        "warnings": warnings,
        "status": "needs_input",
    }


def _lease_gap(
    metric: str,
    subject: str,
    missing: list[str],
    bindings: list[dict],
    absent: frozenset[str],
    warnings: list[dict],
    *,
    missing_input: bool = False,
) -> dict:
    reason = "absent_in_book" if subject in absent_concepts(bindings, absent) else "concept_unknown"
    result = _lease_ask(metric, reason, subject, missing, warnings)
    if missing_input:
        result["status"] = "missing_input"
    return result


def _lease_stop(metric: str, periods: list[dict], status: str, reason: str, message: str, warnings: list[dict]) -> dict:
    period = periods[0] if periods else None
    if period is None:
        rows: list[dict] = []
    else:
        row = _row(metric, period, None, status, reason)
        row["message"] = message
        rows = [row]
    return {
        "metric": metric,
        "rows": rows,
        "needs_input": [],
        "warnings": warnings,
        "status": status,
        "message": message,
    }


def _binding_evidence(binding: dict) -> dict:
    evidence = binding.get("evidence")
    if isinstance(evidence, dict):
        return evidence
    raw = binding.get("evidence_json")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw:
        import json

        try:
            loaded = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return loaded if isinstance(loaded, dict) else {}
    return {}


def _excludes_lease(binding: dict) -> bool:
    """Проценты по кредитам и займам, либо явный флаг. Метка «2330» сама по себе не годится."""

    if _binding_evidence(binding).get("excludes_lease_interest") is True:
        return True
    label = str(binding.get("label_text") or binding.get("label") or "")
    folded = label.casefold().replace("ё", "е")
    loan = "кредит" in folded or "займ" in folded
    lease = "лизинг" in folded or "аренд" in folded
    return bool(loan and not lease)


def _lease_in_opex(named: dict) -> bool:
    for name in ("lease_payment", "lease_interest", "lease_principal"):
        row = named.get(name)
        if row is None:
            continue
        evidence = _binding_evidence(row)
        if evidence.get("operating_lease_in_opex") is True or evidence.get("lease_in_operating_expenses") is True:
            return True
    return False


def _grain_conflict(facts: list[dict], named: dict, periods: list[dict]) -> bool:
    from finance_analysis.domain.cover_metrics import GRAIN_MONTHS

    lengths = []
    for binding in named.values():
        axes = _axes_of(facts, binding)
        found = set()
        for period in periods:
            grain = period.get("grain")
            if period.get("axis_id") not in axes or not grain:
                continue
            found.add(GRAIN_MONTHS.get(str(grain), str(grain)))
        if found:
            lengths.append(found)
    return len(lengths) >= 2 and any(item != lengths[0] for item in lengths[1:])


def _lease_addend(mode: str, key: tuple, series: dict, convention: str) -> Decimal | None:
    """Процент лизинга после приведения знака каждой части. None — части на ключе нет."""

    if mode == "zero":
        return Decimal(0)
    if mode == "direct":
        value = series["lease_interest"].get(key)
        if value is None:
            return None
        return _payment(value, convention)
    paid = series["lease_payment"].get(key)
    principal = series["lease_principal"].get(key)
    if paid is None or principal is None:
        return None
    return _payment(paid, convention) - _payment(principal, convention)


def _lease_points(
    periods: list[dict],
    home: set[str],
    aligned: dict,
    series: dict,
    mode: str,
    convention: str,
    marker_class: str | None,
) -> list[tuple]:
    found = []
    for period in periods:
        if period.get("axis_id") not in home:
            continue
        marker = period.get("marker_class")
        if marker_class and marker and marker != marker_class:
            continue
        own = (period.get("axis_id"), period.get("period_id"))
        key = aligned.get(own, own)
        if key not in series["interest"]:
            continue
        found.append((period, key, _lease_addend(mode, key, series, convention)))
    return found


def _divide(numerator: Decimal, denominator: Decimal) -> Decimal:
    with localcontext() as ctx:
        ctx.prec = 38
        ctx.rounding = "ROUND_HALF_EVEN"
        return quantize_ratio(numerator / denominator)


def _lease_components(facts: list[dict], primaries: dict, used: list[dict], mode: str) -> dict:
    parts = {
        "ebitda": _component_cells(facts, primaries["ebitda"], used),
        "interest": _component_cells(facts, primaries["interest"], used),
    }
    if mode == "pair":
        parts["lease_payment"] = _component_cells(facts, primaries["lease_payment"], used)
        parts["lease_principal"] = _component_cells(facts, primaries["lease_principal"], used)
    elif mode == "direct":
        parts["lease_interest"] = _component_cells(facts, primaries["lease_interest"], used)
    return parts


def _lease_period_rows(
    metric: str,
    points: list[tuple],
    series: dict,
    convention: str,
    facts: list[dict],
    primaries: dict,
    mode: str,
) -> list[dict]:
    rows = []
    for period, key, addend in points:
        if addend is None or key not in series["ebitda"]:
            continue
        denominator = _payment(series["interest"][key], convention) + addend
        if denominator == 0:
            rows.append(_row(metric, period, None, "missing_input", "zero_denominator"))
            continue
        row = _row(metric, period, _divide(series["ebitda"][key], denominator), "computed", None)
        row["components"] = _lease_components(facts, primaries, [period], mode)
        rows.append(row)
    return rows


def _lease_annual_rows(
    metric: str,
    points: list[tuple],
    series: dict,
    convention: str,
    facts: list[dict],
    primaries: dict,
    mode: str,
) -> list[dict]:
    """Сумма потоков за год. Год из одного годового зерна не складывается второй раз."""

    from finance_analysis.domain.cover_metrics import GRAIN_MONTHS

    grouped: dict = {}
    for period, key, addend in points:
        grouped.setdefault(_year_of(period), []).append((period, key, addend))
    rows = []
    for _year, items in sorted(grouped.items(), key=lambda item: (item[0] is None, item[0] or 0)):
        spans = []
        for period, _key, _addend in items:
            span = GRAIN_MONTHS.get(str(period.get("grain") or ""))
            if span is None:
                spans = []
                break
            spans.append(span)
        last = max(items, key=lambda item: int(item[0].get("period_index") or 0))[0]
        ready = [item for item in items if item[2] is not None and item[1] in series["ebitda"]]
        if not spans or sum(spans) != 12 or len(ready) != len(items):
            row = _row(metric, last, None, "not_computed", "partial_window")
            row["message"] = PARTIAL_DENOMINATOR
            rows.append(row)
            continue
        numerator = sum((series["ebitda"][key] for _period, key, _addend in ready), Decimal(0))
        denominator = sum(
            (
                _payment(series["interest"][key], convention) + addend
                for _period, key, addend in ready
            ),
            Decimal(0),
        )
        if denominator == 0:
            rows.append(_row(metric, last, None, "missing_input", "zero_denominator"))
            continue
        row = _row(metric, last, _divide(numerator, denominator), "computed", None)
        row["components"] = _lease_components(facts, primaries, [item[0] for item in ready], mode)
        rows.append(row)
    return rows


def _lease_ltm_rows(
    metric: str,
    periods: list[dict],
    series: dict,
    home: set[str],
    facts: list[dict],
    primaries: dict,
    aligned: dict,
    mode: str,
    convention: str,
    marker_class: str | None,
) -> tuple[list[dict], bool]:
    """Числитель `ltm` делится на сумму знаменателя за двенадцать месяцев, как у ICR."""

    from finance_analysis.domain.cover_metrics import _window

    ordered = _dated_periods([period for period in periods if period.get("axis_id") in home])
    numerator_axes = _axes_of(facts, primaries["ebitda"])
    rows = []
    computed = False
    for period in _dated_periods([item for item in periods if item.get("axis_id") in numerator_axes]):
        marker = period.get("marker_class")
        if marker_class and marker and marker != marker_class:
            continue
        key = aligned.get((period["axis_id"], period["period_id"]), (period["axis_id"], period["period_id"]))
        if key not in series["ebitda"]:
            continue
        window = _window(ordered, period, "lookback")
        if window is None:
            rows.append(_noted(metric, period, "partial_window", PARTIAL_DENOMINATOR))
            continue
        total = Decimal(0)
        hole = False
        for item in window:
            dkey = aligned.get((item["axis_id"], item["period_id"]), (item["axis_id"], item["period_id"]))
            addend = _lease_addend(mode, dkey, series, convention) if dkey in series["interest"] else None
            if addend is None:
                hole = True
                break
            total += _payment(series["interest"][dkey], convention) + addend
        if hole:
            rows.append(_row(metric, period, None, "missing_input", "no_binding"))
            continue
        if total == 0:
            rows.append(_row(metric, period, None, "missing_input", "zero_denominator"))
            continue
        row = _row(metric, period, _divide(series["ebitda"][key], total), "computed", None)
        row["window"] = [item["period_id"] for item in window]
        row["components"] = _lease_components(facts, primaries, window, mode)
        rows.append(row)
        computed = True
    if not rows:
        return [_noted(metric, periods[0], "partial_window", PARTIAL_DENOMINATOR)] if periods else [], False
    return rows, computed


def _ltm_numerator(
    metric: str,
    facts: list[dict],
    numerator_binding: dict,
    denominator_binding: dict,
    periods: list[dict],
    warnings: list[dict],
    sign_convention: str,
    *,
    period_phase: dict,
    explicit_phases: bool,
    marker_class: str | None,
    sheet: bool = False,
    extra_denominators: list[dict] | None = None,
    book: EvidenceBook | None = None,
    numerator_name: str | None = None,
    denominator_name: str | None = None,
    scale_policy: str = "plain",
) -> dict:
    """Числитель `ltm` делится на сумму знаменателя за двенадцать месяцев до его конца.

    Дополнительные строки знаменателя, например основной долг рядом с процентами,
    входят в ту же сумму. Платёж берётся по каждой строке отдельно. Привязка строк
    не меняется. Неполное окно даёт `partial_window`. Окно то же, что у отношения
    чистого долга к EBITDA.
    """

    from finance_analysis.domain.cover_metrics import _window
    from finance_analysis.domain.coverage import is_coverage_test_period

    aligned = aligned_keys(periods)
    numerator_concept = _bound_name(numerator_binding, numerator_name or ("cfads" if metric == "dscr" else "ebitda"))
    numerator = _sums(
        facts,
        numerator_binding,
        aligned,
        periods,
        sheet=sheet,
        book=book,
        concept=numerator_concept,
        scale_policy=scale_policy,
    )
    denominator_bindings = [denominator_binding, *(extra_denominators or [])]
    denominators = []
    concepts: dict[int, str] = {}
    for binding in denominator_bindings:
        default = denominator_name if binding is denominator_binding and denominator_name else (
            "debt_service" if metric == "dscr" else "interest"
        )
        name = _bound_name(binding, default)
        concepts[id(binding)] = name
        denominators.append(
            (binding, _sums(facts, binding, aligned, periods, sheet=sheet, book=book, concept=name, scale_policy=scale_policy))
        )
    numerator_axes = _axes_of(facts, numerator_binding)
    denominator_axes = _axes_of(facts, denominator_binding)
    ordered = _dated_periods([period for period in periods if period["axis_id"] in denominator_axes])
    rows = []
    computed = False
    for period in _dated_periods([period for period in periods if period["axis_id"] in numerator_axes]):
        marker = period.get("marker_class")
        if marker_class and marker and marker != marker_class:
            _remember(book, period, "skipped", "marker_mismatch", ())
            continue
        key = aligned.get((period["axis_id"], period["period_id"]), (period["axis_id"], period["period_id"]))
        if key not in numerator:
            _remember(book, period, "skipped", "missing_side", ())
            continue
        window = _window(ordered, period, "lookback")
        denominator_names = tuple(concepts[id(binding)] for binding, _series in denominators)
        if window is None:
            rows.append(_noted(metric, period, "partial_window", PARTIAL_DENOMINATOR))
            found, missing = _window_gap(ordered, period)
            _remember(
                book,
                period,
                "partial_window",
                "partial_window",
                (),
                window_periods=found,
                window_missing=missing,
                missing_concepts=tuple((item, denominator_names) for item in missing),
            )
            continue
        total = Decimal(0)
        complete = True
        signed_parts = []
        for item in window:
            dkey = aligned.get((item["axis_id"], item["period_id"]), (item["axis_id"], item["period_id"]))
            for binding, series in denominators:
                if dkey not in series:
                    complete = False
                    break
                raw = series[dkey]
                signed = _payment(raw, sign_convention)
                total += signed
                signed_parts.append((binding, dkey, raw, signed))
            if not complete:
                break
        if not complete:
            rows.append(_noted(metric, period, "partial_window", PARTIAL_DENOMINATOR))
            found_ids = tuple(item["period_id"] for item in window)
            missing_ids = []
            named_gaps = []
            for item in window:
                dkey = aligned.get((item["axis_id"], item["period_id"]), (item["axis_id"], item["period_id"]))
                absent = tuple(concepts[id(binding)] for binding, series in denominators if dkey not in series)
                if absent:
                    missing_ids.append(item["period_id"])
                    named_gaps.append((item["period_id"], absent))
            _remember(
                book,
                period,
                "partial_window",
                "partial_window",
                (),
                window_periods=found_ids,
                window_missing=tuple(missing_ids),
                missing_concepts=tuple(named_gaps),
            )
            continue
        phase = period_phase.get((period["axis_id"], period["period_id"]))
        den_keys = {aligned.get((item["axis_id"], item["period_id"]), (item["axis_id"], item["period_id"])) for item in window}
        if metric == "dscr" and not is_coverage_test_period(
            debt_service_nonzero=total != 0,
            phase=phase,
            explicit_phases=explicit_phases,
        ):
            _adopt_side(
                book,
                period,
                aligned,
                denominator_names,
                den_keys,
                "denominator" if total == 0 else "eligibility",
            )
            _remember(book, period, "skipped", "not_coverage_test_period", ())
            continue
        if total == 0:
            _adopt_side(book, period, aligned, denominator_names, den_keys, "denominator")
            status = "no_debt_service" if metric == "dscr" else "missing_input"
            rows.append(_row(metric, period, None, status, "zero_denominator"))
            _remember(book, period, status, "zero_denominator", (), denominator=total)
            continue
        with localcontext() as ctx:
            ctx.prec = 38
            ctx.rounding = "ROUND_HALF_EVEN"
            raw_ratio = numerator[key] / total
            value = quantize_ratio(raw_ratio)
        steps = []
        if book is not None:
            terminals: list[str] = []
            for binding, dkey, raw, signed in signed_parts:
                terminals.extend(
                    _part_terminal(
                        steps,
                        book,
                        concepts[id(binding)],
                        dkey,
                        aligned,
                        before=raw,
                        after=signed,
                        rule=sign_convention,
                    )
                )
            unique = tuple(dict.fromkeys(terminals))
            if len(unique) != 1:
                _step(steps, "aggregation", unique, total, side="denominator")
                den_terminal = (f"step:{steps[-1].step_id}",)
            else:
                den_terminal = unique
            start = len(steps)
            _numerator_steps(steps, book, numerator_concept, key, aligned, numerator[key])
            num_terminal = (
                (f"step:{steps[-1].step_id}",)
                if len(steps) > start
                else _origin_refs(book, numerator_concept, key)
            )
            _step(
                steps,
                "division",
                tuple(dict.fromkeys((*num_terminal, *den_terminal))),
                raw_ratio,
                numerator=numerator[key],
                denominator=total,
            )
            if value != raw_ratio:
                _step(
                    steps,
                    "quantization",
                    (f"step:{steps[-1].step_id}",),
                    value,
                    precision=38,
                    quantum=RATIO,
                    rounding="ROUND_HALF_EVEN",
                )
            slots = [("numerator", numerator_concept, {key})]
            roles = {numerator_concept: "numerator"}
            for binding, _series in denominators:
                name = concepts[id(binding)]
                slots.append(("denominator", name, den_keys))
                roles[name] = "denominator"
            _adopt(book, period, aligned, tuple(slots), _cell_roles(book, roles, den_keys | {key}))
        _remember(
            book,
            period,
            "computed",
            None,
            steps,
            value=value,
            numerator=numerator[key],
            denominator=total,
            window_periods=tuple(item["period_id"] for item in window),
        )
        row = _row(metric, period, value, "computed", None)
        row["window"] = [item["period_id"] for item in window]
        numerator_name = _bound_name(numerator_binding, "cfads" if metric == "dscr" else "ebitda")
        row["components"] = {numerator_name: _component_cells(facts, numerator_binding, [period])}
        row["scale_factor"] = {numerator_name: _stored_scale(facts, numerator_binding)}
        for binding, _series in denominators:
            name = _bound_name(binding, "debt_service" if metric == "dscr" else "interest")
            row["components"][name] = _component_cells(facts, binding, window)
            row["scale_factor"][name] = _stored_scale(facts, binding)
        rows.append(row)
        computed = True
    if not rows:
        return _explained(metric, periods, "partial_window", PARTIAL_DENOMINATOR, warnings)
    status = "succeeded" if computed else "partial_window"
    result = {"metric": metric, "rows": rows, "needs_input": [], "warnings": warnings, "status": status}
    if not computed:
        result["message"] = PARTIAL_DENOMINATOR
    return result


def _noted(metric: str, period: dict, status: str, message: str) -> dict:
    row = _row(metric, period, None, status, status)
    row["message"] = message
    return row


def _dated_periods(periods: list[dict]) -> list[dict]:
    found = []
    for period in periods:
        start = _as_date(period.get("period_start"))
        end = _as_date(period.get("period_end"))
        found.append({**period, "period_start": start, "period_end": end})
    return sorted(found, key=lambda item: (item["period_end"] or date.min, int(item.get("period_index") or 0)))


def _as_date(value) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def _explained(
    metric: str,
    periods: list[dict],
    status: str,
    message: str,
    warnings: list[dict],
    *,
    home: dict | None = None,
    components: dict | None = None,
    scales: dict | None = None,
) -> dict:
    """Один явный исход вместо пустого списка строк.

    Ось — ось числителя, если она известна. Ячейки и масштаб остаются в строке,
    чтобы отказ можно было сверить с книгой.
    """

    period = home if home is not None else (periods[0] if periods else None)
    if period is None:
        row = {
            "metric": metric,
            "axis_id": None,
            "period_id": None,
            "period_key_base": None,
            "period_marker": None,
            "value": None,
            "status": status,
            "reason": status,
            "message": message,
        }
    else:
        row = _row(metric, period, None, status, status)
        row["message"] = message
    if components is not None:
        row["components"] = components
    if scales is not None:
        row["scale_factor"] = scales
    return {"metric": metric, "rows": [row], "needs_input": [], "warnings": warnings, "status": status, "message": message}


def _basis_message(numerator_name: str, numerator: dict, denominator: dict) -> str | None:
    """Сообщение, если способ показа числителя нельзя делить на проценты за период."""

    left = _flow_basis(numerator)
    right = _flow_basis(denominator)
    if left == right:
        return None
    title = "EBITDA" if numerator_name == "ebitda" else "EBIT"
    return (
        f"Строка {title} имеет способ показа «{left}», а строка процентов — «{right}». "
        "ICR по этим строкам не рассчитан."
    )


def _bound_name(binding: dict, default: str) -> str:
    """Имя понятия основной строки: ``effective_concept``, иначе ``concept``."""

    return declared_concept(binding) or default


def _flow_basis(binding: dict) -> str:
    basis, source = basis_of(binding)
    if basis == "ytd" and source in {"header", "formula"}:
        return "period"
    return basis


def _numerator_misses_axis(numerator: dict, denominator: dict, periods: list[dict], aligned: dict, home: set[str]) -> bool:
    """У процентов есть значения, но ни один период не содержит обе стороны."""

    seen_denominator = False
    for period in periods:
        if period["axis_id"] not in home:
            continue
        key = aligned.get((period["axis_id"], period["period_id"]), (period["axis_id"], period["period_id"]))
        if key not in denominator:
            continue
        seen_denominator = True
        if key in numerator:
            return False
    return seen_denominator


def _primaries(bindings: list[dict], absent: frozenset[str] = frozenset()) -> dict[str, dict]:
    found = {}
    for row in bindings:
        concept = declared_concept(row)
        if not (row.get("is_primary") and row.get("status") in _BOUND and concept):
            continue
        # Устаревшая основная строка не входит в расчёт: её отбрасывает и резолвер входа.
        if row.get("stale"):
            continue
        if concept in absent and row.get("source") not in HUMAN_SOURCES:
            continue
        found[concept] = row
    return found


def absent_concepts(bindings: list[dict], absent: frozenset[str] = frozenset()) -> set[str]:
    """`concept.absent` из журнала и строки, которые человек снял с отсутствующего понятия."""

    marked = {
        declared_concept(row)
        for row in bindings
        if row.get("source") == "confirmed" and row.get("status") == "unknown" and declared_concept(row)
    }
    restored = {concept for concept, row in _primaries(bindings).items() if row.get("source") in HUMAN_SOURCES}
    return (marked | set(absent)) - restored


def _groups(bindings: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for row in bindings:
        concept = declared_concept(row)
        if row.get("is_primary") and concept and not row.get("stale"):
            grouped.setdefault(concept, []).append(row)
    return grouped


def aligned_keys(periods: list[dict]) -> dict[tuple[str, str], tuple]:
    """(axis_id, period_id) → ключ шкалы: (`timeline_id`, `period_index`), иначе свой."""

    found = {}
    for period in periods:
        timeline = period.get("timeline_id")
        index = period.get("period_index")
        if timeline and index is not None:
            found[(period["axis_id"], period["period_id"])] = (timeline, int(index))
    return found


def _axes_of(facts: list[dict], binding: dict) -> set[str]:
    return {fact["axis_id"] for fact in facts if fact.get("row_key") == binding["row_key"]}


def _sums(
    facts: list[dict],
    binding: dict,
    aligned: dict | None = None,
    periods: list[dict] | None = None,
    *,
    sheet: bool = False,
    book: EvidenceBook | None = None,
    concept: str | None = None,
    scale_policy: str = "plain",
    considered: str | None = None,
) -> dict[tuple, Decimal]:
    """Сумма строки по ключу шкалы. Нарастающий итог переводится в значение за период.

    Перевод делается только когда у привязки есть календарь и способ показа
    поставлен по заголовку или по формуле. Строка `ltm` здесь не складывается
    и не выбрасывается: окно само берёт её конец.
    """

    totals: dict[tuple, Decimal] = {}
    grouped: dict[tuple, list[dict]] = {}
    row_key = binding["row_key"]
    aligned = aligned or {}
    located = {(period.get("axis_id"), period.get("period_id")): period for period in periods or []}
    for fact in facts:
        if fact.get("row_key") != row_key:
            continue
        number, field, raw = _figure_taken(fact, sheet=sheet)
        if number is None or field is None or raw is None:
            continue
        own = (fact["axis_id"], fact["period_id"])
        key = aligned.get(own, own)
        totals[key] = totals.get(key, Decimal(0)) + Decimal(number)
        if book is not None:
            book.sums_additions += 1
        cell = fact.get("cell_id")
        ref = f"cell:{cell}" if cell else f"fact:{fact['axis_id']}:{fact['period_id']}"
        grouped.setdefault(key, []).append({"cell": str(cell) if cell else None, "ref": ref, "raw": raw, "effective": number})
        if book is not None and concept is not None:
            period = located.get(own) or {}
            index = period.get("period_index")
            factor, marked_policy, applied, source = _scale_mark(fact, sheet=sheet, policy=scale_policy)
            book.observations.append(
                FactObservation(
                    concept=concept,
                    cell_id=str(cell) if cell else None,
                    axis_id=str(fact["axis_id"]),
                    period_id=str(fact["period_id"]),
                    timeline_id=None if period.get("timeline_id") is None else str(period.get("timeline_id")),
                    period_index=None if index is None else int(index),
                    field=field,
                    sheet=sheet,
                    raw_value=raw,
                    effective_value=number,
                    scale_factor=factor,
                    scale_policy=marked_policy,
                    scale_applied=applied,
                    normalization_source=source,
                    considered=considered,
                )
            )
    origins = {
        key: {
            "cells": tuple(item["cell"] for item in items if item["cell"]),
            "refs": tuple(item["ref"] for item in items),
            "raw": sum((item["raw"] for item in items), Decimal(0)),
            "effective": totals[key],
        }
        for key, items in grouped.items()
    }
    if book is not None and concept is not None:
        book.origins.setdefault(concept, {}).update(origins)
    if periods is None:
        return totals
    journal: list | None = [] if book is not None else None
    restated = restate_series(totals, binding, periods, aligned, journal=journal, origins=origins)
    if book is not None and journal:
        for note in journal:
            note["concept"] = concept
        book.notes.extend(journal)
    return restated


def _component_cells(facts: list[dict], binding: dict, periods: list[dict]) -> list[str]:
    """Ячейки строки понятия за указанные периоды. Пустой список, если ячеек нет."""

    wanted = {(item.get("axis_id"), item.get("period_id")) for item in periods}
    found = []
    for fact in facts:
        if fact.get("row_key") != binding.get("row_key"):
            continue
        if (fact.get("axis_id"), fact.get("period_id")) not in wanted:
            continue
        cell = fact.get("cell_id")
        if cell and cell not in found:
            found.append(str(cell))
    return found


def unconfirmed_scale(facts: list[dict], bindings: list[dict]) -> bool:
    """Число строки спорит с её масштабом.

    Отсутствие масштаба у одной стороны отказом не является: тогда обе стороны
    берутся числами на листе.
    """

    return any(_scale_kind(facts, binding) == "unconfirmed" for binding in bindings)


def _assume_sheet_units(facts: list[dict], bindings: list[dict], warnings: list[dict]) -> bool:
    """Масштаб умножает коэффициент, только если он есть у каждой стороны.

    Иначе стороны считаются в единицах книги. Предупреждение одно на расчёт.
    """

    if _scale_policy(facts, bindings) != "sheet":
        return False
    warnings.append({"code": "scale_assumed", "params": {"message": SCALE_ASSUMED}})
    return True


def _scale_policy(facts: list[dict], bindings: list[dict]) -> str:
    known = sum(_stored_scale(facts, binding) is not None for binding in bindings)
    if known == 0 or known == len(bindings):
        return "plain" if known == 0 else "apply"
    return "sheet"


def _home_period(facts: list[dict], binding: dict, periods: list[dict]) -> dict | None:
    """Первый период оси числителя. Чужая ось в начале списка периодов не годится."""

    axes = {fact.get("axis_id") for fact in facts if fact.get("row_key") == binding.get("row_key")}
    for period in periods:
        if period.get("axis_id") in axes:
            return period
    return None


def _scale_bundle(facts: list[dict], named: dict[str, dict]) -> tuple[dict, dict]:
    components = {}
    scales = {}
    for name, binding in named.items():
        cells: list[str] = []
        for fact in facts:
            if fact.get("row_key") != binding.get("row_key"):
                continue
            cell = fact.get("cell_id")
            if cell and str(cell) not in cells:
                cells.append(str(cell))
        components[name] = cells
        scales[name] = _stored_scale(facts, binding)
    return components, scales


def _stored_scale(facts: list[dict], binding: dict):
    for fact in facts:
        if fact.get("row_key") != binding.get("row_key"):
            continue
        scale = fact.get("scale_factor")
        if scale not in (None, ""):
            return scale
    return None


def _scale_kind(facts: list[dict], binding: dict) -> str:
    kinds = {_one_scale(fact) for fact in facts if fact.get("row_key") == binding.get("row_key")}
    if not kinds:
        return "raw"
    if kinds == {"raw"} or kinds == {"base"}:
        return next(iter(kinds))
    return "unconfirmed"


def _one_scale(fact: dict) -> str:
    raw = _decimal(fact.get("value_dec"))
    if raw is None:
        raw = _decimal(fact.get("value"))
    norm = _decimal(fact.get("normalized_value"))
    scale = _scale(fact.get("scale_factor"))
    if scale is None:
        return "raw"
    if scale == 1:
        return "base"
    if raw is not None and norm is not None and _close(norm, raw * scale):
        return "base"
    if raw is not None and (norm is None or norm == raw):
        return "base"
    return "unconfirmed"


def _figure(fact: dict, *, sheet: bool = False) -> Decimal | None:
    """Величина ячейки.

    `sheet` берёт число на листе и не умножает его: так считается коэффициент,
    когда масштаб известен не у каждой стороны. Иначе заданный масштаб применяется,
    если нормализованное значение его ещё не учитывает.
    """

    value, _field, _raw = _figure_taken(fact, sheet=sheet)
    return value


def _figure_taken(fact: dict, *, sheet: bool = False) -> tuple[Decimal | None, str | None, Decimal | None]:
    """Эффективное значение, поле, из которого оно взято, и сырое значение этого поля."""

    raw_dec = _decimal(fact.get("value_dec"))
    raw_val = _decimal(fact.get("value"))
    norm = _decimal(fact.get("normalized_value"))
    sheet_field = "value_dec" if raw_dec is not None else ("value" if raw_val is not None else None)
    sheet_raw = raw_dec if raw_dec is not None else raw_val
    if sheet:
        if sheet_raw is not None:
            return sheet_raw, sheet_field, sheet_raw
        if norm is not None:
            return norm, "normalized_value", norm
        return None, None, None
    scale = _scale(fact.get("scale_factor"))
    if scale is None or scale == 1:
        if norm is not None:
            return norm, "normalized_value", norm
        if sheet_raw is not None:
            return sheet_raw, sheet_field, sheet_raw
        return None, None, None
    if sheet_raw is not None and norm is not None and _close(norm, sheet_raw * scale):
        return norm, "normalized_value", norm
    if sheet_raw is not None and (norm is None or norm == sheet_raw):
        return sheet_raw * scale, sheet_field, sheet_raw
    if norm is not None:
        return norm, "normalized_value", norm
    return None, None, None


def _decimal(value) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _scale(value) -> Decimal | None:
    number = _decimal(value)
    if number is None or number == 0:
        return None
    return number


def _close(left: Decimal, right: Decimal) -> bool:
    return abs(left - right) <= max(abs(right) * Decimal("0.0001"), Decimal("0.01"))


def _payment(value: Decimal, convention: str) -> Decimal:
    if convention == "outflow_positive":
        return value
    return -value if value < 0 else value


def _row(metric, period, value, status, reason) -> dict:
    return {
        "metric": metric,
        "axis_id": period["axis_id"],
        "period_id": period["period_id"],
        "period_key_base": period.get("period_key_base"),
        "period_marker": period.get("period_marker"),
        "value": value,
        "status": status,
        "reason": reason,
    }
