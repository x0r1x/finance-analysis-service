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


def _input(values, precedents, bindings, rows=None, currency=None, units=None):
    if rows is None:
        extra = {"currency": currency} if currency else {}
        rows = [{"binding_key": key, "row_key": key, "label": key, **extra} for key in values]
    return LabelingInput(
        rows=rows,
        values={key: dict(zip(P, map(Decimal, series), strict=True)) for key, series in values.items()},
        precedents=precedents,
        bindings={item["binding_key"]: item for item in bindings},
        concepts=dict(CATALOG.concepts),
        identities=load_identities(),
        order={period: index for index, period in enumerate(P)},
        units=units or {},
    )


def _money_units():
    from finance_analysis.domain.dimensions import UnitSpec

    return {
        "USD": UnitSpec("money", "USD", 1),
        "RUB": UnitSpec("money", "RUB", 1),
        "thousand_rub": UnitSpec("money", "RUB", 1000),
    }


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
    rows = [
        {"binding_key": key, "row_key": key, "label": key, "unit": "RUB", "currency": "RUB"}
        for key in values
    ]
    human = _input(
        values,
        precedents,
        [_binding("int", "interest", "confirmed"), _binding("prn", "principal", "confirmed")],
        rows=rows,
        units=_money_units(),
    )
    assert [(v.binding_key, v.concept) for v in identity(human)] == [("total", "debt_service")]
    assert [(v.binding_key, v.concept) for v in rollforward(human)] == [("bal", "debt_outstanding")]
    cash = _input(
        {"cash": [1, 2, 3, 4, 5], "prn": [9, 9, 9, 9, 9]},
        {"cash": {"cash", "prn"}},
        [_binding("prn", "principal", "confirmed")],
    )
    assert rollforward(cash) == []


def test_identity_follows_composed_of_when_the_identity_file_is_longer():
    from dataclasses import replace

    from finance_analysis.domain.glossary import ConceptRelation

    concepts = dict(CATALOG.concepts)
    concepts["debt_service"] = replace(
        concepts["debt_service"],
        relations=(ConceptRelation("composed_of", "interest"),),
    )
    values = {
        "int": [10, 10, 10, 10, 10],
        "prn": [5, 5, 5, 5, 5],
        "only": [10, 10, 10, 10, 10],
        "both": [15, 15, 15, 15, 15],
    }
    data = LabelingInput(
        rows=[{"binding_key": key, "row_key": key, "label": key, "unit": "RUB", "currency": "RUB"} for key in values],
        values={key: dict(zip(P, map(Decimal, series), strict=True)) for key, series in values.items()},
        precedents={"only": {"int"}, "both": {"int", "prn"}},
        bindings={
            item["binding_key"]: item
            for item in (
                _binding("int", "interest", "confirmed"),
                _binding("prn", "principal", "confirmed"),
            )
        },
        concepts=concepts,
        identities={"debt_service": ["interest", "principal"]},
        order={period: index for index, period in enumerate(P)},
        units=_money_units(),
    )
    assert [(vote.binding_key, vote.concept) for vote in identity(data)] == [("only", "debt_service")]


def test_identity_abstains_unless_one_known_currency():
    values = {"int": [10, 10, 10, 10, 10], "prn": [5, 5, 5, 5, 5], "total": [15, 15, 15, 15, 15]}
    precedents = {"total": {"int", "prn"}}
    bindings = [_binding("int", "interest", "confirmed"), _binding("prn", "principal", "confirmed")]
    rows = [
        {"binding_key": key, "row_key": key, "label": key, "unit": "RUB", "currency": "RUB"}
        for key in values
    ]
    same = _input(values, precedents, bindings, rows=rows, units=_money_units())
    assert [(vote.binding_key, vote.polarity) for vote in identity(same)] == [("total", "+")]
    mixed_rows = [
        {"binding_key": "int", "row_key": "int", "label": "int", "currency": "RUB"},
        {"binding_key": "prn", "row_key": "prn", "label": "prn", "currency": "USD"},
        {"binding_key": "total", "row_key": "total", "label": "total", "currency": "RUB"},
    ]
    mixed = _input(values, precedents, bindings, rows=mixed_rows)
    assert identity(mixed) == []
    unknown = _input(values, precedents, bindings)
    assert identity(unknown) == []


def test_identity_reads_usd_from_the_unit_when_the_row_currency_is_empty():
    values = {"int": [10, 10, 10, 10, 10], "prn": [5, 5, 5, 5, 5], "total": [15, 15, 15, 15, 15]}
    precedents = {"total": {"int", "prn"}}
    bindings = [_binding("int", "interest", "confirmed"), _binding("prn", "principal", "confirmed")]
    rows = [
        {"binding_key": key, "row_key": key, "label": key, "unit": "USD"}
        for key in values
    ]
    data = _input(values, precedents, bindings, rows=rows, units=_money_units())
    assert [(vote.binding_key, vote.polarity) for vote in identity(data)] == [("total", "+")]


