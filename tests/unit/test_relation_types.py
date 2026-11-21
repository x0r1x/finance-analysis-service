"""Реестр типов отношений понятий и проверка каталога при загрузке."""

from dataclasses import replace
from types import MappingProxyType

import pytest

from finance_analysis.application.catalog import load_catalog
from finance_analysis.domain import relations
from finance_analysis.domain.glossary import GlossaryInvalid, build_package
from finance_analysis.domain.relations import (
    ACTIVE_RELATION_TYPES,
    RELATION_TYPES,
    RESERVED_RELATION_TYPES,
    RelationType,
    permits,
)

_DICTS = {
    "flows": {"inflow": ["приток"]},
    "markers": {"actual": ["факт"], "plan": ["план"], "estimate": ["e"]},
}


def _measure(**extra) -> dict:
    body = {"kind": "measure", "unit": "money"}
    body.update(extra)
    return body


def _gloss(name: str, **extra) -> dict:
    base = {"concept": name, "pref": {"ru": name, "en": name}}
    base.update(extra)
    return base


def _concepts(bodies: dict[str, dict], glossaries: dict | None = None):
    return build_package(
        {"taxonomy": "core-1", "concepts": bodies},
        glossaries or {name: _gloss(name) for name in bodies},
        _DICTS,
    )


def _labels(caught: pytest.ExceptionInfo[GlossaryInvalid]) -> list[str]:
    return caught.value.labels


def _replace_type(monkeypatch: pytest.MonkeyPatch, name: str, **fields: object) -> None:
    """Подмена одного типа на время теста. Запись в реестр закрыта."""

    catalog = MappingProxyType(
        {**relations.RELATION_TYPES, name: replace(relations.RELATION_TYPES[name], **fields)}
    )
    monkeypatch.setattr(relations, "RELATION_TYPES", catalog)


def test_registry_declares_every_type_and_keeps_substitution_closed():
    names = {
        "composed_of",
        "calculated_from",
        "derived_from",
        "broader_than",
        "narrower_than",
        "related_to",
        "equivalent_to",
        "supersedes",
        "replaced_by",
        "contradicts",
        "requires",
    }
    assert set(RELATION_TYPES) == names
    # Вид конца не хранится: узел и так понятие пакета, отдельная константа concept сверяла бы себя с собой.
    assert "source_kind" not in RelationType.__dataclass_fields__
    assert "target_kind" not in RelationType.__dataclass_fields__
    for spec in RELATION_TYPES.values():
        assert spec.direction in {"directed", "symmetric"}
        assert spec.allows_substitution is False
        assert spec.participates_in_aggregation is False
        if spec.inverse is not None:
            assert RELATION_TYPES[spec.inverse].inverse == spec.name
        if spec.symmetric:
            assert spec.inverse == spec.name
            assert spec.direction == "symmetric"
        if spec.inverse_required:
            assert spec.inverse is not None
            assert RELATION_TYPES[spec.inverse].active
    composed = RELATION_TYPES["composed_of"]
    assert composed.active and composed.participates_in_reconciliation
    assert composed.same_dimension and composed.source_roles == frozenset({"measure"})
    assert composed.target_roles == frozenset({"measure"})
    assert not composed.symmetric and not composed.transitive and not composed.cycles_allowed
    assert composed.inverse is None
    calculated = RELATION_TYPES["calculated_from"]
    derived = RELATION_TYPES["derived_from"]
    assert calculated.active and derived.active
    assert not calculated.participates_in_reconciliation
    assert not derived.participates_in_reconciliation
    assert not calculated.same_dimension
    broader = RELATION_TYPES["broader_than"]
    narrower = RELATION_TYPES["narrower_than"]
    assert broader.inverse == "narrower_than" and narrower.inverse == "broader_than"
    assert broader.transitive and narrower.transitive
    assert not broader.inverse_required and not narrower.inverse_required
    related = RELATION_TYPES["related_to"]
    assert related.symmetric and related.cycles_allowed and not related.transitive
    assert not related.inverse_required and not related.participates_in_reconciliation
    for name in ("equivalent_to", "supersedes", "replaced_by"):
        assert RELATION_TYPES[name].active is False
    assert RELATION_TYPES["supersedes"].inverse == "replaced_by"
    assert RELATION_TYPES["replaced_by"].inverse == "supersedes"
    assert RELATION_TYPES["contradicts"].symmetric and RELATION_TYPES["contradicts"].cycles_allowed
    assert not RELATION_TYPES["requires"].symmetric and not RELATION_TYPES["requires"].cycles_allowed
    assert permits("related_to", "substitution") is False
    assert permits("composed_of", "substitution") is False
    assert permits("composed_of", "aggregation") is False
    assert permits("composed_of", "reconciliation") is True
    assert permits("equivalent_to", "substitution") is False


