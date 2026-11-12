"""Трассировка DSCR следует варианту типа, а не базовой формуле."""

from finance_analysis.application.financial_catalog import load_financial_catalog
from finance_analysis.application.model_types import load_model_types
from finance_analysis.domain.graphs import (
    MISSING_NO_PRIMARY,
    check_metric_physical_trace,
)
from finance_analysis.domain.model_type import resolve_trace_variant


def test_omitted_variant_follows_corporate_covenant():
    types = load_model_types()
    corporate = types.types["corporate"].variants
    assert resolve_trace_variant(None, "inferred", corporate, "dscr") == "corporate_covenant"
    assert resolve_trace_variant("pf", "inferred", corporate, "dscr") == "pf"
    assert resolve_trace_variant(None, "unresolved", corporate, "dscr") is None


def test_covenant_trace_names_cash_taxes_not_cfads():
    catalog = load_financial_catalog()
    indicator = catalog.indicators["dscr"]
    base = set(indicator.inputs.concepts)
    covenant = set(indicator.variants["corporate_covenant"].inputs.concepts)
    assert base == {"cfads", "debt_service"}
    assert "cash_taxes" in covenant
    assert "cfads" not in covenant
    assert "debt_service" not in covenant
    inputs = indicator.variants["corporate_covenant"].inputs.as_dict()
    trace, _findings = check_metric_physical_trace(
        "dscr",
        inputs=inputs,
        bindings=[
            {
                "model_id": "job",
                "build_key": "build",
                "binding_key": "ebitda",
                "row_key": "ebitda",
                "effective_concept": "ebitda",
                "concept": "ebitda",
                "is_primary": True,
                "status": "bound",
                "stale": False,
            }
        ],
        rows=[{"model_id": "job", "build_key": "build", "row_key": "ebitda", "binding_key": "ebitda"}],
        facts=[],
        variant="corporate_covenant",
        model_id="job",
        build_key="build",
    )
    concepts = [step.concept for step in trace.steps]
    assert "cash_taxes" in concepts
    assert "cfads" not in concepts
    assert "debt_service" not in concepts
    missing = [step.concept for step in trace.steps if step.missing_trace == MISSING_NO_PRIMARY]
    assert "cash_taxes" in missing
    assert trace.variant == "corporate_covenant"
