"""Ветви специализированных формул. Алгоритм остаётся в своём модуле.

Чтение вне объявленной ветви отказывается во время прогона. Объединение
dynamic_names для этого не годится: оно смешивает все ветки сразу.
Использование — сущность, которую деятельность реально читает:
https://www.w3.org/TR/prov-dm/#term-usage
Контекст прогона отделён от описания работы:
https://openlineage.io/docs/spec/object-model/
"""

from __future__ import annotations

from collections.abc import Mapping
from contextvars import ContextVar
from dataclasses import dataclass, replace

from finance_analysis.domain.execution_contract import (
    ExecutionBranchDefinition,
    ExecutionContractError,
    ExecutionTrace,
    bind_branch,
    read_input,
    reset_branch,
    trace_for,
)
from finance_analysis.domain.metric_contract import UndeclaredInput

_FLOWS = ("cfo_statement", "cfi_statement", "financing_inflows")
_SENIOR = ("senior_principal", "senior_interest_paid")
_DEBT = ("principal", "interest", "debt_service")
_HOUSING_FLAGS = ("interest_addback", "include_senior_fees", "include_senior_swaps")
_BANK_FLAGS = (
    "lease_mode",
    "ebitda_definition",
    "finance_costs_confirmed",
    "include_rou_depreciation",
)
_CORE = ("cfads", "debt_service")
_LOAN = ("debt_service", "cfads", "debt_outstanding", "discount_rate")


@dataclass(frozen=True)
class _Shape:
    numerator_plus: tuple[str, ...]
    denominator_plus: tuple[str, ...] = ()
    numerator_minus: tuple[str, ...] = ()
    denominator_minus: tuple[str, ...] = ()
    rate: str | None = None
    window: str | None = None
    optional_numerator: tuple[str, ...] = ()
    optional_denominator: tuple[str, ...] = ()
    optional_minus: tuple[str, ...] = ()


class _Run:
    def __init__(self, branch: ExecutionBranchDefinition, trace: ExecutionTrace) -> None:
        self.branch = branch
        self.trace = trace
        self.cells: list[str] = []


_active: ContextVar[_Run | None] = ContextVar("execution_branch_run", default=None)
_last: ContextVar[ExecutionTrace | None] = ContextVar("execution_branch_trace", default=None)
_SHAPES: dict[str, tuple[_Shape, ...]] = {}


def _keep(branch: ExecutionBranchDefinition, *shapes: _Shape) -> ExecutionBranchDefinition:
    _SHAPES[branch.branch_id] = shapes
    return branch


def _core_shape() -> _Shape:
    return _Shape(("cfads",), ("debt_service",))


ADSCR = _keep(
    ExecutionBranchDefinition("adscr", "metric:adscr", _CORE, (), ("adscr_direction",)),
    _core_shape(),
)
DSCR_MIN = _keep(
    ExecutionBranchDefinition("dscr_min", "reduction:min", _CORE, (), ()),
    _core_shape(),
)
DSCR_AVG = _keep(
    ExecutionBranchDefinition("dscr_avg", "reduction:avg", _CORE, (), ()),
    _core_shape(),
)
CASH = _keep(
    ExecutionBranchDefinition(
        "dscr.cash_covenant",
        "variant:cash_covenant",
        ("operating_cash_flow", "interest_paid", "capex", "principal"),
        ("other_financial_debt_service",),
        (),
    ),
    _Shape(
        ("operating_cash_flow", "interest_paid"),
        ("principal", "interest_paid"),
        ("capex",),
        (),
        None,
        "period",
        (),
        ("other_financial_debt_service",),
    ),
)
LLCR = _keep(
    ExecutionBranchDefinition("llcr", "metric:llcr", _LOAN, (), ("llcr_basis",)),
    _Shape(("cfads",), ("debt_outstanding",), rate="discount_rate"),
)
PLCR = _keep(
    ExecutionBranchDefinition("plcr", "metric:plcr", _LOAN, (), ("llcr_basis",)),
    _Shape(("cfads",), ("debt_outstanding",), rate="discount_rate"),
)
FCFF = _keep(
    ExecutionBranchDefinition(
        "fcff",
        "metric:fcff",
        ("operating_cash_flow", "capex"),
        ("interest", "interest_paid", "income_tax_rate"),
        (),
    ),
    _Shape(("operating_cash_flow",), (), ("capex",), rate="income_tax_rate"),
)
NPV = _keep(
    ExecutionBranchDefinition("npv", "metric:npv", ("project_fcf", "discount_rate"), (), ()),
    _Shape(("project_fcf",), rate="discount_rate"),
)
IRR = _keep(
    ExecutionBranchDefinition("irr", "metric:irr", ("project_fcf",), (), ()),
    _Shape(("project_fcf",),),
)
LEASE_DIRECT = _keep(
    ExecutionBranchDefinition(
        "icr_lease.direct",
        "mode:direct",
        ("ebitda", "interest", "lease_interest"),
        (),
        (),
    ),
    _Shape(("ebitda",), ("interest", "lease_interest"), window="period"),
)
LEASE_PAIR = _keep(
    ExecutionBranchDefinition(
        "icr_lease.pair",
        "mode:pair",
        ("ebitda", "interest", "lease_payment", "lease_principal"),
        (),
        (),
    ),
    _Shape(("ebitda",), ("interest", "lease_payment"), denominator_minus=("lease_principal",), window="period"),
)
ESCROW = _keep(
    ExecutionBranchDefinition(
        "escrow_blended_rate",
        "metric:escrow_blended_rate",
        ("escrow_balance", "debt_outstanding"),
        ("effective_rate",),
        ("escrow_rate_scale",),
    ),
    _Shape(("escrow_balance",), ("debt_outstanding",), window="period"),
)