def test_relation_registry_rejects_writes():
    with pytest.raises(TypeError):
        RELATION_TYPES["composed_of"] = RELATION_TYPES["composed_of"]
    assert isinstance(ACTIVE_RELATION_TYPES, frozenset)
    assert isinstance(RESERVED_RELATION_TYPES, frozenset)


def test_catalog_relations_stay_and_do_not_derive_inverses():
    package = load_catalog()
    debt = package.concepts["debt_service"]
    lease = package.concepts["lease_payments"]
    assert debt.composed_of == ("interest", "principal")
    assert lease.composed_of == ("lease_principal", "lease_interest")
    assert package.concepts["cfads"].related_to == ("dscr",)
    assert package.concepts["dscr"].related_to == ()
    assert package.concepts["interest"].relation_targets("equivalent_to") == ()
    assert package.concepts["interest"].relation_targets("narrower_than") == ()
    assert "interest_paid" not in debt.composed_of
    assert debt.targets_for("reconciliation") == ("interest", "principal")
    assert debt.targets_for("substitution") == ()
    assert debt.targets_for("aggregation") == ()
    tariff = package.concepts["energy_tariff"]
    forecast = package.concepts["forecast_energy_tariff"]
    assert tariff.related_to == ("forecast_energy_tariff",)
    assert forecast.related_to == ("energy_tariff",)
    assert tariff.targets_for("substitution") == ()
    assert forecast.targets_for("substitution") == ()
    assert tariff.targets_for("reconciliation") == ()


def test_reconciliation_view_follows_the_registry_not_the_stored_edge(monkeypatch):
    package = _concepts(
        {
            "debt_service": _measure(relations={"composed_of": ["interest"]}),
            "interest": _measure(),
            "cfads": _measure(relations={"related_to": ["dscr"]}),
            "dscr": _measure(),
        }
    )
    debt = package.concepts["debt_service"]
    assert debt.composed_of == ("interest",)
    assert debt.targets_for("reconciliation") == ("interest",)
    assert package.concepts["cfads"].targets_for("reconciliation") == ()
    _replace_type(monkeypatch, "composed_of", participates_in_reconciliation=False)
    assert debt.composed_of == ("interest",)
    assert debt.targets_for("reconciliation") == ()
    assert debt.targets_for("substitution") == ()


def test_reserved_types_are_rejected_in_russian():
    for name in ("equivalent_to", "replaced_by", "supersedes"):
        with pytest.raises(GlossaryInvalid) as caught:
            _concepts(
                {
                    "interest": _measure(relations={name: ["interest_paid"]}),
                    "interest_paid": _measure(),
                }
            )
        labels = _labels(caught)
        assert f"reserved:{name}" in labels
        assert any("зарезервирован" in item and name in item for item in labels)


def test_unknown_relation_type_is_rejected_in_russian():
    with pytest.raises(GlossaryInvalid) as caught:
        _concepts({"a": _measure(relations={"see_also": ["b"]}), "b": _measure()})
    labels = _labels(caught)
    assert "unknown:see_also" in labels
    assert any("неизвестный тип" in item and "see_also" in item for item in labels)


