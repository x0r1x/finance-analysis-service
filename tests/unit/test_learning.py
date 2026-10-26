"""Сигналы, LF, glossary_mine в режиме предложений, unmapped/ и кластеры (§5.10.4, §5.11)."""

from decimal import Decimal

from finance_analysis.adapters.ml.cluster import HdbscanCluster
from finance_analysis.adapters.storage.parquet_io import PyarrowParquet
from finance_analysis.adapters.storage.store import LocalStore
from finance_analysis.adapters.vector.numpy_index import NumpyIndex
from finance_analysis.application.catalog import (
    load_catalog,
    load_git_document,
    load_identities,
)
from finance_analysis.application.examples import ExampleStore
from finance_analysis.application.glossary_store import GlossaryStore
from finance_analysis.application.learning import Learning
from finance_analysis.application.ports import Models
from finance_analysis.domain.signals import LabelingInput, lexical_relation, mine
from finance_analysis.plugins.labeling import (
    identity,
    ratio_numerator,
    rollforward,
    sum_component,
    unit_sign,
)
from finance_analysis.settings import Settings
from tests.models import FakeClm, FakeEmbed, FakeLlm, text_vector

CATALOG = load_catalog()
P = [("t", str(year)) for year in range(2026, 2031)]


def _binding(key, concept, source="inferred", status="bound"):
    return {"binding_key": key, "row_key": key, "effective_concept": concept, "is_primary": True, "status": status, "source": source}


def _input(values, precedents, bindings, rows=None):
    rows = rows or [{"binding_key": key, "row_key": key, "label": key} for key in values]
    return LabelingInput(
        rows=rows,
        values={key: dict(zip(P, map(Decimal, series), strict=True)) for key, series in values.items()},
        precedents=precedents,
        bindings={item["binding_key"]: item for item in bindings},
        concepts=dict(CATALOG.concepts),
        identities=load_identities(),
        order={period: index for index, period in enumerate(P)},
    )


def test_ratio_numerator_and_sum_component():
    data = _input(
        {"cash": [130, 120, 110, 100, 90], "ds": [100, 100, 100, 100, 100], "dscr": ["1.3", "1.2", "1.1", "1.0", "0.9"], "fee": [1, 1, 1, 1, 1]},
        {"dscr": {"cash", "ds"}, "ds": {"fee"}},
        [_binding("dscr", "dscr"), _binding("ds", "debt_service")],
    )
    assert [(v.binding_key, v.concept, v.kind) for v in ratio_numerator(data)] == [("cash", "cfads", "lf.ratio_numerator")]
    assert [(v.binding_key, v.kind) for v in sum_component(data)] == [("fee", "lf.sum_component")]


def test_identity_needs_human_components_and_rollforward():
    values = {"int": [10, 10, 10, 10, 10], "prn": [5, 5, 5, 5, 5], "total": [15, 15, 15, 15, 15], "bal": [100, 95, 90, 85, 80]}
    precedents = {"total": {"int", "prn"}, "bal": {"bal", "prn"}}
    machine = _input(values, precedents, [_binding("int", "interest"), _binding("prn", "principal")])
    assert identity(machine) == []
    human = _input(values, precedents, [_binding("int", "interest", "confirmed"), _binding("prn", "principal", "confirmed")])
    assert [(v.binding_key, v.concept) for v in identity(human)] == [("total", "debt_service")]
    assert [(v.binding_key, v.concept) for v in rollforward(human)] == [("bal", "debt_outstanding")]
    cash = _input(
        {"cash": [1, 2, 3, 4, 5], "prn": [9, 9, 9, 9, 9]},
        {"cash": {"cash", "prn"}},
        [_binding("prn", "principal", "confirmed")],
    )
    assert rollforward(cash) == []


def test_unit_sign_votes_against():
    rows = [{"binding_key": "r", "row_key": "r", "label": "x", "unit": "%"}]
    votes = unit_sign(_input({"r": [1, 1, 1, 1, 1]}, {}, [_binding("r", "cfads")], rows=rows))
    assert [(v.concept, v.polarity) for v in votes] == [("cfads", "-")]


def test_lexical_relation_and_mine_decisions():
    assert lexical_relation("Debt servce", ["Debt service"]) == "hidden"
    assert lexical_relation("CADS", ["cash available debt service"]) == "hidden"
    assert lexical_relation("Lender cash", ["Debt service"]) == "alt"

    def s(job, actor, polarity="+", kind="human.confirmed", concept="cfads", profile=None):
        return {"job_id": job, "binding_key": "k", "label_norm": "cash for lenders", "label_text": "Cash for lenders", "lang": "en",
                "concept": concept, "polarity": polarity, "kind": kind, "actor": actor, "profile_id": profile}

    strong = [s("a", "u1"), s("b", "u2"), s("c", "u1")]
    rows = mine(strong, owned={}, negatives={}, known_labels={"cfads": ["CFADS"]})
    assert rows[0]["decision"] == "auto" and rows[0]["books"] == 3 and rows[0]["confirmations"] == 2
    conflict = mine([*strong, s("d", "u3", "-", "human.rejected")], owned={}, negatives={}, known_labels={})
    assert conflict[0]["decision"] == "review" and "negative_signal" in conflict[0]["conflicts"]
    same_profile = mine([s("a", "u1", profile="p"), s("b", "u2", profile="p"), s("c", "u3", profile="p")], owned={}, negatives={}, known_labels={})
    assert same_profile[0]["books"] == 1 and same_profile[0]["decision"] == "review"
    model_only = mine([s("a", None, kind="model.inferred")], owned={}, negatives={}, known_labels={})
    assert model_only == []