def housing_flags(profile: Mapping[str, object] | None) -> tuple[bool, bool, bool] | str:
    """Те же три флага, что читает жилищный DSCR. Чужое значение не становится ложью."""

    flag = _bool_flag(profile, "interest_addback")
    fees = _bool_flag(profile, "include_senior_fees")
    swaps = _bool_flag(profile, "include_senior_swaps")
    if flag is None:
        return "interest_addback: true или false"
    if fees is None:
        return "include_senior_fees: true или false"
    if swaps is None:
        return "include_senior_swaps: true или false"
    return flag, fees, swaps


def housing_values(flag: bool, fees: bool, swaps: bool, direction: str | None = None) -> dict[str, object]:
    values: dict[str, object] = {
        "interest_addback": flag,
        "include_senior_fees": fees,
        "include_senior_swaps": swaps,
    }
    if direction is not None:
        values["adscr_direction"] = direction
    return values


def housing_branch(fees: bool, swaps: bool) -> ExecutionBranchDefinition:
    return _housing("dscr", fees, swaps)


def _housing(metric: str, fees: bool, swaps: bool) -> ExecutionBranchDefinition:
    required = [*_FLOWS, *_SENIOR]
    optional = list(_DEBT)
    suffix = ""
    if fees:
        required.append("senior_fees")
        suffix += ".fees"
    if swaps:
        required.append("senior_swaps")
        suffix += ".swaps"
    deps = _HOUSING_FLAGS
    if metric == "adscr":
        deps = (*_HOUSING_FLAGS, "adscr_direction")
    branch = ExecutionBranchDefinition(
        f"{metric}.housing{suffix}",
        f"variant:housing fees={fees} swaps={swaps}",
        tuple(required),
        tuple(optional),
        deps,
    )
    return _keep(branch, _Shape(_FLOWS, tuple(required[len(_FLOWS) :]), window="period"))