def test_composed_of_rejects_bad_role_dimension_and_missing_target():
    with pytest.raises(GlossaryInvalid) as role:
        _concepts(
            {
                "rate": {
                    "semantic_role": "parameter",
                    "dimension": "ratio",
                    "temporal_nature": "rate",
                    "relations": {"composed_of": ["part"]},
                },
                "part": _measure(),
            }
        )
    assert "role:composed_of" in _labels(role)
    assert any("источником" in item for item in _labels(role))
    with pytest.raises(GlossaryInvalid) as dimension:
        _concepts(
            {
                "whole": _measure(relations={"composed_of": ["part"]}),
                "part": {"kind": "ratio", "unit": "ratio"},
            }
        )
    assert "dimension:composed_of" in _labels(dimension)
    assert any("размерность" in item for item in _labels(dimension))
    with pytest.raises(GlossaryInvalid) as missing:
        _concepts({"a": _measure(relations={"related_to": ["missing"]})})
    assert "missing:missing" in _labels(missing)
    assert any("отсутствующее" in item for item in _labels(missing))


def test_new_active_types_load_without_granting_calculation():
    package = _concepts(
        {
            "ratio": {"kind": "ratio", "unit": "ratio", "relations": {"calculated_from": ["money"]}},
            "money": _measure(relations={"derived_from": ["ratio"]}),
            "left": _measure(relations={"contradicts": ["right"], "requires": ["money"]}),
            "right": _measure(relations={"contradicts": ["left"]}),
        }
    )
    ratio = package.concepts["ratio"]
    assert ratio.relation_targets("calculated_from") == ("money",)
    assert ratio.targets_for("substitution") == ()
    assert ratio.targets_for("aggregation") == ()
    assert ratio.targets_for("reconciliation") == ()
    assert package.concepts["money"].relation_targets("derived_from") == ("ratio",)
    assert package.concepts["left"].relation_targets("requires") == ("money",)


def test_cycles_follow_the_type_and_mutual_related_edges_stay():
    with pytest.raises(GlossaryInvalid) as calculated:
        _concepts(
            {
                "a": _measure(relations={"calculated_from": ["b"]}),
                "b": _measure(relations={"calculated_from": ["a"]}),
            }
        )
    assert "cycle:calculated_from" in _labels(calculated)
    assert any("цикл" in item for item in _labels(calculated))
    with pytest.raises(GlossaryInvalid) as requires:
        _concepts(
            {
                "a": _measure(relations={"requires": ["b"]}),
                "b": _measure(relations={"requires": ["a"]}),
            }
        )
    assert "cycle:requires" in _labels(requires)
    mutual = _concepts(
        {
            "a": _measure(relations={"related_to": ["b"], "contradicts": ["b"]}),
            "b": _measure(relations={"related_to": ["a"], "contradicts": ["a"]}),
        }
    )
    assert mutual.concepts["a"].related_to == ("b",)
    assert mutual.concepts["b"].related_to == ("a",)


def test_inverse_direction_conflict_and_optional_reverse_edge():
    with pytest.raises(GlossaryInvalid) as conflict:
        _concepts(
            {
                "parent": _measure(relations={"broader_than": ["child"], "narrower_than": ["child"]}),
                "child": _measure(),
            }
        )
    assert "direction:broader_than" in _labels(conflict)
    assert any("одну сторону" in item for item in _labels(conflict))
    agreed = _concepts(
        {
            "parent": _measure(relations={"broader_than": ["child"]}),
            "child": _measure(relations={"narrower_than": ["parent"]}),
        }
    )
    assert agreed.concepts["parent"].broader_than == ("child",)
    assert agreed.concepts["child"].relation_targets("narrower_than") == ("parent",)


def test_missing_required_inverse_is_reported(monkeypatch):
    _replace_type(monkeypatch, "broader_than", inverse_required=True)
    with pytest.raises(GlossaryInvalid) as missing:
        _concepts(
            {
                "parent": _measure(relations={"broader_than": ["child"]}),
                "child": _measure(),
            }
        )
    assert "inverse:broader_than" in _labels(missing)
    assert any("обратн" in item for item in _labels(missing))
    both = _concepts(
        {
            "parent": _measure(relations={"broader_than": ["child"]}),
            "child": _measure(relations={"narrower_than": ["parent"]}),
        }
    )
    assert both.concepts["child"].relation_targets("narrower_than") == ("parent",)


