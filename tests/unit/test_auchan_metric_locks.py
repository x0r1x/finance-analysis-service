"""Auchan: тип corporate и пропуск ковенанта без cash_taxes — контракт, не дыра.

Строка DSCR книги закрывает только пустой результат со статусом missing_input или needs_input.
"""

import pytest

from finance_analysis.application.model_types import load_model_types
from finance_analysis.domain.covenant import _reported_book_dscr, select_ratio
from finance_analysis.domain.model_type import applicability

_OFF = (
    "adscr",
    "dscr_min",
    "dscr_avg",
    "llcr",
    "plcr",
    "escrow_coverage",
    "escrow_blended_rate",
    "npv",
    "irr",
)


def test_corporate_leaves_project_metrics_not_applicable():
    catalog = load_model_types()
    labels = ("corporate",)
    for metric in _OFF:
        assert applicability(catalog, labels, metric) == "not_applicable"
    assert applicability(catalog, labels, "dscr") == "optional"
    assert applicability(catalog, labels, "icr") == "required"
    assert applicability(catalog, labels, "icr_ebit") == "optional"
    assert catalog.types["corporate"].variants["dscr"] == "corporate_covenant"


def _primary(concept: str) -> dict:
    return {
        "row_key": concept,
        "binding_key": concept,
        "is_primary": True,
        "status": "bound",
        "effective_concept": concept,
        "source": "inferred",
    }


def test_covenant_dscr_does_not_run_without_cash_taxes():
    types = load_model_types()
    present = ("ebitda", "capex", "interest", "principal")
    bindings = [_primary(name) for name in present]
    bindings.append(
        {
            "row_key": "tax",
            "binding_key": "tax",
            "is_primary": False,
            "status": "unknown",
            "effective_concept": None,
            "source": "inferred",
        }
    )
    got = select_ratio(
        "dscr",
        "corporate_covenant",
        {
            "facts": [],
            "bindings": bindings,
            "periods": [],
            "period_phase": {},
            "explicit_phases": False,
            "sign_convention": "outflow_negative",
            "marker_class": None,
            "absent": frozenset(),
        },
        profile=None,
        profile_ref=None,
        composed=types.composed,
        concepts=frozenset(present) | {"cash_taxes", "cfads", "debt_service"},
        money=frozenset(present) | {"cash_taxes"},
        interest_order=types.interest_order,
        row_fallbacks=types.row_fallbacks,
    )
    assert got["status"] == "missing_input"
    assert got["rows"] == []
    assert "cash_taxes" in got["missing_inputs"]
    assert got["needs_input"][0]["subject"] == "cash_taxes"


def test_book_dscr_is_reported_when_the_covenant_cannot_run():
    """The sheet's DSCR stays visible. CFADS / debt service is not substituted."""
    from decimal import Decimal

    types = load_model_types()
    present = ("ebitda", "capex", "interest", "principal", "cfads", "debt_service")
    bindings = [_primary(name) for name in present]
    bindings.append(
        {
            "row_key": "book-dscr",
            "binding_key": "book-dscr",
            "is_primary": True,
            "status": "bound",
            "effective_concept": "dscr",
            "source": "inferred",
        }
    )
    got = select_ratio(
        "dscr",
        "corporate_covenant",
        {
            "facts": [
                {
                    "row_key": "book-dscr",
                    "axis_id": "Outputs!r1",
                    "period_id": "2016",
                    "normalized_value": "1.476",
                    "value_status": "cached",
                },
                {
                    "row_key": "cfads",
                    "axis_id": "Outputs!r1",
                    "period_id": "2016",
                    "normalized_value": "9",
                    "value_status": "cached",
                },
                {
                    "row_key": "debt_service",
                    "axis_id": "Outputs!r1",
                    "period_id": "2016",
                    "normalized_value": "4",
                    "value_status": "cached",
                },
            ],
            "bindings": bindings,
            "periods": [{"axis_id": "Outputs!r1", "period_id": "2016", "period_key_base": "2016"}],
            "period_phase": {},
            "explicit_phases": False,
            "sign_convention": "outflow_negative",
            "marker_class": None,
            "absent": frozenset(),
        },
        profile=None,
        profile_ref=None,
        composed=types.composed,
        concepts=frozenset(present) | {"cash_taxes", "dscr"},
        money=frozenset(present) | {"cash_taxes"},
        interest_order=types.interest_order,
        row_fallbacks=types.row_fallbacks,
    )
    assert got["status"] == "succeeded"
    assert got["definition_source"] == "reported"
    assert [(row["variant"], row["value"]) for row in got["rows"]] == [("reported", Decimal("1.476"))]
    assert "cash_taxes" in got["missing_inputs"]
    warning = next(item for item in got["warnings"] if item["code"] == "dscr_reported")
    assert warning["params"]["variant"] == "corporate_covenant"
    assert "cash_taxes" in warning["params"]["inputs"]


