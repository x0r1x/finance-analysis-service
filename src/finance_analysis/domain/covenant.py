"""Составные коэффициенты среза 2: ковенантный DSCR, чистый долг и эскроу.

Арифметика только над привязанными строками. Чисел из профиля нет: оттуда
приходят состав числителя, знаменателя и окно.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from itertools import pairwise
from types import MappingProxyType
from typing import Any

from finance_analysis.domain.binding_resolution import declared_concept
from finance_analysis.domain.calculation_evidence import (
    EvidenceBook,
    FactUse,
    PeriodResult,
    TransformationStep,
    definition_fields,
    seal,
)
from finance_analysis.domain.cash_flow import net_cash_flow as period_net_cash_flow
from finance_analysis.domain.cover_metrics import (
    _missing,
    _ordered,
    _ratio,
    _window,
    grain_months,
)
from finance_analysis.domain.free_cash_flow import free_cash_flow
from finance_analysis.domain.mapping import marked_line_code
from finance_analysis.domain.metric_contract import (
    BoundInputs,
    ConceptDependency,
    ConceptGroup,
    DynamicInputs,
    UndeclaredInput,
    implements,
)
from finance_analysis.domain.metrics import (
    MIXED_BASIS,
    PARTIAL_DENOMINATOR,
    SCALE_UNCONFIRMED,
    _assume_sheet_units,
    _axes_of,
    _component_cells,
    _flow_basis,
    _payment,
    _primaries,
    _step,
    _sums,
    aligned_keys,
    calculate_coverage,
    calculate_dscr_pf,
    confirm_paid_interest,
    coverage_ratio,
    dscr_pf,
    ebitda_definition,
    interest_choice,
    lease_interest_coverage,
    methodology_block,
    remembered,
    unconfirmed_scale,
)
from finance_analysis.domain.model_type import Composed, MetricExpression, Side
from finance_analysis.domain.net_cash_flow import net_cash_flow
from finance_analysis.domain.period_basis import _as_date, basis_of
from finance_analysis.domain.returns import fcf_identity, project_return

DEFAULT_DEFINITION_TEXT = "определение по умолчанию, не из договора"
_WINDOWS = frozenset({"LTM", "period"})
_FIELDS = frozenset({"numerator", "denominator", "window", "basis_ref", "variant"})
_VARIANT_FIELDS = frozenset({"variant", "basis_ref"})
_SIDE_FIELDS = frozenset({"plus", "minus"})
_CYCLE = frozenset({"dscr", "dscr_covenant"})
_REPORTED_READ = "dscr.reported"
_MISMATCH = Decimal("0.005")
_CASH_OTHER = "other_financial_debt_service"
_CASH_CORE = ("operating_cash_flow", "interest_paid", "capex", "principal")
_CAPITALIZED_INTEREST = re.compile(r"(?<!\d)4224(?!\d)")
CAPITALIZED_INTEREST = (
    "Проценты в стоимости инвестиционного актива, в надбавку к OCF не входят."
)
# shortcut: год i — календарный год по дате конца периода, другой финансовый год — когда в книге появится дата закрытия года
PARTIAL_YEAR = (
    "Год i неполный: нет непрерывных двенадцати месяцев до 31 декабря. Коэффициент не рассчитан."
)


def _number(value) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, dict):
        return any(_number(item) for item in value.values())
    if isinstance(value, list):
        return any(_number(item) for item in value)
    return False


def _terms(side: dict) -> list:
    return [*(side.get("plus") or []), *(side.get("minus") or [])]


def dscr_definition_error(
    value,
    *,
    concepts: frozenset[str],
    money: frozenset[str],
    variants: frozenset[str] | None = None,
) -> str | None:
    """None — структуру можно сохранить. Числа, чужие понятия и цикл отвергаются."""

    if not isinstance(value, dict) or set(value) - _FIELDS or _number(value):
        return "dscr_definition: только состав числителя и знаменателя, окно и basis_ref, без чисел"
    if "variant" in value:
        return _variant_error(value, variants or frozenset())
    if value.get("window") not in _WINDOWS:
        return "dscr_definition: окно LTM или period"
    if "basis_ref" in value and not isinstance(value["basis_ref"], str):
        return "dscr_definition: basis_ref — строка"
    for name in ("numerator", "denominator"):
        problem = _side_error(value.get(name), concepts, money, name)
        if problem:
            return problem
    if not _terms(value["numerator"]):
        return "dscr_definition: числитель не пуст"
    if not _terms(value["denominator"]):
        return "dscr_definition: знаменатель не пуст"
    return None


def _variant_error(value: dict, variants: frozenset[str]) -> str | None:
    name = value.get("variant")
    if not isinstance(name, str) or not name:
        return "dscr_definition: variant — имя варианта"
    if set(value) - _VARIANT_FIELDS:
        return "dscr_definition: либо имя варианта, либо состав"
    if name not in variants:
        return "dscr_definition: неизвестный вариант"
    if "basis_ref" in value and not isinstance(value["basis_ref"], str):
        return "dscr_definition: basis_ref — строка"
    return None


def _named_variant(profile: dict | None) -> str | None:
    raw = (profile or {}).get("dscr_definition")
    if not isinstance(raw, dict) or "numerator" in raw or "denominator" in raw:
        return None
    name = raw.get("variant")
    if not isinstance(name, str) or not name:
        return None
    return name


def _variant_ids(composed: dict[str, Composed] | None) -> frozenset[str]:
    return frozenset(key.removeprefix("dscr.") for key in (composed or {}) if key.startswith("dscr."))


def _side_error(side, concepts: frozenset[str], money: frozenset[str], name: str) -> str | None:
    if not isinstance(side, dict) or set(side) - _SIDE_FIELDS:
        return f"dscr_definition: {name} — plus и minus"
    terms = _terms(side)
    if any(not isinstance(item, str) for item in terms):
        return f"dscr_definition: {name} — id понятий"
    if any(item not in concepts for item in terms):
        return "dscr_definition: понятие вне каталога"
    if any(item in _CYCLE for item in terms):
        return "dscr_definition: цикл на dscr"
    if any(item not in money for item in terms):
        return "dscr_definition: слагаемые должны быть деньгами"
    return None


def _parse(value: dict) -> Composed:
    return Composed(_as_side(value["numerator"]), _as_side(value["denominator"]), str(value["window"]))


def profile_formula(
    raw,
    *,
    concepts: frozenset[str],
    money: frozenset[str],
    variants: frozenset[str] | None = None,
) -> tuple[MetricExpression | None, str | None, str | None, str | None]:
    """Один разбор профиля для ``resolve_covenant`` и сборки определения.

    Возвращает выражение, окно, пункт и текст ошибки. Ошибка значит, что состав
    не подменяет каталог. Именованный вариант ошибки не имеет и сторон не возвращает.
    """

    problem = dscr_definition_error(raw, concepts=concepts, money=money, variants=variants)
    if problem:
        return None, None, None, problem
    if isinstance(raw, dict) and "variant" in raw:
        basis = raw.get("basis_ref")
        return None, None, basis if isinstance(basis, str) else None, None
    parsed = _parse(raw)
    numerator = raw["numerator"] if isinstance(raw.get("numerator"), dict) else {}
    denominator = raw["denominator"] if isinstance(raw.get("denominator"), dict) else {}
    basis = raw.get("basis_ref")
    return (
        MetricExpression(
            numerator_plus=tuple(numerator.get("plus") or ()),
            numerator_minus=tuple(numerator.get("minus") or ()),
            denominator_plus=tuple(denominator.get("plus") or ()),
            denominator_minus=tuple(denominator.get("minus") or ()),
        ),
        parsed.window,
        basis if isinstance(basis, str) else None,
        None,
    )


def profile_dscr_expression(profile: dict | None) -> MetricExpression | None:
    """Неименованный состав профиля. Именованный вариант остаётся формулой каталога."""

    raw = (profile or {}).get("dscr_definition")
    if not isinstance(raw, dict) or "numerator" not in raw or "denominator" not in raw:
        return None
    numerator = raw["numerator"] if isinstance(raw["numerator"], dict) else {}
    denominator = raw["denominator"] if isinstance(raw["denominator"], dict) else {}
    return MetricExpression(
        numerator_plus=tuple(numerator.get("plus") or ()),
        numerator_minus=tuple(numerator.get("minus") or ()),
        denominator_plus=tuple(denominator.get("plus") or ()),
        denominator_minus=tuple(denominator.get("minus") or ()),
    )


def _as_side(raw: dict) -> Side:
    return Side(tuple(raw.get("plus") or ()), tuple(raw.get("minus") or ()))


def resolve_covenant(
    profile: dict | None,
    profile_ref: str | None,
    default: Composed,
    *,
    concepts: frozenset[str],
    money: frozenset[str],
    composed: dict[str, Composed] | None = None,
) -> tuple[Composed, str, dict | None, list[dict]]:
    raw = (profile or {}).get("dscr_definition")
    note = {"code": "dscr_default_definition", "params": {"text": DEFAULT_DEFINITION_TEXT}}
    if not raw:
        return default, "default", None, [note]
    known = _variant_ids(composed)
    expression, window, _basis, problem = profile_formula(raw, concepts=concepts, money=money, variants=known)
    if problem:
        return default, "default", None, [note, {"code": "dscr_definition_invalid", "params": {"reason": problem}}]
    ref = {
        "profile_id": profile_ref.split("@", 1)[0] if profile_ref and "@" in profile_ref else profile_ref,
        "profile_version": profile_ref,
        "basis_ref": raw.get("basis_ref"),
    }
    named = _named_variant(profile)
    if named:
        return composed[f"dscr.{named}"], "profile", ref, []
    return (
        Composed(
            Side(expression.numerator_plus, expression.numerator_minus),
            Side(expression.denominator_plus, expression.denominator_minus),
            window or "period",
        ),
        "profile",
        ref,
        [],
    )


# Договорный состав без имени варианта. interest_paid — отдельное понятие, не синоним interest.
_CORPORATE_PROFILE_INPUTS = (
    "ebitda",
    "cash_taxes",
    "capex",
    "operating_cash_flow",
    "interest",
    "interest_paid",
    "principal",
)


@implements(
    "dscr",
    "dscr.corporate_covenant",
    profile_inputs=_CORPORATE_PROFILE_INPUTS,
    mode="dynamic",
    reason="состав заменяет профиль",
    implementation_version="dscr.corporate_covenant@1",
    profile_field="dscr_definition",
    unnamed_profile=True,
)
def covenant_dscr(
    *,
    facts: list[dict],
    bindings: list[dict],
    periods: list[dict],
    default: Composed,
    concepts: frozenset[str],
    money: frozenset[str],
    profile: dict | None = None,
    profile_ref: str | None = None,
    sign_convention: str = "outflow_negative",
    marker_class: str | None = None,
    absent: frozenset[str] = frozenset(),
    interest_order: dict | None = None,
    row_fallbacks: dict | None = None,
    composed: dict[str, Composed] | None = None,
    aggregations: Mapping[str, str] | None = None,
    plan: Any | None = None,
    outflows: frozenset[str] | None = None,
) -> dict:
    definition, source, ref, notes = resolve_covenant(
        profile, profile_ref, default, concepts=concepts, money=money, composed=composed
    )
    order_name = _named_variant(profile) if source == "profile" else None
    orders = interest_order or {}
    order = orders.get(order_name or "corporate_covenant", ())
    if not order:
        order = orders.get("corporate_covenant", ())
    if plan is not None:
        definition, notes, bindings = _apply_plan(definition, notes, plan, bindings)
    else:
        primaries = _primaries(bindings, absent)
        injected = confirm_paid_interest(primaries, bindings, absent)
        definition, fallback = _swap_interest(
            definition,
            primaries,
            order,
            row_fallbacks=row_fallbacks,
        )
        if injected is not None:
            bindings = [*bindings, injected]
        if fallback:
            notes = [*notes, fallback]
    result = composed_ratio(
        "dscr",
        definition,
        facts=facts,
        bindings=bindings,
        periods=periods,
        sign_convention=sign_convention,
        marker_class=marker_class,
        absent=absent,
        profile=profile,
        aggregations=aggregations,
        plan=plan,
        outflows=outflows,
    )
    if source == "default" and result["status"] == "succeeded":
        notes = [*notes, *_mismatch(result["rows"], facts, bindings, periods, absent)]
    return {**result, "warnings": [*notes, *result["warnings"]], "definition_source": source, "definition_ref": ref}


# Состав каталога dscr.ocf_covenant. interest_paid — запасной вход по interest_order, а не синоним interest: это разные понятия.
OCF_COVENANT_INPUTS = ("operating_cash_flow", "interest", "capex", "principal")
OCF_COVENANT_OPTIONAL = ("interest_paid",)
# resolve_covenant может подставить договор с понятиями корпоративного состава.
OCF_COVENANT_PROFILE = ("ebitda", "cash_taxes")


@implements(
    "dscr",
    "dscr.ocf_covenant",
    implementation_version="dscr.ocf_covenant@1",
    inputs=OCF_COVENANT_INPUTS,
    optional_inputs=OCF_COVENANT_OPTIONAL,
    profile_inputs=OCF_COVENANT_PROFILE,
    profile_field="dscr_definition",
    unnamed_profile=True,
)
def dscr_ocf_covenant(
    *,
    facts: list[dict],
    bindings: list[dict],
    periods: list[dict],
    default: Composed,
    concepts: frozenset[str],
    money: frozenset[str],
    profile: dict | None = None,
    profile_ref: str | None = None,
    sign_convention: str = "outflow_negative",
    marker_class: str | None = None,
    absent: frozenset[str] = frozenset(),
    interest_order: dict | None = None,
    row_fallbacks: dict | None = None,
    composed: dict[str, Composed] | None = None,
    aggregations: Mapping[str, str] | None = None,
    plan: Any | None = None,
    outflows: frozenset[str] | None = None,
) -> dict:
    """OCF-ковенант по составу каталога. Нет входов состава — метрика не считается, CFADS не подставляется."""

    if plan is not None:
        from finance_analysis.domain.resolved_plan import bindings_for_plan

        bindings = list(bindings_for_plan(bindings, plan))
    return covenant_dscr(
        facts=facts,
        bindings=bindings,
        periods=periods,
        default=default,
        concepts=concepts,
        money=money,
        profile=profile,
        profile_ref=profile_ref,
        sign_convention=sign_convention,
        marker_class=marker_class,
        absent=absent,
        interest_order=interest_order,
        row_fallbacks=row_fallbacks,
        composed=composed,
        aggregations=aggregations,
        plan=plan,
        outflows=outflows,
    )


def _unplanned(metric: str, names: list[str]) -> dict:
    """Понятие формулы нет среди подтверждённых входов плана. Привязки не сканируются."""

    return {
        "metric": metric,
        "rows": [],
        "needs_input": [{"kind": "concept", "reason": "concept_unknown", "subject": names[0]}],
        "missing_inputs": names,
        "warnings": [],
        "status": "missing_input",
    }


def _definition_formula(definition) -> Composed | str | None:
    """Стороны определения. Форма вне плюс/минус/окно не считается прежней формулой."""

    if definition is None:
        return None
    expr = definition.normalized_expression
    if (
        expr.one_of
        or expr.rate
        or expr.rates
        or expr.aggregate
        or expr.terminal
        or expr.compare_with
        or expr.add_back
        or expr.base
    ):
        return "unsupported_formula"
    if not (expr.numerator_plus or expr.numerator_minus):
        return "unsupported_formula"
    if not (expr.denominator_plus or expr.denominator_minus):
        return "unsupported_formula"
    if expr.window not in _WINDOWS:
        return "unsupported_formula"
    return Composed(
        Side(expr.numerator_plus, expr.numerator_minus),
        Side(expr.denominator_plus, expr.denominator_minus),
        expr.window,
    )


def _composed_stop(metric: str, reason: str) -> dict:
    return {
        "metric": metric,
        "rows": [],
        "needs_input": [],
        "missing_inputs": [],
        "warnings": [],
        "status": "not_computed",
        "reason": reason,
        "message": reason,
    }


def _mark_profile(result: dict, definition) -> dict:
    if definition is None or definition.definition_source != "profile":
        return result
    ref = definition.definition_ref
    return {
        **result,
        "definition_source": definition.definition_source,
        "definition_ref": None if ref is None else dict(ref),
    }


def _open_trace(metric: str, definition, collect, sign_convention: str, plan, marker_class: str | None):
    if collect is None or definition is None:
        return None
    return EvidenceBook(
        metric=str(metric),
        sign_convention=sign_convention,
        marker_class=marker_class,
        explicit_phases=False,
        plan_content_sha256=getattr(plan, "content_sha256", None) if plan is not None else None,
    )


def _trace_ready(book: EvidenceBook) -> bool:
    """Готов только период, у которого свои FactUse числителя и знаменателя и непустые ссылки шага.

    Один FactUse на весь расчёт и пустой input_refs этого не заменяют.
    """

    computed = [item for item in book.periods or [] if item.status == "computed"]
    if not computed:
        return False
    for item in computed:
        if item.numerator is None or item.denominator is None or not item.steps:
            return False
        axis = None if item.axis_id is None else str(item.axis_id)
        period_id = None if item.period_id is None else str(item.period_id)
        operands = {
            use.operand
            for use in book.fact_uses or []
            if use.result_axis_id == axis and use.result_period_id == period_id
        }
        if "numerator" not in operands or "denominator" not in operands:
            return False
        assemblies = [step for step in item.steps if step.operation in {"numerator_assembly", "denominator_assembly"}]
        if len(assemblies) != 2 or any(not step.input_refs for step in assemblies):
            return False
    return True


def _fill_periods(book: EvidenceBook, rows: list[dict]) -> None:
    detailed = {(item.axis_id, item.period_id): item for item in book.periods or []}
    ordered = []
    for row in rows:
        key = (row.get("axis_id"), row.get("period_id"))
        found = detailed.get(key)
        if found is not None:
            ordered.append(found)
            continue
        window = row.get("window") or ()
        ordered.append(
            PeriodResult(
                axis_id=row.get("axis_id"),
                period_id=row.get("period_id"),
                status=str(row.get("status")),
                reason=row.get("reason"),
                value=row.get("value"),
                numerator=None,
                denominator=None,
                steps=(),
                window_periods=tuple(window),
            )
        )
    book.periods = ordered


def _remember_composed(
    result: dict, definition, collect, sign_convention: str, plan, book=None, marker_class: str | None = None
) -> dict:
    """Версии определения и исполнителя. Пустой успешный след не публикуется как готовый."""

    if collect is None or definition is None:
        return result
    if book is None:
        book = _open_trace(
            str(result.get("metric") or definition.metric_id),
            definition,
            collect,
            sign_convention,
            plan,
            marker_class,
        )
    assert book is not None
    _fill_periods(book, list(result.get("rows") or []))
    status = result.get("status")
    if status == "succeeded":
        execution = "succeeded"
    elif status in {"scale_unconfirmed", "basis_mismatch", "input_absent"}:
        execution = "refused"
    else:
        execution = "not_run"
    from finance_analysis.domain.calculation_evidence import composed_calculation_stamp

    ready = execution == "succeeded" and _trace_ready(book)
    collect.append(
        book.freeze(
            execution,
            "",
            evidence_status="evidence_available" if ready else "evidence_unavailable",
            stamp=composed_calculation_stamp(),
            calculation_origin="calculated",
            **definition_fields(definition),
        )
    )
    return result


def _publish_composed(
    result: dict, definition, collect, sign_convention: str, plan, book=None, marker_class: str | None = None
) -> dict:
    return _remember_composed(
        _mark_profile(result, definition), definition, collect, sign_convention, plan, book, marker_class
    )


def composed_ratio(
    metric: str,
    formula: Composed,
    *,
    facts: list[dict],
    bindings: list[dict],
    periods: list[dict],
    sign_convention: str = "outflow_negative",
    marker_class: str | None = None,
    absent: frozenset[str] = frozenset(),
    profile: dict | None = None,
    aggregations: Mapping[str, str] | None = None,
    plan: Any | None = None,
    definition: Any | None = None,
    collect: list | None = None,
    outflows: frozenset[str] | None = None,
) -> dict:
    book = _open_trace(metric, definition, collect, sign_convention, plan, marker_class)

    def finish(result: dict) -> dict:
        return _publish_composed(result, definition, collect, sign_convention, plan, book, marker_class)

    resolved = _definition_formula(definition)
    if isinstance(resolved, str):
        return finish(_composed_stop(metric, resolved))
    if resolved is not None:
        formula = resolved
    if outflows is not None:
        plus_names = (*formula.numerator.plus, *formula.denominator.plus)
        formula = Composed(
            formula.numerator,
            formula.denominator,
            formula.window,
            frozenset(name for name in plus_names if name in outflows),
        )
    if definition is not None and plan is not None and (
        plan.metric_id != definition.metric_id
        or plan.variant != definition.variant
        or plan.variant_source != definition.variant_source
        or plan.definition_hash != definition.definition_hash
    ):
        return finish(_composed_stop(metric, "definition_mismatch"))
    blocked = methodology_block(
        profile,
        bindings,
        metric=metric,
        names=(
            *formula.numerator.plus,
            *formula.numerator.minus,
            *formula.denominator.plus,
            *formula.denominator.minus,
        ),
    )
    if blocked:
        return finish(blocked)
    if plan is not None and plan.status in {"needs_input", "missing_input"}:
        needs = [item.as_dict() for item in plan.needs_input]
        return finish(
            {
                "metric": metric,
                "rows": [],
                "needs_input": needs,
                "missing_inputs": [item.subject for item in plan.needs_input],
                "warnings": [item.as_dict() for item in plan.warnings],
                "status": plan.status,
            }
        )
    confirmed: frozenset[str] | None = None
    primaries: dict | None = None
    if plan is not None:
        from finance_analysis.domain.resolved_plan import bound_rows

        primaries = bound_rows(plan, bindings)
        confirmed = frozenset(item.concept for item in plan.inputs)
        if definition is not None:
            declared = (
                set(formula.numerator.plus)
                | set(formula.numerator.minus)
                | set(formula.denominator.plus)
                | set(formula.denominator.minus)
            )
            for item in plan.inputs:
                if item.confirmed and not item.ambiguous and item.concept not in declared:
                    raise UndeclaredInput(item.concept)
    unbound: frozenset[str] = frozenset()
    if plan is None and "off_balance_obligations" in formula.numerator.plus:
        bound = _primaries(bindings, absent)
        others = [name for name in formula.numerator.plus if name != "off_balance_obligations"]
        if "off_balance_obligations" not in bound and any(name in bound for name in others):
            unbound = frozenset({"off_balance_obligations"})
    needed = (
        *formula.numerator.plus,
        *formula.numerator.minus,
        *formula.denominator.plus,
        *formula.denominator.minus,
    )
    needed = tuple(name for name in needed if name not in unbound)
    if plan is not None:
        outside = [name for name in needed if name not in (confirmed or frozenset())]
        if outside:
            return finish(_unplanned(metric, outside))
        lost = [name for name in needed if name not in (primaries or {})]
        if lost:
            return finish(_unplanned(metric, lost))
    else:
        missing = _missing(metric, bindings, needed, absent)
        if missing:
            return finish(missing)
        primaries = _primaries(bindings, absent)
    assert primaries is not None
    inputs = list(dict.fromkeys(needed))
    if unconfirmed_scale(facts, [primaries[name] for name in inputs]):
        return finish(_refused(metric, periods, "scale_unconfirmed", SCALE_UNCONFIRMED, inputs))
    flow = {_flow_basis(primaries[name]) for name in inputs}
    reconciled = formula.window == "LTM" or (formula.window == "period" and _rolls(primaries, formula))
    if len(flow) > 1 and not reconciled:
        return finish(_refused(metric, periods, "basis_mismatch", MIXED_BASIS, inputs))
    warnings: list[dict] = []
    sheet = _assume_sheet_units(facts, [primaries[name] for name in inputs], warnings)
    aligned = aligned_keys(periods)
    series = {
        name: _sums(
            facts,
            primaries[name],
            aligned,
            periods,
            sheet=sheet,
            book=book,
            concept=name,
        )
        for name in dict.fromkeys(needed)
    }
    basis = {name: basis_of(primaries[name])[0] for name in series}
    roll = formula.window == "period" and _rolls(primaries, formula)
    window_name = "LTM" if roll else formula.window
    num_names = (*formula.numerator.plus, *formula.numerator.minus)
    den_names = (*formula.denominator.plus, *formula.denominator.minus)
    num_default = "last" if aggregations is None and metric in _EBITDA_STOCK else "sum"
    # Поток со способом `ltm` уже покрывает двенадцать месяцев: полное окно не требуется.
    folds = {name: _term_fold(name, aggregations, num_default) for name in num_names}
    folds.update({name: _term_fold(name, aggregations, "sum") for name in den_names})
    summed = [name for name, fold in folds.items() if fold == "sum"]
    flow_ltm = bool(summed) and all(basis.get(name) == "ltm" for name in summed)
    span_name = "period" if flow_ltm else window_name
    numerator_stock = _all_last(num_names, aggregations, num_default)
    absent_message = _stock_message(num_names)
    home_name = formula.denominator.plus[0] if formula.denominator.plus else formula.denominator.minus[0]
    shared = frozenset(formula.numerator.plus) & frozenset(formula.denominator.plus)
    payment_terms = formula.payment_terms
    rows = []
    for axis in sorted(_axes_of(facts, primaries[home_name])):
        ordered = _ordered(periods, axis)
        axis_keys = [aligned.get((axis, item["period_id"]), (axis, item["period_id"])) for item in ordered]
        dated = numerator_stock and any(
            _stock_choice(item, periods, aligned, series.get(name) or {})[0] is not None
            for item in ordered
            for name in num_names
        )
        on_axis = any(key in (series.get(name) or {}) for name in num_names for key in axis_keys)
        debt_on_axis = not (numerator_stock and window_name == "LTM") or on_axis or dated
        for period in ordered:
            if unbound:
                rows.append(
                    _line(
                        metric,
                        period,
                        None,
                        "input_absent",
                        "input_absent",
                        list(dict.fromkeys((*inputs, *unbound))),
                        None,
                        message=_OFF_BALANCE_ABSENT,
                    )
                )
                continue
            marker = period.get("marker_class")
            if marker_class and marker and marker != marker_class:
                continue
            keys, window, problem = _span(span_name, ordered, period, aligned, axis)
            if problem and not debt_on_axis:
                rows.append(
                    _line(
                        metric, period, None, "input_absent", "input_absent", inputs, window, message=absent_message
                    )
                )
                continue
            if problem:
                message = PARTIAL_DENOMINATOR if roll and problem == "partial_window" else None
                rows.append(_line(metric, period, None, "not_computed", problem, inputs, window, message=message))
                continue
            numerator, num_fold, num_used = _fold_side(
                keys,
                series,
                formula.numerator,
                aggregations=aggregations,
                default=num_default,
                pay_plus=False,
                pay_names=shared,
                pay_terms=payment_terms,
                convention=sign_convention,
                basis=basis,
                period=period,
                periods=periods,
                aligned=aligned,
            )
            denominator, den_fold, den_used = _fold_side(
                keys,
                series,
                formula.denominator,
                aggregations=aggregations,
                default="sum",
                pay_plus=False,
                pay_names=frozenset(),
                pay_terms=payment_terms,
                convention=sign_convention,
                basis=basis,
                period=period,
                periods=periods,
                aligned=aligned,
            )
            fold_problem = num_fold or den_fold
            if fold_problem:
                text = _AMBIGUOUS_STOCK if fold_problem == "ambiguous_stock" else None
                rows.append(_line(metric, period, None, "not_computed", fold_problem, inputs, window, message=text))
                continue
            if numerator_stock and numerator is None and not _series_present(keys, series, num_names):
                rows.append(
                    _line(
                        metric,
                        period,
                        None,
                        "input_absent",
                        "input_absent",
                        inputs,
                        window,
                        message=absent_message,
                    )
                )
                continue
            if numerator is None or denominator is None:
                rows.append(_line(metric, period, None, "missing_input", "no_binding", inputs, window))
                continue
            _cite_used(book, period, aligned, num_used, "numerator")
            _cite_used(book, period, aligned, den_used, "denominator")
            steps: list = []
            _step(steps, "numerator_assembly", _operand_refs(book, period, "numerator"), numerator)
            _step(steps, "denominator_assembly", _operand_refs(book, period, "denominator"), denominator)
            if denominator == 0:
                status = "no_debt_service" if metric == "dscr" else "missing_input"
                _record_period(book, period, status, "zero_denominator", None, numerator, denominator, steps, window)
                rows.append(_line(metric, period, None, status, "zero_denominator", inputs, window))
                continue
            value = _ratio(numerator, denominator)
            _step(steps, "ratio", ("step:1", "step:2"), value)
            _record_period(book, period, "computed", None, value, numerator, denominator, steps, window)
            line = _line(metric, period, value, "computed", None, inputs, window)
            if metric == "net_debt_ebitda":
                used = [period] if flow_ltm else [item for item in ordered if item["period_id"] in set(window or [])]
                line["components"] = {
                    name: _component_cells(facts, primaries[name], _same_end(periods, period)) for name in num_names
                }
                line["components"].update(
                    {
                        name: _component_cells(facts, primaries[name], used or [period])
                        for name in den_names
                    }
                )
            rows.append(line)
    if metric == "escrow_coverage":
        warnings.extend(_escrow_coverage_book(rows, facts, bindings, periods, absent, warnings))
    status = "succeeded"
    message = None
    stock_absent = numerator_stock and window_name == "LTM" and any(row["status"] == "input_absent" for row in rows)
    if stock_absent and not any(row["status"] == "computed" for row in rows):
        status = "input_absent"
        message = next((row.get("message") for row in rows if row.get("message")), absent_message)
    elif roll and rows and not any(row["status"] == "computed" for row in rows):
        if any(row.get("reason") == "partial_window" for row in rows):
            status = "partial_window"
            message = PARTIAL_DENOMINATOR
    elif any(row.get("reason") == "ambiguous_stock" for row in rows) and not any(row["status"] == "computed" for row in rows):
        status = "not_computed"
        message = _AMBIGUOUS_STOCK
    elif any(row.get("reason") in {"not_folded", "aggregation_unknown"} for row in rows) and not any(
        row["status"] == "computed" for row in rows
    ):
        status = "not_computed"
    result = {"metric": metric, "rows": rows, "needs_input": [], "warnings": warnings, "status": status}
    if message:
        result["message"] = message
    return finish(result)


_KNOWN_FOLDS = frozenset({"sum", "last", "average", "none"})


def _term_fold(name: str, aggregations: Mapping[str, str] | None, default: str) -> str | None:
    if aggregations is None:
        return default
    fold = aggregations.get(name)
    if fold not in _KNOWN_FOLDS:
        return None
    return fold


def _all_last(names: tuple[str, ...], aggregations: Mapping[str, str] | None, default: str) -> bool:
    return bool(names) and all(_term_fold(name, aggregations, default) == "last" for name in names)


def _series_present(keys, series: dict, names: tuple[str, ...]) -> bool:
    return any(key in (series.get(name) or {}) for name in names for key in keys)


def _stock_message(names: tuple[str, ...]) -> str:
    if "off_balance_obligations" in names:
        return _OFF_BALANCE_ABSENT
    if names == ("net_debt",):
        return _NET_DEBT_ABSENT
    return _STOCK_ABSENT


def _fold_side(
    keys,
    series: dict,
    side: Side,
    *,
    aggregations: Mapping[str, str] | None,
    default: str,
    pay_plus: bool,
    pay_names: frozenset[str],
    pay_terms: frozenset[str],
    convention: str,
    basis: dict,
    period: dict,
    periods: list[dict],
    aligned: dict,
) -> tuple[Decimal | None, str | None, tuple[tuple[str, tuple], ...]]:
    """Остаток (`last`) берётся на дату, поток складывается окном. Неизвестная свёртка не подменяется."""

    total = Decimal(0)
    used: list[tuple[str, tuple]] = []
    for name, sign, forced_pay in (
        *((item, 1, False) for item in side.plus),
        *((item, -1, True) for item in side.minus),
    ):
        fold = _term_fold(name, aggregations, default)
        if fold is None:
            return None, "aggregation_unknown", ()
        if fold == "last":
            value, problem, key = _stock_choice(period, periods, aligned, series.get(name) or {})
            if problem:
                return None, problem, ()
            if value is None or key is None:
                return None, None, ()
            total += sign * value
            used.append((name, key))
            continue
        chosen, problem = _chosen_keys(keys, name, basis, aggregations)
        if problem:
            return None, problem, ()
        pay = forced_pay or pay_plus or name in pay_names or name in pay_terms
        part, problem = _part(keys, series, name, convention, pay, basis, aggregations)
        if problem:
            return None, problem, ()
        if part is None:
            return None, None, ()
        total += sign * part
        used.extend((name, key) for key in chosen or ())
    return total, None, tuple(used)


def _rolls(primaries: dict, formula: Composed) -> bool:
    """Числитель `ltm` и знаменатель за период: знаменатель собирается окном LTM.

    Привязка строк не меняется. Окно уже заданное как LTM здесь не подменяется.
    """

    numerator = [*formula.numerator.plus, *formula.numerator.minus]
    denominator = [*formula.denominator.plus, *formula.denominator.minus]
    if not numerator or not denominator:
        return False
    if any(_flow_basis(primaries[name]) != "ltm" for name in numerator):
        return False
    return all(_flow_basis(primaries[name]) == "period" for name in denominator)


_LEASE_MODES = frozenset({"in_interest", "add_interest", "nominal"})
_DENOMINATOR_FIELDS = ("source", "binding", "axis", "period", "standard", "method")
_DENOMINATOR_METHODS = frozenset({"interest_expense", "capitalised", "interest_paid"})
_QUARTER_LABEL = "за квартал, справочно"


def icr_definition_error(value) -> str | None:
    """None — профиль можно сохранить. Чисел и чужих полей нет."""

    if not isinstance(value, dict) or _number(value):
        return "icr_definition: variant и lease_mode, без чисел"
    if set(value) - {"variant", "lease_mode", "denominator", "finance_costs_confirmed", "include_rou_depreciation"}:
        return "icr_definition: только variant, lease_mode, denominator, finance_costs_confirmed и include_rou_depreciation"
    if "variant" in value and value.get("variant") != "bank":
        return "icr_definition: variant bank"
    mode = value.get("lease_mode")
    if mode is not None and mode not in _LEASE_MODES:
        return "icr_definition: lease_mode in_interest, add_interest или nominal"
    if "finance_costs_confirmed" in value and not isinstance(value.get("finance_costs_confirmed"), bool):
        return "icr_definition: finance_costs_confirmed — да или нет"
    if "include_rou_depreciation" in value and not isinstance(value.get("include_rou_depreciation"), bool):
        return "icr_definition: include_rou_depreciation — да или нет"
    if "denominator" in value:
        return _denominator_error(value.get("denominator"))
    return None


def _denominator_error(value) -> str | None:
    if not isinstance(value, dict) or set(value) != set(_DENOMINATOR_FIELDS):
        return "icr_definition: denominator — source, binding, axis, period, standard, method"
    for key in ("source", "binding", "axis", "period", "standard"):
        item = value.get(key)
        if not isinstance(item, str) or not item.strip():
            return "icr_definition: denominator — непустые source, binding, axis, period, standard"
    if value.get("method") not in _DENOMINATOR_METHODS:
        return "icr_definition: method interest_expense, capitalised или interest_paid"
    return None


def bank_requested(variant: str | None, profile: dict | None) -> bool:
    """Внутренний профиль icr.bank. Сам по себе он не считается."""

    raw = (profile or {}).get("icr_definition")
    if isinstance(raw, dict) and raw.get("variant") == "bank":
        return True
    return variant == "bank"


def _icr_mode(profile: dict | None) -> str | None:
    raw = (profile or {}).get("icr_definition")
    if not isinstance(raw, dict):
        return None
    mode = raw.get("lease_mode")
    return mode if isinstance(mode, str) else None


def _ask(metric: str, subject: str, reason: str) -> dict:
    return {
        "metric": metric,
        "rows": [],
        "needs_input": [{"kind": "concept", "reason": reason, "subject": subject}],
        "warnings": [],
        "status": "needs_input",
        "missing_inputs": [subject],
    }


def _sign_name(value: Decimal) -> str:
    if value > 0:
        return "positive"
    if value < 0:
        return "negative"
    return "zero"


_FISCAL_REASONS = frozenset({"fiscal_calendar_unknown", "fiscal_calendar_mismatch"})


def _quarter_of(period: dict, year_end_month: int) -> int | None:
    """Квартал финансового года: 4-й кончается в месяц закрытия, не в декабре."""

    end = _as_date(period.get("period_end"))
    if end is None:
        return None
    return {0: 4, 3: 1, 6: 2, 9: 3}.get((end.month - year_end_month) % 12)


def _fiscal_year_of(period: dict, month: int, day: int) -> int | None:
    """Год, в котором финансовый год заканчивается."""

    end = _as_date(period.get("period_end"))
    if end is None:
        return None
    if (end.month, end.day) <= (month, day):
        return end.year
    return end.year + 1


def _same_slot(ordered: list[dict], year: int, quarter: int, month: int, day: int) -> dict | None:
    for item in ordered:
        if _fiscal_year_of(item, month, day) == year and _quarter_of(item, month) == quarter:
            return item
    return None


def _aligned_key(period: dict, aligned: dict):
    own = (period.get("axis_id"), period.get("period_id"))
    return aligned.get(own, own)


def _ytd_ltm(series: dict, period: dict, ordered: list[dict], aligned: dict):
    """LTM = YTD + прошлый финансовый год − YTD того же квартала прошлого года.

    Полный год (4-й квартал финансового года или зерно от 12 месяцев) уже равен LTM.
    Нет конца года — причина fiscal_calendar_unknown или fiscal_calendar_mismatch.
    """

    current = series.get(_aligned_key(period, aligned))
    if current is None:
        return None, "needs_input"
    calendar = _fiscal_calendar(ordered)
    if isinstance(calendar, str):
        return None, calendar
    month, day = calendar
    months = grain_months(period.get("grain"))
    if months is not None and months >= 12:
        return current, None
    year = _fiscal_year_of(period, month, day)
    quarter = _quarter_of(period, month)
    if year is None or quarter is None:
        return None, "fiscal_calendar_mismatch"
    if quarter == 4:
        return current, None
    prior_end = _same_slot(ordered, year - 1, 4, month, day)
    prior_same = _same_slot(ordered, year - 1, quarter, month, day)
    if prior_end is None or prior_same is None:
        return None, "needs_input"
    problem = _ytd_comparable(period, prior_same, prior_end, month)
    if problem:
        return None, problem
    full_year = series.get(_aligned_key(prior_end, aligned))
    prior = series.get(_aligned_key(prior_same, aligned))
    if full_year is None or prior is None:
        return None, "needs_input"
    return current + full_year - prior, None


def _span_days(period: dict) -> int | None:
    start = _as_date(period.get("period_start"))
    end = _as_date(period.get("period_end"))
    if start is None or end is None or end < start:
        return None
    return (end - start).days


def _fiscal_quarter_month(year_end_month: int, quarter: int) -> int:
    month = (year_end_month + 3 * (quarter - 4)) % 12
    return 12 if month == 0 else month


def _dated_quarter(period: dict):
    months = grain_months(period.get("grain"))
    if months != 3:
        return None
    start = _as_date(period.get("period_start"))
    end = _as_date(period.get("period_end"))
    if start is None or end is None or end < start:
        return None
    return start, end


def _fiscal_calendar(ordered: list[dict]) -> tuple[int, int] | str:
    """(месяц, день) конца финансового года либо причина, почему его нет.

    Годовой период задаёт конец, если такие концы совпадают. Иначе конец — закрытие
    четырёх смежных кварталов от самого раннего period_start на оси. Первый квартал
    оси при этом читается как Q1: серия с середины года без годового периода от Q1
    не отличается.
    """

    annuals = []
    quarters = []
    for item in ordered:
        end = _as_date(item.get("period_end"))
        months = grain_months(item.get("grain"))
        if end is None or months is None:
            continue
        if months >= 12:
            annuals.append((end.month, end.day))
        elif _dated_quarter(item) is not None:
            quarters.append(item)
    annual_end = None
    if annuals:
        if len(set(annuals)) != 1:
            return "fiscal_calendar_mismatch"
        annual_end = annuals[0]
    quarter_end = _quarter_year_end(quarters)
    if isinstance(quarter_end, str):
        return quarter_end
    if annual_end is not None and quarter_end is not None and annual_end != quarter_end:
        return "fiscal_calendar_mismatch"
    found = annual_end or quarter_end
    if found is None:
        return "fiscal_calendar_unknown"
    if not _quarters_on_grid(quarters, found[0]):
        return "fiscal_calendar_mismatch"
    return found


def _quarter_year_end(quarters: list[dict]) -> tuple[int, int] | str | None:
    dated = []
    for item in quarters:
        pair = _dated_quarter(item)
        if pair is None:
            return "fiscal_calendar_mismatch"
        dated.append(pair)
    if len(dated) < 4:
        return None
    dated.sort(key=lambda row: row[1])
    anchor = min(start for start, _end in dated)
    anchor_key = (anchor.month, anchor.day)
    closings = []
    for index in range(len(dated) - 3):
        block = dated[index : index + 4]
        if not _contiguous(block):
            continue
        if (block[0][0].month, block[0][0].day) != anchor_key:
            continue
        rolled = block[-1][1] + timedelta(days=1)
        if (rolled.month, rolled.day) != anchor_key:
            continue
        closings.append((block[-1][1].month, block[-1][1].day))
    if not closings:
        return None
    if len(set(closings)) != 1:
        return "fiscal_calendar_mismatch"
    return closings[0]


def _contiguous(block: list[tuple]) -> bool:
    for index in range(len(block) - 1):
        if block[index][1] + timedelta(days=1) != block[index + 1][0]:
            return False
    return True


def _quarters_on_grid(quarters: list[dict], year_end_month: int) -> bool:
    for item in quarters:
        if _quarter_of(item, year_end_month) is None:
            return False
    return True


def _ytd_comparable(current: dict, prior_same: dict, prior_end: dict, year_end_month: int) -> str | None:
    """None — кварталы одного финансового года сравнимы. Иначе причина needs_input.

    Консолидация и учётная база в метаданных периода не лежат: их проверяет договор
    вызова, не эта функция.
    """

    if grain_months(current.get("grain")) != grain_months(prior_same.get("grain")):
        return "needs_input"
    if grain_months(prior_end.get("grain")) != grain_months(current.get("grain")):
        return "needs_input"
    current_len = _span_days(current)
    prior_len = _span_days(prior_same)
    if current_len is None or prior_len is None or current_len != prior_len or _span_days(prior_end) is None:
        return "needs_input"
    current_end = _as_date(current.get("period_end"))
    prior_end_date = _as_date(prior_same.get("period_end"))
    year_end = _as_date(prior_end.get("period_end"))
    quarter = _quarter_of(current, year_end_month)
    if current_end is None or prior_end_date is None or year_end is None or quarter is None:
        return "fiscal_calendar_mismatch"
    if (current_end.month, current_end.day) != (prior_end_date.month, prior_end_date.day):
        return "needs_input"
    if year_end.month != year_end_month:
        return "fiscal_calendar_mismatch"
    if _fiscal_quarter_month(year_end_month, quarter) != current_end.month:
        return "fiscal_calendar_mismatch"
    return None


def _ytd_step(series: dict, period: dict, ordered: list[dict], aligned: dict):
    """Приращение нарастающего итога за один финансовый квартал. На 4 не умножается."""

    current = series.get(_aligned_key(period, aligned))
    calendar = _fiscal_calendar(ordered)
    if current is None or isinstance(calendar, str):
        return None
    month, day = calendar
    quarter = _quarter_of(period, month)
    year = _fiscal_year_of(period, month, day)
    if quarter is None or year is None:
        return None
    if quarter == 1:
        return current
    previous = _same_slot(ordered, year, quarter - 1, month, day)
    if previous is None:
        return None
    prior = series.get(_aligned_key(previous, aligned))
    if prior is None:
        return None
    return current - prior


def _evidence_of(row: dict) -> dict:
    evidence = row.get("evidence")
    if isinstance(evidence, dict):
        return evidence
    raw = row.get("evidence_json")
    if isinstance(raw, str) and raw:
        try:
            loaded = json.loads(raw)
        except json.JSONDecodeError:
            loaded = {}
        if isinstance(loaded, dict):
            return loaded
    return {}


def _lease_scope(row: dict) -> str:
    scope = _evidence_of(row).get("lease_scope")
    return scope.strip() if isinstance(scope, str) else ""


def _finance_confirmed(profile: dict | None) -> bool:
    raw = (profile or {}).get("icr_definition")
    return isinstance(raw, dict) and raw.get("finance_costs_confirmed") is True


def _denominator(profile: dict | None) -> dict | None:
    raw = (profile or {}).get("icr_definition")
    if not isinstance(raw, dict):
        return None
    item = raw.get("denominator")
    return item if isinstance(item, dict) else None


def _require_interest_expense(profile, primaries, periods, binding_name: str) -> dict | None:
    """Режим in_interest без состава знаменателя число не выпускает.

    Процентный расход, капитализированные затраты и уплаченные проценты — три разных
    знаменателя. Полный лизинговый платёж сюда не подставляется.
    """

    evidence = _denominator(profile)
    if evidence is None or _denominator_error(evidence):
        return _ask("icr", "denominator_evidence", "missing")
    method = evidence.get("method")
    if method == "capitalised":
        return _ask("icr", "capitalised", "capitalised")
    if method == "interest_paid":
        return _ask("icr", "interest_paid", "interest_paid")
    if method != "interest_expense":
        return _ask("icr", "denominator_method", "missing")
    if evidence.get("binding") != binding_name or binding_name not in primaries:
        return _ask("icr", "denominator_evidence", "binding")
    axis = str(evidence.get("axis") or "").strip()
    period = str(evidence.get("period") or "").strip()
    if axis == "each":
        if period != "each":
            return _ask("icr", "denominator_evidence", "axis")
        return None
    pairs = {(item.get("axis_id"), item.get("period_id")) for item in periods}
    if axis not in {item[0] for item in pairs}:
        return _ask("icr", "denominator_evidence", "axis")
    if period != "each" and (axis, period) not in pairs:
        return _ask("icr", "denominator_evidence", "period")
    return None


def _unconfirmed_proxy() -> dict:
    warning = {"code": "finance_cost_proxy", "params": {"concept": "finance_costs"}}
    return {
        "metric": "icr",
        "rows": [],
        "needs_input": [],
        "warnings": [warning],
        "status": "not_computed",
        "message": "состав финансовых расходов не подтверждён",
    }


def _bank_formula(primaries: dict, mode: str, profile: dict | None) -> tuple[Composed | None, list[dict], dict | None]:
    """Знаменатель по режиму аренды. EBIT в формулу не входит. Подписи строки не вычитаются."""

    warnings: list[dict] = []
    if "interest" in primaries:
        plus = ["interest"]
    elif "finance_costs" in primaries:
        if not _finance_confirmed(profile):
            return None, [], _unconfirmed_proxy()
        plus = ["finance_costs"]
        warnings.append({"code": "finance_cost_proxy", "params": {"concept": "finance_costs"}})
        minus: list[str] = []
        if mode == "in_interest" and "lease_interest" in primaries:
            warnings.append({"code": "lease_interest_double_count", "params": {"concept": "lease_interest"}})
        if mode == "add_interest":
            extra_plus, extra_minus, problem = _lease_terms(primaries)
            if problem:
                return None, [], problem
            plus = [*plus, *extra_plus]
            minus = extra_minus
        return (
            Composed(Side(("ebitda",), ()), Side(tuple(plus), tuple(minus)), "LTM"),
            warnings,
            None,
        )
    else:
        return None, [], _ask("icr", "interest", "concept_unknown")
    minus = []
    if mode == "in_interest" and "lease_interest" in primaries:
        warnings.append({"code": "lease_interest_double_count", "params": {"concept": "lease_interest"}})
    if mode == "add_interest":
        extra_plus, extra_minus, problem = _lease_terms(primaries)
        if problem:
            return None, [], problem
        plus = [*plus, *extra_plus]
        minus = extra_minus
    return Composed(Side(("ebitda",), ()), Side(tuple(plus), tuple(minus)), "LTM"), warnings, None


def _lease_terms(primaries: dict) -> tuple[list[str], list[str], dict | None]:
    if "lease_interest" in primaries:
        return ["lease_interest"], [], None
    payments = primaries.get("lease_payments")
    principal = primaries.get("lease_principal")
    if payments is not None and principal is not None:
        scope = _lease_scope(payments)
        if not scope or scope != _lease_scope(principal):
            return [], [], _ask("icr", "lease_scope", "scope_mismatch")
        return ["lease_payments"], ["lease_principal"], None
    return [], [], _ask("icr", "lease_interest", "concept_unknown")


_STATEMENT = frozenset({"ras", "ifrs"})
_RAS_INTEREST = frozenset({"ф.2 (2330)", "ф.2 (070)"})
_LEASE_STANDARD = {
    "ifrs16": "ifrs16",
    "ifrs_16": "ifrs16",
    "fsbu25": "fsbu25",
    "fsbu_25": "fsbu25",
    "operating": "operating",
}
_CAPITAL_LEASE = frozenset({"ifrs16", "fsbu25"})
_VALUE_BASIS = frozenset({"period", "ytd", "annual"})
_DEPRECIATION_MISSING = (
    "Коэффициент не посчитан: нет амортизации из пояснений за тот же период. "
    "Строка EBITDA из модели сюда не подставляется."
)
_STATEMENT_LINE_MISSING = (
    "Коэффициент не посчитан: нет строки прибыли отчётности для выбранной методики расчёта EBITDA. "
    "Строка EBITDA из модели сюда не подставляется."
)
_BASIS_MISMATCH = (
    "Коэффициент не посчитан: база EBITDA не совпадает с базой знаменателя. "
    "РСБУ ждёт строку 2330 или 070, МСФО — финансовые расходы или проценты без этих кодов."
)
_LEASE_DOUBLE = (
    "Коэффициент не посчитан: методика EBITDA по IFRS 16 или ФСБУ 25 не сочетается с режимом add_interest. "
    "Проценты по аренде уже входят в знаменатель."
)
_DEP_PERIOD = "Амортизация пояснений другого зерна. Годовое значение на квартальный LTM не раскладывается."
_ROU_MIXED = (
    "Коэффициент не посчитан: амортизация пояснений включает право пользования, "
    "а отделить эту часть нельзя. В EBITDA по РСБУ она не входит."
)
_ROU_UNKNOWN = (
    "Коэффициент не посчитан: для МСФО не подтверждено, входит ли амортизация права пользования "
    "в сумму пояснений. Нужна строка depreciation_rou или пометка includes_rou."
)
_ROU_MARK = "Коэффициент не посчитан: пометка includes_rou должна быть да или нет и с источником подтверждения."
_DEP_BASIS = (
    "Коэффициент не посчитан: у амортизации нет подтверждённой базы суммы "
    "(value_basis: period, ytd или annual). Зерно периода книги её не заменяет."
)
_INTERNAL_ICR_NOTE = (
    "Внутренний профиль icr.bank. Не ICR по Указанию Банка России № 6960-У. "
    "Числитель — утверждённая формула этого профиля, не универсальная EBITDA по РСБУ."
)


def _held(reason: str, message: str) -> dict:
    return {
        "metric": "icr",
        "rows": [],
        "needs_input": [],
        "missing_inputs": [],
        "warnings": [{"code": reason, "params": {"message": message}}],
        "status": "not_computed",
        "reason": reason,
        "message": message,
    }


def _form_code(row: dict) -> str | None:
    raw = row.get("line_code")
    if not isinstance(raw, str) or not raw:
        raw = _evidence_of(row).get("line_code")
    return marked_line_code(raw)


def _basis_conflict(kind: str, denominator: str, primaries: dict) -> bool:
    """РСБУ — строка 2330 или 070. МСФО — финансовые расходы или проценты без этих кодов."""

    ras_line = _form_code(primaries[denominator]) in _RAS_INTEREST
    if kind == "ras":
        return denominator != "interest" or not ras_line
    return not (denominator == "finance_costs" or (denominator == "interest" and not ras_line))


def _standard_token(profile: dict | None) -> str | None:
    """Стандарт учёта аренды. База отчётности — это ebitda_definition, не это поле."""

    evidence = _denominator(profile) or {}
    raw = evidence.get("standard")
    if not isinstance(raw, str):
        return None
    token = "".join(raw.casefold().replace("ё", "е").split()).replace("-", "_")
    token = token.replace("фсбу", "fsbu")
    return _LEASE_STANDARD.get(token)


def _lease_double_counts(mode: str, profile: dict | None) -> bool:
    """IFRS 16 и ФСБУ 25 уже держат проценты аренды в знаменателе. add_interest задваивает их."""

    if mode != "add_interest":
        return False
    return _standard_token(profile) in _CAPITAL_LEASE


def _reported_grains(facts: list[dict], row: dict, periods: list[dict]) -> set[int]:
    row_key = row.get("row_key")
    present = {
        (fact.get("axis_id"), fact.get("period_id"))
        for fact in facts
        if fact.get("row_key") == row_key and fact.get("normalized_value") not in (None, "")
    }
    grains: set[int] = set()
    for item in periods:
        if (item.get("axis_id"), item.get("period_id")) not in present:
            continue
        months = grain_months(item.get("grain"))
        if months is not None:
            grains.add(months)
    return grains


def _include_rou(profile: dict | None) -> bool:
    raw = (profile or {}).get("icr_definition")
    return isinstance(raw, dict) and raw.get("include_rou_depreciation") is True


def _notes_include_rou(row: dict) -> bool | None:
    """True, False или None, если пометка есть, но она не bool или без источника."""

    evidence = _evidence_of(row)
    if "includes_rou" not in evidence:
        return False
    mark = evidence.get("includes_rou")
    if not isinstance(mark, bool):
        return None
    source = evidence.get("includes_rou_source")
    if mark and (not isinstance(source, str) or not source.strip()):
        return None
    return mark


def _value_basis(row: dict) -> str | None:
    raw = _evidence_of(row).get("value_basis")
    if raw not in _VALUE_BASIS:
        return None
    if raw == "ytd" and basis_of(row)[0] != "ytd":
        return None
    return raw


def _statement_terms(kind: str, primaries: dict, profile: dict | None):
    """Плюс и минус числителя. Право пользования в РСБУ не входит без явного флага.

    Общая строка с пометкой includes_rou для РСБУ годится, только если рядом есть
    отдельная сумма depreciation_rou и её можно вычесть. Иначе отказ.
    МСФО считает, только если право пользования отдельно или итог явно помечен includes_rou.
    """

    profit = "profit_from_sales" if kind == "ras" else "ifrs_operating_profit"
    if profit not in primaries:
        return None, _held("statement_line_missing", _STATEMENT_LINE_MISSING)
    if "depreciation_notes" not in primaries:
        return None, _held("depreciation_missing", _DEPRECIATION_MISSING)
    mixed = _notes_include_rou(primaries["depreciation_notes"])
    if mixed is None:
        return None, _held("includes_rou_invalid", _ROU_MARK)
    separate = "depreciation_rou" in primaries
    allow = _include_rou(profile)
    if kind == "ifrs" and not separate and not mixed:
        return None, _held("depreciation_rou_completeness_unknown", _ROU_UNKNOWN)
    if kind == "ras" and mixed and not allow and not separate:
        return None, _held("depreciation_rou_unseparated", _ROU_MIXED)
    plus = [profit, "depreciation_notes"]
    minus: list[str] = []
    if kind == "ifrs" and separate and not mixed:
        plus.append("depreciation_rou")
    elif kind == "ras" and mixed and not allow:
        minus.append("depreciation_rou")
    elif kind == "ras" and separate and allow and not mixed:
        plus.append("depreciation_rou")
    return (tuple(plus), tuple(minus)), None


def _depreciation_grain_mismatch(grains: set[int], period: dict) -> bool:
    """Год не заполняет квартальный LTM. Чужое зерно не переводится и не делится."""

    months = grain_months(period.get("grain"))
    if months is None or not grains:
        return True
    if months >= 12:
        return not any(grain >= 12 for grain in grains)
    return months not in grains


# Числитель и знаменатель bank_icr. EBIT код не подставляет.
_BANK_DYNAMIC = DynamicInputs(
    groups=(ConceptGroup("отчёт", ("ebitda", "interest")),),
    dependencies=(
        ConceptDependency("standard", "ras", ("profit_from_sales", "depreciation_notes", "depreciation_rou")),
        ConceptDependency(
            "standard",
            "ifrs",
            ("ifrs_operating_profit", "depreciation_notes", "depreciation_rou"),
        ),
        ConceptDependency("profile", "lease_mode", ("lease_interest", "lease_payments", "lease_principal")),
        ConceptDependency("profile", "finance_costs_confirmed", ("finance_costs",)),
    ),
)


@implements(
    "icr",
    "icr.bank",
    mode="dynamic",
    reason="стандарт и флаг аренды меняют числитель",
    dynamic_inputs=_BANK_DYNAMIC,
    implementation_version="icr.bank@1",
)
def bank_icr(
    *,
    facts: list[dict],
    bindings: list[dict],
    periods: list[dict],
    profile: dict | None = None,
    sign_convention: str = "outflow_negative",
    marker_class: str | None = None,
    absent: frozenset[str] = frozenset(),
    plan: Any | None = None,
) -> dict:
    """Внутренний профиль icr.bank. Поле regulatory_6960u всегда ложь."""

    if plan is not None:
        from finance_analysis.domain.resolved_plan import bindings_for_plan

        bindings = list(bindings_for_plan(bindings, plan))
    result = _bank_icr(
        facts=facts,
        bindings=bindings,
        periods=periods,
        profile=profile,
        sign_convention=sign_convention,
        marker_class=marker_class,
        absent=absent,
    )
    return {
        **result,
        "profile": "icr.bank",
        "regulatory_6960u": False,
        "profile_note": _INTERNAL_ICR_NOTE,
    }


def _bank_icr(
    *,
    facts: list[dict],
    bindings: list[dict],
    periods: list[dict],
    profile: dict | None = None,
    sign_convention: str = "outflow_negative",
    marker_class: str | None = None,
    absent: frozenset[str] = frozenset(),
) -> dict:
    """Внутренний профиль icr.bank. Не ICR по 6960-У и не ковенант договора.

    EBIT не подставляется. Окно LTM, квартал — только справочная строка.
    При пометке ras числитель — прибыль от продаж плюс амортизация ОС и НМА.
    Право пользования входит только по флагу include_rou_depreciation.
    При пометке ifrs к операционной прибыли добавляется и амортизация права пользования.
    """

    kind = ebitda_definition(profile)
    stated = kind in _STATEMENT
    if not stated:
        blocked = methodology_block(profile, bindings, metric="icr", names=("ebitda",))
        if blocked:
            return blocked
    mode = _icr_mode(profile)
    if mode == "nominal":
        return _ask("icr", "lease_mode", "nominal")
    if mode not in _LEASE_MODES:
        return _ask("icr", "lease_mode", "missing")
    if _denominator(profile) is not None and _standard_token(profile) is None:
        return _ask("icr", "lease_standard", "unknown")
    primaries = _primaries(bindings, absent)
    terms = None
    if stated:
        terms, blocked = _statement_terms(kind, primaries, profile)
        if blocked:
            return blocked
    elif "ebitda" not in primaries:
        return _ask("icr", "ebitda", "concept_unknown")
    formula, warnings, problem = _bank_formula(primaries, mode, profile)
    if problem:
        return problem
    assert formula is not None
    dep_grains: list[set[int]] | None = None
    if terms:
        plus, minus = terms
        formula = Composed(Side(plus, minus), formula.denominator, formula.window)
        if _basis_conflict(kind, formula.denominator.plus[0], primaries):
            return _held("statement_basis_mismatch", _BASIS_MISMATCH)
        if _lease_double_counts(mode, profile):
            return _held("lease_ebitda_double_count", _LEASE_DOUBLE)
        dep_names = [name for name in (*plus, *minus) if name.startswith("depreciation_")]
        dep_grains = []
        for name in dep_names:
            basis = _value_basis(primaries[name])
            if basis is None:
                return _held("depreciation_basis_unknown", _DEP_BASIS)
            if basis == "annual":
                dep_grains.append({12})
                continue
            grains = _reported_grains(facts, primaries[name], periods)
            if not grains:
                if name == "depreciation_rou":
                    return _held("depreciation_rou_unseparated", _ROU_MIXED)
                return _held("depreciation_missing", _DEPRECIATION_MISSING)
            dep_grains.append(grains)
    if mode == "in_interest":
        blocked_mode = _require_interest_expense(profile, primaries, periods, formula.denominator.plus[0])
        if blocked_mode:
            return blocked_mode
    names = [
        *formula.numerator.plus,
        *formula.numerator.minus,
        *formula.denominator.plus,
        *formula.denominator.minus,
    ]

    def _tail():
        from finance_analysis.domain.execution_branches import claim

        for name in dict.fromkeys(names):
            claim(name)
        return _bank_scored(
            formula,
            names,
            warnings,
            dep_grains,
            mode,
            profile,
            primaries,
            facts,
            periods,
            sign_convention,
            marker_class,
        )

    from finance_analysis.domain.execution_branches import (
        bank_values,
        branch_for,
        run_branch,
    )

    branch = branch_for("icr", variant="bank", profile=profile)
    if branch is None:
        return _tail()
    return run_branch(branch, bank_values(profile, kind, mode), facts, bindings, _tail, periods=periods)


def _bank_scored(formula, names, warnings, dep_grains, mode, profile, primaries, facts, periods, sign_convention, marker_class):
    bases = {basis_of(primaries[name])[0] for name in names}
    if len(bases) != 1:
        return _ask("icr", "period_basis", "basis_mismatch")
    basis = bases.pop()
    if basis == "unknown":
        return _ask("icr", "period_basis", "basis_mismatch")
    aligned = aligned_keys(periods)
    raw = basis in {"ytd", "ltm"}
    series = {
        name: _sums(facts, primaries[name], aligned, None if raw else periods)
        for name in dict.fromkeys(names)
    }
    home_name = formula.denominator.plus[0]
    attested_axis = None
    attested_period = None
    if mode == "in_interest":
        evidence = _denominator(profile) or {}
        axis_name = str(evidence.get("axis") or "").strip()
        period_name = str(evidence.get("period") or "").strip()
        if axis_name != "each":
            attested_axis = axis_name
        if period_name != "each":
            attested_period = period_name
    rows = []
    for axis in sorted(_axes_of(facts, primaries[home_name])):
        ordered = _ordered(periods, axis)
        for period in ordered:
            marker = period.get("marker_class")
            if marker_class and marker and marker != marker_class:
                continue
            if attested_axis is not None and period.get("axis_id") != attested_axis:
                rows.append(
                    _line(
                        "icr",
                        period,
                        None,
                        "needs_input",
                        "denominator_axis",
                        names,
                        "LTM",
                        variant="bank",
                    )
                )
                continue
            if attested_period is not None and period.get("period_id") != attested_period:
                rows.append(
                    _line(
                        "icr",
                        period,
                        None,
                        "needs_input",
                        "denominator_period",
                        names,
                        "LTM",
                        variant="bank",
                    )
                )
                continue
            if dep_grains is not None and any(
                _depreciation_grain_mismatch(grains, period) for grains in dep_grains
            ):
                rows.append(
                    _line(
                        "icr",
                        period,
                        None,
                        "not_computed",
                        "depreciation_period_mismatch",
                        names,
                        "LTM",
                        variant="bank",
                        message=_DEP_PERIOD,
                    )
                )
                continue
            number, den, reason = _bank_pair(formula, series, period, ordered, aligned, basis, sign_convention)
            if reason == "partial_window" and basis != "ytd":
                rows.append(
                    _line("icr", period, None, "not_computed", "partial_window", names, "LTM", variant="bank")
                )
                continue
            if number is None or den is None:
                published = reason if reason in _FISCAL_REASONS else "needs_input"
                rows.append(_line("icr", period, None, "needs_input", published, names, "LTM", variant="bank"))
                continue
            if den == 0:
                rows.append(
                    _line(
                        "icr",
                        period,
                        None,
                        "missing_input",
                        "no_interest",
                        names,
                        "LTM",
                        variant="bank",
                        ebitda_sign=_sign_name(number),
                    )
                )
                continue
            if den < 0:
                rows.append(
                    _line(
                        "icr",
                        period,
                        None,
                        "not_computed",
                        "invalid_denominator",
                        names,
                        "LTM",
                        variant="bank",
                    )
                )
                continue
            value = _ratio(number, den)
            row = _line("icr", period, value, "computed", None, names, "LTM", variant="bank")
            if number <= 0:
                warnings.append(
                    {
                        "code": "negative_numerator",
                        "params": {"period_id": period["period_id"], "ebitda_sign": _sign_name(number)},
                    }
                )
            rows.append(row)
            step = _bank_pair(formula, series, period, ordered, aligned, basis, sign_convention, quarter=True)
            if (
                grain_months(period.get("grain")) == 3
                and basis != "ltm"
                and step[0] is not None
                and step[1] not in (None, 0)
                and step[1] > 0
            ):
                rows.append(
                    _line(
                        "icr",
                        period,
                        _ratio(step[0], step[1]),
                        "computed",
                        None,
                        names,
                        "period",
                        variant="quarter_reference",
                        message=_QUARTER_LABEL,
                    )
                )
    ltm = [row for row in rows if row.get("variant") == "bank"]
    status = "succeeded"
    if ltm and not any(row["status"] == "computed" for row in ltm):
        if any(row["status"] == "needs_input" for row in ltm):
            status = "needs_input"
        elif any(row.get("reason") == "no_interest" for row in ltm):
            status = "missing_input"
        elif any(row.get("reason") in {"invalid_denominator", "depreciation_period_mismatch"} for row in ltm):
            status = "not_computed"
        elif any(row.get("reason") == "partial_window" for row in ltm):
            status = "partial_window"
    return {"metric": "icr", "rows": rows, "needs_input": [], "warnings": warnings, "status": status}


def _bank_pair(formula, series, period, ordered, aligned, basis, sign, *, quarter: bool = False):
    parts = {}
    names = (*formula.numerator.plus, *formula.numerator.minus, *formula.denominator.plus, *formula.denominator.minus)
    for name in dict.fromkeys(names):
        value, problem = _concept_amount(name, series, period, ordered, aligned, basis, quarter)
        if value is None:
            if problem in _FISCAL_REASONS:
                return None, None, problem
            return None, None, "partial_window" if basis != "ytd" and not quarter else "needs_input"
        parts[name] = value
    number = Decimal(0)
    for name in formula.numerator.plus:
        number += parts[name]
    for name in formula.numerator.minus:
        number -= parts[name]
    den = Decimal(0)
    for name in formula.denominator.plus:
        den += _payment(parts[name], sign)
    for name in formula.denominator.minus:
        den -= _payment(parts[name], sign)
    return number, den, None


def _concept_amount(name, series, period, ordered, aligned, basis, quarter: bool):
    column = series[name]
    if basis == "ytd":
        if quarter:
            return _ytd_step(column, period, ordered, aligned), None
        return _ytd_ltm(column, period, ordered, aligned)
    if basis == "ltm" or quarter:
        return column.get(_aligned_key(period, aligned)), None
    keys, _window, problem = _span("LTM", ordered, period, aligned, period["axis_id"])
    if problem or not keys:
        return None, None
    total = Decimal(0)
    for key in keys:
        if key not in column:
            return None, None
        total += column[key]
    return total, None


@implements(
    "dscr",
    "dscr.cash_covenant",
    implementation_version="dscr.cash_covenant@1",
    inputs=_CASH_CORE,
    optional_inputs=(_CASH_OTHER,),
)
def cash_covenant_dscr(
    *,
    facts: list[dict],
    bindings: list[dict],
    periods: list[dict],
    sign_convention: str = "outflow_negative",
    marker_class: str | None = None,
    absent: frozenset[str] = frozenset(),
    plan: Any | None = None,
    _inside: bool = False,
) -> dict:
    """Кассовый DSCR года i. OCF со знаком, остальные входы — модули платежей.

    `debt_service` в знаменатель не входит. `concept.absent` на прочей
    финансовой задолженности убирает третье слагаемое и не подставляет ноль
    вместо ненайденной строки. Неполный календарный год не считается.
    """

    if plan is not None:
        from finance_analysis.domain.resolved_plan import bindings_for_plan

        bindings = list(bindings_for_plan(bindings, plan))
    if not _inside:
        from finance_analysis.domain.execution_branches import CASH, run_branch

        return run_branch(
            CASH,
            {},
            facts,
            bindings,
            lambda: _CASH_IMPL(
                facts=facts,
                bindings=bindings,
                periods=periods,
                sign_convention=sign_convention,
                marker_class=marker_class,
                absent=absent,
                plan=None,
                _inside=True,
            ),
            periods=periods,
        )
    include_other = _CASH_OTHER not in absent
    needed = (*_CASH_CORE, *((_CASH_OTHER,) if include_other else ()))
    missing = _missing("dscr", bindings, needed, absent)
    if missing:
        note = _capitalized_interest(bindings)
        if note:
            missing["warnings"] = [*missing["warnings"], note]
        return missing
    primaries = BoundInputs(_CASH_CORE, _primaries(bindings, absent), optional=(_CASH_OTHER,))
    inputs = list(needed)
    from finance_analysis.domain.execution_branches import claim

    for name in inputs:
        claim(name)
    if unconfirmed_scale(facts, [primaries[name] for name in inputs]):
        return _refused("dscr", periods, "scale_unconfirmed", SCALE_UNCONFIRMED, inputs)
    if len({_flow_basis(primaries[name]) for name in inputs}) > 1:
        return _refused("dscr", periods, "basis_mismatch", MIXED_BASIS, inputs)
    warnings: list[dict] = []
    note = _capitalized_interest(bindings)
    if note:
        warnings.append(note)
    sheet = _assume_sheet_units(facts, [primaries[name] for name in inputs], warnings)
    aligned = aligned_keys(periods)
    series = {name: _sums(facts, primaries[name], aligned, periods, sheet=sheet) for name in inputs}
    rows = []
    for axis in sorted(_axes_of(facts, primaries["operating_cash_flow"])):
        ordered = _ordered(periods, axis)
        for window, problem in _cash_spans(ordered):
            anchor = window[-1]
            marker = anchor.get("marker_class")
            if marker_class and marker and marker != marker_class:
                continue
            keys = [aligned.get((axis, item["period_id"]), (axis, item["period_id"])) for item in window]
            window_ids = [item["period_id"] for item in window]
            if problem:
                message = PARTIAL_YEAR if problem == "partial_window" else None
                rows.append(_line("dscr", anchor, None, "not_computed", problem, inputs, window_ids, message=message))
                continue
            numerator = _cash_numerator(keys, series, sign_convention)
            denominator = _cash_denominator(keys, series, sign_convention, include_other=include_other)
            if numerator is None or denominator is None:
                rows.append(_line("dscr", anchor, None, "missing_input", "no_binding", inputs, window_ids))
                continue
            if denominator == 0:
                rows.append(_line("dscr", anchor, None, "no_debt_service", "zero_denominator", inputs, window_ids))
                continue
            line = _line("dscr", anchor, _ratio(numerator, denominator), "computed", None, inputs, window_ids)
            line["components"] = {name: _component_cells(facts, primaries[name], window) for name in inputs}
            line["variant"] = "cash_covenant"
            rows.append(line)
    status = "succeeded"
    message = None
    if rows and not any(row["status"] == "computed" for row in rows):
        if any(row.get("reason") == "partial_window" for row in rows):
            status = "partial_window"
            message = PARTIAL_YEAR
        elif any(row.get("reason") in {"no_period_dates", "grain_unknown"} for row in rows):
            status = "not_computed"
    result = {"metric": "dscr", "rows": rows, "needs_input": [], "warnings": warnings, "status": status}
    if message:
        result["message"] = message
    return result


_CASH_IMPL = cash_covenant_dscr


def _capitalized_interest(bindings: list[dict]) -> dict | None:
    for row in bindings:
        blob = " ".join(str(row.get(key) or "") for key in ("label", "label_path_text", "code"))
        if _CAPITALIZED_INTEREST.search(blob):
            return {"code": "capitalized_interest", "params": {"message": CAPITALIZED_INTEREST, "code": "4224"}}
    return None


def _cash_spans(ordered: list[dict]) -> list[tuple[list[dict], str | None]]:
    if not ordered:
        return []
    months = {grain_months(item.get("grain")) for item in ordered}
    if len(months) != 1 or None in months:
        return [(ordered[-1:], "grain_unknown")]
    span = next(iter(months))
    if span is not None and span >= 12:
        return [([item], None) for item in ordered]
    if any(item.get("period_start") is None or item.get("period_end") is None for item in ordered):
        return [(ordered[-1:], "no_period_dates")]
    groups: dict[int, list[dict]] = {}
    for item in ordered:
        groups.setdefault(item["period_end"].year, []).append(item)
    found = []
    for year in sorted(groups):
        items = sorted(groups[year], key=lambda item: (item["period_end"], int(item.get("period_index") or 0)))
        problem = None
        if items[0]["period_start"] != date(year, 1, 1) or items[-1]["period_end"] != date(year, 12, 31):
            problem = "partial_window"
        else:
            for before, after in pairwise(items):
                if before["period_end"] + timedelta(days=1) != after["period_start"]:
                    problem = "partial_window"
                    break
        found.append((items, problem))
    return found


def _cash_numerator(keys, series: dict, convention: str) -> Decimal | None:
    earned = _cash_signed(keys, series, "operating_cash_flow")
    paid = _cash_paid(keys, series, "interest_paid", convention)
    spent = _cash_paid(keys, series, "capex", convention)
    if earned is None or paid is None or spent is None:
        return None
    return earned + paid - spent


def _cash_denominator(keys, series: dict, convention: str, *, include_other: bool) -> Decimal | None:
    principal = _cash_paid(keys, series, "principal", convention)
    paid = _cash_paid(keys, series, "interest_paid", convention)
    if principal is None or paid is None:
        return None
    total = principal + paid
    if not include_other:
        return total
    other = _cash_paid(keys, series, _CASH_OTHER, convention)
    if other is None:
        return None
    return total + other


def _cash_signed(keys, series: dict, name: str) -> Decimal | None:
    total = Decimal(0)
    values = series[name]
    for key in keys:
        if key not in values:
            return None
        total += values[key]
    return total


def _cash_paid(keys, series: dict, name: str, convention: str) -> Decimal | None:
    total = Decimal(0)
    values = series[name]
    for key in keys:
        if key not in values:
            return None
        total += _payment(values[key], convention)
    return total



def _book_dscr_rows(facts, book, periods, reader: EvidenceBook | None = None) -> list[dict]:
    aligned = aligned_keys(periods)
    cached = _sums(
        facts,
        book,
        aligned,
        periods,
        book=reader,
        concept="dscr" if reader is not None else None,
    )
    rows = []
    for period in periods:
        own = (period.get("axis_id"), period.get("period_id"))
        number = cached.get(aligned.get(own, own))
        if number is None:
            continue
        rows.append(
            _line("dscr", period, number, "computed", "reported", ["dscr"], None, variant="reported")
        )
    return rows


def _scale_key(axis, period, aligned: dict) -> tuple:
    own = (axis, period)
    return aligned.get(own, own)


def _publication_periods(rows: list[dict], reader: EvidenceBook, aligned: dict, row_key) -> tuple[PeriodResult, ...]:
    """Чтение ячейки и публикация её числа. Деления здесь нет."""

    built = []
    observations = reader.observations or []
    for row in rows:
        key = _scale_key(row.get("axis_id"), row.get("period_id"), aligned)
        matched = [
            item
            for item in observations
            if item.considered in {None, "value"} and _scale_key(item.axis_id, item.period_id, aligned) == key
        ]
        refs = tuple(
            f"cell:{item.cell_id}" if item.cell_id else f"fact:{item.axis_id}:{item.period_id}" for item in matched
        )
        value = row.get("value")
        built.append(
            PeriodResult(
                axis_id=None if row.get("axis_id") is None else str(row.get("axis_id")),
                period_id=None if row.get("period_id") is None else str(row.get("period_id")),
                status="published",
                reason="reported",
                value=value if isinstance(value, Decimal) else None,
                numerator=None,
                denominator=None,
                steps=(
                    TransformationStep(
                        step_id=1,
                        operation="publication",
                        input_refs=refs,
                        output_value=value if isinstance(value, Decimal) else None,
                        parameters=MappingProxyType({"row_key": row_key}),
                    ),
                ),
            )
        )
    return tuple(built)


def _publish_reported_read(
    collect: list,
    attempt_evidence,
    reader: EvidenceBook,
    rows: list[dict],
    periods: list[dict],
    row_key,
) -> None:
    """Отдельная улика опубликованного числа. След попытки не переписывается."""

    ref = None if row_key is None else MappingProxyType({"row_key": str(row_key)})
    publication = seal(
        replace(
            reader.freeze(
                "published",
                _REPORTED_READ,
                calculation_origin="reported",
                definition_source="reported",
                definition_ref=ref,
            ),
            sums_additions=0,
            fact_uses=(),
            period_results=_publication_periods(rows, reader, aligned_keys(periods), row_key),
        )
    )
    if attempt_evidence is not None:
        for index, item in enumerate(collect):
            if item is attempt_evidence:
                collect[index] = replace(attempt_evidence, published_read=publication.implementation)
                break
    collect.append(publication)


def _reported_book_dscr(
    attempt: dict,
    *,
    variant: str,
    facts: list[dict],
    bindings: list[dict],
    periods: list[dict],
    absent: frozenset[str],
    plan: Any | None = None,
    collect: list | None = None,
    attempt_evidence=None,
    sign_convention: str = "outflow_negative",
    marker_class: str | None = None,
    explicit_phases: bool = False,
) -> dict:
    """Строка книги только у пустого результата со статусом missing_input или needs_input.

    Число формулы и любой другой статус, включая scale_unconfirmed и basis_mismatch,
    возвращаются как есть. Отказ не закрывается другим определением
    (https://arxiv.org/abs/1705.08500). Кэш строки читается через план:
    понятие, которое план уже разобрал, не сканируется второй раз.
    Опубликованное число — чтение ячейки, не частное. Его улика отдельно от попытки,
    а попытка хранит ссылку на это чтение.
    """

    if any(row.get("value") is not None for row in attempt.get("rows") or []):
        return attempt
    if attempt.get("status") not in {"missing_input", "needs_input"}:
        return attempt
    from finance_analysis.domain.resolved_plan import bindings_for_plan

    book = _primaries(list(bindings_for_plan(bindings, plan)), absent).get("dscr")
    if book is None:
        return attempt
    reader = None
    if collect is not None:
        reader = EvidenceBook(
            metric="dscr",
            sign_convention=sign_convention,
            marker_class=marker_class,
            explicit_phases=explicit_phases,
            plan_content_sha256=(getattr(plan, "content_sha256", None) if plan is not None else None),
        )
    reported = _book_dscr_rows(facts, book, periods, reader)
    if not reported:
        return attempt
    if collect is not None and reader is not None:
        _publish_reported_read(collect, attempt_evidence, reader, reported, periods, book.get("row_key"))
    missing = [str(name) for name in attempt.get("missing_inputs") or [] if name]
    names = ", ".join(missing) if missing else "входы"
    return {
        "metric": "dscr",
        "rows": reported,
        "needs_input": attempt.get("needs_input") or [],
        "warnings": [
            {
                "code": "dscr_reported",
                "params": {
                    "variant": variant,
                    "inputs": missing,
                    "message": (
                        f"Вариант {variant} не посчитан: не хватает {names}. "
                        "Показан DSCR строки книги с пометкой reported."
                    ),
                },
            },
            *(attempt.get("warnings") or []),
        ],
        "status": "succeeded",
        "definition_source": "reported",
        "definition_ref": book.get("row_key"),
        "missing_inputs": missing,
    }


def _refused_covenant(
    plan: Any,
    periods: list[dict],
    *,
    sign_convention: str,
    marker_class: str | None,
    explicit_phases: bool,
):
    """Отказ плана без прохода формулы. Основание — статус и недостающие понятия.

    Число не считается: в следе нет шага. Происхождение отказа — план, который
    уже решил, что вход отсутствует (https://www.w3.org/TR/prov-dm/).
    """

    from finance_analysis.domain.metric_contract import REGISTRY

    needs = tuple(getattr(plan, "needs_input", ()) or ())
    subjects = tuple(str(item.subject) for item in needs if getattr(item, "subject", None))
    reasons = tuple(dict.fromkeys(str(item.reason) for item in needs if getattr(item, "reason", None)))
    reason = reasons[0] if len(reasons) == 1 else None
    status = str(plan.status)
    recorded = []
    for period in list(periods) or [None]:
        period_id = None if period is None else period.get("period_id")
        axis_id = None if period is None else period.get("axis_id")
        label = "" if period_id is None else str(period_id)
        recorded.append(
            PeriodResult(
                axis_id=None if axis_id is None else str(axis_id),
                period_id=None if period_id is None else str(period_id),
                status=status,
                reason=reason,
                value=None,
                numerator=None,
                denominator=None,
                steps=(),
                missing_concepts=((label, subjects),) if subjects else (),
            )
        )
    book = EvidenceBook(
        metric="dscr",
        sign_convention=sign_convention,
        marker_class=marker_class,
        explicit_phases=explicit_phases,
        plan_content_sha256=getattr(plan, "content_sha256", None),
        periods=recorded,
    )
    return book.freeze("not_run", REGISTRY[("dscr", "dscr.corporate_covenant")].implementation_version)


def select_ratio(
    metric: str,
    variant: str | None,
    common: dict,
    *,
    profile: dict | None,
    profile_ref: str | None,
    composed: dict[str, Composed],
    concepts: frozenset[str],
    money: frozenset[str],
    interest_order: dict | None = None,
    row_fallbacks: dict | None = None,
    links: list[dict] | None = None,
    statement_sheets: frozenset[str] | None = None,
    aggregations: Mapping[str, str] | None = None,
    plan: Any | None = None,
    collect: list | None = None,
    definition: Any | None = None,
    outflows: frozenset[str] | None = None,
    slots: tuple | None = None,
) -> dict:
    """Именованный вариант профиля считает свою формулу на любом типе книги.

    Без имени корпоративный тип остаётся на `corporate_covenant`, остальные — на своей формуле.
    """

    if metric == "total_debt":
        from finance_analysis.domain.total_debt import total_debt_result

        return total_debt_result(
            facts=common["facts"],
            bindings=common["bindings"],
            periods=common["periods"],
            profile=profile,
            marker_class=common["marker_class"],
            plan=plan,
        )
    if metric == "debt_incl_off_balance":
        from finance_analysis.domain.debt_incl_off_balance import debt_incl_off_balance

        formula = composed.get(metric)
        plus = formula.numerator.plus if formula is not None else ()
        return debt_incl_off_balance(
            components=plus,
            facts=common["facts"],
            bindings=common["bindings"],
            periods=common["periods"],
            absent=common["absent"],
            plan=plan,
        )
    if metric in {"npv", "irr"}:
        refused = _refuse_branch(metric, definition, plan)
        if refused is not None:
            return refused
        return project_return(
            metric,
            facts=common["facts"],
            bindings=common["bindings"],
            periods=common["periods"],
            absent=common["absent"],
            plan=plan,
        )
    if metric == "fcff":
        refused = _refuse_branch(metric, definition, plan)
        if refused is not None:
            return refused
        return free_cash_flow(
            facts=common["facts"],
            bindings=common["bindings"],
            periods=common["periods"],
            sign_convention=common.get("sign_convention") or "outflow_negative",
            absent=common.get("absent") or frozenset(),
            links=common.get("graph_links") if links is None else links,
            book=common.get("book_fcff") or [],
            statement_sheets=(
                statement_sheets
                if statement_sheets is not None
                else common.get("statement_sheets") or frozenset()
            ),
            plan=plan,
        )
    if metric == "ncf":
        return net_cash_flow(
            facts=common["facts"],
            bindings=common["bindings"],
            periods=common["periods"],
            absent=common.get("absent") or frozenset(),
            book=common.get("book_ncf") or [],
            statement_sheets=(
                statement_sheets
                if statement_sheets is not None
                else common.get("statement_sheets") or frozenset()
            ),
            plan=plan,
        )
    if metric == "ncf_period":
        return period_net_cash_flow(
            facts=common["facts"],
            bindings=common["bindings"],
            periods=common["periods"],
            sign_convention=common.get("sign_convention") or "outflow_negative",
            absent=common.get("absent") or frozenset(),
            plan=plan,
        )
    if metric == "fcf_identity":
        return fcf_identity(
            variant,
            facts=common["facts"],
            bindings=common["bindings"],
            periods=common["periods"],
            absent=common.get("absent") or frozenset(),
            sign_convention=common.get("sign_convention") or "outflow_negative",
            plan=plan,
        )
    if metric == "icr_lease":
        if definition is not None:
            from finance_analysis.domain.metrics import lease_branch_mode

            refused = _refuse_branch(
                metric,
                definition,
                plan,
                lease_mode=lease_branch_mode(common["bindings"], common["absent"], plan=plan),
            )
            if refused is not None:
                return refused
        return lease_interest_coverage(
            facts=common["facts"],
            bindings=common["bindings"],
            periods=common["periods"],
            sign_convention=common["sign_convention"],
            marker_class=common["marker_class"],
            absent=common["absent"],
            plan=plan,
        )
    if metric == "dscr" and variant == "cash_covenant":
        refused = _refuse_branch(metric, definition, plan, variant="cash_covenant")
        if refused is not None:
            return refused
        return cash_covenant_dscr(
            facts=common["facts"],
            bindings=common["bindings"],
            periods=common["periods"],
            sign_convention=common["sign_convention"],
            marker_class=common["marker_class"],
            absent=common["absent"],
            plan=plan,
        )
    named = _named_variant(profile)
    if metric == "dscr" and (named or variant) == "housing":
        refused = _refuse_branch(metric, definition, plan, variant="housing", profile=profile)
        if refused is not None:
            return refused
        from finance_analysis.domain.housing_dscr import housing_dscr

        return housing_dscr(
            facts=common["facts"],
            bindings=common["bindings"],
            periods=common["periods"],
            sign_convention=common.get("sign_convention") or "outflow_negative",
            absent=common.get("absent") or frozenset(),
            profile=profile,
            plan=plan,
        )
    if metric == "dscr" and (variant == "ocf_covenant" or named == "ocf_covenant"):
        return dscr_ocf_covenant(
            facts=common["facts"],
            bindings=common["bindings"],
            periods=common["periods"],
            sign_convention=common["sign_convention"],
            marker_class=common["marker_class"],
            absent=common["absent"],
            profile=profile,
            profile_ref=profile_ref,
            default=composed["dscr.ocf_covenant"],
            concepts=concepts,
            money=money,
            interest_order=interest_order,
            row_fallbacks=row_fallbacks,
            composed=composed,
            aggregations=aggregations,
            plan=plan,
            outflows=outflows,
        )
    if metric == "dscr" and (variant == "corporate_covenant" or (named and f"dscr.{named}" in composed)):
        attempt = covenant_dscr(
            facts=common["facts"],
            bindings=common["bindings"],
            periods=common["periods"],
            sign_convention=common["sign_convention"],
            marker_class=common["marker_class"],
            absent=common["absent"],
            profile=profile,
            profile_ref=profile_ref,
            default=composed["dscr.corporate_covenant"],
            concepts=concepts,
            money=money,
            interest_order=interest_order,
            row_fallbacks=row_fallbacks,
            composed=composed,
            aggregations=aggregations,
            plan=plan,
            outflows=outflows,
        )
        attempt_evidence = None
        if (
            collect is not None
            and plan is not None
            and getattr(plan, "status", None) in {"missing_input", "needs_input"}
            and attempt.get("status") in {"missing_input", "needs_input"}
        ):
            attempt_evidence = _refused_covenant(
                plan,
                common["periods"],
                sign_convention=common["sign_convention"],
                marker_class=common["marker_class"],
                explicit_phases=bool(common.get("explicit_phases")),
            )
            collect.append(attempt_evidence)
        return _reported_book_dscr(
            attempt,
            variant=named or variant or "corporate_covenant",
            facts=common["facts"],
            bindings=common["bindings"],
            periods=common["periods"],
            absent=common.get("absent") or frozenset(),
            plan=plan,
            collect=collect,
            attempt_evidence=attempt_evidence,
            sign_convention=common["sign_convention"],
            marker_class=common["marker_class"],
            explicit_phases=bool(common.get("explicit_phases")),
        )
    if metric == "dscr" and variant == "pf":
        if collect is None:
            return dscr_pf(
                interest_order=interest_order,
                row_fallbacks=row_fallbacks,
                profile=profile,
                plan=plan,
                definition=definition,
                slots=slots,
                **common,
            )
        return remembered(
            calculate_dscr_pf(
                interest_order=interest_order,
                row_fallbacks=row_fallbacks,
                profile=profile,
                plan=plan,
                definition=definition,
                slots=slots,
                evidence=True,
                **common,
            ),
            collect,
        )
    if metric == "icr" and bank_requested(variant, profile):
        refused = _refuse_branch(metric, definition, plan, variant="bank", profile=profile)
        if refused is not None:
            return refused
        return bank_icr(
            facts=common["facts"],
            bindings=common["bindings"],
            periods=common["periods"],
            profile=profile,
            sign_convention=common["sign_convention"],
            marker_class=common["marker_class"],
            absent=common["absent"],
            plan=plan,
        )
    formula = composed.get(metric)
    if formula is not None:
        return composed_ratio(
            metric,
            formula,
            facts=common["facts"],
            bindings=common["bindings"],
            periods=common["periods"],
            sign_convention=common["sign_convention"],
            marker_class=common["marker_class"],
            absent=common["absent"],
            profile=profile,
            aggregations=aggregations,
            plan=plan,
            definition=definition,
            collect=collect,
            outflows=outflows,
        )
    attempt_evidence = None
    if collect is None:
        result = coverage_ratio(
            metric=metric,
            interest_order=interest_order,
            row_fallbacks=row_fallbacks,
            profile=profile,
            plan=plan,
            definition=definition,
            slots=slots,
            **common,
        )
    else:
        outcome = calculate_coverage(
            metric=metric,
            interest_order=interest_order,
            row_fallbacks=row_fallbacks,
            profile=profile,
            plan=plan,
            definition=definition,
            slots=slots,
            evidence=True,
            **common,
        )
        result = remembered(outcome, collect)
        attempt_evidence = outcome.evidence
    if metric != "dscr":
        return result
    return _reported_book_dscr(
        result,
        variant=variant or "catalog",
        facts=common["facts"],
        bindings=common["bindings"],
        periods=common["periods"],
        absent=common.get("absent") or frozenset(),
        plan=plan,
        collect=collect,
        attempt_evidence=attempt_evidence,
        sign_convention=common["sign_convention"],
        marker_class=common["marker_class"],
        explicit_phases=bool(common.get("explicit_phases")),
    )


def _refuse_branch(metric, definition, plan, *, variant=None, profile=None, lease_mode=None):
    """Определение, которое ветвь не считает. Калькулятор при отказе не вызывается."""

    if definition is None:
        return None
    from finance_analysis.domain.execution_branches import branch_for, refuse_definition

    return refuse_definition(
        metric,
        branch_for(metric, variant=variant, profile=profile, lease_mode=lease_mode),
        definition,
        plan,
    )


def _apply_plan(definition: Composed, notes: list, plan: Any, bindings: list[dict]):
    """Подмена процентов и строка 4123 уже записаны в плане."""

    fallback = next((item for item in plan.fallbacks if item.replaced == "interest"), None)
    if fallback is not None and fallback.chosen != "interest":
        definition = _rename(definition, fallback.chosen)
        warning = next((item.as_dict() for item in plan.warnings if item.code == (fallback.warning_code or "")), None)
        if warning:
            notes = [*notes, warning]
    paid = next((item for item in plan.inputs if item.concept == "interest_paid"), None)
    if paid is not None and not any(
        declared_concept(row) == "interest_paid" and row.get("is_primary") for row in bindings
    ):
        source = _row_for(bindings, paid)
        if source is not None and declared_concept(source) != "interest_paid":
            bindings = [*bindings, {**source, "effective_concept": "interest_paid", "is_primary": True}]
    return definition, notes, bindings


def _rename(formula: Composed, chosen: str) -> Composed:
    def replace(side: Side) -> Side:
        return Side(
            tuple(chosen if name == "interest" else name for name in side.plus),
            tuple(chosen if name == "interest" else name for name in side.minus),
        )

    terms = frozenset(chosen if name == "interest" else name for name in formula.payment_terms)
    return Composed(replace(formula.numerator), replace(formula.denominator), formula.window, terms)


def _row_for(bindings: list[dict], item: Any) -> dict | None:
    from finance_analysis.domain.resolved_plan import recover_row

    found = recover_row(bindings, item)
    return found if isinstance(found, dict) else None


def _swap_interest(
    formula: Composed,
    primaries: dict,
    order: tuple[str, ...] | list[str],
    *,
    row_fallbacks: dict | None = None,
) -> tuple[Composed, dict | None]:
    """Подменяет начисленные проценты следующим именем порядка, если основной строки нет."""

    names = (
        *formula.numerator.plus,
        *formula.numerator.minus,
        *formula.denominator.plus,
        *formula.denominator.minus,
    )
    if "interest" not in names or not order:
        return formula, None
    chosen, warning = interest_choice(primaries, order, row_fallbacks=row_fallbacks)
    if chosen is None or chosen == "interest":
        return formula, None

    def replace(side: Side) -> Side:
        return Side(
            tuple(chosen if name == "interest" else name for name in side.plus),
            tuple(chosen if name == "interest" else name for name in side.minus),
        )

    terms = frozenset(chosen if name == "interest" else name for name in formula.payment_terms)
    return Composed(replace(formula.numerator), replace(formula.denominator), formula.window, terms), warning


def _span(window: str, ordered: list[dict], period: dict, aligned: dict, axis: str):
    own = aligned.get((axis, period["period_id"]), (axis, period["period_id"]))
    if window == "period":
        return [own], [period["period_id"]], None
    months = grain_months(period.get("grain"))
    if months is not None and months >= 12:
        return [own], [period["period_id"]], None
    if months is None:
        return None, None, "grain_unknown"
    span = _window(ordered, period, "lookback")
    if span is None:
        return None, None, "partial_window"
    keys = [aligned.get((axis, item["period_id"]), (axis, item["period_id"])) for item in span]
    return keys, [item["period_id"] for item in span], None


_AMBIGUOUS_STOCK = (
    "На одну дату конца периода приходится несколько остатков одной зернистости. "
    "Остаток не выбран, коэффициент не рассчитан."
)


def _stock_choice(
    period: dict, periods: list[dict], aligned: dict, values: dict
) -> tuple[Decimal | None, str | None]:
    """Остаток на дату конца периода, без зависимости от порядка списка.

    Сначала берётся остаток той же оси. Если его нет, берётся единственный
    остаток той же зернистости. Несколько таких остатков не выбираются молча:
    метод возвращает причину `ambiguous_stock`. Ось без своей даты остаток не отдаёт.
    """

    axis = period["axis_id"]
    own = aligned.get((axis, period["period_id"]), (axis, period["period_id"]))
    if own in values:
        return values[own], None, own
    end = period.get("period_end")
    if end is None:
        return None, None, None
    seen: dict[tuple, dict] = {}
    for item in periods:
        if item.get("period_end") != end:
            continue
        key = aligned.get((item["axis_id"], item["period_id"]), (item["axis_id"], item["period_id"]))
        if key in values:
            seen[key] = item
    if not seen:
        return None, None, None
    same_axis = {key: item for key, item in seen.items() if item.get("axis_id") == axis}
    grain = period.get("grain")
    pool = same_axis or (
        {key: item for key, item in seen.items() if grain and item.get("grain") == grain} if grain else {}
    )
    if len(pool) == 1:
        chosen = next(iter(pool))
        return values[chosen], None, chosen
    if len(pool) > 1:
        return None, "ambiguous_stock", None
    return None, None, None


def _stock_numerator(
    period: dict, periods: list[dict], aligned: dict, series: dict, side: Side
) -> tuple[Decimal | None, str | None]:
    """Сумма остатков на одну дату. Пропуск слагаемого нулём не становится."""

    total = Decimal(0)
    for name, sign in (*((item, 1) for item in side.plus), *((item, -1) for item in side.minus)):
        value, problem, _key = _stock_choice(period, periods, aligned, series.get(name) or {})
        if problem:
            return None, problem
        if value is None:
            return None, None
        total += sign * value
    return total, None


def _same_end(periods: list[dict], period: dict) -> list[dict]:
    """Периоды с той же датой конца, включая период оси коэффициента.

    Остаток на другой оси цитируется по этой дате. Период без даты остаётся один.
    """

    end = period.get("period_end")
    found = []
    seen = set()
    for item in periods:
        own = (item.get("axis_id"), item.get("period_id"))
        if own in seen:
            continue
        if own == (period.get("axis_id"), period.get("period_id")) or (end is not None and item.get("period_end") == end):
            seen.add(own)
            found.append(item)
    return found or [period]


def _total(
    keys,
    series: dict,
    side: Side,
    convention: str,
    *,
    pay_plus: bool,
    basis: dict | None = None,
    pay_names: frozenset[str] = frozenset(),
    aggregations: Mapping[str, str] | None = None,
) -> tuple[Decimal | None, str | None]:
    total = Decimal(0)
    for name in side.plus:
        part, problem = _part(
            keys, series, name, convention, pay_plus or name in pay_names, basis, aggregations
        )
        if problem:
            return None, problem
        if part is None:
            return None, None
        total += part
    for name in side.minus:
        part, problem = _part(keys, series, name, convention, True, basis, aggregations)
        if problem:
            return None, problem
        if part is None:
            return None, None
        total -= part
    return total, None


def _chosen_keys(keys, name: str, basis: dict | None, aggregations: Mapping[str, str] | None):
    """Ключи окна, которые входят в свёртку. `average` и `none` на нескольких ключах не сворачиваются."""

    fold = None if not aggregations else aggregations.get(name)
    if fold == "average" and len(keys) > 1:
        return None, "not_folded"
    if keys and ((basis and basis.get(name) == "ltm") or fold == "last"):
        return keys[-1:], None
    if fold == "none" and len(keys) > 1:
        return None, "not_folded"
    return list(keys), None


def _cite_used(book, period: dict, aligned: dict, used: tuple[tuple[str, tuple], ...], operand: str) -> None:
    if book is None:
        return
    result_axis = period.get("axis_id")
    result_period = period.get("period_id")
    taken = set()
    for concept, key in used:
        for obs in book.observations or []:
            if obs.concept != concept:
                continue
            own = (obs.axis_id, obs.period_id)
            if aligned.get(own, own) != key:
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
                    binding_key=obs.binding_key,
                )
            )


def _operand_refs(book, period: dict, operand: str) -> tuple[str, ...]:
    if book is None:
        return ()
    period_id = None if period.get("period_id") is None else str(period.get("period_id"))
    axis_id = None if period.get("axis_id") is None else str(period.get("axis_id"))
    refs = []
    for item in book.fact_uses or []:
        if item.result_axis_id != axis_id or item.result_period_id != period_id or item.operand != operand:
            continue
        refs.append(f"cell:{item.cell_id}" if item.cell_id else f"fact:{item.axis_id}:{item.period_id}")
    return tuple(refs)


def _record_period(book, period, status, reason, value, numerator, denominator, steps, window) -> None:
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
            window_periods=tuple(window or ()),
        )
    )


def _part(
    keys,
    series: dict,
    name: str,
    convention: str,
    pay: bool,
    basis: dict | None = None,
    aggregations: Mapping[str, str] | None = None,
) -> tuple[Decimal | None, str | None]:
    """Складывает окно. `ltm` и `last` берутся на конец. `none` и `average` не сворачиваются."""

    chosen, problem = _chosen_keys(keys, name, basis, aggregations)
    if problem:
        return None, problem
    assert chosen is not None
    total = Decimal(0)
    for key in chosen:
        if key not in series[name]:
            return None, None
        value = series[name][key]
        total += _payment(value, convention) if pay else value
    return total, None


_NET_DEBT_ABSENT = (
    "Чистый долг не содержит значений на оси, по которой считается отношение к EBITDA. "
    "Коэффициент не рассчитан."
)
_EBITDA_STOCK = frozenset({"net_debt_ebitda", "total_debt_ebitda", "debt_off_balance_ebitda"})
_OFF_BALANCE_ABSENT = (
    "Забалансовые обязательства не привязаны. "
    "Показатель долговой нагрузки с их учётом не рассчитан."
)
_STOCK_ABSENT = (
    "Остаток долга не содержит значений на оси, по которой считается отношение к EBITDA. "
    "Коэффициент не рассчитан."
)


def _refused(metric: str, periods: list[dict], status: str, message: str, inputs: list[str]) -> dict:
    """Явный статус вместо числа, когда основания или масштаб нельзя свести."""

    period = periods[0] if periods else None
    if period is None:
        row = {
            "metric": metric,
            "axis_id": None,
            "period_id": None,
            "value": None,
            "status": status,
            "reason": status,
            "message": message,
            "inputs": inputs,
        }
    else:
        row = _line(metric, period, None, status, status, inputs, None, message=message)
    return {"metric": metric, "rows": [row], "needs_input": [], "warnings": [], "status": status, "message": message}


def _line(metric, period, value, status, reason, inputs, window, message: str | None = None, **extra) -> dict:
    row = {
        "metric": metric,
        "axis_id": period["axis_id"],
        "period_id": period["period_id"],
        "period_key_base": period.get("period_key_base"),
        "period_marker": period.get("period_marker"),
        "value": value,
        "status": status,
        "reason": reason,
        "inputs": inputs,
        "window": window,
    }
    if message:
        row["message"] = message
    row.update(extra)
    return row


def _mismatch(rows, facts, bindings, periods, absent) -> list[dict]:
    primaries = _primaries(bindings, absent)
    book = primaries.get("dscr_covenant")
    if book is None:
        return []
    aligned = aligned_keys(periods)
    cached = _sums(facts, book, aligned, periods)
    for row in rows:
        if row.get("value") is None:
            continue
        key = aligned.get((row["axis_id"], row["period_id"]), (row["axis_id"], row["period_id"]))
        other = cached.get(key)
        if other is None or abs(Decimal(row["value"]) - other) <= _MISMATCH:
            continue
        return [
            {
                "code": "covenant_definition_mismatch",
                "params": {
                    "metric": "dscr",
                    "period_id": row["period_id"],
                    "fas": str(row["value"]),
                    "model": str(other),
                },
            }
        ]
    return []


# Пустое и ошибочное значение ячейки не является числом покрытия и не читается как ноль.
_NOT_A_NUMBER = frozenset({"empty", "not_applicable", "error", "missing"})


def _escrow_coverage_book(rows, facts, bindings, periods, absent, warnings) -> list[dict]:
    """Сверяет покрытие эскроу со строкой книги. Допуск — 0,005.

    Ячейка ищется по ключу шкалы суммы: `timeline_id` и `period_index`.
    Строка книги не суммируется, пустая ячейка с нормализованным нулём остаётся
    пустой. На одном ключе берётся ячейка оси результата; если её нет и чужая
    ячейка ровно одна, берётся она. Пустая ячейка совпадает с нулевым
    знаменателем и вторым предупреждением не становится. Число 0 в книге — уже
    расхождение. Ставка из покрытия этого месяца не считается.
    """

    book = _primaries(bindings, absent).get("escrow_coverage")
    if book is None:
        return []
    aligned = aligned_keys(periods)
    grouped: dict[tuple, list[dict]] = {}
    for fact in facts:
        if fact.get("row_key") != book.get("row_key"):
            continue
        own = (fact.get("axis_id"), fact.get("period_id"))
        grouped.setdefault(aligned.get(own, own), []).append(fact)
    noted = _zero_denominator_periods(warnings)
    extra = []
    for row in rows:
        period = row.get("period_id")
        own = (row.get("axis_id"), period)
        chosen = _aligned_coverage(grouped.get(aligned.get(own, own), []), row.get("axis_id"))
        state, number = _coverage_state(chosen)
        if state == "blank" and (row.get("reason") == "zero_denominator" or period in noted):
            continue
        if state != "number":
            if state == "blank" and row.get("value") is not None:
                extra.append(_coverage_warning(row, row.get("value"), None))
            continue
        fas = row.get("value")
        if fas is None:
            extra.append(_coverage_warning(row, None, number))
            continue
        if abs(Decimal(fas) - number) <= _MISMATCH:
            continue
        extra.append(_coverage_warning(row, fas, number))
    return extra


def _aligned_coverage(facts: list[dict], axis) -> dict | None:
    """Ячейка оси результата. Нет её — ровно одна чужая ячейка того же ключа."""

    home = [fact for fact in facts if fact.get("axis_id") == axis]
    if len(home) == 1:
        return home[0]
    if home or len(facts) != 1:
        return None
    return facts[0]


def _zero_denominator_periods(warnings) -> set:
    found = set()
    for item in warnings:
        params = item.get("params") if isinstance(item.get("params"), dict) else {}
        if item.get("code") != "zero_denominator" and params.get("reason") != "zero_denominator":
            continue
        period = params.get("period_id", item.get("period_id"))
        if period is not None:
            found.add(period)
    return found


def _coverage_state(fact) -> tuple[str, Decimal | None]:
    """`blank` — пустая ячейка, в том числе если рядом лежит нормализованный ноль."""

    if not isinstance(fact, dict):
        return "absent", None
    if fact.get("value_status") in _NOT_A_NUMBER:
        return "blank", None
    if "value_dec" in fact:
        number = _as_decimal(fact.get("value_dec"))
        return ("blank", None) if number is None else ("number", number)
    number = _as_decimal(fact.get("normalized_value"))
    return ("blank", None) if number is None else ("number", number)


def _as_decimal(value) -> Decimal | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _coverage_warning(row, fas, model) -> dict:
    return {
        "code": "escrow_coverage_book_mismatch",
        "params": {
            "metric": "escrow_coverage",
            "period_id": row.get("period_id"),
            "fas": None if fas is None else format(Decimal(fas), "f"),
            "model": None if model is None else format(Decimal(model), "f"),
            "message": "Покрытие эскроу расходится со строкой книги.",
        },
    }
