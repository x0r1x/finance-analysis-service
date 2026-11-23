"""Предел следа, хвост в объекте и указатель. Ожидание замера лежит здесь, не в golden."""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from finance_analysis.adapters.storage.store import LocalStore
from finance_analysis.adapters.storage.trace_pointer import DuckDBTracePointer
from finance_analysis.adapters.storage.trace_retention import put_object_governance
from finance_analysis.application.trace_tail import (
    TracePublishError,
    delete_analysis_traces,
    log_trace_metrics,
    publish_trace,
    read_trace,
    read_trace_archive,
    reconcile_traces,
    sweep_expired_traces,
)
from finance_analysis.domain.calculation_evidence import (
    BasisSide,
    CalculationEvidence,
    EvidenceBook,
    FactObservation,
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
    await delete_analysis_traces(store, pointer, "analysis-2", now=NOW)
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


def _rich_evidence() -> CalculationEvidence:
    return CalculationEvidence(
        metric="dscr",
        execution_status="succeeded",
        implementation="dscr@1",
        calculation_stamp="abcd1234abcd1234",
        plan_content_sha256="plan-sha",
        sign_convention="outflow_negative",
        marker_class="actual",
        explicit_phases=True,
        sheet=False,
        sums_additions=2,
        fact_observations=(
            FactObservation(
                concept="cfads",
                cell_id="CFS!A",
                axis_id="CFS!r3",
                period_id="2025",
                timeline_id="tl",
                period_index=0,
                field="value",
                sheet=False,
                raw_value=Decimal(10),
                effective_value=Decimal(10000),
                scale_factor=Decimal(1000),
                scale_policy="scale",
                scale_applied=True,
                normalization_source="factor",
                considered=None,
            ),
        ),
        fact_uses=(
            FactUse(
                concept="debt_service",
                cell_id="Debt!D",
                axis_id="Debt!r3",
                period_id="2025",
                timeline_id="tl",
                period_index=0,
                field="value",
                sheet=False,
                raw_value=Decimal(4),
                effective_value=Decimal(4000),
                scale_factor=Decimal(1000),
                scale_policy="scale",
                scale_applied=True,
                normalization_source="factor",
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
                numerator=Decimal(10000),
                denominator=Decimal(4000),
                steps=(
                    TransformationStep(
                        1,
                        "scale_normalization",
                        ("cell:Debt!D",),
                        Decimal(4000),
                        {"scale_factor": Decimal(1000)},
                    ),
                ),
                window_periods=("2025",),
                window_missing=(),
                missing_concepts=(),
            ),
        ),
        basis_sides=(BasisSide(concept="cfads", period_basis="period", source="header"),),
    )


def test_trace_schema_keeps_identity_stamp_and_fact_provenance():
    view = view_from_evidence(_rich_evidence())
    assert view["implementation"] == "dscr@1"
    assert view["calculation_stamp"] == "abcd1234abcd1234"
    assert view["plan_content_sha256"] == "plan-sha"
    assert view["execution_status"] == "succeeded"
    assert view["sign_convention"] == "outflow_negative"
    assert view["explicit_phases"] is True
    assert view["sheet"] is False
    assert view["marker_class"] == "actual"
    assert view["sums_additions"] == 2
    assert view["basis_sides"] == [{"concept": "cfads", "period_basis": "period", "source": "header"}]
    observed = view["fact_observations"][0]
    assert observed["scale_factor"] == "1000"
    assert observed["scale_policy"] == "scale"
    assert observed["scale_applied"] is True
    assert observed["normalization_source"] == "factor"
    assert observed["raw_value"] == "10"
    used = view["fact_uses"][0]
    assert used["operand"] == "eligibility"
    assert used["scale_factor"] == "1000"
    assert used["scale_policy"] == "scale"
    assert used["scale_applied"] is True
    assert used["normalization_source"] == "factor"
    step = view["periods"][0]["steps"][0]
    assert step["output_value"] == "4000"
    assert step["parameters"] == {"scale_factor": "1000"}


@pytest.mark.asyncio
async def test_publish_keeps_mappingproxy_step_parameters(tmp_path):
    from types import MappingProxyType

    book = EvidenceBook(
        metric="dscr",
        sign_convention="outflow_negative",
        marker_class=None,
        explicit_phases=False,
        plan_content_sha256=None,
    )
    book.periods.append(
        PeriodResult(
            axis_id="Debt!r3",
            period_id="2025",
            status="computed",
            reason=None,
            value=Decimal("2.71"),
            numerator=Decimal("8129962.942385"),
            denominator=Decimal("3000000.000000"),
            steps=(
                TransformationStep(
                    1,
                    "divide",
                    ("cell:A",),
                    Decimal("2.71"),
                    MappingProxyType(
                        {
                            "numerator": Decimal("8129962.942385"),
                            "denominator": Decimal("3000000.000000"),
                        }
                    ),
                ),
            ),
        )
    )
    evidence = book.freeze("succeeded", "dscr@1")
    store = LocalStore(tmp_path / "objects")
    pointer = DuckDBTracePointer(tmp_path / "pointers.duckdb")
    await publish_trace(
        store,
        pointer,
        analysis_id="analysis-proxy",
        execution_id="exec-proxy",
        evidence=evidence,
        retention="analysis",
        now=NOW,
    )
    payload = json.loads(await store.get("traces/analysis-proxy/exec-proxy.json"))
    assert payload["trace"]["periods"][0]["steps"][0]["parameters"] == {
        "numerator": "8129962.942385",
        "denominator": "3000000.000000",
    }


@pytest.mark.asyncio
async def test_publication_logs_the_book_additions(caplog, tmp_path):
    book = EvidenceBook(
        metric="dscr",
        sign_convention="outflow_negative",
        marker_class=None,
        explicit_phases=False,
        plan_content_sha256=None,
    )
    facts = [
        {"row_key": "r", "axis_id": "a", "period_id": "1", "value": "2", "normalized_value": "2"},
        {"row_key": "r", "axis_id": "a", "period_id": "2", "value": "3", "normalized_value": "3"},
    ]
    _sums(facts, {"row_key": "r"}, book=book, concept="cfads")
    evidence = book.freeze("succeeded", "dscr@1")
    store = LocalStore(tmp_path / "objects")
    pointer = DuckDBTracePointer(tmp_path / "pointers.duckdb")
    with caplog.at_level(logging.INFO, logger=LOG):
        await publish_trace(
            store,
            pointer,
            analysis_id="analysis-sums",
            execution_id="exec-sums",
            evidence=evidence,
            retention="analysis",
            now=NOW,
        )
    assert "sums_additions=2" in caplog.text


@pytest.mark.asyncio
async def test_read_trace_archive_keeps_dropped_cells(tmp_path):
    store = LocalStore(tmp_path / "objects")
    pointer = DuckDBTracePointer(tmp_path / "pointers.duckdb")
    cells = [f"cell:c{index}" for index in range(513)]
    await publish_trace(
        store,
        pointer,
        analysis_id="analysis-archive",
        execution_id="exec-archive",
        periods=[{"steps": [{"step_id": 1, "operation": "sum", "input_refs": cells}]}],
        retention="analysis",
        now=NOW,
    )
    await publish_trace(
        store,
        pointer,
        analysis_id="analysis-archive",
        execution_id="exec-archive",
        periods=[{"steps": [{"step_id": 1, "operation": "sum", "input_refs": cells}]}],
        retention="analysis",
        now=NOW,
    )
    assert pointer.count("analysis-archive") == 1
    compact = await read_trace(store, pointer, analysis_id="analysis-archive", execution_id="exec-archive")
    archive = await read_trace_archive(store, pointer, analysis_id="analysis-archive", execution_id="exec-archive")
    assert "cell:c512" not in compact["cited_cells"]
    assert "dropped_cells" not in compact
    assert archive["dropped_cells"] == ["cell:c512"]
    assert archive["trace"]["evidence_complete"] is False


def test_parallel_reserve_stops_at_sixty_four(tmp_path):
    import asyncio
    import threading

    pointer = DuckDBTracePointer(tmp_path / "pointers.duckdb")
    store = LocalStore(tmp_path / "objects")

    async def _fill() -> None:
        for index in range(63):
            await publish_trace(
                store,
                pointer,
                analysis_id="analysis-race",
                execution_id=f"exec-{index}",
                periods=[{"steps": [{"step_id": 1, "operation": "sum", "input_refs": ["cell:one"]}]}],
                retention="analysis",
                now=NOW,
            )

    asyncio.run(_fill())
    barrier = threading.Barrier(2)
    outcomes: list[object] = []

    def _once(execution_id: str) -> None:
        barrier.wait()

        async def _publish() -> None:
            await publish_trace(
                store,
                pointer,
                analysis_id="analysis-race",
                execution_id=execution_id,
                periods=[{"steps": [{"step_id": 1, "operation": "sum", "input_refs": ["cell:one"]}]}],
                retention="analysis",
                now=NOW,
            )

        try:
            asyncio.run(_publish())
            outcomes.append("ok")
        except TraceLimitError:
            outcomes.append("limited")

    threads = [threading.Thread(target=_once, args=(f"exec-extra-{index}",)) for index in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(outcomes) == ["limited", "ok"]
    assert pointer.count("analysis-race") == 64


class _Boom:
    async def hold(self, key: str, *, mode: str, until: datetime) -> None:
        raise RuntimeError("lock failed")


@pytest.mark.asyncio
async def test_hold_failure_does_not_leave_a_locked_object_without_a_pointer(tmp_path):
    store = LocalStore(tmp_path / "objects")
    pointer = DuckDBTracePointer(tmp_path / "pointers.duckdb")
    with pytest.raises(TracePublishError) as raised:
        await publish_trace(
            store,
            pointer,
            analysis_id="analysis-hold",
            execution_id="exec-hold",
            periods=[{"steps": [{"step_id": 1, "operation": "sum", "input_refs": ["cell:keep"]}]}],
            retention="sec_17a4",
            now=NOW,
            retainer=_Boom(),
        )
    assert raised.value.stage == "retention"
    assert isinstance(raised.value.__cause__, RuntimeError)
    row = pointer.get("analysis-hold", "exec-hold")
    assert row is not None
    assert row["state"] == "pending_retention"
    assert await store.stat("traces/analysis-hold/exec-hold.json") is not None
    report = await reconcile_traces(store, pointer)
    assert row["object_key"] in report["held"]
    assert row["object_key"] in report["unfinished"]
    assert row["object_key"] not in report["committed"]
    assert pointer.get("analysis-hold", "exec-hold")["state"] == "pending_retention"


@pytest.mark.asyncio
async def test_pointer_commit_failure_stays_pending_until_reconcile(tmp_path):
    store = LocalStore(tmp_path / "objects")
    pointer = DuckDBTracePointer(tmp_path / "pointers.duckdb")

    def _fail(row: dict) -> None:
        raise RuntimeError("commit failed")

    original = pointer.commit
    pointer.commit = _fail  # type: ignore[method-assign]
    with pytest.raises(TracePublishError) as raised:
        await publish_trace(
            store,
            pointer,
            analysis_id="analysis-commit",
            execution_id="exec-commit",
            periods=[{"steps": [{"step_id": 1, "operation": "sum", "input_refs": ["cell:keep"]}]}],
            retention="analysis",
            now=NOW,
        )
    pointer.commit = original
    assert raised.value.stage == "pointer"
    assert isinstance(raised.value.__cause__, RuntimeError)
    pending = pointer.get("analysis-commit", "exec-commit")
    assert pending is not None
    assert pending["state"] == "pending_commit"
    assert await store.stat("traces/analysis-commit/exec-commit.json") is not None
    await store.put("traces/analysis-commit/orphan.json", b"{}")
    report = await reconcile_traces(store, pointer)
    assert pointer.get("analysis-commit", "exec-commit")["state"] == "committed"
    assert "traces/analysis-commit/orphan.json" in report["orphans"]


@pytest.mark.asyncio
async def test_expired_retention_is_deleted_and_swept(tmp_path):
    store = LocalStore(tmp_path / "objects")
    pointer = DuckDBTracePointer(tmp_path / "pointers.duckdb")
    retainer = _Retainer()
    await publish_trace(
        store,
        pointer,
        analysis_id="analysis-expire",
        execution_id="exec-expire",
        periods=[{"steps": [{"step_id": 1, "operation": "sum", "input_refs": ["cell:keep"]}]}],
        retention="days:10",
        now=NOW,
        retainer=retainer,
    )
    await delete_analysis_traces(store, pointer, "analysis-expire", now=NOW)
    assert pointer.get("analysis-expire", "exec-expire") is not None
    await delete_analysis_traces(store, pointer, "analysis-expire", now=NOW + timedelta(days=11))
    assert pointer.get("analysis-expire", "exec-expire") is None
    assert await store.stat("traces/analysis-expire/exec-expire.json") is None
    await publish_trace(
        store,
        pointer,
        analysis_id="analysis-sweep",
        execution_id="exec-sweep",
        periods=[{"steps": [{"step_id": 1, "operation": "sum", "input_refs": ["cell:keep"]}]}],
        retention="days:10",
        now=NOW,
        retainer=retainer,
    )
    await sweep_expired_traces(store, pointer, now=NOW + timedelta(days=11))
    assert pointer.get("analysis-sweep", "exec-sweep") is None


@pytest.mark.asyncio
async def test_analysis_publish_writes_the_object_and_the_pointer(tmp_path):
    from finance_analysis.application.analyses import Analyses

    store = LocalStore(tmp_path / "objects")
    pointer = DuckDBTracePointer(tmp_path / "pointers.duckdb")

    class _Host:
        def __init__(self) -> None:
            self.store = store
            self.service = type("Svc", (), {})()
            self.service.store = store
            self.service.trace_pointer = pointer
            self.service.trace_retainer = None
            self.service.settings = Settings(_env_file=None)

    await Analyses._publish_traces(_Host(), "01ARZ3NDEKTSV4RRFFQ69G5FAV", [_rich_evidence()])
    rows = pointer.list_analysis("01ARZ3NDEKTSV4RRFFQ69G5FAV")
    assert len(rows) == 1
    assert rows[0]["state"] == "committed"
    payload = json.loads(await store.get(rows[0]["object_key"]))
    assert payload["trace"]["implementation"] == "dscr@1"
    assert payload["trace"]["sums_additions"] == 2
    assert payload["dropped_cells"] == []


def test_public_result_does_not_grow_a_trace_field():
    import inspect

    from finance_analysis.application.analyses import Analyses

    assert "calculation_traces" not in inspect.getsource(Analyses.compute_metrics)
    assert "calculation_traces" not in inspect.getsource(Analyses._execute_ratios)


class _Sticky(LocalStore):
    async def delete_prefix(self, prefix: str) -> int:
        raise RuntimeError("delete failed")


@pytest.mark.asyncio
async def test_failed_hold_and_failed_delete_stays_pending_retention(tmp_path):
    store = _Sticky(tmp_path / "objects")
    pointer = DuckDBTracePointer(tmp_path / "pointers.duckdb")
    with pytest.raises(TracePublishError) as raised:
        await publish_trace(
            store,
            pointer,
            analysis_id="analysis-stuck",
            execution_id="exec-stuck",
            periods=[{"steps": [{"step_id": 1, "operation": "sum", "input_refs": ["cell:keep"]}]}],
            retention="sec_17a4",
            now=NOW,
            retainer=_Boom(),
        )
    assert raised.value.stage == "retention"
    row = pointer.get("analysis-stuck", "exec-stuck")
    assert row is not None
    assert row["state"] == "pending_retention"
    report = await reconcile_traces(store, pointer)
    assert pointer.get("analysis-stuck", "exec-stuck")["state"] == "pending_retention"
    assert row["object_key"] in report["held"]
    assert row["object_key"] not in report["committed"]


def _reserve_many(path: str, analysis: str, start: int, count: int, queue) -> None:
    pointer = DuckDBTracePointer(Path(path))
    refused = 0
    for index in range(start, start + count):
        try:
            pointer.reserve(
                analysis,
                f"exec-{index}",
                object_key=f"traces/{analysis}/exec-{index}.json",
                evidence_complete=True,
                dropped_cell_count=0,
                retained_until=None,
            )
        except TraceLimitError:
            refused += 1
    queue.put(refused)


def test_two_pointer_instances_share_the_sixty_four_limit(tmp_path):
    import threading

    path = tmp_path / "shared.duckdb"
    DuckDBTracePointer(path).count("warm")
    barrier = threading.Barrier(2)
    errors: list[int] = []

    def run(start: int) -> None:
        pointer = DuckDBTracePointer(path)
        barrier.wait()
        for index in range(start, start + 40):
            try:
                pointer.reserve(
                    "analysis-two",
                    f"exec-{index}",
                    object_key=f"k-{index}",
                    evidence_complete=True,
                    dropped_cell_count=0,
                    retained_until=None,
                )
            except TraceLimitError:
                errors.append(index)

    threads = [threading.Thread(target=run, args=(0,)), threading.Thread(target=run, args=(40,))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert DuckDBTracePointer(path).count("analysis-two") == 64
    assert len(errors) == 16


def test_two_processes_share_the_sixty_four_limit(tmp_path):
    import multiprocessing

    path = tmp_path / "shared.duckdb"
    DuckDBTracePointer(path).count("warm")
    context = multiprocessing.get_context("fork")
    queue = context.Queue()
    first = context.Process(target=_reserve_many, args=(str(path), "analysis-proc", 0, 40, queue))
    second = context.Process(target=_reserve_many, args=(str(path), "analysis-proc", 40, 40, queue))
    first.start()
    second.start()
    first.join(30)
    second.join(30)
    assert first.exitcode == 0
    assert second.exitcode == 0
    refused = queue.get() + queue.get()
    assert DuckDBTracePointer(path).count("analysis-proc") == 64
    assert refused == 16


def test_observation_cap_strips_values_past_the_limit():
    observations = tuple(
        FactObservation(
            concept="cfads",
            cell_id=f"CFS!{index}",
            axis_id="CFS!r3",
            period_id="2025",
            timeline_id="tl",
            period_index=index,
            field="value",
            sheet=False,
            raw_value=Decimal(index),
            effective_value=Decimal(index),
            scale_factor=Decimal(1000),
            scale_policy="scale",
            scale_applied=True,
            normalization_source="factor",
        )
        for index in range(513)
    )
    evidence = CalculationEvidence(
        metric="dscr",
        execution_status="succeeded",
        implementation="dscr@1",
        calculation_stamp="abcd1234abcd1234",
        plan_content_sha256=None,
        sign_convention="outflow_negative",
        marker_class=None,
        explicit_phases=False,
        sheet=False,
        fact_observations=observations,
        fact_uses=(),
        period_results=(),
    )
    view = view_from_evidence(evidence)
    assert view["observation_count"] == 513
    assert view["observation_dropped_count"] == 1
    assert view["observation_status"] == "truncated"
    assert view["evidence_complete"] is True
    assert "raw_value" not in view["dropped_observations"][0]
    assert "effective_value" not in view["dropped_observations"][0]
    assert "scale_factor" not in view["dropped_observations"][0]
    assert view["fact_observations"][0]["raw_value"] == "0"


@pytest.mark.asyncio
async def test_object_byte_limit_strips_observation_values(tmp_path, monkeypatch):
    monkeypatch.setattr("finance_analysis.application.trace_tail.OBJECT_BYTE_LIMIT", 1)
    store = LocalStore(tmp_path / "objects")
    pointer = DuckDBTracePointer(tmp_path / "pointers.duckdb")
    with pytest.raises(TraceLimitError):
        await publish_trace(
            store,
            pointer,
            analysis_id="analysis-bytes",
            execution_id="exec-bytes",
            evidence=_rich_evidence(),
            retention="analysis",
            now=NOW,
        )
    assert pointer.get("analysis-bytes", "exec-bytes") is None


def test_every_catalog_metric_names_its_evidence():
    from finance_analysis.application.analyses import RATIO_METRICS, evidence_matrix

    rows = evidence_matrix()
    assert {row[0] for row in rows} == set(RATIO_METRICS)
    assert {row[2] for row in rows} <= {"evidence_available", "evidence_not_supported"}
    available = {(metric, implementation) for metric, implementation, status in rows if status == "evidence_available"}
    assert available == {
        ("dscr", "dscr@1"),
        ("dscr", "dscr.pf@1"),
        ("icr", "icr@1"),
        ("icr_ebit", "icr_ebit@1"),
        ("adscr", "adscr@1"),
        ("dscr_min", "dscr_min@1"),
        ("dscr_avg", "dscr_avg@1"),
    }
    missing = {(metric, implementation) for metric, implementation, status in rows if status == "evidence_not_supported"}
    assert ("llcr", "llcr@1") in missing
    assert ("plcr", "plcr@1") in missing
    assert ("icr", "icr.bank@1") in missing
    assert ("dscr", "dscr.housing@1") in missing
    assert ("llcr", "llcr.domrf@1") in missing
    assert any(metric == "escrow_coverage" and status == "evidence_not_supported" for metric, _, status in rows)


@pytest.mark.asyncio
async def test_delete_checks_the_parent_analysis(tmp_path):
    import inspect

    from finance_analysis.adapters.api.route import analyses as route
    from finance_analysis.application import keys
    from finance_analysis.application.analyses import Analyses
    from finance_analysis.domain.errors import NotFound

    job = "ab" * 32
    own = "01ARZ3NDEKTSV4RRFFQ69G5FAV"
    foreign = "01ARZ3NDEKTSV4RRFFQ69G5FAW"
    build = "bbbbbbbbbbbbbbbb"
    store = LocalStore(tmp_path / "objects")
    pointer = DuckDBTracePointer(tmp_path / "pointers.duckdb")
    host = type("Svc", (), {})()
    host.store = store
    host.trace_pointer = pointer
    analyses = Analyses(host)
    await store.put(keys.report_index_key(job, own), json.dumps({"analysis_id": own, "build_key": build}).encode())
    await store.put(keys.result_key(job, build, own, "result.json"), b"{}")
    for analysis_id in (own, foreign):
        await publish_trace(
            store,
            pointer,
            analysis_id=analysis_id,
            execution_id="exec-one",
            periods=[{"steps": [{"step_id": 1, "operation": "sum", "input_refs": ["cell:keep"]}]}],
            retention="analysis",
            now=NOW,
        )
    with pytest.raises(NotFound) as raised:
        await analyses.delete(job, foreign)
    assert raised.value.status == 404
    assert pointer.get(foreign, "exec-one") is not None
    assert pointer.get(own, "exec-one") is not None
    assert await store.stat(keys.report_index_key(job, own)) is not None
    removed = await analyses.delete(job, own)
    assert removed["traces_removed"] == 1
    assert pointer.get(own, "exec-one") is None
    assert pointer.get(foreign, "exec-one") is not None
    assert await store.stat(keys.report_index_key(job, own)) is None
    assert await store.stat(keys.result_key(job, build, own, "result.json")) is None
    text = inspect.getsource(route.register)
    delete = text.split("async def delete_analysis")[1].split("async def get_analysis")[0]
    read = text.split("async def get_analysis")[1].split("async def get_report")[0]
    assert "actor(request)" in delete and "limited(request, who)" in delete and "user_inflight" in delete
    assert "actor(request)" in read and "limited(request, who)" in read and "user_inflight" in read


_SENTINEL = Decimal("2.718281828")


class _PutFails(LocalStore):
    async def put_if_absent(self, key: str, data: bytes):
        if key.startswith("traces/"):
            raise RuntimeError("put failed")
        return await super().put_if_absent(key, data)


def _ratio_got() -> dict:
    evidence = _rich_evidence()
    return {
        "rows": [
            {
                "metric": "dscr",
                "axis_id": "Debt!r3",
                "period_id": "2025",
                "value": _SENTINEL,
                "status": "computed",
            }
        ],
        "needs_input": [],
        "warnings": [],
        "bindings": [],
        "facts": [],
        "periods": [],
        "phase_of": {},
        "profile": {},
        "absent": frozenset(),
        "evidences": [evidence],
        "applicability": [
            {"metric": "dscr", "applicability": "applicable"},
            {"metric": "icr", "applicability": "not_applicable"},
        ],
        "model_type": "project_finance",
    }


def _ratio_target():
    from finance_analysis.application.analyses import Target
    from finance_analysis.domain.book import Head

    head = Head(build_key="build", state_seq=1, derive_key="derive", versions={})
    return Target(head=head, build="build", manifest={}, fresh=True)


def _ratio_analyses(store, pointer, *, retention: str, retainer=None, got: dict | None = None):
    from types import SimpleNamespace

    from finance_analysis.application.analyses import Analyses
    from finance_analysis.settings import Settings

    service = SimpleNamespace(
        store=store,
        trace_pointer=pointer,
        trace_retainer=retainer,
        settings=Settings(_env_file=None, fas_trace_retention=retention),
        model_types=SimpleNamespace(version="e5e47aa50edf3a3e"),
    )
    analyses = Analyses(service)
    payload = got if got is not None else _ratio_got()

    async def _metrics(job_id, target, metrics):
        return payload

    async def _findings(*args, **kwargs):
        return []

    async def _annotate(envelope):
        return None

    async def _save(job_id, target, analysis_id, kind, tables, envelope, actor, started):
        analyses.saved = envelope

    analyses.compute_metrics = _metrics
    analyses._metric_findings = _findings
    analyses._annotate = _annotate
    analyses._save_tables = _save
    return analyses, payload


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["put", "retention", "pointer"])
async def test_trace_write_failure_keeps_the_analysis(tmp_path, caplog, stage, monkeypatch):
    from prometheus_client import REGISTRY

    from finance_analysis.application.trace_tail import reconcile_traces
    from finance_analysis.domain.book import Actor

    monkeypatch.setattr("finance_analysis.application.analyses.ratio_cells", lambda *args, **kwargs: [])
    retainer = _Boom() if stage == "retention" else None
    store = _PutFails(tmp_path / "objects") if stage == "put" else LocalStore(tmp_path / "objects")
    pointer = DuckDBTracePointer(tmp_path / "pointers.duckdb")
    retention = "sec_17a4" if stage == "retention" else "analysis"
    analyses, _payload = _ratio_analyses(store, pointer, retention=retention, retainer=retainer)
    original = pointer.commit
    if stage == "pointer":

        def _fail(row: dict) -> None:
            raise RuntimeError("commit failed")

        pointer.commit = _fail  # type: ignore[method-assign]
    before = REGISTRY.get_sample_value("fas_trace_write_failures_total") or 0
    analysis_id = "01ARZ3NDEKTSV4RRFFQ69G5FAV"
    with caplog.at_level(logging.ERROR, logger="fas.trace"):
        envelope = await analyses._execute_ratios("job", _ratio_target(), analysis_id, ["dscr"], {}, Actor())
    if stage == "pointer":
        pointer.commit = original  # type: ignore[method-assign]
    assert envelope["status"] == "succeeded"
    assert envelope["result_data"]["ratios"][0]["value"] == "2.718281828"
    assert analyses.saved["status"] == "succeeded"
    assert all(item["evidence_complete"] is False for item in envelope["result_data"]["metrics"])
    assert {item["metric"] for item in envelope["result_data"]["metrics"]} == {"dscr", "icr"}
    after = REGISTRY.get_sample_value("fas_trace_write_failures_total") or 0
    assert after == before + 1
    errors = [record for record in caplog.records if record.levelname == "ERROR"]
    assert len(errors) == 1
    message = errors[0].getMessage()
    assert analysis_id in message
    assert "dscr-0" in message
    assert f"stage={stage}" in message
    assert "RuntimeError" in message
    assert "2.718281828" not in caplog.text
    assert "10000" not in caplog.text
    assert "put failed" not in message
    assert "lock failed" not in message
    assert "commit failed" not in message
    row = pointer.get(analysis_id, "dscr-0")
    assert row is not None
    report = await reconcile_traces(store, pointer)
    key = row["object_key"]
    if stage == "put":
        assert row["state"] == "pending_object"
        assert await store.stat(key) is None
        assert key in report["unfinished"]
        assert key not in report["committed"]
    elif stage == "retention":
        assert row["state"] == "pending_retention"
        assert await store.stat(key) is not None
        assert key in report["unfinished"]
        assert key in report["held"]
        assert key not in report["committed"]
        assert pointer.get(analysis_id, "dscr-0")["state"] == "pending_retention"
    else:
        assert row["state"] == "pending_commit"
        assert key in report["committed"]
        assert pointer.get(analysis_id, "dscr-0")["state"] == "committed"


@pytest.mark.asyncio
async def test_metric_calculation_failure_still_fails_the_analysis(tmp_path, caplog):
    from prometheus_client import REGISTRY

    from finance_analysis.domain.book import Actor

    store = LocalStore(tmp_path / "objects")
    pointer = DuckDBTracePointer(tmp_path / "pointers.duckdb")
    analyses, _payload = _ratio_analyses(store, pointer, retention="analysis")

    async def _boom(job_id, target, metrics):
        raise RuntimeError("metric failed")

    analyses.compute_metrics = _boom
    before = REGISTRY.get_sample_value("fas_trace_write_failures_total") or 0
    with caplog.at_level(logging.ERROR, logger="fas.trace"), pytest.raises(RuntimeError, match="metric failed"):
        await analyses._execute_ratios("job", _ratio_target(), "01ARZ3NDEKTSV4RRFFQ69G5FAV", ["dscr"], {}, Actor())
    after = REGISTRY.get_sample_value("fas_trace_write_failures_total") or 0
    assert after == before
    assert not [record for record in caplog.records if record.levelname == "ERROR"]
    assert pointer.list_analysis("01ARZ3NDEKTSV4RRFFQ69G5FAV") == []


@pytest.mark.asyncio
async def test_byte_limit_keeps_the_analysis(tmp_path, monkeypatch, caplog):
    from prometheus_client import REGISTRY

    from finance_analysis.domain.book import Actor

    monkeypatch.setattr("finance_analysis.application.trace_tail.OBJECT_BYTE_LIMIT", 1)
    store = LocalStore(tmp_path / "objects")
    pointer = DuckDBTracePointer(tmp_path / "pointers.duckdb")
    analyses, _payload = _ratio_analyses(store, pointer, retention="analysis")
    before = REGISTRY.get_sample_value("fas_trace_write_failures_total") or 0
    with caplog.at_level(logging.ERROR, logger="fas.trace"):
        envelope = await analyses._execute_ratios(
            "job", _ratio_target(), "01ARZ3NDEKTSV4RRFFQ69G5FAV", ["dscr"], {}, Actor()
        )
    assert envelope["status"] == "succeeded"
    assert envelope["result_data"]["ratios"][0]["value"] == "2.718281828"
    assert all(item["evidence_complete"] is False for item in envelope["result_data"]["metrics"])
    assert "stage=limit" in caplog.text
    assert "2.718281828" not in caplog.text
    after = REGISTRY.get_sample_value("fas_trace_write_failures_total") or 0
    assert after == before + 1


def test_fit_object_shrinks_an_empty_observation_list_to_the_limit():
    from finance_analysis.domain.trace_limit import fit_object

    view = {
        "fact_observations": [],
        "dropped_observations": [],
        "periods": [
            {
                "period_id": "Y",
                "steps": [
                    {
                        "operation": "sum",
                        "parameters": {"blob": "x" * 4000},
                        "input_refs": [f"cell:{index}" for index in range(40)],
                    }
                ],
            }
        ],
        "fact_uses": [{"raw_value": "9" * 500, "effective_value": "9" * 500, "scale_factor": "1000"}],
        "cited_cells": [],
    }
    envelope = {"analysis_id": "a", "execution_id": "e", "dropped_cells": ["cell:z"] * 80}
    body = fit_object(view, envelope, byte_limit=900)
    assert len(body) <= 900


def test_fit_object_raises_when_nothing_smaller_fits():
    from finance_analysis.domain.trace_limit import fit_object

    with pytest.raises(TraceLimitError):
        fit_object(
            {"fact_observations": [], "periods": [{"note": "x" * 50}]},
            {"id": "a"},
            byte_limit=1,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["pending_commit", "pending_retention"])
async def test_repeat_unfinished_publish_rejects_a_different_body(tmp_path, stage):
    from finance_analysis.domain.errors import InvalidArgument

    store = LocalStore(tmp_path / "objects")
    pointer = DuckDBTracePointer(tmp_path / "pointers.duckdb")
    periods = [{"steps": [{"step_id": 1, "operation": "sum", "input_refs": ["cell:keep"]}]}]
    other = [{"steps": [{"step_id": 1, "operation": "sum", "input_refs": ["cell:other"]}]}]
    kwargs = {
        "analysis_id": "analysis-replay",
        "execution_id": "exec-replay",
        "periods": periods,
        "now": NOW,
    }
    if stage == "pending_commit":

        def _fail(row: dict) -> None:
            raise RuntimeError("commit failed")

        pointer.commit = _fail  # type: ignore[method-assign]
        with pytest.raises(TracePublishError):
            await publish_trace(store, pointer, retention="analysis", **kwargs)
    else:
        with pytest.raises(TracePublishError):
            await publish_trace(store, pointer, retention="sec_17a4", retainer=_Boom(), **kwargs)
    before = pointer.get("analysis-replay", "exec-replay")
    assert before is not None
    assert before["state"] == stage
    second = dict(kwargs)
    second["periods"] = other
    with pytest.raises(TracePublishError) as raised:
        await publish_trace(
            store,
            pointer,
            retention="sec_17a4" if stage == "pending_retention" else "analysis",
            retainer=_Boom() if stage == "pending_retention" else None,
            **second,
        )
    assert raised.value.stage == "put"
    assert isinstance(raised.value.__cause__, InvalidArgument)
    again = pointer.get("analysis-replay", "exec-replay")
    assert again["state"] == stage
    assert again["state"] != "committed"


@pytest.mark.asyncio
async def test_governance_hold_is_readable(minio_endpoint):
    """moto GetObjectRetention отвечает 500. Читаем замок у MinIO, если он свободен."""

    import boto3

    from finance_analysis.adapters.storage.trace_retention import S3GovernanceRetainer

    until = datetime(2030, 1, 2, tzinfo=UTC)
    client = boto3.client(
        "s3",
        endpoint_url=minio_endpoint,
        aws_access_key_id="minioadmin",
        aws_secret_access_key="minioadmin",
        region_name="ap-northeast-1",
    )
    bucket = f"trace-lock-{os.getpid()}"
    client.create_bucket(
        Bucket=bucket,
        CreateBucketConfiguration={"LocationConstraint": "ap-northeast-1"},
        ObjectLockEnabledForBucket=True,
    )
    client.put_object(Bucket=bucket, Key="kept", Body=b"{}")
    retainer = S3GovernanceRetainer(
        bucket=bucket,
        endpoint=minio_endpoint,
        region="ap-northeast-1",
        access_key="minioadmin",
        secret_key="minioadmin",
    )
    await retainer.hold("kept", mode="GOVERNANCE", until=until)
    found = client.get_object_retention(Bucket=bucket, Key="kept")
    assert found["Retention"]["Mode"] == "GOVERNANCE"
    assert found["Retention"]["RetainUntilDate"].replace(tzinfo=UTC) == until


def test_sweep_task_is_on_the_scheduler():
    from finance_analysis.adapters.queue.tasks import SWEEP_TRACES_TASK, register_tasks

    class _Broker:
        def __init__(self) -> None:
            self.tasks = []

        def register_task(self, fn, task_name=None, schedule=None, **kwargs):
            self.tasks.append((task_name, schedule))

    broker = _Broker()
    register_tasks(broker, schedules=True, cron="0 3 * * *", settings=None)
    scheduled = {name: schedule for name, schedule in broker.tasks}
    assert scheduled[SWEEP_TRACES_TASK] == [{"cron": "15 3 * * *"}]


@pytest.mark.asyncio
async def test_sweep_task_removes_an_expired_trace(tmp_path):
    from prometheus_client import REGISTRY

    from finance_analysis.adapters.queue import runtime as runtime_mod
    from finance_analysis.adapters.queue.runtime import WorkerRuntime
    from finance_analysis.adapters.queue.tasks import sweep_traces

    class _Locks:
        def try_lock(self, name: str, ttl_ms: int):
            class _Guard:
                async def __aenter__(self):
                    return 1

                async def __aexit__(self, *args):
                    return None

            return _Guard()

    store = LocalStore(tmp_path / "objects")
    settings = Settings(_env_file=None, fas_data_dir=str(tmp_path / "data"))
    from finance_analysis.adapters.storage.trace_wiring import open_trace_tail

    pointer, _retainer = open_trace_tail(settings)
    await publish_trace(
        store,
        pointer,
        analysis_id="analysis-sweep-runtime",
        execution_id="exec-old",
        periods=[{"steps": [{"step_id": 1, "operation": "sum", "input_refs": ["cell:keep"]}]}],
        retention="days:10",
        now=NOW,
        retainer=_Retainer(),
    )
    assert pointer.get("analysis-sweep-runtime", "exec-old") is not None
    before = REGISTRY.get_sample_value("fas_trace_swept_total") or 0
    previous = runtime_mod.RUNTIME
    runtime_mod.RUNTIME = WorkerRuntime(
        settings=settings,
        redis=None,
        store=store,
        schedule=None,
        broker=None,
        locks=_Locks(),
    )
    try:
        removed = await sweep_traces(now=NOW + timedelta(days=11))
    finally:
        runtime_mod.RUNTIME = previous
    assert removed["removed"] == 1
    assert pointer.get("analysis-sweep-runtime", "exec-old") is None
    assert await store.stat("traces/analysis-sweep-runtime/exec-old.json") is None
    after = REGISTRY.get_sample_value("fas_trace_swept_total") or 0
    assert after == before + 1