def test_computed_catalog_dscr_does_not_take_the_book_row():
    """A formula that produced a number stays that number. The book cell is not a second row."""
    from decimal import Decimal

    types = load_model_types()
    bindings = [_primary("cfads"), _primary("debt_service"), _primary("dscr")]
    got = select_ratio(
        "dscr",
        None,
        {
            "facts": [
                {
                    "row_key": "dscr",
                    "axis_id": "Outputs!r1",
                    "period_id": "2016",
                    "normalized_value": "1.476",
                    "value_status": "cached",
                },
                {
                    "row_key": "cfads",
                    "axis_id": "Outputs!r1",
                    "period_id": "2016",
                    "normalized_value": "9",
                    "value_status": "cached",
                },
                {
                    "row_key": "debt_service",
                    "axis_id": "Outputs!r1",
                    "period_id": "2016",
                    "normalized_value": "4",
                    "value_status": "cached",
                },
            ],
            "bindings": bindings,
            "periods": [{"axis_id": "Outputs!r1", "period_id": "2016", "period_key_base": "2016"}],
            "period_phase": {},
            "explicit_phases": False,
            "sign_convention": "outflow_negative",
            "marker_class": None,
            "absent": frozenset(),
        },
        profile=None,
        profile_ref=None,
        composed=types.composed,
        concepts=frozenset({"cfads", "debt_service", "dscr", "cash_taxes"}),
        money=frozenset({"cfads", "debt_service", "cash_taxes"}),
        interest_order=types.interest_order,
        row_fallbacks=types.row_fallbacks,
    )
    assert [row.get("variant") for row in got["rows"]] == [None]
    assert got["rows"][0]["value"] == Decimal("2.2500000000")
    assert all(item.get("code") != "dscr_reported" for item in got["warnings"])
    assert got.get("definition_source") != "reported"


def _book_attempt(status: str, *, value: str | None) -> dict:
    return {
        "metric": "dscr",
        "rows": [{"value": value, "status": status, "variant": None}],
        "needs_input": [],
        "warnings": [],
        "status": status,
        "missing_inputs": [],
    }


def _book_call(attempt: dict) -> dict:
    return _reported_book_dscr(
        attempt,
        variant="catalog",
        facts=[
            {
                "row_key": "dscr",
                "axis_id": "A",
                "period_id": "Y1",
                "normalized_value": "3.5",
            }
        ],
        bindings=[_primary("dscr")],
        periods=[{"axis_id": "A", "period_id": "Y1"}],
        absent=frozenset(),
    )


@pytest.mark.parametrize("status", ["scale_unconfirmed", "basis_mismatch", "no_debt_service", "input_absent"])
def test_other_recalculation_statuses_do_not_take_the_book_row(status):
    """A refusal that is not a missing input stays that refusal, even when the book has a DSCR cell.

    The attempt has no number. A value would return before the status check and hide the contract.
    """
    attempt = _book_attempt(status, value=None)
    assert _book_call(attempt) is attempt


def test_needs_input_reports_the_book_row_and_keeps_the_question():
    """Two primaries of one input are needs_input. The book cell is shown, the question stays."""
    from decimal import Decimal

    types = load_model_types()
    second = _primary("debt_service")
    second = {**second, "row_key": "debt-service-2", "binding_key": "debt-service-2"}
    got = select_ratio(
        "dscr",
        None,
        {
            "facts": [
                {
                    "row_key": "dscr",
                    "axis_id": "A",
                    "period_id": "Y1",
                    "normalized_value": "3.5",
                }
            ],
            "bindings": [_primary("cfads"), _primary("debt_service"), second, _primary("dscr")],
            "periods": [{"axis_id": "A", "period_id": "Y1"}],
            "period_phase": {},
            "explicit_phases": False,
            "sign_convention": "outflow_negative",
            "marker_class": None,
            "absent": frozenset(),
        },
        profile=None,
        profile_ref=None,
        composed=types.composed,
        concepts=frozenset({"cfads", "debt_service", "dscr"}),
        money=frozenset({"cfads", "debt_service"}),
        interest_order=types.interest_order,
        row_fallbacks=types.row_fallbacks,
    )
    assert got["status"] == "succeeded"
    assert got["definition_source"] == "reported"
    assert [(row["variant"], row["value"]) for row in got["rows"]] == [("reported", Decimal("3.5"))]
    assert got["needs_input"][0]["reason"] == "ambiguous"
    assert "debt_service" in got["missing_inputs"]


