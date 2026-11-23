"""Предел следа, хвост в объекте и указатель. Ожидание замера лежит здесь, не в golden."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from finance_analysis.adapters.storage.store import LocalStore
from finance_analysis.adapters.storage.trace_pointer import DuckDBTracePointer
from finance_analysis.adapters.storage.trace_retention import put_object_governance
from finance_analysis.application.trace_tail import (
    delete_analysis_traces,
    log_trace_metrics,
    publish_trace,
    read_trace,
)
from finance_analysis.domain.calculation_evidence import (
    CalculationEvidence,
    EvidenceBook,
    FactUse,
    PeriodResult,
    TransformationStep,
)
from finance_analysis.domain.metrics import _sums
from finance_analysis.domain.trace_limit import (
    TraceLimitError,
    guard_traces,
    limit_trace,
    retention_policy,
    view_from_evidence,
)
from finance_analysis.settings import Settings
from tests.books import BUILDER_ROOT, job_id

NOW = datetime(2020, 1, 2, tzinfo=UTC)
LOG = "fas.trace"


def _labeled_facts(alias: str, concept: str) -> list[dict]:
    labels = json.loads((Path(__file__).resolve().parents[2] / "eval" / "labels" / f"{alias}.json").read_text())
    paths = {path for path, name in labels["by_path"].items() if name == concept}
    data = json.loads((BUILDER_ROOT / job_id(alias) / "context.json").read_text())
    found = []
    for block in data["blocks"]:
        for row in block["rows"]:
            path = " › ".join([*(row.get("label_path") or []), row.get("label") or ""])
            if path not in paths:
                continue
            for series in row.get("series") or []:
                values = series.get("values") or []
                norms = series.get("normalized_values") or []
                for index, value in enumerate(values):
                    if value is None or value == "":
                        continue
                    found.append(
                        {
                            "row_key": row["row_key"],
                            "axis_id": series.get("axis_id"),
                            "period_id": str(index),
                            "value": value,
                            "normalized_value": norms[index] if index < len(norms) else None,
                            "scale_factor": row.get("scale_factor"),
                        }
                    )
    return found


def _keys(alias: str, concept: str) -> int:
    facts = _labeled_facts(alias, concept)
    return len(_sums(facts, {"row_key": facts[0]["row_key"]}))


class _Retainer:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, datetime]] = []

    async def hold(self, key: str, *, mode: str, until: datetime) -> None:
        self.calls.append((key, mode, until))


def test_snapshot_sums_stay_under_the_guard_and_are_logged(caplog):
    packt_cfads = _keys("packt", "cfads")
    packt_debt = _keys("packt", "debt_service")
    rvi_cfads = _keys("rvi", "cfads")
    rvi_debt = _keys("rvi", "debt_service")
    assert packt_cfads == 40
    assert packt_debt == 40
    assert rvi_cfads == 39
    assert rvi_debt == 39
    views = [
        {"cited_cells": [f"cell:{alias}-{name}-{index}" for index in range(count)]}
        for alias, name, count in (
            ("packt", "cfads", packt_cfads),
            ("packt", "debt", packt_debt),
            ("rvi", "cfads", rvi_cfads),
            ("rvi", "debt", rvi_debt),
        )
    ]
    guard_traces(views)
    with caplog.at_level(logging.INFO, logger=LOG):
        log_trace_metrics(cells=packt_cfads + packt_debt, dropped=0, additions=packt_cfads + packt_debt)
        log_trace_metrics(cells=rvi_cfads + rvi_debt, dropped=0, additions=rvi_cfads + rvi_debt)
    assert "calculation_trace_cells=80" in caplog.text
    assert "calculation_trace_dropped=0" in caplog.text
    assert "sums_additions=80" in caplog.text
    assert "sums_additions=78" in caplog.text
    with pytest.raises(TraceLimitError):
        guard_traces([{"cited_cells": [f"cell:{index}" for index in range(513)]}])
    with pytest.raises(TraceLimitError):
        guard_traces([{"cited_cells": ["cell:one"]} for _ in range(65)])


def test_truncation_marks_the_cut_and_keeps_step_links():
    cells = [f"cell:c{index}" for index in range(513)]
    view = limit_trace(
        [
            {"steps": [{"step_id": 1, "operation": "scale_normalization", "input_refs": cells}]},
            {"steps": [{"step_id": 2, "operation": "division", "input_refs": ["step:1", "cell:c0"]}]},
        ]
    )
    assert view["status"] == "truncated"
    assert view["evidence_complete"] is False
    assert view["dropped_cell_count"] == 1
    assert view["status"] != "complete"
    assert "cell:c512" not in view["cited_cells"]
    assert view["cited_cells"][-1] == "cell:c511"
    assert view["dropped_cells"] == ["cell:c512"]
    scale_refs = view["periods"][0]["steps"][0]["input_refs"]
    assert scale_refs[-1] == "truncated:cell:c512"
    assert "cell:c512" not in scale_refs
    assert view["periods"][1]["steps"][0]["input_refs"] == ["step:1", "cell:c0"]
    guard_traces([view])


def test_sums_additions_count_each_added_fact():
    book = EvidenceBook(
        metric="dscr",
        sign_convention="outflow_negative",
        marker_class=None,
        explicit_phases=False,
        plan_content_sha256=None,
    )
    facts = [
        {"row_key": "r", "axis_id": "a", "period_id": "1", "value": "2", "normalized_value": "2"},
        {"row_key": "r", "axis_id": "a", "period_id": "1", "value": "3", "normalized_value": "3"},
        {"row_key": "other", "axis_id": "a", "period_id": "1", "value": "9", "normalized_value": "9"},
    ]
    totals = _sums(facts, {"row_key": "r"}, book=book, concept="cfads")
    assert len(totals) == 1
    assert book.sums_additions == 2


def test_evidence_keeps_roles_window_and_step_links():
    evidence = CalculationEvidence(
        metric="dscr",
        execution_status="computed",
        implementation="dscr@1",
        calculation_stamp="abcd",
        plan_content_sha256=None,
        sign_convention="outflow_negative",
        marker_class=None,
        explicit_phases=True,
        sheet=False,
        fact_observations=(),
        fact_uses=(
            FactUse(
                concept="debt_service",
                cell_id="Debt!D",
                axis_id="Debt!r3",
                period_id="2025",
                timeline_id=None,
                period_index=0,
                field="value",
                sheet=False,
                raw_value=Decimal(1),
                effective_value=Decimal(1),
                scale_factor=None,
                scale_policy="plain",
                scale_applied=False,
                normalization_source="none",
                result_axis_id="Debt!r3",
                result_period_id="2025",
                operand="eligibility",
            ),
        ),
        period_results=(
            PeriodResult(
                axis_id="Debt!r3",
                period_id="2025",
                status="skipped",
                reason="not_coverage_test_period",
                value=None,
                numerator=None,
                denominator=None,
                steps=(
                    TransformationStep(1, "scale_normalization", ("cell:Debt!D",), None, {}),
                    TransformationStep(2, "division", ("step:1",), None, {}),
                ),
                window_periods=("2024-01",),
                window_missing=("2024-02",),
                missing_concepts=(("cfads", ("2024-02",)),),
            ),
        ),
    )
    view = view_from_evidence(evidence)
    assert view["evidence_complete"] is True
    assert view["status"] == "complete"
    assert view["fact_uses"][0]["operand"] == "eligibility"
    assert view["fact_uses"][0]["cell_ref"] == "cell:Debt!D"
    period = view["periods"][0]
    assert period["window_periods"] == ["2024-01"]
    assert period["window_missing"] == ["2024-02"]
    assert period["missing_concepts"] == [["cfads", ["2024-02"]]]
    assert period["steps"][1]["input_refs"] == ["step:1"]


def test_retention_profiles_and_compliance_stays_manual():
    six = retention_policy("sec_17a4", now=NOW)
    five = retention_policy("credit_org_395_1", now=NOW)
    days = retention_policy("days:10", now=NOW)
    assert retention_policy("analysis", now=NOW) is None
    assert six.mode == "GOVERNANCE" and six.until == datetime(2026, 1, 2, tzinfo=UTC)
    assert five.mode == "GOVERNANCE" and five.until == datetime(2025, 1, 2, tzinfo=UTC)
    assert days.mode == "GOVERNANCE" and days.until == NOW + timedelta(days=10)
    leap = retention_policy("sec_17a4", now=datetime(2024, 2, 29, tzinfo=UTC))
    assert leap.until == datetime(2030, 2, 28, tzinfo=UTC)
    with pytest.raises(ValueError, match="COMPLIANCE"):
        retention_policy("COMPLIANCE", now=NOW)
    assert Settings(_env_file=None).fas_trace_retention == "analysis"
    with pytest.raises(ValidationError, match="COMPLIANCE"):
        Settings(_env_file=None, fas_trace_retention="COMPLIANCE")


@pytest.mark.asyncio
async def test_tail_object_pointer_and_deletion(caplog, tmp_path):
    store = LocalStore(tmp_path / "objects")
    pointer = DuckDBTracePointer(tmp_path / "pointers.duckdb")
    retainer = _Retainer()
    cells = [f"cell:c{index}" for index in range(513)]
    with caplog.at_level(logging.INFO, logger=LOG):
        stored = await publish_trace(
            store,
            pointer,
            analysis_id="analysis-1",
            execution_id="exec-1",
            periods=[{"steps": [{"step_id": 1, "operation": "sum", "input_refs": cells}, {"step_id": 2, "operation": "division", "input_refs": ["step:1"]}]}],
            retention="analysis",
            sums_additions=80,
            now=NOW,
            retainer=retainer,
        )
    assert stored["status"] == "truncated"
    assert stored["evidence_complete"] is False
    assert retainer.calls == []
    assert "calculation_trace_cells=512" in caplog.text
    assert "calculation_trace_dropped=1" in caplog.text
    assert "sums_additions=80" in caplog.text
    key = pointer.get("analysis-1", "exec-1")["object_key"]
    assert key == "traces/analysis-1/exec-1.json"
    payload = json.loads(await store.get(key))
    assert payload["dropped_cells"] == ["cell:c512"]
    assert payload["trace"]["evidence_complete"] is False
    assert "cell:c512" not in payload["trace"]["cited_cells"]
    assert payload["trace"]["periods"][0]["steps"][1]["input_refs"] == ["step:1"]
    read = await read_trace(store, pointer, analysis_id="analysis-1", execution_id="exec-1")
    assert read["cited_cells"] == stored["cited_cells"]
    assert "cell:c512" not in read["cited_cells"]

    await store.delete_prefix(key)
    broken = await read_trace(store, pointer, analysis_id="analysis-1", execution_id="exec-1")
    assert broken["reason"] == "pointer_missing"
    assert broken["evidence_complete"] is False
    assert broken["cited_cells"] == []
    assert "cell:c" not in json.dumps(broken)

    await delete_analysis_traces(store, pointer, "analysis-1")
    missing = await read_trace(store, pointer, analysis_id="analysis-1", execution_id="exec-1")
    assert missing["reason"] == "pointer_missing"
    assert pointer.get("analysis-1", "exec-1") is None


@pytest.mark.asyncio
async def test_governance_keeps_the_object_when_the_analysis_is_deleted(tmp_path):
    store = LocalStore(tmp_path / "objects")
    pointer = DuckDBTracePointer(tmp_path / "pointers.duckdb")
    retainer = _Retainer()
    await publish_trace(
        store,
        pointer,
        analysis_id="analysis-2",
        execution_id="exec-2",
        periods=[{"steps": [{"step_id": 1, "operation": "sum", "input_refs": ["cell:keep"]}]}],
        retention="sec_17a4",
        now=NOW,
        retainer=retainer,
    )
    key, mode, until = retainer.calls[0]
    assert key == "traces/analysis-2/exec-2.json"
    assert mode == "GOVERNANCE"
    assert until == datetime(2026, 1, 2, tzinfo=UTC)
    await delete_analysis_traces(store, pointer, "analysis-2")
    row = pointer.get("analysis-2", "exec-2")
    assert row["retained_until"] == "2026-01-02T00:00:00+00:00"
    assert json.loads(await store.get(key))["dropped_cells"] == []
    five = _Retainer()
    await publish_trace(
        store,
        pointer,
        analysis_id="analysis-3",
        execution_id="exec-3",
        periods=[{"steps": [{"step_id": 1, "operation": "sum", "input_refs": ["cell:five"]}]}],
        retention="credit_org_395_1",
        now=NOW,
        retainer=five,
    )
    assert five.calls[0][1] == "GOVERNANCE"
    assert five.calls[0][2] == datetime(2025, 1, 2, tzinfo=UTC)


@pytest.mark.asyncio
async def test_the_sixty_fifth_trace_is_refused(tmp_path):
    store = LocalStore(tmp_path / "objects")
    pointer = DuckDBTracePointer(tmp_path / "pointers.duckdb")
    for index in range(64):
        await publish_trace(
            store,
            pointer,
            analysis_id="analysis-many",
            execution_id=f"exec-{index}",
            periods=[{"steps": [{"step_id": 1, "operation": "sum", "input_refs": ["cell:one"]}]}],
            retention="analysis",
            now=NOW,
        )
    with pytest.raises(TraceLimitError):
        await publish_trace(
            store,
            pointer,
            analysis_id="analysis-many",
            execution_id="exec-64",
            periods=[{"steps": [{"step_id": 1, "operation": "sum", "input_refs": ["cell:extra"]}]}],
            retention="analysis",
            now=NOW,
        )
    assert pointer.count("analysis-many") == 64
    assert pointer.get("analysis-many", "exec-64") is None


def test_minio_governance_retention_is_six_and_five_years():
    import boto3
    from moto import mock_aws

    from finance_analysis.adapters.storage.trace_retention import S3GovernanceRetainer

    recorded = []
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket="trace-lock", ObjectLockEnabledForBucket=True)
        original = client.put_object_retention

        def _remember(**kwargs):
            recorded.append(kwargs)
            return original(**kwargs)

        client.put_object_retention = _remember
        retainer = S3GovernanceRetainer(
            bucket="trace-lock",
            prefix="",
            region="us-east-1",
            access_key="test",
            secret_key="test",
        )
        for name, profile, expected in (
            ("six", "sec_17a4", datetime(2026, 1, 2, tzinfo=UTC)),
            ("five", "credit_org_395_1", datetime(2025, 1, 2, tzinfo=UTC)),
        ):
            client.put_object(Bucket="trace-lock", Key=name, Body=b"{}")
            policy = retention_policy(profile, now=NOW)
            put_object_governance(client, bucket="trace-lock", key=name, until=policy.until)
            assert recorded[-1]["Bucket"] == "trace-lock"
            assert recorded[-1]["Key"] == name
            assert recorded[-1]["Retention"] == {"Mode": "GOVERNANCE", "RetainUntilDate": expected}
            retainer.hold_key(name, until=policy.until)


def test_public_result_does_not_grow_a_trace_field():
    import inspect

    from finance_analysis.application.analyses import Analyses

    assert "calculation_traces" not in inspect.getsource(Analyses.compute_metrics)
    assert "calculation_traces" not in inspect.getsource(Analyses._execute_ratios)
