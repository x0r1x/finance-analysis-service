"""Трассировка DSCR следует варианту типа, а не базовой формуле."""

import pytest

from finance_analysis.application.financial_catalog import load_financial_catalog
from finance_analysis.application.model_types import load_model_types
from finance_analysis.application.service import FasService
from finance_analysis.domain.book import Actor, Head
from finance_analysis.domain.errors import NotFound
from finance_analysis.domain.graphs import (
    MISSING_NO_PRIMARY,
    check_metric_physical_trace,
)
from finance_analysis.domain.model_type import Effective, resolve_trace_variant


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


@pytest.mark.parametrize("source", ["inferred", "confirmed"])
async def test_metric_trace_view_omitted_variant_uses_book_covenant(source):
    service = FasService.__new__(FasService)
    service.financial_catalog = load_financial_catalog()
    service.model_types = load_model_types()
    head = Head(build_key="build", state_seq=1, derive_key="derive", versions={})

    async def head_ready(*_args, **_kwargs):
        return head

    async def rows_or_accepted(*_args, **_kwargs):
        return [
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
        ]

    async def dataset_rows(_job_id, _head, dataset):
        if dataset == "dim_row":
            return [
                {
                    "model_id": "job",
                    "build_key": "build",
                    "row_key": "ebitda",
                    "binding_key": "ebitda",
                }
            ]
        if dataset == "fact_observation":
            return []
        raise NotFound(dataset)

    async def resolve_model_type(_job_id, _head):
        return Effective(
            labels=("corporate",),
            primary="corporate",
            source=source,
            reason=None,
            seq=None,
            profile_version=None,
            score=1.0,
            scores={"corporate": 1.0},
            candidates=(),
        )

    class _Guard:
        async def read_all(self, _job_id):
            return []

    service._head_ready = head_ready
    service._rows_or_accepted = rows_or_accepted
    service._dataset_rows = dataset_rows
    service.resolve_model_type = resolve_model_type
    service.guard = _Guard()

    body = await service.metric_trace_view("job", "dscr", Actor(), wait_sec=0, variant=None)
    concepts = [step["concept"] for step in body["steps"]]
    assert body["variant"] == "corporate_covenant"
    assert "cash_taxes" in concepts
    assert "cfads" not in concepts
    assert "debt_service" not in concepts


async def test_profile_variant_overrides_omitted_query():
    service = FasService.__new__(FasService)
    service.financial_catalog = load_financial_catalog()
    service.model_types = load_model_types()
    head = Head(build_key="build", state_seq=1, derive_key="derive", versions={})

    async def head_ready(*_args, **_kwargs):
        return head

    async def rows_or_accepted(*_args, **_kwargs):
        return []

    async def dataset_rows(_job_id, _head, dataset):
        if dataset in {"dim_row", "fact_observation"}:
            return []
        raise NotFound(dataset)

    async def resolve_model_type(_job_id, _head):
        return Effective(
            labels=("corporate",),
            primary="corporate",
            source="inferred",
            reason=None,
            seq=None,
            profile_version=None,
            score=1.0,
            scores={"corporate": 1.0},
            candidates=(),
        )

    class _Guard:
        async def read_all(self, _job_id):
            return [{"seq": 1, "type": "profile.set", "target": "book", "value": "auchan@1"}]

    class _Glossary:
        async def profile_body(self, profile_id):
            assert profile_id == "auchan@1"
            return {"dscr_definition": {"variant": "ocf_covenant", "basis_ref": "Формулы!B53"}}

    service._head_ready = head_ready
    service._rows_or_accepted = rows_or_accepted
    service._dataset_rows = dataset_rows
    service.resolve_model_type = resolve_model_type
    service.guard = _Guard()
    service.glossary = _Glossary()

    body = await service.metric_trace_view("job", "dscr", Actor(), wait_sec=0, variant=None)
    concepts = [step["concept"] for step in body["steps"]]
    assert body["variant"] == "ocf_covenant"
    assert "operating_cash_flow" in concepts
    assert "cash_taxes" not in concepts

    explicit = await service.metric_trace_view("job", "dscr", Actor(), wait_sec=0, variant="corporate_covenant")
    explicit_concepts = [step["concept"] for step in explicit["steps"]]
    assert explicit["variant"] == "corporate_covenant"
    assert "cash_taxes" in explicit_concepts
