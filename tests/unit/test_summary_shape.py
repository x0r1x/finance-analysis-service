"""Форма GET /summary совпадает с SummaryDocument (summary-2)."""

from __future__ import annotations

import json

from tests.books import BUILDER_ROOT, job_id
from tests.fixtures.builder.build_summary import build_summary
from tests.fixtures.builder.summary_document import SummaryDocument

_IDENTITY = ("source_filename", "content_sha256", "status", "stage")


def _graph(**overrides) -> dict:
    body = {
        "schema_version": "1.7.0",
        "iterate": True,
        "nodes": 2,
        "edges": 2,
        "kinds": {"ref": 2},
        "unresolved": {"count": 0, "ids": []},
        "external": {"count": 0, "ids": []},
        "dangling": {"count": 0, "ids": []},
        "dynamic": {"count": 0, "ids": []},
        "truncated": {"count": 0, "ids": []},
        "dangling_classes": {},
        "cycles": [
            {
                "id": "c1",
                "class": "unexpected",
                "members": ["S!A1", "S!A2"],
                "breakers": ["S!A1"],
            }
        ],
        "circularity_hints": [
            {
                "sheet": "Construction",
                "row": 19,
                "label": "Uses of funds",
                "cell_ids": ["Construction!B19", "Construction!C19"],
            }
        ],
    }
    body.update(overrides)
    return body


def _context() -> dict:
    return {
        "schema_version": "1.14.0",
        "warnings": ["one warning"],
        "meta": {
            "source_filename": "from-context.xlsx",
            "content_sha256": "a" * 64,
            "status": "succeeded",
            "stage": "done",
        },
        "workbook": {
            "sheets": ["Construction"],
            "formula_count": 3,
            "missing_cached_values": 1,
            "unparsed_formulas": 0,
            "iterate": False,
            "defined_names": [
                {"name": "Tax", "formula": "Construction!$B$19", "hidden": False}
            ],
        },
    }


def test_build_summary_uses_the_summary_document_shape():
    meta = {
        "source_filename": "from-meta.xlsx",
        "content_sha256": "b" * 64,
        "status": "succeeded",
        "stage": "done",
    }
    body = build_summary(_context(), _graph(), meta)
    SummaryDocument.model_validate(body)
    assert body["schema_version"] == "summary-2"
    assert body["cycles"] == [{"id": "c1", "class": "unexpected", "members": 2}]
    assert body["circularity_hints"] == [
        {"sheet": "Construction", "row": 19, "label": "Uses of funds"}
    ]
    assert body["iterate"] is False
    assert [body[key] for key in _IDENTITY] == [meta[key] for key in _IDENTITY]
    assert body["warnings"] == ["one warning"]
    assert body["defined_name_count"] == 1


def test_missing_identity_fields_are_null():
    body = build_summary(_context(), _graph(), {"job_id": "abc"})
    SummaryDocument.model_validate(body)
    assert [body[key] for key in _IDENTITY] == [None, None, None, None]


def test_build_summary_falls_back_to_context_meta():
    context = _context()
    body = build_summary(context, _graph())
    SummaryDocument.model_validate(body)
    assert [body[key] for key in _IDENTITY] == [context["meta"][key] for key in _IDENTITY]


def test_golden_summaries_match_summary_document():
    for alias in ("packt", "rvi"):
        folder = BUILDER_ROOT / job_id(alias)
        context = json.loads((folder / "context.json").read_text(encoding="utf-8"))
        graph = json.loads((folder / "graph.json").read_text(encoding="utf-8"))
        meta_path = folder / "meta.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.is_file() else None
        stored = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
        SummaryDocument.model_validate(stored)
        assert stored == build_summary(context, graph, meta)
        assert stored["iterate"] == context["workbook"]["iterate"]
        identity = meta if meta is not None else context["meta"]
        assert [stored[key] for key in _IDENTITY] == [identity[key] for key in _IDENTITY]
        for hint in stored["circularity_hints"]:
            assert set(hint) == {"sheet", "row", "label"}
        for cycle in stored["cycles"]:
            assert set(cycle) == {"id", "class", "members"}
            assert isinstance(cycle["members"], int)
