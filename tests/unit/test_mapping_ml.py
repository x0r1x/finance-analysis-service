"""Стадии 4, 7b, 9 и конвейер моделей (§5.5, §5.10.1): статус решают правила, модели дают признаки."""

import json

import pytest

from finance_analysis.adapters.builder.acl import parse_context, parse_graph
from finance_analysis.adapters.vector.numpy_index import NumpyIndex
from finance_analysis.application.catalog import load_catalog
from finance_analysis.application.examples import ExampleStore
from finance_analysis.application.mapping_pipeline import MappingPipeline, expand
from finance_analysis.application.project import derive_rows, prepare_rows, project
from finance_analysis.domain.candidates import Candidate, RowEvidence
from finance_analysis.domain.deadline import Deadline
from finance_analysis.domain.mapping import assign_rows, decide
from finance_analysis.settings import Settings
from tests.books import BUILDER_ROOT, job_id
from tests.models import FakeBudget, FakeClm, FakeEmbed, FakeRerank

CATALOG = load_catalog()


def _row(key: str, label: str, **extra) -> dict:
    return {"kind": "fact", "binding_key": key, "row_key": key, "label": label, "label_path_text": label, "sign": None, **extra}


def _strong(concept: str) -> Candidate:
    return Candidate(concept, recall_cos=0.92, rerank_rank=1, rerank_gap=0.6)


def test_strong_candidate_binds_inferred_with_confidence():
    found = RowEvidence(candidates=(_strong("cfads"), Candidate("ebitda", recall_cos=0.6, rerank_rank=2, rerank_gap=-0.6)))
    item = decide(_row("a", "Free cash for lenders", unit="money"), found, CATALOG, None)
    assert item.status == "bound" and item.source == "inferred" and item.is_primary
    assert item.concept == "cfads" and item.confidence > 0.6
    assert item.evidence["candidates"][0]["concept"] == "cfads"


def test_close_candidates_are_ambiguous():
    found = RowEvidence(candidates=(_strong("interest"), _strong("principal")))
    item = decide(_row("a", "Debt payment"), found, CATALOG, None)
    assert item.status == "ambiguous" and not item.is_primary


@pytest.mark.parametrize(
    "found, reason",
    [
        (RowEvidence(candidates=(Candidate("cfads", recall_cos=0.4),), nearest_concept_cos=0.4), "threshold"),
        (RowEvidence(candidates=(_strong("cfads"),), clm_choice="none", clm_none_prob=0.7), "clm_none"),
    ],
)
def test_nil_decision(found, reason):
    item = decide(_row("a", "Something else"), found, CATALOG, None)
    assert item.status == "unknown" and item.concept is None
    assert item.evidence["nil"] == reason


def test_structure_filter_drops_percent_rows():
    item = decide(_row("a", "CFADS margin %"), RowEvidence(candidates=(_strong("cfads"),)), CATALOG, None)
    assert item.status == "unknown" and item.evidence["nil"] == "structure_filtered"


def test_lexical_label_wins_over_model_candidate_of_same_concept():
    rows = [_row("lex", "CFADS"), _row("ml", "Cash for lenders")]
    evidence = {"ml": RowEvidence(candidates=(_strong("cfads"),))}
    assigned = assign_rows(rows, [], CATALOG, evidence=evidence)
    assert assigned["lex"].status == "bound" and assigned["lex"].is_primary
    assert assigned["ml"].status == "ambiguous" and not assigned["ml"].is_primary


def test_human_decision_is_not_touched_by_evidence():
    rows = [_row("a", "Cash for lenders")]
    events = [{"seq": 1, "type": "concept.set", "target": "a", "binding_key": "a", "value": "ebitda"}]
    assigned = assign_rows(rows, events, CATALOG, evidence={"a": RowEvidence(candidates=(_strong("cfads"),))})
    assert assigned["a"].concept == "ebitda" and assigned["a"].source == "confirmed"


def test_expand_adds_abbreviation():
    assert "cash flow available for debt service" in expand("CF › CFADS", CATALOG)


def _settings(**extra) -> Settings:
    return Settings(FAS_REDIS_URL="redis://unused", **extra)


async def test_pipeline_degrades_without_failing():
    rows = prepare_rows({"dim_row": [_row("a", "Free cash for lenders")]}, [], CATALOG, None)
    pipeline = MappingPipeline(
        type("M", (), {"embed": FakeEmbed(fail=True), "rerank": FakeRerank(fail=True), "clm": None, "llm": None})(),
        settings=_settings(),
    )
    result = await pipeline.score("j", "r", rows, CATALOG, glossary_version="g", deadline=Deadline.after_ms(5000))
    assert {item["stage"] for item in result.degraded} == {"embed", "rerank"}
    assert result.evidence["a"].degraded