def test_narrower_than_joins_the_hierarchy_graph():
    agreed = _concepts(
        {
            "parent": _measure(),
            "child": _measure(relations={"narrower_than": ["parent"]}),
        },
        {
            "parent": _gloss("parent"),
            "child": _gloss("child", broader="parent"),
        },
    )
    assert agreed.concepts["child"].broader == "parent"
    with pytest.raises(GlossaryInvalid) as conflict:
        _concepts(
            {
                "parent": _measure(),
                "other": _measure(),
                "child": _measure(relations={"narrower_than": ["other"]}),
            },
            {
                "parent": _gloss("parent"),
                "other": _gloss("other"),
                "child": _gloss("child", broader="parent"),
            },
        )
    assert "child" in _labels(conflict)
    with pytest.raises(GlossaryInvalid) as cycle:
        _concepts(
            {
                "a": _measure(relations={"narrower_than": ["b"]}),
                "b": _measure(relations={"narrower_than": ["a"]}),
            }
        )
    assert "cycle:broader" in _labels(cycle)


def test_active_relation_names_fit_the_semantic_edge_id():
    import json
    import re
    from pathlib import Path

    from finance_analysis.domain.graphs import semantic_relation_edge_id

    schema = json.loads(
        Path("src/finance_analysis/domain/contracts/meta_layer_graphs.json").read_text(encoding="utf-8")
    )
    pattern = schema["$defs"]["semRelEdgeId"]["pattern"]
    for name, spec in RELATION_TYPES.items():
        edge = semantic_relation_edge_id(name, "debt_service", "interest")
        matched = re.fullmatch(pattern, edge) is not None
        assert matched is spec.active


def test_semantic_targets_read_both_sides_without_writing_edges():
    package = load_catalog()
    dscr = package.concepts["dscr"]
    cfads = package.concepts["cfads"]
    assert dscr.relation_targets("related_to") == ()
    assert cfads.relation_targets("related_to") == ("dscr",)
    assert package.semantic_targets("dscr", "related_to") == ("cfads",)
    assert package.semantic_targets("cfads", "related_to") == ("dscr",)
    assert dscr.relation_targets("related_to") == ()
    assert dscr.targets_for("substitution") == ()
    assert dscr.targets_for("aggregation") == ()
    assert dscr.targets_for("reconciliation") == ()
    assert package.semantic_targets("energy_tariff", "related_to") == ("forecast_energy_tariff",)
    assert package.semantic_targets("forecast_energy_tariff", "related_to") == ("energy_tariff",)
    assert package.concepts["interest"].targets_for("reconciliation") == ()
    assert package.semantic_targets("interest", "composed_of") == ()

    contradicts = _concepts(
        {
            "left": _measure(relations={"contradicts": ["right"]}),
            "right": _measure(),
        }
    )
    assert contradicts.concepts["right"].relation_targets("contradicts") == ()
    assert contradicts.semantic_targets("right", "contradicts") == ("left",)
    assert contradicts.semantic_targets("left", "contradicts") == ("right",)
    assert contradicts.concepts["right"].targets_for("substitution") == ()
    assert contradicts.concepts["left"].targets_for("reconciliation") == ()
    assert contradicts.concepts["left"].relation_targets("contradicts") == ("right",)

    hierarchy = _concepts(
        {
            "parent": _measure(relations={"broader_than": ["child"]}),
            "child": _measure(),
        }
    )
    child = hierarchy.concepts["child"]
    parent = hierarchy.concepts["parent"]
    assert child.relation_targets("narrower_than") == ()
    assert parent.relation_targets("narrower_than") == ()
    assert hierarchy.semantic_targets("child", "narrower_than") == ("parent",)
    assert hierarchy.semantic_targets("parent", "broader_than") == ("child",)
    assert child.relations == ()

    both_ways = _concepts(
        {
            "child": _measure(relations={"narrower_than": ["parent"]}),
            "parent": _measure(),
        }
    )
    assert both_ways.concepts["parent"].relation_targets("broader_than") == ()
    assert both_ways.semantic_targets("parent", "broader_than") == ("child",)
    assert both_ways.semantic_targets("child", "narrower_than") == ("parent",)

    incoming = _concepts(
        {
            "b": _measure(relations={"related_to": ["c"]}),
            "a": _measure(relations={"related_to": ["c"]}),
            "c": _measure(relations={"related_to": ["a"]}),
        }
    )
    assert incoming.semantic_targets("c", "related_to") == ("a", "b")


