"""Контракт идентичности CalculationEvidence.

Одинаковое каноническое тело, включая отпечаток реализации, даёт один evidence_id.
Повторная попытка не выпускает новый идентификатор. Идентичность плана — plan_content_sha256.

SHA-256 канонического тела: https://csrc.nist.gov/publications/detail/fips/180/4/final
Contract test: https://martinfowler.com/bliki/ContractTest.html
"""

from __future__ import annotations

from dataclasses import fields
from decimal import Decimal

from finance_analysis.domain.calculation_evidence import (
    BasisSide,
    CalculationEvidence,
    FactObservation,
    FactUse,
    PeriodResult,
    TransformationStep,
    seal,
)

# Сторона по фактическому _identity. basis_sides входит в хеш, хотя бриф его не назвал.
# published_read и evidence_id снаружи: бриф их не назвал. evidence_id — дайджест seal, не вход.
_IN_HASH = frozenset(
    {
        "actual_fact_uses",
        "actual_inputs",
        "actual_period_slots",
        "actual_periods",
        "basis_sides",
        "branch_id",
        "calculation_stamp",
        "definition_hash",
        "execution_status",
        "fact_observations",
        "fact_uses",
        "implementation",
        "marker_class",
        "metric",
        "parent_evidence_ids",
        "parent_period_ids",
        "period_results",
        "plan_content_sha256",
        "profile_values",
        "semantic_model_version",
        "sign_convention",
    }
)
_OUTSIDE_HASH = frozenset(
    {
        "calculation_origin",
        "definition_ref",
        "definition_source",
        "definition_version",
        "evidence_id",
        "evidence_status",
        "executor_id",
        "executor_version",
        "explicit_phases",
        "published_read",
        "sheet",
        "sums_additions",
    }
)

def _observation(concept: str = "cfads") -> FactObservation:
    return FactObservation(
        concept=concept,
        cell_id="c!Y1",
        axis_id="a",
        period_id="Y1",
        timeline_id="t",
        period_index=1,
        field="value",
        sheet=False,
        raw_value=Decimal(8),
        effective_value=Decimal(80),
        scale_factor=Decimal(10),
        scale_policy="thousands",
        scale_applied=True,
        normalization_source="sheet",
        considered="kept",
        binding_key="c",
    )


def _use(concept: str = "cfads") -> FactUse:
    return FactUse(
        concept=concept,
        cell_id="c!Y1",
        axis_id="a",
        period_id="Y1",
        timeline_id="t",
        period_index=1,
        field="value",
        sheet=False,
        raw_value=Decimal(8),
        effective_value=Decimal(80),
        scale_factor=Decimal(10),
        scale_policy="thousands",
        scale_applied=True,
        normalization_source="sheet",
        result_axis_id="a",
        result_period_id="Y1",
        operand="numerator",
        binding_key="c",
    )


def _period(status: str = "ok") -> PeriodResult:
    return PeriodResult(
        axis_id="a",
        period_id="Y1",
        status=status,
        reason=None,
        value=Decimal(8),
        numerator=Decimal(80),
        denominator=Decimal(10),
        steps=(
            TransformationStep(
                step_id=1,
                operation="divide",
                input_refs=("cfads", "debt_service"),
                output_value=Decimal(8),
                parameters={"precision": 38},
            ),
        ),
        node_id="n1",
    )


def _side(concept: str = "cfads") -> BasisSide:
    return BasisSide(concept=concept, period_basis="flow", source="header")


def _evidence(**overrides: object) -> CalculationEvidence:
    body: dict[str, object] = {
        "metric": "dscr",
        "execution_status": "succeeded",
        "implementation": "dscr@1",
        "calculation_stamp": "stamp-a",
        "plan_content_sha256": "plan-a",
        "sign_convention": "outflow_negative",
        "marker_class": "housing",
        "explicit_phases": False,
        "sheet": False,
        "fact_observations": (_observation(),),
        "fact_uses": (_use(),),
        "period_results": (_period(),),
        "basis_sides": (_side(),),
        "sums_additions": 1,
        "evidence_status": "evidence_available",
        "published_read": "full",
        "definition_version": "dscr@1",
        "executor_id": "calculate_coverage",
        "executor_version": "calculate_coverage@1",
        "definition_source": "catalog",
        "definition_ref": {"formula_id": "dscr"},
        "definition_hash": "hash-a",
        "branch_id": "branch-a",
        "actual_inputs": ("cfads",),
        "actual_fact_uses": ("cfads@Y1",),
        "actual_periods": ("Y1",),
        "actual_period_slots": (("a", "Y1"),),
        "profile_values": (("rate", "1"),),
        "parent_evidence_ids": ("parent-a",),
        "parent_period_ids": ("period-a",),
        "calculation_origin": "calculated",
        "evidence_id": None,
    }
    body.update(overrides)
    return CalculationEvidence(**body)  # type: ignore[arg-type]


_ALTERNATE: dict[str, object] = {
    "actual_fact_uses": ("ebitda@Y1",),
    "actual_inputs": ("ebitda",),
    "actual_period_slots": (("a", "Y2"),),
    "actual_periods": ("Y2",),
    "basis_sides": (_side("ebitda"),),
    "branch_id": "branch-b",
    "calculation_origin": "reused",
    "calculation_stamp": "stamp-b",
    "definition_hash": "hash-b",
    "definition_ref": {"formula_id": "icr"},
    "definition_source": "override",
    "definition_version": "dscr@9",
    "evidence_id": "preassigned",
    "evidence_status": "evidence_withheld",
    "execution_status": "failed",
    "executor_id": "other_executor",
    "executor_version": "other_executor@2",
    "explicit_phases": True,
    "fact_observations": (_observation("ebitda"),),
    "fact_uses": (_use("ebitda"),),
    "implementation": "dscr@2",
    "marker_class": "bank",
    "metric": "icr",
    "parent_evidence_ids": ("parent-b",),
    "parent_period_ids": ("period-b",),
    "period_results": (_period("missing"),),
    "plan_content_sha256": "plan-b",
    "published_read": "summary",
    "semantic_model_version": "smv-b",
    "profile_values": (("rate", "2"),),
    "sheet": True,
    "sign_convention": "outflow_positive",
    "sums_additions": 9,
}


def test_identity_matrix_names_every_calculation_evidence_field():
    """Каждое поле датакласса либо входит в хеш, либо остаётся атрибутом."""

    names = {item.name for item in fields(CalculationEvidence)}
    assert names == _IN_HASH | _OUTSIDE_HASH
    assert not (_IN_HASH & _OUTSIDE_HASH)


def test_hashed_field_changes_evidence_id_and_outside_field_does_not():
    """Смена входа хеша меняет evidence_id. Смена атрибута — нет."""

    base = seal(_evidence()).evidence_id
    assert base
    for name in sorted(_IN_HASH):
        changed = seal(_evidence(**{name: _ALTERNATE[name]})).evidence_id
        assert changed != base, name
    for name in sorted(_OUTSIDE_HASH):
        changed = seal(_evidence(**{name: _ALTERNATE[name]})).evidence_id
        assert changed == base, name


def test_identical_bodies_share_an_evidence_id():
    """Одинаковое каноническое тело делит evidence_id. Попытка не выпускает новый."""

    first = seal(_evidence())
    second = seal(_evidence())
    preset = seal(_evidence(evidence_id="attempt-2"))
    again = seal(first)
    assert first.evidence_id
    assert second.evidence_id == first.evidence_id
    assert preset.evidence_id == first.evidence_id
    assert again.evidence_id == first.evidence_id
    assert preset.evidence_id != "attempt-2"