def test_identity_abstains_when_rub_and_usd_units_differ():
    values = {"int": [10, 10, 10, 10, 10], "prn": [5, 5, 5, 5, 5], "total": [15, 15, 15, 15, 15]}
    precedents = {"total": {"int", "prn"}}
    bindings = [_binding("int", "interest", "confirmed"), _binding("prn", "principal", "confirmed")]
    rows = [
        {"binding_key": "int", "row_key": "int", "label": "int", "unit": "RUB"},
        {"binding_key": "prn", "row_key": "prn", "label": "prn", "unit": "USD"},
        {"binding_key": "total", "row_key": "total", "label": "total", "unit": "RUB"},
    ]
    data = _input(values, precedents, bindings, rows=rows, units=_money_units())
    assert identity(data) == []


def test_identity_abstains_when_thousand_rub_and_rub_share_a_currency():
    precedents = {"total": {"int", "prn"}}
    bindings = [_binding("int", "interest", "confirmed"), _binding("prn", "principal", "confirmed")]
    rows = [
        {"binding_key": "int", "row_key": "int", "label": "int", "unit": "RUB", "currency": "RUB"},
        {"binding_key": "prn", "row_key": "prn", "label": "prn", "unit": "RUB", "currency": "RUB"},
        {"binding_key": "total", "row_key": "total", "label": "total", "unit": "thousand_rub", "currency": "RUB"},
    ]
    same_numbers = {"int": [10, 10, 10, 10, 10], "prn": [5, 5, 5, 5, 5], "total": [15, 15, 15, 15, 15]}
    false_match = _input(same_numbers, precedents, bindings, rows=rows, units=_money_units())
    assert identity(false_match) == []
    scaled = {
        "int": [10000, 10000, 10000, 10000, 10000],
        "prn": [5000, 5000, 5000, 5000, 5000],
        "total": [15, 15, 15, 15, 15],
    }
    true_base = _input(scaled, precedents, bindings, rows=rows, units=_money_units())
    assert identity(true_base) == []


def test_identity_abstains_when_explicit_currency_disagrees_with_the_unit():
    values = {"int": [10, 10, 10, 10, 10], "prn": [5, 5, 5, 5, 5], "total": [15, 15, 15, 15, 15]}
    precedents = {"total": {"int", "prn"}}
    bindings = [_binding("int", "interest", "confirmed"), _binding("prn", "principal", "confirmed")]
    rows = [
        {"binding_key": key, "row_key": key, "label": key, "unit": "USD", "currency": "EUR"}
        for key in values
    ]
    data = _input(values, precedents, bindings, rows=rows, units=_money_units())
    assert identity(data) == []


def test_unknown_unit_does_not_become_a_catalog_currency():
    values = {"int": [10, 10, 10, 10, 10], "prn": [5, 5, 5, 5, 5], "total": [15, 15, 15, 15, 15]}
    precedents = {"total": {"int", "prn"}}
    bindings = [_binding("int", "interest", "confirmed"), _binding("prn", "principal", "confirmed")]
    blank = [
        {"binding_key": key, "row_key": key, "label": key, "unit": "FOO"}
        for key in values
    ]
    assert identity(_input(values, precedents, bindings, rows=blank, units=_money_units())) == []
    named = [
        {"binding_key": key, "row_key": key, "label": key, "unit": "FOO", "currency": "RUB"}
        for key in values
    ]
    voted = _input(values, precedents, bindings, rows=named, units=_money_units())
    assert identity(voted) == []


def _identity_book(unit_of, *, currency_of=None, units=None, extra_rows=()):
    values = {"int": [10, 10, 10, 10, 10], "prn": [5, 5, 5, 5, 5], "total": [15, 15, 15, 15, 15]}
    rows = []
    for key in values:
        row = {"binding_key": key, "row_key": key, "label": key, "unit": unit_of[key]}
        named = (currency_of or {}).get(key)
        if named:
            row["currency"] = named
        rows.append(row)
    rows.extend(extra_rows)
    return _input(
        values,
        {"total": {"int", "prn"}},
        [_binding("int", "interest", "confirmed"), _binding("prn", "principal", "confirmed")],
        rows=rows,
        units=_money_units() if units is None else units,
    )


def test_identity_abstains_when_dimension_differs_at_the_same_currency_and_scale():
    from finance_analysis.domain.dimensions import UnitSpec

    units = _money_units()
    units["RUB/MWh"] = UnitSpec("currency_per_energy", "RUB", 1)
    data = _identity_book(
        {"int": "RUB", "prn": "RUB/MWh", "total": "RUB"},
        currency_of={"int": "RUB", "prn": "RUB", "total": "RUB"},
        units=units,
    )
    assert identity(data) == []


def test_identity_abstains_when_a_component_unit_is_unknown():
    data = _identity_book(
        {"int": "FOO", "prn": "RUB", "total": "RUB"},
        currency_of={"int": "RUB", "prn": "RUB", "total": "RUB"},
    )
    assert identity(data) == []


def test_identity_abstains_when_the_total_unit_is_unknown():
    data = _identity_book(
        {"int": "RUB", "prn": "RUB", "total": "FOO"},
        currency_of={"int": "RUB", "prn": "RUB", "total": "RUB"},
    )
    assert identity(data) == []