async def test_pipeline_ranks_and_spends_clm_budget(tmp_path):
    from finance_analysis.adapters.storage.parquet_io import PyarrowParquet
    from finance_analysis.adapters.storage.store import LocalStore

    store = LocalStore(tmp_path)
    examples = ExampleStore(store, PyarrowParquet(), NumpyIndex(), model="fake-embed", refresh_sec=0)
    from tests.models import text_vector

    await examples.append(
        [
            {
                "job_id": "other",
                "binding_key": "x",
                "seq": 1,
                "kind": "confirmed",
                "concept": "interest",
                "path_text": "Finance costs paid",
                "label_norm": "finance costs paid",
                "candidates_json": "{}",
                "embedding": text_vector("Debt › Finance costs paid (money)"),
            }
        ]
    )
    budget = FakeBudget()
    models = type("M", (), {"embed": FakeEmbed(), "rerank": FakeRerank(), "clm": FakeClm("interest"), "llm": None})()
    pipeline = MappingPipeline(models, examples, budget, settings=_settings(CLM_MAX_CALLS_PER_BOOK=1))
    rows = prepare_rows(
        {"dim_row": [_row("a", "Finance costs paid", sheet="Debt", unit="money"), _row("b", "Interest and principal", sheet="Debt", unit="money")]},
        [],
        CATALOG,
        None,
    )
    result = await pipeline.score("job", "run", rows, CATALOG, glossary_version="g", deadline=Deadline.after_ms(5000))
    first = result.evidence["a"]
    assert first.nearest_example_cos is not None and first.nearest_example_cos > 0.9
    assert any("cross_book_example" in c.reasons for c in first.candidates if c.concept == "interest")
    assert set(result.embeddings) == {"a", "b"}
    assert budget.used.get("fas:clm:job", 0) <= 2
    assert models.clm.calls <= 1


def test_partition_holds_with_model_evidence_on_golden_books():
    for alias in ("packt", "rvi"):
        job = job_id(alias)
        folder = BUILDER_ROOT / job
        snapshot = parse_graph(json.loads((folder / "graph.json").read_text()), parse_context(json.loads((folder / "context.json").read_text())))
        tables, _warnings = project(snapshot, model_id=job, build="b")
        prepared = prepare_rows(tables, [], CATALOG, tables["fact_observation"])
        evidence = {
            row["binding_key"]: RowEvidence(candidates=(_strong("capex"), Candidate("ebitda", recall_cos=0.7, rerank_rank=2)))
            for row in prepared
            if row["kind"] == "fact"
        }
        derived = derive_rows(
            tables,
            state_seq=0,
            derive="d",
            versions={"glossary": "none"},
            glossary=CATALOG,
            facts=tables["fact_observation"],
            evidence=evidence,
            prepared=prepared,
        )
        facts = [row for row in tables["dim_row"] if row["kind"] == "fact"]
        assert len(derived["bindings"]) == len(facts)
        owners: dict[str, int] = {}
        for row in derived["bindings"]:
            if row["is_primary"] and row["concept"]:
                owners[row["concept"]] = owners.get(row["concept"], 0) + 1
            if row["source"] == "inferred" and row["status"] in {"bound", "bound_with_warning"}:
                assert json.loads(row["evidence_json"])
        assert all(count == 1 for count in owners.values())


@pytest.mark.parametrize(
    "row",
    [
        _row("a", "Interest", unit="rate"),
        _row("a", "Interest", unit="money", unit_decision="rate"),
        _row("a", "DSCR", unit="money"),
    ],
)
def test_exact_label_passes_the_same_unit_check(row):
    assigned = assign_rows([row], [], CATALOG)
    assert assigned["a"].status == "unknown" and assigned["a"].concept is None


def test_model_binding_has_a_label_id():
    item = decide(_row("a", "Free cash for lenders", unit="money"), RowEvidence(candidates=(_strong("cfads"),)), CATALOG, None)
    assert item.matched_label == "model:cfads"
    assert item.evidence["label"]["kind"] == "model"


async def test_ragged_embeddings_degrade_instead_of_failing():
    class Ragged(FakeEmbed):
        async def embed(self, texts, *, deadline):
            return [[1.0, 0.0, 0.0][: 2 + index % 2] for index, _text in enumerate(texts)]

    rows = prepare_rows({"dim_row": [_row("a", "Free cash"), _row("b", "Other cash")]}, [], CATALOG, None)
    pipeline = MappingPipeline(type("M", (), {"embed": Ragged(), "rerank": None, "clm": None, "llm": None})(), settings=_settings())
    result = await pipeline.score("j", "r", rows, CATALOG, glossary_version="g", deadline=Deadline.after_ms(5000))
    assert {"stage": "embed", "reason": "schema"} in result.degraded
    assert result.embeddings == {}


def test_numeric_identity_marks_rows_verified():
    from decimal import Decimal

    from finance_analysis.domain.mapping import verify_numeric

    rows = [_row("c", "CFADS"), _row("d", "Debt service"), _row("r", "DSCR"), _row("i", "Interest"), _row("p", "Principal")]
    assigned = assign_rows(rows, [], CATALOG)
    periods = [("t", "2027"), ("t", "2028"), ("t", "2029")]
    values = {
        "c": dict(zip(periods, map(Decimal, ["130", "120", "110"]), strict=True)),
        "d": dict(zip(periods, map(Decimal, ["-100", "-100", "-100"]), strict=True)),
        "r": dict(zip(periods, map(Decimal, ["1.3", "1.2", "1.1"]), strict=True)),
        "i": dict(zip(periods, map(Decimal, ["-60", "-60", "-60"]), strict=True)),
        "p": dict(zip(periods, map(Decimal, ["-40", "-40", "-40"]), strict=True)),
    }
    checked = verify_numeric(assigned, rows, values)
    assert checked["c"].source == "verified" and checked["d"].evidence["verified"] == ["ds_composition", "dscr_identity"]
    assert checked["r"].source == "inferred"
    values["c"][("t", "2028")] = Decimal(500)
    values["c"][("t", "2029")] = Decimal(500)
    assert verify_numeric(assigned, rows, values)["c"].source == "inferred"
