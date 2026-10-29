"""Фильтр mapping и resolve глоссария без моделей."""

from __future__ import annotations

import pytest

from finance_analysis.adapters.storage.store import LocalStore
from finance_analysis.application.glossary_store import GlossaryStore
from finance_analysis.application.service import filter_bindings
from finance_analysis.domain.errors import InvalidArgument, NotFound

_ROWS = [
    {"status": "unknown", "concept": None, "effective_concept": None, "importance": "peripheral", "label_path_text": "Other"},
    {"status": "bound", "concept": "cfads", "effective_concept": "cfads", "importance": "normal", "label_path_text": "CFADS"},
    {"status": "bound", "concept": None, "effective_concept": "debt_service", "importance": "material", "label_path_text": "Debt"},
    {"status": "ambiguous", "concept": "revenue", "effective_concept": "revenue", "importance": "peripheral", "label_path_text": "Выручка"},
]


def test_mapping_filters_keep_counts_source_rows():
    assert filter_bindings(_ROWS, None) == _ROWS
    assert filter_bindings(_ROWS, {}) == _ROWS
    assert filter_bindings(_ROWS, {"status": "unknown"}) == [_ROWS[0]]
    assert filter_bindings(_ROWS, {"concept": "debt_service"}) == [_ROWS[2]]
    assert filter_bindings(_ROWS, {"importance": "material"}) == [_ROWS[2]]
    assert filter_bindings(_ROWS, {"q": "cfads"}) == [_ROWS[1]]
    with pytest.raises(InvalidArgument) as caught:
        filter_bindings(_ROWS, {"nope": "1"})
    assert caught.value.extra["supported"] == ["concept", "importance", "q", "status"]


@pytest.mark.asyncio
async def test_resolve_is_lexical_without_models(tmp_path):
    gloss = GlossaryStore(LocalStore(tmp_path))
    with pytest.raises(NotFound):
        await gloss.resolve({"label": "CFADS", "version": "no-such-release"})
    assert await gloss.peek() is None
    hit = await gloss.resolve({"text": "CFADS"})
    assert hit["results"][0]["match"]["concept"] == "cfads"
    assert "state" in hit
    leaf = await gloss.resolve({"path_text": "Лист › CFADS"})
    assert leaf["results"][0]["match"]["concept"] == "cfads"
    rejected = await gloss.resolve({"label": "CFADS", "unit": "%"})
    assert rejected["results"][0]["match"] is None
    assert rejected["results"][0]["candidates"] == [
        {"concept": "cfads", "kind": "alt", "text": "CFADS", "structure_pass": False}
    ]
    missed = await gloss.resolve({"label": "нет такой метки"})
    assert missed["results"][0]["match"] is None
    assert missed["results"][0]["stages"] == ["lexical"]
    assert missed["results"][0]["candidates"] == []
    with pytest.raises(InvalidArgument):
        await gloss.resolve({"label": "CFADS", "path_text": "CF › CFADS"})


@pytest.mark.asyncio
async def test_resolve_ranks_against_the_active_release(tmp_path):
    gloss = GlossaryStore(LocalStore(tmp_path))
    seen = []

    async def rank(row, package, version):
        seen.append(version)

    await gloss.resolve({"label": "нет такой метки"}, rank=rank)
    assert seen == [(await gloss.peek())["active"]]
