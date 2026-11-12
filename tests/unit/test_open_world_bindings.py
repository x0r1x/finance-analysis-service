"""Каталог ограничивает смысл и не назначает понятие каждой строке."""

from finance_analysis.application.catalog import load_catalog
from finance_analysis.domain.candidates import Candidate, RowEvidence
from finance_analysis.domain.evaluation import ABSTAIN, ACCEPTED
from finance_analysis.domain.mapping import assign_rows, decide
from finance_analysis.domain.metrics import coverage_ratio
from finance_analysis.domain.validation.semantics import check_derived

_STATUSES = frozenset(
    {
        "bound",
        "bound_with_warning",
        "unknown",
        "ambiguous",
        "not_applicable",
        "ignored",
    }
)
_LABEL = "nonce-open-world-agency-fee-tranche"


def test_binding_statuses_partition_bind_and_abstain():
    assert ACCEPTED | ABSTAIN == _STATUSES
    assert not (ACCEPTED & ABSTAIN)
    assert "unknown" in ABSTAIN and "ambiguous" in ABSTAIN
    assert "bound" in ACCEPTED and "bound_with_warning" in ACCEPTED


def _row() -> dict:
    return {
        "kind": "fact",
        "binding_key": "fee",
        "row_key": "fee",
        "label": _LABEL,
        "label_path_text": f"Debt › {_LABEL}",
        "sign": None,
        "unit": "money",
    }


def test_label_outside_the_glossary_stays_unknown():
    item = assign_rows([_row()], [], load_catalog())["fee"]
    assert item.status == "unknown"
    assert item.concept is None
    assert item.is_primary is False
    assert item.status in ABSTAIN


def test_nearest_cosine_does_not_bind():
    glossary = load_catalog()
    found = RowEvidence(
        candidates=(Candidate("cfads", recall_cos=0.92),),
        nearest_concept_cos=0.92,
    )
    item = decide(_row(), found, glossary, None)
    assert item.status == "ambiguous"
    assert item.status in ABSTAIN
    assert item.is_primary is False
    assert item.concept == "cfads"
    got = coverage_ratio(
        metric="dscr",
        facts=[
            {
                "row_key": "fee",
                "axis_id": "Sheet!r1",
                "period_id": "p",
                "normalized_value": "100",
                "value_status": "cached",
            },
            {
                "row_key": "debt",
                "axis_id": "Sheet!r1",
                "period_id": "p",
                "normalized_value": "40",
                "value_status": "cached",
            },
        ],
        bindings=[
            {
                "row_key": "fee",
                "binding_key": "fee",
                "is_primary": item.is_primary,
                "status": item.status,
                "effective_concept": item.concept,
                "concept": item.concept,
                "source": item.source,
            },
            {
                "row_key": "debt",
                "binding_key": "debt",
                "is_primary": True,
                "status": "bound",
                "effective_concept": "debt_service",
                "source": "inferred",
            },
        ],
        periods=[
            {
                "axis_id": "Sheet!r1",
                "period_id": "p",
                "period_key_base": "p",
                "marker_class": None,
            }
        ],
        period_phase={},
        explicit_phases=False,
    )
    assert got["status"] == "needs_input"
    assert got["rows"] == []
    assert got["needs_input"] == [
        {"kind": "concept", "reason": "ambiguous", "subject": "cfads"}
    ]


def test_weak_nearest_stays_unknown_and_has_no_dscr():
    glossary = load_catalog()
    found = RowEvidence(
        candidates=(Candidate("cfads", recall_cos=0.4),),
        nearest_concept_cos=0.4,
    )
    item = decide(_row(), found, glossary, None)
    assert item.status == "unknown"
    assert item.concept is None
    assert item.is_primary is False
    assert item.evidence["nil"] == "threshold"
    got = coverage_ratio(
        metric="dscr",
        facts=[
            {
                "row_key": "fee",
                "axis_id": "Sheet!r1",
                "period_id": "p",
                "normalized_value": "100",
                "value_status": "cached",
            },
            {
                "row_key": "debt",
                "axis_id": "Sheet!r1",
                "period_id": "p",
                "normalized_value": "40",
                "value_status": "cached",
            },
        ],
        bindings=[
            {
                "row_key": "fee",
                "binding_key": "fee",
                "is_primary": item.is_primary,
                "status": item.status,
                "effective_concept": item.concept,
                "concept": item.concept,
                "source": item.source,
            },
            {
                "row_key": "debt",
                "binding_key": "debt",
                "is_primary": True,
                "status": "bound",
                "effective_concept": "debt_service",
                "source": "inferred",
            },
        ],
        periods=[
            {
                "axis_id": "Sheet!r1",
                "period_id": "p",
                "period_key_base": "p",
                "marker_class": None,
            }
        ],
        period_phase={},
        explicit_phases=False,
    )
    assert got["status"] == "missing_input"
    assert got["rows"] == []
    assert got["needs_input"] == [
        {"kind": "concept", "reason": "concept_unknown", "subject": "cfads"}
    ]


def test_dictionary_allows_null_and_rejects_a_made_up_concept():
    catalog = load_catalog().ids
    allowed = check_derived(
        {
            "bindings": [
                {
                    "row_key": "fee",
                    "concept": None,
                    "effective_concept": None,
                    "is_primary": False,
                    "status": "unknown",
                }
            ]
        },
        catalog=catalog,
        row_keys=frozenset({"fee"}),
    )
    assert allowed.accepted
    rejected = check_derived(
        {
            "bindings": [
                {
                    "row_key": "fee",
                    "concept": "agency_fee_quirk",
                    "effective_concept": "agency_fee_quirk",
                    "is_primary": True,
                    "status": "bound",
                }
            ]
        },
        catalog=catalog,
        row_keys=frozenset({"fee"}),
    )
    assert rejected.accepted is False
    assert rejected.code == "concept_not_in_catalog"
