"""Прогон точности типа модели. К3 — только через FAS_LOCAL_BOOK_K3, в снимок не входит."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
import yaml

from finance_analysis.domain.book import Actor
from finance_analysis.domain.metrics import _primaries
from finance_analysis.domain.model_type import infer
from finance_analysis.domain.model_type_eval import (
    Expectation,
    build_report,
    render_markdown,
)
from tests.books import job_id
from tests.k3_expect import assert_confident_primary
from tests.workbook_labels import resolved_workbook

pytestmark = pytest.mark.eval

_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "model_type_eval" / "cases.yaml"
_REPORT = Path(__file__).resolve().parents[2] / "eval" / "model_type" / "report.json"
_REPORT_MD = Path(__file__).resolve().parents[2] / "eval" / "model_type" / "report.md"


def _expectation(raw: dict) -> Expectation:
    if raw["kind"] == "question":
        return Expectation("question", reason=raw["reason"])
    return Expectation("type", raw["primary"], tuple(raw["labels"]))


async def _inputs(service, case: dict) -> tuple[frozenset[str], frozenset[str]]:
    if case["source"] == "bound":
        return frozenset(case.get("bound") or ()), frozenset(case.get("sheets") or ())
    if case["source"] == "workbook":
        return resolved_workbook(case["book"])
    job = job_id(case["alias"])
    await service.perform_load(job, actor=Actor(), fence=1)
    head = (await service._read_head(job))[0]
    bindings = await service._dataset_rows(job, head, "bindings")
    rows = await service._dataset_rows(job, head, "dim_row")
    verdict = await service.resolve_model_type(job, head)
    guessed = infer(
        service.model_types,
        bound=frozenset(_primaries(bindings)),
        sheets=frozenset(str(row["sheet"]) for row in rows if row.get("sheet")),
        accept=service.settings.model_type_accept,
        gap=service.settings.model_type_gap,
    )
    assert verdict.source == "inferred" and verdict.primary == guessed.primary, case["id"]
    return frozenset(_primaries(bindings)), frozenset(str(row["sheet"]) for row in rows if row.get("sheet"))


async def test_model_type_accuracy_matches_the_snapshot(local_service, settings):
    spec = yaml.safe_load(_ROOT.read_text(encoding="utf-8"))
    accept = settings.model_type_accept
    gap = settings.model_type_gap
    assert (spec["accept"], spec["gap"]) == (accept, gap) == (0.6, 0.15)
    cases = []
    for case in spec["cases"]:
        bound, sheets = await _inputs(local_service, case)
        got = infer(local_service.model_types, bound=bound, sheets=sheets, accept=accept, gap=gap)
        cases.append((case["id"], _expectation(case["expect"]), got))
    report = build_report(cases, accept=accept, gap=gap, type_ids=tuple(sorted(local_service.model_types.ids)))
    payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    markdown = render_markdown(report)
    assert "k3" not in {row["id"] for row in report["cases"]}
    if os.environ.get("FAS_WRITE_MODEL_TYPE_EVAL") == "1":
        _REPORT.parent.mkdir(parents=True, exist_ok=True)
        _REPORT.write_text(payload, encoding="utf-8")
        _REPORT_MD.write_text(markdown, encoding="utf-8")
        return
    assert _REPORT.read_text(encoding="utf-8") == payload
    assert _REPORT_MD.read_text(encoding="utf-8") == markdown


def _k3_spec() -> dict | None:
    path = os.environ.get("FAS_LOCAL_BOOK_K3")
    if not path:
        return None
    book = Path(path)
    if not book.is_file():
        return None
    spec_path = book.with_suffix(".local.yaml")
    if not spec_path.is_file():
        return None
    spec = yaml.safe_load(spec_path.read_text(encoding="utf-8")) or {}
    primary = spec.get("primary")
    return {
        "bound": spec.get("bound") or [],
        "sheets": spec.get("sheets") or [],
        "primary": primary if isinstance(primary, str) else None,
    }


def test_k3_expects_corporate_and_stays_out_of_the_snapshot():
    spec = _k3_spec()
    if spec is None:
        pytest.skip("FAS_LOCAL_BOOK_K3 не задан")
    if spec["primary"] is None:
        pytest.skip("в .local.yaml нет primary")
    from finance_analysis.application.model_types import load_model_types

    got = infer(
        load_model_types(),
        bound=frozenset(spec["bound"]),
        sheets=frozenset(spec["sheets"]),
        accept=0.6,
        gap=0.15,
    )
    assert_confident_primary(got, spec["primary"])
    snapshot = json.loads(_REPORT.read_text(encoding="utf-8"))
    assert all(row["id"] != "k3" for row in snapshot["cases"])