def _bank(kind: str, mode: str) -> ExecutionBranchDefinition:
    suffix = ""
    if kind == "ras":
        suffix += ".ras"
        required = ("profit_from_sales", "depreciation_notes", "interest")
        optional = ("depreciation_rou", "finance_costs", "lease_interest", "lease_payments", "lease_principal")
        shapes = (
            _Shape(
                ("profit_from_sales", "depreciation_notes"),
                ("interest",),
                window="LTM",
                optional_numerator=("depreciation_rou",),
                optional_denominator=("finance_costs",),
            ),
        )
    elif kind == "ifrs":
        suffix += ".ifrs"
        required = ("ifrs_operating_profit", "depreciation_notes", "interest")
        optional = ("depreciation_rou", "finance_costs", "lease_interest", "lease_payments", "lease_principal")
        shapes = (
            _Shape(
                ("ifrs_operating_profit", "depreciation_notes"),
                ("interest",),
                window="LTM",
                optional_numerator=("depreciation_rou",),
                optional_denominator=("finance_costs",),
            ),
        )
    else:
        required = ("ebitda", "interest")
        optional = ("finance_costs", "lease_interest", "lease_payments", "lease_principal")
        shapes = (_Shape(("ebitda",), ("interest",), window="LTM", optional_denominator=("finance_costs",)),)
    if mode == "add_interest":
        suffix += ".add"
        if kind in {"ras", "ifrs"}:
            shapes = (
                _Shape(
                    shapes[0].numerator_plus,
                    ("interest", "lease_interest"),
                    window="LTM",
                    optional_numerator=shapes[0].optional_numerator,
                    optional_denominator=("finance_costs",),
                ),
                _Shape(
                    shapes[0].numerator_plus,
                    ("interest", "lease_payments"),
                    denominator_minus=("lease_principal",),
                    window="LTM",
                    optional_numerator=shapes[0].optional_numerator,
                    optional_denominator=("finance_costs",),
                ),
            )
        else:
            shapes = (
                _Shape(("ebitda",), ("interest", "lease_interest"), window="LTM", optional_denominator=("finance_costs",)),
                _Shape(
                    ("ebitda",),
                    ("interest", "lease_payments"),
                    denominator_minus=("lease_principal",),
                    window="LTM",
                    optional_denominator=("finance_costs",),
                ),
            )
    return _keep(
        ExecutionBranchDefinition(
            f"icr.bank{suffix}",
            f"standard:{kind} mode:{mode}",
            required,
            optional,
            _BANK_FLAGS,
        ),
        *shapes,
    )


def bank_values(profile: Mapping[str, object] | None, kind: str, mode: str) -> dict[str, object]:
    raw = (profile or {}).get("icr_definition")
    body = raw if isinstance(raw, dict) else {}
    return {
        "lease_mode": mode,
        "ebitda_definition": kind,
        "finance_costs_confirmed": body.get("finance_costs_confirmed") is True,
        "include_rou_depreciation": body.get("include_rou_depreciation") is True,
    }


def _nominal(choice: str) -> ExecutionBranchDefinition:
    if choice == "domrf":
        return _keep(
            ExecutionBranchDefinition(
                "llcr.domrf",
                "variant:domrf",
                (*_FLOWS, "credit_limit", *_SENIOR),
                _DEBT,
                (),
            ),
            _Shape(_FLOWS, ("credit_limit", "senior_interest_paid"), window="period"),
        )
    return _keep(
        ExecutionBranchDefinition(
            "llcr.cbr590",
            "variant:cbr590",
            (*_FLOWS, *_SENIOR),
            (*_DEBT, "guaranteed_funds"),
            ("guaranteed_funds_none",),
        ),
        _Shape((*_FLOWS, "guaranteed_funds"), _SENIOR, window="period"),
    )


def branch_for(
    metric: str,
    *,
    variant: str | None = None,
    profile: Mapping[str, object] | None = None,
    lease_mode: str | None = None,
) -> ExecutionBranchDefinition | None:
    """Ветвь этого вызова. None — флаги не выбраны, калькулятор сам пишет прежний отказ."""

    if metric in {"adscr", "dscr_min", "dscr_avg"} and _is_housing(variant, profile):
        parsed = housing_flags(profile)
        if isinstance(parsed, str):
            return None
        return _housing(metric, parsed[1], parsed[2])
    if metric == "adscr":
        return ADSCR
    if metric == "dscr_min":
        return DSCR_MIN
    if metric == "dscr_avg":
        return DSCR_AVG
    if metric == "dscr" and (variant == "cash_covenant" or _named(profile, "dscr_definition") == "cash_covenant"):
        return CASH
    if metric == "dscr" and (variant == "housing" or _is_housing(variant, profile)):
        parsed = housing_flags(profile)
        if isinstance(parsed, str):
            return None
        return housing_branch(parsed[1], parsed[2])
    if metric == "llcr":
        choice = variant or _named(profile, "llcr_definition")
        if choice in {"cbr590", "domrf"}:
            return _nominal(choice)
        return LLCR
    if metric == "plcr":
        return PLCR
    if metric == "fcff":
        return FCFF
    if metric == "npv":
        return NPV
    if metric == "irr":
        return IRR
    if metric == "icr_lease" and lease_mode in {"direct", "pair"}:
        return LEASE_DIRECT if lease_mode == "direct" else LEASE_PAIR
    if metric == "icr" and (variant == "bank" or _named(profile, "icr_definition") == "bank"):
        mode = _mode(profile)
        kind = _kind(profile)
        if mode not in {"in_interest", "add_interest"} or kind not in {"book", "ras", "ifrs"}:
            return None
        return _bank(kind, mode)
    if metric == "escrow_blended_rate":
        return ESCROW
    return None