def _scan(package, concept_id: str, kind: str) -> tuple[str, ...]:
    """Прежний обход: прямые цели, затем входящие источники по id."""

    concept = package.concepts.get(concept_id)
    spec = RELATION_TYPES.get(kind)
    if concept is None or spec is None:
        return ()
    found: list[str] = []
    seen: set[str] = set()

    def add(name: str) -> None:
        if name == concept_id or name in seen:
            return
        seen.add(name)
        found.append(name)

    for target in concept.relation_targets(kind):
        add(target)
    incoming: list[str] = []
    if spec.symmetric:
        incoming.append(kind)
    inverse = spec.inverse
    if inverse and inverse != kind:
        incoming.append(inverse)
    if not incoming:
        return tuple(found)
    for other_id in sorted(package.concepts):
        if other_id == concept_id:
            continue
        other = package.concepts[other_id]
        for edge_kind in incoming:
            if concept_id in other.relation_targets(edge_kind):
                add(other_id)
                break
    return tuple(found)


def test_incoming_index_matches_the_previous_scan():
    contradicts = _concepts(
        {
            "left": _measure(relations={"contradicts": ["right"]}),
            "right": _measure(),
        }
    )
    hierarchy = _concepts(
        {
            "parent": _measure(relations={"broader_than": ["child"]}),
            "child": _measure(),
        }
    )
    both_ways = _concepts(
        {
            "child": _measure(relations={"narrower_than": ["parent"]}),
            "parent": _measure(),
        }
    )
    incoming = _concepts(
        {
            "b": _measure(relations={"related_to": ["c"]}),
            "a": _measure(relations={"related_to": ["c"]}),
            "c": _measure(relations={"related_to": ["a"]}),
        }
    )
    agreed = _concepts(
        {
            "parent": _measure(relations={"broader_than": ["child"]}),
            "child": _measure(),
        },
        {
            "parent": _gloss("parent"),
            "child": _gloss("child", broader="parent"),
        },
    )
    packages = [load_catalog(), contradicts, hierarchy, both_ways, incoming, agreed]
    for package in packages:
        assert isinstance(package._incoming, MappingProxyType)
        for concept_id in package.concepts:
            for kind in RELATION_TYPES:
                assert package.semantic_targets(concept_id, kind) == _scan(package, concept_id, kind)
    assert hierarchy.semantic_targets("child", "narrower_than") == ("parent",)
    assert hierarchy.semantic_targets("parent", "broader_than") == ("child",)
    assert hierarchy.concepts["child"].relation_targets("narrower_than") == ()
    assert hierarchy.concepts["child"].relations == ()
    assert contradicts.semantic_targets("right", "contradicts") == ("left",)
    assert incoming.semantic_targets("c", "related_to") == ("a", "b")
    assert agreed.concepts["child"].broader == "parent"
    assert agreed.semantic_targets("child", "narrower_than") == ("parent",)
    assert agreed.concepts["parent"].relation_targets("broader_than") == ("child",)
    with pytest.raises(TypeError):
        load_catalog()._incoming[("cfads", "related_to")] = ()


def test_formula_relation_types_grant_no_calculation():
    for name in ("calculated_from", "derived_from", "equivalent_to"):
        assert permits(name, "substitution") is False
        assert permits(name, "aggregation") is False
        assert permits(name, "reconciliation") is False
    package = _concepts(
        {
            "ratio": {"kind": "ratio", "unit": "ratio", "relations": {"calculated_from": ["money"]}},
            "money": _measure(relations={"derived_from": ["ratio"]}),
        }
    )
    ratio = package.concepts["ratio"]
    money = package.concepts["money"]
    assert ratio.targets_for("substitution") == ()
    assert ratio.targets_for("aggregation") == ()
    assert ratio.targets_for("reconciliation") == ()
    assert money.targets_for("reconciliation") == ()
    assert package.semantic_targets("money", "calculated_from") == ()
    assert package.semantic_targets("ratio", "derived_from") == ()
    assert ratio.relation_targets("calculated_from") == ("money",)