def test_identity_abstains_when_row_key_is_duplicated():
    data = _identity_book(
        {"int": "RUB", "prn": "RUB", "total": "RUB"},
        currency_of={"int": "RUB", "prn": "RUB", "total": "RUB"},
        extra_rows=[{"binding_key": "int-copy", "row_key": "int", "label": "int", "unit": "RUB", "currency": "RUB"}],
    )
    assert identity(data) == []


def test_identity_votes_when_dimension_currency_and_scale_agree():
    data = _identity_book(
        {"int": "RUB", "prn": "RUB", "total": "RUB"},
        currency_of={"int": "RUB", "prn": "RUB", "total": "RUB"},
    )
    assert [(vote.binding_key, vote.polarity) for vote in identity(data)] == [("total", "+")]


def test_identity_abstains_when_currencies_differ():
    data = _identity_book(
        {"int": "RUB", "prn": "USD", "total": "RUB"},
        currency_of={"int": "RUB", "prn": "USD", "total": "RUB"},
    )
    assert identity(data) == []


def test_identity_abstains_when_scales_differ():
    data = _identity_book(
        {"int": "RUB", "prn": "RUB", "total": "thousand_rub"},
        currency_of={"int": "RUB", "prn": "RUB", "total": "RUB"},
    )
    assert identity(data) == []


def test_identity_votes_when_plain_units_share_dimension_and_scale():
    from finance_analysis.domain.dimensions import UnitSpec

    data = _identity_book(
        {"int": "MWh", "prn": "MWh", "total": "MWh"},
        units={"MWh": UnitSpec("energy", None, 1)},
    )
    assert [(vote.binding_key, vote.polarity) for vote in identity(data)] == [("total", "+")]


def test_identity_abstains_when_a_plain_unit_names_a_currency():
    from finance_analysis.domain.dimensions import UnitSpec

    data = _identity_book(
        {"int": "MWh", "prn": "MWh", "total": "MWh"},
        currency_of={"int": "RUB", "prn": "RUB", "total": "RUB"},
        units={"MWh": UnitSpec("energy", None, 1)},
    )
    assert identity(data) == []


def test_identity_abstains_for_a_price_unit_without_a_rule():
    from finance_analysis.domain.dimensions import UnitSpec

    data = _identity_book(
        {"int": "RUB/MWh", "prn": "RUB/MWh", "total": "RUB/MWh"},
        currency_of={"int": "RUB", "prn": "RUB", "total": "RUB"},
        units={"RUB/MWh": UnitSpec("currency_per_energy", "RUB", 1)},
    )
    assert identity(data) == []


def test_labeling_input_passes_the_unit_catalog():
    from finance_analysis.application.learning import labeling_input

    data = labeling_input([], [], [], [], CATALOG, {})
    assert data.units["USD"].currency == "USD"
    assert data.units["USD"].scale == 1
    assert data.units["thousand_rub"].currency == "RUB"
    assert data.units["thousand_rub"].scale == 1000
    assert data.units["MWh"].currency is None
    assert data.units["RUB/MWh"].currency == "RUB"


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
    assert same_profile[0]["books"] == 1 and same_profile[0]["decision"] == "auto"
    assert same_profile[0]["scope"].startswith("profile:")
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


async def test_unmapped_percent_and_two_concept_rows_are_proposed(tmp_path):
    learning, glossary = _learning(tmp_path)
    labels = ("Interest, %", "Проценты, %", "EBIT (CFADS)")
    for index, label in enumerate(labels):
        row = {
            "binding_key": f"k{index}",
            "row_key": f"k{index}",
            "label": label,
            "label_path_text": f"Sheet › {label}",
            "unit": "money",
        }
        await learning.after_derive(
            "job",
            prepared=[row],
            bindings=[{**_binding(row["binding_key"], None, status="unknown"), "importance": "critical"}],
            facts=[],
            links=[],
            embeddings={},
            nearest={},
            package=CATALOG,
            glossary_version="g",
            profile=None,
            identities={},
        )
    await learning.cluster_unmapped(CATALOG)
    texts = {item["text"] for item in (await glossary.proposals(status="open"))["proposals"]}
    assert set(labels) <= texts


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
    await glossary.bootstrap()
    for job, actor in (("a", "u1"), ("b", "u2"), ("c", "u3")):
        rows = {"k": {"binding_key": "k", "row_key": "k", "label": "Lender cash", "label_path_text": "Lender cash"}}
        record = {"seq": 1, "type": "concept.confirmed", "binding_key": "k", "value": "cfads", "actor": {"user_id": actor}}
        await learning.record_decisions(job, [record], rows=rows, bindings={}, events=[record], profile=None, glossary_version="g", package=CATALOG)
    before = (await glossary.bootstrap())["seq"]
    result = await learning.mine(CATALOG, load_git_document())
    assert result["mode"] == "proposals" and result["candidates"] == 1
    assert (await glossary.bootstrap())["seq"] == before
    origins = {item["origin"] for item in (await glossary.proposals())["proposals"]}
    assert "auto" in origins