def refuse_definition(metric: str, branch: ExecutionBranchDefinition | None, definition, plan) -> dict | None:
    """Определение, которое ветвь не считает. Калькулятор при отказе не вызывается."""

    if definition is None:
        return None
    if branch is None or not _shape_ok(branch, definition.normalized_expression):
        return _stop(metric, "unsupported_formula")
    extra = _plan_extra(branch, plan)
    if extra:
        raise UndeclaredInput(extra)
    return None


def run_branch(
    branch: ExecutionBranchDefinition,
    profile_values: Mapping[str, object],
    facts,
    bindings,
    function,
    *,
    periods=None,
):
    """Прогон внутри ветви. Уже открытая внешняя ветвь остаётся той, что пишет след."""

    if _active.get() is not None:
        return function()
    run = _Run(branch, trace_for(branch, profile_values))
    active_token = _active.set(run)
    branch_token = bind_branch(branch.branch_id)
    try:
        result = function()
    finally:
        reset_branch(branch_token)
        _active.reset(active_token)
    if isinstance(result, dict):
        run.trace = _complete(run.trace, result, facts, bindings, _alignment(periods), run.cells)
        _hide_horizon(result)
    _last.set(run.trace)
    return result


def use_branch(branch: ExecutionBranchDefinition, profile_values: Mapping[str, object]):
    trace = trace_for(branch, profile_values)
    run = _Run(branch, trace)
    active_token = _active.set(run)
    branch_token = bind_branch(branch.branch_id)

    class _Scope:
        def __enter__(self):
            return run

        def __exit__(self, *_args):
            reset_branch(branch_token)
            _active.reset(active_token)
            return False

    return _Scope()


def note_fact(fact) -> None:
    """Ячейка, чьё число читатель принял. Привязка, которую формула не открыла, сюда не попадает."""

    run = _active.get()
    if run is None or not isinstance(fact, Mapping):
        return
    run.cells.append(_cell_of(fact))


def _cell_of(fact: Mapping) -> str:
    cell = fact.get("cell_id")
    if cell:
        return str(cell)
    return f"{fact.get('row_key')}:{fact.get('axis_id')}:{fact.get('period_id')}"


def claim(name: str) -> None:
    """Чтение понятия выбранной ветвью. Вне ветви чтение не перехватывается."""

    run = _active.get()
    if run is None:
        return
    try:
        run.trace = read_input(run.branch, run.trace, name)
    except ExecutionContractError as exc:
        if exc.reason == "forbidden_input":
            raise UndeclaredInput(name) from exc
        raise


def take_trace() -> ExecutionTrace | None:
    trace = _last.get()
    _last.set(None)
    return trace


def clear_trace() -> None:
    _last.set(None)


def guarded(request_metric: str, branch: ExecutionBranchDefinition | None, definition, plan, call):
    """Отказ до вызова. След забирает исполнитель после возврата."""

    refused = refuse_definition(request_metric, branch, definition, plan)
    if refused is not None:
        clear_trace()
        return refused
    clear_trace()
    return call()


def _shape_ok(branch: ExecutionBranchDefinition, expr) -> bool:
    return any(_one(shape, expr) for shape in _SHAPES.get(branch.branch_id, ()))


def _one(shape: _Shape, expr) -> bool:
    if (expr.window or None) != shape.window:
        return False
    if expr.one_of or expr.rates or expr.aggregate or expr.terminal or expr.compare_with or expr.add_back or expr.base:
        return False
    if (expr.rate or None) != shape.rate:
        return False
    return (
        _fit(expr.numerator_plus, shape.numerator_plus, shape.optional_numerator)
        and _fit(expr.numerator_minus, shape.numerator_minus, ())
        and _fit(expr.denominator_plus, shape.denominator_plus, shape.optional_denominator)
        and _fit(expr.denominator_minus, shape.denominator_minus, shape.optional_minus)
    )


def _fit(actual: tuple[str, ...], required: tuple[str, ...], optional: tuple[str, ...]) -> bool:
    allowed = set(optional)
    kept = tuple(name for name in actual if name not in allowed)
    if kept != tuple(required):
        return False
    return all(name in required or name in allowed for name in actual)