def test_reported_fallback_keeps_the_attempt_trace():
    """The formula that did not run stays. The published book cell is a separate read.

    Selective classification does not fill a refusal with another definition
    (https://arxiv.org/abs/1705.08500). Here the formula did not run, and the
    number on the page is the cell that was read, not a quotient.
    """
    from decimal import Decimal

    from finance_analysis.domain.trace_limit import view_from_evidence

    types = load_model_types()
    collect: list = []
    binding = {**_primary("dscr"), "row_key": "model.dscr"}
    got = select_ratio(
        "dscr",
        None,
        {
            "facts": [
                {
                    "row_key": "model.dscr",
                    "axis_id": "A",
                    "period_id": "Y1",
                    "cell_id": "Model!D12",
                    "normalized_value": "3.5",
                }
            ],
            "bindings": [binding],
            "periods": [{"axis_id": "A", "period_id": "Y1"}],
            "period_phase": {},
            "explicit_phases": False,
            "sign_convention": "outflow_negative",
            "marker_class": None,
            "absent": frozenset(),
        },
        profile=None,
        profile_ref=None,
        composed=types.composed,
        concepts=frozenset({"cfads", "debt_service", "dscr"}),
        money=frozenset({"cfads", "debt_service"}),
        interest_order=types.interest_order,
        row_fallbacks=types.row_fallbacks,
        collect=collect,
    )
    assert got["definition_source"] == "reported"
    assert got["definition_ref"] == "model.dscr"
    assert [item.execution_status for item in collect] == ["not_run", "published"]
    attempt, published = collect
    assert got["rows"][0]["value"] == Decimal("3.5")
    assert attempt.fact_observations == ()
    assert attempt.published_read == published.implementation == "dscr.reported"
    assert view_from_evidence(attempt)["published_read"] == "dscr.reported"
    assert published.sums_additions == 0
    observed = published.fact_observations
    assert len(observed) == 1
    assert observed[0].cell_id == "Model!D12"
    assert observed[0].axis_id == "A"
    assert observed[0].period_id == "Y1"
    assert observed[0].raw_value == Decimal("3.5")
    assert observed[0].effective_value == Decimal("3.5")
    period = published.period_results[0]
    assert (period.axis_id, period.period_id) == ("A", "Y1")
    assert [step.operation for step in period.steps] == ["publication"]
    assert period.steps[0].parameters["row_key"] == "model.dscr"
    assert period.steps[0].input_refs == ("cell:Model!D12",)
    assert period.numerator is None and period.denominator is None


def test_published_read_keeps_the_attempt_plan_digest():
    """The published cell names the same plan as the attempt that did not run.

    The digest is the plan that chose the row, so a later audit can reproduce
    that choice (https://www.w3.org/TR/prov-dm/). The number stays the cell.
    """

    class _Need:
        subject = "cfads"

        def as_dict(self):
            return {"kind": "concept", "reason": "concept_unknown", "subject": self.subject}

    class _Plan:
        status = "missing_input"
        content_sha256 = "plan-digest-reported"
        needs_input = (_Need(),)
        warnings = ()
        inputs = ()
        diagnostic = ()
        rejected = ()
        fallbacks = ()

    types = load_model_types()
    collect: list = []
    got = select_ratio(
        "dscr",
        None,
        {
            "facts": [
                {
                    "row_key": "dscr",
                    "axis_id": "A",
                    "period_id": "Y1",
                    "cell_id": "Model!D12",
                    "normalized_value": "3.5",
                }
            ],
            "bindings": [_primary("dscr")],
            "periods": [{"axis_id": "A", "period_id": "Y1"}],
            "period_phase": {},
            "explicit_phases": False,
            "sign_convention": "outflow_negative",
            "marker_class": None,
            "absent": frozenset(),
        },
        profile=None,
        profile_ref=None,
        composed=types.composed,
        concepts=frozenset({"cfads", "debt_service", "dscr"}),
        money=frozenset({"cfads", "debt_service"}),
        interest_order=types.interest_order,
        row_fallbacks=types.row_fallbacks,
        plan=_Plan(),
        collect=collect,
    )
    assert got["definition_source"] == "reported"
    attempt, published = collect
    assert attempt.execution_status == "not_run"
    assert published.execution_status == "published"
    assert published.plan_content_sha256 == attempt.plan_content_sha256 == "plan-digest-reported"
    assert [step.operation for step in published.period_results[0].steps] == ["publication"]


def test_a_plan_that_rejected_the_book_row_does_not_report_it():
    """The book cell is a cache, not a second scan. A row the plan rejected stays out."""

    class _Need:
        subject = "cfads"

        def as_dict(self):
            return {"kind": "concept", "reason": "concept_unknown", "subject": self.subject}

    class _Rejected:
        concept = "dscr"
        binding_key = "dscr"
        row_key = None

    class _Plan:
        status = "missing_input"
        needs_input = (_Need(),)
        warnings = ()
        inputs = ()
        diagnostic = ()
        rejected = (_Rejected(),)
        fallbacks = ()

    types = load_model_types()
    got = select_ratio(
        "dscr",
        None,
        {
            "facts": [
                {
                    "row_key": "dscr",
                    "axis_id": "A",
                    "period_id": "Y1",
                    "normalized_value": "3.5",
                }
            ],
            "bindings": [_primary("dscr")],
            "periods": [{"axis_id": "A", "period_id": "Y1"}],
            "period_phase": {},
            "explicit_phases": False,
            "sign_convention": "outflow_negative",
            "marker_class": None,
            "absent": frozenset(),
        },
        profile=None,
        profile_ref=None,
        composed=types.composed,
        concepts=frozenset({"cfads", "debt_service", "dscr"}),
        money=frozenset({"cfads", "debt_service"}),
        interest_order=types.interest_order,
        row_fallbacks=types.row_fallbacks,
        plan=_Plan(),
    )
    assert got["status"] == "missing_input"
    assert got["rows"] == []
    assert got.get("definition_source") != "reported"
