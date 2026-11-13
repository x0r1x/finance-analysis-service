"""Отпечаток классификации Packt и RVI: diff показывает, какая строка сменила понятие."""

from __future__ import annotations

import difflib
import json
from collections import Counter
from pathlib import Path

from finance_analysis.adapters.builder.acl import parse_context, parse_graph
from finance_analysis.application.catalog import load_catalog
from finance_analysis.application.project import derive_rows, project
from tests.books import BUILDER_ROOT, job_id

_FINGERPRINT = Path(__file__).resolve().parent.parent / "fixtures" / "classification" / "packt-rvi.txt"
_BOOKS = ("packt", "rvi")
_STATUSES = ("bound", "ambiguous", "unknown", "not_applicable")


def _classification() -> str:
    glossary = load_catalog()
    lines = []
    for alias in _BOOKS:
        folder = BUILDER_ROOT / job_id(alias)
        context = json.loads((folder / "context.json").read_text())
        graph = json.loads((folder / "graph.json").read_text())
        snapshot = parse_graph(graph, parse_context(context))
        projected, _warnings = project(snapshot, model_id=alias, build="fingerprint")
        derived = derive_rows(
            projected,
            state_seq=1,
            derive="fingerprint",
            versions={"glossary": "fingerprint"},
            glossary=glossary,
            facts=projected["fact_observation"],
        )
        facts = {
            row["binding_key"]
            for row in projected["dim_row"]
            if row.get("kind") == "fact" and row.get("binding_key")
        }
        rows = [item for item in derived["bindings"] if item.get("binding_key") in facts]
        counts = Counter(item.get("status") or "unknown" for item in rows)
        for status in _STATUSES:
            lines.append(f"{alias}\t{status}\t{counts[status]}")
        rows.sort(key=lambda item: (item.get("status") or "", item.get("concept") or "", item["binding_key"]))
        for item in rows:
            concept = item.get("concept") or "-"
            primary = "1" if item.get("is_primary") else "0"
            lines.append(f"{alias}\t{item.get('status')}\t{concept}\t{primary}\t{item['binding_key']}")
    return "\n".join(lines) + "\n"


def test_book_classification_matches_the_committed_fingerprint():
    actual = _classification()
    expected = _FINGERPRINT.read_text()
    if actual == expected:
        return
    diff = "".join(
        difflib.unified_diff(
            expected.splitlines(True),
            actual.splitlines(True),
            fromfile="tests/fixtures/classification/packt-rvi.txt",
            tofile="current",
        )
    )
    raise AssertionError(diff)