def _plan_extra(branch: ExecutionBranchDefinition, plan) -> str | None:
    if plan is None:
        return None
    allowed = set(branch.required_inputs) | set(branch.optional_inputs)
    for item in getattr(plan, "inputs", ()) or ():
        if getattr(item, "confirmed", False) and not getattr(item, "ambiguous", False) and item.concept not in allowed:
            return item.concept
    return None


def _complete(
    trace: ExecutionTrace,
    result: Mapping[str, object],
    facts,
    _bindings,
    aligned: Mapping[tuple[str, str], tuple] | None = None,
    noted: list[str] | None = None,
) -> ExecutionTrace:
    slots = _slots(result)
    aligned = aligned or {}
    raw = set(slots)
    normalized = {aligned[pair] for pair in slots if pair in aligned}
    noted_ids = set(noted or ())
    uses: list[str] = []
    if slots and noted_ids:
        for fact in facts or []:
            if not isinstance(fact, Mapping):
                continue
            cell = _cell_of(fact)
            if cell not in noted_ids:
                continue
            pair = (str(fact.get("axis_id")), str(fact.get("period_id") or ""))
            key = aligned.get(pair)
            if pair not in raw and (key is None or key not in normalized):
                continue
            uses.append(cell)
    return replace(
        trace,
        actual_periods=tuple(dict.fromkeys(period for _axis, period in slots)),
        actual_period_slots=slots,
        actual_fact_uses=tuple(dict.fromkeys(uses)),
    )


def _alignment(periods) -> dict[tuple[str, str], tuple]:
    """Тот же ключ, что у aligned_keys: (timeline_id, period_index)."""

    if not periods:
        return {}
    from finance_analysis.domain.metrics import aligned_keys

    found: dict[tuple[str, str], tuple] = {}
    for (axis, period_id), key in aligned_keys(list(periods)).items():
        if axis is None or not period_id:
            continue
        found[(str(axis), str(period_id))] = key
    return found


def _hide_horizon(result: dict) -> None:
    rows = result.get("rows")
    if not isinstance(rows, list):
        return
    for row in rows:
        if isinstance(row, dict):
            row.pop("_trace_periods", None)


def _slots(result: Mapping[str, object]) -> tuple[tuple[str, str], ...]:
    """Пары ось–период строк результата. Пустой набор не означает «все факты»."""

    found: list[tuple[str, str]] = []
    for row in result.get("rows") or []:
        if not isinstance(row, Mapping):
            continue
        axis = row.get("axis_id")
        axis_text = None if axis is None else str(axis)
        period = row.get("period_id")
        if axis_text is not None and period:
            found.append((axis_text, str(period)))
        for key in ("window", "over", "_trace_periods"):
            items = row.get(key)
            if not isinstance(items, (list, tuple, set, frozenset)):
                continue
            for item in items:
                if isinstance(item, tuple) and len(item) == 2 and item[0] is not None and item[1]:
                    found.append((str(item[0]), str(item[1])))
                elif axis_text is not None and item:
                    found.append((axis_text, str(item)))
    return tuple(dict.fromkeys(found))


def _stop(metric: str, reason: str) -> dict:
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


def _bool_flag(profile: Mapping[str, object] | None, name: str) -> bool | None:
    if profile is None or name not in profile or profile.get(name) is None:
        return False
    raw = profile.get(name)
    if raw is True or raw is False:
        return raw
    return None


def _named(profile: Mapping[str, object] | None, key: str) -> str | None:
    raw = (profile or {}).get(key)
    if isinstance(raw, dict):
        variant = raw.get("variant")
        return variant if isinstance(variant, str) else None
    return None


def _is_housing(variant: str | None, profile: Mapping[str, object] | None) -> bool:
    return variant == "housing" or _named(profile, "dscr_definition") == "housing"


def _mode(profile: Mapping[str, object] | None) -> str | None:
    raw = (profile or {}).get("icr_definition")
    if not isinstance(raw, dict):
        return None
    mode = raw.get("lease_mode")
    return mode if isinstance(mode, str) else None


def _kind(profile: Mapping[str, object] | None) -> str:
    raw = (profile or {}).get("ebitda_definition")
    if raw in (None, ""):
        return "book"
    if raw in {"book", "ras", "ifrs", "gaap"}:
        return str(raw)
    return "invalid"