def _learning(tmp_path, *, models=None):
    store = LocalStore(tmp_path)
    parquet = PyarrowParquet()
    settings = Settings(FAS_REDIS_URL="redis://unused", PROPOSE_MIN_BOOKS=2)
    glossary = GlossaryStore(store)
    examples = ExampleStore(store, parquet, NumpyIndex(), model="fake-embed", refresh_sec=0)
    return Learning(store, parquet, glossary, examples, models or Models(), HdbscanCluster(), settings), glossary


async def test_decisions_feed_signals_examples_and_label_proposal(tmp_path):
    learning, glossary = _learning(tmp_path, models=Models(embed=FakeEmbed()))
    rows = {"k": {"binding_key": "k", "row_key": "k", "label": "Cash for lenders", "label_path_text": "CF › Cash for lenders"}}
    bindings = {"k": {**_binding("k", "ebitda"), "evidence_json": '{"candidates": [{"concept": "cfads", "recall_cos": 0.8}]}'}}
    record = {"seq": 3, "type": "concept.set", "binding_key": "k", "value": "cfads", "actor": {"user_id": "u1"}}
    done = await learning.record_decisions(
        "job", [record], rows=rows, bindings=bindings, events=[record], profile=None, glossary_version="g", package=CATALOG
    )
    assert done == {"signals": 2, "examples": 1}
    kinds = sorted((row["kind"], row["polarity"], row["concept"]) for row in await learning.signals.rows())
    assert kinds == [("human.corrected", "+", "cfads"), ("human.rejected", "-", "ebitda")]
    active = await learning.examples.active()
    assert active[0]["concept"] == "cfads" and active[0]["embedding_f32"]
    hits = await learning.examples.search([text_vector("CF › Cash for lenders")], 1)
    assert hits[0][0][1]["concept"] == "cfads"
    proposals = (await glossary.proposals(status="open"))["proposals"]
    assert proposals[0]["origin"] == "decision" and proposals[0]["text"] == "Cash for lenders"


async def test_cluster_unmapped_proposes_once_per_cluster(tmp_path):
    learning, glossary = _learning(tmp_path, models=Models(embed=FakeEmbed(), clm=FakeClm("synonym_of:debt_service"), llm=FakeLlm()))
    rows = []
    for job in ("a", "b", "c"):
        rows.append({"binding_key": f"{job}1", "row_key": f"{job}1", "label": "Agency fee", "label_path_text": "Debt › Agency fee", "unit": "money"})
    for job, row in zip(("a", "b", "c"), rows, strict=True):
        await learning.after_derive(
            job,
            prepared=[row],
            bindings=[{**_binding(row["binding_key"], None, status="unknown"), "importance": "critical"}],
            facts=[],
            links=[],
            embeddings={row["binding_key"]: text_vector(row["label_path_text"])},
            nearest={row["binding_key"]: "debt_service"},
            package=CATALOG,
            glossary_version="g",
            profile=None,
            identities={},
        )
    first = await learning.cluster_unmapped(CATALOG)
    second = await learning.cluster_unmapped(CATALOG)
    assert first["proposals"] >= 1 and second["proposals"] == first["proposals"]
    proposals = (await glossary.proposals(status="open", order_by="impact"))["proposals"]
    clustered = [item for item in proposals if item["origin"] == "cluster"]
    assert len(clustered) == 1
    assert clustered[0]["draft"]["pref"]["en"] == "Agency fee"
    assert clustered[0]["books"] == 3
    assert clustered[0]["type"] == "synonym_of" and clustered[0]["concept"] == "debt_service"
    compacted = await learning.compact()
    assert compacted["unmapped"]["merged"] == 3
    assert len(await learning.unmapped.rows()) == 3


async def test_mine_writes_candidates_and_only_proposes(tmp_path):
    learning, glossary = _learning(tmp_path)
    await glossary.ensure()
    for job, actor in (("a", "u1"), ("b", "u2"), ("c", "u3")):
        rows = {"k": {"binding_key": "k", "row_key": "k", "label": "Lender cash", "label_path_text": "Lender cash"}}
        record = {"seq": 1, "type": "concept.confirmed", "binding_key": "k", "value": "cfads", "actor": {"user_id": actor}}
        await learning.record_decisions(job, [record], rows=rows, bindings={}, events=[record], profile=None, glossary_version="g", package=CATALOG)
    before = (await glossary.ensure())["seq"]
    result = await learning.mine(CATALOG, load_git_document())
    assert result["mode"] == "proposals" and result["candidates"] == 1
    assert (await glossary.ensure())["seq"] == before
    origins = {item["origin"] for item in (await glossary.proposals())["proposals"]}
    assert "auto" in origins
