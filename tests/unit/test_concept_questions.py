"""Вопросы по понятиям, а не по строкам (§5.10.5, Р6)."""

from __future__ import annotations

from finance_analysis.application.catalog import load_catalog
from finance_analysis.application.model_types import load_model_types
from finance_analysis.domain.book import question_digest
from finance_analysis.domain.model_type import (
    MetricInputs,
    ModelTypeCatalog,
    TypeSpec,
    concept_metrics,
    open_concepts,
)
from finance_analysis.domain.questions import concept_questions, question_id_problem


def _catalog():
    return load_model_types()


def _questions(**kwargs):
    base = {
        "job_id": "synthetic",
        "bindings": [],
        "rows": [],
        "events": [],
        "catalog": _catalog(),
        "labels": ("corporate",),
        "concepts": load_catalog().concepts,
        "limit": 5,
    }
    base.update(kwargs)
    return concept_questions(**base)


def test_project_finance_asks_only_unbound_required_inputs():
    catalog = _catalog()
    assert open_concepts(
        catalog, ("project_finance",), bound=frozenset(), absent=frozenset()
    ) == (
        "cfads",
        "debt_service",
    )
    assert (
        open_concepts(
            catalog,
            ("project_finance",),
            bound=frozenset({"cfads", "debt_service"}),
            absent=frozenset(),
        )
        == ()
    )


def test_synthetic_corporate_book_asks_three_icr_concepts():
    """Листы ОПиУ/Баланс/ДДС без строк: до — 0 вопросов по строкам, после — три понятия ICR."""

    got = _questions(rows=[{"sheet": "ОПиУ"}, {"sheet": "Баланс"}, {"sheet": "ДДС"}])
    assert [item["subject"] for item in got] == ["interest", "ebit", "ebitda"]
    assert [item["needed_by"] for item in got] == [["icr"], ["icr"], ["icr"]]
    assert all(
        item["candidates"] == []
        and item["expects"] == {"measure": "money", "shape": "series"}
        for item in got
    )
    assert got[0]["question_id"] == question_digest("concept", "interest", "synthetic")
    assert all(item["kind"] != "model_type" for item in got)


def test_required_variant_asks_for_its_inputs_and_a_tie_stays_on_the_base():
    base = MetricInputs(frozenset({"cfads", "debt_service"}), frozenset())
    covenant = MetricInputs(
        frozenset({"ebitda", "cash_taxes", "capex", "interest", "principal"}), frozenset()
    )
    catalog = ModelTypeCatalog(
        types={
            "corporate": TypeSpec("corporate", (), frozenset(), {"dscr": "required"}, {"dscr": "corporate_covenant"}),
            "project_finance": TypeSpec("project_finance", (), frozenset(), {"dscr": "required"}, {"dscr": "pf"}),
        },
        default_use="not_applicable",
        version="t",
        concepts=frozenset(),
        metric_inputs={"dscr": base},
        documents={},
        compatible=frozenset(),
        composed={},
        variant_inputs={"dscr": {"corporate_covenant": covenant, "pf": base}},
    )
    assert open_concepts(catalog, ("corporate",), bound=frozenset(), absent=frozenset()) == (
        "capex",
        "cash_taxes",
        "ebitda",
        "interest",
        "principal",
    )
    assert concept_metrics(catalog, ("corporate",), "cash_taxes", bound=frozenset()) == ("dscr",)
    assert open_concepts(
        catalog, ("corporate", "project_finance"), bound=frozenset(), absent=frozenset()
    ) == ("cfads", "debt_service")


def test_unresolved_union_asks_both_families_and_skips_optional():
    catalog = _catalog()
    assert open_concepts(
        catalog, ("project_finance", "corporate"), bound=frozenset(), absent=frozenset()
    ) == (
        "cfads",
        "debt_service",
        "interest",
        "ebit",
        "ebitda",
    )


def test_orphan_row_is_not_a_question_and_reject_drops_the_candidate():
    bindings = [
        {
            "binding_key": "interest-row",
            "row_key": "r1",
            "status": "ambiguous",
            "source": "inferred",
            "effective_concept": "interest",
            "is_primary": False,
            "confidence": 0.4,
            "evidence_json": '{"candidates": [{"concept": "interest", "p": 0.42, "reasons": ["label_match"]}]}',
            "label_path_text": "ОПиУ › Проценты",
        },
        {
            "binding_key": "orphan",
            "row_key": "r2",
            "status": "unknown",
            "source": "inferred",
            "effective_concept": None,
            "is_primary": False,
            "evidence_json": "{}",
            "label_path_text": "ОПиУ › Прочие",
        },
        {
            "binding_key": "hint",
            "row_key": "r3",
            "status": "unknown",
            "source": "inferred",
            "effective_concept": None,
            "is_primary": False,
            "evidence_json": '{"candidates": [{"concept": "ebitda", "p": 0.2, "reasons": ["glossary_synonym"], "structure_pass": true}, {"concept": "interest", "p": 0.9, "reasons": [], "structure_pass": false}]}',
            "label_path_text": "ОПиУ › EBITDA",
        },
    ]
    rows = [
        {
            "binding_key": "interest-row",
            "row_key": "r1",
            "sheet": "ОПиУ",
            "label": "Проценты",
        },
        {"binding_key": "hint", "row_key": "r3", "sheet": "ОПиУ", "label": "EBITDA"},
    ]
    got = _questions(bindings=bindings, rows=rows)
    by_subject = {item["subject"]: item for item in got}
    assert [item["binding_key"] for item in by_subject["interest"]["candidates"]] == [
        "interest-row"
    ]
    assert by_subject["interest"]["reason"] == "ambiguous"
    assert by_subject["interest"]["candidates"][0]["sheet"] == "ОПиУ"
    assert by_subject["interest"]["candidates"][0]["label"] == "Проценты"
    assert by_subject["ebitda"]["candidates"][0]["binding_key"] == "hint"
    assert all(
        cand["binding_key"] != "orphan" for item in got for cand in item["candidates"]
    )
    assert all("cell_ref" not in cand for item in got for cand in item["candidates"])
    closed = _questions(
        bindings=bindings,
        rows=rows,
        events=[
            {
                "seq": 1,
                "type": "concept.rejected",
                "target": "interest-row",
                "binding_key": "interest-row",
                "value": "interest",
            },
            {
                "seq": 2,
                "type": "concept.absent",
                "target": "book",
                "binding_key": "book",
                "value": "ebit",
            },
        ],
    )
    again = {item["subject"]: item for item in closed}
    assert "ebit" not in again
    assert again["interest"]["candidates"] == []


