"""Auchan: тип corporate и пропуск ковенанта без cash_taxes — контракт, не дыра."""

from finance_analysis.application.model_types import load_model_types
from finance_analysis.domain.covenant import select_ratio
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