def test_absent_inferred_primary_does_not_close_one_of():
    def primary(concept: str, source: str) -> dict:
        return {
            "binding_key": concept,
            "effective_concept": concept,
            "is_primary": True,
            "status": "bound",
            "source": source,
        }

    def absent(concept: str) -> list[dict]:
        return [{"seq": 1, "type": "concept.absent", "target": "book", "binding_key": "book", "value": concept}]

    inferred = _questions(bindings=[primary("ebitda", "inferred")], events=absent("ebitda"))
    assert [item["subject"] for item in inferred] == ["interest", "ebit"]
    assert [item["subject"] for item in _questions(events=absent("ebitda"))] == ["interest", "ebit"]
    other = _questions(bindings=[primary("ebit", "inferred")], events=absent("ebit"))
    assert [item["subject"] for item in other] == ["interest", "ebitda"]
    confirmed = _questions(bindings=[primary("ebitda", "confirmed")], events=absent("ebitda"))
    assert [item["subject"] for item in confirmed] == ["interest"]


def test_lexical_ambiguous_rows_outrank_weak_model_hits():
    import json

    def lexical(key: str, concept: str) -> dict:
        return {
            "binding_key": key,
            "row_key": key,
            "status": "ambiguous",
            "source": "inferred",
            "effective_concept": concept,
            "is_primary": False,
            "confidence": None,
            "evidence_json": json.dumps({"match_strength": "exact", "label": {"id": concept}}),
        }

    def hinted(key: str, concept: str, score: float) -> dict:
        return {
            "binding_key": key,
            "row_key": key,
            "status": "unknown",
            "source": "inferred",
            "effective_concept": None,
            "is_primary": False,
            "evidence_json": json.dumps(
                {"candidates": [{"concept": concept, "p": score, "reasons": ["label_match"], "structure_pass": True}]}
            ),
        }

    ebitda = [lexical("e1", "ebitda"), lexical("e2", "ebitda")]
    crowded = _questions(bindings=ebitda + [hinted(f"m{i}", "ebitda", 0.2) for i in range(5)], limit=5)
    asked = next(item for item in crowded if item["subject"] == "ebitda")
    assert asked["reason"] == "ambiguous"
    assert [item["binding_key"] for item in asked["candidates"][:2]] == ["e1", "e2"]
    assert asked["candidates"][0]["score"] == 0.0
    alone = next(item for item in _questions(bindings=ebitda) if item["subject"] == "ebitda")
    assert alone["reason"] == "ambiguous"
    assert [item["binding_key"] for item in alone["candidates"]] == ["e1", "e2"]
    interest = [lexical("i1", "interest"), lexical("i2", "interest")]
    mixed = _questions(bindings=interest + [hinted(f"n{i}", "interest", 0.15) for i in range(5)], limit=5)
    service = next(item for item in mixed if item["subject"] == "interest")
    assert service["reason"] == "ambiguous"
    assert [item["binding_key"] for item in service["candidates"][:2]] == ["i1", "i2"]


def test_bound_numerator_closes_the_one_of_group():
    catalog = _catalog()
    assert open_concepts(
        catalog, ("corporate",), bound=frozenset({"ebitda"}), absent=frozenset()
    ) == ("interest",)


def test_question_id_must_match_the_concept():
    job = "job"
    digest = question_digest("concept", "capex", job)
    assert question_id_problem("concept.set", "capex", job, None) is None
    assert question_id_problem("concept.set", "capex", job, digest) is None
    assert (
        question_id_problem("concept.set", "capex", job, "0" * 40)
        == "question_id не совпадает с вопросом"
    )
    assert (
        question_id_problem("concept.rejected", "ebitda", job, digest)
        == "question_id не совпадает с вопросом"
    )
    assert (
        question_id_problem(
            "model_type.set",
            {"labels": ["corporate"], "primary": "corporate"},
            job,
            question_digest("model_type", "book", job),
        )
        is None
    )
    assert (
        question_id_problem("sign.set", "outflow", job, "zz")
        == "question_id должен быть sha1"
    )
